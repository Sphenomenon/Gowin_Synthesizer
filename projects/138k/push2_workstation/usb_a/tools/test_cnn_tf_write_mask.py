#!/usr/bin/env python3
"""Cycle-exact masked TF byte storage versus original clearing for arbitrary controls."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
from cnn_ddr_pipeline_patch import (TF_DMA,retime_tf_write_buffer,retime_tf_capture_limit,
    mask_tf_write_epoch)
ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'results/song_guide_full85_clk50_20261007_084539_884006_route1/Prj1'
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path);p.add_argument('--build',type=Path);a=p.parse_args()
old=retime_tf_capture_limit(retime_tf_write_buffer((BASE/TF_DMA).read_text()));new=mask_tf_write_epoch(old)
if a.build:
    from build_workstation_flash_boot import expected_tf_dma
    build=a.build.resolve();metadata=json.loads((build/'build_metadata.json').read_text())
    assert metadata.get('masked_tf_write_epoch')
    new=(build/'Prj1'/TF_DMA).read_text()
    assert new==expected_tf_dma(metadata),'candidate TF source drift'
def logic(text):
    start=text.index('    always @(posedge clk or negedge rst_n)begin\n        if(!rst_n)begin write_byte_valid') if 'write_byte_valid' in text else text.index('    always @(posedge clk or negedge rst_n) begin\n        if(!rst_n)begin write_buf')
    end=text.index('    always @(posedge clk or negedge rst_n) begin\n        if (!rst_n) begin',start)
    return text[start:end]
ports='input clk,rst_n,epoch_clear,write_accept,fifo_in_rd_valid,capture_limit_hit,input[2:0]state,input[5:0]write_count,input[7:0]fifo_in_rd_data,output[255:0]payload'
body=f'module old({ports});localparam S_STREAM=0;reg[255:0]write_buf;reg write_clear_pending;\n'+logic(old)+'assign payload=write_buf;endmodule\n'
start=new.index('    reg [255:0] read_buf,write_storage;');end=new.index('    reg write_clear_pending;',start)
body+=f'module fresh({ports});localparam S_STREAM=0;\n'+new[start:end]+'reg write_clear_pending;\n'+logic(new)+'assign payload=write_buf;endmodule\n'
body+=r'''`timescale 1ns/1ps
module tb;
reg clk=0,rst=0,epoch=0,accepted=0,valid=0,limit=0;reg[2:0]state=0;reg[5:0]index=0;reg[7:0]data=0;
wire[255:0]a,b;reg[31:0]rng=32'h9853cab7;integer checks=0;
always #5 clk=~clk;
old o(clk,rst,epoch,accepted,valid,limit,state,index,data,a);
fresh f(clk,rst,epoch,accepted,valid,limit,state,index,data,b);
initial begin
 repeat(3)@(negedge clk);rst=1;
 for(integer cycle=0;cycle<100000;cycle=cycle+1)begin
  @(negedge clk);rng=(rng>>1)^({32{rng[0]}}&32'h80200003);
  rst=cycle%311!=310;epoch=rng[0]&&rng[5];accepted=rng[1];valid=rng[2];limit=rng[3];
  state=rng[8:6];index=rng[14:9];data=rng[23:16];
  @(posedge clk);#1;
  if(a!==b)$fatal(1,"TF masked buffer cycle mismatch at%0d",cycle);checks=checks+1;
 end
 $display("PASS TF write mask100000cycles arbitrary reset/epoch/accept/bytevalid/capturelimit/state/all64indexvalues,exactall256observablebits");$finish;
end
endmodule'''
with tempfile.TemporaryDirectory(prefix='cnn_tf_write_mask_') as tmp:
    folder=Path(tmp);(folder/'tb.sv').write_text(body)
    compile=subprocess.run(['iverilog','-g2012','-s','tb','-o',str(folder/'sim'),str(folder/'tb.sv')],capture_output=True,text=True)
    assert compile.returncode==0,compile.stdout+compile.stderr
    run=subprocess.run(['vvp',str(folder/'sim')],capture_output=True,text=True,timeout=120)
    assert run.returncode==0 and 'PASS TF write mask' in run.stdout,run.stdout+run.stderr
result=dict(passed=True,source_bound=bool(a.build),build=str(a.build) if a.build else None,hardware_tested=False,pcm_saved=False,added_cycles=0,added_bsram=0,
    oracle='all256observable payload bits on100000 arbitrary control cycles,including all64indexvalues/reset/epoch/overlappingcapture and clear',
    original_source_sha256=hashlib.sha256(old.encode()).hexdigest(),patched_source_sha256=hashlib.sha256(new.encode()).hexdigest(),fixture_sha256=hashlib.sha256(body.encode()).hexdigest(),log=run.stdout.strip())
if a.output:a.output.write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
