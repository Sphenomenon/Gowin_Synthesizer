#!/usr/bin/env python3
from pathlib import Path
import hashlib,json,subprocess
import argparse
import ae350_pcm_output_context_sources as output_context
U=Path(__file__).resolve().parents[2]
SOURCE=U/'rtl/audio/workstation_ae350_pcm_owner.sv'
REFERENCE=Path(__file__).with_name('fixtures')/'workstation_ae350_pcm_owner_before_bitmap_gate.sv'
parser=argparse.ArgumentParser(description='Actual complete PCM owner bitmap finite four-state miter; includes destructive source controls.')
parser.add_argument('--output',type=Path,required=True)
O=parser.parse_args().output.resolve();O.mkdir(parents=True,exist_ok=False)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
assert hashlib.sha256(output_context.reference_view(SOURCE.read_text()).encode()).hexdigest()=='574c6e268e952a2d72063db5296e781528f47158f4c63ad8cc2968a767d1b71e'
assert sha(REFERENCE)=='3eab83ad77e0ff28aac3bee416751262bb3af01241d1df596e769a871d53f5b3'
original=REFERENCE.read_text().replace('module workstation_ae350_pcm_owner','module pcm_owner_window_reference',1);variant=SOURCE.read_text()
inputs={str(p):sha(p) for p in (SOURCE,REFERENCE,Path(__file__).resolve())}
inputs.update({str(p):sha(p)for p in output_context.inputs()})
signals=['accepted_window_write','accepted_start','accepted_commit','accepted_stop','accepted_cancel',
 'rejected_commit','usable','key_matches','armed','cpu_previous','live_matches','physical_matches',
 'selected','hold_serial','cache_current']
regs='\n'.join('reg f_'+n+';' for n in signals)
forces='\n'.join('force '+unit+'.'+n+'=f_'+n+';' for unit in ('dut','old_owner') for n in signals)
assigns='\n'.join('f_'+n+'=quad(control >> '+str(2*i)+');' for i,n in enumerate(signals[:8]))
patterns='\n'.join('f_'+n+'=quad(pattern >> '+str(2*(i%4))+');' for i,n in enumerate(signals[8:]))
connections='''.clk_i(clk),.reset_ni(rst),.cpu_ready_i(cpu),.command_valid_i(1'b0),.command_write_i(1'b0),
 .command_address_i(12'd0),.command_data_i(32'h5342a918),.command_strobes_i(4'hf),
 .session_live_i(1'b1),.controller_epoch_i(32'd1),.transport_generation_i(32'd1),
 .context_ready_i(1'b1),.rate_44100_i(1'b0),.physical_epoch_i(32'd1),.tf_busy_i(tf),
 .switch_busy_i(1'b0),.sample_take_i(take),.legacy_left_i(32'd0),.legacy_right_i(32'd0),
 .history_ready_i(1'b0),.history_done_i(1'b0)'''
