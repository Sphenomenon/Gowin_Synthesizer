#!/usr/bin/env python3
"""Bit-exact original/retimed TMDS encoder, random reset/blanking/full-byte sweep."""
from pathlib import Path
import argparse,tempfile,subprocess,json,hashlib
from cnn_ddr_pipeline_patch import TMDS,retime_tmds_statistics,lut_tmds_popcount
ROOT=Path(__file__).resolve().parents[1];BASE=ROOT/'results/song_guide_full85_clk50_20261007_084539_884006_route1/Prj1'
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path);p.add_argument('--lut-popcount',action='store_true');a=p.parse_args()
original=(BASE/TMDS).read_text();patched=retime_tmds_statistics(original)
if a.lut_popcount:patched=lut_tmds_popcount(patched)
tb=r'''`timescale 1ns/1ps
module tb;
reg clk=0,rst=1,den=0;reg [7:0] data=0;reg [1:0] ctrl=0;
wire [9:0] before_code,after_code;integer cycles=0,resets=0;reg [31:0] random_state=32'hbc3e81a7;
always #3.367 clk=~clk;
dvi_original baseline(.clock(clk),.reset(rst),.den(den),.data(data),.ctrl(ctrl),.tmds(before_code));
dvi_tx_tmds_enc retimed(.clock(clk),.reset(rst),.den(den),.data(data),.ctrl(ctrl),.tmds(after_code));
always @(posedge clk)begin #1;if(before_code!==after_code)$fatal(1,"TMDS mismatch cycle%0d reset%b before%h after%h",cycles,rst,before_code,after_code);end
initial begin
 repeat(10)@(negedge clk);
 for(integer i=0;i<100000;i=i+1)begin
  @(negedge clk);cycles=cycles+1;
  random_state=(random_state>>1)^({32{random_state[0]}}&32'h80200003);
  rst=(random_state[20:12]==0 || i%4096<5);if(rst)resets=resets+1;
  den=random_state[0];ctrl=random_state[9:8];data=i<65536?i[7:0]:random_state[17:10];
 end
 $display("PASS TMDS100000cycles all256data repeated,randomcontrols/blanking,%0dresetcycles,bitexact10bitcodes",resets);$finish;
end
endmodule'''
with tempfile.TemporaryDirectory(prefix='cnn_tmds_statistics_') as tmp:
 t=Path(tmp);(t/'before.v').write_text(original.replace('module dvi_tx_tmds_enc (','module dvi_original ('));(t/'after.v').write_text(patched);(t/'tb.sv').write_text(tb);exe=t/'sim'
 c=subprocess.run(['iverilog','-g2012','-s','tb','-o',str(exe),str(t/'tb.sv'),str(t/'before.v'),str(t/'after.v')],capture_output=True,text=True);assert c.returncode==0,c.stdout+c.stderr
 v=subprocess.run(['vvp',str(exe)],capture_output=True,text=True,timeout=30);assert v.returncode==0 and 'PASS TMDS' in v.stdout,v.stdout+v.stderr
 r=dict(passed=True,lut_popcount=a.lut_popcount,hardware_tested=False,pcm_saved=False,original_sha256=hashlib.sha256(original.encode()).hexdigest(),patched_sha256=hashlib.sha256(patched.encode()).hexdigest(),log=v.stdout.strip())
 if a.output:a.output.write_text(json.dumps(r,indent=2)+'\n')
 print(json.dumps(r,indent=2))
