#!/usr/bin/env python3
"""Prove same-cycle native sample admission against its immutable prior source.

The recorded block below verifies an approved maintained implementation; it
never generates production RTL. Full-module temporal miters are separate
run_runtime_render_service.py/run_event_config_contract.py modes.
"""
from pathlib import Path
import argparse, hashlib, json, re, subprocess
import z3
from prove_effect_slot_admission import BooleanSV, equation, one
import config_accept_receipt_sources as receipt

ROOT=Path(__file__).resolve().parents[2]
EVENT=ROOT/'rtl/audio/gw138k_event_workstation.sv'
REFERENCE=Path(__file__).with_name('fixtures')/'gw138k_event_workstation_before_sample_admission.sv'
OSCILLATOR=ROOT/'rtl/audio/workstation_runtime_oscillator_engine.sv'
ENGINES=ROOT/'rtl/audio/workstation_runtime_render_engines.sv'
SERVICE=ROOT/'rtl/audio/workstation_audio_render_service.sv'
REFERENCE_SHA256='fad0203c4322b54271ef6f413a7523478cfa5101609f5b2f72e280ae3894bf09'
SERVICE_SHA256='9c80e68049ec1a08b9d176bd1d7dcb22723e3058c7015166a051c45dcd9d2bd0'
# Complete pre-change source fixture; no locked/prepared project dependency.
SAMPLE_ADMISSION_REFERENCES=((REFERENCE,'gw138k_event_workstation',REFERENCE_SHA256),
                             (SERVICE,'workstation_audio_render_service',SERVICE_SHA256))
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
parse=lambda text,env:BooleanSV(text,env).result()
NATIVE_BLOCK="""  // Native request-driven rendering and dispatch reserve disjoint edges.
  // For known render-eligible controls, dispatch and mode_valid are zero;
  // runtime_quiescent already contains the oscillator's stored ready state.
  // Keep current event/config acceptance out of this same-cycle sample CE.
  // Unknown controls retain the complete original four-state expression.
  generate if(REQUEST_DRIVEN_RENDER && RUNTIME_RATE_ENABLE && RUNTIME_EFFECTS_ENABLE)begin: native_sample_admission
    always_comb begin
      case({pending,sample_ce_i,runtime_config_busy})
        3'b100,3'b010,3'b110: core_ce=vec_ready && fx_sample_slot_ready &&
              !synth_joined && !vec_joined && !usb_lifecycle && !native_clear &&
              !runtime_config_block && !runtime_fault && runtime_quiescent;
        3'b000,3'b001,3'b011,3'b101,3'b111: core_ce=1'b0;
        default: core_ce=(pending || sample_ce_i) && core_sample_ready && vec_ready &&
      (RUNTIME_EFFECTS_ENABLE ? fx_sample_slot_ready : fx_ready) &&
      !synth_joined && !vec_joined && !panic_accept && !native_clear && !runtime_config_block && !runtime_config_busy && !runtime_fault &&
      (!REQUEST_DRIVEN_RENDER || (RUNTIME_RATE_ENABLE ? runtime_quiescent : legacy_cancel_tail==0));
      endcase
    end
  end else begin: original_sample_admission
    assign core_ce=(pending || sample_ce_i) && core_sample_ready && vec_ready &&
      (RUNTIME_EFFECTS_ENABLE ? fx_sample_slot_ready : fx_ready) &&
      !synth_joined && !vec_joined && !panic_accept && !native_clear && !runtime_config_block && !runtime_config_busy && !runtime_fault &&
      (!REQUEST_DRIVEN_RENDER || (RUNTIME_RATE_ENABLE ? runtime_quiescent : legacy_cancel_tail==0));
  end endgenerate"""

def source_contract(event=None):
    """Exact inverse to immutable source; preserve all other priorities/NBAs."""
    event=EVENT.read_text() if event is None else event
    maintained_digest=hashlib.sha256(event.encode()).hexdigest()
    config_ready_contract=None
    if 'logic public_rate_ready;' in event:
        import prove_config_ready_cofactor as readiness
        config_ready_contract=readiness.source_contract(event)
        event=readiness.reference_view(event)
    assert sha(REFERENCE)==REFERENCE_SHA256,'pre-sample-admission fixture drift'
    assert hashlib.sha256(receipt.reference_view('rtl/audio/workstation_audio_render_service.sv').encode()).hexdigest()==SERVICE_SHA256,'render-service pre-receipt reference drift'
    base=REFERENCE.read_text();old=equation(base,'core_ce')
    assert event.count(NATIVE_BLOCK)==1,'native sample admission exact block drift'
    inverse=event.replace(NATIVE_BLOCK,'  assign core_ce='+old+';')
    assert inverse==base,'sample admission edits escape exact original source'
    assert re.findall(r'\b(\w+(?:\[[^]]+\])?)\s*<=\s*([^;]+);',event)==re.findall(r'\b(\w+(?:\[[^]]+\])?)\s*<=\s*([^;]+);',base),'sequential assignment order/RHS drift'
    return {'reference_sha256':REFERENCE_SHA256,'maintained_source_sha256':maintained_digest,
            'exact_whole_source_inverse':True,'all_NBA_targets_rhs_and_order_unchanged':True,
            'service_reference_sha256':SERVICE_SHA256,
            'public_config_ready_inverse':config_ready_contract}