tb='''`timescale 1ns/1ps
module tb;
reg clk=0,rst=1,cpu=1,tf=0,take=0;
'''+regs+'''
workstation_ae350_pcm_owner dut('''+connections+''');
pcm_owner_window_reference old_owner('''+connections+''');
function quad(input integer v);begin case(v&3)0:quad=0;1:quad=1;2:quad=1'bx;3:quad=1'bz;endcase end endfunction
integer control,pattern,k,checks=0;
reg [31:0] rng=32'h95723ea1;
reg [1:0] slot=0,tail=0;reg[6:0] index=0;
initial begin
'''+forces+'''
force dut.owned=4'd0;force old_owner.owned=4'd0;
force dut.write_slot=slot;force old_owner.write_slot=slot;
force dut.write_index=index;force old_owner.write_index=index;
force dut.tail_slot=tail;force old_owner.tail_slot=tail;
for(pattern=0;pattern<16;pattern=pattern+1)begin
'''+""+'''
 cpu=quad(pattern);tf=quad(pattern>>2);take=quad(pattern>>4);
 for(control=0;control<65536;control=control+1)begin
'''+assigns+'''
  rng=rng^(rng<<13);rng=rng^(rng>>17);rng=rng^(rng<<5);
  f_armed=quad(rng);f_cpu_previous=quad(rng>>2);f_live_matches=quad(rng>>4);
  f_physical_matches=quad(rng>>6);f_selected=quad(rng>>8);f_hold_serial=quad(rng>>10);f_cache_current=quad(rng>>12);
  take=quad(rng>>14);
  slot=pattern[1:0];tail=pattern[3:2];index=rng[6:0];
  for(k=0;k<4;k=k+1)begin
   dut.written[k]={rng,~rng,rng^32'h48ac,~rng};
   old_owner.written[k]={rng,~rng,rng^32'h48ac,~rng};
  end
  #1;clk=1;#1;
  for(k=0;k<4;k=k+1)if(dut.written[k] !== old_owner.written[k])
   $fatal(1,"bitmap differs pattern=%0d control=%0d slot=%0d old=%h new=%h",pattern,control,k,old_owner.written[k],dut.written[k]);
  clk=0;#1;checks=checks+1;
 end
end
$display("PASS bitmap actual four-state checks=%0d",checks);$finish;
end
endmodule
'''
(O/'tb.sv').write_text(tb)
(O/'reference.sv').write_text(original)
mutants={
 'missing_context':('else if(!physical_matches)bitmap_clear_late=1;',"else if(1'b0)bitmap_clear_late=1;"),
 'missing_stop':('if(accepted_stop)bitmap_clear_late=1;',"if(1'b0)bitmap_clear_late=1;"),
 'missing_cancel':('if(accepted_cancel)bitmap_clear_late=1;',"if(1'b0)bitmap_clear_late=1;"),
 'missing_rejected_commit':('if(rejected_commit && usable && key_matches && !owned[tail_slot])bitmap_clear_late=1;',"if(1'b0)bitmap_clear_late=1;"),
 'clear_before_window':('            if(accepted_window_write)written[write_slot][write_index]<=1;\n','')}
rows={}
for label,change in [('baseline',None),*mutants.items()]:
 text=variant
 if change:
  a,b=change;assert text.count(a)==1;text=text.replace(a,b,1)
  if label=='clear_before_window':text=text.replace('            if(bitmap_clear_late)begin','            if(accepted_window_write)written[write_slot][write_index]<=1;\n            if(bitmap_clear_late)begin',1)
 p=O/(label+'.sv');p.write_text(text);binary=O/(label+'.vvp')
 r=subprocess.run(['iverilog','-g2012','-s','tb','-o',str(binary),str(O/'tb.sv'),str(p),str(O/'reference.sv')],capture_output=True,text=True,timeout=60)
 (O/(label+'-compile.log')).write_text(r.stdout+r.stderr);assert r.returncode==0,r.stderr
 r=subprocess.run(['vvp',str(binary)],capture_output=True,text=True,timeout=180);log=r.stdout+r.stderr;(O/(label+'.log')).write_text(log)
 passed=(r.returncode!=0 and 'bitmap differs' in log) if change else (r.returncode==0 and 'checks=1048576' in log)
 rows[label]={'passed':passed,'exit_code':r.returncode,'log':log,'source_sha256':sha(p)}
 print(label,passed,log[-250:],flush=True);assert passed
result=dict(passed=True,source_implementation=True,finite_four_state_not_formal=True,checks=1048576,cases=rows,
 source_sha256=sha(SOURCE),reference_sha256=sha(REFERENCE),input_sha256=inputs,
 stimulus_scope='8 permission scalars exhaustively enumerated in four-state for each of 16 index/cpu/tf groups; other context scalars use fixed-seed random four-state values. No reachability assumption or full four-state formal claim.',
 files={str(p.relative_to(O)):sha(p) for p in O.rglob('*') if p.is_file()},hardware=False,pnr=False)
assert all(sha(p)==h for p,h in inputs.items())
(O/'verification.json').write_text(json.dumps(result,indent=2)+'\n')
print('verification',sha(O/'verification.json'))
