`timescale 1ns/1ps
module tb_hspi_link;
 reg clk=0,hclk=0,rst=1,enable=0;
 always #10 clk=~clk; always #4.167 hclk=~hclk;
 wire htclk,htreq,htvld,htrdy,hrclk,hrreq,hrvld,hrack;tri [15:0] hd;
 reg rv=0,tv=0,last=0;reg [7:0] td;wire rr,tr,done;wire [2:0] resp;
 wire mv;reg mr=1;wire [31:0] me;wire configured,hs;wire[15:0]vid,pid;
 wire[6:0]addr;wire[7:0]dep,mep,hstate,ee,he;wire[10:0]dm,mm;wire[31:0]replies,errs,ie,ip;
 push2_hspi_link #(.POLL_CYCLES(100),.TIMEOUT_CYCLES(100000)) dut(clk,rst,enable,htclk,htreq,htvld,htrdy,hrclk,hrreq,hrvld,hrack,hd,
 rv,rr,7'd8,4'd1,1'b0,10'd512,tv,tr,td,last,done,resp,mv,mr,me,configured,hs,vid,pid,addr,dep,mep,dm,mm,replies,errs,ie,ip,hstate,ee,he);
 reg act=0;wire[31:0]ho,rxd;wire[2:0]oe;wire[8:0]ta,ra;wire wr,rdone,crc,num,txdone;
 reg[15:0]ram[0:511];reg[15:0]rx[0:511];reg [11:0]len=543;
 reg[15:0] txread; always @(posedge hclk) txread<=ram[ta];
 assign hd=oe[1]?ho[15:0]:16'bz;
 push_hspi_phy #(.TX_ADDR(0),.RX_ADDR(0)) model(.clk(hclk),.rstn(!rst),.dat_mod(2'b01),
 .HTCLK(hrclk),.HTREQ(hrreq),.HTVLD(hrvld),.HTRDY(hrack),.HTD(ho),.HTOE(oe),.tx_act(act),.tx_len(len),
 .HRCLK(htclk),.HRACT(htreq),.HRVLD(htvld),.HTACK(htrdy),.HRD({16'd0,hd}),.ram_rdata({16'd0,txread}),
 .tx_addr(ta),.tx_done(txdone),.rx_write(wr),.rx_addr(ra),.rx_data(rxd),.rx_done(rdone),.rx_crc_error(crc),.rx_num_error(num),
 .ram_clk(),.ram_csn(),.ram_wen(),.ram_addr(),.ram_wdata(),.rx_crc_value());
 always @(posedge htclk)if(wr)rx[ra]<=rxd[15:0];
 time last_return=0;
 always @(posedge htreq) if(last_return && $time-last_return<2000)$fatal(1,"CH569 turnaround violated");
 integer nrequests=0,nout=0,nmidi=0;reg running=0,truncate_next=0,truncated=0;
 initial begin
  for(integer k=0;k<512;k=k+1)ram[k]=0;
  forever begin
   @(posedge rdone);#1;
   if(crc||num)$fatal(1,"model received bad native HSPI CRC/sequence");
   if(rx[0]!==16'h3250||rx[1]!==16'h3151)$fatal(1,"request header wrong %h %h",rx[0],rx[1]);
   if(rx[3][7:0]==2)running=1;
   if(rx[3][7:0]==1)begin
    if(rx[5]!==512)$fatal(1,"512 length truncated");
    for(integer k=0;k<256;k=k+1)if(rx[8+k]!=={8'(k*2+1),8'(k*2)})$fatal(1,"payload word %d mismatch %h",k,rx[8+k]);
    nout=nout+1;
   end
   ram[0]=16'h3250;ram[1]=16'h3152;ram[2]=rx[2];ram[3]={(running?8'd2:8'd0),(rx[3][7:0]==1?8'd1:8'd0)};
   ram[4]=16'h2982;ram[5]=16'h1967;ram[6]=16'h0108;ram[7]=16'h0201;ram[8]=512;ram[9]=512;
   ram[10]=(rx[3][7:0]==1)?512:0;ram[11]=0;ram[12]=0;ram[13]=0;ram[14]=nrequests;ram[15]=0;
   for(integer k=0;k<128;k=k+1)begin ram[16+2*k]=16'h9009;ram[17+2*k]=16'h4000|k;end
   len=truncate_next?31:543;
   if(truncate_next)begin truncate_next=0;truncated=1;end
   repeat(5)@(posedge hclk);act=1;repeat(4)@(posedge hclk);act=0;@(posedge txdone);last_return=$time;nrequests=nrequests+1;
  end
 end
 always @(posedge clk) if(mv&&mr)begin
  if(me!==(32'h40009009|(nmidi<<16)))$fatal(1,"MIDI payload mismatch %h",me);
  nmidi=nmidi+1;
 end
 initial begin
  #100;rst=0;repeat(500)@(posedge clk);enable=1;wait(configured);@(negedge clk);rv=1;do @(posedge clk);while(!rr);@(negedge clk);rv=0;
  for(integer k=0;k<512;k=k+1)begin
   td=k;tv=1;last=k==511;do @(posedge clk);while(!tr);@(negedge clk);tv=0;
  end
  wait(done);if(resp!=1)$fatal(1,"not USB ACK");mr=0;repeat(100)@(posedge clk);@(negedge clk);mr=1;
  wait(nmidi==128);repeat(100)@(posedge clk);
  if(errs||he||ie||nout!=1||vid!=16'h2982||pid!=16'h1967||!hs)$fatal(1,"link counters/profile fail");
  truncate_next=1;wait(truncated);wait(errs==1);wait(configured);repeat(100)@(posedge clk);
  if(errs!=1 || nmidi!=128)$fatal(1,"truncated packet leaked stale data or failed recovery");
  $display("PASS 128 MIDI events, CRC-valid truncated reply rejected/recovered; native HSPI CRC/sequence, USB OFF/enable/profile, 512-byte OUT, ACK, bidirectional MIDI/backpressure");$finish;
 end
 initial begin #10000000;$fatal(1,"timeout state=%d replies=%d errs=%d",dut.state,replies,errs);end
endmodule
