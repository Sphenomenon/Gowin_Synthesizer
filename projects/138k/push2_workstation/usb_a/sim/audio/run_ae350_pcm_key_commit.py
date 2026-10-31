#!/usr/bin/env python3
"""Validate the combined kept PCM key groups and local rejected-COMMIT gate."""
from pathlib import Path
import argparse,hashlib,json,re,subprocess,sys
import z3
root=Path(__file__).resolve().parents[2]
ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--reference',type=Path,required=True,help='Exact W12 consumed owner source');ap.add_argument('--output',type=Path,required=True)
args=ap.parse_args();base=args.output.resolve();assert not base.is_relative_to(root),'external evidence directory required';base.mkdir(parents=True,exist_ok=False)
SOURCE=root/'rtl/audio/workstation_ae350_pcm_owner.sv'
sys.path.insert(0,str(root/'sim/audio'));import run_ae350_pcm_window_gate as whole
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
reference=args.reference.resolve();assert sha(reference)=='3342a94cfd4e103efbb11808c5753aa8839069634ebf5d78ed80c0dab9cff837','exact W12 reference drift'
old=reference.read_text();frozen_source_sha256=sha(SOURCE)
for name in ['key_groups','local_commit_rejection']:
 d=base/name;d.mkdir();(d/'reference.sv').write_text(old.replace('module workstation_ae350_pcm_owner','module pcm_owner_window_reference',1));(d/'variant.sv').write_text(SOURCE.read_text())
def record():return dict(schema=1,passed=False,scope='combined production owner against exact W12, full-cycle twin plus source-bound logical proofs and actual owner four-state',reference_sha256=sha(reference),source_sha256=sha(SOURCE),input_sha256={str(p):sha(p)for p in [SOURCE,reference,Path(__file__),Path(whole.__file__),root/'sim/test_ae350_pcm_owner.py']},hardware_accepted=False,physical_timing_verified=False,resource_saving_claimed=False)
inst=re.search(r'pcm_owner_window_reference\s*#\(.*?\)\s+old_owner\s*\(.*?\);',whole.bench(),re.S).group()
def run(d,label,text,tb,want=True):
 source=d/(label+'.sv');source.write_text(text);tp=d/(label+'-tb.sv');tp.write_text(tb);binary=d/(label+'.vvp')
 c=subprocess.run(['iverilog','-g2012','-s','tb','-o',str(binary),str(tp),str(source),str(d/'reference.sv')],capture_output=True,text=True,timeout=60);(d/(label+'-compile.log')).write_text(c.stdout+c.stderr);assert c.returncode==0,c.stderr
 r=subprocess.run(['vvp',str(binary)],capture_output=True,text=True,timeout=120);(d/(label+'-run.log')).write_text(r.stdout+r.stderr)
 assert (r.returncode==0 and 'PASS' in r.stdout) if want else (r.returncode!=0 and 'proposal mismatch' in r.stdout),r.stdout+r.stderr
 return dict(exit_code=r.returncode,expected_rejection=not want,log=r.stdout,source_sha256=sha(source),fixture_sha256=sha(tp))
def fixture(extra,body):
 return '`timescale 1ns/1ps\n'+whole.BASE.replace('EXTRA',inst+'\n'+extra).replace('BODY',body).replace('@PREFILL@','4').replace('MAXTIME','2000000').replace('always #5 clk=~clk;','').replace('#21;rst=1;cpu=1;repeat(4)@(negedge clk);','#1;rst=1;cpu=1;')
def check(v,wanted=z3.unsat):
 s=z3.Solver();s.add(v);r=s.check();assert r==wanted,str(s.model());return dict(result=str(r),counterexample=str(s.model())if r==z3.sat else None)
