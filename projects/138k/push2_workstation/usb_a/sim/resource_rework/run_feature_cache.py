#!/usr/bin/env python3
"""Five-bank cache: all layers, halo padding, DDR stalls and vendor 16-bit RAM."""
from pathlib import Path
import subprocess,json,argparse
ROOT=Path(__file__).resolve().parents[2]
def main():
 a=argparse.ArgumentParser();a.add_argument('--vendor',action='store_true');a=a.parse_args()
 out=ROOT/('out/resource_feature_vendor' if a.vendor else 'out/resource_feature_cache');out.mkdir(parents=True,exist_ok=True)
 tb=r'''`timescale 1ns/1ps
`include "basic_pitch_ddr_map.svh"
module tb_feature;
reg clk=0,rst=0,start=0,read_valid=0,rsp=0;reg[1:0] kind=0;reg signed[10:0] row=0,col=0;reg[14:0] ra=0;reg[15:0] data=0;
wire ld,overflow,req,wr;wire[31:0] addr;wire[15:0] wd;wire signed[15:0] rd;
integer cycle=0,timer=0,checks=0,transactions=0,freq_bins,channels,gr,gc,expected;
always #5 clk=~clk;
wire ready=timer==0 && !rsp && cycle%5!=0;
function automatic [15:0] contents(input [31:0] byte_address);
 contents=16'((byte_address>>1) ^ (byte_address>>11) ^ 32'h3e912dd7);
endfunction
basic_pitch_feature_ddr #(.FRAMES(8),.TILE_COLS(20)) dut(.clk_i(clk),.rst_ni(rst),
.contour_we_i(1'b0),.notes_we_i(1'b0),.onset_we_i(1'b0),.load_start_i(start),.load_kind_i(kind),.load_start_row_i(row),.load_rows_i(4'd7),.load_start_col_i(col),.load_cols_i(9'd20),.load_done_o(ld),.overflow_o(overflow),.read_valid_i(read_valid),.read_addr_i(ra),.read_data_o(rd),.mem_req_o(req),.mem_write_o(wr),.mem_byte_addr_o(addr),.mem_wdata_o(wd),.mem_ready_i(ready),.mem_rsp_valid_i(rsp),.mem_rdata_i(data));
always @(posedge clk)if(rst)begin
 cycle=cycle+1;rsp<=0;
 if(req && ready)begin
  if(wr)$fatal(1,"unexpected write");data<=contents(addr);timer<=1+cycle%4;transactions=transactions+1;
 end else if(timer>0)begin timer<=timer-1;if(timer==1)rsp<=1;end
 if(overflow)$fatal(1,"cache overflow");
end
initial begin
 repeat(3)@(negedge clk);rst=1;
 for(integer layer=0;layer<3;layer=layer+1)for(integer pos=0;pos<3;pos=pos+1)begin
  kind=2'(layer);freq_bins=layer==0?264:88;channels=layer==0?8:32;
  row=pos==0?-3:pos==1?1:5;col=pos==0?-2:pos==1?14:freq_bins-10;
  @(negedge clk);start=1;@(negedge clk);start=0;wait(ld);@(negedge clk);
  for(integer rr=0;rr<7;rr=rr+1)for(integer cc=0;cc<20;cc=cc+1)for(integer ch=0;ch<channels;ch=ch+1)begin
   ra=15'((rr*20+cc)*channels+ch);read_valid=1;gr=$signed(row)+rr;gc=$signed(col)+cc;
   expected=0;
   if(gr>=0 && gr<8 && gc>=0 && gc<freq_bins)expected=contents((layer==0?`BP_DDR_NN_CONTOUR_BYTE_BASE:layer==1?`BP_DDR_NN_NOTES_BYTE_BASE:`BP_DDR_NN_ONSET_BYTE_BASE)+(((gr*freq_bins+gc)*channels+ch)*2));
   @(negedge clk);if(rd!==16'(expected))$fatal(1,"cache mismatch layer=%0d row=%0d col=%0d ch=%0d idx=%0d got=%h expected=%h",layer,gr,gc,ch,ra,rd,16'(expected));checks=checks+1;
  end
  read_valid=0;@(negedge clk);if(rd!==0)$fatal(1,"invalid read must be zero");
  read_valid=1;ra=15'd4480;@(negedge clk);if(rd!==0)$fatal(1,"out of range read");read_valid=0;
 end
 $display("PASS feature cache: %0d words checked, %0d variable-latency DDR reads, five banks, all three layers, row/frequency halo boundaries",checks,transactions);$finish;
end
initial begin repeat(1000000)@(posedge clk);$fatal(1,"cache test timeout");end
endmodule
'''
 sources=[ROOT/'rtl/music/basic_pitch_feature_ddr.sv',ROOT/'rtl/memory/workstation_sdp.sv']
 if a.vendor:
  lib=Path.home()/'.local/opt/gowin-1.9.12.03/IDE/simlib/gw5a/prim_sim.v';text=lib.read_text();parts=[]
  for name in ('GSR','SDPB'):
   start=text.index('module '+name+' (');end=text.index('endmodule',start)+len('endmodule');parts.append(text[start:end])
  (out/'vendor.v').write_text('\n'.join(parts));sources.append(out/'vendor.v');tb=tb.replace('module tb_feature;','module tb_feature;\nGSR GSR(.GSRI(1\'b1));')
 (out/'tb.sv').write_text(tb);sources.append(out/'tb.sv')
 cmd=['verilator','--binary','--timing','--build-jobs','3','-Wno-fatal','-I'+str(ROOT/'rtl/music'),'--top-module','tb_feature','--Mdir',str(out/'obj_dir')]+(['-DWORKSTATION_SDP_VENDOR_SIM'] if a.vendor else [])+list(map(str,sources))
 for label,command in [('build',cmd),('simulation',[str(out/'obj_dir/Vtb_feature')])]:
  with (out/(label+'.log')).open('w') as log:p=subprocess.run(command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
  if p.returncode:raise RuntimeError((out/(label+'.log')).read_text()[-5000:])
 log=(out/'simulation.log').read_text();print(log)
 (out/'summary.json').write_text(json.dumps(dict(passed='PASS feature cache:' in log,vendor_model=a.vendor,log=log.strip()),indent=2)+'\n')
if __name__=='__main__':main()
