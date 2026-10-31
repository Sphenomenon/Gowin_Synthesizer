#!/usr/bin/env python3
"""Prove the maintained CLEAR completion cofactor against the immutable W13 raw store."""
from pathlib import Path
import argparse
import importlib.util
import re
import json
import hashlib
import difflib
import z3

BASELINE_SHA256 = '21471d722da294e841829f6ff1ec396fab016358bf6a796f93d17ec0f95c978d'
MAINTAINED_SHA256 = '39ae3b918a4674f849eb0663bb193e2890881f164063f22b473b5dbb61df290b'
OLD_CLEAR_GUARD = 'if(memory_clear_pending && fifo_consumed==memory_clear_target &&\n               !fifo_read_valid && memory_quiescent && !memory_channel_fault && !memory_fault_now)begin'
NEW_CLEAR_GUARD = 'if(clear_initialize)begin'
CLEAR_BLOCK = "    // Cache-only proposal: the CLEAR completion assignments remain in their\n    // original sequential position. Only a known quiescent slot uses the exact\n    // immediate fault cofactor; unknown quiescence retains the complete guard.\n    reg clear_initialize;\n    always @* begin\n        clear_initialize=0;\n        case(memory_quiescent)\n            1'b0:begin end\n            1'b1:begin\n                if(memory_clear_pending && fifo_consumed==memory_clear_target &&\n                   !fifo_read_valid && !memory_channel_fault &&\n                   !(transport_fault_i || native_protocol_fault_o ||\n                     unused_submitted || native_accept_i || read_response_i))\n                    clear_initialize=1;\n            end\n            default:begin\n                if(memory_clear_pending && fifo_consumed==memory_clear_target &&\n                   !fifo_read_valid && memory_quiescent && !memory_channel_fault && !memory_fault_now)\n                    clear_initialize=1;\n            end\n        endcase\n    end\n"

