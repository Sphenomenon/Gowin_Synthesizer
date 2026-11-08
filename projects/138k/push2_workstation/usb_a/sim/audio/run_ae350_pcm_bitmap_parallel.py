#!/usr/bin/env python3
"""A9 private revoke cone: full-owner cycle miter and four-state guards."""
from pathlib import Path
import argparse,hashlib,json,subprocess,sys
import run_ae350_pcm_window_gate as whole
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from tools.workstation_pcm_bitmap_permission import restore_parallel,PARALLEL_OLD,PARALLEL_NEW

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    out=parser.parse_args().output.resolve();out.mkdir(parents=True,exist_ok=False)
    source=ROOT/'rtl/audio/workstation_ae350_pcm_owner.sv'
    current=source.read_text();before=restore_parallel(current).decode()
    sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
    inputs={str(p):sha(p)for p in [source,Path(__file__),Path(whole.__file__),
        ROOT/'tools/workstation_pcm_bitmap_permission.py',ROOT/'sim/test_ae350_pcm_owner.py']}
    reference=before.replace('module workstation_ae350_pcm_owner','module pcm_owner_window_reference',1)
    (out/'reference.sv').write_text(reference)
    (out/'tb.sv').write_text(whole.bench())
    rows={}
    def run(name,files,expected):
        binary=out/(name+'.vvp')
        c=subprocess.run(['iverilog','-g2012','-s','tb','-o',str(binary),*map(str,files)],capture_output=True,text=True,timeout=60)
        (out/(name+'-compile.log')).write_text(c.stdout+c.stderr)
        assert c.returncode==0,c.stderr
        r=subprocess.run(['vvp',str(binary)],capture_output=True,text=True,timeout=180)
        (out/(name+'.log')).write_text(r.stdout+r.stderr)
        passed=(r.returncode==0 if expected else r.returncode!=0)
        assert passed,(name,r.stdout,r.stderr)
        rows[name]=dict(passed=passed,exit_code=r.returncode,log=r.stdout+r.stderr)
        print(name,rows[name],flush=True)
    for name,text,expected in [('whole',current,True),('lost_revoke',current.replace(
            '            bitmap_clear_without_context=1;','            bitmap_clear_without_context=0;',1),False)]:
        (out/(name+'.sv')).write_text(text)
        run(name,[out/'tb.sv',out/(name+'.sv'),out/'reference.sv'],expected)
    # Exhaust all 4^9 scalar guard combinations. Complex vector predicates
    # are deliberately arbitrary scalars; the whole-owner test above keeps
    # their real dependencies and compares every stored bit and public output.
    names=['accepted_stop','accepted_cancel','armed','cpu_previous','cpu_ready_i',
           'live_matches','bitmap_physical_without_context','tf_busy_i','sample_take_i']
    decl='reg '+','.join(names)+',selected=1,hold_serial=0,cache_current=0;'
    assigns='\n'.join(n+'=quad(pattern >> '+str(2*i)+');'for i,n in enumerate(names))
    old=PARALLEL_OLD.replace('bitmap_clear_without_context','old_clear')
    new=PARALLEL_NEW.replace('bitmap_clear_without_context','new_clear')
    tb='''module tb;
'''+decl+'\nreg old_clear,new_clear;\n'+old+new+'''
function quad(input integer v);begin case(v&3)0:quad=0;1:quad=1;2:quad=1'bx;3:quad=1'bz;endcase end endfunction
integer pattern;
initial begin
for(pattern=0;pattern<262144;pattern=pattern+1)begin
'''+assigns+'''
#1;if(old_clear !== new_clear)$fatal(1,"parallel guard mismatch %0d",pattern);
end
$display("PASS four-state parallel guards checks=262144");$finish;
end
endmodule
'''
    (out/'guards.sv').write_text(tb);run('guards',[out/'guards.sv'],True)
    # Exercise the actual new ID decoder against the complete prior owner.
    # Every byte takes 00/ff/xx/zz, followed by a zero/X/Z in each individual
    # position of an otherwise all-one ID. No derived admission is forced.
    id_tb=whole.bench()
    declarations='''
integer id_pattern,id_byte,id_bit,id_checks=0;
reg [31:0] id_word;
function id_quad(input integer v);begin case(v&3)0:id_quad=0;1:id_quad=1;2:id_quad=1'bx;3:id_quad=1'bz;endcase end endfunction
'''
    id_tb=id_tb.replace('integer equivalence_cycles=0;',declarations+'integer equivalence_cycles=0;',1)
    marker='$display("PASS PCM window gate whole-owner'
    at=id_tb.index(marker)
    id_body='''
@(negedge clk);cv=0;cw=0;take=0;cpu=1;live=1;ctx_ready=1;tf=0;sw=0;rst=1;
for(id_pattern=0;id_pattern<352;id_pattern=id_pattern+1)begin
 @(negedge clk);
 if(id_pattern<256)begin
  for(id_byte=0;id_byte<4;id_byte=id_byte+1)
   for(id_bit=0;id_bit<8;id_bit=id_bit+1)id_word[id_byte*8+id_bit]=id_quad(id_pattern>>(id_byte*2));
 end else begin
  id_word=32'hffffffff;
  if(id_pattern<288)id_word[id_pattern-256]=0;
  else if(id_pattern<320)id_word[id_pattern-288]=1'bx;
  else id_word[id_pattern-320]=1'bz;
 end
 dut.command_id=id_word;old_owner.command_id=id_word;
 #1;if(dut.control_id_ok !== old_owner.control_id_ok)$fatal(1,"ID guard mismatch %h",id_word);
 id_checks=id_checks+1;
end
$display("PASS actual command-ID guard four-state patterns=%0d",id_checks);
'''
    id_tb=id_tb[:at]+id_body+id_tb[at:]
    (out/'id_tb.sv').write_text(id_tb)
    run('id_guards',[out/'id_tb.sv',out/'whole.sv',out/'reference.sv'],True)
    assert all(sha(p)==h for p,h in inputs.items())
    result=dict(passed=True,cases=rows,input_sha256=inputs,
        historical_parent_sha256=hashlib.sha256(before.encode()).hexdigest(),
        exact_source_inverse=True,new_cycles=False,hardware_tested=False,
        routed_timing_verified=False)
    (out/'verification.json').write_text(json.dumps(result,indent=2)+'\n')

if __name__=='__main__':main()
