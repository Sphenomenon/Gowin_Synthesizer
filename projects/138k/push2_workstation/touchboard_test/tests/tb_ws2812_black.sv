`timescale 1ns/1ps
module tb_ws2812_black;
 reg clk=0,rst_n=0; always #10 clk=~clk;
 wire din,complete;
 ws2812_black dut(.clk(clk),.rst_n(rst_n),.enable(1'b1),.din(din),.complete(complete));
 integer pulses=0; time rise,last_rise=0,fall=0;
 always @(posedge din) begin
   if(last_rise && $time-last_rise!=1260) $fatal(1,"WS2812 data period");
   rise=$time;last_rise=$time;pulses=pulses+1;
 end
 always @(negedge din) if(rst_n && rise) begin if($time-rise!=300) $fatal(1,"WS2812 zero high duration");fall=$time;end
 initial begin
   #100;rst_n=1;
   wait(complete);if(pulses!=384 || din!==0 || $time-fall<1000000) $fatal(1,"WS2812 all-black frame/reset");
   #2000000;if(din!==0 || pulses!=384) $fatal(1,"WS2812 must not repeat or light LEDs");
   $display("PASS 16*24 zero bits, 300ns/960ns waveform, >=1ms latch, remains low");$finish;
 end
 initial begin #6000000;$fatal(1,"WS2812 timeout");end
endmodule
