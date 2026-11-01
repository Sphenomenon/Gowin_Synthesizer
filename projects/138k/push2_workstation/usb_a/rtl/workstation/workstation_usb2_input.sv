module workstation_usb2_input #(
    parameter ROM_FILE = "usb2_cpu.hex",
    parameter integer CPU_FREQUENCY_HZ = 48000000,
    parameter integer ATTACH_DEBOUNCE_US = 100000,
    parameter integer BUS_TIMEOUT_CYCLES = 480000,
    parameter integer FEEDBACK_AUDIO_DOMAIN = 0,
    parameter integer STOP_CLOCK_QUEUE_FENCE = 0,
    parameter bit CNN_FOLLOW_ENABLE = 1'b1,
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
    output wire [31:0] sof_count_o
);
    (* async_reg = "true", syn_preserve=1 *) reg [1:0] cpu_release_q, session_release_q, feedback_release_q;
    wire cpu_reset_n = cpu_release_q[1];
    wire session_reset_n = cpu_reset_n && transaction_reset_n_o;
    wire service_valid, service_write, service_ready, service_error;
    wire [7:0] service_address;
    wire [31:0] service_write_data, service_read_data;
    wire [3:0] service_mask;
    wire owner_select, owner_write, owner_ready;
    wire [7:0] owner_address;
    wire [31:0] owner_write_data, owner_read_data;

    always @(posedge clk_cpu or negedge reset_n)
        if (!reset_n) cpu_release_q <= 0;
        else cpu_release_q <= {cpu_release_q[0], 1'b1};
    always @(posedge clk_ref or negedge reset_n)
        if (!reset_n) feedback_release_q <= 0;
        else feedback_release_q <= {feedback_release_q[0], 1'b1};
    always @(posedge clk_cpu or negedge session_reset_n)
        if (!session_reset_n) session_release_q <= 0;
        else session_release_q <= {session_release_q[0], 1'b1};

    workstation_usb2_soc #(.ROM_FILE(ROM_FILE), .CPU_FREQUENCY_HZ(CPU_FREQUENCY_HZ),
                          .ATTACH_DEBOUNCE_US(ATTACH_DEBOUNCE_US), .BUS_TIMEOUT_CYCLES(BUS_TIMEOUT_CYCLES)) host (
        .clk_cpu(clk_cpu), .clk_ref(clk_ref), .clk_ulpi(clk_ulpi), .reset_n(reset_n),
        .uart_rx_i(uart_rx_i), .uart_tx_o(uart_tx_o), .ulpi_data_i(ulpi_data_i),
        .ulpi_dir_i(ulpi_dir_i), .ulpi_nxt_i(ulpi_nxt_i), .ulpi_data_o(ulpi_data_o),
        .ulpi_data_oe_o(ulpi_data_oe_o), .ulpi_stp_o(ulpi_stp_o),
        .service_valid_o(service_valid), .service_write_o(service_write), .service_address_o(service_address),
        .service_write_data_o(service_write_data), .service_mask_o(service_mask),
        .service_ready_i(service_ready), .service_error_i(service_error), .service_read_data_i(service_read_data),
        .cpu_fault_o(cpu_fault_o), .cpu_fault_address_o(cpu_fault_address_o),
        .transaction_reset_n_o(transaction_reset_n_o), .phy_ready_o(phy_ready_o), .failed_o(failed_o),
        .high_speed_o(high_speed_o), .traffic_enable_o(traffic_enable_o), .sof_count_o(sof_count_o)
    );
    workstation_usb2_service_adapter #(.WORKER_DEMO(WORKER_DEMO)) services (
        .clk_cpu(clk_cpu), .reset_n(cpu_reset_n), .session_valid_i(session_release_q[1]),
        .owner_connected_i(telemetry_o[1]), .service_valid_i(service_valid), .service_write_i(service_write),
        .service_address_i(service_address), .service_write_data_i(service_write_data), .service_mask_i(service_mask),
        .service_ready_o(service_ready), .service_error_o(service_error), .service_read_data_o(service_read_data),
        .owner_select_o(owner_select), .owner_write_o(owner_write), .owner_address_o(owner_address),
        .owner_write_data_o(owner_write_data), .owner_ready_i(owner_ready), .owner_read_data_i(owner_read_data),
        .canceled_requests_o(canceled_requests_o)
    );
    wire owner_audio_reset_n;
    generate if (AUDIO_OWNER_RESET_SYNC != 0) begin: audio_owner_reset
        // The runtime reset request belongs to the platform/startup domain.
        // Assert even with a stopped audio clock; release only after three
        // real audio edges. Only the final stage may reset functional state.
        wire qualified_n = reset_n && audio_reset_n;
        (* ASYNC_REG="TRUE", syn_preserve=1 *) reg [2:0] release_q;
        always @(posedge clk_audio or negedge qualified_n)
            if (!qualified_n) release_q <= 0;
            else release_q <= {release_q[1:0], 1'b1};
        assign owner_audio_reset_n = release_q[2];
    end else begin: legacy_audio_owner_reset
        assign owner_audio_reset_n = audio_reset_n;
    end endgenerate
    wire feedback_clk = FEEDBACK_AUDIO_DOMAIN != 0 ? clk_audio : clk_ref;
    wire feedback_reset_n = FEEDBACK_AUDIO_DOMAIN != 0 ? owner_audio_reset_n : feedback_release_q[1];
    push2_usb_a_control #(.STOP_CLOCK_QUEUE_FENCE(STOP_CLOCK_QUEUE_FENCE),
                         .CNN_FOLLOW_ENABLE(CNN_FOLLOW_ENABLE),.MEDIA_CONTROLS_ENABLE(MEDIA_CONTROLS_ENABLE),
                         .WORKER_DEMO(WORKER_DEMO)) input_owner (
        .clk(clk_cpu), .reset_n(cpu_reset_n), .audio_clk(clk_audio), .audio_reset_n(owner_audio_reset_n),
        .feedback_clk(feedback_clk), .feedback_reset_n(feedback_reset_n), .performance_words(performance_words_i),
        .display_meta_data(display_meta_data_i), .display_meta_valid(display_meta_valid_i),
        .service_state_data(service_state_data_i), .service_state_valid(service_state_valid_i),
        .score_valid(score_valid_i), .analysis_done(analysis_done_i), .score_ready(score_ready_o), .score_note(score_note_i),
        .playlist_valid(playlist_valid_i), .playlist_ready(playlist_ready_o), .playlist_word(playlist_word_i),
        .track_launch(track_launch_o), .track_index(track_index_o), .select(owner_select), .write(owner_write),
        .address(owner_address), .wdata(owner_write_data), .ready(owner_ready), .rdata(owner_read_data),
        .audio_valid(audio_valid_o), .audio_ready(audio_ready_i), .audio_event(audio_event_o),
        .audio_lifecycle(audio_lifecycle_o), .audio_cancel(audio_cancel_o), .telemetry(telemetry_o)
    );
endmodule
