#!/usr/bin/env python3
"""Prove final global failure publication against the immutable consumed W14 store."""
from pathlib import Path
import argparse,hashlib,json,importlib.util,re,difflib
import z3

BASELINE_SHA256 = '39ae3b918a4674f849eb0663bb193e2890881f164063f22b473b5dbb61df290b'
MAINTAINED_SHA256 = 'b654b55a47e017aec5f3c386f26cb2aac34f311bdb564852cf047c24dc1c3809'
FAILURE_RHS = 'bridge_fault ? F_TRANSPORT :\n                    command_expired ? F_COMMAND_TIMEOUT : read_expired ? F_READ_TIMEOUT : F_PROTOCOL'
OLD_GLOBAL = '            if(memory_fault_now)begin\n                memory_channel_fault<=1;memory_fetch_cancel<=1;\n                if(!memory_channel_fault)memory_failure<=bridge_fault ? F_TRANSPORT :\n                    command_expired ? F_COMMAND_TIMEOUT : read_expired ? F_READ_TIMEOUT : F_PROTOCOL;\n            end\n'
NEW_GLOBAL = '            if(memory_fault_now)begin\n                memory_channel_fault<=1;memory_fetch_cancel<=1;\n            end\n            if(global_failure_write)memory_failure<=global_failure_value;\n'
GLOBAL_FAILURE_BLOCK = "    // A known bridge fault publishes the transport code directly. Keep the\n    // immediate fault, first-fault sticky guard and exact X/Z ternary semantics.\n    // This write retains its last priority after every protocol failure.\n    reg global_failure_write;\n    reg [3:0] global_failure_value;\n    always @* begin\n        global_failure_write=0;global_failure_value=F_PROTOCOL;\n        case(bridge_fault)\n            1'b1:begin\n                if(!memory_channel_fault)begin\n                    global_failure_write=1;global_failure_value=F_TRANSPORT;\n                end\n            end\n            1'b0:begin\n                if(command_expired || read_expired || response_bad)begin\n                    if(!memory_channel_fault)begin\n                        global_failure_write=1;\n                        global_failure_value=command_expired ? F_COMMAND_TIMEOUT :\n                            read_expired ? F_READ_TIMEOUT : F_PROTOCOL;\n                    end\n                end\n            end\n            default:begin\n                if(memory_fault_now)begin\n                    if(!memory_channel_fault)begin\n                        global_failure_write=1;\n                        global_failure_value=bridge_fault ? F_TRANSPORT :\n                            command_expired ? F_COMMAND_TIMEOUT : read_expired ? F_READ_TIMEOUT : F_PROTOCOL;\n                    end\n                end\n            end\n        endcase\n    end\n"

