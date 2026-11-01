"""Prove final memory_failure write-enable factoring against the exact consumed W17 owner."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,importlib.util,json,re,difflib,subprocess,sys
sys.dont_write_bytecode=True
import argparse
ROOT=Path(__file__).resolve().parents[2]
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output',type=Path,required=True)
O=parser.parse_args().output.resolve();O.mkdir(parents=True,exist_ok=False)
helper_path=Path(__file__).with_name('ble_raw_failure_ce_sources.py')
spec=importlib.util.spec_from_file_location('final_failure_ce_inverse',helper_path)
pin=importlib.util.module_from_spec(spec);spec.loader.exec_module(pin)
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
source=ROOT/'rtl/memory/workstation_ble_raw_ddr_store.sv';assert sha(source)==pin.MAINTAINED_SHA256
maintained_text=source.read_text();old=pin.restore_before_failure_final_ce(maintained_text);changes=[]
def replace(s,a,b,n=1):
 assert s.count(a)==n,(a,s.count(a),n);changes.append(dict(old=a,new=b,count=n));return s.replace(a,b)
# Exact original failure-only projection, with all old procedural X/Z semantics.
projection='''        if(fifo_pop)begin
            if(!memory_clear_pending)begin
                if(fifo_read_data[63:32]!=memory_next_index ||
                   (!fifo_read_data[64] && memory_next_index>=CAPACITY_FRAMES))begin
                    memory_failure<=F_PROTOCOL;
                end
            end
        end
        if(memory_command_start)begin
            if(memory_channel_fault || memory_fault_now)begin end
            else case(command_kind)
                CMD_START:begin if(start_context_bad)memory_failure<=F_PROTOCOL;end
                CMD_CLEAR:begin
                    if(command_generation!=memory_generation+1'b1 || memory_generation==32'hffffffff)
                        memory_failure<=F_PROTOCOL;
                end
                CMD_FETCH:begin end
                default:memory_failure<=F_PROTOCOL;
            endcase
        end
        if(global_failure_write)memory_failure<=global_failure_value;
'''
protocol='''    wire failure_fifo_without_fault=fifo_read_valid && memory_reset_n && !memory_channel_fault &&
        !memory_command_start && (clear_fifo_pop || (!memory_clear_pending && normal_fifo_pop));
    reg memory_failure_protocol_write /* synthesis syn_keep=1 */;
    always @* begin
        memory_failure_protocol_write=0;
        if(failure_fifo_without_fault)begin
            if(!memory_clear_pending)begin
                if(fifo_read_data[63:32]!=memory_next_index ||
                   (!fifo_read_data[64] && memory_next_index>=CAPACITY_FRAMES))begin
                    memory_failure_protocol_write=1;
                end
            end
        end
        if(memory_command_start)begin
            if(memory_channel_fault)begin end
            else case(command_kind)
                CMD_START:begin if(start_context_bad)memory_failure_protocol_write=1;end
                CMD_CLEAR:begin
                    if(command_generation!=memory_generation+1'b1 || memory_generation==32'hffffffff)
                        memory_failure_protocol_write=1;
                end
                CMD_FETCH:begin end
                default:memory_failure_protocol_write=1;
            endcase
        end
    end
'''
block='''    // Private failure-code writes keep the original edge and first-fault rule.
    // A known immediate fault suppresses every protocol write, so it reaches
    // the final write enable directly. Its zero cofactor has no fault feedback;
    // unknown fault values retain the exact original procedural projection.
'''+protocol+'''    always @(posedge memory_clk_i or negedge memory_reset_n)begin
        if(!memory_reset_n)memory_failure<=0;
        else case(memory_fault_now)
            1'b1:begin
                if(!memory_channel_fault)memory_failure<=global_failure_value;
            end
            1'b0:begin
                if(memory_failure_protocol_write)memory_failure<=F_PROTOCOL;
            end
            default:begin
'''+''.join('        '+line+'\n' for line in projection.splitlines())+'''            end
        endcase
    end

'''
# No other target/RHS/order is changed by isolating this private register.
new=replace(old,'memory_channel_fault<=0;memory_failure<=0;pack_frames<=0;','memory_channel_fault<=0;pack_frames<=0;')
new=replace(new,'memory_channel_fault<=1;memory_failure<=F_PROTOCOL;\n','memory_channel_fault<=1;\n',3)
new=replace(new,'memory_channel_fault<=1;memory_failure<=F_PROTOCOL;completion_code<=F_PROTOCOL;','memory_channel_fault<=1;completion_code<=F_PROTOCOL;')
new=replace(new,'            if(global_failure_write)memory_failure<=global_failure_value;\n','')
anchor='    always @(posedge memory_clk_i or negedge memory_reset_n)begin\n        if(!memory_reset_n)begin\n            command_req_meta<=0;'
new=replace(new,anchor,block+anchor)
inverse=new
for c in reversed(changes):
 if c['new']:
  assert inverse.count(c['new'])==c['count'],('inverse',c)
  inverse=inverse.replace(c['new'],c['old'])
 else:
  marker='            if(memory_fault_now)begin\n                memory_channel_fault<=1;memory_fetch_cancel<=1;\n            end\n';assert inverse.count(marker)==1
  inverse=inverse.replace(marker,marker+c['old'])
assert inverse==old
nbas=lambda s:re.findall(r'\b(\w+(?:\[[^]]+\])?)\s*<=\s*([^;]+);',s)
assert [x for x in nbas(old)if x[0]!='memory_failure']==[x for x in nbas(new)if x[0]!='memory_failure']
assert len([x for x in nbas(old)if x[0]=='memory_failure'])==6
assert new==maintained_text and block==pin.FAILURE_BLOCK
assert pin.apply_failure_final_ce(old)==new
candidate=O/'candidate.sv';candidate.write_text(maintained_text);reference=O/'reference.sv';reference.write_text(old.replace('module workstation_ble_raw_ddr_store #(','module workstation_ble_raw_ddr_store_reference #(',1));(O/'before.sv').write_text(old)
(O/'proposed.patch').write_text(''.join(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile='a/rtl/memory/workstation_ble_raw_ddr_store.sv',tofile='b/rtl/memory/workstation_ble_raw_ddr_store.sv')))
# Reuse the exact maintained complete-owner miter generator, never a reduced owner.
helper_src=ROOT/'sim/memory/prove_ble_raw_start_factor.py';helper=O/'helper.py';helper.write_bytes(helper_src.read_bytes());spec=importlib.util.spec_from_file_location('raw_complete_helper',helper);h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)
tb_src=ROOT/'sim/memory/tb_ble_raw_ddr_store.sv';h.TB=O/'tb-source.sv';h.TB.write_bytes(tb_src.read_bytes())
deps=[];inputs=[source,helper_src,tb_src,Path(__file__),helper_path]
for rel in ['rtl/memory/workstation_sdp.sv','rtl/music/music_async_fifo.sv','rtl/memory/workstation_recording_ddr_native_bridge.sv']:
 p=ROOT/rel;q=O/'inputs'/rel;q.parent.mkdir(parents=True,exist_ok=True);q.write_bytes(p.read_bytes());deps.append(q);inputs.append(p)
ports,states,nets=h.inventories(old);np,ns,nn=h.inventories(new);assert np==ports and ns==sorted(states+['memory_failure_protocol_write']) and nn==sorted(nets+['failure_fifo_without_fault'])
twin,inventory=h.twin_bench(old,ports,states,nets);(O/'twin.sv').write_text(twin)
comb=['start_fault_now','start_initialize','clear_initialize','global_failure_write','global_failure_value'];seq=[n for n in states if n not in comb]
directed,cases=h.directed_bench(ports,seq,nets+comb)
# These are actual module inputs/old state, not forced derived fault/predicate wires.
base={'command_req_sync':'0','command_req_meta':'0','command_req':'0','memory_failure':"4'hc"}
extra=[
 ('transport',{**base,'transport_fault_i':'1'},'if(dut.memory_failure!==7)$fatal(1,"transport final CE");'),
 ('transport_sticky',{**base,'transport_fault_i':'1','memory_channel_fault':'1'},'if(dut.memory_failure!==12)$fatal(1,"first fault sticky");'),
 ('transport_unknown_sticky',{**base,'transport_fault_i':'1','memory_channel_fault':"1'bx"},'if(dut.memory_failure!==12)$fatal(1,"X sticky guard");'),
 ('transport_Z_sticky',{**base,'transport_fault_i':'1','memory_channel_fault':"1'bz"},'if(dut.memory_failure!==12)$fatal(1,"Z sticky guard");'),
 ('transport_over_timeout_cancel',{**base,'transport_fault_i':'1','published_valid':'1','command_wait':'2047','read_outstanding':'1','read_wait':'2047','cancel_sync':'1'},'if(dut.memory_failure!==7 || dut.memory_fetch_cancel!==1 || dut.cancel_seen!==1)$fatal(1,"fault timeout cancel priority");'),
 ('X_bridge_command',{**base,'transport_fault_i':"1'bx",'published_valid':'1','command_wait':'2047'},"if(dut.memory_failure!==4'b01x1)$fatal(1,\"X fault code merge\");"),
 ('Z_bridge_read',{**base,'transport_fault_i':"1'bz",'read_outstanding':'1','read_wait':'2047'},"if(dut.memory_failure!==4'b011x)$fatal(1,\"Z fault code merge\");"),
 ('command_timeout',{**base,'published_valid':'1','command_wait':'2047'},'if(dut.memory_failure!==5)$fatal(1,"command timeout");'),
 ('read_timeout',{**base,'read_outstanding':'1','read_wait':'2047'},'if(dut.memory_failure!==6)$fatal(1,"read timeout");'),
 ('response_fault',{**base,'read_response_i':'1'},'if(dut.memory_failure!==8)$fatal(1,"response fault");'),
 ('unknown_fault_protocol',{'command_kind':'3','transport_fault_i':"1'bx",'memory_failure':"4'hc"},'if(dut.memory_failure!==8)$fatal(1,"unknown fault procedural command else");'),
 ('X_channel_protocol',{'command_kind':'3','memory_channel_fault':"1'bx",'memory_failure':"4'hc"},'if(dut.memory_failure!==8)$fatal(1,"X channel procedural else");'),
 ('bad_start_clear_same_edge',{'command_kind':'0','memory_empty':'0','memory_clear_pending':'1','memory_failure':"4'hc"},'if(dut.memory_failure!==8 || dut.completion_code!==0)$fatal(1,"protocol code and later clear completion keep independent NBA priorities");'),
 ('cancel_fetch_fault',{**base,'memory_fetch_active':'1','fetch_beats_total':'1','cancel_sync':'1','transport_fault_i':'1'},'if(dut.memory_failure!==7 || dut.completion_code!==10)$fatal(1,"cancel completion uses old channel/code before same edge global fault");'),
]
inputs_names={n for n,p in ports.items()if p[0]=='input'};lines=[]
for i,(name,values,check)in enumerate(extra,50):
 lines+=['set_base;twin_case='+str(i)+';']
 for n,v in values.items():lines.append(n+'='+v+';'if n in inputs_names else'dut.'+n+'='+v+';reference.'+n+'='+v+';')
 lines+=['#0.1;compare_all;step;',check,'$display("PASS directed '+name+'");']
anchor='// Every old register is independently randomized';assert directed.count(anchor)==1;directed=directed.replace(anchor,'\n'.join(lines)+'\n'+anchor).replace('directed_cases=18 random_four_state_edges=4096','directed_cases='+str(len(cases)+len(extra))+' random_four_state_edges=4096');(O/'directed.sv').write_text(directed)
# Exact-source equations tie the cofactor and projection to the maintained DAG.
assert h.expression(old,'fifo_read_ready','assign')=='memory_reset_n && !memory_channel_fault && !memory_fault_now && !memory_command_start && (clear_fifo_pop || (!memory_clear_pending && normal_fifo_pop))'
assert h.expression(old,'fifo_pop')=='fifo_read_valid && fifo_read_ready'
assert h.expression(old,'memory_fault_now')=='bridge_fault || command_expired || read_expired || response_bad'
# Project only constant F_PROTOCOL writes. The generated full twin checks the actual nested module.
constants=re.search(r'    localparam \[3:0\] F_OVERFLOW=.*?;',old,re.S)[0]
globalblock=old[old.index('    reg global_failure_write;'):old.index('    // Retire one previously admitted FIFO word')]
four='''`timescale 1ns/1ps
module failure_four;
function automatic logic digit(input integer n);case(n)0:digit=0;1:digit=1;2:digit=1'bx;3:digit=1'bz;endcase endfunction
reg bridge_fault,command_expired,read_expired,response_bad,memory_channel_fault,fifo_without,clear_pending,fifo_bad,command_start;
reg command_bad;
wire memory_fault_now=bridge_fault || command_expired || read_expired || response_bad;
wire fifo_pop=fifo_without && !memory_fault_now;
'''+constants+'\n'+globalblock+'''
reg old_write,new_write,protocol_zero;reg [3:0] old_value,new_value;
integer vector_index,bit_index;reg [8:0] flags;integer vectors=0;
initial begin
for(vector_index=0;vector_index<262144;vector_index=vector_index+1)begin
for(bit_index=0;bit_index<9;bit_index=bit_index+1)flags[bit_index]=digit((vector_index>>(2*bit_index))&3);
{bridge_fault,command_expired,read_expired,response_bad,memory_channel_fault,fifo_without,clear_pending,fifo_bad,command_start}=flags;
for(integer c=0;c<2;c=c+1)begin command_bad=c;#0.001;
old_write=0;old_value=F_PROTOCOL;
if(fifo_pop)begin if(!clear_pending)begin if(fifo_bad)begin old_write=1;old_value=F_PROTOCOL;end end end
if(command_start)begin if(memory_channel_fault || memory_fault_now)begin end else if(command_bad)begin old_write=1;old_value=F_PROTOCOL;end end
if(global_failure_write)begin old_write=1;old_value=global_failure_value;end
protocol_zero=0;
if(fifo_without)begin if(!clear_pending)begin if(fifo_bad)protocol_zero=1;end end
if(command_start)begin if(memory_channel_fault)begin end else if(command_bad)protocol_zero=1;end
new_write=0;new_value=F_PROTOCOL;
case(memory_fault_now)
1'b1:begin if(!memory_channel_fault)begin new_write=1;new_value=global_failure_value;end end
1'b0:begin if(protocol_zero)begin new_write=1;new_value=F_PROTOCOL;end end
default:begin
if(fifo_pop)begin if(!clear_pending)begin if(fifo_bad)begin new_write=1;new_value=F_PROTOCOL;end end end
if(command_start)begin if(memory_channel_fault || memory_fault_now)begin end else if(command_bad)begin new_write=1;new_value=F_PROTOCOL;end end
if(global_failure_write)begin new_write=1;new_value=global_failure_value;end
end
endcase
if(old_write!==new_write || (old_write && old_value!==new_value))$fatal(1,"final failure CE/value four-state vector=%0d command=%0d old=%b/%b new=%b/%b",vector_index,c,old_write,old_value,new_write,new_value);
vectors=vectors+1;
end end
$display("PASS final failure CE/value four-state vectors=%0d prior_failure_bits_free=4 no_reachability_assumptions=1",vectors);$finish;
end endmodule
''';(O/'failure-four.sv').write_text(four)
# Additionally exhaust actual protocol kind/bad-condition procedural projection.
projection_four='''`timescale 1ns/1ps
module protocol_four;
function automatic logic digit(input integer n);case(n)0:digit=0;1:digit=1;2:digit=1'bx;3:digit=1'bz;endcase endfunction
reg [1:0] command_kind;reg start_context_bad,clear_bad,command_start,channel,fault;
reg before_enable,cofactor_enable;localparam [1:0] CMD_START=0,CMD_CLEAR=1,CMD_FETCH=2;
integer i;initial begin
for(i=0;i<16384;i=i+1)begin
command_kind={digit(i&3),digit((i>>2)&3)};start_context_bad=digit((i>>4)&3);clear_bad=digit((i>>6)&3);command_start=digit((i>>8)&3);channel=digit((i>>10)&3);fault=digit((i>>12)&3);
#0.001;before_enable=0;cofactor_enable=0;
if(command_start)begin if(channel || fault)begin end else case(command_kind)
CMD_START:if(start_context_bad)before_enable=1;CMD_CLEAR:if(clear_bad)before_enable=1;CMD_FETCH:begin end default:before_enable=1;endcase end
case(fault)
1'b1:begin end
1'b0:begin if(command_start)begin if(channel)begin end else case(command_kind)
CMD_START:if(start_context_bad)cofactor_enable=1;CMD_CLEAR:if(clear_bad)cofactor_enable=1;CMD_FETCH:begin end default:cofactor_enable=1;endcase end end
default:begin if(command_start)begin if(channel || fault)begin end else case(command_kind)
CMD_START:if(start_context_bad)cofactor_enable=1;CMD_CLEAR:if(clear_bad)cofactor_enable=1;CMD_FETCH:begin end default:cofactor_enable=1;endcase end end
endcase
if(before_enable!==cofactor_enable)$fatal(1,"protocol case projection i=%0d",i);
end
$display("PASS exact protocol kind/start/clear four-state vectors=16384");$finish;
end endmodule
''';(O/'protocol-four.sv').write_text(projection_four)
inputs += [candidate,reference,O/'before.sv',helper,h.TB,*deps,O/'twin.sv',O/'directed.sv',O/'failure-four.sv',O/'protocol-four.sv'];before={str(p):sha(p)for p in inputs}
result=dict(stage='maintained_final_memory_failure_CE_cofactor',source_implementation=True,captured_utc=datetime.now(timezone.utc).isoformat(),passed=False,source_sha256=sha(source),candidate_sha256=sha(candidate),exact_source_inverse=True,all_other_targets_global_NBA_target_RHS_order_identical=True,source_replacements=changes,source_input_sha256=before,whole_owner_inventory=inventory,directed_cases=cases+[n for n,_,_ in extra],cases={},negative_controls={},source_modified_by_runner=False,EDA_started=False,hardware_tested=False,timing_or_resource_gain_claimed=False,limits=['No physical gain or timing closure claim; full sequential formal is not proved.','Final memory_failure is isolated on the same clock/reset; all other owner state, mailbox and native interface remains byte-identical.'])
try:
 result['cases']['failure_four']=h.simulate(O,'failure-four',[O/'failure-four.sv'],'failure_four',timeout=180)
 result['cases']['protocol_four']=h.simulate(O,'protocol-four',[O/'protocol-four.sv'],'protocol_four',timeout=120)
 for name,params in [('fifo8_async_memory',[('FIFO_BITS',8),('MEM_HALF',7)]),('fifo3_100mhz_memory',[('FIFO_BITS',3),('MEM_HALF',5)])]:result['cases'][name]=h.simulate(O,name,[O/'twin.sv',candidate,reference,*deps],'tb_ble_raw_ddr_store',params,timeout=180)
 result['cases']['arbitrary_state']=h.simulate(O,'arbitrary-state',[O/'directed.sv',candidate,reference,*deps],'directed',timeout=180)
 mutants=[
 ('wrong_transport_code','if(!memory_channel_fault)memory_failure<=global_failure_value;','if(!memory_channel_fault)memory_failure<=F_PROTOCOL;'),
 ('drop_sticky_guard','if(!memory_channel_fault)memory_failure<=global_failure_value;','memory_failure<=global_failure_value;'),
 ('drop_unknown_fallback','            default:begin\n'+''.join('        '+line+'\n'for line in projection.splitlines())+'            end','            default:begin end'),
 ('unknown_channel_false_guard','            if(memory_channel_fault)begin end\n            else case(command_kind)','            if(memory_channel_fault!==1\'b0)begin end\n            else case(command_kind)'),
 ('change_earlier_protocol_code','if(memory_failure_protocol_write)memory_failure<=F_PROTOCOL;','if(memory_failure_protocol_write)memory_failure<=F_TRANSPORT;'),
 ]
 for name,a,b in mutants:
  assert new.count(a)==1,(name,new.count(a));m=O/(name+'.sv');m.write_text(new.replace(a,b));result['negative_controls'][name]=h.simulate(O,name,[O/'directed.sv',m,reference,*deps],'directed',expected='complete raw twin',timeout=180)
 assert before=={str(p):sha(p)for p in inputs};result['passed']=True
finally:
 (O/'verification.json').write_text(json.dumps(result,indent=2)+'\n')
if result['passed']:
 files={str(p.relative_to(O)):sha(p)for p in O.rglob('*')if p.is_file()};(O/'seal.json').write_text(json.dumps(dict(file_sha256=files,verification_sha256=sha(O/'verification.json'),script_sha256=sha(__file__),inputs_reverified=True,source_modified_by_runner=False,EDA_started=False,hardware_tested=False),indent=2)+'\n');print(json.dumps({'candidate_sha256':sha(candidate),'verification_sha256':sha(O/'verification.json'),'seal_sha256':sha(O/'seal.json'),'files':len(files)},indent=2))
