`include "rtl/ddr_address_map.vh"
module workstation_usb2_audio #(
    parameter ROM_FILE = "usb2_cpu.hex",
    parameter integer CPU_FREQUENCY_HZ = 48000000,
    parameter integer ATTACH_DEBOUNCE_US = 100000,
    parameter integer BUS_TIMEOUT_CYCLES = 480000
)(
    input wire clk_cpu, clk_ref, clk_ulpi, clk_audio, clk_memory,
    input wire reset_n, audio_reset_n, memory_reset_n, control_reset_n,
    input wire uart_rx_i, midi_rx_i, pc_uart_rx_i,
    output wire uart_tx_o,
    input wire [7:0] ulpi_data_i,
    input wire ulpi_dir_i, ulpi_nxt_i,
    output wire [7:0] ulpi_data_o,
    output wire ulpi_data_oe_o, ulpi_stp_o,
    input wire [63:0] display_meta_data_i,
    input wire display_meta_valid_i,
    input wire [33:0] service_state_data_i,
    input wire service_state_valid_i,
    input wire score_valid_i, analysis_done_i,
    output wire score_ready_o,
    input wire [6:0] score_note_i,
    input wire playlist_valid_i,
    output wire playlist_ready_o,
    input wire [15:0] playlist_word_i,
    output wire track_launch_o,
    output wire [3:0] track_index_o,
    input wire psel_i, penable_i, pwrite_i,
    input wire [11:0] paddr_i,
    input wire [31:0] pwdata_i,
    input wire [3:0] pstrb_i,
    output wire pready_o, pslverr_o,
    output wire [31:0] prdata_o,
    output wire [223:0] telemetry_o,
    output wire [447:0] performance_words_o,
    output wire performance_valid_o,
    output wire [31:0] feedback_drop_o, canceled_requests_o,
    output wire [3:0] cpu_fault_o,
    output wire [31:0] cpu_fault_address_o,
    output wire transaction_reset_n_o, phy_ready_o, failed_o, high_speed_o, traffic_enable_o,
    output wire [31:0] sof_count_o,
    output wire reference_bck_o, reference_ws_o, reference_din_o, reference_pa_en_o,
    output wire sample_ce_o, sample_valid_o,
    output wire signed [31:0] audio_left_o, audio_right_o,
    output wire [31:0] active_mask_o, deadline_miss_o, midi_overflow_o, note_drop_o,
    output wire [31:0] underrun_count_o, midi_cdc_drop_o, observation_drop_o,
    output wire uart_error_o,
    output wire [31:0] record_drop_o, led_mask_o, score_frame_o,
    output wire score_running_o, score_done_o, record_enabled_o,
    output wire display_valid_o,
    output wire [31:0] display_pcm_o, display_reference_o, display_voices_o, display_status_o,
    output wire [2:0] effect_mask_o,
    output wire [5:0] effect_order_o,
    output wire [31:0] scope_status_o, tf_scope_control_o,
    output wire [31:0] dac_reference_o, dac_voices_o, dac_health_o,
    output wire delay_ddr_request_o, delay_ddr_write_o,
    output wire [28:0] delay_ddr_address_o,
    output wire [255:0] delay_ddr_data_o,
    output wire [31:0] delay_ddr_mask_o,
    input wire delay_ddr_ready_i, delay_ddr_response_i,
    input wire [255:0] delay_ddr_read_data_i,
    output wire [7:0] delay_ddr_debug_o
);
    wire processing_reset_n = reset_n && audio_reset_n;
    wire usb_event_valid, usb_event_ready, usb_lifecycle, usb_cancel;
    wire [17:0] usb_event;
    wire [447:0] audio_performance;
    wire delay_dwr_valid, delay_dwr_pop, delay_drd_push, delay_drd_ready;
    wire [64:0] delay_dwr_data, delay_drd_data;
    reg [11:0] feedback_divider;

    always @(posedge clk_audio or negedge processing_reset_n)
        if (!processing_reset_n) feedback_divider <= 0;
        else feedback_divider <= feedback_divider + 1'b1;

    gw138k_stream_cdc #(.WIDTH(448)) audio_feedback (
        .reset_n(processing_reset_n), .source_clk(clk_audio), .destination_clk(clk_ref),
        .source_valid(&feedback_divider), .source_data(audio_performance), .drop_count(feedback_drop_o),
        .destination_valid(performance_valid_o), .destination_data(performance_words_o)
    );
    workstation_usb2_input #(.ROM_FILE(ROM_FILE), .CPU_FREQUENCY_HZ(CPU_FREQUENCY_HZ),
                            .ATTACH_DEBOUNCE_US(ATTACH_DEBOUNCE_US), .BUS_TIMEOUT_CYCLES(BUS_TIMEOUT_CYCLES)) usb_input (
        .clk_cpu(clk_cpu), .clk_ref(clk_ref), .clk_ulpi(clk_ulpi), .clk_audio(clk_audio),
        .reset_n(reset_n), .audio_reset_n(audio_reset_n), .uart_rx_i(uart_rx_i), .uart_tx_o(uart_tx_o),
        .ulpi_data_i(ulpi_data_i), .ulpi_dir_i(ulpi_dir_i), .ulpi_nxt_i(ulpi_nxt_i),
        .ulpi_data_o(ulpi_data_o), .ulpi_data_oe_o(ulpi_data_oe_o), .ulpi_stp_o(ulpi_stp_o),
        .performance_words_i(performance_words_o), .display_meta_data_i(display_meta_data_i),
        .display_meta_valid_i(display_meta_valid_i), .service_state_data_i(service_state_data_i),
        .service_state_valid_i(service_state_valid_i), .score_valid_i(score_valid_i), .analysis_done_i(analysis_done_i),
        .score_ready_o(score_ready_o), .score_note_i(score_note_i), .playlist_valid_i(playlist_valid_i),
        .playlist_ready_o(playlist_ready_o), .playlist_word_i(playlist_word_i),
        .track_launch_o(track_launch_o), .track_index_o(track_index_o), .audio_valid_o(usb_event_valid),
        .audio_ready_i(usb_event_ready), .audio_event_o(usb_event), .audio_lifecycle_o(usb_lifecycle),
        .audio_cancel_o(usb_cancel), .telemetry_o(telemetry_o), .canceled_requests_o(canceled_requests_o),
        .cpu_fault_o(cpu_fault_o), .cpu_fault_address_o(cpu_fault_address_o),
        .transaction_reset_n_o(transaction_reset_n_o), .phy_ready_o(phy_ready_o), .failed_o(failed_o),
        .high_speed_o(high_speed_o), .traffic_enable_o(traffic_enable_o), .sof_count_o(sof_count_o)
    );
    gw138k_usb_controlled_audio audio (
        .usb_event_valid(usb_event_valid), .usb_lifecycle(usb_lifecycle), .usb_cancel(usb_cancel),
        .usb_event_data(usb_event), .usb_event_ready(usb_event_ready), .clk_50m(clk_ref), .audio_clk(clk_audio),
        .reset_n(processing_reset_n), .midi_rx_i(midi_rx_i), .pc_uart_rx_i(pc_uart_rx_i),
        .performance_words_o(audio_performance), .pclk(clk_ref), .preset_n(control_reset_n),
        .psel(psel_i), .penable(penable_i), .pwrite(pwrite_i), .paddr(paddr_i), .pwdata(pwdata_i), .pstrb(pstrb_i),
        .pready(pready_o), .pslverr(pslverr_o), .prdata(prdata_o),
        .hp_bck(reference_bck_o), .hp_ws(reference_ws_o), .hp_din(reference_din_o), .pa_en(reference_pa_en_o),
        .scope_status_o(scope_status_o), .tf_scope_control_o(tf_scope_control_o),
        .dac_reference_o(dac_reference_o), .dac_voices_o(dac_voices_o), .dac_health_o(dac_health_o),
        .sample_ce_o(sample_ce_o), .sample_valid_o(sample_valid_o),
        .audio_left_o(audio_left_o), .audio_right_o(audio_right_o), .active_mask_o(active_mask_o),
        .deadline_miss_o(deadline_miss_o), .midi_overflow_o(midi_overflow_o), .note_drop_o(note_drop_o),
        .underrun_count_o(underrun_count_o), .midi_cdc_drop_o(midi_cdc_drop_o), .observation_drop_o(observation_drop_o),
        .uart_error_o(uart_error_o), .record_drop_o(record_drop_o), .led_mask_o(led_mask_o), .score_frame_o(score_frame_o),
        .score_running_o(score_running_o), .score_done_o(score_done_o), .record_enabled_o(record_enabled_o),
        .display_valid_o(display_valid_o), .display_pcm_o(display_pcm_o), .display_reference_o(display_reference_o),
        .display_voices_o(display_voices_o), .display_status_o(display_status_o),
        .effect_mask_o(effect_mask_o), .effect_order_o(effect_order_o),
        .delay_mem_clk_i(clk_memory), .delay_mem_rst_ni(memory_reset_n),
        .delay_dwr_valid_o(delay_dwr_valid), .delay_dwr_data_o(delay_dwr_data), .delay_dwr_pop_i(delay_dwr_pop),
        .delay_drd_push_i(delay_drd_push), .delay_drd_data_i(delay_drd_data), .delay_drd_ready_o(delay_drd_ready)
    );
    delay_ddr_dma #(.DELAY_BITS(14), .ECHO_SAMPLES(9600), .RING_APP_BASE(`PRJ1_DDR_BULK_POOL_APP_BASE)) delay_memory (
        .clk_i(clk_memory), .rst_ni(memory_reset_n), .dwr_valid_i(delay_dwr_valid), .dwr_data_i(delay_dwr_data),
        .dwr_pop_o(delay_dwr_pop), .drd_push_o(delay_drd_push), .drd_data_o(delay_drd_data), .drd_ready_i(delay_drd_ready),
        .ddr_req_o(delay_ddr_request_o), .ddr_write_o(delay_ddr_write_o), .ddr_address_o(delay_ddr_address_o),
        .ddr_data_o(delay_ddr_data_o), .ddr_mask_o(delay_ddr_mask_o), .ddr_ready_i(delay_ddr_ready_i),
        .ddr_response_i(delay_ddr_response_i), .ddr_read_data_i(delay_ddr_read_data_i), .debug_status_o(delay_ddr_debug_o)
    );
endmodule
