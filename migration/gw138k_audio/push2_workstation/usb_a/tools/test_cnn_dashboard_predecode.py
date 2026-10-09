#!/usr/bin/env python3
"""Compare every raster pixel to frozen dashboard after exactly one enabled stage."""
import argparse,hashlib,json,subprocess,tempfile,re
from pathlib import Path
from cnn_ddr_pipeline_patch import DASHBOARD,predecode_dashboard,predecode_dashboard_text_coordinates,parallel_dashboard_cards
ROOT=Path(__file__).resolve().parents[1];BASE=ROOT/'results/song_guide_full85_clk50_20261007_084539_884006_route1/Prj1'
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path);p.add_argument('--text-coordinates',action='store_true');p.add_argument('--parallel-cards',action='store_true');a=p.parse_args()
if a.parallel_cards and not a.text_coordinates:p.error('--parallel-cards requires --text-coordinates')
original=(BASE/DASHBOARD).read_text();patched=predecode_dashboard(original)
if a.text_coordinates:patched=predecode_dashboard_text_coordinates(patched)
if a.parallel_cards:patched=parallel_dashboard_cards(patched)
header=original[:original.index('    localparam')];signals=[]
for declaration in re.findall(r'input wire\s+([^\n]+)',header):
 width=re.search(r'\[[^]]+\]',declaration);width=width[0] if width else ''
 for name in declaration.replace(width,'').strip().strip(',').split(','):
  name=name.strip()
  if name not in ['clk','reset_n','enable','frame_start','pixel_x','pixel_y']:signals.append((width,name))
ports=['.clk(clk)','.reset_n(rst)','.enable(en)','.frame_start(frame_start)','.pixel_x(x)','.pixel_y(y)']+[f'.{n}({n})' for _,n in signals]
assignments=[]
for width,name in signals:assignments.append(f'{name}=random_state ^ i;')
tb='''`timescale 1ns/1ps
module tb;
reg clk=0,rst=0,en=0,frame_start=0;reg [10:0] x=0,y=0;
wire [31:0] before_pixel,after_pixel;reg [31:0] prior=0;integer cycles=0,checks=0,warm=0;reg [31:0] random_state=32'h691fb003;
always #5 clk=~clk;
'''+''.join(f'reg {w} {n}=0;\n' for w,n in signals)+'''
feedback_original #(.ENABLE_ANALYSIS(1)) baseline('''+','.join(ports)+''',.pixel_data(before_pixel));
feedback_dashboard #(.ENABLE_ANALYSIS(1)) retimed('''+','.join(ports)+''',.pixel_data(after_pixel));
always @(posedge clk)begin
 #1;
 if(!rst)begin warm=0;prior=0;end
 else if(en)begin
  if(warm>6)begin
   checks=checks+1;
   if(after_pixel!==prior)$fatal(1,"pixel mismatch cycle%0d x%0d y%0d before%h after%h",cycles,x,y,prior,after_pixel);
  end
  warm=warm+1;prior=before_pixel;
 end
end
initial begin
 repeat(5)@(negedge clk);rst=1;
 // All1920x1080 coordinates, plus random background/input/stall/reset epochs.
 for(integer i=0;i<2200000;i=i+1)begin
  @(negedge clk);cycles=cycles+1;
  random_state=(random_state>>1)^({32{random_state[0]}}&32'h80200003);
  en=i<2073600 || random_state[0];
  rst=i%700000!=699999;frame_start=i%100000==0;
  x=i<2073600?i%1920:random_state%1920;y=i<2073600?i/1920:(random_state>>11)%1080;
  '''+'\n  '.join(assignments)+'''
 end
 $display("PASS dashboard complete1920x1080 raster,%0dcompared pixels,randommetadata/stalls/frameanimation/reset,oneenabledcycle latency",checks);$finish;
end
endmodule
'''
with tempfile.TemporaryDirectory(prefix='cnn_dashboard_predecode_') as tmp:
 t=Path(tmp);(t/'before.v').write_text(original.replace('module feedback_dashboard #','module feedback_original #'));(t/'after.v').write_text(patched);(t/'tb.sv').write_text(tb);exe=t/'sim'
 c=subprocess.run(['verilator','--binary','--timing','-j','4','-Wno-fatal','--top-module','tb','--Mdir',str(t/'obj'),str(t/'tb.sv'),str(t/'before.v'),str(t/'after.v'),str(BASE/'src/video/video_font_5x7.v')],capture_output=True,text=True,timeout=120);assert c.returncode==0,c.stdout+c.stderr
 v=subprocess.run([str(t/'obj/Vtb')],capture_output=True,text=True,timeout=300);assert v.returncode==0 and 'PASS dashboard' in v.stdout,v.stdout+v.stderr
 r=dict(passed=True,predecoded_text_coordinates=a.text_coordinates,parallel_cards=a.parallel_cards,hardware_tested=False,pcm_saved=False,additional_enabled_cycles=1,original_sha256=hashlib.sha256(original.encode()).hexdigest(),patched_sha256=hashlib.sha256(patched.encode()).hexdigest(),log=v.stdout.strip())
 if a.output:a.output.write_text(json.dumps(r,indent=2)+'\n')
 print(json.dumps(r,indent=2))
