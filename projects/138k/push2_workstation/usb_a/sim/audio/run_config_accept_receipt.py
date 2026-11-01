#!/usr/bin/env python3
"""Verify real M/W config receipts, same-edge withdrawal and runtime ACKs."""
from pathlib import Path
import argparse,ast,collections,hashlib,json,re,subprocess
from run_runtime_controlled import runtime_sources
import config_accept_receipt_sources as receipt

ROOT=Path(__file__).resolve().parents[2]
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()

def source_list(project,tb):
    sources=runtime_sources(project,tb)
    maintained={p.name for p in sources if p.is_relative_to(ROOT)}
    return [p for p in sources if not(p.parent==project/'rtl/audio/delay_ddr'and p.name in maintained)]

def four_state_sources(sources,out):
    # Icarus requires a declaration before its first procedural use. Reuse
    # the established, token-preserving same-scope declaration adaptation.
    original=ROOT/'sim/audio/run_config_ready_four_state.py'
    tree=ast.parse(original.read_text())
    function=next(n for n in tree.body if isinstance(n,ast.FunctionDef)and n.name=='adapt')
    ns={'re':re,'hashlib':hashlib,'adaptation_records':[]}
    exec(compile(ast.Module(body=[function],type_ignores=[]),str(original),'exec'),ns)
    adapted=[]
    for p in sources:
        if p.name=='workstation_audio_render_service.sv':
            text=p.read_text();blocks=[]
            for pattern in [r'    reg request_epoch_match;\n',r'    wire accepted=[^;]+;\n',r'    wire cancelled=[^;]+;\n']:
                found=re.findall(pattern,text,re.S);assert len(found)==1,(p.name,pattern)
                blocks.extend(found);text=text.replace(found[0],'',1)
            anchor='    wire core_history_ready,core_history_done;\n'
            assert text.count(anchor)==1;text=text.replace(anchor,anchor+''.join(blocks))
            assert collections.Counter(re.findall(r'\S+',text))==collections.Counter(re.findall(r'\S+',p.read_text()))
            q=out/('compatibility-'+p.name);q.write_text(text);adapted.append(q)
            ns['adaptation_records'].append(dict(name=p.name,before_sha256=sha(p),after_sha256=sha(q),only_same_scope_declaration_reorder=True))
        elif p.name in ['gw138k_event_workstation.sv','workstation_runtime_oscillator_engine.sv','workstation_runtime_stereo_effects.sv','workstation_runtime_delay_effect_ddr.sv']:
            q=out/('compatibility-'+p.name);q.write_text(ns['adapt'](p.read_text(),p.name));adapted.append(q)
        else:adapted.append(p)
    return adapted,dict(adapter_input=str(original),adapter_sha256=sha(original),same_scope_declaration_reorders=ns['adaptation_records'])

def execute(cmd,project,out,name,positive,marker):
    with(out/(name+'.log')).open('w')as log:
        run=subprocess.run(cmd,cwd=project,stdout=log,stderr=subprocess.STDOUT,timeout=300)
    text=(out/(name+'.log')).read_text()
    assert (run.returncode==0 if positive else run.returncode!=0)and marker in text,text[-4000:]
    return dict(argv=cmd,returncode=run.returncode,expected_negative=not positive,log_sha256=sha(out/(name+'.log')))

def four_state(project,out,negative=False):
    out.mkdir()
    tb=ROOT/'sim/audio/tb_config_accept_receipt_four_state.sv'
    sources,adaptations=four_state_sources(source_list(project,tb),out)
    if negative:
        original=next(p for p in sources if p.name=='compatibility-workstation_audio_render_service.sv')
        text=original.read_text();anchor='assign config_accepted_o=external_config && core_rate_accepted;'
        assert text.count(anchor)==1;text=text.replace(anchor,'assign config_accepted_o=config_ready_o;')
        mutant=out/'wrong-ready-is-receipt.sv';mutant.write_text(text);sources=[mutant if p==original else p for p in sources]
    result=dict(adaptations=adaptations,input_sha256={str(p):sha(p)for p in sources})
    result['compile']=execute(['iverilog','-g2012','-s','tb','-o',str(out/'test.vvp'),'-I'+str(ROOT),'-I'+str(project),*map(str,sources)],project,out,'compile',True,'')
    result['run']=execute(['vvp',str(out/'test.vvp')],project,out,'run',not negative,'RECEIPT mismatch'if negative else'PASS COMPLETE_RECEIPT_ALL_FOUR_STATE')
    return result

