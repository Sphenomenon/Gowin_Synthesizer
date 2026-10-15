`timescale 1ns/1ps
module tb_i2c_faults;
    reg clk=0; always #5 clk=~clk;
    reg rst=0,start=0,enabled=1,scl_fault=0,sda_fault=0;
    tri1 scl,sda;
    assign scl=scl_fault ? 1'b0 : 1'bz;
    assign sda=sda_fault ? 1'b0 : 1'bz;
    wire busy,done; wire [3:0] error;
    reg [6:0] addr=7'h0d;
    wire [511:0] data;
    integer high_ticks;
    tb_i2c_master #(.CLK_HZ(1000000),.I2C_HZ(100000)) dut(
      .clk(clk),.rst_n(rst),.start(start),.address(addr),.read_mode(1'b0),.length(7'd0),
      .tx_data(512'd0),.rx_data(data),.busy(busy),.done(done),.error(error),.scl(scl),.sda(sda));
    i2c_device_model device(.scl(scl),.sda(sda),.enabled(enabled));
    task launch;
      begin @(negedge clk); start=1; @(negedge clk); start=0; end
    endtask
    initial begin
      repeat(10) @(posedge clk); rst=1;
      launch; wait(done); if(error!=0) $fatal(1,"valid address");
      repeat(100) @(posedge clk);
      // A brief low SCL during FREE must restart the 100-us high guard.
      launch; wait(dut.state==1);
      repeat(40) @(negedge clk); scl_fault=1;
      repeat(20) @(negedge clk); scl_fault=0;
      wait(dut.scl_sync); high_ticks=0;
      while(dut.state==1) begin @(negedge clk); high_ticks=high_ticks+1; end
      if(high_ticks<99) $fatal(1,"START before 100 consecutive idle cycles: %0d",high_ticks);
      wait(done); if(error!=0) $fatal(1,"free-bus disturbance recovery");
      repeat(100) @(posedge clk);
      launch; wait(dut.state==1);
      repeat(40) @(negedge clk); sda_fault=1;
      repeat(20) @(negedge clk); sda_fault=0;
      wait(dut.sda_sync); high_ticks=0;
      while(dut.state==1) begin @(negedge clk); high_ticks=high_ticks+1; end
      if(high_ticks<99) $fatal(1,"START before 100 consecutive SDA-high cycles: %0d",high_ticks);
      wait(done); if(error!=0) $fatal(1,"SDA idle disturbance recovery");
      repeat(100) @(posedge clk);
      addr=7'h2a; launch; wait(done); if(error!=1) $fatal(1,"address NACK");
      repeat(100) @(posedge clk); addr=7'h0d;
      launch; wait(dut.state==4); scl_fault=1;
      repeat(100) @(posedge clk); scl_fault=0;
      wait(done); if(error!=0) $fatal(1,"clock stretch resume");
      repeat(100) @(posedge clk);
      scl_fault=1; launch; wait(done); if(error!=3 || dut.scl_low || dut.sda_low) $fatal(1,"clock timeout/release");
      scl_fault=0; repeat(100) @(posedge clk);
      sda_fault=1; launch; wait(done); if(error!=4) $fatal(1,"SDA recovery error");
      if(dut.recovery!=8) $fatal(1,"nine recovery clocks");
      sda_fault=0; repeat(100) @(posedge clk);
      launch; wait(done); if(error!=0) $fatal(1,"after recovery");
      $display("PASS faults: continuous 100-us bus idle, address NACK, clock stretching, SCL timeout, nine-pulse recovery, reconnect"); $finish;
    end
    initial begin repeat(50000) @(posedge clk); $fatal(1,"fault test timeout"); end
endmodule
