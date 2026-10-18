#!/usr/bin/env python3
"""Validate a frozen --with-ui build; write a new timestamped evidence directory.
Usage: check_spectrum_bars.py /absolute/build/directory
"""
import sys
from pathlib import Path
import datetime,subprocess,json,hashlib
r=Path(__file__).resolve().parents[2];stage=Path(sys.argv[1]).resolve()/'Prj1';out=r/'results'/datetime.datetime.now().strftime('bar_map_%Y%m%d_%H%M%S_%f');out.mkdir();print(out,flush=True)
tb=r'''`timescale 1ns/1ps
module tb_spectrum_map;
reg clk=0,reset_n=0,rd=0;always #5 clk=~clk;
reg [8:0] col=0;wire ready;wire [7:0] left_o,right_o;
output_audio_analysis dut(.clk(clk),.reset_n(reset_n),.source_clk(clk),.source_reset_n(reset_n),.pcm_pair(32'd0),.sample_valid(1'b0),.release_frame(1'b0),.ready(ready),.peak_left(),.peak_right(),.image_gain(),.sequence_data(),.skipped_data(),.display_read_enable(rd),.spectrum_column(col),.image_addr(16'd0),.spectrum_left(left_o),.spectrum_right(right_o),.image_hit());
integer el[0:511],er[0:511],anchor[0:511],writes[0:511];
integer k,n,c,lo,hi,x,w,dl,dr,cycles,maxcycles=0,prevcol=0,checks=0;
reg [31:0] rng=32'h18faba97;
reg [7:0] saved_l,saved_r;
function integer rnd;
 begin rng=rng^(rng<<13);rng=rng^(rng>>17);rng=rng^(rng<<5);rnd=(rng&32'h7fffffff)%225;end
endfunction
always @(posedge clk) if(reset_n) begin
 if(dut.state==dut.MAP_WRITE) writes[dut.group_column]=writes[dut.group_column]+1;
 if(dut.state==dut.MAP_CLEAR) writes[dut.clear_column]=writes[dut.clear_column]+1;
end
initial begin
 for(k=0;k<880;k=k+1) begin
  reset_n=0;rd=0;col=0;repeat(4)@(negedge clk);
  for(n=0;n<512;n=n+1) begin
   el[n]=0;er[n]=0;anchor[n]=0;writes[n]=0;
  end
  for(n=0;n<1024;n=n+1) begin
   if(k<852)begin dut.levels_left[n]=n==k+2 ? 224 : 0;dut.levels_right[n]=n==k+2 ? 192 : 0;end
   else if(k==852)begin dut.levels_left[n]=0;dut.levels_right[n]=0;end
   else if(k==853)begin dut.levels_left[n]=224;dut.levels_right[n]=224;end
   else if(k==854)begin dut.levels_left[n]=n[0]?224:0;dut.levels_right[n]=n[0]?0:224;end
   else begin dut.levels_left[n]=rnd();dut.levels_right[n]=rnd();end
   if(n<512)begin dut.display_left[n]=255;dut.display_right[n]=255;end
  end
  for(n=2;n<=853;n=n+1)begin
   c=$rtoi(511*$ln(1.0*n/2)/$ln(853.0/2)+0.5);anchor[c]=1;
   if(dut.levels_left[n]>el[c])el[c]=dut.levels_left[n];
   if(dut.levels_right[n]>er[c])er[c]=dut.levels_right[n];
  end
  reset_n=1;@(negedge clk);dut.index=2;dut.state=dut.MAP_CLEAR;cycles=0;
  while(!ready)begin @(negedge clk);cycles=cycles+1;if(cycles>10000)$fatal(1,"map too slow case %0d",k);end
  if(cycles>maxcycles)maxcycles=cycles;
  for(n=0;n<512;n=n+1)begin
   if(writes[n]!=(1+anchor[n]))$fatal(1,"column clear/group write count case=%0d col=%0d count=%0d",k,n,writes[n]);
   if(dut.display_left[n]!==el[n] || dut.display_right[n]!==er[n])$fatal(1,"map mismatch case=%0d col=%0d got=%0d/%0d expected=%0d/%0d",k,n,dut.display_left[n],dut.display_right[n],el[n],er[n]);
   checks=checks+2;
  end
  // Cycle-exact read latency and output holding while enable is low.
  prevcol=0;saved_l=left_o;saved_r=right_o;
  for(n=0;n<40;n=n+1)begin
   col=(n*41)%512;rd=n%3!=1;
   @(posedge clk);#1;
   if(rd)begin
    if(left_o!==el[prevcol] || right_o!==er[prevcol])$fatal(1,"read latency mismatch");
   end else if(left_o!==saved_l || right_o!==saved_r)$fatal(1,"read changed under stall");
   prevcol=col;saved_l=left_o;saved_r=right_o;@(negedge clk);
  end
 end
 $display("PASS %0d level comparisons, 880 cases, every bin impulse 2..853, random/extreme levels; clear once and write each measured column once; stalled reads; max %0d cycles",checks,maxcycles);$finish;
end
initial begin #100000000;$fatal(1,"timeout");end
endmodule
'''
p=out/'tb_spectrum_map.sv';p.write_text(tb);sources=[stage/'src/video'/f for f in ['output_audio_analysis.v','output_audio_capture.v','audio_analysis_rom.v']]+[p]
h={str(p):hashlib.sha256(p.read_bytes()).hexdigest()for p in sources};(out/'inputs.json').write_text(json.dumps(h,indent=2)+'\n')
for name,cmd in [('compile',['iverilog','-g2012','-s','tb_spectrum_map','-o',str(out/'sim.vvp'),*map(str,sources)]),('simulation',['vvp',str(out/'sim.vvp')])]:
 with(out/(name+'.log')).open('w')as log:res=subprocess.run(cmd,cwd=out,stdout=log,stderr=subprocess.STDOUT)
 print(name,res.returncode,flush=True)
 if res.returncode:raise SystemExit(res.returncode)
assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==v for p,v in h.items())
(out/'verification.json').write_text(json.dumps(dict(passed=True,inputs_unchanged=True,scope='Independent log-bar peak pooling oracle; every source bin as a narrow impulse, no lost high-frequency peaks; extremes, random stereo data and held read protocol.'),indent=2)+'\n')
