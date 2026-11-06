// Alternate input composition, selected only by the explicit paired-W policy.
// Port/parameter compatibility retains the native top and all fallback sources.
module workstation_usb2_input #(
    parameter ROM_FILE = "usb2_cpu.hex",
    parameter integer CPU_FREQUENCY_HZ = 48000000,
    parameter integer ATTACH_DEBOUNCE_US = 100000,
    parameter integer BUS_TIMEOUT_CYCLES = 480000,
    parameter integer FEEDBACK_AUDIO_DOMAIN = 0,
    parameter integer STOP_CLOCK_QUEUE_FENCE = 0,
    parameter bit CNN_FOLLOW_ENABLE = 1'b1,
    parameter bit TF_MENU_ENABLE = CNN_FOLLOW_ENABLE,
    parameter bit MEDIA_CONTROLS_ENABLE = 1'b1,
    parameter bit WORKER_DEMO = 1'b0,
    parameter integer AUDIO_OWNER_RESET_SYNC = 0
)(
    input wire clk_cpu, clk_ref, clk_ulpi, clk_audio, reset_n, audio_reset_n,
    input wire uart_rx_i,
    output wire uart_tx_o,
    input wire [7:0] ulpi_data_i,
    input wire ulpi_dir_i, ulpi_nxt_i,
    output wire [7:0] ulpi_data_o,
    output wire ulpi_data_oe_o, ulpi_stp_o,
    input wire [447:0] performance_words_i,
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
    output wire audio_valid_o, audio_lifecycle_o, audio_cancel_o,
    input wire audio_ready_i,
    output wire [17:0] audio_event_o,
    output wire [223:0] telemetry_o,
    output wire [31:0] canceled_requests_o,
    output wire [3:0] cpu_fault_o,
    output wire [31:0] cpu_fault_address_o,
    output wire transaction_reset_n_o, phy_ready_o, failed_o, high_speed_o, traffic_enable_o,
    output wire [31:0] sof_count_o,
    output wire [2:0] device_state_o
);
    // Explicit paired-worker termination. No host, CPU, event FIFO or owner.
    // Score/playlist ready remains low because no consumer exists. Retiring
    // USB must never manufacture attach, cancellation, events or readiness.
    assign uart_tx_o=1'b1;
    assign ulpi_data_o=8'd0,ulpi_data_oe_o=1'b0,ulpi_stp_o=1'b0;
    assign score_ready_o=1'b0,playlist_ready_o=1'b0;
    assign track_launch_o=1'b0,track_index_o=4'd0;
    assign audio_valid_o=1'b0,audio_lifecycle_o=1'b0,audio_cancel_o=1'b0,audio_event_o=18'd0;
    assign telemetry_o=224'd0,canceled_requests_o=32'd0,cpu_fault_o=4'd0,cpu_fault_address_o=32'd0;
    assign transaction_reset_n_o=1'b0,phy_ready_o=1'b0,failed_o=1'b0,high_speed_o=1'b0;
    assign traffic_enable_o=1'b0,sof_count_o=32'd0,device_state_o=3'd0;
endmodule
