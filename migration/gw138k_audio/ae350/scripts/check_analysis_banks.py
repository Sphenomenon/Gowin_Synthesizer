import sys
from pathlib import Path
import datetime,json,hashlib,subprocess
r=Path(__file__).resolve().parents[2];build=Path(sys.argv[1]).resolve();stage=build/'Prj1';o=r/'results'/datetime.datetime.now().strftime('analysis_banks_%Y%m%d_%H%M%S_%f');o.mkdir();print(o,flush=True)
tb=r'''`timescale 1ns/1ps
module tb_analysis_banks;
reg clk=0,rst=0,valid=0,rd=0,release_a=0,release_g=0;always #5 clk=~clk;
reg [31:0] pcm=0;reg [8:0] col=0;reg [15:0] addr=0;
wire ar,gr,ah,gh;wire [7:0] al,ax,gl,gx;wire [15:0] alp,arp,glp,grp;wire [2:0] ag,gg;wire [31:0] aseq,gseq;
output_audio_analysis #(.ASYNC_DISPLAY(1)) dut(.clk(clk),.reset_n(rst),.source_clk(clk),.source_reset_n(rst),.pcm_pair(pcm),.sample_valid(valid),.release_frame(release_a),.ready(ar),.peak_left(alp),.peak_right(arp),.image_gain(ag),.sequence_data(aseq),.skipped_data(),.display_read_enable(rd),.spectrum_column(col),.image_addr(addr),.spectrum_left(al),.spectrum_right(ax),.image_hit(ah));
output_audio_analysis golden(.clk(clk),.reset_n(rst),.source_clk(clk),.source_reset_n(rst),.pcm_pair(pcm),.sample_valid(valid),.release_frame(release_g),.ready(gr),.peak_left(glp),.peak_right(grp),.image_gain(gg),.sequence_data(gseq),.skipped_data(),.display_read_enable(rd),.spectrum_column(col),.image_addr(addr),.spectrum_left(gl),.spectrum_right(gx),.image_hit(gh));
integer n,k,l,r,checks=0;real pi=3.141592653589793;
task feed(input integer tone);
 begin
  for(n=0;n<2048;n=n+1)begin
   @(negedge clk);l=$rtoi(14000*$sin(2*pi*tone*n/2048.0));r=$rtoi(6000*$sin(2*pi*(tone+29)*n/2048.0));pcm={l[15:0],r[15:0]};valid=1;
  end
  @(negedge clk);valid=0;
 end
endtask
task compare_front;
 begin
  if({alp,arp,ag,aseq}!=={glp,grp,gg,gseq})$fatal(1,"published metadata mismatch");
  for(k=0;k<65536;k=k+1)begin
   @(negedge clk);addr=k;col=k%512;rd=k%7!=3;
   @(posedge clk);#1;
   if({al,ax,ah}!=={gl,gx,gh})$fatal(1,"front/back data mismatch at image=%0d",k);
   checks=checks+3;
  end
  @(negedge clk);rd=0;
 end
endtask
initial begin
 repeat(4)@(negedge clk);rst=1;rd=1;repeat(4)@(negedge clk);
 if({al,ax,ah,alp,arp,ag,aseq}!==0)$fatal(1,"unpublished front not blank");rd=0;
 feed(32);wait(ar && gr);@(negedge clk);release_a=1;@(negedge clk);release_a=0;
 // Golden holds frame1. DUT captures/calculates frame2 into its other bank.
 feed(91);compare_front();wait(ar);compare_front();
 // Only publication can replace the display; let golden finish frame2 too.
 release_g=1;release_a=1;@(negedge clk);release_g=0;release_a=0;
 wait(gr);compare_front();
 rst=0;repeat(4)@(negedge clk);rst=1;rd=1;repeat(4)@(negedge clk);
 if({al,ax,ah,alp,arp,ag,aseq}!==0)$fatal(1,"reset did not invalidate old front");
 $display("PASS %0d banked-vs-legacy pixel/column reads with stalls, concurrent capture/FFT, held finished back bank, atomic publication and reset blanking",checks);$finish;
end
initial begin #30000000;$fatal(1,"watchdog");end
endmodule
'''
p=o/'tb_analysis_banks.sv';p.write_text(tb);sources=[stage/'src/video'/n for n in ['output_audio_analysis.v','output_audio_capture.v','audio_analysis_rom.v']]+[p];h={str(p):hashlib.sha256(p.read_bytes()).hexdigest()for p in sources};(o/'inputs.json').write_text(json.dumps(h,indent=2)+'\n')
for name,cmd in [('compile',['verilator','--binary','--timing','-j','4','-Wno-fatal','--top-module','tb_analysis_banks','--Mdir',str(o/'obj'),*map(str,sources)]),('simulation',[str(o/'obj/Vtb_analysis_banks')])]:
 with(o/(name+'.log')).open('w')as f:p=subprocess.run(cmd,cwd=o,stdout=f,stderr=subprocess.STDOUT)
 print(name,p.returncode,flush=True)
 if p.returncode:raise SystemExit(p.returncode)
assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==v for p,v in h.items())
(o/'verification.json').write_text(json.dumps(dict(passed=True,build=str(build),scope='589824 banked vs legacy spectrum/image read comparisons; concurrent new FFT, finished-back hold, atomic metadata and pixels, stalls and reset invalidation'),indent=2)+'\n')
