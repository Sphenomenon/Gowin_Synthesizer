#!/usr/bin/env python3
"""Compare actual dashboard movement and pixel output against routed reference."""
from pathlib import Path
import hashlib,json,subprocess,sys
ROOT=Path(__file__).resolve().parents[2]
build=Path(sys.argv[1]).resolve();stage=build/'Prj1';out=build/'dashboard_timing';out.mkdir(exist_ok=True)
old=ROOT/'results/resource_rework_final_route0_20261020_041042/Prj1/src/video/feedback_dashboard.v'
new=stage/'src/video/feedback_dashboard.v';ref=out/'reference.v'
ref.write_text(old.read_text().replace('module feedback_dashboard #','module feedback_dashboard_reference #',1))
bench=out/'tb.sv'
ports=""".clk(clk),.reset_n(rst),.enable(enable),.frame_start(fs),.pixel_x(x),.pixel_y(y),
.wave_sample(seed),.wave_previous(~seed),.waveform_held(seed[0]),.spectrum_left(seed[7:0]),.spectrum_right(seed[15:8]),
.image_hit(seed[1]),.peak_left(seed[15:0]),.peak_right(seed[31:16]),.image_gain(seed[4:2]),
.analysis_sequence(seed),.analysis_skipped(~seed),.peak_data(seed),.active_voices(seed),.status_data(seed),
.effect_mask(mask),.effect_order(order),.sequence_data(seed),.skipped_data(~seed),.memory_status(seed),
.underruns(seed),.framecount(seed),.pixel_data(PIXEL)"""
body='''`timescale 1ns/1ps
module tb;
reg clk=0,rst=0,enable=0,fs=0;reg [10:0]x=0,y=0;reg [31:0]seed=32'h0b3efc19;
reg [2:0]mask=0;reg [5:0]order=0;wire [31:0]n0,o0,n1,o1;integer checks=0;
'''
for module,name,param,pixel in [('feedback_dashboard','n',0,'n0'),('feedback_dashboard_reference','o',0,'o0'),('feedback_dashboard','na',1,'n1'),('feedback_dashboard_reference','oa',1,'o1')]:
 body+=f'{module} #(.ENABLE_ANALYSIS({param})) {name}('+ports.replace('PIXEL',pixel)+');\n'
body+='''
task cycle;
begin
 #2;clk=1;#2;
 if({n0,n1}!=={o0,o1})$fatal(1,"pixel mismatch %0d",checks);
 if({n.effect_x0,n.effect_x1,n.effect_x2,n.visible_mask,n.front_effect} !==
    {o.effect_x0,o.effect_x1,o.effect_x2,o.visible_mask,o.front_effect})$fatal(1,"animation mismatch %0d",checks);
 clk=0;checks=checks+1;
end endtask
initial begin
 cycle;rst=1;
 // Full 11-bit position domain, all masks and orders, including duplicate slots.
 // Checking the actual new combinational net preserves overflow corner cases.
 for(integer p=0;p<2048;p=p+1)begin
  n.effect_x0=11'(p);n.effect_x1=11'(2047-p);n.effect_x2=11'(p*31);
  for(integer m=0;m<8;m=m+1)for(integer q=0;q<64;q=q+1)begin
   mask=3'(m);order=6'(q);#1;
   if(n.dash_next_0!==o.slide(11'(p),o.destination(0)) ||
      n.dash_next_1!==o.slide(11'(2047-p),o.destination(1)) ||
      n.dash_next_2!==o.slide(11'(p*31),o.destination(2)))$fatal(1,"movement mismatch p=%0d mask=%0d order=%0d",p,m,q);
  end
 end
 rst=0;cycle;rst=1;enable=1;
 for(integer c=0;c<100000;c=c+1)begin
  seed={seed[30:0],seed[31]^seed[21]^seed[1]^seed[0]};
  x=11'(seed[10:0]%1920);y=11'(seed[21:11]%1080);mask=seed[24:22];order=seed[30:25];
  fs=c%17==0;enable=c%29!=0;cycle;
 end
 $display("PASS dashboard: 1048576 movement configurations (three positions each), %0d cycles, both analysis modes and all pixels/state exact",checks);$finish;
end
endmodule
'''
if '--full-raster' in sys.argv[2:]:
 body=body.replace(' $display("PASS dashboard:', '''
 mask=0;fs=1;enable=1;repeat(100)cycle;fs=0;
 for(integer yy=0;yy<1080;yy=yy+1)for(integer xx=0;xx<1920;xx=xx+1)begin
  x=11'(xx);y=11'(yy);cycle;
 end
 $display("PASS dashboard:''')
bench.write_text(body)
sources=[new,ref,stage/'src/video/video_font_5x7.v',bench]
log='';passed=False
for command in (['iverilog','-g2012','-s','tb','-o',str(out/'test')]+list(map(str,sources)),['vvp',str(out/'test')]):
 p=subprocess.run(command,cwd=stage,capture_output=True,text=True);log+=p.stdout+p.stderr
 if p.returncode:break
passed=p.returncode==0 and 'PASS dashboard:' in log
(out/'run.log').write_text(log)
(out/'verification.json').write_text(json.dumps(dict(passed=passed,source_sha256={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},hardware_tested=False),indent=2)+'\n')
print(log[-3000:])
if not passed:raise SystemExit(1)
