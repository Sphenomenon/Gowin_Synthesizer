`timescale 1ns/1ps
module tb_push_pixel_mmio;
  reg clk=0,reset_n=0;
  always #5 clk=~clk;
  reg select=0,write_bus=0;
  reg [7:0] address=0;
  reg [31:0] wdata=0;
  wire ready;
  wire [31:0] rdata;
  push2_usb_a_control dut(.clk(clk),.reset_n(reset_n),.audio_clk(clk),.audio_reset_n(reset_n),
      .feedback_clk(clk),.feedback_reset_n(reset_n),.performance_words(448'd0),
      .display_meta_data(64'd0),.display_meta_valid(1'b0),.service_state_data(34'd0),
      .service_state_valid(1'b0),.score_valid(1'b0),.analysis_done(1'b0),.score_ready(),.score_note(7'd0),
      .playlist_valid(1'b0),.playlist_ready(),.playlist_word(16'd0),.track_launch(),.track_index(),
      .select(select),.write(write_bus),.address(address),.wdata(wdata),.ready(ready),.rdata(rdata),
      .audio_valid(),.audio_ready(1'b1),.audio_event(),.telemetry());
  wire [15:0] expected;
  push2_surface_pixels_reference reference_pixels(.clk(clk),.rst(!reset_n || !dut.push_connected),
      .frame_ready(dut.frame_capture),.frame_start(),.x(dut.pixel_index[9:0]),.y(dut.pixel_index[17:10]),
      .pixel_valid(),.pixel(expected),.control(dut.control),.options(dut.options),.held(dut.actual_held),
      .note(dut.note),.velocity(dut.velocity),.display_meta(dut.display_meta_q),.display_meta_valid(dut.display_meta_seen),
      .score_mask(dut.service_state_q[31:0]),.score_running(dut.service_state_q[32]),.record_enabled(dut.service_state_q[33]),
      .guide_mode(dut.guide_mode),.guide_chosen(dut.guide_chosen),.guide_browse(dut.guide_browse),
      .guide_track(dut.track_index),.guide_track_count(dut.guide_track_count),.guide_score_count(dut.guide_score_count),
      .guide_cursor(dut.guide_cursor),.guide_analysis_done(dut.analysis_done_sync),
      .name_write_valid(1'b0),.name_write_addr(8'd0),.name_write_data(8'd0));
  task automatic put(input [7:0] a,input [31:0] d);
    @(negedge clk);select=1;write_bus=1;address=a;wdata=d;
    while(!ready)@(negedge clk);
    @(negedge clk);select=0;write_bus=0;
  endtask
  integer reads=0,stalls=0,wait_cycles=0;
  task automatic pixel_read;
    reg [17:0] old_index;
    reg [15:0] want;
    begin
      @(negedge clk);select=1;write_bus=0;address=8'h2c;wait_cycles=0;
      while(!ready)begin @(negedge clk);wait_cycles=wait_cycles+1;if(wait_cycles>5)$fatal(1,"pixel MMIO stalled");end
      old_index=dut.pixel_index;want=old_index[9:0]<960 ? expected : 16'd0;
      if(rdata!=={16'd0,want})$fatal(1,"pixel MMIO index=%0d got=%h expected=%h",old_index,rdata,want);
      @(negedge clk);select=0;reads=reads+1;stalls=stalls+wait_cycles;
      if(dut.pixel_index!==old_index+18'd1)$fatal(1,"pixel MMIO did not advance once");
    end
  endtask
  integer i;
  reg [17:0] index_value;
  initial begin
    repeat(8)@(negedge clk);reset_n=1;
    put(0,1);repeat(30)@(negedge clk);put(8,0);
    for(i=0;i<2100;i=i+1)pixel_read();
    for(i=0;i<500;i=i+1)begin
      index_value={8'($urandom_range(0,159)),10'($urandom_range(0,1023))};
      put(8'h28,{14'd0,index_value});pixel_read();pixel_read();
      if(i%13==0)put(8'h08,0);
    end
    put(0,0);put(0,1);repeat(30)@(negedge clk);put(8,0);pixel_read();
    $display("PASS push_pixel_mmio: %0d reads, %0d backpressure clocks, consecutive/wrap/invalid-column/rewind/frame/reconnect",reads,stalls);
    $finish;
  end
  initial begin #10000000;$fatal(1,"pixel MMIO timeout");end
endmodule
