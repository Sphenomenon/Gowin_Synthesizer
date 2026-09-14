`timescale 1ns/1ps

module tb_unified_mode2_32;
  logic clk_i = 1'b0;
  // 76.8 MHz audio clock: one 48 kHz sample period is 1600 cycles.
  always #6.510416 clk_i = ~clk_i;

  logic rst_ni = 1'b0;
  logic mode_set_valid_i = 1'b0;
  logic mode_set_ready_o;
  logic [1:0] mode_i = 2'd2;
  logic [1:0] current_mode_o;
  logic event_valid_i = 1'b0;
  logic event_ready_o;
  logic event_note_on_i = 1'b0;
  logic [2:0] event_profile_i = 3'd0;
  logic [6:0] event_midi_note_i = 7'd60;
  logic [6:0] event_velocity_i = 7'd100;
  logic [21:0] pitch_ratio_q20_i = 22'd1048576;
  logic sample_ce_i = 1'b0;
  logic sample_ready_o;
  logic sample_valid_o;
  logic signed [31:0] sample_o;
  logic [31:0] allocated_mask_o;
  logic [31:0] active_mask_o;
  logic [5:0] active_voice_count_o;
  logic load_busy_o;
  logic mix_busy_o;
  logic [7:0] issued_slot_count_o;

  unified_oscillator_engine #(.EXPRESSION_ENABLE(1'b0), .SAMPLE_RATE_HZ(192000)) dut (
      .clk_i, .rst_ni,
      .mode_set_valid_i, .mode_set_ready_o, .mode_i, .current_mode_o,
      .event_valid_i, .event_ready_o, .event_note_on_i, .event_profile_i,
      .event_midi_note_i, .event_velocity_i, .pitch_ratio_q20_i,
      .sample_ce_i, .sample_ready_o, .sample_valid_o, .sample_o,
      .allocated_mask_o, .active_mask_o, .active_voice_count_o,
      .load_busy_o, .mix_busy_o, .issued_slot_count_o);

  task automatic set_mode(input logic [1:0] mode);
    begin
      @(negedge clk_i);
      while (!mode_set_ready_o) @(negedge clk_i);
      mode_i = mode;
      mode_set_valid_i = 1'b1;
      @(negedge clk_i);
      mode_set_valid_i = 1'b0;
    end
  endtask

  task automatic send_note(input logic [6:0] note);
    begin
      @(negedge clk_i);
      while (!event_ready_o) @(negedge clk_i);
      event_midi_note_i = note;
      event_note_on_i = 1'b1;
      event_valid_i = 1'b1;
      @(negedge clk_i);
      event_valid_i = 1'b0;
      event_note_on_i = 1'b0;
      while (!event_ready_o) @(negedge clk_i);
    end
  endtask

  integer i;
  integer wait_cycles;
  integer issue_cycles;
  bit saw_last;
  bit saw_sample;

  initial begin
    repeat (5) @(negedge clk_i);
    rst_ni = 1'b1;
    set_mode(2'd2);
    if (current_mode_o !== 2'd2) $fatal(1, "mode did not switch to C");

    for (i = 0; i < 32; i = i + 1) begin
      send_note(7'd36 + i[6:0]);
    end

    wait_cycles = 0;
    while (allocated_mask_o !== 32'hffff_ffff && wait_cycles < 20000) begin
      @(negedge clk_i);
      wait_cycles = wait_cycles + 1;
    end
    if (allocated_mask_o !== 32'hffff_ffff)
      $fatal(1, "C mode did not allocate 32 voices: %h", allocated_mask_o);
    if (active_voice_count_o !== 6'd32)
      $fatal(1, "C mode active count is %0d", active_voice_count_o);

    @(negedge clk_i);
    while (!sample_ready_o) @(negedge clk_i);
    sample_ce_i = 1'b1;
    @(negedge clk_i);
    sample_ce_i = 1'b0;

    issue_cycles = 0;
    saw_last = 1'b0;
    saw_sample = 1'b0;
    wait_cycles = 0;
    while ((!saw_last || !saw_sample) && wait_cycles < 5000) begin
      @(posedge clk_i);
      if (dut.slot_read_valid) begin
        issue_cycles = issue_cycles + 1;
        if (dut.slot_read_last) saw_last = 1'b1;
      end
      if (sample_valid_o) saw_sample = 1'b1;
      wait_cycles = wait_cycles + 1;
    end
    if (!saw_last) $fatal(1, "C mode scan did not reach final slot");
    if (issue_cycles !== 1024)
      $fatal(1, "C mode scanned %0d slots, expected 1024", issue_cycles);
    if (!saw_sample) $fatal(1, "C mode sample result did not return");
    if (wait_cycles > 1600)
      $fatal(1, "C mode sample exceeded 48 kHz deadline: %0d cycles", wait_cycles);
    $display("PASS C_MODE_32 allocated=%h active=%0d issue_cycles=%0d sample_latency=%0d",
        allocated_mask_o, active_voice_count_o, issue_cycles, wait_cycles);
    $finish;
  end
endmodule