def reference_view(event):
    """Verified prior view for older cofactor proofs; never a build input."""
    source_contract(event)
    return REFERENCE.read_text()

def contract_inputs():
    """Inputs consumed by the layered exact inverse, including newer hunks."""
    inputs=[Path(__file__).resolve(),REFERENCE]+receipt.contract_inputs()
    if 'logic public_rate_ready;' in EVENT.read_text():
        import prove_config_ready_cofactor as readiness
        inputs.extend([Path(readiness.__file__).resolve(),readiness.REFERENCE])
    return inputs


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',type=Path,required=True);args=ap.parse_args()
    P=args.output.resolve();P.mkdir(parents=True,exist_ok=False)
    tracked=[REFERENCE,EVENT,OSCILLATOR,ENGINES,SERVICE,Path(__file__).resolve(),ROOT/'sim/audio/prove_effect_slot_admission.py']
    tracked=list(dict.fromkeys(tracked+contract_inputs()))
    before={str(p):sha(p)for p in tracked};contract=source_contract();source_negatives=[]
    actual=EVENT.read_text()
    for label,mutant in [('native_fast_fault_veto',actual.replace(NATIVE_BLOCK,NATIVE_BLOCK.replace('!runtime_fault','1',1))),
                         ('outside_core_ce_parameter_commit',actual.replace('wire parameter_commit=event_valid','wire parameter_commit=1\'b0 && event_valid',1))]:
        assert mutant!=actual,label
        try:source_contract(mutant)
        except AssertionError as error:source_negatives.append({'mutation':label,'rejected':True,'diagnostic':str(error)})
        else:raise AssertionError('source drift control escaped: '+label)
    base=REFERENCE.read_text();event=EVENT.read_text();osc=OSCILLATOR.read_text().split('\nendmodule',1)[0];eng=ENGINES.read_text()
    old=equation(base,'core_ce');fast=one(event,r"3'b100,3'b010,3'b110: core_ce=(.*?);");fallback=one(event,r'default: core_ce=(.*?);\s*endcase\s*end\s*end else begin: original_sample_admission')
    assert fallback==old and equation(event,'core_ce')==old
    case=one(event,r'begin: native_sample_admission\s*(always_comb begin.*?endcase\s*end)\s*end else begin: original_sample_admission')
    assert "case({pending,sample_ce_i,runtime_config_busy})"in case and "3'b000,3'b001,3'b011,3'b101,3'b111: core_ce=1'b0;"in case
    assert 'generate if(REQUEST_DRIVEN_RENDER && RUNTIME_RATE_ENABLE && RUNTIME_EFFECTS_ENABLE)begin: native_sample_admission'in event
    control=one(base,r'(always_comb begin\s*core_event_valid=0;.*?)\n  end\n  wire decoder_valid')+'\n  end\n'
    assert [re.sub(r'\s+','',x)for x in re.findall(r'\bcore_event_valid\s*=\s*(.*?);',control)]==['0','dispatch&&deferred_current','dispatch&&!(kind==1&&full)']
    assert [re.sub(r'\s+','',x)for x in re.findall(r'\bcore_expression_valid\s*=\s*(.*?);',control)]==['0','dispatch&&core_expression_ready']
    assert '.event_valid_i(event_valid_i && !scope_enable_i)'in eng and '.mode_set_valid_i,'in eng
    assert '.synth_sample_ready_o(core_sample_ready)'in base and '.quiescent_o(runtime_quiescent)'in base
    assert '.PIPELINED_ENVELOPE(RUNTIME_RATE_ENABLE), .PIPELINED_RATE(RUNTIME_RATE_ENABLE)'in eng
    assert 'assign core_sample_ready=1;'in base and 'assign runtime_quiescent=!rendered;'in base
    q=equation(osc,'quiescent_o');sr=equation(osc,'sample_ready_o');eq=equation(eng,'quiescent_o')
    assert q.count('!(|sine_pending_valid)')==1
    rows=[]
    for synth in (True,False):
     env={'REQUEST_DRIVEN_RENDER':z3.BoolVal(True),'RUNTIME_RATE_ENABLE':z3.BoolVal(True),'RUNTIME_EFFECTS_ENABLE':z3.BoolVal(True),'TIMING_OPTIMIZED':z3.BoolVal(True),'PIPELINED_RATE':z3.BoolVal(True),'allocated':z3.BitVec('allocated',32),'kind':z3.BitVec('kind',4),'a':z3.BitVec('a',7),'legacy_cancel_tail':z3.BitVec('legacy_cancel_tail',6),'load_state':z3.BitVec('load_state',3),'LOAD_IDLE':z3.BitVecVal(0,3)}
     env['mix_busy_o']=z3.Bool('mix_busy');env['load_busy']=env['load_state']!=0;env['mix_busy']=env['mix_busy_o']
     if not synth:
      env.update(load_busy=z3.BoolVal(False),mix_busy=z3.BoolVal(False),vec_ready=z3.BoolVal(True),vec_busy=z3.BoolVal(False))
     for n in ('mode_valid','dispatch','panic_accept'):env[n]=parse(equation(base,n),env)
     env['core_event_valid']=z3.And(env['dispatch'],z3.Bool('arbitrary_event_qualification'))
     env['event_valid_i']=z3.And(env['core_event_valid'],z3.Not(z3.Bool('scope_enable')));env['mode_set_valid_i']=env['mode_valid'];env['event_ready_o']=z3.Bool('arbitrary_oscillator_event_ready')
     if synth:
      env['quiescent_o']=parse(q.replace('!(|sine_pending_valid)','sine_pending_empty'),env)
      env['core_sample_ready']=parse(sr,env)
      env.update(oscillator_quiescent=env['quiescent_o'],vector_sample_ready_o=z3.Bool('vec_ready'),vector_valid_o=z3.Bool('vec_valid'),vector_busy_o=z3.Bool('vec_busy'))
      env['runtime_quiescent']=parse(eq,env)
     else:env.update(core_sample_ready=z3.BoolVal(True),runtime_quiescent=z3.Not(z3.Bool('rendered')))
     reference=parse(old,env);candidate=z3.If(z3.And(z3.Or(z3.Bool('pending'),z3.Bool('sample_ce_i')),z3.Not(z3.Bool('runtime_config_busy'))),parse(fast,env),z3.BoolVal(False))
     s=z3.Solver();s.add(reference!=candidate);out=str(s.check());assert out=='unsat',s.model();rows.append({'synth_engines':synth,'all_binary_combinational_states':out,'reachability_assumptions':[]})
     for name,target in [('fault','!runtime_fault'),('lifecycle','!usb_lifecycle'),('clear','!native_clear'),('configuration','!runtime_config_block'),('quiescent','runtime_quiescent')]:
      assert fast.count(target)==1;bad=z3.If(z3.And(z3.Or(z3.Bool('pending'),z3.Bool('sample_ce_i')),z3.Not(z3.Bool('runtime_config_busy'))),parse(fast.replace(target,'1'),env),z3.BoolVal(False));s=z3.Solver();s.add(reference!=bad);out=str(s.check());assert out=='sat',(synth,name);rows.append({'synth_engines':synth,'negative_removed_veto':name,'result':out,'counterexample':str(s.model())})
    # Compile exact source equations/procedural event cone and exact candidate case.
    bools='pending sample_ce_i runtime_config_busy mode_pending mode_ready usb_lifecycle native_clear event_config_block event_valid releasing deferred_current sustain scope_enable core_expression_ready vec_dispatch_ready core_event_ready full synth_joined vec_joined fx_sample_slot_ready fx_ready runtime_fault runtime_config_block rst_ni vec_ready_state vec_busy_state vec_valid mix_busy_state rendered partial_busy partial_valid gain_valid midi_valid issue_active slot_read_valid pitch_write_valid arithmetic_busy sine_valid_o gain_product_valid envelope_product_valid finalize_valid quantizer_quiescent osc_sample_valid envelope_lane_busy'.split()
    text='module tb;parameter integer NO_SYNTH=0;\nlogic '+','.join(bools)+';\n'
    text+='localparam REQUEST_DRIVEN_RENDER=1,RUNTIME_RATE_ENABLE=1,RUNTIME_EFFECTS_ENABLE=1,TIMING_OPTIMIZED=1,PIPELINED_RATE=1;localparam [2:0]LOAD_IDLE=0;\n'
    text+='logic [2:0]load_state;logic [3:0]sine_pending_valid,kind;logic [6:0]a,b,release_index;logic [31:0]allocated;logic [12:0]tf_scope_control_o;logic [5:0]legacy_cancel_tail;\n'
    text+='wire load_busy=NO_SYNTH ? 0 : load_state!=LOAD_IDLE;wire mix_busy=NO_SYNTH ? 0 : mix_busy_state;wire mix_busy_o=mix_busy;wire vec_ready=NO_SYNTH ? 1 : vec_ready_state;wire vec_busy=NO_SYNTH ? 0 : vec_busy_state;\n'
    text+='wire oscillator_quiescent='+q.replace('sample_valid_o','osc_sample_valid')+';\n'
    text+='wire runtime_quiescent=NO_SYNTH ? !rendered : '+eq.replace('vector_sample_ready_o','vec_ready').replace('vector_valid_o','vec_valid').replace('vector_busy_o','vec_busy')+';\n'
    text+='wire event_valid_i=core_event_valid && !scope_enable;wire event_ready_o=core_event_ready;wire mode_set_valid_i=mode_valid;wire quiescent_o=oscillator_quiescent;\n'
    text+='wire core_sample_ready=NO_SYNTH ? 1 : '+sr+';\n'
    text+='wire mode_valid='+equation(base,'mode_valid')+';\nwire dispatch='+equation(base,'dispatch')+';\nwire panic_accept='+equation(base,'panic_accept')+';\n'
    text+='logic core_event_valid,core_expression_valid,core_note_on,event_ready;logic [6:0]core_note,core_velocity,core_expression_note,core_expression_value;\n'+control+'\n'
    text+='wire reference_core_ce='+old+';logic core_ce;\n'+case+'\n'
    text+='''integer checks=0,k,j,idx,t;reg [31:0]rng=32'h91847bda;
    function automatic [1:0]code4();begin rng=(rng>>1)^((rng&1)?32'h80200003:0);code4=rng[1:0];end endfunction
    function automatic four(input integer code);begin case(code&3)0:four=0;1:four=1;2:four=1'bx;3:four=1'bz;endcase end endfunction
    function automatic random4();random4=four(code4());endfunction
    task automatic check;begin #1;if(core_ce!==reference_core_ce)$fatal(1,"core_ce four-state mismatch vector=%0d no_synth=%0d controls=%b%b%b old=%b new=%b",checks,NO_SYNTH,pending,sample_ce_i,runtime_config_busy,reference_core_ce,core_ce);checks=checks+1;end endtask
    task automatic healthy;begin
    '''+''.join(n+'=0;\n'for n in bools)+'''rst_ni=1;vec_ready_state=1;fx_sample_slot_ready=1;fx_ready=1;quantizer_quiescent=1;mode_ready=1;core_event_ready=1;vec_dispatch_ready=1;core_expression_ready=1;
    load_state=0;sine_pending_valid=0;kind=2;a=120;b=0;release_index=0;allocated=0;tf_scope_control_o=0;legacy_cancel_tail=0;end endtask
    initial begin
    // All four values of the three optimization controls with healthy actual
    // stored pipeline state, varied real event/control branches and cancellation.
    for(k=0;k<64;k=k+1)for(j=0;j<128;j=j+1)begin healthy();
    pending=four(k);sample_ce_i=four(k>>2);runtime_config_busy=four(k>>4);
    event_valid=j[0];releasing=j[1];mode_pending=j[2];usb_lifecycle=j[3];native_clear=j[4];scope_enable=j[5];event_config_block=j[6];deferred_current=1;
    kind=4'(j%6);a=(j%5==0)?120:7'(j);b=127;check();end
    '''
    # For every eligible combination, every single actual scalar gets all four
    # values while all other stored state is healthy, exposing buried X behavior.
    for n in bools:
     text+='for(k=0;k<3;k=k+1)for(j=0;j<4;j=j+1)begin healthy();pending=k!=1;sample_ce_i=k!=0;'+n+'=four(j);check();end\n'
    text+='''for(k=0;k<131072;k=k+1)begin
    '''+''.join(n+'=random4();\n'for n in bools)+'''pending=four(k);sample_ce_i=four(k>>2);runtime_config_busy=four(k>>4);load_state=3'(rng);sine_pending_valid=4'(rng>>3);allocated=rng;kind=4'(rng>>7);a=7'(rng>>11);b=7'(rng>>18);tf_scope_control_o=13'(rng>>2);legacy_cancel_tail=6'(rng>>20);
    if(k%13==0)load_state[k%3]=random4();if(k%17==0)sine_pending_valid[k%4]=random4();check();end
    $display("PASS actual-source core_ce four-state no_synth=%0d checks=%0d",NO_SYNTH,checks);$finish;end
    endmodule
    '''
    decl='logic core_event_valid,core_expression_valid,core_note_on,event_ready;logic [6:0]core_note,core_velocity,core_expression_note,core_expression_value;\n'
    assert text.count(decl)==1;text=text.replace(decl,'');text=text.replace('wire event_valid_i=',decl+'wire mode_valid;\nwire event_valid_i=');text=text.replace('wire mode_valid=','assign mode_valid=')
    fixture=P/'actual_source_four_state.sv';fixture.write_text(text);runs=[]
    for no in (0,1):
     binary=P/f'four_state_{no}.vvp';cmd=['iverilog','-g2012','-s','tb',f'-Ptb.NO_SYNTH={no}','-o',str(binary),str(fixture)];p=subprocess.run(cmd,capture_output=True,text=True,timeout=60);(P/f'compile_{no}.log').write_text(p.stdout+p.stderr);assert p.returncode==0,p.stderr
     p=subprocess.run(['vvp',str(binary)],capture_output=True,text=True,timeout=60);(P/f'run_{no}.log').write_text(p.stdout+p.stderr);assert p.returncode==0,p.stdout+p.stderr;runs.append({'no_synth':no,'returncode':p.returncode,'log':p.stdout.strip(),'log_sha256':sha(P/f'run_{no}.log')})
    negative_runs=[]
    for label,changed_case in [
        ('drop_fault',case.replace(fast,fast.replace('!runtime_fault','1'))),
        ('drop_lifecycle',case.replace(fast,fast.replace('!usb_lifecycle','1'))),
        ('unknown_controls_use_fast',case.replace('default: core_ce='+old+';','default: core_ce='+fast+';'))]:
        assert changed_case!=case and text.count(case)==1,label
        mutant=P/(label+'.sv');mutant.write_text(text.replace(case,changed_case));binary=P/(label+'.vvp')
        cmd=['iverilog','-g2012','-s','tb','-o',str(binary),str(mutant)]
        cp=subprocess.run(cmd,capture_output=True,text=True,timeout=60);(P/(label+'-compile.log')).write_text(cp.stdout+cp.stderr);assert cp.returncode==0,cp.stderr
        run=subprocess.run(['vvp',str(binary)],capture_output=True,text=True,timeout=60);(P/(label+'-run.log')).write_text(run.stdout+run.stderr)
        assert run.returncode!=0 and 'core_ce four-state mismatch' in run.stdout,label+': '+run.stdout+run.stderr
        negative_runs.append({'mutation':label,'expected_failure_observed':True,'source_sha256':sha(mutant),'run_log_sha256':sha(P/(label+'-run.log'))})

    inputs=[REFERENCE,EVENT,OSCILLATOR,ENGINES,SERVICE,Path(__file__),ROOT/'sim/audio/prove_effect_slot_admission.py']
    record={'schema':1,'passed':True,'production_modified':False,'binary':rows,'source_bound_four_state':runs,'fixture_sha256':sha(fixture),'input_sha256':{str(p):sha(p)for p in inputs},'source_contracts':['all actual event-valid assignments are dispatch-qualified','mode_valid and dispatch exclude eligible render controls','runtime_quiescent includes actual oscillator_quiescent','oscillator_quiescent absorbs all stored sample-ready conditions','no-synth exact sample-ready constant and !rendered quiescence','native flags only; disabled original expression and X/Z fallback exact'],'limits':'Boolean grammar actual-source equation proof and finite actual-source four-state simulation; no physical timing/resource/hardware claim. Full-module sequential miters are separate.'}
    record['source_contract']=contract;record['source_drift_controls']=source_negatives;record['actual_source_negative_four_state']=negative_runs
    assert before=={str(p):sha(p)for p in tracked},'sample admission proof input drift'
    record['all_inputs_unchanged']=True
    (P/'verification.json').write_text(json.dumps(record,indent=2)+'\n');print(json.dumps({'passed':True,'binary_proofs':len(rows),'four_state_runs':runs},indent=2))

if __name__=='__main__':main()
