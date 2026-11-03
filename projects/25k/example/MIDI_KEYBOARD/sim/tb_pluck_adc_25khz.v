`timescale 1ns/1ps
module tb_pluck_adc_25khz;
 reg clk=0;
 always #10 clk=!clk;
 reg reset=1,busy=0,douta=0,doutb=0;
 wire convst,cs_n,sclk,valid,online;
 wire [127:0] samples;
 wire [31:0] count;
 wire [15:0] timeouts;
 reg [63:0] serial_a,serial_b;
 integer cycles=0,last_conversion=0,conversions=0,edges=0;
 time last_cs,last_sclk_rise;
 midi_pluck_adc #(.SAMPLE_HZ(25000)) dut(
  .clk(clk),.reset(reset),.adc_busy(busy),.adc_douta(douta),.adc_doutb(doutb),
  .adc_convst(convst),.adc_cs_n(cs_n),.adc_sclk(sclk),.sample_valid(valid),.online(online),
  .samples(samples),.sample_count(count),.timeouts(timeouts));
 always @(posedge clk)cycles=cycles+1;
 always @(posedge convst)if(!reset)begin
  if(conversions!=0 && cycles-last_conversion!=2000)$fatal(1,"25 kHz conversion schedule slipped");
  conversions=conversions+1;last_conversion=cycles;
  #45;busy=1;
  if(conversions%3==0)#4200;
  else if(conversions%3==1)#3450;
  else #4000;
  busy=0;
 end
 always @(negedge cs_n)begin
  if(busy)$fatal(1,"CS asserted before conversion completed");
  last_cs=$time;
  serial_a=64'h80007fff0001ffff;serial_b=64'h123456789abcdef0;
  edges=0;#35;douta=serial_a[63];doutb=serial_b[63];
 end
 always @(posedge sclk)if(!cs_n)begin
  last_sclk_rise=$time;
  serial_a=serial_a<<1;serial_b=serial_b<<1;
  #39;douta=serial_a[63];doutb=serial_b[63];
 end
 always @(posedge cs_n)begin #22;douta=1'bz;doutb=1'bz;end
 always @(negedge sclk)if(!cs_n)begin
  if(edges==0 && $time-last_cs<35)$fatal(1,"CS to first MSB access time violated");
  if(edges!=0 && $time-last_sclk_rise<39)$fatal(1,"SCLK to data access time violated");
  edges=edges+1;
 end
 initial begin #1000000;$fatal(1,"25 kHz ADC timeout");end
 initial begin
  repeat(4)@(negedge clk);reset=0;
  repeat(12)begin
   @(posedge valid);#1;
   if(!online || timeouts!=0 || edges!=64 || samples!==128'hdef09abc56781234ffff00017fff8000)
    $fatal(1,"25 kHz serial timing/channel/error mismatch");
  end
  if(count!=12 || conversions!=12)$fatal(1,"25 kHz samples skipped/duplicated");
  $display("PASS tb_pluck_adc_25khz AD7606 Rev.G read-after-conversion, 25 kHz, 2.5 MHz dual serial, 3.45..4.2 us BUSY, delayed/high-Z DOUT, 64 clocks and no skipped frames");$finish;
 end
endmodule
