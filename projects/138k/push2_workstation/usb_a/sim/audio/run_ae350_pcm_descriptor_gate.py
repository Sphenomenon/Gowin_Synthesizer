#!/usr/bin/env python3
"""Actual owner descriptor/reference proof, including every prefix/hole pair."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

import run_ae350_pcm_window_gate as whole

ROOT=whole.ROOT
SOURCE=whole.SOURCE
REFERENCE=Path(__file__).with_name('fixtures')/'workstation_ae350_pcm_owner_before_descriptor_mask.sv'
REFERENCE_SHA256='e1823ee42fb94a2bf2f1d8600881a0c401b95853766778878cecee13556adf2e'


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def require(ok,message):
    if not ok:raise ValueError('PCM descriptor gate regression: '+message)


def descriptor_bench(cycle_bench):
    instance=re.search(r'pcm_owner_window_reference\s*#\(.*?\)\s+old_owner\s*\(.*?\);',cycle_bench,re.S)
    require(instance is not None,'whole-owner reference instance changed')
    extra=instance[0]+r'''
integer mask_vectors=0,hole_vectors=0,permission_vectors=0;
reg [31:0] random_state=32'h98451b63;
task check_descriptor(input [31:0] count,input [127:0] bitmap);begin
 dut.staged_frames=count;old_owner.staged_frames=count;
 dut.written[0]=bitmap;old_owner.written[0]=bitmap;#1;
 if(dut.required_mask !== old_owner.required_mask)
  $fatal(1,"descriptor reference mismatch: mask count=%h",count);
 if(dut.command_error !== old_owner.command_error || err !== old_owner.response_error_o)
  $fatal(1,"descriptor reference mismatch: acceptance count=%h bitmap=%h",count,bitmap);
 mask_vectors=mask_vectors+1;
end endtask
task check_permission;begin
 #1;
 if(dut.key_matches !== old_owner.key_matches || dut.live_matches !== old_owner.live_matches ||
    dut.physical_matches !== old_owner.physical_matches || left !== old_owner.pcm_left_o ||
    right !== old_owner.pcm_right_o)
  $fatal(1,"descriptor reference mismatch: real-time permission");
 permission_vectors=permission_vectors+1;
end endtask
'''
    body=r'''
arm(1);@(negedge clk);cv=0;cw=1;ca='h040;cd=2;
// Exhaust all low sixteen-bit counts, then the high-bit and wrap boundaries.
for(i=0;i<65536;i=i+1)check_descriptor(32'(i),~128'd0);
for(i=0;i<32;i=i+1)begin
 check_descriptor(32'd1<<i,~128'd0);check_descriptor(~(32'd1<<i),~128'd0);
end
check_descriptor(32'hffffff80,0);check_descriptor(32'hffffff81,~128'd0);
check_descriptor(32'hffffffff,~128'd0);
// Every legal count against every single missing bit: required holes reject,
// holes beyond the prefix remain legal. All-zero and complete blocks too.
for(i=1;i<=128;i=i+1)begin
 check_descriptor(32'(i),0);check_descriptor(32'(i),~128'd0);
 for(j=0;j<128;j=j+1)begin
  check_descriptor(32'(i),~(128'd1<<j));hole_vectors=hole_vectors+1;
 end
end
for(i=0;i<32768;i=i+1)begin
 random_state={random_state[30:0],random_state[31]^random_state[21]^random_state[1]^random_state[0]};
 check_descriptor(random_state,{random_state,~random_state,random_state^32'h548a1b2c,random_state});
end
// Direct one-bit mismatch coverage in every permission/key word. Both whole
// owners see each probe; no reachability or pipeline claim is made.
for(i=0;i<32;i=i+1)begin
 ce=32'd11^(32'd1<<i);check_permission();ce=11;
 tg=32'd22^(32'd1<<i);check_permission();tg=22;
 pe=32'd7^(32'd1<<i);check_permission();pe=7;
 dut.staged_controller=32'd11^(32'd1<<i);old_owner.staged_controller=dut.staged_controller;
 check_permission();dut.staged_controller=11;old_owner.staged_controller=11;
 dut.staged_generation=32'd22^(32'd1<<i);old_owner.staged_generation=dut.staged_generation;
 check_permission();dut.staged_generation=22;old_owner.staged_generation=22;
 dut.staged_stream=32'd1^(32'd1<<i);old_owner.staged_stream=dut.staged_stream;
 check_permission();dut.staged_stream=1;old_owner.staged_stream=1;
 dut.staged_rate=32'd48000^(32'd1<<i);old_owner.staged_rate=dut.staged_rate;
 check_permission();dut.staged_rate=48000;old_owner.staged_rate=48000;
 dut.staged_physical=32'd7^(32'd1<<i);old_owner.staged_physical=dut.staged_physical;
 check_permission();dut.staged_physical=7;old_owner.staged_physical=7;
end
if(mask_vectors!=115011 || hole_vectors!=16384 || permission_vectors!=256)
 $fatal(1,"descriptor coverage changed %d/%d/%d",mask_vectors,hole_vectors,permission_vectors);
$display("PASS descriptor mask/reference: vectors=%0d legal_prefix_holes=%0d permission_mismatches=%0d",mask_vectors,hole_vectors,permission_vectors);
$finish;
'''
    return '`timescale 1ns/1ps\n'+whole.BASE.replace('EXTRA',extra).replace('BODY',body).replace('@PREFILL@','4').replace('MAXTIME','2000000')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();out=a.output.resolve();require(not out.exists(),'new output required');out.mkdir(parents=True)
    require(sha(REFERENCE)==REFERENCE_SHA256,'frozen W8 owner changed')
    inputs={str(path):sha(path) for path in (SOURCE,REFERENCE,Path(__file__).resolve(),
        Path(whole.__file__).resolve(),ROOT/'sim/test_ae350_pcm_owner.py')}
    (out/'reference.sv').write_text(REFERENCE.read_text().replace('module workstation_ae350_pcm_owner','module pcm_owner_window_reference',1))
    whole.STATE += ['required_mask','key_matches','live_matches','physical_matches']
    cycle_bench=whole.bench()
    (out/'cycles.sv').write_text(cycle_bench);(out/'descriptor.sv').write_text(descriptor_bench(cycle_bench))
    original=SOURCE.read_text()
    physical_comparison_variants=[
        ('!(|(active_physical^physical_epoch_i))','!(|(active_physical|physical_epoch_i))'),
        ('!(|(active_physical[7:0]^physical_epoch_i[7:0]))',
            '!(|(active_physical[7:0]|physical_epoch_i[7:0]))'),
    ]
    physical_comparison_matches=[mutation for mutation in physical_comparison_variants if mutation[0] in original]
    require(len(physical_comparison_matches)==1 and original.count(physical_comparison_matches[0][0])==1,
        'physical comparison negative requires one unique whole-word or low-byte anchor')
    mutations={
        'threshold_off_by_one':("staged_frames[7:0]>8'(frame_bit)","staged_frames[7:0]>=8'(frame_bit)"),
        'missing_frame_and_reduction':('descriptor_missing_frames=|(~written[tail_slot]&required_mask)',
            'descriptor_missing_frames=&(~written[tail_slot]&required_mask)'),
        'high_count_alias':('descriptor_frames_valid=staged_frames>=32\'d1 && staged_frames<=32\'d128',
            'descriptor_frames_valid=staged_frames[7:0]>=8\'d1 && staged_frames[7:0]<=8\'d128'),
        'wrong_physical_compare':physical_comparison_matches[0],
    }
    result=dict(schema=1,passed=False,input_sha256=inputs,reference_sha256=REFERENCE_SHA256,cases={},
        physical_comparison_negative_anchor=physical_comparison_matches[0][0],
        hardware_tested=False,physical_timing_verified=False,PNR=False)
    try:
        for name,mutation,bench in [('whole_owner',None,'cycles'),('descriptor',None,'descriptor'),
                *((key,value,'descriptor') for key,value in mutations.items())]:
            text=original
            if mutation:
                before,after=mutation;require(text.count(before)==1,'negative anchor drift: '+name);text=text.replace(before,after,1)
            source=out/(name+'_source.sv');source.write_text(text)
            command=['iverilog','-g2012','-s','tb','-o',str(out/name),str(out/(bench+'.sv')),str(source),str(out/'reference.sv')]
            r=subprocess.run(command,capture_output=True,text=True,timeout=60)
            (out/(name+'_compile.log')).write_text(r.stdout+r.stderr);require(r.returncode==0,'compile failed: '+name)
            r=subprocess.run(['vvp',str(out/name)],capture_output=True,text=True,timeout=180)
            log=r.stdout+r.stderr;(out/(name+'.log')).write_text(log)
            if mutation:require(r.returncode!=0 and 'descriptor reference mismatch' in log,'negative escaped/wrong oracle: '+name)
            else:require(r.returncode==0 and ('PASS PCM window gate whole-owner' in log or 'PASS descriptor mask/reference:' in log),'reference mismatch: '+name+' '+log)
            result['cases'][name]=dict(returncode=r.returncode,negative_rejected=bool(mutation),log=log,
                log_sha256=sha(out/(name+'.log')))
        require({str(path):sha(path) for path in map(Path,inputs)}==inputs,'source drift during proof')
        result['passed']=True
    finally:
        result['output_sha256']={str(path.relative_to(out)):sha(path) for path in out.rglob('*') if path.is_file()}
        (out/'verification.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(output=str(out),passed=True,negative_controls=len(mutations))))


if __name__=='__main__':main()
