#!/usr/bin/env python3
"""Actual video diagnostic HDL: exact one-pixel event delay including dense pulses/rollover."""
from pathlib import Path
import argparse,sys,tempfile,subprocess,json,hashlib
root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root/'tools'))
from build_workstation_flash_boot import retime_video_frame_telemetry
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path);a=p.parse_args()
source=root/'results/song_guide_full85_clk50_20261007_084539_884006_route1/Prj1/src/video/video_runtime_diagnostics.v';old=source.read_text();new=retime_video_frame_telemetry(old)
tb='''`timescale 1ns/1ps
module tb;
reg clk=0,pclk=0,uclk=0;always #10 clk=~clk;always #3.367 pclk=~pclk;always #5 uclk=~uclk;
reg rst=0,prst=0,urst=0,vblank=0;reg [31:0] frames=0,under=0;
wire [127:0] a,b;
original #(.WINDOW_CYCLES(100)) x(clk,rst,pclk,prst,vblank,uclk,urst,frames,under,1'b1,1'b1,1'b1,1'b0,a);
retimed #(.WINDOW_CYCLES(100)) y(clk,rst,pclk,prst,vblank,uclk,urst,frames,under,1'b1,1'b1,1'b1,1'b0,b);
reg [31:0] previous_count=0,previous_gray=0,lfsr=32'h25250901;
initial begin
 repeat(4)@(negedge pclk);rst=1;prst=1;urst=1;
 for(integer i=0;i<30000;i=i+1)begin
  @(negedge pclk);
  lfsr={lfsr[30:0],lfsr[31]^lfsr[21]^lfsr[1]^lfsr[0]};
  vblank=i%19<4 || lfsr[0];
  if(i%2001==0)begin
   // Reset including while event is asserted; no stale event may count later.
   prst=0;#1;previous_count=0;previous_gray=0;
   if(y.pixel_frame_count!==0 || y.frame_advance_q!==0)$fatal(1,"async reset/stale event");
   @(negedge pclk);prst=1;
  end
  if(i==15000)begin
   // Start both references identically immediately below low16 rollover.
   x.pixel_frame_count=32'h0001fffe;y.pixel_frame_count=32'h0001fffe;
   x.pixel_frame_gray=32'h0001fffe^(32'h0001fffe>>1);y.pixel_frame_gray=x.pixel_frame_gray;
   previous_count=x.pixel_frame_count;previous_gray=x.pixel_frame_gray;
   y.frame_advance_q=0;vblank=1;
  end
  @(posedge pclk);#0.1;
  if(y.pixel_frame_count!==previous_count || y.pixel_frame_gray!==previous_gray)$fatal(1,"telemetry not exact1cycle event delay at%0d old%h new%h expected%h",i,x.pixel_frame_count,y.pixel_frame_count,previous_count);
  previous_count=x.pixel_frame_count;previous_gray=x.pixel_frame_gray;
  // Other diagnostics blocks retain exact local cycles.
  if({x.pixel_cycle_low,x.pixel_block_count,x.pixel_block_gray}!=={y.pixel_cycle_low,y.pixel_block_count,y.pixel_block_gray})$fatal(1,"pixel measurement changed");
  if({x.memory_rendered_gray,x.memory_underrun_gray}!=={y.memory_rendered_gray,y.memory_underrun_gray})$fatal(1,"DDR telemetry changed");
 end
 $display("PASS video diagnostics30000pixel cycles,exact1cycle frame/count/Gray delay,dense pulses,low16rollover,async reset; other counters unchanged");$finish;
end
endmodule
'''
with tempfile.TemporaryDirectory(prefix='cnn_video_count_') as temp:
 temp=Path(temp);code=temp/'test.sv';code.write_text(old.replace('module video_runtime_diagnostics','module original')+'\n'+new.replace('module video_runtime_diagnostics','module retimed')+'\n'+tb);exe=temp/'sim'
 c=subprocess.run(['iverilog','-g2012','-s','tb','-o',str(exe),str(code)],capture_output=True,text=True);assert c.returncode==0,c.stdout+c.stderr
 v=subprocess.run(['vvp',str(exe)],capture_output=True,text=True,timeout=15);assert v.returncode==0 and 'PASS video diagnostics' in v.stdout,v.stdout+v.stderr
 d=dict(passed=True,pixel_cycles=30000,added_diagnostic_latency_pixel_cycles=1,image_path_changed=False,original_source_sha256=hashlib.sha256(old.encode()).hexdigest(),patched_source_sha256=hashlib.sha256(new.encode()).hexdigest(),log=v.stdout.strip(),hardware_tested=False)
 if a.output:a.output.write_text(json.dumps(d,indent=2)+'\n')
 print(json.dumps(d,indent=2))
