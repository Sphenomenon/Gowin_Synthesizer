`timescale 1ns/1ps
// Decode the real ODDRC pins for both panel rotations. RAM is synchronous and
// row-major, deliberately unlike the panel's native pixel scan direction.
module remote_tile_display_case #(parameter integer ROTATE_CW=0)(output reg passed=0);
 reg clk=0,reset=1,remote_enable=0,tile_valid=0;
 always #10 clk=~clk;
 reg [8:0] tile_x=17,tile_width=5;
 reg [7:0] tile_y=9,tile_height=3;
 wire tile_ready,tile_done,ncs,dc,sck,mosi,snapshot;
 wire [7:0] tile_read_addr,pixel_y;
 wire [8:0] pixel_x;
 wire [31:0] refreshes;
 reg [15:0] ram[0:255],ram_data=0,render_pipe[0:3];
 integer i,xx,yy;
 midi_landscape_display #(.ROTATE_CW(ROTATE_CW),.MS_TICKS(1),
  .BOOT_MS(1),.POST_INIT_MS(1)) dut(
  .clk(clk),.reset(reset),.pixel_color(render_pipe[3]),.dirty_regions(27'd0),
  .remote_enable(remote_enable),.tile_valid(tile_valid),.tile_ready(tile_ready),
  .tile_x(tile_x),.tile_y(tile_y),.tile_width(tile_width),.tile_height(tile_height),
  .tile_read_addr(tile_read_addr),.tile_read_data(ram_data),.tile_done(tile_done),
  .pixel_x(pixel_x),.pixel_y(pixel_y),.snapshot(snapshot),
  .completed_refreshes(refreshes),.overrun_count(),
  .lcd_ncs(ncs),.lcd_dc(dc),.lcd_sck(sck),.lcd_mosi(mosi));
 function [15:0] pattern;
  input integer x,y,seed;
  begin pattern=(x*16'h0131)^(y*16'h075b)^(seed*16'h92e5);end
 endfunction
 always @(posedge clk)begin
  ram_data<=ram[tile_read_addr];
  render_pipe[0]<=pattern(pixel_x,pixel_y,7);
  for(i=1;i<4;i=i+1)render_pipe[i]<=render_pipe[i-1];
 end
 reg armed=0,in_window=0;
 integer windows=0,completed_windows=0,done_count=0,handshakes=0;
 integer left,right,top,bottom,seed,kind;
 integer col_first,col_last,row_first,row_last;
 integer bit_index=0,byte_index=0,pixel_index,px,py;
 reg [7:0] shift=0,received,expected;
 reg [15:0] expected_color;
 time cs_released=0;
 task expected_bounds;
  input integer window_number;
  begin
   left=0;right=427;top=0;bottom=141;kind=0;seed=0;
   case(window_number)
    1,5:kind=0;
    2:begin left=17;right=21;top=9;bottom=11;kind=1;seed=1;end
    3:begin left=39;right=42;top=21;bottom=22;kind=1;seed=2;end
    4:begin kind=2;seed=7;end
    6:begin left=102;right=104;top=31;bottom=34;kind=1;seed=3;end
    default:$fatal(1,"rotation%0d unexpected window%0d",ROTATE_CW,window_number);
   endcase
   col_first=ROTATE_CW ? 141-bottom : top;
   col_last=ROTATE_CW ? 141-top : bottom;
   row_first=ROTATE_CW ? left : 427-right;
   row_last=ROTATE_CW ? right : 427-left;
  end
 endtask
 function [7:0] header_byte;
  input integer index;
  begin case(index)
   0:header_byte=8'h36;1:header_byte=0;2:header_byte=8'h20;
   3:header_byte=8'h2a;4:header_byte=0;5:header_byte=col_first+12;
   6:header_byte=0;7:header_byte=col_last+12;8:header_byte=8'h2b;
   9:header_byte=row_first>>8;10:header_byte=row_first;
   11:header_byte=row_last>>8;12:header_byte=row_last;13:header_byte=8'h2c;
   default:header_byte=0;
  endcase end
 endfunction
 function header_dc;
  input integer index;
  begin header_dc=!(index==0 || index==2 || index==3 || index==8 || index==13);end
 endfunction
 always @(negedge ncs)if(armed)begin
  if(in_window)$fatal(1,"Nested physical CS");
  windows=windows+1;expected_bounds(windows);
  in_window=1;byte_index=0;bit_index=0;
 end
 always @(posedge sck)if(armed)begin
  if(ncs || !in_window)$fatal(1,"SPI clocks outside window");
  shift={shift[6:0],mosi};bit_index=bit_index+1;
  if(bit_index==8)begin
   bit_index=0;received=shift;
   if(byte_index<14)begin
    if(received!==header_byte(byte_index) || dc!==header_dc(byte_index))
     $fatal(1,"rotation%0d window%0d header%0d got%02h dc%b expected%02h dc%b",
      ROTATE_CW,windows,byte_index,received,dc,header_byte(byte_index),header_dc(byte_index));
   end else begin
    if(!dc)$fatal(1,"Pixel byte marked command");
    pixel_index=(byte_index-14)/2;
    px=ROTATE_CW ? row_first+pixel_index/(col_last-col_first+1) :
        427-(row_first+pixel_index/(col_last-col_first+1));
    py=ROTATE_CW ? 141-(col_first+pixel_index%(col_last-col_first+1)) :
        col_first+pixel_index%(col_last-col_first+1);
    expected_color=kind==0 ? 16'd0 : pattern(px,py,seed);
    expected=byte_index[0] ? expected_color[7:0] : expected_color[15:8];
    if(received!==expected)
     $fatal(1,"rotation%0d window%0d pixel(%0d,%0d) byte%0d got%02h expected%02h",
      ROTATE_CW,windows,px,py,byte_index[0],received,expected);
   end
   byte_index=byte_index+1;
  end
 end
 always @(posedge ncs)if(armed && in_window)begin
  if(sck || bit_index!=0 || byte_index!=14+2*(right-left+1)*(bottom-top+1))
   $fatal(1,"rotation%0d window%0d incomplete bytes%0d",ROTATE_CW,windows,byte_index);
  in_window=0;completed_windows=completed_windows+1;cs_released=$time;
 end
 always @(posedge tile_done)if(armed)begin
  if(!ncs || sck || in_window || !dut.spi_idle || $time<=cs_released)
   $fatal(1,"tile_done before physical CS released");
  if(!(completed_windows==2 || completed_windows==3 || completed_windows==6))
   $fatal(1,"Spurious tile_done after window%0d",completed_windows);
  done_count=done_count+1;
 end
 always @(posedge clk)if(armed && tile_ready && tile_valid)begin
  if(!ncs || !(completed_windows==1 || completed_windows==2 || completed_windows==5))
   $fatal(1,"Tile accepted before clean-page transition completed");
  handshakes=handshakes+1;
 end
 task load_tile;
  input integer x,y,w,h,s;
  begin
   tile_x=x;tile_y=y;tile_width=w;tile_height=h;
   for(yy=0;yy<h;yy=yy+1)
    for(xx=0;xx<w;xx=xx+1)ram[yy*w+xx]=pattern(x+xx,y+yy,s);
  end
 endtask
 initial begin
  for(xx=0;xx<256;xx=xx+1)ram[xx]=16'hdead;
  repeat(5)@(negedge clk);reset=0;
  wait(refreshes==1 && ncs);@(negedge clk);armed=1;
  // A pending tile accompanies first entry, but the full black clear owns SPI.
  load_tile(17,9,5,3,1);tile_valid=1;remote_enable=1;
  wait(handshakes==1);@(negedge clk);tile_valid=0;
  tile_x=400;tile_y=100;tile_width=1;tile_height=1;
  wait(done_count==1);repeat(50)@(negedge clk);
  if(windows!=2 || !ncs)$fatal(1,"Idle remote page generated traffic");
  load_tile(39,21,4,2,2);tile_valid=1;
  wait(handshakes==2);@(negedge clk);tile_valid=0;
  wait(windows==3 && byte_index>14);@(negedge clk);remote_enable=0;
  // Exiting during transmission must finish the tile, acknowledge after CS,
  // then repaint every local pixel even though dirty_regions stays zero.
  wait(done_count==2);@(negedge clk);load_tile(102,31,3,4,3);tile_valid=1;
  wait(windows==4 && byte_index>1000);@(negedge clk);remote_enable=1;
  // Re-entry waits for the whole local window, clears, then consumes the tile.
  wait(handshakes==3);@(negedge clk);tile_valid=0;
  tile_x=0;tile_y=0;tile_width=1;tile_height=1;
  wait(done_count==3);repeat(100)@(negedge clk);
  if(windows!=6 || completed_windows!=6 || handshakes!=3 || !ncs || sck)
   $fatal(1,"rotation%0d final coverage windows%0d completed%0d handshake%0d",
    ROTATE_CW,windows,completed_windows,handshakes);
  passed=1;
 end
 initial begin #110000000;$fatal(1,"Remote display timeout rotation%0d state%0d windows%0d",ROTATE_CW,dut.state,windows);end
endmodule

module tb_remote_tile_display;
 wire passed_ccw,passed_cw;
 remote_tile_display_case #(.ROTATE_CW(0)) ccw(.passed(passed_ccw));
 remote_tile_display_case #(.ROTATE_CW(1)) cw(.passed(passed_cw));
 initial begin
  wait(passed_ccw && passed_cw);
  $display("PASS remote display: both rotations, synchronous row-major RAM, off-origin asymmetric RGB565 tiles/high byte first, entry clear, forced complete local repaint, safe mid-window switching, physical-CS tile_done, idle silence");
  $finish;
 end
endmodule
