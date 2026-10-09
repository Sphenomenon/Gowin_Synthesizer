#!/usr/bin/env python3
"""Exercise UINT32 terminal capture, short-beat zero padding and restart explicitly."""
from pathlib import Path
import argparse,tempfile,subprocess,json,hashlib
from cnn_ddr_pipeline_patch import TF_DMA,retime_tf_write_buffer,retime_tf_capture_limit
ROOT=Path(__file__).resolve().parents[1];BASE=ROOT/'results/song_guide_full85_clk50_20261007_084539_884006_route1/Prj1'
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path);a=p.parse_args()
original=(BASE/TF_DMA).read_text();patched=retime_tf_capture_limit(retime_tf_write_buffer(original))
tb=r'''`timescale 1ns/1ps
module tb;
reg clk=0,rst=0,restart=0,valid=0;reg [7:0] byte_data=0;
wire err;wire [255:0] wdata;wire en,wr;wire [2:0] cmd;wire [28:0] addr;
always #5 clk=~clk;
tf_audio_ddr_dma #(.AUDIO_BANK_BYTES(128)) dut(
 .clk(clk),.rst_n(rst),.mem_ready(1'b1),.capture_done_toggle(1'b0),.restart_toggle(restart),.file_size_bytes(32'd0),
 .fifo_in_empty(1'b1),.fifo_in_rd_valid(valid),.fifo_in_rd_data(byte_data),.fifo_in_rd_en(),
 .playback_start_toggle(),.playback_done_toggle(),.fifo_out_full(1'b1),.fifo_out_wr_en(),.fifo_out_wr_data(),
 .app_cmd(cmd),.app_en(en),.app_addr(addr),.app_wdata(wdata),.app_rdy(1'b0),.app_wren(wr),.app_wend(),.app_wrdy(1'b0),
 .app_rvalid(1'b0),.app_rdata(256'd0),.capacity_error(err),.bank0_valid(),.bank1_valid(),.file_size_valid(),.staged_file_size());
initial begin
 repeat(5)@(negedge clk);rst=1;repeat(5)@(negedge clk);
 // Fast-forward only legal counters, not the limit predictor. The final two
 // queued FIFO replies model the terminal byte and one rejected overflow.
 dut.capture_byte_count=32'hffff_fffe;dut.read_total_bytes=32'hffff_ffe0;
 dut.write_total_bytes=32'hffff_ffe0;dut.write_count=30;dut.in_read_wait=1;
 valid=1;byte_data=8'haa;@(negedge clk);byte_data=8'hbb;@(negedge clk);valid=0;
 repeat(2)@(negedge clk);
 if(!err || dut.capture_byte_count!==32'hffff_ffff || dut.write_buf[247:240]!==8'haa || dut.write_buf[255:248]!==0 || dut.write_count!==31)
  $fatal(1,"terminal capture/overflow corrupted staged bytes/count");
 restart=1;repeat(8)@(negedge clk);
 if(err || dut.capture_byte_count || dut.write_buf || dut.write_count)$fatal(1,"restart failed to clear terminal epoch");
 valid=1;byte_data=8'hcd;@(negedge clk);valid=0;repeat(2)@(negedge clk);
 if(dut.capture_byte_count!==1 || dut.write_buf[7:0]!==8'hcd)$fatal(1,"new epoch retained terminal limit");
 $display("PASS TF UINT32 terminal byte accepted,overflow rejected with shortbeatpadding,restart accepts fresh byte");$finish;
end
endmodule'''
cases=[]
with tempfile.TemporaryDirectory(prefix='cnn_tf_capture_limit_') as tmp:
 t=Path(tmp);(t/'tb.sv').write_text(tb)
 for label,text in [('original',original),('registered_limit',patched)]:
  (t/'dma.v').write_text(text);exe=t/'sim'
  c=subprocess.run(['iverilog','-g2012','-I',str(BASE),'-s','tb','-o',str(exe),str(t/'tb.sv'),str(t/'dma.v')],capture_output=True,text=True);assert c.returncode==0,c.stdout+c.stderr
  v=subprocess.run(['vvp',str(exe)],capture_output=True,text=True,timeout=30);assert v.returncode==0 and 'PASS TF UINT32' in v.stdout,v.stdout+v.stderr
  cases.append(dict(source=label,passed=True,log=v.stdout.strip()))
 r=dict(passed=True,hardware_tested=False,pcm_saved=False,cases=cases,patched_sha256=hashlib.sha256(patched.encode()).hexdigest())
 if a.output:a.output.write_text(json.dumps(r,indent=2)+'\n')
 print(json.dumps(r,indent=2))
