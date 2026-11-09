#!/usr/bin/env python3
"""Compare every actual W endpoint output and the four-state CANCEL predicate.

The selected staging adapter must round-trip to the exact maintained native
endpoint. The paired fixture includes the real record data engine. The second
fixture exhausts channel/kind/reset/ready combinations and injects X/Z values.
It does not grant physical or sustained-phone acceptance.
"""
from pathlib import Path
import argparse, re, json, subprocess, hashlib, sys
u=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(u))
from tools import workstation_w_tx_class as selection
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output',type=Path,required=True)
args=parser.parse_args();out=args.output.resolve()
if out.is_relative_to(u.parents[3]):raise ValueError('output must be outside the repository')
out.mkdir(parents=True,exist_ok=False)
f=u/selection.SOURCE;source=f.read_text()
staged=out/'selection'/selection.SOURCE;staged.parent.mkdir(parents=True);staged.write_text(source)
configuration={'demo_role':'W',selection.KEY:selection.POLICY,selection.CANCEL_KEY:selection.CANCEL_POLICY}
receipt=selection.select(out/'selection',configuration)
assert selection.native(staged.read_bytes())==f.read_bytes()
# The real paired fixture supplies the same parameter to both endpoint twins.
candidate=staged.read_text().replace(selection.SELECTED,selection.DEFAULT,1)
old,new=selection.CANCEL_PARENT,selection.CANCEL_SELECTED
assert candidate==source.replace(old,new,1)
# The actual endpoint shape/ready decoder is used in every check, including X/Z.
header=source[source.index('module workstation_task3_w_bus_endpoint'):source.index('    wire [95:0] common=')];ports=[];outputs=[]
for match in re.finditer(r'\b(input|output)\s+(wire|reg)\s*(\[[^\]]+\])?\s*([\w,]+)\s*[,\n]',header):
 direction,kind,width,names=match.groups()
 for name in names.strip(',').split(','):
  ports.append(name)
  if direction=='output':outputs.append((name,width or ''))
assert len(ports)==62 and len(outputs)>20,(len(ports),outputs)
params='#(.BLOCK_PCM(BLOCK_PCM),.PHONE_WINDOW_BLOCK(PHONE_WINDOW_BLOCK),.PHONE_BATCH(PHONE_BATCH),.REGISTER_TX_CLASS(REGISTER_TX_CLASS),.MEDIA_CAP_TIMEOUT_CYCLES(MEDIA_CAP_TIMEOUT_CYCLES))'
wrapper=header
for name,width in outputs:wrapper+=f'wire {width} reference_{name};\n'
for label in ['candidate','reference']:
 wrapper+=f'{label}_endpoint {params} {label}('+','.join('.'+x+'('+('reference_'+x if label=='reference'and any(x==y for y,_ in outputs)else x)+')'for x in ports)+');\n'
wrapper+='integer compared=0;always @(negedge clk_i)if(reset_ni)begin\n'
for name,width in outputs:wrapper+=f'if({name} !== reference_{name})$fatal(1,"public output changed: {name}");\n'
wrapper+='compared=compared+1;end\nfinal $display("PASS all public outputs=%0d edges=%0d",'+str(len(outputs))+',compared);\nendmodule\n'
(out/'candidate.sv').write_text(candidate.replace('module workstation_task3_w_bus_endpoint','module candidate_endpoint',1));(out/'reference.sv').write_text(source.replace('module workstation_task3_w_bus_endpoint','module reference_endpoint',1));(out/'twins.sv').write_text(wrapper)
names=('m_bus_endpoint','pcm_block_tx','pcm_block_rx','record_ingress','final_tap_export','phone_command_ingress','phone_command_proxy','phone_command_mux','record_source_gate','phone_batch_w','phone_window_tx')
inputs=[u/('rtl/workstation/workstation_task3_'+n+'.sv')for n in names]+[u/'rtl/music/workstation_task3_tf_analysis_source.sv',u/'rtl/music/workstation_task3_score_commit_m.sv',u/'rtl/bluetooth/cpu_owner/workstation_ble_record_data_engine.sv']
tb=(u/'sim/audio/tb_workstation_task3_paired_bus.sv').read_text();tb=tb.replace('defparam w.phone_proxy.ROUND_TRIP_TIMEOUT_CYCLES=80;','defparam w.candidate.phone_proxy.ROUND_TRIP_TIMEOUT_CYCLES=80;\n    defparam w.reference.phone_proxy.ROUND_TRIP_TIMEOUT_CYCLES=80;');tb=tb.replace('w.record_active_local','w.candidate.record_active_local');(out/'tb.sv').write_text(tb)
def run(name,argv,success=True):
 r=subprocess.run(list(map(str,argv)),cwd=u,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=60);(out/(name+'.log')).write_text(r.stdout);assert (r.returncode==0)==success,(name,r.returncode,r.stdout[-2000:]);return r.stdout
