#!/usr/bin/env python3
"""Source-bound proof of the private request-service event configuration fence."""
from pathlib import Path
import argparse, hashlib, json, re, subprocess, sys
import z3

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(Path(__file__).resolve().parent))
from prove_effect_slot_admission import BooleanSV, equation, one

SERVICE_NAMES=('external_free','external_config','external_history','active_automatic_config',
               'accepted','automatic_config','core_config','event_config_request','sample_ce_o')
SERVICE_INPUTS=('active response_sent cancelled held_rate core_rate core_rate_busy external_busy core_fault '
                'config_valid_i history_clear_i render_request_i render_ready_o render_44k1_i').split()
EVENT_INPUTS=('mode_pending mode_ready pending usb_lifecycle native_clear load_busy mix_busy vec_busy '
              'TIMING_OPTIMIZED').split()

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def compact(v):return re.sub(r'\s+','',v)
def parse(v,env):return BooleanSV(v,env).result()

def source_contract(service,event):
    instance=one(service,r'gw138k_event_workstation #\(.*?\) workstation\((.*?)\);')
    for port,signal in [('sample_ce_i','sample_ce_o'),('rate_commit_i','core_config'),
                        ('event_rate_commit_i','event_config_request'),('history_clear_i','external_history')]:
        assert one(instance,r'\.'+port+r'\((.*?)\)')==signal,'private port binding drift: '+port
    assert '.EVENT_CONFIG_COFACTOR_ENABLE(RUNTIME_EFFECTS_ENABLE)' in service,'native-only enable binding drift'
    assert 'parameter bit EVENT_CONFIG_COFACTOR_ENABLE=0' in event,'legacy default changed'
    assert ('if(EVENT_CONFIG_COFACTOR_ENABLE && (!RUNTIME_EFFECTS_ENABLE || !REQUEST_DRIVEN_RENDER))' in event
            and 'event configuration cofactor requires native request-driven effects' in event),'private interface misuse guard changed'
    expr={n:equation(service,n) for n in SERVICE_NAMES}
    # Reject reintroducing the eliminated physical interface dependency even
    # when its binary function would remain equivalent.
    def dependencies(name,seen=None):
        seen=set() if seen is None else seen
        if name in seen:return seen
        seen.add(name)
        if name in expr:
            for token in re.findall(r'\b[A-Za-z_]\w*\b',expr[name]):dependencies(token,seen)
        return seen
    assert not {'accepted','render_request_i','render_ready_o','sample_ce_o'} & dependencies('event_config_request'),'private event request regained accepted-sample dependency'
    cone=one(event,r'generate if\(EVENT_CONFIG_COFACTOR_ENABLE\)begin: sample_event_config_fence\s*(.*?)\s*end else begin: full_event_config_fence')
    known=one(cone,r"1'b0,1'b1:\s*event_config_block=(.*?);")
    assert compact(one(cone,r'default:\s*event_config_block=(.*?);'))=='runtime_config_block','unknown-sample fallback changed'
    assert compact(one(event,r'begin: full_event_config_fence\s*assign event_config_block=(.*?);'))=='runtime_config_block','disabled legacy fence changed'
    # The new signal is private to two event consumers. No real audio/config
    # admission, transaction state, history or readiness is allowed to use it.
    consumers=[]
    for line in event.splitlines():
        if 'event_config_block' in line and not re.search(r'(logic event_config_block|event_config_block\s*=)',line):
            match=re.match(r'\s*assign\s+(\w+)',line)
            consumers.append(match.group(1) if match else 'non_event_assignment_continuation')
    assert consumers==['mode_valid','dispatch'],'event fence escaped private consumers'
    return expr,known,cone

def bound_environment(service,event):
    expr,known,cone=source_contract(service,event)
    env={'RUNTIME_EFFECTS_ENABLE':z3.BoolVal(True),'allocated':z3.BitVec('allocated',32)}
    for n in SERVICE_NAMES:env[n]=parse(expr[n],env)
    env.update(sample_ce_i=env['sample_ce_o'],rate_commit_i=env['core_config'],history_clear_i=env['external_history'],
               event_rate_commit_i=env['event_config_request'])
    native=one(event,r'begin: runtime_configuration\n(.*?)end else begin: fixed_configuration')
    env['runtime_config_busy']=parse(equation(native,'runtime_config_busy'),env)
    env['runtime_config_block']=parse(equation(native,'runtime_config_block'),env)
    env['event_config_block']=parse(known,env)
    return env,expr,known,cone,native

