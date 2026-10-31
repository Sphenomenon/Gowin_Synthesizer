#!/usr/bin/env python3
"""Exact TF failure-admission rewrite against the complete consumed M11 owner."""
import argparse,hashlib,json,re,subprocess,sys
from pathlib import Path
import z3
ROOT=Path(__file__).resolve().parents[2]
SOURCE=ROOT/'rtl/tf_audio/workstation_tf_runtime_service.sv'
REFERENCE=Path(__file__).with_name('fixtures')/'workstation_tf_runtime_service_before_failure_factor.sv'
TB=Path(__file__).with_name('workstation_tf_runtime_service_tb.sv')
OLD_SHA='c42dc0bbe4919adf86275388239f52ccf63d6670b30c2bdf362ebea5bcb0b483'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def require(ok,msg):
 if not ok:raise ValueError('TF failure factor equivalence: '+msg)
def prove():
 state=z3.BitVec('state',3);epoch,launched=z3.BitVecs('epoch launched',32);file_rate=z3.BitVec('file_rate',20)
 flags=z3.Bools('restart_play card ddr memory_ready unsupported transport valid fault busy rate launched_rate format_ready')
 rp,card,ddr,mem,unsupported,transport,valid,fault,busy,rate,lr,fmt=flags
 physical=z3.Or(z3.And(state==4,rp),state==2,state==3);bad=z3.Or(z3.Not(valid),fault,busy)
 conditions=[card,z3.Or(z3.And(state!=4,ddr),z3.Not(mem)),z3.And(state!=4,unsupported),transport,bad,z3.Or(epoch!=launched,rate!=lr),z3.And(state!=4,fmt,file_rate!=z3.If(lr,z3.BitVecVal(44100,20),z3.BitVecVal(48000,20)))]
 code=z3.BitVecVal(0,4)
 for condition,value in reversed(list(zip(conditions,[4,3,2,7,5,6,1]))):code=z3.If(condition,z3.BitVecVal(value,4),code)
 old=z3.If(physical,code,z3.BitVecVal(0,4))!=0
 new=z3.And(physical,z3.Or(*conditions[:-2],z3.Or((epoch^launched)!=0,rate!=lr),conditions[-1]))
 s=z3.Solver();s.add(old!=new);require(s.check()==z3.unsat,'full-domain failure predicate differs')
 return dict(result='UNSAT',free_input_bits=3+64+20+len(flags),error_priority=[4,3,2,7,5,6,1],state_and_all_context_bits_unrestricted=True,z3_version=z3.get_version_string())
def twin_bench():
 text=TB.read_text();start=text.index('    workstation_tf_runtime_service #(');end=text.index('    localparam [28:0]',start);instance=text[start:end].strip();require(instance.endswith(');'),'instance end')
 prefix,bindings=instance.split(' dut(',1);bindings=bindings.rsplit(');',1)[0];connections=dict(re.findall(r'\.([A-Za-z_]\w*)\(([^()]*)\)',bindings))
 header=REFERENCE.read_text().split(') (',1)[1].split(');',1)[0];header=re.sub(r'//[^\n]*','',header);ports=[];checks=[];wires=[];inputs=0
 for direction,signed,width,names in re.findall(r'\b(input|output)\s+(?:wire|reg)\s*(signed\s*)?(\[[^]]+\])?\s*([\w,\s]+?)(?=\binput|\boutput|$)',header):
  for name in names.strip().strip(',').split(','):
   name=name.strip();require(re.fullmatch(r'[A-Za-z_]\w*',name),'port parsing '+name);require(name in connections,'missing actual test port '+name)
   if direction=='output':
    wires.append('wire '+signed+width+' reference_'+name+';');ports.append('.'+name+'(reference_'+name+')');checks.append('if(dut.'+name+' !== reference_'+name+')$fatal(1,"whole TF output '+name+'");')
   else:ports.append('.'+name+'('+connections[name]+')');inputs+=1
 require(len(ports)==len(connections),'complete actual port inventory')
 reference=prefix.replace('workstation_tf_runtime_service #(','workstation_tf_runtime_service_reference #(',1)+' reference('+','.join(ports)+');'
 scalars='state restart_playback path_track path_clear_toggle pending_clear restart_q cancel_q reader_restart_q mode_q run_q card_lost_q transport_error_q track_q pending_start pending_reader_restart path_restart launched_rate launched_epoch quiet_wait source_quiesce stop_request_q stop_latched stop_transaction_failed stop_wait'.split()
 checks.extend('if(dut.'+name+' !== reference.'+name+')$fatal(1,"whole TF state '+name+'");'for name in scalars)
 checks.extend('if(dut.'+name+' !== reference.'+name+')$fatal(1,"whole TF combinational '+name+'");'for name in ['error_now','new_failure','invalidate','path_pcm_ready','playback_accept','analysis_accept','stop_begin','stop_invalidate'])
 extra='\n'+ '\n'.join(wires)+'\n'+reference+'\ninteger equivalence_edges=0;\nalways @(posedge source_clk or posedge compute_clk or posedge memory_clk)begin #0.01;equivalence_edges=equivalence_edges+1;\n'+'\n'.join(checks)+'\nend\nfinal $display("PASS whole TF owner equivalence edges=%0d outputs='+str(len(wires))+' inputs='+str(inputs)+' state_groups='+str(len(scalars))+'",equivalence_edges);\n'
 text=text[:end]+extra+text[end:]
 # Mirror only explicit fault-injection assignments to the independent path.
 pattern=r'(?:(?:force|release)\s+dut\.[\w.]+(?:\s*=\s*[^;]+)?;|(?<![\w.])dut\.path\.u_file_reader\.present\s*=\s*[^;]+;)'
 text,count=re.subn(pattern,lambda m:m[0]+' '+m[0].replace('dut.','reference.'),text)
 require(count==22,'fault injection inventory drift: '+str(count))
 return text,dict(outputs=len(wires),inputs=inputs,internal_state_groups=len(scalars),mirrored_path_fault_injections=count)
