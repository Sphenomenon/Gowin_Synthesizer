`timescale 1ns/1ps
module tb_push_song_pixels;
  reg clk=0,rst=1,write_name=0,chosen=0,done=0;
  always #5 clk=~clk;
  reg [7:0] name_addr=0,name_data=0;
  reg [3:0] browse=0,track=0;
  reg [4:0] count=16;
  reg [15:0] score_count=0,cursor=0;
  reg [2:0] effects=0;
  reg [9:0] x=0;
  reg [7:0] y=0;
  wire [15:0] old_pixel,new_pixel;
`define PORTS(pixel_value) .clk(clk),.rst(rst),.name_write_valid(write_name), \
 .name_write_addr(name_addr),.name_write_data(name_data),.chosen(chosen), \
 .browse_index(browse),.track_index(track),.track_count(count), \
 .score_count(score_count),.cursor(cursor),.analysis_done(done),.effect_mask(effects), \
 .x(x),.y(y),.pixel(pixel_value)
  push2_song_screen_reference old_screen(`PORTS(old_pixel));
  push2_song_screen new_screen(`PORTS(new_pixel));
`undef PORTS
  integer i,state,px,py,checked=0;
  initial begin
    repeat(4)@(negedge clk);rst=0;
    for(i=0;i<192;i=i+1)begin
      @(negedge clk);write_name=1;name_addr=i[7:0];name_data=8'(65+i%26);
    end
    @(negedge clk);write_name=0;
    for(state=0;state<10;state=state+1)begin
      chosen=state>=2;browse=state[3:0];track=4'(15-state);count=5'(16-state%4);
      effects=state[2:0];done=state[0];
      case(state)
        0:begin cursor=0;score_count=0;end
        1:begin cursor=9;score_count=99;end
        2:begin cursor=0;score_count=36;end
        3:begin cursor=36;score_count=36;end
        4:begin cursor=999;score_count=1234;end
        5:begin cursor=10000;score_count=65535;end
        6:begin cursor=65535;score_count=65535;end
        7:begin cursor=32768;score_count=32767;end
        8:begin cursor=799;score_count=800;end
        9:begin cursor=800;score_count=801;end
      endcase
      repeat(34)@(negedge clk);
      for(py=0;py<160;py=py+1)for(px=0;px<960;px=px+1)begin
        x=px[9:0];y=py[7:0];#1;
        if(new_pixel!==old_pixel)$fatal(1,"screen mismatch state=%0d x=%0d y=%0d got=%h expected=%h",state,px,py,new_pixel,old_pixel);
        checked=checked+1;
      end
    end
    $display("PASS push_song_pixels: %0d identical pixels, all positions in 10 menu/practice/count/effect states",checked);
    $finish;
  end
endmodule
