`timescale 1ns/1ps
module tb_workstation_usb2_input_25k #(
    parameter integer HIGH_SPEED = 1
);
    reg clk_cpu = 0, clk_ref = 0, clk_ulpi = 0, clk_audio = 0, reset_n = 1, attached = 1;
    always #10.417 clk_cpu = !clk_cpu;
    always #10 clk_ref = !clk_ref;
    always #8.333 clk_ulpi = !clk_ulpi;
    always #6.510417 clk_audio = !clk_audio;
    wire [7:0] host_data, phy_data;
    wire host_oe, host_stp, phy_oe, phy_dir, phy_nxt;
    tri [7:0] physical_data;
    assign physical_data = host_oe ? host_data : 8'hzz;
    assign physical_data = phy_oe ? phy_data : 8'hzz;
    wire [3:0] cpu_fault;
    wire [31:0] cpu_fault_address, sof_count, normal_packets, canceled_requests;
    wire transaction_reset_n, phy_ready, failed, high_speed, traffic_enable;
    wire audio_valid, audio_lifecycle, audio_cancel;
    wire [17:0] audio_event;
    wire [223:0] telemetry;
    integer phase = 0, source_index = 0, source_target = 128, writes = 0, audio_received = 0;
    integer tiles = 0, tile_delay = 0, attaches = 0, barriers = 0, detaches = 0, stalled_cycles = 0;
    reg initial_stall_complete = 0, tile_done = 0;
    reg [3:0] audio_phase = 0;
    wire audio_blocked = phase == 0 ? barriers != 0 && !initial_stall_complete : phase == 1 || phase == 2;
    wire audio_ready = !audio_blocked && audio_phase[2:0] != 3;
    reg previous_stalled = 0;
    reg [17:0] previous_event;
    wire [7:0] device_txdata, device_rxdata, control_txdata, control_rxdata;
    wire device_txvalid, device_txready, device_rxvalid, device_rxactive, device_term;
    wire [1:0] device_xcvr, device_line;
    wire device_hs, device_configured, control_reset, control_txvalid, control_txready, control_rxvalid, control_rxready;
    wire [6:0] device_address;
    wire midi_ready, unexpected_midi_valid;
    wire [31:0] unused_midi_data;
    wire tile_valid, remote_enable;
    wire [8:0] tile_x, tile_width;
    wire [7:0] tile_y, tile_height;
    wire [15:0] protocol_errors;

    function automatic [31:0] midi_word(input integer index);
        reg [7:0] note;
        begin
            if (index < 128) begin
                note = 8'd36 + 8'(index >> 1);
                midi_word = index[0] ? {8'd0, note, 8'h80, 8'h08} : {8'd100, note, 8'h90, 8'h09};
            end else if (index < 148) begin
                note = 8'd70 + 8'(index - 128);
                midi_word = {8'd90, note, 8'h90, 8'h09};
            end else begin
                note = 8'd60 + 8'((index - 148) >> 1);
                midi_word = index[0] ? {8'd0, note, 8'h80, 8'h08} : {8'd110, note, 8'h90, 8'h09};
            end
        end
    endfunction
    function automatic [17:0] mapped_word(input integer index);
        reg [31:0] packet;
        begin
            packet = midi_word(index);
            mapped_word = {packet[15:12] == 9 ? 4'd1 : 4'd0, packet[22:16], packet[30:24]};
        end
    endfunction

    workstation_usb2_input #(.ATTACH_DEBOUNCE_US(100)) host (
        .clk_cpu(clk_cpu), .clk_ref(clk_ref), .clk_ulpi(clk_ulpi), .clk_audio(clk_audio),
        .reset_n(reset_n), .audio_reset_n(reset_n), .uart_rx_i(1'b1), .uart_tx_o(),
        .ulpi_data_i(physical_data), .ulpi_dir_i(phy_dir), .ulpi_nxt_i(phy_nxt),
        .ulpi_data_o(host_data), .ulpi_data_oe_o(host_oe), .ulpi_stp_o(host_stp),
        .performance_words_i(448'd0), .display_meta_data_i(64'd0), .display_meta_valid_i(1'b0),
        .service_state_data_i(34'd0), .service_state_valid_i(1'b0), .score_valid_i(1'b0),
        .analysis_done_i(1'b0), .score_ready_o(), .score_note_i(7'd0), .playlist_valid_i(1'b0),
        .playlist_ready_o(), .playlist_word_i(16'd0), .track_launch_o(), .track_index_o(),
        .audio_valid_o(audio_valid), .audio_ready_i(audio_ready), .audio_event_o(audio_event),
        .audio_lifecycle_o(audio_lifecycle), .audio_cancel_o(audio_cancel), .telemetry_o(telemetry),
        .canceled_requests_o(canceled_requests), .cpu_fault_o(cpu_fault), .cpu_fault_address_o(cpu_fault_address),
        .transaction_reset_n_o(transaction_reset_n), .phy_ready_o(phy_ready), .failed_o(failed),
        .high_speed_o(high_speed), .traffic_enable_o(traffic_enable), .sof_count_o(sof_count)
    );
    usb3300_host_model #(.HIGH_SPEED(HIGH_SPEED)) phy (
        .clk_ulpi(clk_ulpi), .reset_n(reset_n), .runtime_i(transaction_reset_n), .attached_i(attached), .stall_i(1'b0),
        .link_data_i(physical_data), .link_oe_i(host_oe), .link_stp_i(host_stp),
        .phy_data_o(phy_data), .phy_oe_o(phy_oe), .phy_dir_o(phy_dir), .phy_nxt_o(phy_nxt),
        .device_txdata_i(device_txdata), .device_txvalid_i(device_txvalid), .device_chirp_i(device.chirp),
        .device_xcvr_i(device_xcvr), .device_term_i(device_term), .device_txready_o(device_txready),
        .device_rxdata_o(device_rxdata), .device_rxvalid_o(device_rxvalid), .device_rxactive_o(device_rxactive),
        .device_line_o(device_line), .function_o(), .normal_packets_o(normal_packets)
    );
    midi_usb_device device (
        .clk(clk_ulpi), .reset(!reset_n), .enable(reset_n), .utmi_rxdata(device_rxdata),
        .utmi_rxvalid(device_rxvalid), .utmi_rxactive(device_rxactive), .utmi_rxerror(1'b0),
        .utmi_linestate(device_line), .utmi_txready(device_txready), .utmi_txdata(device_txdata),
        .utmi_txvalid(device_txvalid), .utmi_opmode(), .utmi_xcvr(device_xcvr), .utmi_termsel(device_term),
        .utmi_dppd(), .utmi_dmpd(), .midi_tx_valid(attached && device_configured && source_index < source_target),
        .midi_tx_ready(midi_ready), .midi_tx_data(midi_word(source_index)), .midi_rx_valid(unexpected_midi_valid),
        .midi_rx_ready(1'b1), .midi_rx_data(unused_midi_data), .control_tx_valid(control_txvalid),
        .control_tx_ready(control_txready), .control_tx_data(control_txdata), .control_rx_valid(control_rxvalid),
        .control_rx_ready(control_rxready), .control_rx_data(control_rxdata), .configured(device_configured),
        .session_reset(), .midi_session_reset(), .control_session_reset(control_reset), .hs_active(device_hs),
        .phy_state(), .device_address(device_address)
    );
    panel_display_endpoint #(.CLK_HZ(60000000)) panel (
        .clk(clk_ulpi), .reset(!reset_n), .link_reset(control_reset), .rx_valid(control_rxvalid),
        .rx_ready(control_rxready), .rx_data(control_rxdata), .tx_valid(control_txvalid),
        .tx_ready(control_txready), .tx_data(control_txdata), .settings_toggle(1'b0),
        .remote_enable(remote_enable), .manual_settings(), .redraw_required(), .protocol_errors(protocol_errors),
        .tile_valid(tile_valid), .tile_ready(tile_delay == 0), .tile_x(tile_x), .tile_y(tile_y),
        .tile_width(tile_width), .tile_height(tile_height), .tile_read_addr(8'd0), .tile_read_data(), .tile_done(tile_done)
    );
    always @(posedge clk_ulpi) begin
        if (host_oe && phy_oe) $fatal(1, "input ULPI contention");
        if (attached && device_configured && source_index < source_target && midi_ready) source_index <= source_index + 1;
        tile_done <= tile_delay == 1;
        if (tile_delay > 0) tile_delay <= tile_delay - 1;
        if (tile_valid && tile_delay == 0) begin
            if (tile_width != 62 || tile_height != 4) $fatal(1, "input PL tile dimensions");
            if (tiles < 2 && (tile_x != 9'(tiles * 62) || tile_y != 0)) $fatal(1, "input PL tile coordinates");
            tiles <= tiles + 1; tile_delay <= 20;
        end
        if (unexpected_midi_valid) $fatal(1, "input PL leaked into MIDI OUT");
    end
    always @(posedge clk_cpu) begin
        if (host.owner_select && host.owner_write && host.owner_address == 8'h54 && !host.owner_ready && phase == 0) begin
            stalled_cycles <= stalled_cycles + 1;
            if (stalled_cycles == 200) initial_stall_complete <= 1;
        end
        if (host.owner_select && host.owner_ready && host.owner_write && host.owner_address == 8'h54) begin
            if (writes >= 156 || host.owner_write_data != {14'd0, mapped_word(writes)})
                $fatal(1, "input owner event %0d got=%x", writes, host.owner_write_data);
            writes <= writes + 1;
        end
    end
    always @(posedge clk_audio) begin
        audio_phase <= audio_phase + 1'b1;
        if (previous_stalled && !audio_cancel && (!audio_valid || audio_event != previous_event))
            $fatal(1, "audio event changed under backpressure without cancellation");
        previous_stalled <= audio_valid && !audio_ready;
        previous_event <= audio_event;
        if (reset_n && audio_valid && audio_ready) begin
            if (audio_lifecycle) begin
                if (audio_event[17:14] != 15) $fatal(1, "input lifecycle kind changed");
                case (audio_event[6:0])
                    0: detaches <= detaches + 1;
                    1: begin
                        if (!audio_event[7]) $fatal(1, "GW25K attach lost defaults");
                        attaches <= attaches + 1;
                    end
                    3: barriers <= barriers + 1;
                    default: $fatal(1, "unexpected input lifecycle");
                endcase
            end else begin
                if (attaches == 0 || barriers != attaches || (phase != 0 && phase != 4) ||
                    audio_received >= 136 || audio_event != mapped_word(audio_received < 128 ? audio_received : audio_received + 20))
                    $fatal(1, "audio-domain event %0d phase=%0d got=%x", audio_received, phase, audio_event);
                audio_received <= audio_received + 1;
            end
        end
    end
    initial begin #1; reset_n = 0; repeat (10) @(negedge clk_cpu); reset_n = 1; end
    initial begin
        wait(audio_received == 128 && tiles >= 2);
        if (!initial_stall_complete || stalled_cycles < 200 || writes != 128 || attaches != 1 || barriers != 1)
            $fatal(1, "input FIFO/attach coverage missing");
        $display("INPUT HS=%0d initial 128 audio events, real FIFO backpressure and PL at %0t", HIGH_SPEED, $time);
        @(negedge clk_cpu); phase = 1; source_target = 148;
        wait(writes == 148);
        @(negedge clk_cpu); phase = 2; attached = 0;
        wait(!transaction_reset_n);
        repeat (8) @(negedge clk_cpu);
        if (telemetry[1]) $fatal(1, "physical session loss did not detach owner independently of firmware");
        wait(audio_cancel);
        if (audio_event != {4'd15, 7'd0, 7'd0}) $fatal(1, "hardware detach did not preempt queued notes");
        @(negedge clk_audio); phase = 3;
        wait(detaches == 1);
        #12000000;
        if (audio_received != 128 || device_configured || device_address != 0)
            $fatal(1, "detached FIFO/device state not discarded");
        @(negedge clk_cpu); phase = 4; attached = 1; source_target = 156;
        wait(audio_received == 136 && writes == 156 && barriers == 2 && tiles >= 4);
        if (cpu_fault || failed || !phy_ready || !traffic_enable || high_speed != (HIGH_SPEED != 0) ||
            device_hs != (HIGH_SPEED != 0) || !device_configured || device_address != 1 || !remote_enable ||
            protocol_errors || !telemetry[1] || attaches != 2 || detaches != 1 || normal_packets < 100 || sof_count < 20)
            $fatal(1, "input acceptance fault=%x address=%x canceled=%0d", cpu_fault, cpu_fault_address, canceled_requests);
        $display("PASS workstation_usb2_input_25k: HS=%0d production CPU/real owner/FIFO/CDC, 136 audio events, 20 stale discarded, backpressure, hardware detach/reattach, PL", HIGH_SPEED);
        $finish;
    end
    initial begin #2000000000; $fatal(1, "input timeout pc=%x phase=%0d source=%0d writes=%0d audio=%0d tiles=%0d attaches=%0d barriers=%0d fault=%x", host.host.instruction_address, phase, source_index, writes, audio_received, tiles, attaches, barriers, cpu_fault); end
endmodule