def runtime(project,out,negative=False):
    out.mkdir();tb=ROOT/'sim/audio/tb_config_accept_receipt_runtime.sv';sources=source_list(project,tb)
    if negative:
        original=ROOT/'rtl/workstation/workstation_runtime_audio.sv';text=original.read_text()
        anchor='CFG_ACCEPT:if(config_accepted)begin';assert text.count(anchor)==1
        mutant=out/'workstation_runtime_audio.sv';mutant.write_text(text.replace(anchor,'CFG_ACCEPT:if(config_ready)begin'))
        sources=[mutant if p==original else p for p in sources]
    result=dict(input_sha256={str(p):sha(p)for p in sources})
    result['compile']=execute(['verilator','--binary','--timing','-j','4','-Wno-fatal','--top-module','tb','--Mdir',str(out/'obj'),'-I'+str(ROOT),'-I'+str(project),*map(str,sources)],project,out,'compile',True,'')
    assert '%Warning-UNOPTFLAT'not in(out/'compile.log').read_text(),'combinational admission loop'
    result['run']=execute([str(out/'obj/Vtb')],project,out,'run',not negative,'PHANTOM_ACK'if negative else'PASS REAL_RUNTIME_RECEIPT_M_W')
    return result

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--project',type=Path,required=True);ap.add_argument('--output',type=Path,required=True)
    a=ap.parse_args();project=a.project.resolve();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    inputs=list(dict.fromkeys(receipt.contract_inputs()+[Path(__file__).resolve(),ROOT/'sim/audio/run_runtime_controlled.py',ROOT/'sim/audio/run_config_ready_four_state.py',ROOT/'sim/audio/tb_config_accept_receipt_four_state.sv',ROOT/'sim/audio/tb_config_accept_receipt_runtime.sv',ROOT/'rtl/audio/runtime_spatial_room_preset.svh']+source_list(project,ROOT/'sim/audio/tb_config_accept_receipt_runtime.sv')))
    hashes={str(p):sha(p)for p in inputs}
    result=dict(schema=1,passed=False,stage='actual_M_W_configuration_acceptance_receipt',source_contract=receipt.source_contract(),input_sha256=hashes,cases={},hardware_tested=False,physical_timing_verified=False,resource_saving_claimed=False,
                scope='Complete actual M/W service four-state receipt, actual runtime FSM and broadcast, PCM/core-fault same-edge veto, request withdrawal, healthy actual commit and applied-to-IDLE; forced faults only at owned boundary operands, no timing/hardware claim')
    try:
        for name,job,negative in [('four-state',four_state,False),('wrong-ready-receipt',four_state,True),('runtime',runtime,False),('old-ready-ACK',runtime,True)]:
            result['cases'][name]=job(project,out/name,negative);print(name,'PASS',flush=True)
        for relative in receipt.HUNKS:
            text=(ROOT/relative).read_text();old,new=receipt.HUNKS[relative][-1]
            try:receipt.reference_view(relative,text.replace(new,new+'\n// unexpected source drift',1))
            except AssertionError:pass
            else:raise AssertionError('source drift was not rejected: '+relative)
        assert hashes=={str(p):sha(p)for p in inputs},'receipt regression input drift'
        result['all_inputs_unchanged']=True;result['passed']=True
    finally:(out/'verification.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(passed=True,report=str(out/'verification.json'),sha256=sha(out/'verification.json'))))

if __name__=='__main__':main()
