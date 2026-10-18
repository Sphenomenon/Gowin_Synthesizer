`timescale 1ns/1ps
module tb_quiet;
 reg clk=0;always #5 clk=~clk;
 tri1 scl1,sda1,scl2,sda2,scl3,sda3,change_n;
 wire tx,pa,ws;
 touchboard_top #(.CLK_HZ(1000000)) dut(.clk_50m(clk),.button1_n(1'b1),.debug_uart_tx(tx),.pa_en(pa),
 .scl1(scl1),.sda1(sda1),.scl2(scl2),.sda2(sda2),.scl3(scl3),.sda3(sda3),.change_n(change_n),.ws2812_din(ws));
 i2c_device_model q1(.scl(scl1),.sda(sda1),.enabled(1'b1));
 reg testing=0;
 always @(negedge scl2 or negedge sda2 or negedge scl3 or negedge sda3) if(testing) $fatal(1,"unexpected traffic on isolated buses");
 initial begin
  force dut.boot_count=0;repeat(20) @(posedge clk);force dut.boot_count=20'hfffff;
  testing=1;
  wait(dut.configured[0] && dut.raw_valid[0]);
  if(q1.mem[54]!=1 || q1.mem[12]!=1 || dut.ISOLATE_U1!=1 || dut.FRAME_HZ!=5) $fatal(1,"quiet profile");
  if(dut.online[1] || dut.configured[1]) $fatal(1,"isolated chip must not claim ready");
  q1.mem[3]=8'h42;wait(dut.status1[31:24]==8'h42);
  if(dut.raw1[15:0]!=1000-dut.raw_index1 || dut.raw1[31:16]!=1000) $fatal(1,"quiet raw values");
  repeat(500000) @(posedge clk);q1.mem[3]=0;wait(dut.status1[31:24]==0);
  $display("PASS quiet exact staged profile: U1 ID/config/raw/touch/release, no bus2/3 edges, 5Hz profile");$finish;
 end
 initial begin repeat(6000000) @(posedge clk);$fatal(1,"quiet timeout");end
endmodule
