#!/usr/bin/env python3
"""Prove the public configuration-ready cofactor against a fixed whole source.

This verifier records an approved source hunk; it never generates production RTL.
Complete sequential service and four-state module tests use separate runners.
"""
from pathlib import Path
import argparse,hashlib,json,re
import z3
from prove_effect_slot_admission import one,equation,parse
ROOT=Path(__file__).resolve().parents[2]
EVENT=ROOT/'rtl/audio/gw138k_event_workstation.sv'
REFERENCE=Path(__file__).with_name('fixtures')/'gw138k_event_workstation_before_config_ready_cofactor.sv'
SERVICE=ROOT/'rtl/audio/workstation_audio_render_service.sv'
REFERENCE_SHA256='5569269a1d5ef02f2b1702f928d282fbab7455fba9af6ac229a97cbf8dc77bc9'
SERVICE_SHA256='9c80e68049ec1a08b9d176bd1d7dcb22723e3058c7015166a051c45dcd9d2bd0'
CONFIG_READY_REFERENCES=((REFERENCE,'gw138k_event_workstation',REFERENCE_SHA256),
                         (SERVICE,'workstation_audio_render_service',SERVICE_SHA256))
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
OLD_BLOCK='    assign rate_ready_o=rst_ni && !busy && !runtime_fault && pipeline_quiet &&\n        !panic_accept && !core_event_valid && !core_expression_valid && !mode_valid && fx_config_ready;'
NATIVE_BLOCK="    logic public_rate_ready;\n    assign rate_ready_o=public_rate_ready;\n    // A held event-fenced rate request excludes dispatch/mode admission.\n    // Keep the original ready expression for every other/unknown control.\n    always_comb begin\n      case ({rate_commit_i,busy,event_rate_commit_i})\n        3'b101: public_rate_ready=rst_ni && !runtime_fault && pipeline_quiet &&\n            !usb_lifecycle && fx_config_ready;\n        default: public_rate_ready=rst_ni && !busy && !runtime_fault && pipeline_quiet &&\n            !panic_accept && !core_event_valid && !core_expression_valid && !mode_valid && fx_config_ready;\n      endcase\n    end"

def source_contract(event=None):
    event=EVENT.read_text() if event is None else event
    assert sha(REFERENCE)==REFERENCE_SHA256,'pre-config-ready fixture drift'
    assert sha(SERVICE)==SERVICE_SHA256,'unchanged render-service reference drift'
    assert event.count(NATIVE_BLOCK)==1,'public config-ready exact block drift'
    base=REFERENCE.read_text()
    assert event.replace(NATIVE_BLOCK,OLD_BLOCK)==base,'public config-ready edits escape exact original source'
    assert re.findall(r'\b(\w+(?:\[[^]]+\])?)\s*<=\s*([^;]+);',event)==re.findall(r'\b(\w+(?:\[[^]]+\])?)\s*<=\s*([^;]+);',base),'sequential assignment order/RHS drift'
    return {'reference_sha256':REFERENCE_SHA256,'maintained_source_sha256':hashlib.sha256(event.encode()).hexdigest(),
            'exact_whole_source_inverse':True,'all_NBA_targets_rhs_and_order_unchanged':True,
            'service_reference_sha256':SERVICE_SHA256}

def reference_view(event):
    source_contract(event)
    return REFERENCE.read_text()

