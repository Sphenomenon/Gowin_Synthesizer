#!/usr/bin/env python3
"""Full-domain arithmetic proof plus actual old/new SV function comparisons."""
import argparse
import hashlib
import json
from pathlib import Path
import random
import re
import shutil
import struct
import subprocess
import sys
import time

import z3

ROOT=Path(__file__).resolve().parents[2]
SOURCE=ROOT/'rtl/audio/gw138k_event_workstation.sv'
REFERENCE=Path(__file__).with_name('fixtures')/'d_process_before_exact_mask.svh'
OLD_SHA='11247717c12f218bd37fe96d399cc6a6e1ae6b7aa6228388bd3c9a6d414742e2'
NEW_SHA='3c64039789e097306086e3bb015dc1cd2ec08027bfb2c646d3670d559433dbf5'
THRESHOLDS=(10,21,31,42,52,63,74,84,95,105,116,126)


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def require(ok,message):
    if not ok:raise ValueError('D arithmetic proof: '+message)


def function(text,name):
    matches=re.findall(r'  function automatic signed \[31:0\] '+name+r'\(.*?  endfunction',text,re.S)
    require(len(matches)==1,'function extraction drift: '+name)
    return matches[0]


def prove_arithmetic():
    x=z3.BitVec('x',32);c=z3.BitVec('crush',7);d=z3.BitVec('drive',7);p=z3.BitVec('amplified',64)
    xx=z3.SignExt(32,x);cc=z3.ZeroExt(25,c);dd=z3.ZeroExt(57,d)
    shift=z3.If(c==0,z3.BitVecVal(0,32),16+z3.UDiv(cc*12,127))
    bits=[]
    for bit in range(32):
        keep=c==0 if bit<16 else z3.Or(c==0,z3.ULE(c,THRESHOLDS[bit-16])) if bit<28 else z3.BoolVal(True)
        bits.append(z3.If(keep,z3.Extract(bit,bit,x),z3.BitVecVal(0,1)))
    old_sat=z3.If(p>2147483647,z3.BitVecVal(0x7fffffff,32),z3.If(p< -2147483648,z3.BitVecVal(0x80000000,32),z3.Extract(31,0,p)))
    new_sat=z3.If(z3.Extract(63,31,p)==z3.SignExt(32,z3.Extract(31,31,p)),z3.Extract(31,0,p),z3.If(p<0,z3.BitVecVal(0x80000000,32),z3.BitVecVal(0x7fffffff,32)))
    comparisons=[('crush_all_32bit_clipped_7bit_control',(x>>shift)<<shift,z3.Concat(*reversed(bits)),39),
                 ('drive_all_32bit_pcm_7bit_control',(xx*(128+dd*8))>>7,(xx*(16+dd))>>4,39),
                 ('saturation_all_64bit_amplified',old_sat,new_sat,64)]
    result=[]
    for name,old,new,domain in comparisons:
        solver=z3.Solver();solver.set(timeout=20000);solver.add(old!=new);started=time.monotonic();answer=str(solver.check())
        require(answer=='unsat',name+' returned '+answer)
        result.append(dict(name=name,result=answer,input_bits=domain,seconds=time.monotonic()-started))
    return result


def old_integer(x,c,d):
    amplified=(x*(128+8*d))>>7
    clipped=max(-2147483648,min(2147483647,amplified));shift=0 if c==0 else 16+(c*12)//127
    return ((clipped>>shift)<<shift)&0xffffffff


def proposed_integer(x,c,d):
    amplified=(x*(16+d))>>4;low=amplified&0xffffffff
    signed_low=low-(1<<32) if low&(1<<31) else low
    clipped=low if signed_low==amplified else 0x80000000 if amplified<0 else 0x7fffffff
    mask=0xf0000000
    for bit in range(28):
        if c==0 or (bit>=16 and c<=THRESHOLDS[bit-16]):mask|=1<<bit
    return clipped&mask


