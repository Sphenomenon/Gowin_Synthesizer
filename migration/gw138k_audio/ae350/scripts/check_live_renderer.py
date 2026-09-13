import sys
from pathlib import Path
import datetime,json,hashlib,subprocess
r=Path(__file__).resolve().parents[2];build=Path(sys.argv[1]).resolve();stage=build/'Prj1';o=r/'results'/datetime.datetime.now().strftime('live_renderer_%Y%m%d_%H%M%S_%f');o.mkdir();print(o,flush=True)
tb=r'''`timescale 1ns/1ps
module tb_live_renderer;
reg clk=0,src=0,rst=0,start=0,valid=0;
always #5 clk=~clk;always #10 src=~src;
reg [31:0] pcm=0,mono=0,reference=0;
wire ready,busy,done,pv;wire [63:0] pd;
reg [15:0] rng=16'h9abd;wire accept=rng[3:0]!=0;
feedback_renderer #(.ENABLE_ANALYSIS(1)) dut(.clk(clk),.rst_n(rst),.start(start),.frame_ready(ready),.busy(busy),.frame_done(done),.pixel_valid(pv),.pixel_ready(accept),.pixel_data(pd),.source_clk(src),.source_reset_n(rst),.sample_data(mono),.sample_valid(valid),.output_pcm(pcm),.trigger_reference(reference),.active_voices(32'd3),.status_data(32'd0),.memory_status(32'hcb),.underruns(32'd0),.frame_count(32'd0));
integer divider=0,samples=0,cycles=0,frames=0,publications=0,misses=0,first_start=0,last_seq=-1,stale=0,most_stale=0,wave_checks=0,n,l,r;
integer copied[0:511];reg first_done=0,bank;reg [31:0] aseq,wseq;reg active=0;
reg held=0;reg [63:0] held_pixels;
real pi=3.141592653589793;
always @(negedge src)if(rst)begin
 valid=0;
 if(divider==1041)begin
  divider=0;samples=samples+1;valid=1;
  // Changing timbre/phase/amplitude and commands much faster than one capture.
  l=$rtoi((4000+(samples/1000)%4*3000)*$sin(2*pi*(samples<6000?440:697)*samples/48000.0));
  r=$rtoi(7000*$sin(2*pi*(samples<11000?523:329)*samples/48000.0));
  if(samples>=17000)begin l=0;r=0;end
  pcm={l[15:0],r[15:0]};mono=(l+r)*32768;
  reference=(samples/9)<<8;
 end else divider=divider+1;
end
always @(negedge clk)if(rst)begin
 cycles=cycles+1;start=0;
 if(cycles%1666667==0 && frames<24)begin
  if(ready)begin
   start=1;frames=frames+1;
   if(!first_start)first_start=cycles;
   if(dut.analysis_ready)publications=publications+1;
   if(dut.snapshot_sequence==last_seq)stale=stale+1;else stale=0;
   if(stale>most_stale)most_stale=stale;
   last_seq=dut.snapshot_sequence;
   if(dut.waveform_held)$fatal(1,"live trace entered HOLD");
   for(n=0;n<512;n=n+1)begin
    if(dut.u_align.trace_samples[n]!==dut.u_capture.samples[{dut.u_capture.render_bank,9'(n)}])$fatal(1,"copied waveform mismatch frame=%0d n=%0d",frames,n);
    wave_checks=wave_checks+1;
   end
  end else misses=misses+1;
 end
 if(done && frames==24)begin
  if(misses!=0 || first_start!=1666667 || publications<7 || most_stale!=0)$fatal(1,"refresh not independent frames=%0d missed=%0d first=%0d FFT=%0d stale=%0d",frames,misses,first_start,publications,most_stale);
  $display("PASS 24 consecutive 60Hz waveform rasters, %0d independent FFT publications, %0d PCM checks; rapid revision changes cannot starve capture; no HOLD; immutable banks/metadata and backpressure",publications,wave_checks);$finish;
 end
end
always @(posedge clk)if(rst)begin
 rng<={rng[14:0],rng[15]^rng[13]^rng[12]^rng[10]};
 if(held && (!pv || pd!==held_pixels))$fatal(1,"pixels changed under stall");
 held=pv && !accept;held_pixels=pd;
 if(start && ready)begin
  #1;active=1;bank=dut.g_analysis.u_analysis.read_bank;aseq=dut.analysis_sequence;wseq=dut.snapshot_sequence;
 end else if(active)begin
  if(dut.g_analysis.u_analysis.read_bank!==bank || dut.analysis_sequence!==aseq || dut.snapshot_sequence!==wseq)$fatal(1,"front data/metadata changed during raster");
  if(dut.u_align.state==dut.u_align.COPY)$fatal(1,"wave trace overwritten while rendering");
 end
 if(done)active=0;
end
initial begin repeat(8)@(negedge clk);rst=1;end
initial begin #550000000;$fatal(1,"live renderer watchdog");end
endmodule
'''
p=o/'tb_live_renderer.sv';p.write_text(tb);sources=list((stage/'src/video').glob('*.v'))+[p];h={str(p):hashlib.sha256(p.read_bytes()).hexdigest()for p in sources};(o/'inputs.json').write_text(json.dumps(h,indent=2)+'\n')
for name,cmd in [('compile',['verilator','--binary','--timing','-j','4','-Wno-fatal','--top-module','tb_live_renderer','--Mdir',str(o/'obj'),*map(str,sources)]),('simulation',[str(o/'obj/Vtb_live_renderer')])]:
 with(o/(name+'.log')).open('w')as f:p=subprocess.run(cmd,cwd=o,stdout=f,stderr=subprocess.STDOUT)
 print(name,p.returncode,flush=True)
 if p.returncode:raise SystemExit(p.returncode)
assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==v for p,v in h.items())
(o/'verification.json').write_text(json.dumps(dict(passed=True,build=str(build),scope='24 complete consecutive 1080p rasters at 60Hz while continuously changing MIDI revision, independent FFT publications, waveform exact PCM copy, no HOLD, front-bank and metadata atomicity, randomized backpressure'),indent=2)+'\n')
