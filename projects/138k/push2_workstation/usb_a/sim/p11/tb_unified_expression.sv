`timescale 1ns/1ps

module tb_unified_expression;
  logic clk = 1'b0;
  always #6.510416 clk = ~clk;
  logic rst = 1'b0;
  logic mode_valid = 1'b0;
  logic mode_ready;
  logic [1:0] mode = 2'd2, current_mode;
  logic event_valid = 1'b0, event_ready, note_on = 1'b0;
  logic expression_valid = 1'b0, expression_ready;
  logic [6:0] expression_note = 0, expression_value = 0;
  logic [2:0] profile = 0;
  logic [6:0] note = 60, velocity = 100;
  logic [21:0] ratio = 22'd1048576;
  logic sample_ce = 0, sample_ready, sample_valid;
  logic signed [31:0] sample;
  logic [31:0] allocated, active;
  logic [5:0] active_count;
  logic load_busy, mix_busy;
  logic [7:0] issued;

  unified_oscillator_engine #(.EXPRESSION_ENABLE(1'b0), .SAMPLE_RATE_HZ(192000)) dut(
      .clk_i(clk), .rst_ni(rst), .mode_set_valid_i(mode_valid),
      .mode_set_ready_o(mode_ready), .mode_i(mode), .current_mode_o(current_mode),
      .event_valid_i(event_valid), .event_ready_o(event_ready),
      .event_note_on_i(note_on), .expression_valid_i(expression_valid),
      .expression_ready_o(expression_ready), .expression_note_i(expression_note),
      .expression_value_i(expression_value), .event_profile_i(profile),
      .event_midi_note_i(note), .event_velocity_i(velocity),
      .pitch_ratio_q20_i(ratio), .sample_ce_i(sample_ce),
      .sample_ready_o(sample_ready), .sample_valid_o(sample_valid), .sample_o(sample),
      .allocated_mask_o(allocated), .active_mask_o(active),
      .active_voice_count_o(active_count), .load_busy_o(load_busy),
      .mix_busy_o(mix_busy), .issued_slot_count_o(issued));

  task automatic send_note;
    begin
      @(negedge clk); while (!event_ready) @(negedge clk);
      event_valid = 1'b1; note_on = 1'b1;
      @(negedge clk); event_valid = 1'b0; note_on = 1'b0;
      while (!event_ready) @(negedge clk);
    end
  endtask

  task automatic send_pressure(input logic [6:0] value);
    begin
      @(negedge clk); while (!expression_ready) @(negedge clk);
      expression_note = 7'd60; expression_value = value; expression_valid = 1'b1;
      @(negedge clk); expression_valid = 1'b0;
      while (!expression_ready) @(negedge clk);
    end
  endtask

  initial begin
    repeat (5) @(negedge clk);
    rst = 1'b1;
    @(negedge clk); while (!mode_ready) @(negedge clk);
    mode_valid = 1'b1; @(negedge clk); mode_valid = 1'b0;
    send_note();
    while (active_count != 6'd1) @(negedge clk);
    send_pressure(7'd0);
    if (dut.expression_gain_q8[0] !== 8'd0)
      $fatal(1, "pressure zero was not latched: %0d", dut.expression_gain_q8[0]);
    send_pressure(7'd127);
    if (dut.expression_gain_q8[0] !== 8'd128)
      $fatal(1, "pressure full was not latched: %0d", dut.expression_gain_q8[0]);
    $display("PASS UNIFIED_EXPRESSION note=%0d gain_zero_then_full=0,128", note);
    $finish;
  end
endmodule
