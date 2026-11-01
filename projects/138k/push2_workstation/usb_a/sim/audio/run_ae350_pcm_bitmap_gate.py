#!/usr/bin/env python3
from pathlib import Path
import hashlib, json, subprocess, sys, difflib
import argparse
U=Path(__file__).resolve().parents[2]
SOURCE_SHA256='574c6e268e952a2d72063db5296e781528f47158f4c63ad8cc2968a767d1b71e'
REFERENCE_SHA256='3eab83ad77e0ff28aac3bee416751262bb3af01241d1df596e769a871d53f5b3'
REFERENCE=Path(__file__).with_name('fixtures')/'workstation_ae350_pcm_owner_before_bitmap_gate.sv'
parser=argparse.ArgumentParser(description='Verify private PCM bitmap write/flush ordering against the complete previous owner.')
parser.add_argument('--output',type=Path,required=True)
C=parser.parse_args().output.resolve();C.mkdir(parents=True,exist_ok=False)
sys.path.insert(0,str(U/'sim/audio'))
import run_ae350_pcm_window_gate as whole
import ae350_pcm_output_context_sources as output_context
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
p=U/'rtl/audio/workstation_ae350_pcm_owner.sv';original=REFERENCE.read_text()
assert sha(REFERENCE)==REFERENCE_SHA256
assert hashlib.sha256(output_context.reference_view(p.read_text()).encode()).hexdigest()==SOURCE_SHA256
inputs={str(p):sha(p),str(Path(whole.__file__)):sha(whole.__file__),str(U/'sim/test_ae350_pcm_owner.py'):sha(U/'sim/test_ae350_pcm_owner.py'),str(REFERENCE):sha(REFERENCE),str(Path(__file__).resolve()):sha(__file__)}
inputs.update({str(p):sha(p)for p in output_context.inputs()})
source=original
changes=[
 ('            for(k=0;k<4;k=k+1)written[k]<=0;\n',''),
 ('            for(k=0;k<4;k=k+1)begin written[k]<=0;frames[k]<=0;end','            for(k=0;k<4;k=k+1)frames[k]<=0;'),
 ('memory[{write_slot,write_index}]<=command_data_i;written[write_slot][write_index]<=1;','memory[{write_slot,write_index}]<=command_data_i;'),
 ('frames[tail_slot]<=staged_frames[7:0];written[tail_slot]<=0;tail_slot<=tail_slot+1\'b1;','frames[tail_slot]<=staged_frames[7:0];tail_slot<=tail_slot+1\'b1;')]
for before,after in changes:
 assert source.count(before)==1,before
 source=source.replace(before,after,1)
block='''    // Private bitmap writes retain the original ordering. The revocation
    // clear needs no failure-code or unrelated command-response selection.
    reg bitmap_clear_late /* synthesis syn_keep=1 */;
    always @* begin
        bitmap_clear_late=0;
        if(accepted_stop)bitmap_clear_late=1;
        if(accepted_cancel)bitmap_clear_late=1;
        if(rejected_commit && usable && key_matches && !owned[tail_slot])bitmap_clear_late=1;
        if(armed)begin
            if(cpu_previous && !cpu_ready_i)bitmap_clear_late=1;
            else if(!live_matches)bitmap_clear_late=1;
            else if(!physical_matches)bitmap_clear_late=1;
            else if(tf_busy_i)bitmap_clear_late=1;
            else if(sample_take_i && selected && !hold_serial && !cache_current)bitmap_clear_late=1;
        end
    end
    integer bitmap_slot;
    always @(posedge clk_i or negedge reset_ni)begin
        if(!reset_ni)begin
            for(bitmap_slot=0;bitmap_slot<4;bitmap_slot=bitmap_slot+1)written[bitmap_slot]<=0;
        end else begin
            if(accepted_window_write)written[write_slot][write_index]<=1;
            if(accepted_start)begin
                for(bitmap_slot=0;bitmap_slot<4;bitmap_slot=bitmap_slot+1)written[bitmap_slot]<=0;
            end
            if(accepted_commit)written[tail_slot]<=0;
            if(bitmap_clear_late)begin
                for(bitmap_slot=0;bitmap_slot<4;bitmap_slot=bitmap_slot+1)written[bitmap_slot]<=0;
            end
        end
    end
'''
anchor='    always @(posedge clk_i or negedge reset_ni)begin\n'
assert source.count(anchor)==1
source=source.replace(anchor,block+anchor,1)
# Reverse exact insertion and all four edits, binding every other source byte.
inverse=source.replace(block,'',1)
for before,after in reversed(changes):
 if not after:
  anchor2='            owned<=0;head_slot<=0;tail_slot<=0;head_index<=0;queued<=0;\n'
  # task only; the second reset occurrence is intentionally not changed.
  at=inverse.index(anchor2)+len(anchor2);inverse=inverse[:at]+before+inverse[at:]
 else:
  assert inverse.count(after)==1,after;inverse=inverse.replace(after,before,1)