def binary_proof(service,event):
    env,expr,known,cone,native=bound_environment(service,event)
    rows=[]
    def prove(label,a,b,conditions=()):
        s=z3.Solver();s.add(*conditions,a!=b);result=str(s.check())
        assert result=='unsat',label+': '+str(s.model())
        rows.append(dict(property=label,result=result,reachability_assumptions=[]))
    prove('native sample_ce equals accepted',env['sample_ce_i'],env['accepted'])
    prove('private request equals complete request whenever sample_ce=0',env['event_rate_commit_i'],env['rate_commit_i'],[z3.Not(env['sample_ce_i'])])
    for name in ('mode_valid','dispatch'):
        new=parse(equation(event,name),env)
        old_env=dict(env);old_env['event_config_block']=env['runtime_config_block']
        old=parse(equation(event,name),old_env)
        prove(name+' all binary service inputs and event states',old,new)
        if name=='mode_valid':env['mode_valid']=new
    return rows

def compare_preserved(event,reference):
    # Reference is the exact event module actually consumed by M13. This is
    # deliberately broader than the new fence proof: real broadcast/state and
    # audio CE must remain byte-for-byte the same equations/procedural body.
    for name in ('core_ce','panic_accept','engine_clear','render_idle_o','parameter_commit'):
        assert equation(event,name)==equation(reference,name),'preserved '+name+' changed'
    pattern=r'begin: runtime_configuration\n(.*?)end else begin: fixed_configuration'
    assert one(event,pattern)==one(reference,pattern),'complete native configuration state/readiness/broadcast changed'
    assert one(event,r'begin: fixed_configuration\n(.*?)end endgenerate')==one(reference,r'begin: fixed_configuration\n(.*?)end endgenerate'),'legacy configuration changed'
    for port in ('config_valid_i','history_clear_i'):
        pattern=r'\.'+port+r'\((engine_rate_commit|history_clear_i && history_ready_o)\)'
        assert re.findall(pattern,event)==re.findall(pattern,reference),'effect real broadcast/history changed'
    return ['core_ce','panic_accept','engine_clear','render_idle_o','parameter_commit','complete native configuration state/readiness/broadcast','legacy configuration','effect configuration/history ports']

