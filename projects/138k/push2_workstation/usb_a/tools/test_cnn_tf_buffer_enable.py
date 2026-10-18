#!/usr/bin/env python3
"""Independent queued DDR command oracle; invalid payload deliberately ignored."""
from pathlib import Path
import argparse,tempfile,subprocess,json,hashlib
from cnn_ddr_pipeline_patch import TF_BUFFER,retime_tf_buffer_enable
ROOT=Path(__file__).resolve().parents[1];BASE=ROOT/'results/song_guide_full85_clk50_20261007_084539_884006_route1/Prj1'
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path);a=p.parse_args()
original=(BASE/TF_BUFFER).read_text();patched=retime_tf_buffer_enable(original)
tb=r'''`timescale 1ns/1ps
module tb;
reg clk=0,rst=0,valid=0,write=0,ready=0;reg [28:0] address=0;reg [255:0] data=0;
wire in_ready,out_valid,out_write;wire [28:0] out_address;wire [255:0] out_data;
reg [285:0] expected[0:9999];integer put=0,take=0,epochs=0;reg [31:0] salt=32'h41905327;
always #5 clk=~clk;
tf_audio_ddr_command_buffer dut(.clk(clk),.rst_n(rst),.in_valid(valid),.in_write(write),.in_address(address),.in_data(data),.in_ready(in_ready),.out_valid(out_valid),.out_write(out_write),.out_address(out_address),.out_data(out_data),.out_ready(ready));
always @(posedge clk)if(rst)begin
 if(out_valid && ready)begin if(take>=put || {out_write,out_address,out_data}!==expected[take])$fatal(1,"queue command mismatch");take=take+1;end
 if(valid && in_ready)begin expected[put]={write,address,data};put=put+1;end
end
initial begin
 repeat(4)@(negedge clk);rst=1;
 for(integer i=0;i<20000;i=i+1)begin
  @(negedge clk);salt=(salt>>1)^({32{salt[0]}}&32'h80200003);
  if(i%4096==4095)begin rst=0;put=0;take=0;epochs=epochs+1;end else rst=1;
  valid=salt[0];write=salt[1];ready=salt[8:5]>5;address=i;data={8{salt^i}};
 end
 @(negedge clk);valid=0;ready=1;
 repeat(8)@(negedge clk);if(put!=take)$fatal(1,"queue did not drain");
 $display("PASS TF buffer20000cycles independentoracle native stalls,invalidpayloadchanges,%0dresets,last_epoch%0dcommands",epochs,take);$finish;
end
endmodule'''
with tempfile.TemporaryDirectory(prefix='cnn_tf_buffer_enable_') as tmp:
 t=Path(tmp);(t/'dma.v').write_text(patched);(t/'tb.sv').write_text(tb);exe=t/'sim'
 c=subprocess.run(['iverilog','-g2012','-s','tb','-o',str(exe),str(t/'tb.sv'),str(t/'dma.v')],capture_output=True,text=True);assert c.returncode==0,c.stdout+c.stderr
 v=subprocess.run(['vvp',str(exe)],capture_output=True,text=True,timeout=30);assert v.returncode==0 and 'PASS TF buffer' in v.stdout,v.stdout+v.stderr
 r=dict(passed=True,hardware_tested=False,pcm_saved=False,original_sha256=hashlib.sha256(original.encode()).hexdigest(),patched_sha256=hashlib.sha256(patched.encode()).hexdigest(),log=v.stdout.strip())
 if a.output:a.output.write_text(json.dumps(r,indent=2)+'\n')
 print(json.dumps(r,indent=2))
