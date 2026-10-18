`timescale 1ns/1ps

module tb_panic_spectrum;
  logic clk = 0;
  always #6.510416 clk = ~clk;
  logic rst_n = 0;
  logic cpu_valid = 0;
  wire cpu_ready;
  logic [17:0] cpu_event = 0;
  logic sample_ce = 0;
  integer sample_div = 0;
  wire sample_valid;
  wire signed [31:0] left, right;
  wire [31:0] active;
  wire [9:0] panic_epoch;
  wire clip;

  gw138k_event_workstation dut(
      .clk_i(clk),.rst_ni(rst_n),.midi_byte_valid_i(1'b0),.midi_byte_i(8'd0),
      .pc_byte_valid_i(1'b0),.pc_byte_i(8'd0),.held_notes_o(),.applied_events_o(),
      .pc_overflow_o(),.control_options_o(),.panic_epoch_o(panic_epoch),
      .cpu_event_valid_i(cpu_valid),.cpu_event_i(cpu_event),.cpu_event_ready_o(cpu_ready),
      .sample_ce_i(sample_ce),.pcm_left_i(32'sd0),.pcm_right_i(32'sd0),
      .sample_valid_o(sample_valid),.left_o(left),.right_o(right),
      .synth_valid_o(),.synth_o(),.active_mask_o(active),.active_voice_count_o(),
      .mode_o(),.pitch_q20_o(),.deadline_miss_o(),.midi_overflow_o(),
      .note_drop_o(),.clip_o(clip),.synth_gain_o(),.pcm_gain_o(),.route_o(),
      .profile_o(),.effect_mask_o(),.effect_order_o());

  always @(negedge clk) begin
    if(!rst_n) begin sample_div <= 0; sample_ce <= 0; end
    else if(sample_div == 1599) begin sample_div <= 0; sample_ce <= 1; end
    else begin sample_div <= sample_div + 1; sample_ce <= 0; end
  end

  task automatic send_event(input [3:0] kind,input [6:0] a,input [6:0] b);
    begin
      @(negedge clk);while(!cpu_ready)@(negedge clk);
      cpu_event={kind,a,b};cpu_valid=1;
      @(negedge clk);cpu_valid=0;
    end
  endtask

  integer fd,frames,pre_count,post_count;
  integer capture_pre,capture_post;
  string output_path;
  always @(posedge clk) if(sample_valid) begin
    frames <= frames + 1;
    if(capture_pre) begin
      $fwrite(fd,"pre,%0d,%0d\n",$signed(left),$signed(right));
      pre_count <= pre_count + 1;
    end
    if(capture_post) begin
      $fwrite(fd,"post,%0d,%0d\n",$signed(left),$signed(right));
      post_count <= post_count + 1;
      if(left || right)$fatal(1,"nonzero PCM after hard PANIC left=%0d right=%0d",left,right);
    end
  end

  initial begin
    frames=0;pre_count=0;post_count=0;capture_pre=0;capture_post=0;
    if(!$value$plusargs("OUT=%s",output_path))$fatal(1,"missing OUT");
    fd=$fopen(output_path,"w");if(!fd)$fatal(1,"cannot open output");
    repeat(10)@(negedge clk);rst_n=1;
    // Real production allocator, oscillator and serial effect chain.  Fill
    // all three effects before taking the reference block.
    send_event(4'd2,7'd80,7'd0);
    send_event(4'd3,7'd40,7'd0);
    send_event(4'd2,7'd81,7'd7);
    send_event(4'd2,7'd84,7'd2);
    send_event(4'd2,7'd85,7'd0);
    send_event(4'd2,7'd86,7'd1);
    send_event(4'd1,7'd60,7'd120);
    wait(active!=0);wait(frames>=1000);
    capture_pre=1;wait(pre_count>=2048);@(negedge clk);capture_pre=0;
    send_event(4'd2,7'd120,7'd0);
    repeat(4)@(posedge clk);@(negedge clk);
    if(panic_epoch!=1 || active!=0)$fatal(1,"PANIC did not clear before post capture");
    capture_post=1;wait(post_count>=4096);@(negedge clk);capture_post=0;
    $fclose(fd);
    if(clip)$fatal(1,"unexpected effect clip");
    $display("PASS P25 PANIC spectrum capture pre=%0d post=%0d post_nonzero=0 epoch=%0d",
        pre_count,post_count,panic_epoch);
    $finish;
  end

  initial begin
    #500000000;
    $fatal(1,"P25 PANIC spectrum timeout");
  end
endmodule
