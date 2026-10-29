`timescale 1ns/1ps
module tb_workstation_usb2_input_push #(
    parameter integer HIGH_SPEED = 1,
    parameter integer COMPLETE_FINAL_FRAME = 0
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
    reg [3:0] audio_phase = 0;
    wire audio_ready = audio_phase[2:0] != 3;
    wire [7:0] device_txdata, device_rxdata;
    wire device_txvalid, device_txready, device_rxvalid, device_rxactive, device_term, device_chirp;
    wire [1:0] device_xcvr, device_line;
    wire device_hs, device_configured, midi_ready;
    wire [6:0] device_address;
    wire [31:0] display_headers, display_bytes, midi_out_packets, midi_in_acked;
    integer phase = 0, source_index = 0, source_target = 2, writes = 0, audio_received = 0;
    integer attaches = 0, detaches = 0, barriers = 0, frame_commits = 0;
    reg previous_stalled = 0;
    reg [17:0] previous_event;

    function automatic [31:0] midi_word(input integer index);
        case (index)
            0: midi_word = 32'h02249009;
            1: midi_word = 32'h00248008;
            2, 3: midi_word = 32'h04259009;
            4: midi_word = 32'h00258008;
            default: midi_word = 0;
        endcase
    endfunction
    function automatic [17:0] mapped_word(input integer index);
        case (index)
            0: mapped_word = {4'd1, 7'd36, 7'd30};
            1: mapped_word = {4'd0, 7'd36, 7'd0};
            2, 3: mapped_word = {4'd1, 7'd37, 7'd32};
            4: mapped_word = {4'd0, 7'd37, 7'd0};
            default: mapped_word = 0;
        endcase
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
        .device_txdata_i(device_txdata), .device_txvalid_i(device_txvalid), .device_chirp_i(device_chirp),
        .device_xcvr_i(device_xcvr), .device_term_i(device_term), .device_txready_o(device_txready),
        .device_rxdata_o(device_rxdata), .device_rxvalid_o(device_rxvalid), .device_rxactive_o(device_rxactive),
        .device_line_o(device_line), .function_o(), .normal_packets_o(normal_packets)
    );
    usb_push_device_model device (
        .clk(clk_ulpi), .reset(!reset_n || !attached), .enable(reset_n), .utmi_rxdata(device_rxdata),
        .utmi_rxvalid(device_rxvalid), .utmi_rxactive(device_rxactive), .utmi_linestate(device_line),
        .utmi_txready(device_txready), .utmi_txdata(device_txdata), .utmi_txvalid(device_txvalid),
        .utmi_xcvr(device_xcvr), .utmi_termsel(device_term), .chirp(device_chirp), .high_speed(device_hs),
        .midi_valid_i(attached && device_configured && source_index < source_target),
        .midi_data_i(midi_word(source_index)), .midi_ready_o(midi_ready), .configured(device_configured),
        .device_address(device_address), .display_headers(display_headers), .display_bytes(display_bytes),
        .midi_out_packets(midi_out_packets), .midi_in_acked(midi_in_acked)
    );
    always @(posedge clk_ulpi) begin
        if (host_oe && phy_oe) $fatal(1, "Push ULPI contention");
        if (attached && device_configured && source_index < source_target && midi_ready)
            source_index <= source_index + 1;
    end
    always @(posedge clk_cpu) begin
        if (reset_n && (cpu_fault || failed)) $fatal(1, "Push host fault=%x address=%x", cpu_fault, cpu_fault_address);
        if (host.owner_select && host.owner_ready && host.owner_write && host.owner_address == 8'h04) begin
            if (writes >= 5 || host.owner_write_data != midi_word(writes))
                $fatal(1, "Push raw owner event %0d got=%x", writes, host.owner_write_data);
            writes <= writes + 1;
        end
        if (host.owner_select && host.owner_ready && host.owner_write && host.owner_address == 8'h30) begin
            if (host.owner_write_data != 32'(frame_commits + 1)) $fatal(1, "Push frame commit sequence");
            frame_commits <= frame_commits + 1;
        end
    end
    always @(posedge clk_audio) begin
        audio_phase <= audio_phase + 1'b1;
        if (previous_stalled && !audio_cancel && (!audio_valid || audio_event != previous_event))
            $fatal(1, "Push audio event changed under backpressure");
        previous_stalled <= audio_valid && !audio_ready;
        previous_event <= audio_event;
        if (reset_n && audio_valid && audio_ready) begin
            if (audio_lifecycle) begin
                if (audio_event[17:14] != 15) $fatal(1, "Push lifecycle kind changed");
                case (audio_event[6:0])
                    0: detaches <= detaches + 1;
                    1: attaches <= attaches + 1;
                    3: barriers <= barriers + 1;
                    default: $fatal(1, "Push unexpected lifecycle");
                endcase
            end else begin
                if (audio_received >= 5 || audio_event != mapped_word(audio_received) ||
                    (phase != 0 && phase != 1 && phase != 3) || barriers != attaches)
                    $fatal(1, "Push mapped event %0d phase=%0d got=%x", audio_received, phase, audio_event);
                audio_received <= audio_received + 1;
            end
        end
    end
    initial begin #1; reset_n = 0; repeat (10) @(negedge clk_cpu); reset_n = 1; end
    initial begin
        wait(audio_received == 2 && display_headers != 0 && display_bytes >= 1024 && midi_out_packets != 0);
        if (writes != 2 || midi_in_acked != 2 || attaches != 1 || barriers != 1)
            $fatal(1, "Push initial connection coverage missing");
        $display("PUSH HS=%0d CPU enumeration, two pad events and partial display at %0t", HIGH_SPEED, $time);
        @(negedge clk_ulpi); phase = 1; source_target = 3;
        wait(audio_received == 3 && writes == 3 && midi_in_acked == 3);
        if (display_bytes == 0 || display_bytes >= 327680 || frame_commits != 0)
            $fatal(1, "Push did not poll MIDI during incomplete frame");
        @(negedge clk_ulpi); phase = 2; attached = 0;
        wait(!transaction_reset_n && !telemetry[1]);
        wait(detaches == 1);
        #12000000;
        if (audio_received != 3 || device_configured || device_address != 0)
            $fatal(1, "Push unplug did not discard device/session state");
        @(negedge clk_ulpi); phase = 3; attached = 1; source_target = 5;
        wait(audio_received == 5 && writes == 5 && barriers == 2 && display_headers != 0 && display_bytes >= 1024);
        if (COMPLETE_FINAL_FRAME != 0) begin
            wait(display_bytes == 327680 && frame_commits == 1);
            if (display_headers != 1) $fatal(1, "Push completed frame unexpectedly restarted");
        end
        if (cpu_fault || failed || !phy_ready || !traffic_enable || high_speed != (HIGH_SPEED != 0) ||
            device_hs != (HIGH_SPEED != 0) || !device_configured || device_address != 1 || !telemetry[1] ||
            attaches != 2 || detaches != 1 || midi_in_acked != 2 || midi_out_packets == 0 || normal_packets < 40)
            $fatal(1, "Push reconnect coverage missing");
        $display("PASS workstation_usb2_input_push: HS=%0d production CPU/ULPI/owner/FIFO/CDC, 5 mapped events, held-pad unplug, re-enumeration, display restart, complete_frames=%0d; modeled Push, not hardware/image acceptance", HIGH_SPEED, frame_commits);
        $finish;
    end
    initial begin
        #(COMPLETE_FINAL_FRAME != 0 ? 64'd12000000000 : 64'd2000000000);
        $fatal(1, "Push timeout pc=%x phase=%0d src=%0d writes=%0d audio=%0d headers=%0d bytes=%0d cfg=%b addr=%0d",
               host.host.instruction_address, phase, source_index, writes, audio_received, display_headers,
               display_bytes, device_configured, device_address);
    end
endmodule
