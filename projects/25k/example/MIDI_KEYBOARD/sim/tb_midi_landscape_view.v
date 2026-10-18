`timescale 1ns/1ps
// Rasterize actual four-stage RTL, then test streaming latency and snapshot coherence.
module tb_midi_landscape_view;
 reg clk=0,reset=1,snapshot=0;
 always #5 clk=~clk;
 reg [15:0] keys=16'h0125;
 reg [3:0] channel=2;
 reg signed [7:0] shift=-12;
 reg [6:0] velocity=100,program_number=23;
 reg [1:0] mode=2;
 reg [7:0] brightness=192,strip=166;
 reg [2:0] focus=3;
 reg usb=1,ble=1,touch=1,panic=0;
 reg slider_ready=1,slider_touched=1,slider_overrun=0;
 reg [7:0] slider_raw=174,slider_position=166,slider_error=0,slider_status=8'h02,slider_count=8'h7f;
 reg [15:0] theme=16'h07ff,background=16'h0841;
 reg [8:0] x=0;
 reg [7:0] y=0;
 wire [15:0] color;
 midi_landscape_view dut(.clk(clk),.reset(reset),.snapshot(snapshot),
  .key_bitmap(keys),.midi_channel(channel),.transpose(shift),.velocity(velocity),
  .program_number(program_number),.slider_mode(mode),.brightness(brightness),.strip_value(strip),
  .focus(focus),.usb_online(usb),.ble_online(ble),.touch_ready(touch),.panic_busy(panic),
  .slider_ready(slider_ready),.slider_touched(slider_touched),.slider_overrun(slider_overrun),
  .slider_raw_position(slider_raw),.slider_filtered_position(slider_position),
  .slider_error(slider_error),.slider_general_status(slider_status),.slider_sample_count(slider_count),
  .theme_rgb565(theme),.clear_rgb565(background),.pixel_x(x),.pixel_y(y),.pixel_color(color));
 reg [15:0] reference[0:60775];
 integer fd,px,py,index,stream_index,strip_case,changed=0,foreground=0;
 reg [15:0] expected_track;
 reg [2047:0] ppm_path;
 task sample_pixel;
  input integer tx,ty;
  begin
   @(negedge clk);x=tx;y=ty;
   repeat(4) @(posedge clk);#1;
  end
 endtask
 task check_pixel;
  input integer tx,ty;
  input [15:0] expected;
  begin sample_pixel(tx,ty);if(color!==expected)
   $fatal(1,"Pixel (%0d,%0d) got %h expected %h",tx,ty,color,expected);end
 endtask
 // Independent pixel oracle: check every glyph pixel and the cell spacing,
 // without using the renderer's text IDs, character mux, or font function.
 function [34:0] expected_glyph;
  input [7:0] letter;
  begin
   case(letter)
    "0":expected_glyph=35'b01110_10001_10011_10101_11001_10001_01110;
    "1":expected_glyph=35'b00100_01100_00100_00100_00100_00100_01110;
    "2":expected_glyph=35'b01110_10001_00001_00010_00100_01000_11111;
    "3":expected_glyph=35'b11110_00001_00001_01110_00001_00001_11110;
    "4":expected_glyph=35'b00010_00110_01010_10010_11111_00010_00010;
    "5":expected_glyph=35'b11111_10000_10000_11110_00001_00001_11110;
    "6":expected_glyph=35'b01110_10000_10000_11110_10001_10001_01110;
    "7":expected_glyph=35'b11111_00001_00010_00100_01000_01000_01000;
    "8":expected_glyph=35'b01110_10001_10001_01110_10001_10001_01110;
    "9":expected_glyph=35'b01110_10001_10001_01111_00001_00001_01110;
    "A":expected_glyph=35'b01110_10001_10001_11111_10001_10001_10001;
    "C":expected_glyph=35'b01110_10001_10000_10000_10000_10001_01110;
    "E":expected_glyph=35'b11111_10000_10000_11110_10000_10000_11111;
    "F":expected_glyph=35'b11111_10000_10000_11110_10000_10000_10000;
    "G":expected_glyph=35'b01110_10001_10000_10111_10001_10001_01110;
    "N":expected_glyph=35'b10001_11001_10101_10011_10001_10001_10001;
    "O":expected_glyph=35'b01110_10001_10001_10001_10001_10001_01110;
    "P":expected_glyph=35'b11110_10001_10001_11110_10000_10000_10000;
    "R":expected_glyph=35'b11110_10001_10001_11110_10100_10010_10001;
    "S":expected_glyph=35'b01111_10000_10000_01110_00001_00001_11110;
    "T":expected_glyph=35'b11111_00100_00100_00100_00100_00100_00100;
    "V":expected_glyph=35'b10001_10001_10001_10001_10001_01010_00100;
    "W":expected_glyph=35'b10001_10001_10001_10101_10101_11011_10001;
    " ":expected_glyph=0;
    default:$fatal(1,"No external diagnostic glyph oracle for %c",letter);
   endcase
  end
 endfunction
 task check_diagnostic_text;
  input integer origin_x,origin_y,count;
  input [175:0] message;
  input [15:0] ink,paper;
  integer column,dx,dy;
  reg [7:0] letter;
  reg [34:0] glyph;
  reg lit;
  begin
   for(column=0;column<count;column=column+1)begin
    letter=message>>((count-1-column)*8);glyph=expected_glyph(letter);
    for(dy=0;dy<7;dy=dy+1)for(dx=0;dx<6;dx=dx+1)begin
     lit=dx<5 && glyph[(6-dy)*5+(4-dx)];
     check_pixel(origin_x+column*6+dx,origin_y+dy,lit?ink:paper);
    end
   end
  end
 endtask
 initial begin
  if(!$value$plusargs("ppm=%s",ppm_path)) ppm_path="reports/midi_keyboard_preview.ppm";
  repeat(3) @(negedge clk);reset=0;snapshot=1;@(negedge clk);snapshot=0;
  check_pixel(0,26,16'h0841);
  check_pixel(8,5,16'hffff); // two-times title M
  check_pixel(194,29,16'h07ff); // selected STRIP card border
  check_pixel(195,30,16'h19a6);
  check_pixel(375,29,16'h2945);check_pixel(376,29,16'h0841); // final card ends before sidebar
  check_pixel(384,29,16'h07ff);check_pixel(419,126,16'h07ff);
  check_pixel(400,50,16'h2104);check_pixel(400,90,16'h07ff);
  check_pixel(400,77,16'hffff); // horizontal center marker in vertical pitch track
  check_pixel(300,78,16'h0841); // diagnostic row stays clear of the sidebar
  check_diagnostic_text(8,74,22,"S2 R1 T1 RAW174 POS166",16'h07ff,16'h0841);
  check_diagnostic_text(208,133,15,"G02 E00 OV0 N7F",16'h07e0,16'h0841);
  check_pixel(140,74,16'h0841);check_pixel(207,133,16'h0841);check_pixel(298,133,16'h0841);
  check_pixel(9,84,16'h07ff);check_pixel(32,84,16'h2945);
  check_pixel(354,84,16'h2945);check_pixel(373,84,16'h0841); // key 16 fits before sidebar
  check_pixel(383,90,16'h0841);check_pixel(420,90,16'h0841); // sidebar has clear margins
  fd=$fopen(ppm_path,"w");if(!fd)$fatal(1,"Cannot create RTL preview %s",ppm_path);
  $fwrite(fd,"P3\n428 142\n255\n");
  for(py=0;py<142;py=py+1)for(px=0;px<428;px=px+1)begin
   sample_pixel(px,py);index=py*428+px;reference[index]=color;
   if(^color===1'bx)$fatal(1,"Undefined raster pixel (%0d,%0d)",px,py);
   if(color!=background)foreground=foreground+1;
   $fwrite(fd,"%0d %0d %0d\n",(color[15:11]*255)/31,(color[10:5]*255)/63,(color[4:0]*255)/31);
  end
  $fclose(fd);
  // Every live value changes, but the rendered frame must remain identical.
  keys=~keys;channel=15;shift=24;velocity=1;program_number=127;mode=0;
  brightness=4;strip=0;focus=0;usb=0;ble=0;touch=0;panic=1;theme=16'hf800;background=16'h0000;
  slider_ready=0;slider_touched=0;slider_overrun=1;slider_raw=255;slider_position=9;
  slider_error=8'ha5;slider_status=8'hc3;slider_count=8'hfe;
  // One new coordinate every clock checks the exact four-edge latency,
  // including the final three in-flight pixels after the raster ends.
  for(stream_index=0;stream_index<60779;stream_index=stream_index+1)begin
   @(negedge clk);
   if(stream_index<60776)begin x=stream_index%428;y=stream_index/428;end
   @(posedge clk);#1;
   if(stream_index>=3 && color!==reference[stream_index-3])
    $fatal(1,"Streaming snapshot/latency mismatch at pixel %0d",stream_index-3);
  end
  @(negedge clk);snapshot=1;@(negedge clk);snapshot=0;
  for(py=0;py<142;py=py+1)for(px=0;px<428;px=px+1)begin
   sample_pixel(px,py);if(color!==reference[py*428+px])changed=changed+1;
  end
  if(changed<10000 || foreground<10000)$fatal(1,"Renderer did not display substantial content/update");
  check_pixel(8,29,16'hf800);check_pixel(0,26,16'h0000);
  check_diagnostic_text(8,74,22,"S2 R0 T0 RAW255 POS009",16'hf800,16'h0000);
  check_diagnostic_text(208,133,15,"GC3 EA5 OV1 NFE",16'hf800,16'h0000);
  // A valid idle sensor is green, and its actual general-status register is
  // rendered independently from both error and overrun, including hex digits.
  slider_ready=1;slider_touched=0;slider_overrun=0;slider_raw=83;slider_position=72;
  slider_error=0;slider_status=8'h40;slider_count=8'h09;
  @(negedge clk);snapshot=1;@(negedge clk);snapshot=0;
  check_diagnostic_text(8,74,22,"S2 R1 T0 RAW083 POS072",16'h07e0,16'h0000);
  check_diagnostic_text(208,133,15,"G40 E00 OV0 N09",16'h07e0,16'h0000);
  slider_ready=0;
  @(negedge clk);snapshot=1;@(negedge clk);snapshot=0;
  check_diagnostic_text(8,74,22,"S2 R0 T0 RAW083 POS072",16'hf800,16'h0000);
  check_diagnostic_text(208,133,15,"G40 E00 OV0 N09",16'hfd20,16'h0000);
  // Independently check every vertical-track pixel at empty, half, full and
  // centered pitch values. The track must fill upward with exact endpoints.
  for(strip_case=0;strip_case<4;strip_case=strip_case+1)begin
   case(strip_case)
    0:begin strip=0;mode=0;end
    1:begin strip=128;mode=1;end
    2:begin strip=255;mode=0;end
    3:begin strip=128;mode=2;end
   endcase
   @(negedge clk);snapshot=1;@(negedge clk);snapshot=0;
   for(py=43;py<=112;py=py+1)for(px=392;px<=411;px=px+1)begin
    expected_track=((112-py)*256<strip*70)?16'hf800:16'h2104;
    if(mode==2 && py==77)expected_track=16'hffff;
    check_pixel(px,py,expected_track);
   end
   check_pixel(391,90,16'h10a3);check_pixel(412,90,16'h10a3);
   check_pixel(383,90,16'h0000);check_pixel(420,90,16'h0000);
   // All sixteen key cells remain visible and within their own region.
   for(px=0;px<16;px=px+1)begin
    check_pixel(9+px*23,84,keys[px]?16'hf800:16'h2945);
    check_pixel(28+px*23,84,16'h0000);
   end
  end
  $display("PASS: landscape view 428x142 actual RTL raster, six cards/16 keys clear of right-side vertical strip, empty/half/full/centered upward track, S2 decimal/hex diagnostics and status colors checked by external glyph oracle, four-edge streaming latency, full-frame snapshot stability, %0d changed pixels",changed);
  $finish;
 end
 initial begin #20000000;$fatal(1,"View simulation timeout");end
endmodule
