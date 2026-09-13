`timescale 1ns/1ps
module tb_host_gate;
 reg clk=0,rst=1,rx=1;wire enabled;
 always #10 clk=~clk;
 push2_host_gate dut(clk,rst,rx,enabled);
 task send(input [7:0] b);
  begin @(negedge clk);rx=0;repeat(434)@(negedge clk);
   for(integer k=0;k<8;k=k+1)begin rx=b[k];repeat(434)@(negedge clk);end
   rx=1;repeat(500)@(negedge clk);
  end
 endtask
 task command(input [7:0] value);
  begin send(8'hf0);send(8'h7d);send("P");send("U");send("S");send("H");send(value);send(8'hf7);end
 endtask
 initial begin #100;rst=0;command(2);if(enabled)$fatal(1,"malformed command accepted");
  command(1);if(!enabled)$fatal(1,"enable failed");
  send(8'h90);send(60);send(100);if(!enabled)$fatal(1,"notes changed host state");
  command(0);if(enabled)$fatal(1,"disable failed");
  $display("PASS actual 50MHz/115200 UART, malformed SysEx, enable/disable, ordinary notes");$finish;
 end
 initial begin #10000000;$fatal(1,"UART test timeout");end
endmodule
