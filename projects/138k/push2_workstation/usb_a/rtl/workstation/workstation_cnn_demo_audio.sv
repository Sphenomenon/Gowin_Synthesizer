`timescale 1ns/1ps
// CPU-facing subsystem candidate. Existing physical HDMI top is unchanged.
// preset_n resets only control state; audio reset remains independently owned.
module workstation_cnn_demo_audio #(
    parameter bit EXTERNAL_MASTER_VOLUME=0
) (
    input wire usb_event_valid,usb_lifecycle,usb_cancel,
    input wire [17:0] usb_event_data,
    output wire usb_event_ready,
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
    output wire [15:0] master_volume_o,
    output wire [31:0] scope_status_o,tf_scope_control_o,
    output wire [31:0] dac_reference_o,dac_voices_o,dac_health_o,
    output wire sample_ce_o, sample_valid_o,
    output wire signed [31:0] audio_left_o, audio_right_o,
    output wire [31:0] active_mask_o, deadline_miss_o, midi_overflow_o, note_drop_o,
    output wire [31:0] underrun_count_o, midi_cdc_drop_o, observation_drop_o,
    output wire uart_error_o,
    output wire [31:0] record_drop_o, led_mask_o, score_frame_o,
    output wire score_running_o, score_done_o,record_enabled_o,
    output wire display_valid_o,
    output wire [31:0] display_pcm_o, display_reference_o, display_voices_o, display_status_o,
    output wire [2:0] effect_mask_o,
    output wire [5:0] effect_order_o,
    // P10 delay DDR ring bridge (memory-domain side, see delay_ddr_dma)
    input wire delay_mem_clk_i, delay_mem_rst_ni,
    output wire delay_dwr_valid_o,
    output wire [64:0] delay_dwr_data_o,
    input wire delay_dwr_pop_i,
    input wire delay_drd_push_i,
    input wire [64:0] delay_drd_data_i,
    output wire delay_drd_ready_o);
    wire panel_event_valid;wire [6:0] panel_command;wire record_valid;wire [95:0] record_packet;
    wire [31:0] control_state,control_pitch,control_options,applied_events,pc_health;
    wire [127:0] held_notes;
    assign performance_words_o={32'h43545231,128'd0,control_pitch,control_options,held_notes,pc_health,control_state,applied_events};
    assign pready=1,pslverr=0,prdata=0;
    assign record_enabled_o=0;
    wire merged_valid,merged_ready;wire [17:0] merged_data;
    gw138k_usb_lifecycle_merge #(.EXPLICIT_LIFECYCLE(1)) u_usb_cpu_events(
        .clk(audio_clk),.reset_n(reset_n),
        .g1_valid(usb_event_valid),.g1_lifecycle(usb_lifecycle),.g1_cancel(usb_cancel),.g1_data(usb_event_data),.g1_ready(usb_event_ready),
        .pc_valid(1'b0),.pc_data(18'd0),.pc_ready(),.cpu_valid(1'b0),.cpu_data(18'd0),.cpu_ready(),
        .event_valid(merged_valid),.event_ready(merged_ready),.event_data(merged_data));
    workstation_cnn_demo_adapter #(.EXTERNAL_MASTER_VOLUME(EXTERNAL_MASTER_VOLUME)) u_audio(
        .master_volume_o(master_volume_o),
        .control_state_o(control_state),.control_pitch_o(control_pitch),.control_options_o(control_options),.scope_status_o(scope_status_o),.tf_scope_control_o(tf_scope_control_o),.dac_reference_o(dac_reference_o),.dac_voices_o(dac_voices_o),.dac_health_o(dac_health_o),
        .pc_uart_rx_i(pc_uart_rx_i),.held_notes_o(held_notes),.applied_events_o(applied_events),.pc_health_o(pc_health),
        .panel_event_valid_o(panel_event_valid),.panel_command_o(panel_command),
        .cpu_event_valid_i(merged_valid),.cpu_event_ready_o(merged_ready),.cpu_event_i(merged_data),
        .clk_50m(clk_50m),.audio_clk(audio_clk),.reset_n(reset_n),.midi_rx_i(midi_rx_i),
        .hp_bck(hp_bck),.hp_ws(hp_ws),.hp_din(hp_din),.pa_en(pa_en),
        .sample_ce_o(sample_ce_o),.sample_valid_o(sample_valid_o),.audio_left_o(audio_left_o),.audio_right_o(audio_right_o),
        .active_mask_o(active_mask_o),.deadline_miss_o(deadline_miss_o),.midi_overflow_o(midi_overflow_o),
        .note_drop_o(note_drop_o),.underrun_count_o(underrun_count_o),.midi_cdc_drop_o(midi_cdc_drop_o),
        .observation_drop_o(observation_drop_o),.uart_error_o(uart_error_o),
        .record_enable_i(1'b0),.record_ready_i(1'b1),.record_valid_o(record_valid),
        .record_packet_o(record_packet),.record_drop_o(record_drop_o),
        .fft_valid_o(),.fft_bin_o(),.fft_real_o(),.fft_imag_o(),.fft_frame_o(),
        .score_write_i(1'b0),.score_address_i(8'd0),.score_data_i(64'd0),
        .score_length_i(9'd0),.score_start_i(1'b0),.score_stop_i(1'b0),
        .score_running_o(score_running_o),.score_done_o(score_done_o),.led_mask_o(led_mask_o),.score_frame_o(score_frame_o),
        .display_valid_o(display_valid_o),.display_pcm_o(display_pcm_o),.display_reference_o(display_reference_o),
        .display_voices_o(display_voices_o),.display_status_o(display_status_o),.effect_mask_o(effect_mask_o),.effect_order_o(effect_order_o),
        .delay_mem_clk_i(delay_mem_clk_i),.delay_mem_rst_ni(delay_mem_rst_ni),
        .delay_dwr_valid_o(delay_dwr_valid_o),.delay_dwr_data_o(delay_dwr_data_o),.delay_dwr_pop_i(delay_dwr_pop_i),
        .delay_drd_push_i(delay_drd_push_i),.delay_drd_data_i(delay_drd_data_i),.delay_drd_ready_o(delay_drd_ready_o));
endmodule
