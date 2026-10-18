`timescale 1ns/1ps
module tb_usb_board_cdc;
 reg wr_clk=0,rd_clk=0,reset=1;
 always #10 wr_clk=!wr_clk;
 always #8.333 rd_clk=!rd_clk;
 reg wr_valid=0,rd_ready=0;wire wr_ready,rd_valid;
 reg[31:0]wr_data=0;wire[31:0]rd_data;
 midi_usb_async_fifo #(.WIDTH(32),.ADDR_BITS(3)) dut(
  .reset(reset),.wr_clk(wr_clk),.wr_valid(wr_valid),.wr_ready(wr_ready),.wr_data(wr_data),
  .rd_clk(rd_clk),.rd_valid(rd_valid),.rd_ready(rd_ready),.rd_data(rd_data));
 integer put=0,get=0,total=0,checks=0,stall_count=0,seed=7823;
 reg[31:0]expected[0:8191];
 reg[31:0]held_data;reg held=0;
 always @(posedge wr_clk)if(!reset&&wr_valid&&wr_ready)begin
  expected[put]=wr_data;put=put+1;total=total+1;
 end
 always @(posedge rd_clk)if(!reset)begin
  if(held)begin
   checks=checks+1;
   if(!rd_valid||rd_data!==held_data)$fatal(1,"CDC output changed while stalled");
  end
  held=rd_valid&&!rd_ready;held_data=rd_data;
  if(rd_valid&&rd_ready)begin
   checks=checks+1;
   if(get>=put||rd_data!==expected[get])$fatal(1,"CDC order/loss/duplicate at %0d got %h expected %h",get,rd_data,expected[get]);
   get=get+1;
  end
 end
 initial begin
  repeat(4)@(negedge wr_clk);reset=0;
  // Fill all eight entries. Source holds its beat until ready returns.
  for(integer i=0;i<8;i=i+1)begin
   @(negedge wr_clk);wr_valid=1;wr_data=i;
   while(!wr_ready)@(negedge wr_clk);@(posedge wr_clk);
  end
  @(negedge wr_clk);wr_valid=0;
  repeat(10)begin @(negedge wr_clk);checks=checks+1;if(wr_ready)$fatal(1,"CDC full queue did not backpressure");end
  rd_ready=1;while(get<put)@(negedge rd_clk);
  // Noncommensurate clocks, random read stalls and thousands of pointer wraps.
  fork
   begin
    for(integer i=0;i<2000;i=i+1)begin
     @(negedge wr_clk);wr_valid=1;wr_data=32'h81230000+i;
     while(!wr_ready)begin stall_count=stall_count+1;@(negedge wr_clk);end
     @(posedge wr_clk);
     if(i%7==0)begin @(negedge wr_clk);wr_valid=0;repeat(i%4)@(negedge wr_clk);end
    end
    @(negedge wr_clk);wr_valid=0;
   end
   begin
    repeat(7000)begin @(negedge rd_clk);rd_ready=($random(seed)&7)==0;end
    rd_ready=1;
   end
  join
  while(get<put)@(negedge rd_clk);
  // Assert common reset with pending data and a stalled output. Both pointer
  // domains must forget the old session, despite different release edges.
  rd_ready=0;
  for(integer i=0;i<5;i=i+1)begin
   @(negedge wr_clk);wr_valid=1;wr_data=32'hdead0000+i;
   while(!wr_ready)@(negedge wr_clk);@(posedge wr_clk);
  end
  @(negedge wr_clk);wr_valid=0;#3;reset=1;held=0;put=0;get=0;
  #57;reset=0;rd_ready=1;
  repeat(10)@(negedge rd_clk);
  checks=checks+1;if(rd_valid)$fatal(1,"CDC stale data survived session reset");
  @(negedge wr_clk);wr_valid=1;wr_data=32'h1234abcd;
  while(!wr_ready)@(negedge wr_clk);@(posedge wr_clk);
  @(negedge wr_clk);wr_valid=0;
  while(get<put)@(negedge rd_clk);
  checks=checks+1;if(stall_count==0)$fatal(1,"CDC stress did not backpressure");
  $display("PASS USB board async FIFO: %0d checks, %0d accepted words, %0d stalled writer cycles, 50/60MHz wrap/full/order/reset",checks,total,stall_count);
  $finish;
 end
 initial begin #1000000;$fatal(1,"CDC timeout");end
endmodule
