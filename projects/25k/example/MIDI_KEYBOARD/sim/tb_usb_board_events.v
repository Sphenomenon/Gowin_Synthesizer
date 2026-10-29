`timescale 1ns/1ps
module tb_usb_board_events;
 reg clk=0,reset=1,enabled=0,dir=0,nxt=0;
 reg rxvalid=0,rxactive=0,rxerror=0,txvalid=0,txready=0;
 reg[2:0]phy_state=0;
 reg[7:0]pad_input=0;
 wire[31:0]history;
 midi_usb2_events dut(.clk(clk),.reset(reset),.enabled(enabled),.protocol_active(1'b1),.phy_state(phy_state),
  .utmi_line(2'd0),.utmi_data(8'd0),.statistics(),
  .pad_input(pad_input),.dir(dir),.nxt(nxt),.rxvalid(rxvalid),.rxactive(rxactive),
  .rxerror(rxerror),.txvalid(txvalid),.txready(txready),.history(history));
 always #5 clk=!clk;
 integer index;
 initial begin
  repeat(2)@(negedge clk);reset=0;
  rxvalid=1;rxerror=1;txvalid=1;txready=1;rxactive=1;
  repeat(3)@(negedge clk);
  if(history!=0)$fatal(1,"disabled boot bus polluted USB history");
  rxvalid=0;enabled=1;phy_state=1;
  @(negedge clk);dir=1;pad_input=8'hff;
  @(negedge clk);
  if(history[23:20]!=0||history[7:0]!=0)$fatal(1,"turnaround captured as RXCMD");
  pad_input=8'h40;
  @(negedge clk);
  if(history[23:20]!=1||history[7:0]!=8'h40)$fatal(1,"SE0 RXCMD missing");
  pad_input=8'h41;phy_state=2;rxvalid=1;nxt=1;
  repeat(300)@(negedge clk);
  if(history[15:8]!=255)$fatal(1,"RX byte history wrapped instead of saturating");
  if(history[7:0]!=8'h40)$fatal(1,"RX data captured as RXCMD");
  rxvalid=0;nxt=0;
  for(index=0;index<4;index=index+1)begin
   pad_input=8'h40|index;phy_state=index+2;
   @(negedge clk);
  end
  if(history[23:20]!=15||history[19:16]!=15||history[31:24]!=8'h3e)
   $fatal(1,"sticky PHY history incomplete: %h",history);
  enabled=0;dir=0;rxerror=0;txvalid=0;txready=0;rxactive=0;
  repeat(5)@(negedge clk);
  if(history!=32'h3effff43)$fatal(1,"history disappeared while disabled: %h",history);
  reset=1;
  @(negedge clk);
  if(history!=0)$fatal(1,"new load/reset did not clear history");
  $display("PASS USB2 event history: boot exclusion, turnaround, sticky states, real RXCMD and saturated byte count");
  $finish;
 end
endmodule
