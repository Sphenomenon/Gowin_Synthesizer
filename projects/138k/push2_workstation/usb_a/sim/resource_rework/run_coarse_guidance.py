#!/usr/bin/env python3
"""Coarse-score retention, DDR stalls and exact rational CQT center tests."""
from pathlib import Path
import subprocess,json
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'out/resource_coarse_guidance'
def main():
 OUT.mkdir(parents=True,exist_ok=True)
 tb=r'''`timescale 1ns/1ps
`include "basic_pitch_ddr_map.svh"
module tb_coarse;
parameter integer EXT=0;
reg clk=0,rst=0,ready=0,rsp=0;reg[15:0] data=0;wire req,wr,sv,done,rv,complete;wire[31:0] addr;wire[6:0] sn,rn;wire[15:0] conf,frame;
reg[6:0] expected[0:7];integer n=0,cycle=0,timer=0,reads=0;
always #5 clk=~clk;
wire mr=timer==0 && !rsp && cycle%5!=0;
basic_pitch_viterbi #(.FRAMES(8),.USE_EXTERNAL_STATE(EXT),.COARSE_GUIDANCE(1)) dut(
.clk_i(clk),.rst_ni(rst),.start_i(1'b0),.active_i(1'b1),.note_valid_i(1'b0),.note_idx_i(7'd0),.note_q_i(16'd0),.onset_valid_i(1'b0),.onset_idx_i(7'd0),.onset_q_i(16'd0),.frame_valid_i(1'b0),.frame_last_i(1'b0),.frame_ready_o(),.result_valid_o(rv),.result_note_o(rn),.result_conf_o(conf),.result_frame_o(frame),.score_valid_o(sv),.score_ready_i(ready),.score_note_o(sn),.score_complete_o(complete),.done_o(done),.busy_o(),.mem_req_o(req),.mem_write_o(wr),.mem_byte_addr_o(addr),.mem_wdata_o(),.mem_ready_i(mr),.mem_rsp_valid_i(rsp),.mem_rdata_i(data));
always @(posedge clk)if(rst)begin
 cycle=cycle+1;rsp<=0;
 if(EXT && req && mr)begin
  if(wr)$fatal(1,"unexpected write during path commit");
  if(addr>=`BP_DDR_NOTE_BYTE_BASE && addr<`BP_DDR_NOTE_BYTE_BASE+32'h100000)data<=16'h5000;
  else if(addr>=`BP_DDR_ONSET_BYTE_BASE && addr<`BP_DDR_ONSET_BYTE_BASE+32'h100000)data<=0;
  else $fatal(1,"bad coarse DDR address %h",addr);
  timer<=2+cycle%4;reads=reads+1;
 end else if(timer>0)begin timer<=timer-1;if(timer==1)rsp<=1;end
 if(sv && ready)begin if(n>=4 || sn!==expected[n])$fatal(1,"score %0d got=%0d expected=%0d",n,sn,expected[n]);n=n+1;end
end
initial begin
 expected[0]=60;expected[1]=62;expected[2]=64;expected[3]=65;
 repeat(4)@(negedge clk);rst=1;@(negedge clk);
 // Single-frame changes, silence in the middle and a final-frame-only pitch.
 dut.path_mem[0]=39;dut.path_mem[1]=41;dut.path_mem[2]=88;dut.path_mem[3]=43;
 dut.path_mem[4]=43;dut.path_mem[5]=88;dut.path_mem[6]=88;dut.path_mem[7]=44;
 for(integer k=0;k<8;k=k+1)for(integer j=0;j<88;j=j+1)begin dut.note_mem[k*88+j]=16'h5000;dut.onset_hot_mem[k*88+j]=0;end
 dut.frame_cnt=7;dut.cmt_idx=0;dut.cmt_found=0;dut.state=8;
 repeat(30)@(negedge clk);
 if(!sv || sn!=60 || n!=0)$fatal(1,"coarse first note must wait for ready");
 for(integer k=0;k<250;k=k+1)begin @(negedge clk);ready=k%3!=0;end
 if(n!=4 || !done || !rv || rn!=60 || conf!=16'h5000 || frame!=0)$fatal(1,"coarse commit failed count=%0d",n);
 // A phrase containing only the last sampled pitch must still produce a target.
 @(negedge clk);ready=0;for(integer k=0;k<7;k=k+1)dut.path_mem[k]=88;
 dut.path_mem[7]=39;dut.cmt_idx=0;dut.cmt_found=0;dut.state=8;n=0;
 repeat(80)@(negedge clk);
 if(!sv || sn!=60 || !rv || frame!=7)$fatal(1,"last-frame-only pitch lost");
 ready=1;repeat(20)@(negedge clk);if(n!=1)$fatal(1,"last pitch duplicates");
 $display("PASS coarse guidance EXT=%0d: isolated and final sampled pitches retained, silence, dedup, stalls; reads=%0d",EXT,reads);$finish;
end
endmodule
module tb_centers;
reg clk=0;
basic_pitch_cqt_engine #(.WIN_LEN(44100),.HOP_NUMERATOR(22050),.HOP_DENOMINATOR(4)) dut(.clk_i(clk),.rst_ni(1'b0));
integer expected,count=0;
initial begin
 for(integer o=0;o<9;o=o+1)for(integer t=0;t<8;t=t+1)for(integer k=0;k<256;k=k+1)begin
  dut.oct=5'(o);dut.t_cnt=9'(t);dut.k_cnt=9'(k);#1;expected=((t*22050/4)>>o)+k-128;
  if($signed(dut.raw_idx)!==expected)$fatal(1,"bad rational center oct=%0d frame=%0d k=%0d idx=%0d expected=%0d",o,t,k,$signed(dut.raw_idx),expected);
  count=count+1;
 end
 $display("PASS rational CQT centers: %0d indices across nine octaves; centers at 0,250,...1750ms",count);$finish;
end
endmodule
'''
 (OUT/'tb.sv').write_text(tb)
 results=[]
 for top,params,src in [('tb_coarse',['-Ptb_coarse.EXT=0'],['basic_pitch_viterbi.sv']),('tb_coarse',['-Ptb_coarse.EXT=1'],['basic_pitch_viterbi.sv']),('tb_centers',[],['basic_pitch_cqt_engine.sv'])]:
  label=top+('_ddr' if '1' in ''.join(params) else '_local');binary=OUT/label
  cmd=['iverilog','-g2012','-I',str(ROOT/'rtl/music'),'-s',top,'-o',str(binary)]+params+[str(ROOT/'rtl/music'/s) for s in src]+[str(OUT/'tb.sv')]
  log=''
  for command in [cmd,['vvp',str(binary)]]:
   p=subprocess.run(command,cwd=ROOT,text=True,capture_output=True);log+=p.stdout+p.stderr
   if p.returncode:break
  (OUT/(label+'.log')).write_text(log);print(log[-1800:]);results.append(dict(test=label,passed=p.returncode==0 and 'PASS ' in log))
 (OUT/'summary.json').write_text(json.dumps(results,indent=2)+'\n')
 if not all(r['passed'] for r in results):raise SystemExit(1)
if __name__=='__main__':main()
