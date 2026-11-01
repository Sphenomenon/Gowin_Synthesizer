#!/usr/bin/env python3
"""Actual owner context-output equivalence: four-state proof, module and NBA miter."""
from pathlib import Path
import argparse,hashlib,json,re,subprocess,sys
import z3
import ae350_pcm_output_context_sources as sources
import run_ae350_pcm_window_gate as whole

ROOT=Path(__file__).resolve().parents[2]
sha=sources.sha

def one(text,pattern):
    matches=re.findall(pattern,text,re.S)
    assert len(matches)==1,pattern
    return matches[0]

def proof():
    # 0/1/X/Z scalar abstraction over every actual equality result includes
    # every raw key/rate/epoch value, without a reachability assumption.
    old=sources.reference_view();new=sources.SOURCE.read_text();values={}
    def value(name):
        if name in ('0','1'):return z3.BitVecVal(int(name),2)
        if name not in values:values[name]=z3.BitVec(name,2)
        return values[name]
    def conjunction(a,b):
        return z3.If(z3.Or(a==0,b==0),z3.BitVecVal(0,2),
            z3.If(z3.And(a==1,b==1),z3.BitVecVal(1,2),z3.BitVecVal(2,2)))
    def negate(a):return z3.If(a==0,z3.BitVecVal(1,2),z3.If(a==1,z3.BitVecVal(0,2),z3.BitVecVal(2,2)))
    def mux(c,a,b):return z3.If(c==0,b,z3.If(c==1,a,z3.If(a==b,a,z3.BitVecVal(2,2))))
    class Parse:
        def __init__(self,text,env):
            self.tokens=re.findall(r'&&|[!()?:]|\w+',text);self.i=0;self.env=env
            assert ''.join(self.tokens)==re.sub(r'\s+','',text),text
        def take(self,t):
            if self.i<len(self.tokens)and self.tokens[self.i]==t:self.i+=1;return True
            return False
        def atom(self):
            if self.take('!'):return negate(self.atom())
            if self.take('('):v=self.expr();assert self.take(')');return v
            t=self.tokens[self.i];self.i+=1;return self.env.get(t,value(t))
        def expr(self):
            v=self.atom()
            while self.take('&&'):v=conjunction(v,self.atom())
            if self.take('?'):a=self.expr();assert self.take(':');v=mux(v,a,self.expr())
            return v
        def result(self):
            v=self.expr();assert self.i==len(self.tokens);return v
    def equation(text,name):
        expression=one(text,r'\b(?:assign|wire)\s+'+name+r'\s*=\s*(.*?);')
        return expression.replace("active_rate==(rate_44100_i ? 32'd44100:32'd48000)",'rate_match')
    env={}
    for n in ('physical_matches','usable'):
        env[n]=Parse(equation(old,n),env).result()
    env['pcm_output_without_context']=Parse(equation(new,'pcm_output_without_context'),env).result()
    normalize=lambda e:e.replace("{interpolated_l,16'd0}",'payload').replace("32'd0",'0').replace('legacy_left_i','legacy')
    original=Parse(normalize(equation(old,'pcm_left_o')),env).result()
    modified=Parse(normalize(equation(new,'pcm_left_o')),env).result()
    solver=z3.Solver();solver.add(original!=modified);assert solver.check()==z3.unsat
    negatives=[]
    expression=normalize(equation(new,'pcm_left_o'))
    for label,mutant in [('missing_context',expression.replace('context_ready_i && ','',1)),
                         ('reversed_context',expression.replace('context_ready_i && ','!context_ready_i && ',1)),
                         ('legacy_always_pcm',expression.replace('selected ?','1 ?' ,1))]:
        variant=Parse(mutant,env).result();solver=z3.Solver();solver.add(original!=variant)
        assert solver.check()==z3.sat,label
        negatives.append(dict(name=label,different_output='sat',counterexample=str(solver.model())))
    return dict(four_state_equivalence='unsat',raw_four_state_encoding='0=0,1=1,2=X,3=Z',
        source_expressions_parsed=True,arbitrary_comparison_results=True,reachability_assumptions=[],
        payload_and_legacy_bit_arbitrary_0_1_X_Z=True,negative_controls=negatives)