assert inverse==original
assert source==output_context.reference_view(p.read_text()), 'maintained bitmap gate exact source inverse drift'
source=p.read_text()
(C/'reference.sv').write_text(original.replace('module workstation_ae350_pcm_owner','module pcm_owner_window_reference',1))
(C/'variant.sv').write_text(source)
(C/'proposal.patch').write_text(''.join(difflib.unified_diff(original.splitlines(True),source.splitlines(True),fromfile='before.sv',tofile='after.sv')))
bench=whole.bench()
anchor="arm(1);"
assert bench.count(anchor)==1
directed="""arm(1);write('h800,32'h1234abcd,0);
@(negedge clk);ctx_ready=0;repeat(3)@(negedge clk);ctx_ready=1;
@(negedge clk);rst=0;repeat(4)@(negedge clk);rst=1;repeat(4)@(negedge clk);
"""
bench=bench.replace(anchor,directed+anchor,1)
(C/'tb.sv').write_text(bench)
cases={}
for label,text in [('baseline',source),('missing_context_revoke',source.replace('else if(!physical_matches)bitmap_clear_late=1;','else if(1\'b0)bitmap_clear_late=1;',1)),('late_clear_lost',source.replace('if(bitmap_clear_late)begin','if(1\'b0)begin',1)),('commit_clear_lost',source.replace('if(accepted_commit)written[tail_slot]<=0;','if(1\'b0)written[tail_slot]<=0;',1))]:
 f=C/(label+'.sv');f.write_text(text);binary=C/(label+'.vvp')
 cmd=['iverilog','-g2012','-s','tb','-o',str(binary),str(C/'tb.sv'),str(f),str(C/'reference.sv')]
 r=subprocess.run(cmd,capture_output=True,text=True,timeout=60);(C/(label+'-compile.log')).write_text(r.stdout+r.stderr);assert r.returncode==0,r.stderr
 r=subprocess.run(['vvp',str(binary)],capture_output=True,text=True,timeout=180);log=r.stdout+r.stderr;(C/(label+'.log')).write_text(log)
 if label=='baseline':assert r.returncode==0 and 'PASS PCM window gate whole-owner' in log,log
 else:assert r.returncode!=0 and 'whole-owner cycle mismatch' in log,(label,log)
 cases[label]={'exit':r.returncode,'log':log,'source_sha256':sha(f)}
 print(label,r.returncode,log[-300:],flush=True)
assert all(sha(k)==v for k,v in inputs.items())
d=dict(schema=1,source_implementation=True,passed=True,baseline_sha256=REFERENCE_SHA256,variant_sha256=sha(C/'variant.sv'),source_inverse_exact=True,
 inputs=inputs,cases=cases,files={str(p.relative_to(C)):sha(p) for p in C.rglob('*') if p.is_file()},synthesis=False,pnr=False,hardware=False)
(C/'verification.json').write_text(json.dumps(d,indent=2)+'\n')
print('verification',sha(C/'verification.json'))
