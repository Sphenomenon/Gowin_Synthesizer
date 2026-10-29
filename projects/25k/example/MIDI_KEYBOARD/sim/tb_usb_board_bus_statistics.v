`timescale 1ns/1ps
module tb_usb_board_bus_statistics;
 reg clk=0,reset=1,enabled=0,protocol_active=0,dir=0,nxt=0,rxvalid=0;
 reg[2:0]phy_state=1;
 reg[1:0]utmi_line=0;
 reg[7:0]pad_input=0,utmi_data=0;
 wire[191:0]statistics;
 wire[23:0]raw_max=statistics[23:0],utmi_max=statistics[55:32];
 wire[23:0]rxcmd_count=statistics[87:64],phy_bytes=statistics[119:96];
 wire[23:0]utmi_bytes=statistics[151:128],link_nxt_count=statistics[183:160];
 midi_usb2_events dut(.clk(clk),.reset(reset),.enabled(enabled),.protocol_active(protocol_active),
  .phy_state(phy_state),.pad_input(pad_input),.utmi_line(utmi_line),.utmi_data(utmi_data),
  .dir(dir),.nxt(nxt),.rxvalid(rxvalid),.rxactive(1'b0),.rxerror(1'b0),
  .txvalid(1'b0),.txready(1'b0),.history(),.statistics(statistics));
 always #5 clk=!clk;
 task tick(input integer cycles);
  repeat(cycles)@(negedge clk);
 endtask
 task restart;
  begin
   reset=1;enabled=0;protocol_active=0;dir=0;nxt=0;rxvalid=0;
   phy_state=1;utmi_line=0;pad_input=0;utmi_data=0;
   tick(2);reset=0;enabled=1;protocol_active=1;tick(1);
  end
 endtask
 task idle_j;
  begin
   dir=0;nxt=0;rxvalid=0;tick(1);
   dir=1;pad_input=8'h41;utmi_line=1;tick(2);
   if(!dut.raw_armed||!dut.utmi_armed)$fatal(1,"FS idle J did not arm SE0 observation");
  end
 endtask
 initial begin
  tick(2);reset=0;dir=1;nxt=1;rxvalid=1;tick(5);
  if(rxcmd_count||phy_bytes||utmi_bytes||link_nxt_count)$fatal(1,"boot polluted bus statistics");
  restart();dir=1;pad_input=8'h40;tick(20);
  if(raw_max||utmi_max)$fatal(1,"initial/unknown SE0 counted as host reset");
  idle_j();pad_input=8'h40;utmi_line=0;tick(1);
  dir=0;tick(179999);
  if(raw_max!=180000||utmi_max!=180000)$fatal(1,"held RXCMD SE0 duration mismatch %d %d",raw_max,utmi_max);
  phy_state=2;tick(20);
  if(raw_max!=180000||utmi_max!=180000)$fatal(1,"chirp/HS line state polluted FS reset duration");
  protocol_active=0;tick(20);
  if(raw_max!=180000||utmi_max!=180000)$fatal(1,"reset history disappeared between USB sessions");
  restart();idle_j();pad_input=8'h40;utmi_line=1;tick(300);
  if(raw_max!=300||utmi_max!=0)$fatal(1,"raw RXCMD and wrapper line cannot be distinguished");
  restart();dir=1;nxt=1;pad_input=8'h9a;tick(1);
  if(phy_bytes!=0)$fatal(1,"DIR turnaround counted as PHY receive data");
  tick(7);
  rxvalid=1;utmi_data=8'ha5;tick(5);
  if(phy_bytes!=12||utmi_bytes!=5||statistics[127:120]!=8'h9a||statistics[159:152]!=8'ha5)
   $fatal(1,"native NXT/data and UTMI byte counts not independent");
  rxvalid=0;dir=0;tick(1);
  if(link_nxt_count!=0)$fatal(1,"reverse turnaround counted as link NXT acknowledge");
  tick(4);
  if(link_nxt_count!=4)$fatal(1,"link-side NXT acknowledge cycles missing");
  protocol_active=0;rxvalid=1;tick(5);
  if(phy_bytes!=12||utmi_bytes!=5||link_nxt_count!=4)$fatal(1,"inactive bridge polluted counters");
  restart();idle_j();pad_input=8'h40;utmi_line=0;
  dut.raw_run=24'hfffffe;dut.utmi_run=24'hfffffe;
  dut.raw_max=24'hfffffe;dut.utmi_max=24'hfffffe;
  dut.raw_runs=255;dut.utmi_runs=255;tick(3);
  if(raw_max!=24'hffffff||utmi_max!=24'hffffff||dut.raw_run!=24'hffffff||dut.utmi_run!=24'hffffff)
   $fatal(1,"SE0 cycle counters wrapped instead of saturating");
  if(statistics[31:24]!=255||statistics[63:56]!=255)$fatal(1,"SE0 run counters wrapped");
  dut.rxcmd_count=24'hfffffe;tick(3);
  if(rxcmd_count!=24'hffffff)$fatal(1,"RXCMD count wrapped");
  dut.phy_bytes=24'hfffffe;dut.utmi_bytes=24'hfffffe;nxt=1;rxvalid=1;tick(3);
  if(phy_bytes!=24'hffffff||utmi_bytes!=24'hffffff)$fatal(1,"receive byte counts wrapped");
  dut.link_nxt_count=24'hfffffe;dir=0;tick(4);
  if(link_nxt_count!=24'hffffff)$fatal(1,"link NXT count wrapped");
  restart();
  if(raw_max||utmi_max||rxcmd_count||phy_bytes||utmi_bytes||link_nxt_count)$fatal(1,"global reset did not clear statistics");
  $display("PASS USB2 bus statistics: qualified FS SE0 durations, native/UTMI disagreement, turnaround exclusion, NXT/data and saturation");
  $finish;
 end
endmodule
