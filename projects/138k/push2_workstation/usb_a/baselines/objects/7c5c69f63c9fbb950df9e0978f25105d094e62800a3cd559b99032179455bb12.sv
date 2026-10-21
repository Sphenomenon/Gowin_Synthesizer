`timescale 1ns/1ps
// CPU-facing subsystem candidate. Existing physical HDMI top is unchanged.
// preset_n resets only control state; audio reset remains independently owned.
module gw138k_controlled_audio (
    input wire clk_50m, audio_clk, reset_n, midi_rx_i,
    input wire pc_uart_rx_i,
    output wire [447:0] performance_words_o,
    input wire pclk, preset_n, psel, penable, pwrite,
    input wire [11:0] paddr,
    input wire [31:0] pwdata,
    input wire [3:0] pstrb,
    output wire pready, pslverr,
    output wire [31:0] prdata,
    output wire hp_bck, hp_ws, hp_din, pa_en,
    output wire sample_ce_o, sample_valid_o,
    output wire signed [31:0] audio_left_o, audio_right_o,
    output wire [31:0] active_mask_o, deadline_miss_o, midi_overflow_o, note_drop_o,
    output wire [31:0] underrun_count_o, midi_cdc_drop_o, observation_drop_o,
    output wire uart_error_o,
    output wire [31:0] record_drop_o, led_mask_o, score_frame_o,
    output wire score_running_o, score_done_o,
    output wire display_valid_o,
    output wire [31:0] display_pcm_o, display_reference_o, display_voices_o, display_status_o
);
    wire command_reset_n,command_valid,command_ready,command_write,response_error;
    wire [11:0] command_address;
    wire [31:0] command_data,response_data;
    wire [3:0] command_strobes;
    gw138k_apb_cdc u_control_cdc(
        .reset_n(reset_n && preset_n),.pclk(pclk),.audio_clk(audio_clk),
        .psel(psel),.penable(penable),.pwrite(pwrite),.paddr(paddr),.pwdata(pwdata),.pstrb(pstrb),
        .pready(pready),.pslverr(pslverr),.prdata(prdata),
        .command_reset_n(command_reset_n),.command_valid(command_valid),.command_ready(command_ready),
        .command_write(command_write),.command_address(command_address),.command_data(command_data),
        .command_strobes(command_strobes),.response_data(response_data),.response_error(response_error));
    wire cpu_event_valid,cpu_event_ready;
    wire [31:0] control_state,control_pitch,control_options,applied_events,pc_health;
    wire [127:0] held_notes;
    wire [31:0] snap_status,snap_left,snap_right,snap_sequence;
    // Low half is the unchanged K138 payload; upper half is E138 control/snapshot telemetry.
    assign performance_words_o={32'h43545231,snap_sequence,snap_right,snap_left,snap_status,control_pitch,control_options,held_notes,pc_health,control_state,applied_events};
    wire [17:0] cpu_event;
    wire record_enable,record_valid,record_ready,score_write,score_start,score_stop;
    wire [95:0] record_packet;
    wire [7:0] score_address;
    wire [63:0] score_data;
    wire [8:0] score_length;
    wire [31:0] midi_drop_audio;
    gw138k_counter_cdc u_midi_drop_cdc(.reset_n(reset_n),.source_clk(clk_50m),
        .destination_clk(audio_clk),.source_count(midi_cdc_drop_o),.destination_count(midi_drop_audio));
    gw138k_controlled_services u_services(
        .control_state(control_state),.control_pitch(control_pitch),.control_options(control_options),
        .held_notes(held_notes),.applied_events(applied_events),.pc_health(pc_health),
        .cpu_event_valid(cpu_event_valid),.cpu_event_ready(cpu_event_ready),.cpu_event(cpu_event),
        .panel_event_valid(1'b0),.panel_command(7'd0),.panel_event_ready(),
        .clk(audio_clk),.reset_n(command_reset_n),.command_valid(command_valid),
        .command_write(command_write),.command_address(command_address),.command_data(command_data),
        .command_strobes(command_strobes),.command_ready(command_ready),.response_data(response_data),
        .response_error(response_error),.sample_valid(sample_valid_o),
        .active_mask(active_mask_o),.deadline_miss(deadline_miss_o),.midi_overflow(midi_overflow_o),
        .note_drop(note_drop_o),.underrun_count(underrun_count_o),.midi_cdc_drop(midi_drop_audio),
        .observation_drop(observation_drop_o),.record_drop(record_drop_o),
        .snap_status(snap_status),.snap_left(snap_left),.snap_right(snap_right),.snap_sequence(snap_sequence),
        .record_enable(record_enable),.record_valid(record_valid),.record_packet(record_packet),.record_ready(record_ready),
        .score_write(score_write),.score_start(score_start),.score_stop(score_stop),
        .score_address(score_address),.score_data(score_data),.score_length(score_length),
        .score_running(score_running_o),.score_done(score_done_o),.led_mask(led_mask_o),.score_frame(score_frame_o));
    gw138k_controlled_adapter u_audio(
        .control_state_o(control_state),.control_pitch_o(control_pitch),.control_options_o(control_options),.scope_status_o(),.tf_scope_control_o(),.dac_reference_o(),.dac_voices_o(),.dac_health_o(),
        .pc_uart_rx_i(pc_uart_rx_i),.held_notes_o(held_notes),.applied_events_o(applied_events),.pc_health_o(pc_health),
        .cpu_event_valid_i(cpu_event_valid),.cpu_event_ready_o(cpu_event_ready),.cpu_event_i(cpu_event),
        .clk_50m(clk_50m),.audio_clk(audio_clk),.reset_n(reset_n),.midi_rx_i(midi_rx_i),
        .hp_bck(hp_bck),.hp_ws(hp_ws),.hp_din(hp_din),.pa_en(pa_en),
        .sample_ce_o(sample_ce_o),.sample_valid_o(sample_valid_o),.audio_left_o(audio_left_o),.audio_right_o(audio_right_o),
        .active_mask_o(active_mask_o),.deadline_miss_o(deadline_miss_o),.midi_overflow_o(midi_overflow_o),
        .note_drop_o(note_drop_o),.underrun_count_o(underrun_count_o),.midi_cdc_drop_o(midi_cdc_drop_o),
        .observation_drop_o(observation_drop_o),.uart_error_o(uart_error_o),
        .record_enable_i(record_enable),.record_ready_i(record_ready),.record_valid_o(record_valid),
        .record_packet_o(record_packet),.record_drop_o(record_drop_o),
        .fft_valid_o(),.fft_bin_o(),.fft_real_o(),.fft_imag_o(),.fft_frame_o(),
        .score_write_i(score_write),.score_address_i(score_address),.score_data_i(score_data),
        .score_length_i(score_length),.score_start_i(score_start),.score_stop_i(score_stop),
        .score_running_o(score_running_o),.score_done_o(score_done_o),.led_mask_o(led_mask_o),.score_frame_o(score_frame_o),
        .display_valid_o(display_valid_o),.display_pcm_o(display_pcm_o),.display_reference_o(display_reference_o),
        .display_voices_o(display_voices_o),.display_status_o(display_status_o));
endmodule