def directed_controls(out,fixtures,original_sources,new):
 # Isolate the actual complete owner's immediate combinational contract before
 # any clock edge. Force only its context/path status, never the tested controls.
 directed=r'''
    initial if(!RUN_SCENARIOS)begin
        #1;source_run=0;compute_run=0;memory_run=0;
        force dut.state=3'd3;force dut.launched_epoch=32'd0;
        force dut.launched_rate=1'b0;force dut.memory_ready_sync=2'b11;
        force dut.card_lost_o=1'b0;force dut.ddr_error_o=1'b0;
        force dut.unsupported_o=1'b0;force dut.format_ready_o=1'b0;
        force dut.stop_latched=1'b0;force dut.stop_request_q=1'b0;
        force dut.stop_pending_o=1'b0;force dut.track_q=4'd0;
        force dut.mode_q=1'b1;force dut.restart_q=1'b0;
        force dut.cancel_q=1'b0;force dut.reader_restart_q=1'b0;
        runtime_epoch=0;#1;
        if(dut.new_failure!==0 || dut.error_now!==0 || dut.invalidate!==0)
            $fatal(1,"directed clean admission");
        for(integer bit_index=0;bit_index<32;bit_index=bit_index+1)begin
            runtime_epoch=32'b1<<bit_index;#1;
            if(dut.new_failure!==1 || dut.error_now!==6 || dut.invalidate!==1)
                $fatal(1,"directed epoch bit %0d",bit_index);
        end
        runtime_epoch=0;runtime_valid=0;force dut.state=3'd0;#1;
        if(dut.new_failure!==0 || dut.error_now!==0)
            $fatal(1,"directed physical guard");
        force dut.state=3'd3;force dut.card_lost_o=1'b1;
        force dut.ddr_error_o=1'b1;force dut.unsupported_o=1'b1;
        transport_error=1;#1;
        if(dut.error_now!==4 || dut.new_failure!==1)
            $fatal(1,"directed diagnostic priority");
        force dut.state=3'd0;force dut.card_lost_o=1'b0;
        force dut.ddr_error_o=1'b0;force dut.unsupported_o=1'b0;
        transport_error=0;runtime_valid=1;stop_request=1;#1;
        if(dut.stop_begin!==1 || dut.stop_invalidate!==1 || dut.invalidate!==1)
            $fatal(1,"directed immediate stop veto");
        $display("PASS directed actual TF controls epoch_bits=32 physical_guard=1 diagnostic_priority=1 immediate_stop_veto=1");
        $finish;
    end
'''
 text=TB.read_text();pos=text.rfind('endmodule');bench=out/'directed.sv';bench.write_text(text[:pos]+directed+text[pos:])
 cases=[('baseline',new,None),
  ('epoch_bit22_omitted',new.replace('|(runtime_epoch_i ^ launched_epoch)','|((runtime_epoch_i ^ launched_epoch) & 32\'hffbfffff)',1),'directed epoch bit 22'),
  ('physical_guard_removed',new.replace("        if(physical)begin\n            if(card_lost_o ||","        if(1'b1)begin\n            if(card_lost_o ||",1),'directed physical guard'),
  ('stop_veto_removed',new.replace(' || stop_invalidate ||',' || 1\'b0 ||',1),'directed immediate stop veto'),
  ('diagnostic_priority_changed',new.replace('if(card_lost_o)error_now=CARD;','if(card_lost_o)error_now=DDR;',1),'directed diagnostic priority')]
 results={}
 for name,source,expected in cases:
  require(name=='baseline' or source!=new,'mutant failed to change source '+name)
  path=out/(name+'.sv');path.write_text(source)
  sources=[str(path)if s==str(SOURCE)else str(bench)if s==str(TB)else s for s in original_sources]
  cmd=['iverilog','-g2012','-Wall','-I',str(fixtures),'-s','tb_workstation_tf_runtime_service','-Ptb_workstation_tf_runtime_service.RUN_SCENARIOS=0','-Ptb_workstation_tf_runtime_service.EXTERNAL_STOP_PROTOCOL=1','-o',str(out/(name+'.vvp')),*sources]
  c=subprocess.run(cmd,cwd=fixtures,text=True,capture_output=True,timeout=90);(out/(name+'_compile.log')).write_text(c.stdout+c.stderr);require(c.returncode==0,'directed compile '+name)
  r=subprocess.run(['vvp',str(out/(name+'.vvp'))],cwd=fixtures,text=True,capture_output=True,timeout=90);log=out/(name+'.log');log.write_text(r.stdout+r.stderr)
  if expected:require(r.returncode!=0 and expected in r.stdout,'specific negative not rejected '+name+': '+r.stdout[-1500:])
  else:require(r.returncode==0 and 'PASS directed actual TF controls' in r.stdout,'directed baseline '+r.stdout[-1500:])
  results[name]=dict(returncode=r.returncode,expected_failure=expected,rejected=bool(expected),actual_source_sha256=sha(path),log_sha256=sha(log))
 return results
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--fixtures',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
 require(sha(REFERENCE)==OLD_SHA,'complete M11 fixture identity');old=REFERENCE.read_text();new=SOURCE.read_text();old_inverse=new.replace('    wire epoch_mismatch=|(runtime_epoch_i ^ launched_epoch);\n    wire rate_mismatch=runtime_44k1_i!=launched_rate;\n','').replace('else if(epoch_mismatch || rate_mismatch)error_now=EPOCH;','else if(runtime_epoch_i!=launched_epoch || runtime_44k1_i!=launched_rate)error_now=EPOCH;')
 start=old_inverse.index('    // Admission needs only whether a failure exists.');end=old_inverse.index('    wire invalidate=',start);old_inverse=old_inverse[:start]+'    wire new_failure=error_now!=0;\n'+old_inverse[end:];require(old_inverse==old,'changes escape exact combinational boundaries')
 inputs={str(p):sha(p)for p in (SOURCE,REFERENCE,TB,Path(__file__).resolve())};proof=prove();bench,inventory=twin_bench();(out/'bench.sv').write_text(bench);(out/'reference.sv').write_text(old.replace('module workstation_tf_runtime_service #(','module workstation_tf_runtime_service_reference #(',1))
 meta=json.loads((a.fixtures/'verification.json').read_text());argv=meta['compile_argv'];original_sources=argv[argv.index('-o')+2:];sources=[str(out/'bench.sv')if s==str(TB)else s for s in original_sources]+[str(out/'reference.sv')]
 runs={}
 for buffered,split in [(0,0),(1,0),(0,1),(1,1)]:
  name=f'twin_b{buffered}_split{split}';cmd=['iverilog','-g2012','-Wall','-I',str(a.fixtures),'-s','tb_workstation_tf_runtime_service','-Ptb_workstation_tf_runtime_service.USE_COMMAND_BUFFER='+str(buffered),'-Ptb_workstation_tf_runtime_service.SEPARATE_COMMON_RESET='+str(split),'-o',str(out/(name+'.vvp')),*sources];c=subprocess.run(cmd,cwd=a.fixtures,text=True,capture_output=True,timeout=90);(out/(name+'_compile.log')).write_text(c.stdout+c.stderr);require(c.returncode==0,'compile '+name)
  r=subprocess.run(['vvp',str(out/(name+'.vvp'))],cwd=a.fixtures,text=True,capture_output=True,timeout=90);(out/(name+'.log')).write_text(r.stdout+r.stderr);require(r.returncode==0 and 'PASS whole TF owner equivalence' in r.stdout,'whole owner '+name+': '+r.stdout[-1500:]);runs[name]=dict(returncode=r.returncode,summary=next(s for s in r.stdout.splitlines()if s.startswith('PASS whole TF')),log_sha256=sha(out/(name+'.log')))
 negatives=directed_controls(out,a.fixtures,original_sources,new)
 require(all(sha(Path(p))==v for p,v in inputs.items()),'source drift')
 report=dict(stage='full_consumed_TF_owner_exact_combinational_rewrite',passed=True,inputs_sha256=inputs,full_domain_smt=proof,complete_source_inverse_exact=True,port_and_state_inventory=inventory,whole_real_path_twin_runs=runs,directed_actual_owner_controls=negatives,physical_or_hardware_verified=False);(out/'verification.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
if __name__=='__main__':main()