def compile_run(out,label,source,bench,reference,pass_text,negative=False):
    f=out/(label+'.sv');f.write_text(source)
    binary=out/(label+'.vvp');tb=out/(label+'_tb.sv');tb.write_text(bench)
    cmd=['iverilog','-g2012','-s','tb','-o',str(binary),str(tb),str(f),str(reference)]
    r=subprocess.run(cmd,capture_output=True,text=True,timeout=60);(out/(label+'_compile.log')).write_text(r.stdout+r.stderr)
    assert r.returncode==0,r.stderr
    r=subprocess.run(['vvp',str(binary)],capture_output=True,text=True,timeout=180);log=r.stdout+r.stderr
    (out/(label+'.log')).write_text(log)
    assert (r.returncode!=0 and 'context output mismatch' in log) if negative else (r.returncode==0 and pass_text in log),(label,log)
    return dict(returncode=r.returncode,negative_rejected=negative,source_sha256=sha(f),log_sha256=sha(out/(label+'.log')))

def fourstate_bench():
    pins='''.clk_i(clk),.reset_ni(rst),.cpu_ready_i(cpu),.command_valid_i(1'b0),.command_write_i(1'b0),
 .command_address_i(12'd0),.command_data_i(32'd0),.command_strobes_i(4'hf),
 .session_live_i(1'b1),.controller_epoch_i(32'd1),.transport_generation_i(32'd1),
 .context_ready_i(ctx),.rate_44100_i(rate),.physical_epoch_i(32'd1),.tf_busy_i(tf),
 .switch_busy_i(sw),.sample_take_i(1'b0),.legacy_left_i(legacy_l),.legacy_right_i(legacy_r),
 .history_ready_i(1'b0),.history_done_i(1'b0)'''
    forced='armed failed live_matches physical_epoch_match_0 physical_epoch_match_1 physical_epoch_match_2 physical_epoch_match_3 hold_serial cache_current selected'.split()
    decl='\n'.join('reg f_'+n+';'for n in forced)
    forces='\n'.join('force '+unit+'.'+n+'=f_'+n+';'for unit in ('dut','old_owner')for n in forced)
    forces+='\n'+'\n'.join('force '+unit+'.'+name+'='+reg+';'for unit in ('dut','old_owner')for name,reg in [('active_rate','active_rate'),('interpolated_l','payload_l'),('interpolated_r','payload_r')])
    scalar_assign='\n'.join(name+'=quad(control >> '+str(2*i)+');'for i,name in enumerate(['ctx','f_armed','f_failed','f_live_matches','sw','cpu','tf','f_hold_serial']))
    return '''`timescale 1ns/1ps
module tb;
reg clk=0,rst=1,cpu=1,ctx=1,rate=0,tf=0,sw=0;
reg[31:0]legacy_l=32'h5a960000,legacy_r=32'hc34b0000,active_rate=48000;
reg[15:0]payload_l=16'h51c3,payload_r=16'hbc29;
'''+decl+'\nworkstation_ae350_pcm_owner dut('+pins+');\npcm_owner_window_reference old_owner('+pins+''');
function quad(input integer v);begin case(v&3)0:quad=0;1:quad=1;2:quad=1'bx;3:quad=1'bz;endcase end endfunction
integer control,pattern,k,checks=0;reg[31:0]rng=32'h274f93a1;
task check;begin
 #1;
 if(dut.pcm_left_o!==old_owner.pcm_left_o || dut.pcm_right_o!==old_owner.pcm_right_o)
 $fatal(1,"context output mismatch pattern=%0d control=%0d left=%h/%h right=%h/%h",pattern,control,dut.pcm_left_o,old_owner.pcm_left_o,dut.pcm_right_o,old_owner.pcm_right_o);
 checks=checks+1;
end endtask
initial begin
'''+forces+'''
for(pattern=0;pattern<4;pattern=pattern+1)begin
 for(control=0;control<65536;control=control+1)begin
'''+scalar_assign+'''
 rng=rng^(rng<<13);rng=rng^(rng>>17);rng=rng^(rng<<5);
 f_selected=quad(rng);f_cache_current=quad(rng>>2);
 f_physical_epoch_match_0=quad(rng>>4);f_physical_epoch_match_1=quad(rng>>6);
 f_physical_epoch_match_2=quad(rng>>8);f_physical_epoch_match_3=quad(rng>>10);
 rate=quad(rng>>12);active_rate=pattern[0] ? 44100:48000;
 for(k=0;k<16;k=k+1)begin payload_l[k]=quad(rng>>(2*(k%16)));payload_r[k]=quad((~rng)>>(2*(k%16)));end
 legacy_l={payload_r,payload_l};legacy_r={payload_l,payload_r};
 check();
 // No edge may intervene before immediate context revocation zeroes PCM.
 f_armed=1;f_failed=0;f_live_matches=1;sw=0;cpu=1;tf=0;f_hold_serial=0;
 f_selected=1;f_cache_current=1;f_physical_epoch_match_0=1;f_physical_epoch_match_1=1;
 f_physical_epoch_match_2=1;f_physical_epoch_match_3=1;rate=0;active_rate=48000;
 payload_l=16'h7349;payload_r=16'h9ac5;ctx=1;check();ctx=0;check();
 if(dut.pcm_left_o!==0 || dut.pcm_right_o!==0)$fatal(1,"immediate context output mismatch");
 end
end
$display("PASS PCM context output actual four-state checks=%0d",checks);$finish;
end
endmodule
'''

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    inputs=list(dict.fromkeys(sources.inputs()+[Path(__file__).resolve(),Path(whole.__file__),ROOT/'sim/test_ae350_pcm_owner.py']))
    before={str(p):sha(p)for p in inputs};source=sources.SOURCE.read_text();reference=out/'reference.sv'
    reference.write_text(sources.reference_view().replace('module workstation_ae350_pcm_owner','module pcm_owner_window_reference',1))
    result=dict(schema=1,passed=False,source_implementation=True,contract=sources.contract(),proof=proof(),input_sha256=before,cases={},
        hardware_tested=False,physical_timing_verified=False,resource_saving_claimed=False,EDA_started=False)
    try:
        bench=fourstate_bench()
        for name,mutation in [('four_state',None),('missing_context',('context_ready_i && pcm_output_without_context','pcm_output_without_context')),
                              ('missing_hold',('!tf_busy_i && !hold_serial && cache_current','!tf_busy_i && cache_current')),
                              ('missing_epoch',('assign pcm_output_without_context=armed && !failed && live_matches &&\n        physical_epoch_match_0',
                                                'assign pcm_output_without_context=armed && !failed && live_matches &&\n        1\'b1'))]:
            text=source
            if mutation:
                old,new=mutation;assert text.count(old)==(2 if name=='missing_context'else 1);text=text.replace(old,new)
            result['cases'][name]=compile_run(out,name,text,bench,reference,'checks=786432',bool(mutation))
            print(name,result['cases'][name],flush=True)
        result['cases']['whole_owner']=compile_run(out,'whole_owner',source,whole.bench(),reference,'PASS PCM window gate whole-owner cycle reference:')
        assert all(sha(p)==h for p,h in before.items()),'maintained input drift'
        result['passed']=True
    finally:
        result['output_sha256']={str(p.relative_to(out)):sha(p)for p in out.rglob('*')if p.is_file()}
        (out/'verification.json').write_text(json.dumps(result,indent=2)+'\n')
    print('PASS exact PCM output source inverse, unrestricted four-state proof, actual-module context/NBA miters and three actual negative controls')

if __name__=='__main__':main()
