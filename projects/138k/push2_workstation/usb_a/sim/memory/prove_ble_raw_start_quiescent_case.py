#!/usr/bin/env python3
from pathlib import Path
import hashlib,json,importlib.util,difflib,time,re,sys
import z3
import argparse
parser=argparse.ArgumentParser(description='Prove the complete raw START quiescent case against its immutable consumed W12 source');parser.add_argument('--output',type=Path,required=True);args=parser.parse_args();out=args.output.resolve();out.mkdir(exist_ok=False);root=Path(__file__).resolve().parents[2];stage=root;sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();source=root/'rtl/memory/workstation_ble_raw_ddr_store.sv';baseline=Path(__file__).with_name('fixtures')/'workstation_ble_raw_ddr_store_before_start_case.sv';assert sha(baseline)=='214c0a5df77d11921fecb4848e5897f7b116de039f48b69cae47b7953809da1d';old=baseline.read_text();helper_src=root/'sim/memory/prove_ble_raw_start_factor.py';helper=out/'proof_helper_snapshot.py';helper.write_bytes(helper_src.read_bytes());tb=out/'tb_ble_raw_ddr_store.sv';tb.write_bytes((root/'sim/memory/tb_ble_raw_ddr_store.sv').read_bytes());spec=importlib.util.spec_from_file_location('h',helper);h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h);h.TB=tb
old_guard='''        start_initialize=0;
        if(memory_command_start)begin
            if(memory_channel_fault || start_fault_now)begin end
            else if(command_kind==CMD_START)begin
                if(start_context_bad)begin end
                else start_initialize=1;
            end
        end
'''
new_guard='''        start_initialize=0;
        // An occupied memory slot makes start_context_bad known true. Keep
        // its false and unknown cases explicit so binary mapping need not
        // share the complete command/read fault cone into wide START state.
        case(memory_quiescent)
            1'b0:begin end
            1'b1:begin
                if(memory_command_start)begin
                    if(memory_channel_fault || transport_fault_i || native_protocol_fault_o ||
                       unused_submitted || native_accept_i || read_response_i)begin end
                    else if(command_kind==CMD_START)begin
                        if(start_context_bad)begin end
                        else start_initialize=1;
                    end
                end
            end
            default:begin
                if(memory_command_start)begin
                    if(memory_channel_fault || start_fault_now)begin end
                    else if(command_kind==CMD_START)begin
                        if(start_context_bad)begin end
                        else start_initialize=1;
                    end
                end
            end
        endcase
'''
preload_proof = Path(__file__).with_name('prove_ble_raw_return_mailbox_preload.py')
preload_fixture = (Path(__file__).with_name('fixtures') /
                   'workstation_ble_raw_ddr_store_before_return_preload.sv')
preload_spec = importlib.util.spec_from_file_location('return_preload_inverse', preload_proof)
preload = importlib.util.module_from_spec(preload_spec)
preload_spec.loader.exec_module(preload)
assert sha(preload_fixture) == preload.BASELINE_SHA256
global_proof = Path(__file__).with_name('prove_ble_raw_global_failure_case.py')
global_fixture = (Path(__file__).with_name('fixtures') /
                  'workstation_ble_raw_ddr_store_before_global_failure_case.sv')
