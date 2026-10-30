`timescale 1ns/1ps

// Explicit opt-in composition of the native control and synthesis engines.
// This boundary has no effects, PCM/source routing, or final volume policy.
// Oscillator committed rate is the sole rate authority for all three blocks.
module workstation_runtime_render_engines #(
    parameter bit RUNTIME_RATE_ENABLE=0
) (
    input logic clk_i, rst_ni, panic_i,
    input logic sample_ce_i,
    input logic rate_commit_i, rate_44100_i,
    output wire rate_ready_o, applied_rate_44100_o, quiescent_o,
    input logic [21:0] target_ratio_q20_i,
    input logic [15:0] glide_step_q20_i,
    input logic [6:0] vibrato_depth_i,
    output wire [21:0] pitch_q20_o,
    input logic mode_set_valid_i,
    output wire mode_set_ready_o,
    input logic [1:0] mode_i,
    output wire [1:0] current_mode_o,
    input logic event_valid_i, event_note_on_i, scope_enable_i,
    input logic [2:0] event_profile_i,
    input logic [6:0] event_note_i, event_off_note_i, event_velocity_i,
    output wire synth_event_ready_o, vector_event_ready_o,
    input logic expression_valid_i,
    input logic [6:0] expression_note_i, expression_value_i,
    output wire expression_ready_o,
    output wire synth_sample_ready_o, synth_valid_o,
    output wire signed [31:0] synth_o,
    output wire [31:0] allocated_mask_o, synth_active_mask_o,
    output wire [5:0] synth_active_count_o,
    output wire load_busy_o, mix_busy_o,
    output wire [7:0] issued_slot_count_o,
    input logic [2:0] vector_shape_i, vector_morph_shape_i,
    input logic [15:0] vector_morph_q15_i, vector_scale_q15_i,
    input logic [6:0] vector_rotation_i,
    input logic signed [15:0] vector_cal_x_q14_i, vector_cal_y_q14_i,
    input logic signed [31:0] vector_offset_x_i, vector_offset_y_i,
    output wire vector_sample_ready_o, vector_valid_o, vector_busy_o,
    output wire signed [31:0] vector_left_o, vector_right_o,
    output wire [7:0] vector_active_mask_o,
    output wire [3:0] vector_active_count_o,
    output wire [31:0] vector_rejected_o,
    output wire vector_config_error_o, vector_frequency_error_o, vector_clip_o
);
    wire oscillator_quiescent, oscillator_rate_ready;
    // Actual engine state only: safe to feed an outer request admission gate.
    // Same-cycle input guards belong to rate_ready, not the idle observation.
    assign quiescent_o = rst_ni && oscillator_quiescent &&
        vector_sample_ready_o && !vector_valid_o && !vector_busy_o;
    assign rate_ready_o = RUNTIME_RATE_ENABLE && quiescent_o &&
        oscillator_rate_ready && !panic_i && !sample_ce_i &&
        !event_valid_i && !expression_valid_i && !mode_set_valid_i;

    workstation_rate_pitch_expression pitch (
        .clk_i, .rst_ni, .sample_ce_i, .rate_44k1_i(applied_rate_44100_o),
        .target_ratio_q20_i, .glide_step_q20_i, .vibrato_depth_i,
        .ratio_q20_o(pitch_q20_o)
    );
    workstation_runtime_oscillator_engine #(
        .EXPRESSION_ENABLE(1), .SAMPLE_RATE_HZ(48000),
        .SEPARATE_OFF_NOTE(1), .RUNTIME_RATE_ENABLE(RUNTIME_RATE_ENABLE),
        .PIPELINED_ENVELOPE(RUNTIME_RATE_ENABLE), .PIPELINED_RATE(RUNTIME_RATE_ENABLE)
    ) oscillator (
        .clk_i, .rst_ni, .panic_i, .mode_set_valid_i,
        .mode_set_ready_o, .mode_i, .current_mode_o,
        .event_valid_i(event_valid_i && !scope_enable_i),
        .event_ready_o(synth_event_ready_o), .event_note_on_i,
        .event_profile_i, .event_midi_note_i(event_note_i),
        .event_off_note_i, .event_velocity_i,
        .expression_valid_i(expression_valid_i && !scope_enable_i),
        .expression_ready_o, .expression_note_i, .expression_value_i,
        .pitch_ratio_q20_i(pitch_q20_o), .sample_ce_i,
        .sample_ready_o(synth_sample_ready_o), .sample_valid_o(synth_valid_o),
        .sample_o(synth_o), .allocated_mask_o, .active_mask_o(synth_active_mask_o),
        .active_voice_count_o(synth_active_count_o), .load_busy_o, .mix_busy_o,
        .issued_slot_count_o,
        .rate_commit_i(rate_commit_i && rate_ready_o), .rate_44100_i,
        .rate_ready_o(oscillator_rate_ready), .applied_rate_44100_o,
        .quiescent_o(oscillator_quiescent)
    );
    workstation_runtime_scope_vec #(.SEPARATE_OFF_NOTE(1),.PIPELINED_RATE(RUNTIME_RATE_ENABLE)) vector_engine (
        .clk_i, .rst_ni, .panic_i, .sample_ce_i,
        .rate_44k1_i(applied_rate_44100_o),
        .sample_ready_o(vector_sample_ready_o), .sample_valid_o(vector_valid_o),
        .left_o(vector_left_o), .right_o(vector_right_o),
        .event_valid_i(event_valid_i && scope_enable_i), .event_note_on_i,
        .event_ready_o(vector_event_ready_o), .event_note_i, .event_off_note_i,
        .event_velocity_i, .event_profile_i,
        .event_shape_i(vector_shape_i), .event_morph_shape_i(vector_morph_shape_i),
        .event_pitch_q20_i(22'd1048576), .pitch_q20_i(pitch_q20_o),
        .morph_q15_i(vector_morph_q15_i), .scale_q15_i(vector_scale_q15_i),
        .rotation_i(vector_rotation_i), .cal_x_q14_i(vector_cal_x_q14_i),
        .cal_y_q14_i(vector_cal_y_q14_i), .offset_x_i(vector_offset_x_i),
        .offset_y_i(vector_offset_y_i), .active_mask_o(vector_active_mask_o),
        .active_count_o(vector_active_count_o), .rejected_events_o(vector_rejected_o),
        .config_error_o(vector_config_error_o),
        .frequency_error_o(vector_frequency_error_o), .clip_o(vector_clip_o),
        .busy_o(vector_busy_o)
    );
endmodule