def symbol(v):return(v==0,v==1)
def invert(v):return(v[1],v[0])
def AND(vs):return(z3.Or([v[0]for v in vs]),z3.And([v[1]for v in vs]))
def OR(vs):return(z3.And([v[0]for v in vs]),z3.Or([v[1]for v in vs]))
def XOR(a,b):return(z3.Or(z3.And(a[0],b[0]),z3.And(a[1],b[1])),z3.Or(z3.And(a[0],b[1]),z3.And(a[1],b[0])))
def different(a,b):return z3.Or(a[0]!=b[0],a[1]!=b[1])
# Proposal 1: exact source guard plus five independent comparator proofs.
d=base/'key_groups';text=(d/'variant.sv').read_text();v=record();v['whole_owner']=run(d,'whole_owner',text,whole.bench())
start=old.index('    // Express equality as an XOR mismatch reduction');end=old.index('    wire live_matches=',start)
ns=text.index('    // Preserve independent eight-bit key');ne=text.index('    wire live_matches=',ns)
local_added="\n    // The rejected COMMIT state update must not traverse unrelated response decodes.\n    wire rejected_commit=write_command && command_address_i==12'h040 && command_data_i==32'd2 &&\n        (!control_format_ok || !control_id_ok || commit_error);"
local_new='if(rejected_commit && usable && key_matches && !owned[tail_slot])begin'
local_old="if(write_command && response_error_o && command_address_i==12'h040 && command_data_i==2 &&\n                usable && key_matches && !owned[tail_slot])begin"
without_local=text.replace(local_added,'',1).replace(local_new,local_old,1)
assert without_local[:ns]==old[:start] and without_local[ne:]==old[end:],'outside approved key/local guard boundaries changed'
block=text[ns:ne];names=['controller','generation','stream','rate','physical'];binary=[];four=[]
for name in names:
 a,b=z3.BitVecs(name+'_staged '+name+'_active',32);groups=[]
 for p in range(4):
  hi=8*p+7;lo=8*p;n=f'key_{name}_match_{p}'
  assert f'wire {n} /* synthesis syn_keep=1 */;' in block
  assert f'assign {n}=!(|(staged_{name}[{hi}:{lo}]^active_{name}[{hi}:{lo}]));' in block
  groups.append(z3.Extract(hi,lo,a)==z3.Extract(hi,lo,b))
 binary.append(check((a==b)!=z3.And(groups)))
 aa=[z3.BitVec(name+'_a4_'+str(i),2)for i in range(32)];bb=[z3.BitVec(name+'_b4_'+str(i),2)for i in range(32)]
 differences=[XOR(symbol(x),symbol(y))for x,y in zip(aa,bb)]
 four.append(check(different(invert(OR(differences)),AND([invert(OR(differences[p*8:p*8+8]))for p in range(4)]))))
assert re.sub(r'\s+','',re.search(r'wire key_matches=(.*?);',block,re.S).group(1))=='&&'.join(f'key_{name}_match_{p}'for name in names for p in range(4))
extra='reg [31:0] a[0:4],b[0:4];integer k,p,q,checks=0;\nfunction four(input integer code);case(code)0:four=0;1:four=1;2:four=1\'bx;3:four=1\'bz;endcase endfunction\n'
extra+='task compare;begin #1;if(dut.key_matches!==old_owner.key_matches)$fatal(1,"proposal mismatch key four-state bit=%0d",checks);checks=checks+1;end endtask\n'
extra+=''.join(f'wire [31:0] force_a{n}=a[{n}],force_b{n}=b[{n}];\n'for n in range(5))
body=''
for n,name in enumerate(names):
 for unit in ['dut','old_owner']:body+=f'force {unit}.staged_{name}=force_a{n};force {unit}.active_{name}=force_b{n};\n'
body+='''for(p=0;p<5;p=p+1)for(k=0;k<32;k=k+1)for(i=0;i<4;i=i+1)for(j=0;j<4;j=j+1)begin
 for(q=0;q<5;q=q+1)begin a[q]=0;b[q]=0;end
 a[p][k]=four(i);b[p][k]=four(j);compare();a[(p+1)%5][(k+8)%32]=1;compare();end
if(checks!=5120)$fatal(1,"key coverage");$display("PASS actual complete owner key four-state checks=%0d",checks);$finish;'''
tb=fixture(extra,body);v['actual_owner_four_state']=run(d,'four_state',text,tb)
v['source_bound_proof']=dict(binary_five_64bit_comparators=binary,four_state_five_128_symbol_bit_comparators=four,all_twenty_kept_slices_and_AND_audited=True,outside_boundary_unchanged=True)
v['negative_controls']={}
for label,before,after in [('missing_bit31','staged_controller[31:24]^active_controller[31:24]','staged_controller[30:23]^active_controller[31:24]'),('final_OR','key_physical_match_2 && key_physical_match_3','key_physical_match_2 || key_physical_match_3')]:
 assert text.count(before)==1;v['negative_controls'][label]=run(d,label,text.replace(before,after,1),tb,False)
