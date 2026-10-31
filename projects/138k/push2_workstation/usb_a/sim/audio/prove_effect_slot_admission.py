#!/usr/bin/env python3
"""Prove the native core_ce cofactor from actual maintained SV equations."""
from pathlib import Path
import argparse,hashlib,json,re,subprocess,sys
import z3

ROOT=Path(__file__).resolve().parents[2]
OLD_SHA='07e61423d09114dbb2ca3a19d0fc2084c35457a366f66890f6b7573e61a0046b'

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def one(text,pattern):
    found=re.findall(pattern,text,re.S)
    if len(found)!=1:raise ValueError('source equation anchor drift: '+pattern)
    return found[0]
def equation(text,name):return one(text,r'\b(?:assign|wire)\s+'+re.escape(name)+r'\s*=\s*(.*?);')

class BooleanSV:
    """Only the boolean/equality/conditional grammar used by these equations."""
    def __init__(self,text,values):
        self.tokens=re.findall(r'&&|\|\||==|!=|[!()?:]|[A-Za-z_]\w*|\d+',text)
        if ''.join(self.tokens)!=re.sub(r'\s+','',text):raise ValueError('unsupported SV expression '+text)
        self.i=0;self.values=values
    def take(self,value):
        if self.i<len(self.tokens) and self.tokens[self.i]==value:self.i+=1;return True
        return False
    def atom(self):
        if self.take('!'):return z3.Not(self.atom())
        if self.take('('):
            result=self.conditional();assert self.take(')');return result
        name=self.tokens[self.i];self.i+=1
        value=z3.BoolVal(name=='1') if name in ('0','1') else self.values[name] if name in self.values else z3.Bool(name)
        equality=self.take('==');inequality=False if equality else self.take('!=')
        if equality or inequality:
            other=self.tokens[self.i];self.i+=1
            rhs=(z3.BitVecVal(int(other),value.size()) if z3.is_bv(value) else z3.BoolVal(other=='1')) if other.isdecimal() else self.values.get(other,z3.Bool(other))
            value=value!=rhs if inequality else value==rhs
        return value
    def conjunction(self):
        value=self.atom()
        while self.take('&&'):value=z3.And(value,self.atom())
        return value
    def disjunction(self):
        value=self.conjunction()
        while self.take('||'):value=z3.Or(value,self.conjunction())
        return value
    def conditional(self):
        value=self.disjunction()
        if self.take('?'):
            yes=self.conditional();assert self.take(':');value=z3.If(value,yes,self.conditional())
        return value
    def result(self):
        value=self.conditional();assert self.i==len(self.tokens);return value

def parse(text,values):return BooleanSV(text,values).result()

def broadcast_expression(text,native):
    """Read the binary cofactor and check every non-binary fallback anchor."""
    body=one(native,r'logic config_accept;\s*always_comb begin\s*case \(\{rate_commit_i,busy\}\)(.*?)endcase\s*end')
    expression=one(body,r"2'b10:\s*config_accept=(.*?);")
    rest=re.sub(r"2'b10:\s*config_accept=.*?;",'',body,flags=re.S)
    assert re.sub(r'\s+','',rest)=="2'b00,2'b01,2'b11:config_accept=1'b0;default:config_accept=rate_commit_i&&rate_ready_o;",'configuration case/fallback changed'
    assert equation(native,'engine_rate_commit')=='config_accept','engine broadcast split'
    assert one(text,r'\.config_valid_i\((.*?)\),\.rate_44100_i,')=='engine_rate_commit','effect broadcast split'
    return 'rate_commit_i && !busy && ('+expression+')'

