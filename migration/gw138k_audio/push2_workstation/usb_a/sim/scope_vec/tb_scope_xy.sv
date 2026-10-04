`timescale 1ns/1ps
module tb_scope_xy;
 reg clk=0,source_clk=0,rst_n=0,valid=0;
 reg [31:0] pair=0;
 wire ready,legacy_ready;
 integer i;
 always #5 clk=~clk;
 always #7 source_clk=~source_clk;
 output_audio_analysis #(.XY_DIRECT(1)) direct(
  .clk(clk),.reset_n(rst_n),.source_clk(source_clk),.source_reset_n(rst_n),.pcm_pair(pair),.sample_valid(valid),
  .release_frame(1'b0),.ready(ready),.peak_left(),.peak_right(),.image_gain(),.sequence_data(),.skipped_data(),
  .display_read_enable(1'b0),.spectrum_column(9'd0),.image_addr(16'd0),.spectrum_left(),.spectrum_right(),.image_hit(),.display_valid());
 output_audio_analysis legacy(
  .clk(clk),.reset_n(rst_n),.source_clk(source_clk),.source_reset_n(rst_n),.pcm_pair(pair),.sample_valid(valid),
  .release_frame(1'b0),.ready(legacy_ready),.peak_left(),.peak_right(),.image_gain(),.sequence_data(),.skipped_data(),
  .display_read_enable(1'b0),.spectrum_column(9'd0),.image_addr(16'd0),.spectrum_left(),.spectrum_right(),.image_hit(),.display_valid());
 initial begin
  repeat(10) @(negedge source_clk);rst_n=1;
  // Allow both image banks to initialize before publishing a complete block.
  repeat(70000) @(negedge clk);
  for(i=0;i<2048;i=i+1) begin
   @(negedge source_clk);pair={i[0] ? 16'hc000 : 16'h4000,i[1] ? 16'he000 : 16'h2000};valid=1;
   @(negedge source_clk);valid=0;repeat(3) @(negedge source_clk);
  end
  wait(ready && legacy_ready);@(negedge clk);
  if(!direct.image_pixels[112*256+160] || !direct.image_pixels[112*256+96] ||
     !direct.image_pixels[144*256+160] || !direct.image_pixels[144*256+96]) $fatal(1,"L=X R=Y quadrants");
  if(direct.image_pixels[80*256+112] || direct.image_pixels[176*256+144]) $fatal(1,"mid-side projection leaked into XY");
  if(!legacy.image_pixels[80*256+112] || !legacy.image_pixels[176*256+144]) $fatal(1,"legacy projection changed");
  $display("M xy_quadrants 4");$display("PASS scope_xy");$finish;
 end
 initial begin #30000000;$fatal(1,"timeout");end
endmodule