v['passed']=True;v['validation_runner_sha256']=sha(Path(__file__));v['output_sha256']={str(p.relative_to(d)):sha(p)for p in d.iterdir()if p.is_file()and p.name!='verification.json'};(d/'verification.json').write_text(json.dumps(v,indent=2)+'\n')
# Proposal 2: literal local guard, no response output or other statement change.
d=base/'local_commit_rejection';text=(d/'variant.sv').read_text();v=record();v['whole_owner']=run(d,'whole_owner',text,whole.bench())
added="\n    // The rejected COMMIT state update must not traverse unrelated response decodes.\n    wire rejected_commit=write_command && command_address_i==12'h040 && command_data_i==32'd2 &&\n        (!control_format_ok || !control_id_ok || commit_error);"
newcondition='if(rejected_commit && usable && key_matches && !owned[tail_slot])begin'
oldcondition="if(write_command && response_error_o && command_address_i==12'h040 && command_data_i==2 &&\n                usable && key_matches && !owned[tail_slot])begin"
assert text.count(added)==1 and text.count(newcondition)==1
key_start=text.index('    // Preserve independent eight-bit key');key_end=text.index('    wire live_matches=',key_start)
original_start=old.index('    // Express equality as an XOR mismatch reduction');original_end=old.index('    wire live_matches=',original_start)
without_key=text[:key_start]+old[original_start:original_end]+text[key_end:]
assert without_key.replace(added,'',1).replace(newcondition,oldcondition,1)==old,'outside approved key/local guard boundaries changed'
# Full binary decoder is the same source-bound case tree as the maintained
# owner: every independent operation error remains arbitrary.
address=z3.BitVec('address',12);data=z3.BitVec('data',32);strobes=z3.BitVec('strobes',4)
accepted,writing,saturated,window_error,usable,key,owned,*errors=z3.Bools('accepted writing saturated window_error usable key owned e1 e2 e3 e4 e5')
full=z3.And(strobes==15,z3.Extract(1,0,address)==0);upper=z3.Extract(11,11,address)==1
stage=z3.And(z3.UGE(address,0x020),z3.ULE(address,0x03c))
cmd_error=z3.Or(saturated,z3.If(data==1,errors[0],z3.If(data==2,errors[1],z3.If(data==3,errors[2],z3.If(data==4,errors[3],z3.If(data==5,errors[4],True))))))
response=z3.If(writing,z3.If(z3.Not(full),True,z3.If(upper,window_error,z3.If(stage,False,z3.If(address==0x040,cmd_error,True)))),z3.Extract(1,0,address)!=0)
oldguard=z3.And(accepted,writing,response,address==0x040,data==2,usable,key,z3.Not(owned))
newguard=z3.And(accepted,writing,address==0x040,data==2,z3.Or(z3.Not(full),saturated,errors[1]),usable,key,z3.Not(owned))
v['binary_all_command_and_arbitrary_error_states']=check(oldguard!=newguard)
# Three-valued logical results (both X and Z map to unknown for reductions).
# Keep original procedural if(!full_write), if(&command_id) behavior exactly.
f,s,e=[z3.BitVec(n,2)for n in ['full4','saturation4','commit_error4']]
F,S,E=map(symbol,[f,s,e]);old_error=(z3.If(F[0],False,z3.If(S[1],False,E[0])),z3.If(F[0],True,z3.If(S[1],True,E[1])))
format_ok=(F[0],z3.Not(F[0]));id_ok=(S[1],z3.Not(S[1]));new_error=OR([invert(format_ok),invert(id_ok),E])
v['four_state_procedural_control_context_all_symbols']=check(different(old_error,new_error))
extra=r'''
reg probe_error=0,probe_usable=1,probe_key=1;reg [3:0] probe_owned=0;reg [31:0] probe_id=0;
integer k,p,q,checks=0;reg [31:0] rng=32'h38ac702b;
function four(input integer code);case(code&3)0:four=0;1:four=1;2:four=1'bx;3:four=1'bz;endcase endfunction
function random4();begin rng=(rng>>1)^((rng&1)?32'h80200003:0);random4=four(rng[1:0]);end endfunction
wire old_terminate=old_owner.write_command && old_owner.response_error_o && old_owner.command_address_i==12'h040 && old_owner.command_data_i==2 && old_owner.usable && old_owner.key_matches && !old_owner.owned[old_owner.tail_slot];
wire new_terminate=dut.rejected_commit && dut.usable && dut.key_matches && !dut.owned[dut.tail_slot];
task compare;begin #1;
 if((old_terminate===1'b1)!=(new_terminate===1'b1))$fatal(1,"proposal mismatch rejected commit update vector=%0d",checks);
 if(cv===1'b1 && cw===1'b1 && ca===12'h040 && cd===32'd2 && dut.rejected_commit!==(old_owner.write_command && old_owner.response_error_o && old_owner.command_address_i==12'h040 && old_owner.command_data_i==2))
  $fatal(1,"proposal mismatch rejected commit process semantics vector=%0d",checks);
 checks=checks+1;end endtask
'''
body=''
for unit in ['dut','old_owner']:body+=f'force {unit}.commit_error=probe_error;force {unit}.usable=probe_usable;force {unit}.key_matches=probe_key;force {unit}.owned=probe_owned;force {unit}.tail_slot=0;force {unit}.command_id=probe_id;\n'
body+=r'''
ca='h040;cd=2;
for(k=0;k<65536;k=k+1)begin
 for(p=0;p<4;p=p+1)cs[p]=four(k>>(2*p));cv=four(k>>8);cw=four(k>>10);probe_error=four(k>>12);
 case((k>>14)&3)0:probe_id=0;1:probe_id=32'hffffffff;2:probe_id=32'hfffffffx;3:probe_id=32'hfffffffz;endcase
 probe_usable=1;probe_key=1;probe_owned=0;compare();end
for(k=0;k<32768;k=k+1)begin
 for(p=0;p<12;p=p+1)ca[p]=random4();for(p=0;p<32;p=p+1)cd[p]=random4();
 for(p=0;p<4;p=p+1)begin cs[p]=random4();probe_owned[p]=random4();end
 cv=random4();cw=random4();probe_error=random4();probe_usable=random4();probe_key=random4();
 for(p=0;p<32;p=p+1)probe_id[p]=random4();compare();end
if(checks!=98304)$fatal(1,"local guard coverage");$display("PASS actual complete owner rejection four-state checks=%0d",checks);$finish;
'''
tb=fixture(extra,body);v['actual_owner_four_state']=run(d,'four_state',text,tb)
v['negative_controls']={}
for label,before,after in [('missing_format','!control_format_ok || !control_id_ok || commit_error','!control_id_ok || commit_error'),('missing_id','!control_format_ok || !control_id_ok || commit_error','!control_format_ok || commit_error'),('logical_format_unknown_semantics','!control_format_ok || !control_id_ok || commit_error','!full_write || !control_id_ok || commit_error')]:
 assert text.count(before)==1;v['negative_controls'][label]=run(d,label,text.replace(before,after,1),tb,False)
v['outside_boundary_unchanged']=True;v['passed']=True;v['validation_runner_sha256']=sha(Path(__file__));v['output_sha256']={str(p.relative_to(d)):sha(p)for p in d.iterdir()if p.is_file()and p.name!='verification.json'};(d/'verification.json').write_text(json.dumps(v,indent=2)+'\n')
assert sha(SOURCE)==frozen_source_sha256,'production source drift'
summary=record();summary['passed']=True;summary['combined_source_unchanged']=True;summary['case_verification']={n:dict(path=str(base/n/'verification.json'),sha256=sha(base/n/'verification.json'))for n in ['key_groups','local_commit_rejection']};summary['evidence_sha256']={str(p.relative_to(base)):sha(p)for p in base.rglob('*')if p.is_file()and p.suffix in ('.sv','.json','.log')};(base/'verification.json').write_text(json.dumps(summary,indent=2)+'\n')
print('PASS combined production PCM owner, complete-owner W12 twins, source-bound binary/four-state proofs, actual-owner four-state and five negatives')
