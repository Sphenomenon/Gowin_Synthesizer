`timescale 1ns/1ps
module tb_usb_board_attach;
 reg clk50=0,clk60=0,reset=1;
 always #10 clk50=!clk50;
 always #8.333 clk60=!clk60;
 tri[7:0]ulpi_data;
 wire ulpi_stp;
 midi_usb2_link #(.ATTACH_DELAY_CYCLES(100)) dut(
  .clk_50mhz(clk50),.clk_ulpi60(clk60),.reset(reset),
  .ulpi_data(ulpi_data),.ulpi_dir(1'b0),.ulpi_nxt(1'b1),.ulpi_stp(ulpi_stp),
  .midi_tx_valid(1'b0),.midi_tx_ready(),.midi_tx_data(32'd0),
  .midi_rx_valid(),.midi_rx_ready(1'b1),.midi_rx_data(),
  .control_tx_valid(1'b0),.control_tx_ready(),.control_tx_data(8'd0),
  .control_rx_valid(),.control_rx_ready(1'b1),.control_rx_data(),
  .online(),.control_reset(),.hs_active());
 reg expect_data=0,detached_written=0,attached_written=0;
 always @(posedge clk60)begin
  if(dut.protocol_reset)expect_data<=0;
  else if(expect_data)begin
   expect_data<=0;
   if(ulpi_data[2]==0&&ulpi_data[4:3]!=0)detached_written<=1;
   if(ulpi_data==8'h45)attached_written<=1;
  end else if(ulpi_data==8'h84)expect_data<=1;
 end
 initial begin
  force dut.boot_done=1'b1;
  force dut.boot_error=1'b0;
  repeat(5)@(negedge clk50);reset=0;
  wait(!dut.protocol_reset);
  repeat(2)@(negedge clk50);
  if(dut.attach_delay.attach_count!=0||dut.attach_delay.attach_ready)
   $fatal(1,"attach counter released before local reset synchronization");
  repeat(50)@(negedge clk50);
  if(dut.protocol_reset||!dut.bridge_reset||dut.ulpi.ulpi_rst_i)
   $fatal(1,"attach delay incorrectly stops the ULPI register writer");
  if(!detached_written||attached_written)$fatal(1,"PHY was not commanded to detach before attach");
  repeat(100)@(negedge clk50);
  if(dut.bridge_reset)$fatal(1,"attach delay did not release");
  repeat(70000)@(negedge clk60);
  if(!attached_written)$fatal(1,"PHY FS termination was not actually written");
  reset=1;
  repeat(5)@(negedge clk50);
  if(!dut.bridge_reset)$fatal(1,"new reset failed to cancel delayed attachment");
  $display("PASS USB2 real detach/attach: ULPI writer runs during bridge reset and writes detached then attached Function Control");
  $finish;
 end
 initial begin #2000000;$fatal(1,"attach timeout");end
endmodule
