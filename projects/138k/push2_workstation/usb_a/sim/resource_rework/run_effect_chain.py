#!/usr/bin/env python3
"""All effect masks/orders with actual DDR delay DMA; deadline and clear checks."""
from pathlib import Path
import subprocess,json,hashlib
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'out/resource_effect_chain'
BASE=ROOT/'results/timing_p27_uart_cdc_route1_20261018_142516_456857/Prj1'
def main():
 OUT.mkdir(parents=True,exist_ok=True)
 tb=r'''`timescale 1ns/1ps
module tb_effect_chain;
reg clk=0,mclk=0,rst=0,mrst=0,clear=0,valid=0;always #5 clk=~clk;always #7 mclk=~mclk;
reg signed[31:0] synth=0,l=0,r=0,vl=0,vr=0;reg[2:0] mask=0;reg[5:0] order=6'b10_01_00;
wire ready,ov,clip;wire signed[31:0] ol,orr;
wire wv,wp,rp,rr;wire[64:0] wd,rd;wire req,wr;wire[28:0] addr;wire[255:0] data;wire[31:0] wm;reg drsp=0;reg[255:0] drdata=0;wire[7:0] status;
reg[255:0] memory[0:4095];integer timer=0,mcycle=0;reg[11:0] pending=0;wire mr=timer==0 && !drsp && mcycle%5!=0;
stereo_effects #(.VECTOR_ENABLE(1)) dut(.clk_i(clk),.rst_ni(rst),.clear_i(clear),.valid_i(valid),.synth_i(synth),.pcm_left_i(l),.pcm_right_i(r),.vector_left_i(vl),.vector_right_i(vr),.synth_gain_i(16'd8192),.pcm_gain_i(16'd8192),.effect_mask_i(mask),.effect_order_i(order),.ready_o(ready),.valid_o(ov),.left_o(ol),.right_o(orr),.clip_o(clip),.mem_clk_i(mclk),.mem_rst_ni(mrst),.dwr_valid_o(wv),.dwr_data_o(wd),.dwr_pop_i(wp),.drd_push_i(rp),.drd_data_i(rd),.drd_ready_o(rr));
delay_ddr_dma dma(.clk_i(mclk),.rst_ni(mrst),.dwr_valid_i(wv),.dwr_data_i(wd),.dwr_pop_o(wp),.drd_push_o(rp),.drd_data_o(rd),.drd_ready_i(rr),.ddr_req_o(req),.ddr_write_o(wr),.ddr_address_o(addr),.ddr_data_o(data),.ddr_mask_o(wm),.ddr_ready_i(mr),.ddr_response_i(drsp),.ddr_read_data_i(drdata),.debug_status_o(status));
always @(posedge mclk)if(mrst)begin
 mcycle=mcycle+1;drsp<=0;
 if(req && mr)begin
  if(wr)memory[addr[14:3]]<=data;else begin pending<=addr[14:3];timer<=2+mcycle%5;end
 end else if(timer>0)begin timer<=timer-1;if(timer==1)begin drsp<=1;drdata<=memory[pending];end end
end
integer frames=0,maxlat=0,latency=0;reg[31:0] seed=1;reg[5:0] orders[0:5];
task automatic sample_one;
 begin
  @(negedge clk);if(!ready)$fatal(1,"chain busy at next sample");
  valid=1;@(negedge clk);valid=0;latency=1;
  while(!ov)begin @(negedge clk);latency=latency+1;if(latency>=1600)$fatal(1,"48kHz deadline missed");end
  if($isunknown({ol,orr,clip}))$fatal(1,"unknown output");
  if(dut.processed!=3'b111)$fatal(1,"effect maintenance dropped");
  if(latency>maxlat)maxlat=latency;
  if(dut.delay_stage.debug_status_o[3:2]!=0)$fatal(1,"DDR delay underrun/overflow at frame %0d status=%h",frames,dut.delay_stage.debug_status_o);
  repeat(1600-latency)@(negedge clk);frames=frames+1;
 end
endtask
initial begin
 orders[0]=6'b10_01_00;orders[1]=6'b01_10_00;orders[2]=6'b10_00_01;
 orders[3]=6'b00_10_01;orders[4]=6'b01_00_10;orders[5]=6'b00_01_10;
 repeat(5)@(negedge clk);rst=1;mrst=1;
 for(integer o=0;o<6;o=o+1)for(integer m=0;m<8;m=m+1)begin
  order=orders[o];mask=3'(m);
  for(integer n=0;n<256;n=n+1)begin
   seed=seed*1664525+1013904223;synth=$signed(seed)>>>5;l=$signed(seed^32'h612ae345)>>>4;r=-l;vl=synth>>>1;vr=-vl;sample_one();
  end
 end
 // Settle all bypass gains and check the dry mix including synth/vector/PCM.
 mask=0;for(integer n=0;n<128;n=n+1)sample_one();
 if(ol!==32'(audio_math_pkg::rshift(64'($signed(synth))+64'($signed(l))+64'($signed(vl)),2)) || orr!==32'(audio_math_pkg::rshift(64'($signed(synth))+64'($signed(r))+64'($signed(vr)),2)))$fatal(1,"bypass mix incorrect got=%h %h",ol,orr);
 // Clear in flight: the chain must abort and restart cleanly.
 @(negedge clk);valid=1;@(negedge clk);valid=0;repeat(13)@(negedge clk);clear=1;
 @(negedge clk);clear=0;repeat(1600)@(negedge clk);if(!ready || ov)$fatal(1,"clear failed");
 synth=0;l=0;r=0;vl=0;vr=0;sample_one();if(ol!==0 || orr!==0)$fatal(1,"clear leaked stale tail");
 $display("PASS effect chain: six orders x eight masks, %0d stereo frames, max_latency=%0d/1600 cycles, actual dual-clock DDR delay, synth/PCM/vector dry mix, abort/clear",frames,maxlat);$finish;
end
endmodule
'''
 (OUT/'tb.sv').write_text(tb)
 sources=[BASE/'legacy/rtl/audio/audio_math_pkg.sv',ROOT/'rtl/memory/workstation_sdp.sv',ROOT/'rtl/memory/workstation_sdp_banked.sv',ROOT/'rtl/audio/serial_spatial_reverb.sv',ROOT/'rtl/audio/stereo_effects.sv',ROOT/'rtl/audio/delay_ddr/serial_delay_effect_ddr.sv',ROOT/'rtl/audio/delay_ddr/delay_ddr_dma.sv',ROOT/'rtl/music/music_async_fifo.sv',OUT/'tb.sv']
 cmd=['verilator','--binary','--timing','--build-jobs','3','-Wno-fatal','-I'+str(ROOT),'--top-module','tb_effect_chain','--Mdir',str(OUT/'obj_dir')]+list(map(str,sources))
 for label,command in [('build',cmd),('simulation',[str(OUT/'obj_dir/Vtb_effect_chain')])]:
  with (OUT/(label+'.log')).open('w') as log:p=subprocess.run(command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
  if p.returncode:raise RuntimeError((OUT/(label+'.log')).read_text()[-5000:])
 log=(OUT/'simulation.log').read_text();print(log);passed='PASS effect chain:' in log
 (OUT/'summary.json').write_text(json.dumps(dict(passed=passed,log=log.strip(),source_sha256={str(x):hashlib.sha256(x.read_bytes()).hexdigest() for x in sources+[ROOT/'rtl/audio/spatial_room_preset.svh']},hardware_tested=False),indent=2)+'\n')
 if not passed:raise SystemExit(1)
if __name__=='__main__':main()
