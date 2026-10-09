#!/usr/bin/env python3
"""Independent BIST command/content oracle with lane pipeline, fault/timeout/reset cases."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
from cnn_ddr_pipeline_patch import BIST,retime_bist_expected_pattern,pipeline_bist_compare
ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'results/song_guide_full85_clk50_20261007_084539_884006_route1/Prj1'
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path);p.add_argument('--build',type=Path);a=p.parse_args()
original=(BASE/BIST).read_text();patched=pipeline_bist_compare(retime_bist_expected_pattern(original))
if a.build:
    build=a.build.resolve();metadata=json.loads((build/'build_metadata.json').read_text())
    assert metadata.get('pipelined_bist_compare') and metadata.get('retimed_bist_expected_pattern')
    assert (build/'Prj1'/BIST).read_text()==patched,'candidate BIST drift'
tb=r'''`timescale 1ns/1ps
module tb;
parameter BURSTS=31,CASE=0;
reg clk=0,rst=0;always #5 clk=~clk;
wire[1:0]valid,write,done,failed;wire[28:0]addr[0:1],first[0:1];wire[255:0]data[0:1];wire[31:0]errors[0:1];
reg[1:0]ready=0,rsp=0;reg[255:0]rdata[0:1];
bist_original #(.BURSTS(BURSTS),.TIMEOUT_CYCLES(37)) original(.clk(clk),.rst_n(rst),.req_valid(valid[0]),.req_ready(ready[0]),.req_write(write[0]),.req_addr(addr[0]),.req_wdata(data[0]),.rsp_valid(rsp[0]),.rsp_data(rdata[0]),.done(done[0]),.failed(failed[0]),.error_count(errors[0]),.first_error_addr(first[0]));
ddr3_bist #(.BURSTS(BURSTS),.TIMEOUT_CYCLES(37)) dut(.clk(clk),.rst_n(rst),.req_valid(valid[1]),.req_ready(ready[1]),.req_write(write[1]),.req_addr(addr[1]),.req_wdata(data[1]),.rsp_valid(rsp[1]),.rsp_data(rdata[1]),.done(done[1]),.failed(failed[1]),.error_count(errors[1]),.first_error_addr(first[1]));
reg[255:0]memory[0:1][0:BURSTS-1],held[0:1],stall_data[0:1];reg[28:0]stall_addr[0:1];reg[1:0]pending=0,stalled=0,stall_write=0;
integer wait_cycles[0:1],ordinal[0:1],reads[0:1],cycles=0,compares=0,epochs=0,done_at[0:1];reg[31:0]rng=32'h71855bca;
function automatic[255:0]pattern(input[28:0]address,input inv);
 reg[31:0]word_data;
 for(integer lane=0;lane<8;lane=lane+1)begin
  word_data={3'b101,address}^(32'h9e3779b9*(lane+1));pattern[lane*32+:32]=inv?~word_data:word_data;
 end
endfunction
always @(posedge clk)if(rst)begin
 for(integer d=0;d<2;d=d+1)begin
  if(stalled[d]&&!done[d]&&(!valid[d]||addr[d]!==stall_addr[d]||data[d]!==stall_data[d]||write[d]!==stall_write[d]))$fatal(1,"unstable BIST request");
  stalled[d]=valid[d]&&!ready[d];stall_addr[d]=addr[d];stall_data[d]=data[d];stall_write[d]=write[d];
  if(valid[d]&&ready[d])begin
   if(ordinal[d]>=4*BURSTS)$fatal(1,"extra BIST request");
   if(write[d] !== ((ordinal[d]/BURSTS)%2==0) || addr[d] !== 29'((ordinal[d]%BURSTS)*8) || data[d]!==pattern(29'((ordinal[d]%BURSTS)*8),ordinal[d]>=2*BURSTS))$fatal(1,"ordered BIST content mismatch d=%d cmd=%d",d,ordinal[d]);
   if(write[d])memory[d][addr[d]/8]=data[d];
   else begin
    if(pending[d])$fatal(1,"more than one read");pending[d]=1;held[d]=memory[d][addr[d]/8];
    if(CASE==1 && reads[d]==BURSTS-1)held[d][255]=!held[d][255];
    if(CASE==2)held[d][(reads[d]%8)*32+(reads[d]%32)]=!held[d][(reads[d]%8)*32+(reads[d]%32)];
    wait_cycles[d]=reads[d]%5;reads[d]=reads[d]+1;
   end
   ordinal[d]=ordinal[d]+1;compares=compares+1;
  end
  if(done[d] && done_at[d]==0)done_at[d]=cycles;
 end
end
initial begin
 for(integer epoch=0;epoch<3;epoch=epoch+1)begin
  @(negedge clk);rst=0;ready=0;rsp=0;pending=0;stalled=0;cycles=0;
  for(integer d=0;d<2;d=d+1)begin ordinal[d]=0;reads[d]=0;wait_cycles[d]=0;done_at[d]=0;rdata[d]=0;end
  repeat(4)@(negedge clk);rst=1;epochs=epochs+1;
  while(!(&done) && cycles<100000)begin
   @(negedge clk);cycles=cycles+1;rng=(rng>>1)^({32{rng[0]}}&32'h80200003);
   for(integer d=0;d<2;d=d+1)begin
    ready[d]=CASE==3?0:CASE==5?1:(rng[d]|rng[d+3]);rsp[d]=0;
    if(pending[d])begin
     if(wait_cycles[d]==0 && CASE!=4)begin rsp[d]=1;rdata[d]=held[d];pending[d]=0;end
     else if(wait_cycles[d]>0)wait_cycles[d]=wait_cycles[d]-1;
    end
   end
  end
  for(integer d=0;d<2;d=d+1)if(done_at[d]==0)done_at[d]=cycles;
  if(!(&done))$fatal(1,"BIST timeout");
  if(failed[0]!==failed[1]||errors[0]!==errors[1]||first[0]!==first[1])$fatal(1,"original/pipelined BIST final result mismatch");
  if(CASE==0||CASE==5)begin if(failed || errors[0]!=0 || ordinal[0]!=4*BURSTS || ordinal[1]!=4*BURSTS)$fatal(1,"clean pattern rejected");end
  if(CASE==1 && (failed!=3 || errors[0]!=1 || first[0]!=(BURSTS-1)*8))$fatal(1,"final-bit fault accounting");
  if(CASE==2 && (failed!=3 || errors[0]!=2*BURSTS))$fatal(1,"all lane fault accounting");
  if((CASE==3||CASE==4)&&(failed!=3||errors[0]!=1))$fatal(1,"timeout fault missing");
  #1;
  if(CASE==5 && done_at[1]-done_at[0]!=2*BURSTS)$fatal(1,"expected exactly one check cycle per read: %d",done_at[1]-done_at[0]);
 end
 $display("PASS pipelined BIST bursts=%0d case=%0d orderedcommand checks=%0d 3resetepochs final-bit/all-lane faults,timeouts,one-check-cycle-per-response",BURSTS,CASE,compares);$finish;
end
endmodule'''
checks=[]
with tempfile.TemporaryDirectory(prefix='cnn_bist_pipeline_') as tmp:
    folder=Path(tmp);(folder/'old.v').write_text(original.replace('module ddr3_bist #','module bist_original #'));(folder/'new.v').write_text(patched);(folder/'tb.sv').write_text(tb)
    for bursts in (1,31,257):
        for case in range(6):
            compile=subprocess.run(['iverilog','-g2012','-I',str(BASE),'-s','tb','-P',f'tb.BURSTS={bursts}','-P',f'tb.CASE={case}','-o',str(folder/'sim'),str(folder/'old.v'),str(folder/'new.v'),str(folder/'tb.sv')],capture_output=True,text=True)
            assert compile.returncode==0,compile.stdout+compile.stderr
            run=subprocess.run(['vvp',str(folder/'sim')],capture_output=True,text=True,timeout=30)
            assert run.returncode==0 and 'PASS pipelined BIST' in run.stdout,run.stdout+run.stderr
            checks.append(dict(bursts=bursts,case=case,passed=True,log=run.stdout.strip()))
result=dict(passed=True,source_bound=bool(a.build),build=str(a.build) if a.build else None,
    hardware_tested=False,pcm_saved=False,bsram_added=0,check_cycles_per_read_added=1,
    full8MiB_startup_extra_ms=5.24288,checks=checks,
    original_sha256=hashlib.sha256(original.encode()).hexdigest(),patched_sha256=hashlib.sha256(patched.encode()).hexdigest())
if a.output:a.output.write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