def four_state(service,event,out,label,expect_pass=True):
    # Compile the maintained source expressions and case body, not a Python
    # implementation of four-state algebra. Only the outer event terms are
    # unconstrained fixture inputs; source-bound service wires are preserved.
    expr={n:equation(service,n) for n in SERVICE_NAMES}
    cone=one(event,r'generate if\(EVENT_CONFIG_COFACTOR_ENABLE\)begin: sample_event_config_fence\s*(.*?)\s*end else begin: full_event_config_fence')
    native=one(event,r'begin: runtime_configuration\n(.*?)end else begin: fixed_configuration')
    inputs=SERVICE_INPUTS+EVENT_INPUTS+['busy']
    text='module tb;\nlogic '+','.join(n if n!='history_clear_i' else 'service_history_clear_i' for n in inputs)+';\n'
    text+='logic [31:0] allocated;wire RUNTIME_EFFECTS_ENABLE=1;\n'
    for name in SERVICE_NAMES:text+='wire '+name+'='+re.sub(r'\bhistory_clear_i\b','service_history_clear_i',expr[name])+';\n'
    text+='wire sample_ce_i=sample_ce_o,rate_commit_i=core_config,history_clear_i=external_history,event_rate_commit_i=event_config_request;\n'
    for name in ('runtime_config_busy','runtime_config_block'):text+='wire '+name+'='+equation(native,name)+';\n'
    text+='logic event_config_block;\n'+cone+'\n'
    for name in ('mode_valid','dispatch'):
        text+='wire '+name+'='+equation(event,name)+';\n'
        old=equation(event,name).replace('event_config_block','runtime_config_block')
        if name=='dispatch':old=re.sub(r'\bmode_valid\b','old_mode_valid',old)
        text+='wire old_'+name+'='+old+';\n'
    assignments=''.join((n if n!='history_clear_i' else 'service_history_clear_i')+'=random4();\n'for n in inputs)
    text+='''integer checks=0,k;reg [31:0] rng=32'h871fce39;
function automatic random4();begin rng=(rng>>1)^((rng&1)?32'h80200003:0);case(rng[1:0]) 0:random4=0;1:random4=1;2:random4=1'bx;3:random4=1'bz;endcase end endfunction
function automatic digit4(input integer value);begin case(value&3) 0:digit4=0;1:digit4=1;2:digit4=1'bx;3:digit4=1'bz;endcase end endfunction
task automatic check;begin #1;if(mode_valid!==old_mode_valid || dispatch!==old_dispatch ||
 ((sample_ce_i!==1'b0 && sample_ce_i!==1'b1) && event_config_block!==runtime_config_block))
 $fatal(1,"event cofactor four-state mismatch vector=%0d sample=%b rate=%b private=%b",checks,sample_ce_i,rate_commit_i,event_rate_commit_i);checks=checks+1;end endtask
initial begin
'''+assignments+'''
allocated=0;
// Exhaust all four values of seven service inputs; independently vary all
// remaining stored/event inputs, then exercise additional seeded vectors.
for(k=0;k<16384;k=k+1)begin
'''+assignments+'''
render_request_i=digit4(k);render_ready_o=digit4(k>>2);render_44k1_i=digit4(k>>4);core_rate=digit4(k>>6);
active=digit4(k>>8);held_rate=digit4(k>>10);busy=digit4(k>>12);allocated=rng;check();end
for(k=0;k<131072;k=k+1)begin
'''+assignments+'''
allocated=rng;check();end
$display("PASS event cofactor four-state vectors=%0d",checks);$finish;end
endmodule
'''
    source=out/(label+'.sv');source.write_text(text);executable=out/(label+'.vvp')
    compile=subprocess.run(['iverilog','-g2012','-s','tb','-o',str(executable),str(source)],capture_output=True,text=True,timeout=60)
    (out/(label+'-compile.log')).write_text(compile.stdout+compile.stderr)
    assert compile.returncode==0,'actual-source four-state fixture failed to compile: '+compile.stderr
    run=subprocess.run(['vvp',str(executable)],capture_output=True,text=True,timeout=60)
    (out/(label+'-run.log')).write_text(run.stdout+run.stderr)
    if expect_pass:assert run.returncode==0 and 'vectors=147456' in run.stdout,run.stdout+run.stderr
    else:assert run.returncode!=0 and 'event cofactor four-state mismatch' in run.stdout,run.stdout+run.stderr
    return dict(vectors=147456 if expect_pass else None,expected_rejection=not expect_pass,exit_code=run.returncode,fixture_sha256=sha(source),run_log_sha256=sha(out/(label+'-run.log')))

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--project',type=Path,required=True);ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--negative-modules',action='store_true',help='Also run real full-module wrong-port/history/legacy-enable negatives')
    args=ap.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    sp=ROOT/'rtl/audio/workstation_audio_render_service.sv';ep=ROOT/'rtl/audio/gw138k_event_workstation.sv';ref=args.project.resolve()/'src/ae350/gw138k_event_workstation.sv'
    assert sha(ref)=='5d02329a6b7f08ec30d79552a4814436b7c01611f4e4bed83c1514d154ef3fd1','M13 reference identity drift'
    inputs=[sp,ep,ref,Path(__file__).resolve(),Path(__file__).with_name('prove_effect_slot_admission.py')]
    before={str(p):sha(p) for p in inputs};service=sp.read_text();event=ep.read_text()
    record=dict(schema=1,passed=False,input_sha256=before,scope='unrestricted binary actual service/event equations plus finite actual-source Icarus four-state checks; full module negatives are separate',hardware_accepted=False,physical_timing_verified=False,resource_saving_claimed=False)
    try:
        record['preserved_from_exact_M13']=compare_preserved(event,ref.read_text());record['binary_proofs']=binary_proof(service,event)
        record['four_state']=four_state(service,event,out,'positive')
        mutants=[
            ('private_accepted_dependency',service.replace('wire event_config_request=external_config ||','wire event_config_request=core_config ||'),event,'private event request regained accepted-sample dependency'),
            ('disconnected_private_port',service.replace('.event_rate_commit_i(event_config_request)','.event_rate_commit_i(1\'b0)'),event,'private port binding drift'),
            ('real_core_uses_private_fence',service,event.replace('!native_clear && !runtime_config_block && !runtime_config_busy','!native_clear && !event_config_block && !runtime_config_busy'),'event fence escaped private consumers'),
            ('history_veto_dropped',service,event.replace('(event_rate_commit_i || history_clear_i)','(event_rate_commit_i || 0)'),'binary'),
            ('existing_active_config_omitted',service.replace('(RUNTIME_EFFECTS_ENABLE && active_automatic_config);','(RUNTIME_EFFECTS_ENABLE && 0);'),event,'binary'),
            ('unknown_sample_fallback_dropped',service,event.replace('default: event_config_block=runtime_config_block;','default: event_config_block=!runtime_config_busy && (event_rate_commit_i || history_clear_i);'),'unknown-sample fallback changed'),
            ('forced_legacy_enable',service.replace('.EVENT_CONFIG_COFACTOR_ENABLE(RUNTIME_EFFECTS_ENABLE)','.EVENT_CONFIG_COFACTOR_ENABLE(1)'),event,'native-only enable binding drift')]
        rows=[]
        for name,ms,me,diagnostic in mutants:
            assert ms!=service or me!=event,'mutant anchor missing: '+name
            try:binary_proof(ms,me)
            except (AssertionError,ValueError) as error:
                message=str(error);assert diagnostic=='binary' or diagnostic in message,(name,message)
            else:raise AssertionError('misuse control escaped: '+name)
            row=dict(misuse=name,source_bound_oracle_rejected=True,diagnostic=message)
            if name in ('history_veto_dropped','existing_active_config_omitted','unknown_sample_fallback_dropped'):
                row['actual_source_four_state']=four_state(ms,me,out,name,expect_pass=False)
            if args.negative_modules and name in ('disconnected_private_port','history_veto_dropped','forced_legacy_enable'):
                variant=out/(name+'-sources');variant.mkdir();(variant/sp.name).write_text(ms);(variant/ep.name).write_text(me)
                result=out/(name+'-module');cmd=[sys.executable,'-B',str(Path(__file__).with_name('run_event_config_contract.py')),'--project',str(args.project.resolve()),'--output',str(result),'--variant',str(variant)]
                run=subprocess.run(cmd,capture_output=True,text=True,timeout=600);(out/(name+'-module-driver.log')).write_text(run.stdout+run.stderr)
                assert run.returncode!=0 and (result/'run.log').is_file(),'negative did not reach actual module runtime: '+name
                log=(result/'run.log').read_text();expected='event configuration cofactor requires native request-driven effects' if name=='forced_legacy_enable' else 'M13/current'
                assert expected in log,(name,log)
                row['actual_module_runtime_rejected']=dict(exit_code=run.returncode,diagnostic=expected,verification=str(result/'verification.json'),run_log_sha256=sha(result/'run.log'))
            rows.append(row)
        record['seven_misuse_controls']=rows;assert before=={str(p):sha(p)for p in inputs},'proof source drift';record['all_inputs_unchanged']=True;record['passed']=True
        print(json.dumps(dict(passed=True,binary_proofs=len(record['binary_proofs']),four_state_vectors=record['four_state']['vectors'],misuse_controls=len(rows)),indent=2))
    finally:
        record['evidence_sha256']={str(p.relative_to(out)):sha(p) for p in out.rglob('*')if p.is_file()and p.suffix in ('.json','.log','.sv')}
        (out/'verification.json').write_text(json.dumps(record,indent=2)+'\n')

if __name__=='__main__':main()
