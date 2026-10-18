`timescale 1ns/1ps
module tb_effect_slide;
reg clk=0,rst=0,en=1,frame_start=0;
always #5 clk=~clk;
reg [10:0] x=0,y=0;
reg [2:0] mask=0;
reg [5:0] order=6'b11_11_11;
wire [31:0] pixels[0:1];
for(genvar k=0;k<2;k++) begin: lane
feedback_dashboard #(.ENABLE_ANALYSIS(1)) dut(.clk(clk),.reset_n(rst),.enable(en),.frame_start(frame_start),
.pixel_x(x+11'(k)),.pixel_y(y),.wave_sample(32'd0),.wave_previous(32'd0),.waveform_held(1'b0),
.spectrum_left(8'd0),.spectrum_right(8'd0),.image_hit(1'b0),.peak_left(16'd0),.peak_right(16'd0),.image_gain(3'd0),
.analysis_sequence(32'd0),.analysis_skipped(32'd0),.peak_data(32'd0),.active_voices(32'd0),.status_data(32'd0),
.effect_mask(mask),.effect_order(order),.sequence_data(32'd0),.skipped_data(32'd0),.memory_status(32'd3),
.underruns(32'd0),.framecount(32'd0),.pixel_data(pixels[k]));
end
integer f,fd,logfd,old0,old1,old2;
task tick; begin @(negedge clk);frame_start=1;@(negedge clk);frame_start=0;end endtask
function integer abs(input integer v);abs=v<0?-v:v;endfunction
task render(input integer number);
 begin
  fd=$fopen($sformatf("frame_%03d.rgb",number),"wb");
  for(integer yy=832;yy<988;yy++) for(integer xx=48;xx<1088;xx+=2) begin
    @(negedge clk); x=11'(xx);y=11'(yy);
    repeat(4) @(posedge clk);#1;
    $fwrite(fd,"%c%c%c%c%c%c",pixels[0][23:16],pixels[0][15:8],pixels[0][7:0],pixels[1][23:16],pixels[1][15:8],pixels[1][7:0]);
  end
  $fclose(fd);
 end
endtask
initial begin
 #12;rst=1;logfd=$fopen("positions.csv","w");
 $fwrite(logfd,"frame,delay_x,chorus_x,reverb_x,mask,order\n");
 for(f=0;f<244;f++) begin
  case(f)
   1:begin mask=1;order=6'b11_11_00;end
   54:begin mask=5;order=6'b11_10_00;end
   99:begin mask=7;order=6'b01_10_00;end
   141:begin mask=4;order=6'b11_11_10;end
   // Retarget a departing card while it is moving: never jump to its slot.
   148:begin mask=6;order=6'b11_01_10;end
   191:begin mask=7;order=6'b00_01_10;end
  endcase
  old0=lane[0].dut.effect_x0;old1=lane[0].dut.effect_x1;old2=lane[0].dut.effect_x2;
  tick();
  if(abs(integer'(lane[0].dut.effect_x0)-old0)>32 || abs(integer'(lane[0].dut.effect_x1)-old1)>32 || abs(integer'(lane[0].dut.effect_x2)-old2)>32)
    $fatal(1,"card teleported");
  if({lane[0].dut.effect_x0,lane[0].dut.effect_x1,lane[0].dut.effect_x2} !== {lane[1].dut.effect_x0,lane[1].dut.effect_x1,lane[1].dut.effect_x2}) $fatal(1,"odd/even coordinate mismatch");
  $fwrite(logfd,"%0d,%0d,%0d,%0d,%0d,%0d\n",f,lane[0].dut.effect_x0,lane[0].dut.effect_x1,lane[0].dut.effect_x2,mask,order);
  if(f%3==0 || f==243) render(f);
  // A held raster origin and a stalled pixel pipe must not advance motion.
  old0=lane[0].dut.effect_x0;@(negedge clk);x=0;y=0;en=0;
  repeat(100) @(posedge clk);@(negedge clk);en=1;repeat(100) @(posedge clk);#1;
  if(lane[0].dut.effect_x0!=old0) $fatal(1,"clock cycles advanced animation without a frame");
  if(f==52 && (lane[0].dut.effect_x0!=64 || lane[0].dut.effect_x1!=1120 || lane[0].dut.effect_x2!=1120)) $fatal(1,"single card failed to settle");
 end
 if(lane[0].dut.effect_x0!=736 || lane[0].dut.effect_x1!=400 || lane[0].dut.effect_x2!=64) $fatal(1,"reverse order failed to settle");
 $fclose(logfd);$display("PASS 244 frames: <=32 px/frame; actual moving pixels; even/odd agree; stalls; retarget during motion; final reverse order");$finish;
end
endmodule
