module workstation_usb2_hotplug_top #(
    parameter [31:0] SIGNATURE = 32'h55324850
) (
    input wire clk_50m, pc_uart_rx_i,
    output wire debug_uart_tx,
    input wire usb2_ulpi_clk, usb2_ulpi_dir, usb2_ulpi_nxt,
    inout wire [7:0] usb2_ulpi_data,
    output wire usb2_ulpi_stp
);
    wire reset_n, usb_clk, usb_locked, audio_clk, audio_reset_n, audio_locked;
    reset_release u_reset (.clk(clk_50m), .ext_reset_n(1'b1), .reset_n(reset_n));
    gw138k_cpu_pll_cell #(.OUTPUT_DIV0(25), .OUTPUT1_ENABLE("FALSE")) u_usb_pll (
        .clkin(clk_50m), .init_clk(clk_50m), .reset(!reset_n), .enable0(1'b1),
        .lock(usb_locked), .clkout0(usb_clk), .clkout1()
    );
    gw138k_audio_clock u_audio_clock (
        .clk_50m(clk_50m), .reset_n(reset_n), .audio_clk(audio_clk),
        .audio_reset_n(audio_reset_n), .pll_locked(audio_locked)
    );
    (* async_reg = "true", syn_preserve = 1 *) reg [3:0] usb_release = 0;
    wire usb_qualified = reset_n && usb_locked;
    always @(posedge usb_clk or negedge usb_qualified)
        if (!usb_qualified) usb_release <= 0;
        else usb_release <= {usb_release[2:0], 1'b1};
    wire usb_reset_n = usb_release[3];
    wire [7:0] ulpi_output;
    wire ulpi_enable;
    assign usb2_ulpi_data = ulpi_enable ? ulpi_output : 8'hzz;
    wire audio_valid, audio_lifecycle, audio_cancel;
    wire [17:0] audio_event;
    wire [223:0] telemetry;
    wire [3:0] cpu_fault;
    wire [31:0] cpu_fault_address, canceled_requests, sof_count;
    wire transaction_reset_n, phy_ready, failed, high_speed, traffic_enable;
    defparam u_native_usb.host.usb.PORT_OBSERVER = 1;
    reg [31:0] event_count_q, lifecycle_count_q, cancel_count_q;
    reg [17:0] last_event_q;
    always @(posedge audio_clk or negedge audio_reset_n) begin
        if (!audio_reset_n) begin
            event_count_q <= 0;
            lifecycle_count_q <= 0;
            cancel_count_q <= 0;
            last_event_q <= 0;
        end else if (audio_valid) begin
            event_count_q <= event_count_q + 1'b1;
            last_event_q <= audio_event;
            if (audio_lifecycle) lifecycle_count_q <= lifecycle_count_q + 1'b1;
            if (audio_cancel) cancel_count_q <= cancel_count_q + 1'b1;
        end
    end
    workstation_usb2_input #(.FEEDBACK_AUDIO_DOMAIN(1)) u_native_usb (
        .clk_cpu(usb_clk), .clk_ref(clk_50m), .clk_ulpi(usb2_ulpi_clk), .clk_audio(audio_clk),
        .reset_n(usb_reset_n), .audio_reset_n(audio_reset_n), .uart_rx_i(pc_uart_rx_i), .uart_tx_o(),
        .ulpi_data_i(usb2_ulpi_data), .ulpi_dir_i(usb2_ulpi_dir), .ulpi_nxt_i(usb2_ulpi_nxt),
        .ulpi_data_o(ulpi_output), .ulpi_data_oe_o(ulpi_enable), .ulpi_stp_o(usb2_ulpi_stp),
        .performance_words_i({252'd0, event_count_q, 164'd0}), .display_meta_data_i(64'd0), .display_meta_valid_i(1'b0),
        .service_state_data_i(34'd0), .service_state_valid_i(1'b0),
        .score_valid_i(1'b0), .analysis_done_i(1'b0), .score_ready_o(), .score_note_i(7'd0),
        .playlist_valid_i(1'b0), .playlist_ready_o(), .playlist_word_i(16'd0),
        .track_launch_o(), .track_index_o(), .audio_valid_o(audio_valid), .audio_ready_i(1'b1),
        .audio_event_o(audio_event), .audio_lifecycle_o(audio_lifecycle), .audio_cancel_o(audio_cancel),
        .telemetry_o(telemetry), .canceled_requests_o(canceled_requests), .cpu_fault_o(cpu_fault),
        .cpu_fault_address_o(cpu_fault_address), .transaction_reset_n_o(transaction_reset_n),
        .phy_ready_o(phy_ready), .failed_o(failed), .high_speed_o(high_speed),
        .traffic_enable_o(traffic_enable), .sof_count_o(sof_count)
    );
    wire [113:0] event_snapshot;
    gw138k_stream_cdc #(.WIDTH(114)) u_diagnostic_snapshot (
        .reset_n(usb_reset_n && audio_reset_n), .source_clk(audio_clk), .destination_clk(usb_clk),
        .source_valid(1'b1), .source_data({event_count_q, lifecycle_count_q, cancel_count_q, last_event_q}),
        .destination_valid(), .destination_data(event_snapshot), .drop_count()
    );
    wire [36:0] link_snapshot;
    (* async_reg = "true", syn_preserve = 1 *) reg [1:0] link_release_q;
    always @(posedge usb2_ulpi_clk or negedge usb_reset_n)
        if (!usb_reset_n) link_release_q <= 0;
        else link_release_q <= {link_release_q[0], 1'b1};
    (* async_reg = "true", syn_preserve = 1 *) reg [4:0] link_level_meta_q, link_level_sync_q;
    always @(posedge usb2_ulpi_clk or negedge link_release_q[1]) begin
        if (!link_release_q[1]) begin
            link_level_meta_q <= 0;
            link_level_sync_q <= 0;
        end else begin
            link_level_meta_q <= {transaction_reset_n, traffic_enable, high_speed, failed, phy_ready};
            link_level_sync_q <= link_level_meta_q;
        end
    end
    gw138k_stream_cdc #(.WIDTH(37)) u_diagnostic_link (
        .reset_n(usb_reset_n), .source_clk(usb2_ulpi_clk), .destination_clk(usb_clk),
        .source_valid(1'b1),
        .source_data({sof_count, link_level_sync_q}),
        .destination_valid(), .destination_data(link_snapshot), .drop_count()
    );
    (* async_reg = "true", syn_preserve = 1 *) reg [1:0] audio_lock_sync_q;
    (* async_reg = "true", syn_preserve = 1 *) reg [1:0] usb_lock_sync_q;
    always @(posedge usb_clk or negedge usb_reset_n)
        if (!usb_reset_n) begin
            audio_lock_sync_q <= 0;
            usb_lock_sync_q <= 0;
        end else begin
            audio_lock_sync_q <= {audio_lock_sync_q[0], audio_locked};
            usb_lock_sync_q <= {usb_lock_sync_q[0], usb_locked};
        end
    wire [31:0] flags = {20'd0, cpu_fault, telemetry[1], audio_lock_sync_q[1], usb_lock_sync_q[1],
                         link_snapshot[4:0]};
    workstation_usb2_diagnostic_uart u_diagnostic_uart (
        .clk(usb_clk), .reset_n(usb_reset_n), .uart_tx_o(debug_uart_tx),
        .report_i({SIGNATURE, flags, link_snapshot[36:5], telemetry, event_snapshot[113:18],
                   14'd0, event_snapshot[17:0], cpu_fault_address, canceled_requests})
    );
endmodule