base=['iverilog','-g2012','-I'+str(u),'-s','tb_workstation_task3_paired_bus','-o',out/'paired.vvp',out/'tb.sv',out/'reference.sv',out/'candidate.sv',out/'twins.sv',*inputs]
run('paired-build',base);result=run('paired-run',['vvp',out/'paired.vvp']);assert 'PASS task3 paired typed bus checks='in result
# Exhaust every 2-bit kind and 4-bit channel, with all padding/identity cases,
# arbitrary ready state, both block modes and unknown control bits.
predicate='''`timescale 1ns/1ps
`include "rtl/workstation/task3_paired_channels.vh"
module predicate;
reg clk=0;always #5 clk=~clk;reg rst=0,valid=0;reg [3:0] channel=0;reg [255:0] payload=0;reg [5:0] length=0;
reg lv=0,match_key=0,active_key=0,wait_arm=0,ack_arm=0,ready=0;wire [1:0] original,selected;
genvar j;generate for(j=0;j<2;j=j+1)begin:g
reference_endpoint #(.BLOCK_PCM(j)) dut(.clk_i(clk),.reset_ni(rst),.rx_valid_i(valid),.rx_channel_i(channel),.rx_payload_i(payload),.rx_length_i(length),.cnn_desc_ready_i(ready),.cnn_frame_ready_i(ready),.cnn_seal_ready_i(ready),.cnn_cancel_ready_i(ready));
initial begin force dut.live=lv;force dut.record_matches=match_key;force dut.record_active_matches=active_key;force dut.record_wait_result=wait_arm;force dut.record_ack_pending=ack_arm;force dut.phone_ack_matches=match_key;force dut.phone_response_ready=ready;end
assign original[j]=dut.record_cancel_fire;
assign selected[j]=valid && rst && dut.record_cancel && match_key && active_key;
end endgenerate
integer i,k,checks=0;
task check;begin #1;if(original!==selected)$fatal(1,"CANCEL ready cofactor changed i=%0d kind=%0d old=%b new=%b",i,payload[195:194],original,selected);checks=checks+1;end endtask
initial begin
for(i=0;i<65536;i=i+1)begin
{rst,valid,lv,match_key,active_key,wait_arm,ack_arm,ready}=i[7:0];channel=i[11:8];length=`TASK3_PAIR_RECORD_BYTES;payload=0;payload[195:194]=i[13:12];
case(i[15:14])1:payload[200]=1;2:payload[97]=1;3:payload[194]=1'bx;endcase
check;
end
for(i=0;i<20000;i=i+1)begin
{rst,valid,lv,match_key,active_key,wait_arm,ack_arm,ready}=$urandom;channel=`TASK3_PAIR_CH_RECORD;length=`TASK3_PAIR_RECORD_BYTES;payload=0;payload[195:194]=`TASK3_PAIR_KIND_CANCEL;
k=$urandom_range(0,255);case(i%4)0:payload[k]=1'bx;1:payload[k]=1'bz;2:channel[i%4]=1'bx;3:length[i%6]=1'bz;endcase
check;
end
$display("PASS actual CANCEL predicate four-state checks=%0d",checks);$finish;end
endmodule
'''
(out/'predicate.sv').write_text(predicate);run('predicate-build',['iverilog','-g2012','-I'+str(u),'-s','predicate','-o',out/'predicate.vvp',out/'predicate.sv',out/'reference.sv',*inputs]);result2=run('predicate-run',['vvp',out/'predicate.vvp']);assert 'checks=85536'in result2
mutant=candidate.replace(new,'wire record_cancel_fire=1\'b0;',1);(out/'candidate.sv').write_text(mutant.replace('module workstation_task3_w_bus_endpoint','module candidate_endpoint',1));run('mutant-build',base);result3=run('mutant-run',['vvp',out/'paired.vvp'],False);assert 'public output changed'in result3
(out/'candidate.sv').write_text(candidate.replace('module workstation_task3_w_bus_endpoint','module candidate_endpoint',1))
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest();r=dict(passed=True,production_selected=True,selection=receipt,source_sha256=sha(f),selected_source_sha256=hashlib.sha256(candidate.encode()).hexdigest(),scope='Actual ready and record CANCEL predicates; all public endpoint outputs under actual paired bus/record engine. No added cycles/state; no physical acceptance.',all_public_outputs=len(outputs),paired_log=result,predicate_log=result2,negative_control_rejected=True,evidence_sha256={str(p):sha(p)for p in out.glob('*')if p.is_file()});(out/'verification.json').write_text(json.dumps(r,indent=2)+'\n');print(r['all_public_outputs'],result2,result[-300:],flush=True)
