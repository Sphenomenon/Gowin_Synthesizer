#!/usr/bin/env python3
"""Compare operation-specific command admission with the complete old owner."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import z3
import run_ae350_pcm_window_gate as whole


def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def require(ok,message):
    if not ok:raise ValueError('PCM control admission: '+message)


def proof():
    address=z3.BitVec('address',12);data=z3.BitVec('data',32);strobes=z3.BitVec('strobes',4)
    accepted,writing,saturated,window_error,*errors=z3.Bools('accepted writing saturated window_error e1 e2 e3 e4 e5')
    full=z3.And(strobes==15,z3.Extract(1,0,address)==0)
    stage=z3.And(z3.UGE(address,0x020),z3.ULE(address,0x03c))
    upper=z3.Extract(11,11,address)==1
    cmd_error=z3.Or(saturated,z3.If(data==1,errors[0],z3.If(data==2,errors[1],z3.If(data==3,errors[2],z3.If(data==4,errors[3],z3.If(data==5,errors[4],True))))))
    response=z3.If(writing,z3.If(z3.Not(full),True,z3.If(upper,window_error,z3.If(stage,False,z3.If(address==0x040,cmd_error,True)))),z3.Extract(1,0,address)!=0)
    common=z3.And(accepted,writing,full,address==0x040,z3.Not(saturated))
    outcomes={}
    for n,error in enumerate(errors,1):
        old=z3.And(accepted,writing,z3.Not(response),address==0x040,data==n)
        new=z3.And(common,data==n,z3.Not(error))
        s=z3.Solver();s.add(old!=new);require(s.check()==z3.unsat,'symbolic operation differs');outcomes[str(n)]='UNSAT'
    old=z3.And(accepted,writing,z3.Not(response),z3.Not(upper),stage)
    new=z3.And(accepted,writing,full,z3.Not(upper),stage)
    s=z3.Solver();s.add(old!=new);require(s.check()==z3.unsat,'symbolic staging differs')
    return dict(operation_acceptance=outcomes,staging='UNSAT',free_bits=57,unreachable_state_assumptions=False,z3_version=z3.get_version_string())


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    require(whole.sha(whole.REFERENCE)==whole.REFERENCE_SHA256,'frozen whole owner changed')
    original=whole.SOURCE.read_text();inputs={str(p):sha(p) for p in [whole.SOURCE,whole.REFERENCE,Path(__file__).resolve(),Path(whole.__file__).resolve(),whole.ROOT/'sim/test_ae350_pcm_owner.py']}
    reference=out/'reference.sv';reference.write_text(whole.REFERENCE.read_text().replace('module workstation_ae350_pcm_owner','module pcm_owner_window_reference',1))
    bench=whole.bench()
    checks='integer control_checks=0;\nalways @(posedge clk)if(rst && cpu)begin\n'
    for n,name in enumerate(['start','commit','select','stop','cancel'],1):
        checks+=f' if(dut.accepted_{name} !== (old_owner.accepted && old_owner.command_write_i && !old_owner.response_error_o && old_owner.command_address_i==12\'h040 && old_owner.command_data_i==32\'d{n}))$fatal(1,"control admission mismatch: {name}");\n'
    checks+=' if(dut.accepted_staging_write !== (old_owner.accepted && old_owner.command_write_i && !old_owner.response_error_o && !old_owner.command_address_i[11] && old_owner.command_address_i>=12\'h020 && old_owner.command_address_i<=12\'h03c))$fatal(1,"control admission mismatch: staging");\n control_checks=control_checks+1;end\n'
    checks+=r'''
integer four_state_checks=0;
task probe_unknown(input [11:0] address,input [3:0] strobes,input [31:0] identifier);begin
 @(negedge clk);cv=1;cw=1;ca=address;cd=1;cs=strobes;
 dut.command_id=identifier;old_owner.command_id=identifier;#1;
 if(dut.accepted_start !== (old_owner.accepted && old_owner.command_write_i && !old_owner.response_error_o && address==12'h040))
  $fatal(1,"control admission mismatch: four-state start");
 if(dut.accepted_staging_write !== (old_owner.accepted && old_owner.command_write_i && !old_owner.response_error_o && address==12'h020))
  $fatal(1,"control admission mismatch: four-state staging");
 four_state_checks=four_state_checks+1;
 // Pure combinational probes end before the active edge. The full owner
 // clock comparison below covers actual command/state update priorities.
 cv=0;cw=0;cs=15;dut.command_id=0;old_owner.command_id=0;
end endtask
reg [3:0] probe_strobes;reg [31:0] probe_id;
'''
    bench=bench.replace('integer equivalence_cycles=0;',checks+'integer equivalence_cycles=0;')
    anchor="write('h800,32'hbad00001,1);"
    require(bench.count(anchor)==1,'stimulus anchor changed')
    probes=r'''
key(1);
for(i=0;i<256;i=i+1)begin
 for(j=0;j<4;j=j+1)case((i>>(2*j))&3)
  0:probe_strobes[j]=0;1:probe_strobes[j]=1;2:probe_strobes[j]=1'bx;3:probe_strobes[j]=1'bz;
 endcase
 probe_unknown('h040,probe_strobes,0);probe_unknown('h020,probe_strobes,0);
end
for(i=0;i<32;i=i+1)begin
 probe_id=32'hffffffff;probe_id[i]=1'bx;probe_unknown('h040,15,probe_id);
 probe_id[i]=1'bz;probe_unknown('h040,15,probe_id);
end
if(four_state_checks!=576)$fatal(1,"four-state coverage");
$display("PASS original four-state admission vectors=%0d",four_state_checks);
dut.command_id=32'hffffffff;old_owner.command_id=32'hffffffff;write('h040,1,1);
dut.command_id=0;old_owner.command_id=0;cs=7;write('h040,1,1);cs=15;
'''
    bench=bench.replace(anchor,probes+anchor,1)
    anchor='arm(1);';require(bench.count(anchor)==1,'start anchor changed');bench=bench.replace(anchor,anchor+"write('h040,1,1);",1)
    anchor='// Complete command-space';require(bench.count(anchor)==1,'stop anchor changed');bench=bench.replace(anchor,"write('h040,4,0);wait(!hold);tick();arm(3);write('h040,5,0);wait(!hold);tick();\n"+anchor,1)
    bench=bench.replace('$display("PASS PCM window gate whole-owner', '$display("PASS PCM control admission checks=%0d",control_checks);\n$display("PASS PCM window gate whole-owner')
    (out/'tb.sv').write_text(bench)
    mutants={
        'missing_id_saturation':("command_address_i==12'h040 && control_id_ok","command_address_i==12'h040"),
        'missing_full_write':('control_write=write_command && control_format_ok &&','control_write=write_command &&'),
        'missing_start_rejection':("command_data_i==32'd1 && !start_error","command_data_i==32'd1"),
        'stop_select_confusion':('desired_source<=accepted_select;','desired_source<=accepted_stop;')}
    result=dict(schema=1,passed=False,input_sha256=inputs,symbolic=proof(),cases={},hardware_tested=False,physical_timing_verified=False)
    try:
        for label,mutation in [('baseline',None),*mutants.items()]:
            source=out/(label+'.sv');text=original
            if mutation:
                before,after=mutation;require(text.count(before)==1,'mutation anchor changed: '+label);text=text.replace(before,after,1)
            source.write_text(text);binary=out/(label+'.vvp')
            c=subprocess.run(['iverilog','-g2012','-s','tb','-o',str(binary),str(out/'tb.sv'),str(source),str(reference)],capture_output=True,text=True,timeout=60);(out/(label+'-compile.log')).write_text(c.stdout+c.stderr);require(c.returncode==0,'compile '+label+' '+c.stderr)
            r=subprocess.run(['vvp',str(binary)],capture_output=True,text=True,timeout=180);log=r.stdout+r.stderr;(out/(label+'.log')).write_text(log)
            passed=(r.returncode!=0 and ('control admission mismatch:' in log or 'whole-owner cycle mismatch:' in log)) if mutation else r.returncode==0 and 'PASS PCM control admission' in log
            result['cases'][label]=dict(passed=passed,negative_control=bool(mutation),exit_code=r.returncode,log=log,source_sha256=sha(source))
            require(passed,label+' '+log)
        require(inputs=={str(p):sha(p) for p in map(Path,inputs)},'source drift')
        result['passed']=True
    finally:
        result['output_sha256']={str(p.relative_to(out)):sha(p) for p in out.rglob('*') if p.is_file()}
        (out/'verification.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(passed=True,output=str(out),negative_controls=len(mutants))))


if __name__=='__main__':main()