def restore_before_global_failure(text):
    """Invert only the reviewed final-write cofactor and reject every drift."""
    if hashlib.sha256(text.encode()).hexdigest() != MAINTAINED_SHA256:
        raise ValueError('maintained global failure source identity changed')
    if text.count(GLOBAL_FAILURE_BLOCK) != 1 or text.count(NEW_GLOBAL) != 1:
        raise ValueError('reviewed global failure block/write anchor changed')
    restored = text.replace(GLOBAL_FAILURE_BLOCK, '', 1).replace(NEW_GLOBAL, OLD_GLOBAL, 1)
    if hashlib.sha256(restored.encode()).hexdigest() != BASELINE_SHA256:
        raise ValueError('exact pre-global-failure source reconstruction changed')
    return restored


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    root=Path(__file__).resolve().parents[2]
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    maintained_source=root/'rtl/memory/workstation_ble_raw_ddr_store.sv'
    preload_proof = Path(__file__).with_name('prove_ble_raw_return_mailbox_preload.py')
    preload_fixture = (Path(__file__).with_name('fixtures') /
                       'workstation_ble_raw_ddr_store_before_return_preload.sv')
    preload_spec = importlib.util.spec_from_file_location('return_preload_inverse', preload_proof)
    preload = importlib.util.module_from_spec(preload_spec)
    preload_spec.loader.exec_module(preload)
    assert sha(preload_fixture) == preload.BASELINE_SHA256
    source=out/'normalized-before-return-preload.sv'
    source.write_text(preload.restore_before_return_preload(maintained_source.read_text()))
    fixture=Path(__file__).with_name('fixtures')/'workstation_ble_raw_ddr_store_before_global_failure_case.sv'
    assert sha(fixture)==BASELINE_SHA256
    old=fixture.read_text();new=source.read_text();assert restore_before_global_failure(new)==old
    baseline=out/'baseline.sv';baseline.write_bytes(fixture.read_bytes())
    helper_src=root/'sim/memory/prove_ble_raw_start_factor.py';helper=out/'proof-helper.py';helper.write_bytes(helper_src.read_bytes())
    s=importlib.util.spec_from_file_location('h',helper);h=importlib.util.module_from_spec(s);s.loader.exec_module(h)
    tb_source=root/'sim/memory/tb_ble_raw_ddr_store.sv';h.TB=out/'tb-source.sv';h.TB.write_bytes(tb_source.read_bytes())
    dep_sources=[root/x for x in ['rtl/memory/workstation_sdp.sv','rtl/music/music_async_fifo.sv','rtl/memory/workstation_recording_ddr_native_bridge.sv']]
    deps=[]
    for original in dep_sources:
        target=out/'dependencies'/original.relative_to(root);target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(original.read_bytes());deps.append(target)
    rhs=FAILURE_RHS;old_global=OLD_GLOBAL;new_global=NEW_GLOBAL;block=GLOBAL_FAILURE_BLOCK
    for name,mutant in [('body_drift',new.replace('    reg global_failure_write;','    reg global_failure_write_changed;',1)),('write_drift',new.replace('if(global_failure_write)memory_failure<=global_failure_value;','if(!global_failure_write)memory_failure<=global_failure_value;',1))]:
        try:restore_before_global_failure(mutant)
        except ValueError:pass
        else:raise AssertionError(('global failure source inverse drift accepted',name))
    # Only the last memory_failure RHS is redirected; all prior memory_failure
    # writes and the complete global NBA sequence for every other target are exact.
    def nbas(text):return re.findall(r'\b(\w+(?:\[[^]]+\])?)\s*<=\s*([^;]+);',text)
    a,b=nbas(old),nbas(new)
    assert len(a)==len(b) and a[:-1]==b[:-1] and a[-1][0]==b[-1][0]=='memory_failure'
    assert [r for r in a if r[0]!='memory_failure']==[r for r in b if r[0]!='memory_failure']
    assert [r for r in a if r[0]=='memory_failure'][:-1]==[r for r in b if r[0]=='memory_failure'][:-1]
    assert 'completion_generation<=' not in block
    variant=out/'variant.sv';variant.write_text(new)
    reference=out/'reference.sv';reference.write_text(old.replace('module workstation_ble_raw_ddr_store #(','module workstation_ble_raw_ddr_store_reference #(',1))
    (out/'proposed.patch').write_text(''.join(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile='a/rtl/memory/workstation_ble_raw_ddr_store.sv',tofile='b/rtl/memory/workstation_ble_raw_ddr_store.sv')))
    ports,states,nets=h.inventories(old);assert h.inventories(new)==(ports,sorted(states+['global_failure_write','global_failure_value']),nets)
    twin,inventory=h.twin_bench(old,ports,states,nets);(out/'twin.sv').write_text(twin)
    comb=['start_fault_now','start_initialize','clear_initialize'];seq=[n for n in states if n not in comb]
    directed,cases=h.directed_bench(ports,seq,nets+comb)
    input_names={n for n,row in ports.items() if row[0]=='input'}
    # Each source state is unrestricted. These cases target fault codes, sticky
    # behavior and ternary merges; the original complete test and random twin remain.
    base={'command_req_sync':'0','command_req_meta':'0','command_req':'0','memory_failure':"4'hc"}
    extra=[
     ('transport',{**base,'transport_fault_i':'1'},"if(dut.memory_failure!==7 || dut.memory_channel_fault!==1 || dut.memory_fetch_cancel!==1)$fatal(1,\"immediate transport code\");"),
     ('transport_over_timeouts',{**base,'transport_fault_i':'1','published_valid':'1','command_wait':'2047','read_outstanding':'1','read_wait':'2047'},"if(dut.memory_failure!==7)$fatal(1,\"transport highest fault code priority\");"),
     ('command_over_read',{**base,'published_valid':'1','command_wait':'2047','read_outstanding':'1','read_wait':'2047'},"if(dut.memory_failure!==5)$fatal(1,\"command timeout priority\");"),
     ('read_timeout',{**base,'read_outstanding':'1','read_wait':'2047'},"if(dut.memory_failure!==6)$fatal(1,\"read timeout code\");"),
     ('response_protocol',{**base,'read_response_i':'1'},"if(dut.memory_failure!==8)$fatal(1,\"response protocol code\");"),
     ('sticky_transport',{**base,'transport_fault_i':'1','memory_channel_fault':'1'},"if(dut.memory_failure!==12)$fatal(1,\"sticky first fault retains old code\");"),
     ('X_sticky',{**base,'transport_fault_i':'1','memory_channel_fault':"1'bx"},"if(dut.memory_failure!==12)$fatal(1,\"unknown sticky guard does not publish\");"),
     ('Z_sticky',{**base,'transport_fault_i':'1','memory_channel_fault':"1'bz"},"if(dut.memory_failure!==12)$fatal(1,\"Z sticky guard does not publish\");"),
     ('X_bridge_command',{**base,'transport_fault_i':"1'bx",'published_valid':'1','command_wait':'2047'},"if(dut.memory_failure!==4'b01x1)$fatal(1,\"X bridge ternary transport/command merge\");"),
     ('Z_bridge_read',{**base,'transport_fault_i':"1'bz",'read_outstanding':'1','read_wait':'2047'},"if(dut.memory_failure!==4'b011x)$fatal(1,\"Z bridge ternary transport/read merge\");"),
     ('X_command_read',{**base,'published_valid':'1','command_wait':"32'hxxxxxxxx",'read_outstanding':'1','read_wait':'2047'},"if(dut.memory_failure!==4'b01xx)$fatal(1,\"X command/read ternary merge\");"),
     ('X_bridge_no_fault',{**base,'transport_fault_i':"1'bx"},"if(dut.memory_failure!==12)$fatal(1,\"unknown fault guard does not publish\");"),
     ('default_kind_protocol',{'command_kind':'3','memory_failure':"4'hc"},"if(dut.memory_failure!==8)$fatal(1,\"lower case default retained\");"),
     ('X_kind_protocol',{'command_kind':"2'bx1",'memory_failure':"4'hc"},"if(dut.memory_failure!==8)$fatal(1,\"lower X kind case default retained\");"),
     ('bad_clear_protocol',{'command_kind':'1','command_generation':'9','memory_failure':"4'hc"},"if(dut.memory_failure!==8)$fatal(1,\"lower CLEAR failure retained\");"),
     ('bad_start_protocol',{'command_kind':'0','memory_empty':'0','memory_failure':"4'hc"},"if(dut.memory_failure!==8)$fatal(1,\"lower START failure retained\");"),
     ('global_transport_rejects_command',{'command_kind':'3','transport_fault_i':'1','memory_failure':"4'hc"},"if(dut.memory_failure!==7)$fatal(1,\"global fault wins command default\");"),
    ]
    lines=[]
    for i,(name,values,check) in enumerate(extra,50):
     lines+=['set_base; twin_case='+str(i)+';']
     for n,v in values.items():lines.append(n+'='+v+';' if n in input_names else 'dut.'+n+'='+v+';reference.'+n+'='+v+';')
     lines+=['#0.1;compare_all;step;',check,'$display("PASS directed '+name+'");']
    anchor='// Every old register is independently randomized';assert directed.count(anchor)==1;directed=directed.replace(anchor,'\n'.join(lines)+'\n'+anchor).replace('directed_cases=18 random_four_state_edges=4096','directed_cases='+str(len(cases)+len(extra))+' random_four_state_edges=4096');(out/'directed.sv').write_text(directed)
    bridge=deps[2];eq={n:h.expression(bridge.read_text(),n,k) for n,k in [('native_ready_o','assign'),('protocol_fault_now','wire'),('transport_fault_o','assign')]}
    for n in ['native_commit','native_read_commit','command_expired','read_expired','response_bad','memory_fault_now','memory_quiescent','memory_command_start']:
     eq[n]=h.expression(old,n);assert eq[n]==h.expression(new,n)
    # Full-domain binary guard/code/nextQ including unrestricted preceding writes.
    bf,ce,rexp,rb,ch,rst=z3.Bools('bridge command_expired read_expired response_bad channel reset');before=z3.BitVec('prior_failure_after_all_lower_writes',4)
    fault=z3.Or(bf,ce,rexp,rb);oldenable=z3.And(fault,z3.Not(ch));oldvalue=z3.If(bf,7,z3.If(ce,5,z3.If(rexp,6,8)))
    newenable=z3.If(bf,z3.Not(ch),z3.And(z3.Or(ce,rexp,rb),z3.Not(ch)));newvalue=z3.If(bf,7,z3.If(ce,5,z3.If(rexp,6,8)))
    oldq=z3.If(rst,z3.BitVecVal(0,4),z3.If(oldenable,z3.Int2BV(oldvalue,4),before));newq=z3.If(rst,z3.BitVecVal(0,4),z3.If(newenable,z3.Int2BV(newvalue,4),before))
    solver=z3.Solver();solver.add(z3.Or(oldenable!=newenable,z3.And(oldenable,oldvalue!=newvalue),oldq!=newq));assert solver.check()==z3.unsat
    # Exhaust the actual extracted helper and original statement over every
    # four-state aggregate predicate; each code bit before the last write is free.
    constants=re.search(r'    localparam \[3:0\] F_OVERFLOW=.*?;',old,re.S)[0]
    four='''`timescale 1ns/1ps
    module failure_guards;
    function automatic logic digit(input integer n);case(n)0:digit=0;1:digit=1;2:digit=1'bx;3:digit=1'bz;endcase endfunction
    reg bridge_fault,command_expired,read_expired,response_bad,memory_channel_fault;
    wire memory_fault_now='''+eq['memory_fault_now']+''';
    '''+constants+'\n'+block+'''
    reg oldenable;reg [3:0] oldvalue,before_value,oldq,newq;
    integer i,j,bit_index;integer guard_vectors=0,nextq_vectors=0;
    initial begin
    for(i=0;i<1024;i=i+1)begin
    {bridge_fault,command_expired,read_expired,response_bad,memory_channel_fault}={digit(i&3),digit((i>>2)&3),digit((i>>4)&3),digit((i>>6)&3),digit((i>>8)&3)};
    #0.001;oldenable=0;oldvalue=F_PROTOCOL;
    if(memory_fault_now)begin if(!memory_channel_fault)begin oldenable=1;oldvalue='''+rhs+''';end end
    if(oldenable!==global_failure_write || (oldenable && oldvalue!==global_failure_value))$fatal(1,"global failure four-state guard/value vector=%d",i);
    guard_vectors=guard_vectors+1;
    for(j=0;j<256;j=j+1)begin
    for(bit_index=0;bit_index<4;bit_index=bit_index+1)before_value[bit_index]=digit((j>>(2*bit_index))&3);
    oldq=before_value;newq=before_value;
    if(oldenable)oldq=oldvalue;
    if(global_failure_write)newq=global_failure_value;
    if(oldq!==newq)$fatal(1,"global failure arbitrary prior nextQ vector=%d prior=%d",i,j);
    nextq_vectors=nextq_vectors+1;
    end
    end
    $display("PASS global failure four-state guard_vectors=%0d arbitrary_prior_nextQ=%0d no_reachability_filter=1",guard_vectors,nextq_vectors);$finish;
    end endmodule
    ''';(out/'guard-four-state.sv').write_text(four)
    inputs=[maintained_source,preload_proof,preload_fixture,source,fixture,helper_src,tb_source,*dep_sources,baseline,helper,h.TB,*deps,variant,reference,Path(__file__).resolve()];beforehash={str(p):sha(p) for p in inputs}
    result=dict(schema=1,passed=False,cache_only=False,source_implementation=True,maintained_source_sha256=sha(maintained_source),exact_reviewed_return_preload_inverse=True,baseline_sha256=sha(baseline),variant_sha256=sha(variant),patch_sha256=sha(out/'proposed.patch'),exact_whole_source_inverse=True,all_prior_memory_failure_writes_and_RHS_byte_identical=True,all_other_targets_global_NBA_order_identical=True,only_last_global_memory_failure_NBA_redirected=True,immediate_bridge_fault_retained=True,completion_generation_unchanged=True,full_binary_guard_code_arbitrary_4bit_nextQ='UNSAT',source_equations=eq,whole_twin_inventory=inventory,directed_cases=cases+[n for n,_,_ in extra],input_sha256=beforehash,cases={},synthesis=False,pnr=False,hardware_tested=False,timing_or_resource_gain_claimed=False,scope_limit='Only final global memory_failure write is redirected to exact combinational cofactor. Lower writes, channel/cancel and completion retain original source priority. No physical gain claimed and full sequential formal not proven.')
    try:
     result['cases']['guard_four_state']=h.simulate(out,'guard-four-state',[out/'guard-four-state.sv'],'failure_guards')
     for name,params in [('fifo8_async_memory',[('FIFO_BITS',8),('MEM_HALF',7)]),('fifo3_100mhz_memory',[('FIFO_BITS',3),('MEM_HALF',5)])]:result['cases'][name]=h.simulate(out,name,[out/'twin.sv',variant,reference,*deps],'tb_ble_raw_ddr_store',params,timeout=180)
     result['cases']['arbitrary_state']=h.simulate(out,'arbitrary-state',[out/'directed.sv',variant,reference,*deps],'directed',timeout=180)
     mutants = [
         ('wrong_transport_code',
          'global_failure_write=1;global_failure_value=F_TRANSPORT;',
          'global_failure_write=1;global_failure_value=F_PROTOCOL;'),
         ('drop_sticky_guard',
          "            1'b1:begin\n                if(!memory_channel_fault)begin",
          "            1'b1:begin\n                if(1'b1)begin"),
         ('X_sticky_writes',
          "            1'b1:begin\n                if(!memory_channel_fault)begin",
          "            1'b1:begin\n                if(memory_channel_fault!==1'b1)begin"),
         ('drop_unknown_fallback',
          '            default:begin\n                if(memory_fault_now)begin',
          "            default:begin\n                if(1'b0)begin"),
         ('wrong_timeout_priority',
          'global_failure_value=command_expired ? F_COMMAND_TIMEOUT :\n                            read_expired ? F_READ_TIMEOUT : F_PROTOCOL;',
          'global_failure_value=read_expired ? F_READ_TIMEOUT :\n                            command_expired ? F_COMMAND_TIMEOUT : F_PROTOCOL;'),
         ('wrong_unknown_merge',
          'global_failure_value=bridge_fault ? F_TRANSPORT :\n                            command_expired ? F_COMMAND_TIMEOUT : read_expired ? F_READ_TIMEOUT : F_PROTOCOL;',
          'global_failure_value=command_expired ? F_COMMAND_TIMEOUT :\n                            read_expired ? F_READ_TIMEOUT : F_PROTOCOL;'),
     ]
     for name,a,b in mutants:
      assert new.count(a)==1,(name,new.count(a));m=out/(name+'.sv');m.write_text(new.replace(a,b,1));result['cases'][name]=h.simulate(out,name,[out/'directed.sv',m,reference,*deps],'directed',expected='complete raw twin')
     assert beforehash=={str(p):sha(p) for p in inputs};result['passed']=True
    finally:(out/'verification.json').write_text(json.dumps(result,indent=2)+'\n')
    print('PASS maintained global memory_failure cofactor',sha(variant),flush=True)


if __name__ == '__main__':
    main()