def vectors(path):
    xs=[-2147483648,-2147483647,-268435457,-268435456,-65537,-65536,-1,0,1,65535,65536,268435455,268435456,2147483646,2147483647]
    count=clamped=0;stream_hash=hashlib.sha256()
    with path.open('w') as output:
        def add(x,c,d):
            nonlocal count
            old=old_integer(x,c,d);new=proposed_integer(x,c,d);require(old==new,'independent integer mismatch')
            stream_hash.update(struct.pack('<iBBII',x,c,d,old,new))
            output.write(f'{x&0xffffffff:08x}{c:02x}{d:02x}{old:08x}\n');count+=1
        for d in range(128):
            factor=16+d
            seeds=xs+[(2147483647*16)//factor+i for i in (-1,0,1)]+[-(2147483648*16//factor)+i for i in (-1,0,1)]
            for c in range(128):
                for seed in seeds:
                    x=max(-2147483648,min(2147483647,seed));clamped+=x!=seed;add(x,c,d)
        rng=random.Random(0xd31031)
        for _ in range(100000):add(rng.randrange(-2147483648,2147483648),rng.randrange(128),rng.randrange(128))
    require(count==444064 and clamped==256,'vector count drift')
    return dict(count=count,directed_with_duplicates=344064,random=100000,seed=0xd31031,
        clamped_outside_pcm32_boundary_seeds=clamped,all_submitted_inputs_within_declared_domain=True,
        independent_integer_comparisons=True,stream_format='<iBBII x,crush,drive,old,new',stream_sha256=stream_hash.hexdigest(),mem_sha256=sha(path))


def actual_sv(old,new,out,name,negative=False):
    # Compile the complete actual extracted functions, with no hand transcription
    # of either body's SV sizing, signedness, saturation or mask semantics.
    tb='''`timescale 1ns/1ps
module tb;
OLD
NEW
reg [79:0] cases[0:444063];
reg signed [31:0] x,expected,old_result,new_result;
reg [6:0] crush,drive;
initial begin
 $readmemh("vectors.mem",cases);
 for(integer i=0;i<444064;i=i+1)begin
  x=cases[i][79:48];crush=cases[i][46:40];drive=cases[i][38:32];expected=cases[i][31:0];
  old_result=d_process_old_reference(x,crush,drive);new_result=d_process_dut(x,crush,drive);#1;
  if(old_result!==expected)$fatal(1,"old source vs integer mismatch i=%0d",i);
  if(new_result!==old_result)$fatal(1,"D actual function mismatch i=%0d x=%h crush=%0d drive=%0d old=%h new=%h",i,x,crush,drive,old_result,new_result);
 end
 $display("PASS D actual old/new full functions: vectors=444064");$finish;
end
endmodule
'''.replace('OLD',old).replace('NEW',new.replace('d_process','d_process_dut'))
    source=out/(name+'.sv');source.write_text(tb)
    compile_argv=['iverilog','-g2012','-s','tb','-o',str(out/name),str(source)]
    p=subprocess.run(compile_argv,cwd=out,capture_output=True,text=True,timeout=60)
    (out/(name+'_compile.log')).write_text(p.stdout+p.stderr);require(p.returncode==0,'actual SV compile failed: '+name)
    started=time.monotonic();p=subprocess.run(['vvp',str(out/name)],cwd=out,capture_output=True,text=True,timeout=180)
    log=p.stdout+p.stderr;(out/(name+'.log')).write_text(log)
    if negative:require(p.returncode!=0 and 'D actual function mismatch' in log,'negative escaped or wrong oracle: '+name)
    else:require(p.returncode==0 and 'PASS D actual old/new full functions: vectors=444064' in log,'actual SV mismatch: '+log)
    return dict(negative=negative,rejected=negative,exit_code=p.returncode,seconds=time.monotonic()-started,
        compile_argv=compile_argv,source_sha256=sha(source),log_sha256=sha(out/(name+'.log')),log=log)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    old=function(REFERENCE.read_text(),'d_process_old_reference');new=function(SOURCE.read_text(),'d_process')
    require(hashlib.sha256(old.replace('d_process_old_reference','d_process').encode()).hexdigest()==OLD_SHA,'frozen W9b reference drift')
    require(hashlib.sha256(new.encode()).hexdigest()==NEW_SHA,'new expression drift; review and re-prove before changing seal')
    input_paths=[SOURCE,REFERENCE,Path(__file__).resolve(),Path(sys.executable).resolve(),Path(z3.__file__).resolve(),
        Path(z3.__file__).parent/'z3.py',Path(z3.__file__).parent/'z3core.py']
    input_paths+=list((Path(z3.__file__).parent/'lib').glob('libz3*.dylib'))
    input_paths+=[Path(shutil.which(x)).resolve() for x in ('iverilog','vvp')]
    inputs={str(p):sha(p) for p in input_paths}
    report=dict(schema=1,passed=False,input_sha256=inputs,old_function_sha256=OLD_SHA,new_function_sha256=NEW_SHA,
        z3_version=z3.get_full_version(),python_version=sys.version,scope='composable full-domain SMT and actual complete old/new SV functions against independent integer reference',
        hardware_accepted=False,physical_timing_verified=False,synthesis_verified=False,added_sample_cycles=0,cases={})
    try:
        report['smt']=prove_arithmetic();report['vectors']=vectors(out/'vectors.mem')
        report['cases']['actual_functions']=actual_sv(old,new,out,'actual_functions')
        mutations={'threshold_off_by_one':("crush<=7'd10,16'd0","crush<=7'd11,16'd0"),
            'crush_zero_bypass_removed':("if(crush==0)keep_mask=32'hffffffff;","if(crush==1)keep_mask=32'hffffffff;"),
            'drive_factor_off_by_one':("8'(16+int'(drive))","8'(17+int'(drive))"),
            'positive_saturation_off_by_one':("32'sh7fffffff","32'sh7ffffffe")}
        for name,(before,after) in mutations.items():
            require(new.count(before)==1,'mutation anchor drift: '+name)
            report['cases'][name]=actual_sv(old,new.replace(before,after),out,name,negative=True)
        require(inputs=={str(p):sha(p) for p in input_paths},'source/tool drift during proof')
        report['passed']=True
    finally:
        (out/'verification.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(dict(output=str(out),passed=True,vectors=report['vectors']['count'],smt=len(report['smt']),actual_sv_negative_controls=4)))


if __name__=='__main__':main()