def binary_proof():
    source_contract();text=REFERENCE.read_text();native=one(text,r'begin: runtime_configuration\n(.*?)end else begin: fixed_configuration')
    control=one(text,r'always_comb begin\s*(core_event_valid=0;.*?)\n  end\n  wire decoder_valid')
    assert [re.sub(r'\s+','',s)for s in re.findall(r'\bcore_event_valid\s*=\s*(.*?);',control)]==['0','dispatch&&deferred_current','dispatch&&!(kind==1&&full)']
    assert [re.sub(r'\s+','',s)for s in re.findall(r'\bcore_expression_valid\s*=\s*(.*?);',control)]==['0','dispatch&&core_expression_ready']
    proposal=one(NATIVE_BLOCK,r"3'b101: public_rate_ready=(.*?);")
    fallback=one(NATIVE_BLOCK,r'default: public_rate_ready=(.*?);')
    assert re.sub(r'\s+','',fallback)==re.sub(r'\s+','',equation(native,'rate_ready_o'))
    env={'allocated':z3.BitVec('allocated',32),'kind':z3.BitVec('kind',4),'a':z3.BitVec('a',7)}
    for n in ('runtime_config_busy','runtime_config_block','runtime_fault'):env[n]=parse(equation(native,n),env)
    # In two-state controls the actual private event-fence case always chooses
    # this same expression, for both sample values. Its X/Z fallback is tested
    # on complete real modules by run_config_ready_four_state.py.
    actual_fence=one(text,r'1\x27b0,1\x27b1: event_config_block=(.*?);')
    env['event_config_block']=parse(actual_fence,env)
    for n in ('mode_valid','dispatch','panic_accept'):env[n]=parse(equation(text,n),env)
    env['core_event_valid']=z3.And(env['dispatch'],z3.Bool('actual_event_qualification'))
    env['core_expression_valid']=parse('dispatch && core_expression_ready',env)
    old=parse(equation(native,'rate_ready_o'),env);simple=parse(proposal,env)
    guard=parse('rate_commit_i && !busy && event_rate_commit_i',env)
    solver=z3.Solver();solver.add(old!=z3.If(guard,simple,old));assert solver.check()==z3.unsat
    result={'equivalence':'unsat','reachability_assumptions':[],'guard':'rate_commit_i && !busy && event_rate_commit_i',
            'arbitrary_event_qualification':True,'fallback_exact':True,'negative_controls':[]}
    for name,g,c in [('no_event_fence',parse('rate_commit_i && !busy',env),simple),
                     ('idle_ignores_event',parse('!busy',env),simple),
                     ('no_lifecycle_veto',guard,parse(proposal.replace('!usb_lifecycle','1'),env)),
                     ('no_fault_veto',guard,parse(proposal.replace('!runtime_fault','1'),env)),
                     ('no_quiet_veto',guard,parse(proposal.replace('pipeline_quiet','1'),env))]:
        solver=z3.Solver();solver.add(old!=z3.If(g,c,old));assert solver.check()==z3.sat,name
        result['negative_controls'].append({'name':name,'different_ready':'sat','counterexample':str(solver.model())})
    return result

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',type=Path,required=True);args=ap.parse_args()
    out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    inputs=[EVENT,REFERENCE,SERVICE,Path(__file__).resolve(),Path(__file__).with_name('prove_effect_slot_admission.py')]
    before={str(p):sha(p)for p in inputs};contract=source_contract();negatives=[];actual=EVENT.read_text()
    for name,mutant in [('missing_event_fence',actual.replace(NATIVE_BLOCK,NATIVE_BLOCK.replace('case ({rate_commit_i,busy,event_rate_commit_i})', 'case ({rate_commit_i,busy,event_rate_commit_i || 1\x27b1})'))),
                        ('outside_ready_commit',actual.replace('wire parameter_commit=event_valid','wire parameter_commit=1\x27b0 && event_valid',1))]:
        assert mutant!=actual
        try:source_contract(mutant)
        except AssertionError:negatives.append({'name':name,'rejected':True})
        else:raise AssertionError('source drift not rejected: '+name)
    result={'schema':1,'passed':True,'source_contract':contract,'binary':binary_proof(),'source_drift_negatives':negatives,
            'input_sha256':before,'scope':'exact whole-source inverse and unrestricted binary proof; full-module sequential/four-state tests separate',
            'hardware_accepted':False,'physical_timing_verified':False,'resource_saving_claimed':False}
    assert before=={str(p):sha(p)for p in inputs},'input drift';(out/'verification.json').write_text(json.dumps(result,indent=2)+'\n')
    print('PASS exact config-ready source inverse, binary proof and five counterexamples')
if __name__=='__main__':main()