def restore_before_clear(text):
    """Invert only the one reviewed CLEAR insertion; fail on every byte drift."""
    if hashlib.sha256(text.encode()).hexdigest() != MAINTAINED_SHA256:
        raise ValueError('maintained CLEAR source identity changed')
    if text.count(CLEAR_BLOCK) != 1 or text.count(NEW_CLEAR_GUARD) != 1:
        raise ValueError('reviewed CLEAR block/guard anchor changed')
    restored = text.replace(CLEAR_BLOCK, '', 1).replace(NEW_CLEAR_GUARD, OLD_CLEAR_GUARD, 1)
    if hashlib.sha256(restored.encode()).hexdigest() != BASELINE_SHA256:
        raise ValueError('exact pre-CLEAR source reconstruction changed')
    return restored


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args();root=Path(__file__).resolve().parents[2];out=args.output.resolve();out.mkdir(parents=True,exist_ok=False);sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    source=root/'rtl/memory/workstation_ble_raw_ddr_store.sv';baseline=Path(__file__).with_name('fixtures')/'workstation_ble_raw_ddr_store_before_clear_case.sv';assert sha(baseline)==BASELINE_SHA256;old=baseline.read_text();assert restore_before_clear(source.read_text())==old;helper_src=root/'sim/memory/prove_ble_raw_start_factor.py';helper=out/'proof-helper-snapshot.py';helper.write_bytes(helper_src.read_bytes());s=importlib.util.spec_from_file_location('h',helper);h=importlib.util.module_from_spec(s);s.loader.exec_module(h);tb=out/'tb-source.sv';tb.write_bytes((root/'sim/memory/tb_ble_raw_ddr_store.sv').read_bytes());h.TB=tb
    oldguard=OLD_CLEAR_GUARD;newguard=NEW_CLEAR_GUARD;block=CLEAR_BLOCK
    assert old.count(oldguard)==1 and old.count('    wire clear_fifo_pop=')==1
    new=old.replace(oldguard,newguard).replace('    wire clear_fifo_pop=',block+'    wire clear_fifo_pop=');assert new.replace(block,'').replace(newguard,oldguard)==old
    assert re.findall(r'\b(\w+(?:\[[^]]+\])?)\s*<=\s*([^;]+);',old)==re.findall(r'\b(\w+(?:\[[^]]+\])?)\s*<=\s*([^;]+);',new)
    assert new==source.read_text();variant=source;(out/'variant.sv').write_text(new);reference=out/'reference.sv';reference.write_text(old.replace('module workstation_ble_raw_ddr_store #(','module workstation_ble_raw_ddr_store_reference #(',1));(out/'proposed.patch').write_text(''.join(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile='a/rtl/memory/workstation_ble_raw_ddr_store.sv',tofile='b/rtl/memory/workstation_ble_raw_ddr_store.sv')))
    ports,states,nets=h.inventories(old);assert h.inventories(new)==(ports,sorted(states+['clear_initialize']),nets);twin,inventory=h.twin_bench(old,ports,states,nets);(out/'twin.sv').write_text(twin);seqstates=[x for x in states if x not in ('start_fault_now','start_initialize')];directed,cases=h.directed_bench(ports,seqstates,nets+['start_fault_now','start_initialize'])
    cases_more=[('clear_transport',{'transport_fault_i':'1'}),('clear_sticky_protocol',{'native_bridge.protocol_fault_o':'1'}),('clear_stale_submitted',{'native_bridge.submitted_o':'1'}),('clear_native_accept',{'native_accept_i':'1'}),('clear_response',{'read_response_i':'1'}),('clear_channel',{'memory_channel_fault':'1'}),('clear_X_transport',{'transport_fault_i':"1'bx"}),('clear_Z_submitted',{'native_bridge.submitted_o':"1'bz"}),('clear_published',{'published_valid':'1'}),('clear_read_outstanding',{'read_outstanding':'1'}),('clear_return_pending',{'return_pending':'1'}),('clear_pack_pending',{'pack_word_valid':'1'}),('clear_X_quiescent',{'published_valid':"1'bx"}),('clear_Z_quiescent',{'read_outstanding':"1'bz"}),('clear_target_mismatch',{'memory_clear_target':'3'}),('clear_command_timeout',{'published_valid':'1','command_wait':'2047'}),('clear_read_timeout',{'read_outstanding':'1','read_wait':'2047'}),('clear_X_channel',{'memory_channel_fault':"1'bx"})]
    input_names={name for name,row in ports.items() if row[0]=='input'};extra=[]
    for i,(name,values) in enumerate(cases_more,50):
     lines=['set_base; twin_case='+str(i)+';','dut.memory_clear_pending=1;reference.memory_clear_pending=1;']
     for name_,value in values.items():lines.append(name_+'='+value+';' if name_ in input_names else 'dut.'+name_+'='+value+';reference.'+name_+'='+value+';')
     lines+=['#0.1;compare_all;step;','$display("PASS directed '+name+'");'];extra.extend(lines)
    anchor='// Every old register is independently randomized';assert directed.count(anchor)==1;directed=directed.replace(anchor,'\n'.join(extra)+'\n'+anchor);directed=directed.replace('directed_cases=18 random_four_state_edges=4096','directed_cases=36 random_four_state_edges=4096');(out/'directed.sv').write_text(directed)
    # Exact source equations, with counter comparisons independent over every value.
    bridge=root/'rtl/memory/workstation_recording_ddr_native_bridge.sv';eq={name:h.expression(bridge.read_text(),name,kind) for name,kind in [('native_ready_o','assign'),('protocol_fault_now','wire'),('transport_fault_o','assign')]}
    for name in ('native_commit','native_read_commit','command_expired','read_expired','response_bad','memory_fault_now','memory_quiescent','memory_command_start'):eq[name]=h.expression(old,name);assert eq[name]==h.expression(new,name)
    assert h.NEW_BLOCK in old and h.NEW_BLOCK in new
    for name,mutant in [('body_drift',new.replace('    reg clear_initialize;','    reg clear_initialize_changed;',1)),('guard_drift',new.replace('if(clear_initialize)begin','if(!clear_initialize)begin',1))]:
     try:restore_before_clear(mutant)
     except ValueError:pass
     else:raise AssertionError(('CLEAR source inverse drift accepted',name))
    (out/'actual-fault-four-state.sv').write_text(h.four_state_bench(eq,old))
    p,r,ret,pack,n,s,t,f,response,write,cb,rb,clear,target,fifo,channel=z3.Bools('published read return_pending pack native submitted transport sticky response write command_limit read_limit clear target fifo channel')
    ready=z3.And(n,s);native=z3.And(p,ready);protocol=z3.Or(z3.And(n,z3.Or(z3.Not(s),z3.Not(p))),z3.And(s,z3.Not(p)));fault=z3.Or(t,f,protocol,z3.And(p,z3.Not(ready),cb),z3.And(r,z3.Not(response),rb),z3.And(response,z3.Not(r),z3.Not(z3.And(native,z3.Not(write)))));quiet=z3.And(z3.Not(p),z3.Not(r),z3.Not(ret),z3.Not(pack));fast=z3.Or(t,f,s,n,response);a=z3.And(clear,target,z3.Not(fifo),quiet,z3.Not(channel),z3.Not(fault));b=z3.And(quiet,clear,target,z3.Not(fifo),z3.Not(channel),z3.Not(fast));solver=z3.Solver();solver.add(a!=b);assert solver.check()==z3.unsat
    # Both guards are taken from the exact source strings. The full fault equals
    # fast under known quiescence; the separate actual-source exhaustive check
    # verifies this relation over all 12 four-state source input predicates.
    four='''`timescale 1ns/1ps
    module clear_guard_four;
    function automatic logic digit(input integer n);case(n)0:digit=0;1:digit=1;2:digit=1'bx;3:digit=1'bz;endcase endfunction
    reg memory_clear_pending,target_match,fifo_read_valid,memory_quiescent,memory_channel_fault,full_fault,fast_fault;
    wire [3:0] fifo_consumed=0,memory_clear_target=target_match ? 0:1;
    wire memory_fault_now=(memory_quiescent===1'b1)?fast_fault:full_fault;
    wire transport_fault_i=fast_fault,native_protocol_fault_o=0,unused_submitted=0,native_accept_i=0,read_response_i=0;
    reg old_clear;
    '''+block+'''
    integer index;initial begin
    for(index=0;index<16384;index=index+1)begin
    memory_clear_pending=digit(index&3);target_match=digit((index>>2)&3);fifo_read_valid=digit((index>>4)&3);memory_quiescent=digit((index>>6)&3);memory_channel_fault=digit((index>>8)&3);full_fault=digit((index>>10)&3);fast_fault=digit((index>>12)&3);
    #0.001;old_clear=0;
    '''+oldguard+''' old_clear=1;end
    if(old_clear!==clear_initialize)$fatal(1,"CLEAR complete guard differs index=%0d old=%b new=%b",index,old_clear,clear_initialize);
    end
    $display("PASS exact CLEAR procedural guards four_state_combinations=16384");$finish;
    end endmodule
    ''';(out/'clear-guard-four.sv').write_text(four)
    deps=[root/'rtl/memory/workstation_sdp.sv',root/'rtl/music/music_async_fifo.sv',bridge];inputs=[source,baseline,Path(__file__),helper_src,helper,tb,variant,reference,*deps];before={str(p):sha(p) for p in inputs};result=dict(schema=1,passed=False,scope='complete maintained CLEAR completion guard cofactor against immutable actual W13 source',source_sha256=sha(source),baseline_W13_sha256=sha(baseline),variant_sha256=sha(variant),exact_inverse=True,all_sequential_NBA_target_RHS_order_identical=True,source_equations=eq,full_domain_guard_proof='UNSAT',whole_twin_inventory=inventory,directed_cases=cases+[name for name,_ in cases_more],input_sha256=before,cases={},source_implementation=True,synthesis=False,pnr=False,hardware_tested=False,timing_or_resource_gain_claimed=False,runner_sha256=sha(Path(__file__)))
    try:
     result['cases']['clear_guard_four']=h.simulate(out,'clear-guard-four',[out/'clear-guard-four.sv'],'clear_guard_four')
     for name,params in [('fifo8_async_memory',[('FIFO_BITS',8),('MEM_HALF',7)]),('fifo3_100mhz_memory',[('FIFO_BITS',3),('MEM_HALF',5)])]:result['cases'][name]=h.simulate(out,name,[out/'twin.sv',variant,reference,*deps],'tb_ble_raw_ddr_store',params,timeout=180)
     result['cases']['arbitrary_state']=h.simulate(out,'arbitrary-state',[out/'directed.sv',variant,reference,*deps],'directed',timeout=180)
     for name,anchor,replacement in [('drop_native_fault','unused_submitted || native_accept_i || read_response_i))','unused_submitted || read_response_i))'),('drop_transport_fault','!(transport_fault_i || native_protocol_fault_o ||','!(native_protocol_fault_o ||'),('allow_nonquiescent_clear',"            1'b0:begin end\n            1'b1:begin\n                if(memory_clear_pending", "            1'b0:begin clear_initialize=1;end\n            1'b1:begin\n                if(memory_clear_pending"),('unknown_fault_procedural_else','!fifo_read_valid && !memory_channel_fault &&\n                   !(transport_fault_i || native_protocol_fault_o ||\n                     unused_submitted || native_accept_i || read_response_i))\n                    clear_initialize=1;', '!fifo_read_valid && !memory_channel_fault)begin\n                    if(transport_fault_i || native_protocol_fault_o || unused_submitted || native_accept_i || read_response_i)begin end\n                    else clear_initialize=1;\n                end')]:
      assert new.count(anchor)==1,(name,new.count(anchor));path=out/(name+'.sv');path.write_text(new.replace(anchor,replacement));result['cases'][name]=h.simulate(out,name,[out/'directed.sv',path,reference,*deps],'directed',expected='complete raw twin')
     result['cases']['actual_fault_four_state']=h.simulate(out,'actual-fault-four-state',[out/'actual-fault-four-state.sv'],'four_state',timeout=300)
     assert before=={str(p):sha(p) for p in inputs};result['passed']=True
    finally:(out/'verification.json').write_text(json.dumps(result,indent=2)+'\n')
    print('PASS complete maintained CLEAR completion cofactor',sha(variant),flush=True)

if __name__ == '__main__':
    main()