def prove_configuration(text,native,expression):
    # Every actual procedural event-valid assignment is zero or dispatch
    # qualified. Abstract the remaining event qualification freely; this
    # includes every input/state without a reachability assumption.
    control=one(text,r'always_comb begin\s*(core_event_valid=0;.*?)\n  end\n  wire decoder_valid')
    event=re.findall(r'\bcore_event_valid\s*=\s*(.*?);',control)
    expr=re.findall(r'\bcore_expression_valid\s*=\s*(.*?);',control)
    assert [re.sub(r'\s+','',v) for v in event]==['0','dispatch&&deferred_current','dispatch&&!(kind==1&&full)']
    assert [re.sub(r'\s+','',v) for v in expr]==['0','dispatch&&core_expression_ready']
    env={'allocated':z3.BitVec('allocated',32),'kind':z3.BitVec('kind',4),'a':z3.BitVec('a',7)}
    for name in ('runtime_config_busy','runtime_config_block','runtime_fault'):
        env[name]=parse(equation(native,name),env)
    # The private service fence may differ only on a sample edge, where the
    # actual event/mode equations force admission low. main() first proves
    # this relation from the actual maintained service wires and port binding.
    env['event_config_block']=z3.If(z3.Bool('sample_ce_i'),z3.Bool('private_event_fence_on_sample'),env['runtime_config_block'])
    for name in ('mode_valid','dispatch','panic_accept'):
        env[name]=parse(equation(text,name),env)
    env['core_event_valid']=z3.And(env['dispatch'],z3.Bool('event_qualification'))
    env['core_expression_valid']=parse('dispatch && core_expression_ready',env)
    env['rate_ready_o']=parse(equation(native,'rate_ready_o'),env)
    old=parse('rate_commit_i && rate_ready_o',env);new=parse(expression,env)
    solver=z3.Solver();solver.add(old!=new);status=str(solver.check());assert status=='unsat',solver.model()
    rows=[{'configuration_broadcast_all_combinational_states':status,'reachability_assumptions':[],
           'event_qualification':'arbitrary, actual assignments all dispatch-qualified'}]
    for name,anchor in [('lifecycle_veto_removed','!usb_lifecycle'),('fault_veto_removed','!runtime_fault'),
                        ('quiet_veto_removed','pipeline_quiet'),('busy_veto_removed','!busy')]:
        assert expression.count(anchor)==1
        mutant=parse(expression.replace(anchor,'1'),env)
        solver=z3.Solver();solver.add(old!=mutant);status=str(solver.check());assert status=='sat',name
        rows.append({'mutant':name,'different_actual_broadcast':status,'counterexample':str(solver.model())})
    return rows

