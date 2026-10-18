`timescale 1ns/1ps
module tb_surface_fault;
 reg clk=0,hclk=0,aclk=0,rst=1;
 always #10 clk=~clk;always #4.167 hclk=~hclk;always #6.510 aclk=~aclk;
 wire htclk,htreq,htvld,htrdy,hrclk,hrreq,hrvld,hrack;tri[15:0]hd;
 wire av;reg ar=1;wire[17:0]ae;wire[223:0]telemetry;
 push2_surface dut(clk,rst,aclk,!rst,1'b1,448'd0,htclk,htreq,htvld,htrdy,hrclk,hrreq,hrvld,hrack,hd,av,ar,ae,telemetry);
 defparam dut.link.POLL_CYCLES=100;
 reg act=0;wire[31:0]ho,rxd;wire[2:0]oe;wire[8:0]ta,ra;wire wr,rdone,crc,num,txdone;
 reg[15:0]ram[0:511];reg[15:0]rx[0:511];reg[15:0]txread;
 always @(posedge hclk)txread<=ram[ta];
 assign hd=oe[1]?ho[15:0]:16'bz;
 push_hspi_phy #(.TX_ADDR(0),.RX_ADDR(0)) model(.clk(hclk),.rstn(!rst),.dat_mod(2'b01),
 .HTCLK(hrclk),.HTREQ(hrreq),.HTVLD(hrvld),.HTRDY(hrack),.HTD(ho),.HTOE(oe),.tx_act(act),.tx_len(12'd543),
 .HRCLK(htclk),.HRACT(htreq),.HRVLD(htvld),.HTACK(htrdy),.HRD({16'd0,hd}),.ram_rdata({16'd0,txread}),
 .tx_addr(ta),.tx_done(txdone),.rx_write(wr),.rx_addr(ra),.rx_data(rxd),.rx_done(rdone),.rx_crc_error(crc),.rx_num_error(num),
 .ram_clk(),.ram_csn(),.ram_wen(),.ram_addr(),.ram_wdata(),.rx_crc_value());
 always @(posedge htclk)if(wr)rx[ra]<=rxd[15:0];
 reg running=0,sent_notes=0;integer accepted=0;
 initial begin
  for(integer k=0;k<512;k=k+1)ram[k]=0;
  forever begin
   @(posedge rdone);#1;
   if(crc||num)$fatal(1,"bad native HSPI");
   if(rx[3][7:0]==2)running=1;
   ram[0]=16'h3250;ram[1]=16'h3152;ram[2]=rx[2];ram[3]={(running?8'd2:8'd0),(rx[3][7:0]==1?8'd3:8'd0)};
   ram[4]=16'h2982;ram[5]=16'h1967;ram[6]=16'h0108;ram[7]=16'h0201;ram[8]=512;ram[9]=512;ram[10]=0;
   // Deliberately wait until the real output scheduler has faulted on STALL.
   if(dut.fault&&!sent_notes)begin
    ram[10]=8;ram[16]=16'h9009;ram[17]=16'h643c;ram[18]=16'h8008;ram[19]=16'h003c;sent_notes=1;
   end
   repeat(5)@(posedge hclk);act=1;repeat(4)@(posedge hclk);act=0;@(posedge txdone);
  end
 end
 always @(posedge aclk)if(av&&ar)begin
  if(!dut.fault)$fatal(1,"event arrived before injected STALL");
  if(ae!==(accepted==0?{4'd1,7'd60,7'd100}:{4'd0,7'd60,7'd0}))$fatal(1,"wrong audio event %h",ae);
  accepted=accepted+1;
 end
 initial begin
  #100;rst=0;force dut.enable=1;
  wait(accepted==2);repeat(100)@(posedge aclk);
  if(dut.link_errors || !dut.configured || dut.mapped!=2)$fatal(1,"unrelated input failure");
  $display("PASS actual USB OUT STALL -> display fault, then MIDI note on/off -> 76.8MHz audio FIFO; input remains operational");$finish;
 end
 initial begin #10000000;$fatal(1,"timeout configured=%d fault=%d reply=%d mapped=%d state=%d",dut.configured,dut.fault,dut.replies,dut.mapped,dut.link.state);end
endmodule
