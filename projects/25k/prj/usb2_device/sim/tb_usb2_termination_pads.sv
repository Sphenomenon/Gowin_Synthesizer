`timescale 1ns/1ps
module tb_usb2_termination_pads;
 reg clk50=0,clk60=0,dir=0,nxt=0;
 always #10 clk50=~clk50;
 always #8.333 clk60=~clk60;
 tri [7:0] pads;
 reg external_oe=0;
 reg [7:0] external_data=8'h3c;
 assign pads=external_oe ? external_data : 8'hzz;
 wire stp,ready,done;
 usb2_device_top dut(.clk_50mhz(clk50),.clk_ulpi60(clk60),
  .ulpi_data(pads),.ulpi_dir(dir),.ulpi_nxt(nxt),.ulpi_stp(stp),
  .led_ready(ready),.led_done(done));
 initial begin
  force dut.u_init.drive_armed=0;
  force dut.u_init.drive_data=8'ha5;
  #1;if(pads!==8'hzz) $fatal(1,"unarmed pads drive");
  force dut.u_init.drive_armed=1;
  #1;if(pads!==8'ha5) $fatal(1,"pad output polarity");
  dir=1;
  #1;if(pads!==8'hzz) $fatal(1,"raw DIR did not release before clock edge");
  external_oe=1;
  #1;if(dut.init_data_in!==8'h3c) $fatal(1,"pad input path");
  force dut.u_init.drive_armed=0;
  external_oe=0;dir=0;
  #1;if(pads!==8'hzz) $fatal(1,"unarmed return turnaround drove");
  force dut.u_init.drive_armed=1;
  #1;if(pads!==8'ha5) $fatal(1,"armed return output");
  $display("PASS termination physical pad LUT2/IOBUF truth table, immediate DIR release, input path and guarded return");
  $finish;
 end
endmodule
