`timescale 1ns/1ps
module tb_sampler_controls;
  import sampler_pkg::*;
  logic clk=0;always #5 clk=~clk;logic rst_n=0,panic=0;
  logic in_valid=0,in_ready,out_valid,out_ready=1;logic [17:0] in_event=0,out_event;
  logic pattern_valid;logic [3:0] pattern;logic [1:0] group_select;
  logic cc_valid=0,pcm_valid=0,fx_valid;logic [6:0] cc=0,value=0,delay_send;
  logic signed [15:0] pcm_l=10001,pcm_r=-10001,out_l,out_r;
  logic manual_write=0,manual=0;logic [3:0] marker_index=0,slice_index=0;logic [31:0] marker_frame=0;
  logic [31:0] slice_start,slice_end;logic slice_valid;
  logic frame_start=0;logic [63:0] grid=0;logic [3:0] step=0;
  logic [10:0] x=32;logic [7:0] y=32;logic dirty,ink;logic [23:0] rgb;
  sampler_push push(.clk(clk),.rst_n(rst_n),.panic(panic),.in_valid(in_valid),.in_ready(in_ready),.in_event(in_event),
    .out_valid(out_valid),.out_ready(out_ready),.out_event(out_event),.pattern_valid(pattern_valid),.pattern(pattern),.group_select(group_select));
  sampler_fx fx(.clk(clk),.rst_n(rst_n),.panic(panic),.cc_valid(cc_valid),.cc(cc),.value(value),
    .pcm_valid(pcm_valid),.pcm_l(pcm_l),.pcm_r(pcm_r),.out_valid(fx_valid),.out_l(out_l),.out_r(out_r),.delay_send(delay_send));
  sampler_slice slices(.clk(clk),.rst_n(rst_n),.manual_write(manual_write),.marker_index(marker_index),.marker_frame(marker_frame),
    .manual(manual),.slice_index(slice_index),.trim_start(32'd10),.trim_end(32'd170),.slice_start(slice_start),.slice_end(slice_end),.valid(slice_valid));
  sampler_grid screen(.clk(clk),.rst_n(rst_n),.frame_start(frame_start),.grid(grid),.pattern(pattern),.step(step),
    .group_select(group_select),.running(1'b1),.x(x),.y(y),.dirty(dirty),.ink(ink),.rgb(rgb));
  task automatic send(input integer kind,note,velocity);
    @(negedge clk);in_event={4'(kind),7'(note),7'(velocity)};in_valid=1;
    @(negedge clk);in_valid=0;
  endtask
  task automatic effect(input integer c,v);
    @(negedge clk);cc=7'(c);value=7'(v);cc_valid=1;
    @(negedge clk);cc_valid=0;pcm_valid=1;@(negedge clk);pcm_valid=0;
  endtask
  initial begin
    repeat(3) @(negedge clk);rst_n=1;
    send(1,36,88);if(out_event!={4'd1,7'd36,7'd88} || !out_valid) $fatal(1,"velocity pad");
    send(1,94,127);if(group_select!=2) $fatal(1,"group selector");
    send(5,36,80);if(out_event!={4'd5,7'd36,7'd80}) $fatal(1,"aftertouch press mapping");
    send(0,36,0);if(out_event!={4'd0,7'd36,7'd0}) $fatal(1,"group change broke release");
    send(1,63,60);if(out_event[13:7]!=83) $fatal(1,"4x4 group2 mapping");
    send(1,72,100);if(!pattern_valid || pattern!=0) $fatal(1,"pattern0 pad");
    send(1,99,100);if(!pattern_valid || pattern!=15) $fatal(1,"pattern15 pad");
    out_ready=0;send(1,36,70);if(in_ready) $fatal(1,"event backpressure");
    repeat(4) @(negedge clk);if(out_event[13:7]!=68 || !out_valid) $fatal(1,"stable stalled event");out_ready=1;
    effect(110,127);if(out_l!=8192 || out_r!= -12288) $fatal(1,"bitcrush precision");
    effect(110,0);if(out_l!=10001 || out_r!= -10001) $fatal(1,"momentary release");
    effect(111,127);if(out_l!=32767 || out_r!= -32768) $fatal(1,"drive saturation");
    effect(111,0);effect(112,99);if(delay_send!=99) $fatal(1,"P10 delay send");
    effect(112,0);if(delay_send!=0) $fatal(1,"P10 delay release");
    for(int i=0;i<16;i++) begin slice_index=4'(i);#1;
      if(!slice_valid || slice_start!=10+i*10 || slice_end!=20+i*10) $fatal(1,"equal slicing");
    end
    manual=1;slice_index=0;#1;if(slice_valid) $fatal(1,"absent marker accepted");
    @(negedge clk);manual_write=1;marker_index=0;marker_frame=20;
    @(negedge clk);marker_index=1;marker_frame=43;
    @(negedge clk);manual_write=0;
    if(!slice_valid || slice_start!=20 || slice_end!=43) $fatal(1,"manual markers");
    marker_index=1;marker_frame=19;manual_write=1;@(negedge clk);manual_write=0;
    if(slice_valid) $fatal(1,"unordered manual marker accepted");
    grid=1;#1;if(!dirty) $fatal(1,"P26 change detection");
    frame_start=1;@(negedge clk);frame_start=0;#1;
    if(dirty || !ink || rgb!=24'hf0c040) $fatal(1,"P26 frame commit %h",rgb);
    grid=0;#1;if(!dirty || rgb!=24'hf0c040) $fatal(1,"frame snapshot tearing");
    panic=1;@(negedge clk);panic=0;
    if(out_valid || delay_send!=0 || out_l!=0 || out_r!=0) $fatal(1,"panic FX/mapping");
    $display("METRIC groups=4 main_pads=16 pattern_pads=16 equal_slices=16 momentary_fx=3 snapshot_tears=0");
    $display("PASS tb_sampler_controls");$finish;
  end
endmodule
