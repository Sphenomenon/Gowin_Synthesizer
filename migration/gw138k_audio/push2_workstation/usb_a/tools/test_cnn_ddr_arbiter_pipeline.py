#!/usr/bin/env python3
"""Independent command/masked-memory/response scoreboard for shared DDR pipeline."""
from pathlib import Path
import argparse,json,subprocess,tempfile
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path);a=p.parse_args()
# Connections are generated mechanically; stimulus and scoreboard do not use
# DUT owner/priority/tag state. All eight client interfaces are observed.
clients=['bist','scan','cpu','writer','audio','music','delay','display']
connections=['.clk(clk)', '.reset_n(rst)', '.bist_done(bd)']
for i,c in enumerate(clients):
 connections += [f'.{c}_valid(valid[{i}])',f'.{c}_address(address[{i}])',f'.{c}_ready(ready[{i}])']
 if c not in ('scan','display'):connections += [f'.{c}_data(data[{i}])']
 if c not in ('scan','display','writer'):connections += [f'.{c}_write(write[{i}])']
 if c in ('music','cpu'):connections += [f'.{c}_mask(mask[{i}])']
 if c!='writer':connections += [f'.{c}_response(response[{i}])']
connections += ['.app_cmd(cmd)','.app_en(en)','.app_wren(wren)','.app_wend(wend)', '.app_address(native_address)','.app_data(native_data)','.app_mask(native_mask)', '.app_ready(native_ready)','.app_write_ready(native_wrdy)','.app_response(native_rsp)', '.app_response_data(native_rddata)','.response_data(client_rddata)','.response_fault(fault)']
text=r'''
`timescale 1ns/1ps
module tb_arbiter_pipeline;
parameter integer BITS=5,SEED=7;
reg clk=0,rst=0,bd=0;
always #5 clk=~clk;
reg [7:0] valid=0,write=0;
reg [28:0] address[0:7];reg [255:0] data[0:7];reg [31:0] mask[0:7];
wire [7:0] ready,response;
assign response[3]=0;
wire [2:0] cmd;wire en,wren,wend;wire [28:0] native_address;
wire [255:0] native_data,client_rddata;wire [31:0] native_mask;wire fault;
reg native_ready=0,native_wrdy=0,native_rsp=0;reg [255:0] native_rddata=0;
__INSTANCE__
reg [255:0] model[0:4095],physical[0:4095];
reg [28:0] eq_addr[0:100000];reg [255:0] eq_data[0:100000];reg [31:0] eq_mask[0:100000];reg eq_write[0:100000];
reg [255:0] er_data[0:100000];integer er_owner[0:100000];
reg [255:0] nr_data[0:100000];integer nr_cycle[0:100000];
integer accept_count=0,issue_count=0,read_count=0,returned=0,nr_in=0,nr_out=0,cycle=0;
integer per_client[0:7],sequence_no[0:7];integer max_tags=0,blocked=0;
reg [31:0] random_state=SEED;
reg stalled=0;reg [319:0] held;
function [255:0] pattern(input integer owner,input integer seq);
 for(integer k=0;k<8;k=k+1)pattern[k*32+:32]=(seq*32'h9e3779b9)^(owner*32'h12121212)^k;
endfunction
always @(posedge clk)begin
 if(rst)begin
  cycle=cycle+1;
  if(stalled && held !== {cmd,native_address,native_data,native_mask})$fatal(1,"command changed under native stall");
  stalled=dut.command_full && !en;held={cmd,native_address,native_data,native_mask};
  if($countones(ready)>1 || $countones(response)>1)$fatal(1,"nonexclusive handshake/response");
  for(integer i=0;i<8;i=i+1)if(response[i])begin
   if(returned>=read_count || er_owner[returned]!=i || er_data[returned]!==client_rddata)$fatal(1,"response lost/reordered/memory mismatch at%0d owner%0d wanted%0d",returned,i,er_owner[returned]);
   returned=returned+1;
  end
  if(en)begin
   if(issue_count>=accept_count || native_address!==eq_addr[issue_count] || native_mask!==eq_mask[issue_count] || native_data!==eq_data[issue_count] || (cmd==0)!==eq_write[issue_count])$fatal(1,"native command order/data changed at%0d",issue_count);
   if(wren!==wend || wren!==(cmd==0))$fatal(1,"write handshake mismatch");
   if(cmd==0)begin
    for(integer k=0;k<32;k=k+1)if(!native_mask[k])physical[native_address[14:3]][k*8+:8]=native_data[k*8+:8];
   end else begin nr_data[nr_in]=physical[native_address[14:3]];nr_cycle[nr_in]=cycle;nr_in=nr_in+1;end
   issue_count=issue_count+1;
  end
  for(integer i=0;i<8;i=i+1)if(valid[i] && ready[i])begin
   eq_addr[accept_count]=address[i];
   eq_data[accept_count]=(i==1 || i==7)?0:data[i];
   eq_mask[accept_count]=(i==2 || i==5)?mask[i]:0;
   eq_write[accept_count]=(i==1 || i==7)?0:((i==3)?1:write[i]);
   if(eq_write[accept_count])begin
    for(integer k=0;k<32;k=k+1)if(!eq_mask[accept_count][k])model[address[i][14:3]][k*8+:8]=data[i][k*8+:8];
   end else begin er_data[read_count]=model[address[i][14:3]];er_owner[read_count]=i;read_count=read_count+1;end
   accept_count=accept_count+1;per_client[i]=per_client[i]+1;sequence_no[i]=sequence_no[i]+1;
   valid[i]=0;
  end
  if(dut.count>max_tags)max_tags=dut.count;
  if(dut.count==(1<<BITS))blocked=blocked+1;
  if(fault)$fatal(1,"unexpected native response fault");
 end
end
task zero_state;
 begin
  rst=0;bd=0;valid=0;native_rsp=0;stalled=0;
  accept_count=0;issue_count=0;read_count=0;returned=0;nr_in=0;nr_out=0;cycle=0;max_tags=0;blocked=0;
  for(integer i=0;i<8;i=i+1)begin per_client[i]=0;sequence_no[i]=0;end
  for(integer i=0;i<4096;i=i+1)begin model[i]=pattern(9,i);physical[i]=pattern(9,i);end
  repeat(4)@(negedge clk);rst=1;
 end
endtask
task native_drive(input integer pause);
 begin
  random_state=(random_state>>1)^({32{random_state[0]}}&32'h80200003);
  native_ready=random_state[2:0]!=0;native_wrdy=random_state[6:4]>1;
  native_rsp=0;native_rddata=pattern(99,cycle); // data changes even without valid
  if(nr_out<nr_in && cycle>nr_cycle[nr_out]+1 && pause==0 && random_state[12:10]!=0)begin
   native_rsp=1;native_rddata=nr_data[nr_out];nr_out=nr_out+1;
  end
 end
endtask
task offer(input integer i);
 begin
  if(!valid[i])begin
   valid[i]=1;write[i]=random_state[(i+5)%32];
   address[i]=((i*256)+(sequence_no[i]%32))*8;
   data[i]=pattern(i,sequence_no[i]);mask[i]=random_state^(32'h80808080>>i);
  end
 end
endtask
initial begin
 zero_state();
 // BIST owns the bus before the completion epoch, even with other requests.
 for(integer k=0;k<1200;k=k+1)begin
  @(negedge clk);native_drive(0);if(k<500)begin offer(0);offer(1);offer(5);end
  else valid=0;
 end
 if(per_client[0]<100 || per_client[1]!=0 || per_client[5]!=0 || returned!=read_count)$fatal(1,"BIST epoch isolation failed");
 bd=1;
 // Force the tag FIFO to fill, then drain under mixed competing clients.
 for(integer k=0;k<30000;k=k+1)begin
  @(negedge clk);native_drive(k<300?1:0);
  for(integer i=1;i<8;i=i+1)if(((random_state>>((i*3)%27))&31)==0 || k<1000)offer(i);
 end
 @(negedge clk);valid=0;native_drive(0);
 for(integer k=0;k<5000;k=k+1)begin @(negedge clk);native_drive(0);end
 if(accept_count!=issue_count || read_count!=returned || nr_in!=nr_out || blocked==0)$fatal(1,"drain/tag-full mismatch accepted%0d issue%0d read%0d returned%0d blocked%0d",accept_count,issue_count,read_count,returned,blocked);
 for(integer i=0;i<8;i=i+1)if(per_client[i]<8)$fatal(1,"client%0d unexercised count%0d",i,per_client[i]);
 $display("PASS shared DDR pipeline seed=%0d tags=%0d commands=%0d reads=%0d full_tag_cycles=%0d all8clients masked memory/native stalls/consecutive returns/BIST epoch/order",SEED,1<<BITS,accept_count,returned,blocked);
 // A full global reset discards pending command/tags/data and rearms fault.
 @(negedge clk);offer(1);native_ready=0;repeat(3)@(negedge clk);zero_state();
 if(dut.command_full || dut.count || dut.response_valid || fault)$fatal(1,"global reset retained traffic");
 @(negedge clk);native_rsp=1;@(posedge clk);#1;if(!fault)$fatal(1,"unexpected untagged response not explicit");
 @(negedge clk);rst=0;native_rsp=0;repeat(3)@(negedge clk);rst=1;repeat(3)@(negedge clk);if(fault)$fatal(1,"fault did not reset");
 $finish;
end
endmodule
'''
text=text.replace('__INSTANCE__','basic_pitch_ddr_arbiter_pipeline #(.TAG_BITS(BITS)) dut('+','.join(connections)+');')
cases=[]
with tempfile.TemporaryDirectory(prefix='cnn_ddr_arbiter_') as tmp:
 tb=Path(tmp)/'tb.sv';tb.write_text(text)
 for bits,seed in [(2,7),(3,31),(5,127)]:
  exe=Path(tmp)/'sim'
  c=subprocess.run(['iverilog','-g2012','-s','tb_arbiter_pipeline',f'-Ptb_arbiter_pipeline.BITS={bits}',f'-Ptb_arbiter_pipeline.SEED={seed}','-o',str(exe),str(tb),str(ROOT/'rtl/music/basic_pitch_ddr_arbiter_pipeline.sv')],capture_output=True,text=True)
  assert c.returncode==0,c.stdout+c.stderr
  v=subprocess.run(['vvp',str(exe)],capture_output=True,text=True,timeout=30)
  assert v.returncode==0 and 'PASS shared DDR pipeline' in v.stdout,v.stdout+v.stderr
  cases.append(dict(tag_bits=bits,seed=seed,passed=True,log=v.stdout.strip()))
report=dict(passed=True,cases=cases,hardware_tested=False,pcm_saved=False)
if a.output:a.output.write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
