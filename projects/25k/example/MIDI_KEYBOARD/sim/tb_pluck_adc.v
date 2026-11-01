`timescale 1ns/1ps
module tb_pluck_adc;
 reg clk=0;
 always #10 clk=!clk;
 reg reset=1,busy=0,douta=0,doutb=0;
 wire convst,cs_n,sclk,valid,online;
 wire [127:0] samples;
 wire [31:0] count;
 wire [15:0] timeouts;
 reg [63:0] serial_a,serial_b;
 integer mode=0,edges=0;
 midi_pluck_adc #(.CLK_HZ(1000000),.SAMPLE_HZ(1000),.HALF_CYCLES(4),.CONV_CYCLES(10),.TIMEOUT_CYCLES(50)) dut(
  .clk(clk),.reset(reset),.adc_busy(busy),.adc_douta(douta),.adc_doutb(doutb),
  .adc_convst(convst),.adc_cs_n(cs_n),.adc_sclk(sclk),.sample_valid(valid),.online(online),
  .samples(samples),.sample_count(count),.timeouts(timeouts),.busy_observed());
 always @(posedge convst)if(!reset && mode==0)begin
  #30;busy=1;#600;busy=0;
 end
 always @(negedge cs_n)begin
  serial_a=64'h00017fff8000ffff;serial_b=64'h1234fedc567889ab;
  douta=serial_a[63];doutb=serial_b[63];edges=0;
 end
 always @(posedge sclk)if(!cs_n)begin
  serial_a=serial_a<<1;serial_b=serial_b<<1;douta=serial_a[63];doutb=serial_b[63];
 end
 always @(negedge sclk)if(!cs_n)edges=edges+1;
 initial begin
  #1000000;$fatal(1,"ADC test timeout");
 end
 initial begin
  repeat(4)@(negedge clk);reset=0;
  @(posedge valid);#1;
  if(samples!==128'h89ab5678fedc1234ffff80007fff0001 || count!=1 || edges!=64 || !online)
   $fatal(1,"dual serial channel order or clock count: %h edges=%0d",samples,edges);
  mode=1;
  wait(timeouts!=0);#1;
  if(online || !cs_n || !sclk || convst || count!=1)$fatal(1,"missing BUSY did not fail closed");
  mode=0;
  @(posedge valid);#1;
  if(!online || count!=2)$fatal(1,"ADC did not recover");
  @(negedge cs_n);repeat(8)@(negedge clk);reset=1;
  repeat(2)@(negedge clk);
  if(!cs_n || !sclk || convst || online || count!=0)$fatal(1,"reset must cancel partial serial frame");
  reset=0;
  @(posedge valid);#1;
  if(samples!==128'h89ab5678fedc1234ffff80007fff0001 || count!=1)$fatal(1,"partial frame survived reset");
  mode=1;busy=1;wait(!online);#1;
  if(timeouts==0)$fatal(1,"stuck BUSY was not reported");
  $display("PASS tb_pluck_adc dual output, signed words, BUSY failures, reset and recovery");$finish;
 end
endmodule
