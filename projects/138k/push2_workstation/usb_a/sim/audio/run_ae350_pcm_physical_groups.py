#!/usr/bin/env python3
"""Verify only the four kept physical-epoch comparator groups in the PCM owner."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import z3


ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'sim'))
from test_ae350_pcm_owner import BASE
SOURCE=ROOT/'rtl/audio/workstation_ae350_pcm_owner.sv'
OLD_SHA='a28f84ee8ba95e8aa0a3ea7faf764f9c5cbcaf40dc25e13f17f01871ce5645ae'
OLD="""    wire physical_matches=context_ready_i && !(|(active_physical^physical_epoch_i)) &&
"""
GROUPS="""    // Keep four independent epoch comparisons so synthesis cannot rebuild the
    // full 32-bit serial inequality chain on the PCM permission path.
    wire physical_epoch_match_0 /* synthesis syn_keep=1 */;
    wire physical_epoch_match_1 /* synthesis syn_keep=1 */;
    wire physical_epoch_match_2 /* synthesis syn_keep=1 */;
    wire physical_epoch_match_3 /* synthesis syn_keep=1 */;
    assign physical_epoch_match_0=!(|(active_physical[7:0]^physical_epoch_i[7:0]));
    assign physical_epoch_match_1=!(|(active_physical[15:8]^physical_epoch_i[15:8]));
    assign physical_epoch_match_2=!(|(active_physical[23:16]^physical_epoch_i[23:16]));
    assign physical_epoch_match_3=!(|(active_physical[31:24]^physical_epoch_i[31:24]));
    wire physical_matches=context_ready_i && physical_epoch_match_0 && physical_epoch_match_1 &&
        physical_epoch_match_2 && physical_epoch_match_3 &&