global_spec = importlib.util.spec_from_file_location('global_failure_inverse', global_proof)
global_failure = importlib.util.module_from_spec(global_spec)
global_spec.loader.exec_module(global_failure)
assert sha(global_fixture) == global_failure.BASELINE_SHA256
clear_proof=Path(__file__).with_name('prove_ble_raw_clear_quiescent_case.py');clear_baseline=Path(__file__).with_name('fixtures')/'workstation_ble_raw_ddr_store_before_clear_case.sv';clear_spec=importlib.util.spec_from_file_location('clear_inverse',clear_proof);clear=importlib.util.module_from_spec(clear_spec);clear_spec.loader.exec_module(clear);assert sha(clear_baseline)==clear.BASELINE_SHA256;normalized=clear.restore_before_clear(global_failure.restore_before_global_failure(preload.restore_before_return_preload(source.read_text())));assert normalized==clear_baseline.read_text()
assert old.count(old_guard)==1;new=old.replace(old_guard,new_guard);assert new.replace(new_guard,old_guard)==old;assert normalized==new,'exact CLEAR inverse escapes reviewed START case split';variant=out/'normalized-before-clear.sv';variant.write_text(new);(out/'variant.sv').write_text(new);reference=out/'reference.sv';reference.write_text(old.replace('module workstation_ble_raw_ddr_store #(','module workstation_ble_raw_ddr_store_reference #(',1));(out/'proposed.patch').write_text(''.join(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile='a/rtl/memory/workstation_ble_raw_ddr_store.sv',tofile='b/rtl/memory/workstation_ble_raw_ddr_store.sv')))
assert h.expression(old,'start_context_bad')=='!memory_empty || !memory_closed || memory_active || memory_clear_pending || memory_fetch_active || pack_frames!=0 || !memory_quiescent || fifo_consumed!=command_event_target || command_generation!=memory_generation+1\'b1 || memory_generation==32\'hffffffff'
quiet,residual,full,fast,cmd,channel=z3.Bools('quiet residual full fast cmd channel');kind=z3.BitVec('kind',2);context=z3.Or(residual,z3.Not(quiet));old_enable=z3.And(cmd,z3.Not(z3.Or(channel,z3.If(quiet,fast,full))),kind==0,z3.Not(context));new_enable=z3.And(quiet,cmd,z3.Not(z3.Or(channel,fast)),kind==0,z3.Not(context));sol=z3.Solver();sol.add(old_enable!=new_enable);assert sol.check()==z3.unsat
# All non-guard source bytes and all sequential NBA locations/priorities stay exact.
ports,states,nets=h.inventories(old);assert h.inventories(new)==(ports,states,nets);twin,inventory=h.twin_bench(old,ports,states,nets);(out/'twin.sv').write_text(twin);state_registers=[x for x in states if x not in ('start_fault_now','start_initialize')];directed,cases=h.directed_bench(ports,state_registers,nets+['start_fault_now','start_initialize']);(out/'directed.sv').write_text(directed)
# The guards below are extracted verbatim from the sealed source/candidate;
# only source equation expressions are abstracted by independent four-state predicates.
current_start=old[old.index('        start_initialize=0;'):old.index('\n    end\n    wire clear_fifo_pop',old.index('        start_initialize=0;'))]
case_start=new[new.index('        start_initialize=0;'):new.index('\n    end\n    wire clear_fifo_pop',new.index('        start_initialize=0;'))]
case_start=case_start.replace('start_initialize','case_initialize')
four='''`timescale 1ns/1ps
module guard_four_state;
function automatic logic digit(input integer n);case(n)0:digit=0;1:digit=1;2:digit=1'bx;3:digit=1'bz;endcase endfunction
reg memory_quiescent,residual_bad,full_fault,fast_fault,memory_command_start,memory_channel_fault;
reg [1:0] command_kind;localparam [1:0] CMD_START=0;
wire start_context_bad=residual_bad || !memory_quiescent;
wire transport_fault_i=fast_fault,native_protocol_fault_o=0,unused_submitted=0,native_accept_i=0,read_response_i=0;
reg start_fault_now,start_initialize,case_initialize;
always @* begin start_fault_now=full_fault;if(memory_quiescent)start_fault_now=fast_fault;end
always @* begin
'''+current_start+'''\nend
always @* begin
'''+case_start+'''\nend
integer index;initial begin
for(index=0;index<65536;index=index+1)begin
memory_quiescent=digit(index&3);residual_bad=digit((index>>2)&3);full_fault=digit((index>>4)&3);fast_fault=digit((index>>6)&3);memory_command_start=digit((index>>8)&3);memory_channel_fault=digit((index>>10)&3);command_kind={digit((index>>14)&3),digit((index>>12)&3)};
#0.001;if(start_initialize!==case_initialize)$fatal(1,"four-state guard changed index=%0d",index);
end
$display("PASS verbatim procedural guards four_state_combinations=65536 independent_predicates=6 kind_bits=2 exact_context_quiescent_relation=1");$finish;
end endmodule
''';(out/'guard-four-state.sv').write_text(four)
deps=[stage/'rtl/memory/workstation_sdp.sv',stage/'rtl/music/music_async_fifo.sv',stage/'rtl/memory/workstation_recording_ddr_native_bridge.sv'];inputs=[source,baseline,helper_src,helper,tb,variant,reference,clear_proof,clear_baseline,global_proof,global_fixture,preload_proof,preload_fixture,Path(__file__),*deps];before={str(p):sha(p) for p in inputs};result=dict(schema=1,passed=False,scope='complete maintained raw START quiescent case split against immutable W12 source',baseline_W12_SHA256=sha(baseline),maintained_source_sha256=sha(source),normalized_pre_CLEAR_sha256=sha(variant),exact_reviewed_CLEAR_inverse=True,exact_reviewed_global_failure_inverse=True,exact_reviewed_return_preload_inverse=True,variant_sha256=sha(variant),patch_sha256=sha(out/'proposed.patch'),exact_inverse_and_all_other_source_bytes=True,all_NBA_order_and_positions_unchanged=True,binary_guard_equivalence='UNSAT',four_state_guard_equation='start_context_bad = residual_bad OR !memory_quiescent; full/fast faults unrestricted',whole_twin_inventory=inventory,directed_cases=cases,input_sha256=before,cases={},source_implementation=True,synthesis=False,pnr=False,hardware_tested=False,timing_or_resource_improvement_claimed=False,runner_sha256=sha(Path(__file__)))
try:
 result['cases']['guard_four_state']=h.simulate(out,'guard-four-state',[out/'guard-four-state.sv'],'guard_four_state')
 for name,params in [('fifo8_async_memory',[('FIFO_BITS',8),('MEM_HALF',7)]),('fifo3_100mhz_memory',[('FIFO_BITS',3),('MEM_HALF',5)])]:result['cases'][name]=h.simulate(out,name,[out/'twin.sv',variant,reference,*deps],'tb_ble_raw_ddr_store',params,timeout=180)
 result['cases']['arbitrary_state']=h.simulate(out,'arbitrary-state',[out/'directed.sv',variant,reference,*deps],'directed',timeout=180)
 # Exact unknown fallback and immediate veto negative controls.
 for name,a,b in [('drop_unknown_fallback',"            default:begin\n                if(memory_command_start)begin",'            default:begin\n                if(1\'b0)begin'),('drop_fast_native_veto','unused_submitted || native_accept_i || read_response_i)begin end','unused_submitted || read_response_i)begin end'),('allow_occupied_START',"            1'b0:begin end","            1'b0:begin start_initialize=1;end")]:
  assert new.count(a)==1;mutant=out/(name+'.sv');mutant.write_text(new.replace(a,b));result['cases'][name]=h.simulate(out,name,[out/'directed.sv',mutant,reference,*deps],'directed',expected='complete raw twin')
 assert before=={str(p):sha(p) for p in inputs};result['passed']=True
finally:(out/'verification.json').write_text(json.dumps(result,indent=2)+'\n')
print('PASS complete maintained raw START quiescent case split',flush=True)
