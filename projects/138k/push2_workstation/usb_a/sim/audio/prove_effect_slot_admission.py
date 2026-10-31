#!/usr/bin/env python3
"""Prove the native core_ce cofactor from actual maintained SV equations."""
from pathlib import Path
import argparse,hashlib,json,re,sys
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
        self.tokens=re.findall(r'&&|\|\||==|[!()?:]|[A-Za-z_]\w*|[01]',text)
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
        if self.take('=='):
            other=self.tokens[self.i];self.i+=1
            rhs=z3.BitVecVal(int(other),value.size()) if other in ('0','1') else self.values[other]
            value=value==rhs
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

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',type=Path,required=True);args=ap.parse_args()
    out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    top=ROOT/'rtl/audio/gw138k_event_workstation.sv';fx=ROOT/'rtl/audio/workstation_runtime_stereo_effects.sv'
    fixture=ROOT/'sim/audio/fixtures/core_ce_before_effect_slot.svh'
    paths=[top,fx,fixture,Path(__file__).resolve()];before={str(p):sha(p) for p in paths}
    old=fixture.read_text().strip();assert hashlib.sha256(('  '+old).encode()).hexdigest()==OLD_SHA
    text=top.read_text();effect=fx.read_text()
    native=one(text,r'begin: runtime_configuration\n(.*?)end else begin: fixed_configuration')
    expr={k:equation(text,k) for k in ['core_ce','engine_clear']}
    expr.update({k:equation(native,k) for k in ['runtime_config_busy','runtime_config_block','runtime_fault']})
    expr.update({k:equation(effect,k) for k in ['sample_slot_ready_o','ready_o','config_accept','history_accept']})
    expr['old_core_ce']=old.split('=',1)[1].rstrip(';')
    expr['effect_config_input']=one(text,r'\.config_valid_i\((rate_commit_i && rate_ready_o)\)')
    expr['effect_history_input']=one(text,r'\.history_clear_i\((history_clear_i && history_ready_o)\)')
    assert '.clear_i(engine_clear)' in text
    original_ready='state==IDLE && !barrier_busy && !fault_o && !clear_i && !config_accept && !history_accept'
    assert re.sub(r'\s+','',expr['ready_o'])==re.sub(r'\s+','',original_ready),'full external ready changed'
    state=z3.BitVec('effect_state',4);fault=z3.Bool('effect_fault')
    rows=[]
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
    assert before=={str(p):sha(p) for p in paths},'source drift'
    record={'passed':True,'scope':'actual SV boolean equations, all combinational states and both runtime/legacy selection; no clock-cycle or sampling changes',
        'input_sha256':before,'old_core_ce_sha256':OLD_SHA,'equations':expr,'proofs':rows,'z3_version':z3.get_full_version(),
        'hardware_accepted':False,'physical_timing_verified':False,'resource_saving_claimed':False}
    (out/'verification.json').write_text(json.dumps(record,indent=2)+'\n');print(json.dumps(rows,indent=2))
if __name__=='__main__':main()
