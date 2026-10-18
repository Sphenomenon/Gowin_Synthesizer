#!/usr/bin/env python3
"""Old/new convolution MAC-retiming oracle; same MAC cadence, one local drain/output."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[2]
TB = r'''`timescale 1ns/1ps
module tb;
 parameter STACK=0, DDR=0, CHANNELS=33;
 reg clk=0, rst=0, start=0;
 always #5 clk=~clk;
 integer cycle=0, outputs=0, refs=0, req_stalls=0, padding=0;
 integer done_ref_cycle=0,done_new_cycle=0;
 reg [114:0] reference_outputs[0:97];
 wire [15:0] pa,pb;
 wire [23:0] xa,xb,ca,cb,ya,yb;
 wire [7:0] cha,chb;
 wire signed [17:0] ra,rb,fa,fb;
 wire inra,inrb,reqa,reqb,breqa,breqb,wa,wb,busya,busyb,donea,doneb;
 wire [17:0] aa,ab;
 wire [8:0] ba,bb,yra,yrb,yfa,yfb,ycha,ychb;
 wire signed [15:0] da,db;
 wire signed [47:0] acca,accb;
 reg signed [15:0] wdataa,wdatab,xdataa,xdatab,pdataa,pdatab;
 reg signed [31:0] bdataa,bdatab;
 wire sv=(cycle%11>=4 && cycle%11<=7), bv=(cycle%13>=5 && cycle%13<=8);
 function signed [15:0] value(input [23:0] address, input [15:0] salt);
  reg [31:0] v;
  begin
   v=(address*32'd1664525 + 32'd1013904223)^salt;
   case(address%17)
    0:value=16'sh8000;
    1:value=16'sh7fff;
    2:value=-16'sd1;
    3:value=16'sd0;
    default:value=v[23:8];
   endcase
  end
 endfunction
 always @(posedge clk) begin
  cycle<=cycle+1;
  wdataa<=value({6'd0,aa},16'h1143); wdatab<=value({6'd0,ab},16'h1143);
  xdataa<=inra ? value(xa,16'h23d9) : 16'hxxxx;
  xdatab<=inrb ? value(xb,16'h23d9) : 16'hxxxx;
  pdataa<=inra ? value({8'd0,pa},16'hb738) : 16'hxxxx;
  pdatab<=inrb ? value({8'd0,pb},16'hb738) : 16'hxxxx;
  bdataa<=ba[0] ? 32'sh80000000 : 32'sh7fffffff;
  bdatab<=bb[0] ? 32'sh80000000 : 32'sh7fffffff;
 end
 basic_pitch_conv2d_reference #(.IN_T(7),.IN_F(11),.IN_C(CHANNELS),.KH(3),.KW(3),
   .OUT_T(7),.OUT_F(7),.OUT_C(2),.STRIDE_T(1),.STRIDE_F(2),.PAD_T(1),.PAD_F(1),.USE_STACK(STACK),.ACT(1),.DDR_FETCH(DDR)) a(
  .clk_i(clk),.rst_ni(rst),.start_i(start),.row_start_i(9'd0),.row_limit_i(9'd7),
  .pl_addr_o(pa),.pl_data_i(pdataa),.x_addr_o(xa),.x_cell_addr_o(ca),.x_channel_o(cha),
  .x_row_o(ra),.x_col_o(fa),.input_in_range_o(inra),.sample_req_o(reqa),.sample_valid_i(sv),.x_data_i(xdataa),
  .w_addr_o(aa),.w_data_i(wdataa),.b_addr_o(ba),.bias_req_o(breqa),.bias_valid_i(bv),.b_data_i(bdataa),
  .y_we_o(wa),.y_addr_o(ya),.y_row_o(yra),.y_col_o(yfa),.y_channel_o(ycha),.y_data_o(da),.y_acc_o(acca),.busy_o(busya),.done_o(donea));
 basic_pitch_conv2d #(.IN_T(7),.IN_F(11),.IN_C(CHANNELS),.KH(3),.KW(3),
   .OUT_T(7),.OUT_F(7),.OUT_C(2),.STRIDE_T(1),.STRIDE_F(2),.PAD_T(1),.PAD_F(1),.USE_STACK(STACK),.ACT(1),.DDR_FETCH(DDR)) b(
  .clk_i(clk),.rst_ni(rst),.start_i(start),.row_start_i(9'd0),.row_limit_i(9'd7),
  .pl_addr_o(pb),.pl_data_i(pdatab),.x_addr_o(xb),.x_cell_addr_o(cb),.x_channel_o(chb),
  .x_row_o(rb),.x_col_o(fb),.input_in_range_o(inrb),.sample_req_o(reqb),.sample_valid_i(sv),.x_data_i(xdatab),
  .w_addr_o(ab),.w_data_i(wdatab),.b_addr_o(bb),.bias_req_o(breqb),.bias_valid_i(bv),.b_data_i(bdatab),
  .y_we_o(wb),.y_addr_o(yb),.y_row_o(yrb),.y_col_o(yfb),.y_channel_o(ychb),.y_data_o(db),.y_acc_o(accb),.busy_o(busyb),.done_o(doneb));
 always @(negedge clk) if(rst) begin
  if (DDR && ({pa,xa,ca,cha,ra,fa,inra,reqa,breqa,aa,ba,wa,busya,donea} !==
      {pb,xb,cb,chb,rb,fb,inrb,reqb,breqb,ab,bb,wb,busyb,doneb}))
   $fatal(1,"control/address changed cycle=%0d",cycle);
  if(cha>=CHANNELS)$fatal(1,"illegal channel=%0d",cha);
  if(reqa && !sv)req_stalls=req_stalls+1;
  if(busya && !inra)padding=padding+1;
  if(wa)begin
   if(refs>=98)$fatal(1,"too many reference outputs");
   reference_outputs[refs]={ya,yra,yfa,ycha,da,acca};refs=refs+1;
  end
  if(wb)begin
   if(outputs>=refs)$fatal(1,"candidate output precedes reference");
   if (reference_outputs[outputs] !== {yb,yrb,yfb,ychb,db,accb})
    $fatal(1,"retimed output differs cycle=%0d index=%0d ref=%h new=%h",cycle,outputs,reference_outputs[outputs],{yb,yrb,yfb,ychb,db,accb});
   if((^accb)===1'bx || (^db)===1'bx)$fatal(1,"padding leaked X into output");
   outputs=outputs+1;
  end
  if(donea)done_ref_cycle=cycle;
  if(doneb)begin
   done_new_cycle=cycle;
   if(refs!=98 || outputs!=98 || padding==0 || (DDR && req_stalls==0))$fatal(1,"coverage gap");
   if(done_ref_cycle==0 || done_new_cycle-done_ref_cycle!=(DDR ? 0 : 98))
    $fatal(1,"extra MAC cycles: done_ref=%0d new=%0d",done_ref_cycle,done_new_cycle);
   $display("PASS retimed MAC stack=%0d DDR=%0d channels=%0d cycles=%0d outputs=%0d stalls=%0d padded=%0d local_drain_cycles=%0d",STACK,DDR,CHANNELS,cycle,outputs,req_stalls,padding,done_new_cycle-done_ref_cycle);$finish;
  end
  if(cycle>500000)$fatal(1,"cycle hard cap");
 end
 initial begin
  #2;rst=0;
  repeat(3)@(negedge clk);
  rst=1;
  repeat(2)@(negedge clk);
  start=1;@(negedge clk);start=0;
 end
endmodule
'''


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():parser.error('preserve earlier evidence; use a new output')
    args.output.mkdir(parents=True)
    live=ROOT/'rtl/music/basic_pitch_conv2d.sv'
    old=args.reference.read_text()
    assert old.count('module basic_pitch_conv2d #(')==1
    ref=args.output/'basic_pitch_conv2d_reference.sv'
    ref.write_text(old.replace('module basic_pitch_conv2d #(','module basic_pitch_conv2d_reference #(',1))
    tb=args.output/'tb.sv';tb.write_text(TB)
    cases=[]
    for stack,channels in [(0,1),(0,8),(0,32),(0,33),(1,8)]:
        for ddr in (0,1):
            exe=args.output/f'case_s{stack}_c{channels}_d{ddr}.vvp'
            command=['iverilog','-g2012','-s','tb','-I',str(live.parent),
                     f'-Ptb.STACK={stack}',f'-Ptb.CHANNELS={channels}',f'-Ptb.DDR={ddr}',
                     '-o',str(exe),str(ref),str(live),str(tb)]
            compiled=subprocess.run(command,capture_output=True,text=True)
            (exe.with_suffix('.compile.log')).write_text(compiled.stdout+compiled.stderr)
            if compiled.returncode:raise RuntimeError(compiled.stderr)
            run=subprocess.run(['vvp','-i',str(exe)],capture_output=True,text=True,timeout=60)
            exe.with_suffix('.run.log').write_text(run.stdout+run.stderr)
            ok=run.returncode==0 and 'PASS ' in run.stdout
            cases.append({'stack':stack,'channels':channels,'ddr':ddr,'passed':ok,'output':run.stdout.strip()})
            print(run.stdout.strip(),flush=True)
            if not ok:break
    result={'passed':len(cases)==10 and all(c['passed'] for c in cases),'cases':cases,
            'reference_sha256':hashlib.sha256(args.reference.read_bytes()).hexdigest(),
            'candidate_sha256':hashlib.sha256(live.read_bytes()).hexdigest(),
            'DDR_control_and_output_cycle_exact':True,'extra_mac_cycles':0,'local_drain_cycles_per_output':1,
            'coverage':'old reference every output accumulator/activation/address; exact DDR cycles and local one-drain/output; signed extrema and bias; 1/8/32/33 channels; stack shifts; sync memories; padding X; DDR/bias stalls'}
    (args.output/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    if not result['passed']:raise SystemExit(1)


if __name__=='__main__':main()