def four_state_configuration(text,native,out):
    # Compile the actual procedural event cone and actual new case, keeping
    # the previous public-ready expression as the independent reference.
    control=one(text,r'(always_comb begin\s*core_event_valid=0;.*?)\n  end\n  wire decoder_valid')+'\n  end\n'
    case=one(native,r'(always_comb begin\s*case \(\{rate_commit_i,busy\}\).*?endcase\s*end)')
    names='rate_commit_i busy rst_ni failed fx_fault pipeline_quiet usb_lifecycle fx_config_ready history_clear_i mode_pending mode_ready pending sample_ce_i native_clear load_busy mix_busy vec_busy TIMING_OPTIMIZED event_valid releasing deferred_current sustain core_expression_ready scope_enable vec_dispatch_ready core_event_ready RUNTIME_RATE_ENABLE full'
    declarations='logic '+','.join(names.split())+';\n'
    declarations+='logic [3:0] kind;logic [6:0] a,b,release_index;logic [31:0] allocated;logic [12:0] tf_scope_control_o;\n'
    declarations+='logic mode_valid,dispatch,panic_accept,runtime_config_block,runtime_config_busy,runtime_fault,rate_ready_o,config_accept;\n'
    declarations+='logic event_config_block,event_rate_commit_i;\n'
    declarations+='logic core_event_valid,core_expression_valid,core_note_on,event_ready;logic [6:0] core_note,core_velocity,core_expression_note,core_expression_value;\n'
    assigns=''.join('assign '+name+'='+equation(native if name in ('runtime_config_block','runtime_config_busy','runtime_fault','rate_ready_o') else text,name)+';\n'
                    for name in ('runtime_config_block','runtime_config_busy','runtime_fault','mode_valid','dispatch','panic_accept','rate_ready_o'))
    random_assign=''.join(name+'=random4();\n' for name in names.split())
    event_case=one(text,r'begin: sample_event_config_fence\s*(.*?)\s*end else begin: full_event_config_fence')
    generated=('module tb;\n'+declarations+assigns+event_case+'\n'+control+case+'''
integer checks=0;integer k,j;reg [31:0] rng=32'h7ad1395b;
function automatic [1:0] random_code();begin rng=(rng>>1)^((rng&1)?32'h80200003:0);random_code=rng[1:0];end endfunction
function automatic random4();begin case(random_code()) 0:random4=0;1:random4=1;2:random4=1'bx;3:random4=1'bz;endcase end endfunction
function automatic digit4(input integer value);begin case(value&3) 0:digit4=0;1:digit4=1;2:digit4=1'bx;3:digit4=1'bz;endcase end endfunction
task automatic check;begin event_rate_commit_i=(sample_ce_i===1'b0)?rate_commit_i:random4();#1;if(config_accept !== (rate_commit_i && rate_ready_o))$fatal(1,"broadcast four-state mismatch vector=%0d",checks);checks=checks+1;end endtask
initial begin
'''+random_assign+'''
kind=2;a=120;b=0;release_index=0;allocated=0;tf_scope_control_o=0;
// All four values of seven acceptance inputs; other event/state inputs
// vary independently on each vector, including X and Z.
for(k=0;k<16384;k=k+1)begin
'''+random_assign+'''
rate_commit_i=digit4(k);busy=digit4(k>>2);rst_ni=digit4(k>>4);failed=digit4(k>>6);
pipeline_quiet=digit4(k>>8);usb_lifecycle=digit4(k>>10);fx_config_ready=digit4(k>>12);
fx_fault=0;kind=random_code();a=7'(rng);b=7'(rng>>7);allocated=rng;tf_scope_control_o=13'(rng>>11);check();
end
for(j=0;j<65536;j=j+1)begin
'''+random_assign+'''
kind=4'(rng);a=7'(rng>>4);b=7'(rng>>11);allocated=rng;tf_scope_control_o=13'(rng>>15);check();
end
$display("PASS configuration four-state vectors=%0d",checks);$finish;end
endmodule
''')
    source=out/'configuration_four_state.sv';source.write_text(generated)
    executable=out/'configuration_four_state.vvp'
    compile=subprocess.run(['iverilog','-g2012','-s','tb','-o',str(executable),str(source)],capture_output=True,text=True,timeout=60)
    (out/'fourstate_compile.log').write_text(compile.stdout+compile.stderr)
    if compile.returncode:raise ValueError('four-state cone compile failed: '+compile.stderr)
    run=subprocess.run(['vvp',str(executable)],capture_output=True,text=True,timeout=60)
    (out/'fourstate_run.log').write_text(run.stdout+run.stderr)
    assert run.returncode==0 and 'PASS configuration four-state vectors=81920' in run.stdout,run.stdout+run.stderr
    return {'scope':'actual source procedural cone, finite four-state vectors; no cycle/physical timing claim','vectors':81920,
            'seven_inputs_all_four_value_combinations':16384,'seeded_additional_vectors':65536,
            'fixture_sha256':sha(source),'compile_log_sha256':sha(out/'fourstate_compile.log'),'run_log_sha256':sha(out/'fourstate_run.log')}

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',type=Path,required=True);args=ap.parse_args()
    out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    top=ROOT/'rtl/audio/gw138k_event_workstation.sv';fx=ROOT/'rtl/audio/workstation_runtime_stereo_effects.sv'
    fixture=ROOT/'sim/audio/fixtures/core_ce_before_effect_slot.svh'
    paths=[top,fx,fixture,Path(__file__).resolve()];before={str(p):sha(p) for p in paths}
    old=fixture.read_text().strip();assert hashlib.sha256(('  '+old).encode()).hexdigest()==OLD_SHA
    text=top.read_text();effect=fx.read_text();sample_contract=None
    if 'begin: native_sample_admission' in text:
        import prove_sample_admission_cofactor as admission
        sample_contract=admission.source_contract(text)
        text=admission.reference_view(text)
        paths.extend([Path(admission.__file__).resolve(),admission.REFERENCE])
        before.update({str(p):sha(p)for p in (Path(admission.__file__).resolve(),admission.REFERENCE)})
    from prove_event_config_cofactor import binary_proof
    service=ROOT/'rtl/audio/workstation_audio_render_service.sv'
    private_proof=Path(__file__).with_name('prove_event_config_cofactor.py')
    paths.extend([service,private_proof]);before.update({str(p):sha(p)for p in (service,private_proof)})
    private_contract=binary_proof(service.read_text(),text)
    native=one(text,r'begin: runtime_configuration\n(.*?)end else begin: fixed_configuration')
    expr={k:equation(text,k) for k in ['core_ce','engine_clear']}
    expr.update({k:equation(native,k) for k in ['runtime_config_busy','runtime_config_block','runtime_fault']})
    expr.update({k:equation(effect,k) for k in ['sample_slot_ready_o','ready_o','config_accept','history_accept']})
    expr['old_core_ce']=old.split('=',1)[1].rstrip(';')
    broadcast=broadcast_expression(text,native)
    expr['effect_config_input']=broadcast
    expr['effect_history_input']=one(text,r'\.history_clear_i\((history_clear_i && history_ready_o)\)')
    assert '.clear_i(engine_clear)' in text
    original_ready='state==IDLE && !barrier_busy && !fault_o && !clear_i && !config_accept && !history_accept'
    assert re.sub(r'\s+','',expr['ready_o'])==re.sub(r'\s+','',original_ready),'full external ready changed'
    state=z3.BitVec('effect_state',4);fault=z3.Bool('effect_fault')
    rows=prove_configuration(text,native,broadcast)
    for runtime in (False,True):
        env={'RUNTIME_EFFECTS_ENABLE':z3.BoolVal(runtime),'busy':z3.Bool('runtime_busy'),'fx_fault':fault,
             'legacy_cancel_tail':z3.BitVec('legacy_cancel_tail',6)}
        env['runtime_config_busy']=parse(expr['runtime_config_busy'],env)
        env['runtime_config_block']=parse(expr['runtime_config_block'],env)
        env['runtime_fault']=parse(expr['runtime_fault'],env)
        engine_clear=parse(expr['engine_clear'],env)
        e={'state':state,'IDLE':z3.BitVecVal(0,4),'fault_o':fault,'clear_i':engine_clear,
           'config_valid_i':parse(expr['effect_config_input'],env),
           'history_clear_i':parse(expr['effect_history_input'],env),
           'config_ready_o':z3.Bool('effect_config_ready'),'history_ready_o':z3.Bool('effect_history_ready')}
        e['config_accept']=parse(expr['config_accept'],e);e['history_accept']=parse(expr['history_accept'],e)
        env['fx_ready']=parse(expr['ready_o'],e)
        env['fx_sample_slot_ready']=parse(expr['sample_slot_ready_o'],e)
        old_ce=parse(expr['old_core_ce'],env);new_ce=parse(expr['core_ce'],env)
        solver=z3.Solver();solver.add(old_ce!=new_ce);status=str(solver.check());assert status=='unsat',solver.model()
        rows.append({'runtime_effects':runtime,'all_combinational_states':'unsat','reachability_assumptions':[]})
        if runtime:
            for name,key,changed in [
                ('slot_barrier_removed','sample_slot_ready_o','state==IDLE'),
                ('top_fault_veto_removed','core_ce',expr['core_ce'].replace('!runtime_fault','1')),
                ('top_clear_veto_removed','core_ce',expr['core_ce'].replace('!native_clear','1')),
                ('top_configuration_veto_removed','core_ce',expr['core_ce'].replace('!runtime_config_block','1'))]:
                changed_env=dict(env)
                if key=='sample_slot_ready_o':changed_env['fx_sample_slot_ready']=parse(changed,e)
                mutant=parse(changed if key=='core_ce' else expr['core_ce'],changed_env)
                solver=z3.Solver();solver.add(old_ce!=mutant);status=str(solver.check());assert status=='sat',name
                rows.append({'mutant':name,'different_actual_core_ce':'sat','counterexample':str(solver.model())})
    four_state=four_state_configuration(text,native,out)
    assert before=={str(p):sha(p) for p in paths},'source drift'
    record={'passed':True,'scope':'actual SV boolean equations, all combinational states and both runtime/legacy selection; no clock-cycle or sampling changes',
        'input_sha256':before,'old_core_ce_sha256':OLD_SHA,'equations':expr,'proofs':rows,'private_service_contract':private_contract,'configuration_four_state':four_state,'z3_version':z3.get_full_version(),
        'sample_admission_source_contract':sample_contract,
        'core_ce_proof_view':'Exact inverse to the pre-sample-admission source when present; its later cofactor has a separate maintained proof and full-module miter',
        'hardware_accepted':False,'physical_timing_verified':False,'resource_saving_claimed':False}
    (out/'verification.json').write_text(json.dumps(record,indent=2)+'\n');print(json.dumps(rows,indent=2))
if __name__=='__main__':main()