"""


def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def require(ok,message):
    if not ok:raise ValueError('PCM physical groups: '+message)


def source_guard(text):
    require(text.count(GROUPS)==1,'exact four slices/kept scalar groups/final AND changed')
    old=text.replace(GROUPS,OLD,1)
    require(hashlib.sha256(old.encode()).hexdigest()==OLD_SHA,'change outside approved comparison boundary')


def proof():
    a,b=z3.BitVecs('physical_active physical_input',32)
    slices=[(7,0),(15,8),(23,16),(31,24)]
    groups=[z3.Extract(hi,lo,a)==z3.Extract(hi,lo,b) for hi,lo in slices]
    def check(statement,wanted):
        s=z3.Solver();s.add(statement);result=s.check()
        require(result==wanted,'symbolic comparator result '+str(result))
        return dict(result=str(result),counterexample=str(s.model()) if result==z3.sat else None)
    result=dict(binary_all_64_input_bits=check((a==b)!=z3.And(groups),z3.unsat))
    # Two-bit symbols encode 0,1,X,Z. Operations use the Verilog known-value
    # dominance rules; X and Z both produce an unknown result in bitwise XOR.
    aa=[z3.BitVec('a4_'+str(i),2) for i in range(32)]
    bb=[z3.BitVec('b4_'+str(i),2) for i in range(32)]
    def bit(v):return (v==0,v==1)
    def xor(x,y):return (z3.Or(z3.And(x[0],y[0]),z3.And(x[1],y[1])),z3.Or(z3.And(x[0],y[1]),z3.And(x[1],y[0])))
    def red_or(xs):return (z3.And([x[0] for x in xs]),z3.Or([x[1] for x in xs]))
    def red_and(xs):return (z3.Or([x[0] for x in xs]),z3.And([x[1] for x in xs]))
    def invert(x):return (x[1],x[0])
    differences=[xor(bit(x),bit(y)) for x,y in zip(aa,bb)]
    old=invert(red_or(differences))
    new=red_and([invert(red_or(differences[lo:hi+1])) for hi,lo in slices])
    result['four_state_all_128_symbol_bits']=check(z3.Or(old[0]!=new[0],old[1]!=new[1]),z3.unsat)
    result['binary_negative_missing_bit31']=check((a==b)!=z3.And(groups[:3]+[z3.Extract(30,24,a)==z3.Extract(30,24,b)]),z3.sat)
    result['binary_negative_group_OR']=check((a==b)!=z3.Or(groups),z3.sat)
    result['z3_version']=z3.get_version_string()
    return result


def bench():
    extra=r'''
reg [31:0] probe_active=0,probe_rate=48000;
reg expected_physical;
integer comparisons=0,k,l,m,n;
function four(input integer code);begin
 case(code)0:four=0;1:four=1;2:four=1'bx;3:four=1'bz;endcase
end endfunction
task compare_physical;begin
 #1;
 expected_physical=ctx_ready && !(|(probe_active^pe)) &&
     probe_rate==(rate44 ? 32'd44100:32'd48000) && !sw;
 if(dut.physical_matches!==expected_physical)
  $fatal(1,"physical comparator four-state mismatch a=%h b=%h",probe_active,pe);
 comparisons=comparisons+1;
end endtask
'''
    body=r'''
force dut.active_physical=probe_active;force dut.active_rate=probe_rate;
for(i=0;i<32;i=i+1)for(j=0;j<4;j=j+1)for(k=0;k<4;k=k+1)begin
 probe_active=0;pe=0;probe_active[i]=four(j);pe[i]=four(k);compare_physical();
 // A definite mismatch in another group must dominate an unknown input.
 probe_active[(i+8)%32]=1;compare_physical();
end
for(i=0;i<4;i=i+1)for(j=0;j<4;j=j+1)for(k=0;k<4;k=k+1)for(l=0;l<4;l=l+1)begin
 ctx_ready=four(i);sw=four(j);rate44=four(k);
 case(l)0:probe_rate=48000;1:probe_rate=44100;2:probe_rate=32'hxxxxxxxx;3:probe_rate=32'hzzzzzzzz;endcase
 probe_active=32'h8294c130;pe=probe_active;compare_physical();
 probe_active[31]=1'bx;compare_physical();
end
if(comparisons!=1536)$fatal(1,"physical comparator probe coverage");
$display("PASS actual owner physical comparison four-state vectors=%0d",comparisons);
$finish;
'''
    return '`timescale 1ns/1ps\n'+BASE.replace('EXTRA',extra).replace('BODY',body).replace('@PREFILL@','4').replace('MAXTIME','100000')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    inputs={str(p):sha(p) for p in (SOURCE,Path(__file__).resolve(),ROOT/'sim/test_ae350_pcm_owner.py')}
    text=SOURCE.read_text();source_guard(text)
    mutations={
        'missing_high_slice_bit':('[31:24]^physical_epoch_i[31:24]','[30:23]^physical_epoch_i[31:24]'),
        'final_OR':('physical_epoch_match_2 && physical_epoch_match_3','physical_epoch_match_2 || physical_epoch_match_3'),
        'missing_keep':('wire physical_epoch_match_0 /* synthesis syn_keep=1 */;','wire physical_epoch_match_0;'),
        'outside_boundary_rate_change':('active_rate==(rate_44100_i','active_rate!=(rate_44100_i')}
    result=dict(schema=1,passed=False,input_sha256=inputs,original_source_sha256=OLD_SHA,
        proof=proof(),source_negatives={},hardware_tested=False,physical_timing_verified=False)
    try:
        for name,(old,new) in mutations.items():
            require(text.count(old)==1,'negative anchor drift '+name)
            mutated=text.replace(old,new,1)
            try:source_guard(mutated)
            except ValueError as e:result['source_negatives'][name]=dict(rejected=True,reason=str(e))
            else:raise ValueError('source guard negative survived '+name)
        (out/'tb.sv').write_text(bench())
        c=subprocess.run(['iverilog','-g2012','-s','tb','-o',str(out/'tb.vvp'),str(out/'tb.sv'),str(SOURCE)],capture_output=True,text=True,timeout=60)
        (out/'compile.log').write_text(c.stdout+c.stderr);require(c.returncode==0,'actual owner compile '+c.stderr)
        r=subprocess.run(['vvp',str(out/'tb.vvp')],capture_output=True,text=True,timeout=60)
        (out/'simulation.log').write_text(r.stdout+r.stderr)
        require(r.returncode==0 and 'PASS actual owner physical comparison four-state vectors=1536' in r.stdout,'actual owner four-state simulation '+r.stdout+r.stderr)
        require(inputs=={str(p):sha(p) for p in map(Path,inputs)},'source drift')
        result['simulation']=dict(exit_code=r.returncode,actual_owner_vectors=1536)
        result['passed']=True
    finally:
        result['output_sha256']={str(p.relative_to(out)):sha(p) for p in out.rglob('*') if p.is_file()}
        (out/'verification.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(passed=True,output=str(out),source_negatives=len(mutations))))


if __name__=='__main__':main()
