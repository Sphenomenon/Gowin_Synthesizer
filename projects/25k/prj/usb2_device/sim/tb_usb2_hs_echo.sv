`timescale 1ns/1ps
module tb_usb2_hs_echo;
 reg clk=0; always #5 clk=~clk;
 reg reset_n=0,clear=0,rx_valid=0,tx_accept=0;
 reg [7:0] rx_data=0;
 wire rx_space,tx_valid;
 wire [7:0] tx_data;
 wire [31:0] rx_count,tx_count;
 wire [15:0] overflow_count,occupancy;
 integer sent=0,received=0,cycles=0;
 usb2_hs_echo dut(.*);
 always @(posedge clk)begin
  if(reset_n && !clear && tx_valid && tx_accept)begin
   if(tx_data!==received[7:0])$fatal(1,"FIFO corruption %0d got %h",received,tx_data);
   received=received+1;
  end
 end
 initial begin
  repeat(4)@(negedge clk);reset_n=1;
  // Fill enough to require packet reserve backpressure, then drain under
  // bursty backpressure while writing three complete packet-sized bursts.
  repeat(1537)begin @(negedge clk);rx_valid=1;rx_data=sent[7:0];sent=sent+1;end
  @(negedge clk);rx_valid=0;
  if(rx_space)$fatal(1,"512-byte reservation not enforced");
  while(received<sent || sent<6000)begin
   @(negedge clk);cycles=cycles+1;
   tx_accept=(cycles%7!=0);
   rx_valid=(sent<6000 && rx_space && cycles%3!=0);
   if(rx_valid)begin rx_data=sent[7:0];sent=sent+1;end
   if(cycles>30000)$fatal(1,"FIFO progress timeout");
  end
  @(negedge clk);rx_valid=0;tx_accept=0;
  if(rx_count!=6000 || tx_count!=6000 || overflow_count!=0 || occupancy!=0)$fatal(1,"count/drop mismatch");
  clear=1;@(negedge clk);clear=0;
  if(tx_valid || occupancy)$fatal(1,"USB reset did not clear queue");
  $display("PASS: HS FIFO 6000 ordered bytes, packet reserve/backpressure, empty and USB reset");$finish;
 end
 initial begin #1000000;$fatal(1,"timeout");end
endmodule
