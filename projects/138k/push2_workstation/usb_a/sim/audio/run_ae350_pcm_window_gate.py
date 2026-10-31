#!/usr/bin/env python3
"""Every-cycle whole-owner reference for the factored PCM RAM write gate."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'sim'))
from test_ae350_pcm_owner import BASE

SOURCE=ROOT/'rtl/audio/workstation_ae350_pcm_owner.sv'
REFERENCE=Path(__file__).with_name('fixtures')/'workstation_ae350_pcm_owner_before_window_gate.sv'
REFERENCE_SHA256='765e05213e6de5df1c729ef9b43ac2a40025fdaf90ebc060080079855d31dfb8'
OUTPUTS=('command_ready_o','response_data_o','response_error_o','pcm_left_o','pcm_right_o',
    'history_clear_o','serial_hold_o','cancel_epoch_o','selected_o','failed_o','hard_fault_o')
STATE=('owned head_slot tail_slot head_index queued staged_controller staged_generation staged_stream '
    'staged_rate staged_physical staged_slot staged_frames staged_sequence active_controller active_generation '
    'active_stream active_rate active_physical last_controller last_generation last_stream retired_key_valid '
    'armed selected failed cpu_previous failure expected_sequence command_id applied_id pending_id history_state '
    'desired_source hold_serial history_wait phase step_q24 input_frames output_frames underflows overflows '
    'minimum_queue maximum_queue window_count occupancy_sum integral cache0 cache1 cache_address cache_valid').split()


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def require(ok,message):
    if not ok:raise ValueError('PCM window gate regression: '+message)


def bench():
    instance=re.search(r'workstation_ae350_pcm_owner\s*#\(.*?\)\s+dut\s*\(.*?\);',BASE,re.S)
    require(instance is not None,'whole-owner fixture binding missing')
    old=instance[0].replace('workstation_ae350_pcm_owner','pcm_owner_window_reference',1).replace(' dut(', ' old_owner(',1)
    for port in OUTPUTS:
        old,count=re.subn(r'\.'+port+r'\([^()]*\)', '.'+port+'()',old)
        require(count==1,'reference output anchor changed: '+port)
    comparisons='\n'.join(' if(dut.'+name+' !== old_owner.'+name+')$fatal(1,"whole-owner cycle mismatch: '+name+'");'
        for name in list(dict.fromkeys(STATE+list(OUTPUTS))))
    extra=old+'''
integer equivalence_cycles=0;
always @(posedge clk)begin
 #1;
'''+comparisons+'''
 for(integer slot=0;slot<4;slot=slot+1)begin
  if(dut.written[slot] !== old_owner.written[slot] || dut.frames[slot] !== old_owner.frames[slot])
   $fatal(1,"whole-owner cycle mismatch: written/frame slot=%0d",slot);
 end
 for(integer index=0;index<512;index=index+1)
  if(dut.memory[index] !== old_owner.memory[index])$fatal(1,"whole-owner cycle mismatch: PCM RAM index=%0d",index);
 equivalence_cycles=equivalence_cycles+1;
end
reg [31:0] random_state=32'h9531ac24;
'''
    body=r'''
write('h800,32'hbad00001,1); // Unarmed RAM write must remain blocked.
arm(1);
// Unrelated invalid descriptor state must not affect legal window writes.
write('h038,32'h80000081,0);write('h800,32'h12345678,0);
cs=7;write('h804,32'hbad00002,1);cs=15;
key(2);write('h808,32'hbad00003,1);key(1);
for(i=0;i<4;i=i+1)for(j=0;j<128;j=j+1)write('h800+i*512+j*4,32'(i*128+j+4096),0);
write('h034,0,0);write('h038,128,0);write('h03c,0,0);write('h040,2,0);
write('h800,32'hbad00004,1); // Owned slot is immutable.
write('h034,1,0);write('h038,128,0);write('h03c,1,0);write('h040,2,0);
select_bt();for(i=0;i<4;i=i+1)tick();
// The original accepts this same-edge RAM write, then revokes the stream.
// RAM bytes update while written/ownership are cleared by the later fence.
@(negedge clk);cv=1;cw=1;ca='he00;cd=32'h31415926;tf=1;
@(negedge clk);cv=0;cw=0;tf=0;
wait(!hold);tick();repeat(3)@(negedge clk);
arm(2);block(0,0,2,100);block(1,1,2,200);select_bt();
write('hc00,32'hfed4012c,0);write('hc04,32'hfed3012d,0);
write('h034,2,0);write('h038,2,0);write('h03c,2,0);
@(negedge clk);take=1;cv=1;cw=1;ca='h040;cd=2;
@(negedge clk);take=0;cv=0;cw=0;
repeat(3)@(negedge clk);
// Complete command-space and raw key/reset/session errors are compared each
// clock against the frozen owner, including same-edge revocation priority.
for(i=0;i<6000;i=i+1)begin
 @(negedge clk);random_state={random_state[30:0],random_state[31]^random_state[21]^random_state[1]^random_state[0]};
 cv=random_state[0];cw=random_state[1];ca=random_state[13:2];cd=random_state^32'h53a77129;cs=random_state[17:14];
 take=random_state[18];cpu=random_state[22:19]!=0;live=random_state[26:23]!=0;
 ctx_ready=random_state[30:27]!=0;tf=random_state[9:5]==0;sw=random_state[14:10]==0;
 if(random_state[7:0]==8'h5a)begin ce=ce+1;tg=tg+1;pe=pe+1;end
 if(random_state[11:0]==12'h684)rst=0;else rst=1;
end
@(negedge clk);cv=0;cw=0;take=0;
repeat(4)@(negedge clk);
if(equivalence_cycles<7000)$fatal(1,"whole-owner reference coverage incomplete");
$display("PASS PCM window gate whole-owner cycle reference: cycles=%0d compared_state=STATE_COUNT memory_words=512 written_slots=4 random_commands=6000 same_edge_revocation=1",equivalence_cycles);
$finish;
'''.replace('STATE_COUNT',str(len(set(STATE+list(OUTPUTS)))))
    return '`timescale 1ns/1ps\n'+BASE.replace('EXTRA',extra).replace('BODY',body).replace('@PREFILL@','4').replace('MAXTIME','2000000')


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();out=args.output.resolve();require(not out.exists(),'new output required');out.mkdir(parents=True)
    require(sha(REFERENCE)==REFERENCE_SHA256,'frozen whole-owner reference changed')
    inputs={str(p):sha(p) for p in (SOURCE,REFERENCE,Path(__file__).resolve(),ROOT/'sim/test_ae350_pcm_owner.py')}
    (out/'reference.sv').write_text(REFERENCE.read_text().replace('module workstation_ae350_pcm_owner','module pcm_owner_window_reference',1))
    (out/'tb.sv').write_text(bench());original=SOURCE.read_text()
    mutations={
        'missing_strobes':('window_write && full_write && armed','window_write && armed'),
        'missing_key':('&& armed && key_matches && !owned[write_slot]','&& armed && !owned[write_slot]'),
        'missing_ownership':('&& key_matches && !owned[write_slot]','&& key_matches'),
        'changed_revocation_priority':('&& armed && key_matches && !owned[write_slot]','&& armed && key_matches && !owned[write_slot] && !tf_busy_i'),
    }
    result=dict(schema=1,passed=False,reference_sha256=REFERENCE_SHA256,input_sha256=inputs,cases={},
        hardware_tested=False,physical_timing_verified=False,PNR=False)
    try:
        for name,mutation in [('current',None),*mutations.items()]:
            source=out/(name+'.sv');text=original
            if mutation:
                before,after=mutation;require(text.count(before)==1,'negative anchor drift: '+name);text=text.replace(before,after,1)
            source.write_text(text)
            command=['iverilog','-g2012','-s','tb','-o',str(out/name),str(out/'tb.sv'),str(source),str(out/'reference.sv')]
            p=subprocess.run(command,cwd=out,capture_output=True,text=True,timeout=60);(out/(name+'_compile.log')).write_text(p.stdout+p.stderr)
            require(p.returncode==0,'compile failed: '+name)
            p=subprocess.run(['vvp',str(out/name)],cwd=out,capture_output=True,text=True,timeout=120)
            log=p.stdout+p.stderr;(out/(name+'.log')).write_text(log)
            if mutation:require(p.returncode!=0 and 'whole-owner cycle mismatch' in log,'negative survived/wrong oracle: '+name)
            else:require(p.returncode==0 and 'PASS PCM window gate whole-owner cycle reference:' in log,'current/reference mismatch: '+log)
            result['cases'][name]=dict(returncode=p.returncode,passed=p.returncode==0,negative_rejected=bool(mutation),log_sha256=sha(out/(name+'.log')))
        require({str(p):sha(p) for p in map(Path,inputs)}==inputs,'maintained source drift')
        result['passed']=True
    finally:
        result['outputs_sha256']={str(p.relative_to(out)):sha(p) for p in out.rglob('*') if p.is_file()}
        (out/'verification.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(output=str(out),passed=True,negative_controls=4)))


if __name__=='__main__':main()
