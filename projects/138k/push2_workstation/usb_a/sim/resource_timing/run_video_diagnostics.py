#!/usr/bin/env python3
"""Prove diagnostic frame register delay, rollover and Gray step safety."""
from pathlib import Path
import argparse,subprocess,json,hashlib
ROOT=Path(__file__).resolve().parents[2]
def main():
 p=argparse.ArgumentParser();p.add_argument('build',type=Path);a=p.parse_args();build=a.build.resolve();out=build/'video_diag_timing';out.mkdir(exist_ok=True)
 rel='src/video/video_runtime_diagnostics.v';src=build/'Prj1'/rel;ref=out/'reference.v';ref.write_text((ROOT/'results/resource_rework_final_route0_20261020_041042/Prj1'/rel).read_text().replace('module video_runtime_diagnostics','module video_runtime_diagnostics_reference',1))
 tb=r'''`timescale 1ns/1ps
module tb;
reg c=0,p=0,u=0,rst=0,prst=0,urst=0,frame=0;
always #10 c=~c;always #3.3670035 p=~p;always #5 u=~u;
wire[127:0]di,dr;
`define PORTS .clk_50m(c),.reset_n(rst),.pixel_clk(p),.pixel_reset_n(prst),.vblank_start(frame),.ui_clk(u),.ui_reset_n(urst),.rendered_frames(32'd0),.underruns(32'd0),.hdmi_hpd(1'b1),.video_locked(1'b1),.scanout_reset_n(prst),.serializer_reset(1'b0)
video_runtime_diagnostics #(.WINDOW_CYCLES(100)) dut(`PORTS,.diagnostics(di));
video_runtime_diagnostics_reference #(.WINDOW_CYCLES(100)) old(`PORTS,.diagnostics(dr));
reg[31:0] prev_count=0,prev_gray=0,last_gray=0;integer checked=0,events=0;
always @(posedge p)begin
 if(!prst)begin prev_count=0;prev_gray=0;last_gray=0;end
 else begin
  #1;
  if(dut.pixel_frame_count!==prev_count || dut.pixel_frame_gray!==prev_gray)$fatal(1,"frame diagnostic changed beyond exactly one pixel clock");
  if($countones(dut.pixel_frame_gray^last_gray)>1)$fatal(1,"Gray counter changed multiple bits");
  prev_count=old.pixel_frame_count;prev_gray=old.pixel_frame_gray;last_gray=dut.pixel_frame_gray;checked=checked+1;
 end
end
initial begin
 repeat(5)@(negedge p);rst=1;prst=1;urst=1;
 for(integer n=0;n<230000;n=n+1)begin @(negedge p);frame=n%3==0;if(frame)events=events+1;end
 frame=0;repeat(5)@(negedge p);
 if(dut.pixel_frame_count!=events || dut.pixel_frame_count<=65536)$fatal(1,"counter rollover coverage");
 prst=0;repeat(5)@(negedge p);prst=1;repeat(5)@(negedge p);
 if(dut.pixel_frame_count!=0)$fatal(1,"reset failed");
 $display("PASS video diagnostics: %0d cycles, %0d frames, 16-bit carry rollover, Gray step, reset, exactly one pixel clock added",checked,events);$finish;
end
endmodule
'''
 f=out/'tb.sv';f.write_text(tb);log=''
 for c in [['iverilog','-g2012','-s','tb','-o',str(out/'sim'),str(src),str(ref),str(f)],['vvp',str(out/'sim')]]:
  x=subprocess.run(c,capture_output=True,text=True);log+=x.stdout+x.stderr
  if x.returncode:break
 (out/'test.log').write_text(log);print(log)
 d=dict(passed=x.returncode==0 and 'PASS video' in log,source_sha256={str(x):hashlib.sha256(x.read_bytes()).hexdigest() for x in [src,ref,f]},hardware_tested=False);(out/'verification.json').write_text(json.dumps(d,indent=2)+'\n')
 if not d['passed']:raise SystemExit(1)
if __name__=='__main__':main()
