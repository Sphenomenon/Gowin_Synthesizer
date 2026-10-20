`timescale 1ns/1ps
module tb_push_surface_pipeline;
  reg clk=0,rst=1,frame=0,guide=0,chosen=0,done=0;
  always #5 clk=~clk;
  reg [9:0] x=0;
  reg [7:0] y=0;
  reg [31:0] control=0,options=0,mask=0;
  reg [63:0] held=0,meta=0;
  reg [15:0] cursor=0,count=0;
  reg [3:0] browse=0,track=0;
  reg [2:0] effects=0;
  reg name_valid=0;
  reg [7:0] name_addr=0,name_data=0;
  wire [15:0] expected,actual;
`define PORTS(pixel_value) .clk(clk),.rst(rst),.frame_ready(frame),.frame_start(), \
 .x(x),.y(y),.pixel_valid(),.pixel(pixel_value),.control(control),.options(options), \
 .held(held),.note(7'd60),.velocity(7'd100),.display_meta(meta),.display_meta_valid(1'b1), \
 .score_mask(mask),.score_running(1'b1),.record_enabled(1'b1), \
 .guide_mode(guide),.guide_chosen(chosen),.guide_browse(browse),.guide_track(track), \
 .guide_track_count(5'd16),.guide_score_count(count),.guide_cursor(cursor),.guide_analysis_done(done), \
 .name_write_valid(name_valid),.name_write_addr(name_addr),.name_write_data(name_data)
  push2_surface_pixels_reference old_pixels(`PORTS(expected));
  push2_surface_pixels #(.PIPELINED(1)) new_pixels(`PORTS(actual));
`undef PORTS
  reg [15:0] captured;
  integer state,i,px,py,checked=0;
  task automatic check_pixel;
    begin
      captured=expected;
      @(posedge clk);#1;
      if(actual!==captured)$fatal(1,"pipelined pixel mismatch state=%0d x=%0d y=%0d got=%h expected=%h",state,x,y,actual,captured);
      checked=checked+1;
    end
  endtask
  initial begin
    repeat(4)@(negedge clk);rst=0;
    for(i=0;i<192;i=i+1)begin
      @(negedge clk);name_valid=1;name_addr=i[7:0];name_data=8'(65+i%26);
    end
    @(negedge clk);name_valid=0;
    for(state=0;state<8;state=state+1)begin
      guide=state>=4;chosen=state[0];done=state[1];browse=state[3:0];track=4'(15-state);
      count=16'(state*9191);cursor=16'(state*9999);control=$random;options=$random;
      held={$random,$random};mask=$random;meta={32'd0,$random};frame=1;
      @(negedge clk);frame=0;repeat(34)@(negedge clk);
      for(py=0;py<160;py=py+1)for(px=0;px<960;px=px+1)begin
        @(negedge clk);x=px[9:0];y=py[7:0];#1;check_pixel();
      end
      for(i=0;i<100;i=i+1)begin
        @(negedge clk);x=10'($urandom_range(0,959));y=8'($urandom_range(0,159));#1;check_pixel();
      end
    end
    $display("PASS push_surface_pipeline: %0d exact pixels at one-stage latency, performance/menu/practice, frame capture and random rewind",checked);
    $finish;
  end
endmodule
