`timescale 1ns/1ps
module tb_workstation_usb2_mixed_hotplug #(
    parameter integer HIGH_SPEED = 1,
    parameter integer COMPLETE_FINAL_FRAME = 0,
    parameter integer AUDIO_CORE = 0
);
    reg clk_cpu = 0, clk_ref = 0, clk_ulpi = 0, clk_audio = 0, reset_n = 1, attached = 1;
    always #10.417 clk_cpu = !clk_cpu;
    always #10 clk_ref = !clk_ref;
    always #8.333 clk_ulpi = !clk_ulpi;
    always #6.510417 clk_audio = !clk_audio;
    reg clk_memory = 0, clk_dac_reference = 0;
    generate if (AUDIO_CORE != 0) begin : audio_clocks
        always #5 clk_memory = !clk_memory;
        always #40.690104 clk_dac_reference = !clk_dac_reference;
    end endgenerate
    reg push_selected = 0;
    integer connection_index = 0, panel_source = 0, panel_target = 3, push_source = 0, push_target = 2;
    integer owner_writes = 0, panel_writes = 0, push_writes = 0, owner_attaches = 0, frame_commits = 0;
    integer audio_received = 0, attaches = 0, detaches = 0, barriers = 0;
    integer panel_tiles = 0, total_tiles = 0, tile_delay = 0;
    reg tile_done = 0, boot_observed = 0;
    reg [31:0] first_pl_session = 0;
    reg [3:0] audio_phase = 0;
    reg previous_stalled = 0;
    reg [17:0] previous_event;
    wire audio_ready;
    wire [447:0] feedback;
    wire [127:0] held_notes;
    wire [31:0] initializations, applied_notes, sample_ticks, serial_nonzero, serial_sequence, serial_pcm;
    wire applied_note_valid;
    wire [17:0] applied_note;
    integer serial_baseline = 0, played_connections = 0;
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
    wire [7:0] device_rxdata, panel_txdata, push_txdata;
    wire device_rxvalid, device_rxactive, device_txready;
    wire panel_txvalid, push_txvalid, panel_term, push_term, push_chirp;
    wire [1:0] panel_xcvr, push_xcvr, device_line;
    wire panel_hs, push_hs, panel_configured, push_configured, panel_midi_ready, push_midi_ready;
    wire [6:0] panel_address, push_address;
    wire panel_midi_received, control_reset, control_txvalid, control_txready, control_rxvalid, control_rxready;
    wire [7:0] control_txdata, control_rxdata;
    wire tile_valid, remote_enable;
    wire [8:0] tile_x, tile_width;
    wire [7:0] tile_y, tile_height;
    wire [15:0] protocol_errors;
    wire [31:0] display_headers, display_bytes, midi_out_packets, midi_in_acked;
    wire selected_configured = push_selected ? push_configured : panel_configured;
    wire [6:0] selected_address = push_selected ? push_address : panel_address;
    wire selected_hs = push_selected ? push_hs : panel_hs;

    function automatic [31:0] panel_packet(input integer index);
        case (index)
            0: panel_packet = 32'h643c9009;
            1: panel_packet = 32'h003c8008;
            2, 3: panel_packet = 32'h5a3d9009;
            4: panel_packet = 32'h003d8008;
            default: panel_packet = 0;
        endcase
    endfunction
    function automatic [31:0] push_packet(input integer index);
        case (index)
            0: push_packet = 32'h02249009;
            1: push_packet = 32'h00248008;
            2, 3: push_packet = 32'h04259009;
            4: push_packet = 32'h00258008;
            default: push_packet = 0;
        endcase
    endfunction
    function automatic [17:0] expected_event(input integer index);
        case (index)
            0: expected_event = {4'd1, 7'd60, 7'd100};
            1: expected_event = {4'd0, 7'd60, 7'd0};
            2, 6: expected_event = {4'd1, 7'd61, 7'd90};
            3: expected_event = {4'd1, 7'd36, 7'd30};
            4: expected_event = {4'd0, 7'd36, 7'd0};
            5, 8: expected_event = {4'd1, 7'd37, 7'd32};
            7: expected_event = {4'd0, 7'd61, 7'd0};
            9: expected_event = {4'd0, 7'd37, 7'd0};
            default: expected_event = 0;
        endcase
    endfunction
    workstation_usb2_input #(.ATTACH_DEBOUNCE_US(100), .FEEDBACK_AUDIO_DOMAIN(AUDIO_CORE)) host (
        .clk_cpu(clk_cpu), .clk_ref(clk_ref), .clk_ulpi(clk_ulpi), .clk_audio(clk_audio),
        .reset_n(reset_n), .audio_reset_n(reset_n), .uart_rx_i(1'b1), .uart_tx_o(),
        .ulpi_data_i(physical_data), .ulpi_dir_i(phy_dir), .ulpi_nxt_i(phy_nxt),
        .ulpi_data_o(host_data), .ulpi_data_oe_o(host_oe), .ulpi_stp_o(host_stp),
        .performance_words_i(feedback), .display_meta_data_i(64'd0), .display_meta_valid_i(1'b0),
        .service_state_data_i(34'd0), .service_state_valid_i(1'b0), .score_valid_i(1'b0),
        .analysis_done_i(1'b0), .score_ready_o(), .score_note_i(7'd0), .playlist_valid_i(1'b0),
        .playlist_ready_o(), .playlist_word_i(16'd0), .track_launch_o(), .track_index_o(),
        .audio_valid_o(audio_valid), .audio_ready_i(audio_ready), .audio_event_o(audio_event),
        .audio_lifecycle_o(audio_lifecycle), .audio_cancel_o(audio_cancel), .telemetry_o(telemetry),
        .canceled_requests_o(canceled_requests), .cpu_fault_o(cpu_fault), .cpu_fault_address_o(cpu_fault_address),
        .transaction_reset_n_o(transaction_reset_n), .phy_ready_o(phy_ready), .failed_o(failed),
        .high_speed_o(high_speed), .traffic_enable_o(traffic_enable), .sof_count_o(sof_count)
    );
    generate if (AUDIO_CORE != 0) begin : real_audio
        workstation_usb2_audio_sink sink (
            .clk_cpu(clk_cpu), .clk_ref(clk_ref), .clk_audio(clk_audio), .clk_memory(clk_memory),
            .clk_dac_reference(clk_dac_reference), .reset_n(reset_n), .event_valid_i(audio_valid),
            .lifecycle_i(audio_lifecycle), .cancel_i(audio_cancel), .event_i(audio_event),
            .event_ready_o(audio_ready), .feedback_o(feedback), .held_o(held_notes),
            .initialization_count_o(initializations), .note_count_o(applied_notes),
            .applied_note_valid_o(applied_note_valid), .applied_note_o(applied_note),
            .sample_ticks_o(sample_ticks), .serial_nonzero_o(serial_nonzero),
            .serial_sequence_o(serial_sequence), .serial_pcm_o(serial_pcm)
        );
    end else begin : event_checker
        assign audio_ready = audio_phase[2:0] != 3;
        assign feedback = 0;
        assign held_notes = 0;
        assign initializations = 0;
        assign applied_notes = 0;
        assign applied_note_valid = 0;
        assign applied_note = 0;
        assign sample_ticks = 0;
        assign serial_nonzero = 0;
        assign serial_sequence = 0;
        assign serial_pcm = 0;
    end endgenerate
    usb3300_host_model #(.HIGH_SPEED(HIGH_SPEED)) phy (
        .clk_ulpi(clk_ulpi), .reset_n(reset_n), .runtime_i(transaction_reset_n), .attached_i(attached), .stall_i(1'b0),
        .link_data_i(physical_data), .link_oe_i(host_oe), .link_stp_i(host_stp),
        .phy_data_o(phy_data), .phy_oe_o(phy_oe), .phy_dir_o(phy_dir), .phy_nxt_o(phy_nxt),
        .device_txdata_i(push_selected ? push_txdata : panel_txdata),
        .device_txvalid_i(attached && (push_selected ? push_txvalid : panel_txvalid)),
        .device_chirp_i(push_selected ? push_chirp : panel_device.chirp),
        .device_xcvr_i(push_selected ? push_xcvr : panel_xcvr),
        .device_term_i(push_selected ? push_term : panel_term), .device_txready_o(device_txready),
        .device_rxdata_o(device_rxdata), .device_rxvalid_o(device_rxvalid), .device_rxactive_o(device_rxactive),
        .device_line_o(device_line), .function_o(), .normal_packets_o(normal_packets)
    );
    midi_usb_device panel_device (
        .clk(clk_ulpi), .reset(!reset_n || push_selected), .enable(reset_n && !push_selected),
        .utmi_rxdata(device_rxdata), .utmi_rxvalid(device_rxvalid && !push_selected),
        .utmi_rxactive(device_rxactive && !push_selected), .utmi_rxerror(1'b0),
        .utmi_linestate(!push_selected ? device_line : 2'b00), .utmi_txready(device_txready && !push_selected),
        .utmi_txdata(panel_txdata), .utmi_txvalid(panel_txvalid), .utmi_opmode(),
        .utmi_xcvr(panel_xcvr), .utmi_termsel(panel_term), .utmi_dppd(), .utmi_dmpd(),
        .midi_tx_valid(attached && !push_selected && panel_configured && panel_source < panel_target),
        .midi_tx_ready(panel_midi_ready), .midi_tx_data(panel_packet(panel_source)),
        .midi_rx_valid(panel_midi_received), .midi_rx_ready(1'b1), .midi_rx_data(),
        .control_tx_valid(control_txvalid), .control_tx_ready(control_txready), .control_tx_data(control_txdata),
        .control_rx_valid(control_rxvalid), .control_rx_ready(control_rxready), .control_rx_data(control_rxdata),
        .configured(panel_configured), .session_reset(), .midi_session_reset(), .control_session_reset(control_reset),
        .hs_active(panel_hs), .phy_state(), .device_address(panel_address)
    );
    panel_display_endpoint #(.CLK_HZ(60000000)) panel (
        .clk(clk_ulpi), .reset(!reset_n || push_selected), .link_reset(control_reset),
        .rx_valid(control_rxvalid), .rx_ready(control_rxready), .rx_data(control_rxdata),
        .tx_valid(control_txvalid), .tx_ready(control_txready), .tx_data(control_txdata), .settings_toggle(1'b0),
        .remote_enable(remote_enable), .manual_settings(), .redraw_required(), .protocol_errors(protocol_errors),
        .tile_valid(tile_valid), .tile_ready(tile_delay == 0), .tile_x(tile_x), .tile_y(tile_y),
        .tile_width(tile_width), .tile_height(tile_height), .tile_read_addr(8'd0), .tile_read_data(), .tile_done(tile_done)
    );
    usb_push_device_model push_device (
        .clk(clk_ulpi), .reset(!reset_n || !push_selected), .enable(reset_n && push_selected),
        .utmi_rxdata(device_rxdata), .utmi_rxvalid(device_rxvalid && push_selected),
        .utmi_rxactive(device_rxactive && push_selected), .utmi_linestate(push_selected ? device_line : 2'b00),
        .utmi_txready(device_txready && push_selected), .utmi_txdata(push_txdata), .utmi_txvalid(push_txvalid),
        .utmi_xcvr(push_xcvr), .utmi_termsel(push_term), .chirp(push_chirp), .high_speed(push_hs),
        .midi_valid_i(attached && push_selected && push_configured && push_source < push_target),
        .midi_data_i(push_packet(push_source)), .midi_ready_o(push_midi_ready), .configured(push_configured),
        .device_address(push_address), .display_headers(display_headers), .display_bytes(display_bytes),
        .midi_out_packets(midi_out_packets), .midi_in_acked(midi_in_acked)
    );
    always @(posedge clk_ulpi) begin
        if (host_oe && phy_oe) $fatal(1, "mixed ULPI contention");
        if (attached && !push_selected && panel_configured && panel_source < panel_target && panel_midi_ready)
            panel_source <= panel_source + 1;
        if (attached && push_selected && push_configured && push_source < push_target && push_midi_ready)
            push_source <= push_source + 1;
        if (push_selected || !attached) begin
            panel_tiles <= 0; tile_delay <= 0; tile_done <= 0;
        end else begin
            tile_done <= tile_delay == 1;
            if (tile_delay > 0) tile_delay <= tile_delay - 1;
            if (tile_valid && tile_delay == 0) begin
                if (panel_tiles < 2 && (tile_width != 62 || tile_height != 4 ||
                    tile_x != 9'(panel_tiles * 62) || tile_y != 0))
                    $fatal(1, "mixed new PL session resumed stale tile coordinates");
                panel_tiles <= panel_tiles + 1; total_tiles <= total_tiles + 1; tile_delay <= 20;
            end
        end
        if (panel_midi_received) $fatal(1, "mixed PL traffic leaked into panel MIDI OUT");
        if (attached && !push_selected && protocol_errors) $fatal(1, "mixed PL protocol error");
    end
    always @(posedge clk_cpu) begin
        if (reset_n && (cpu_fault || failed)) $fatal(1, "mixed CPU fault=%x address=%x", cpu_fault, cpu_fault_address);
        if (host.owner_select && host.owner_ready && host.owner_write) begin
            if (host.owner_address == 8'h30) begin
                if (host.owner_write_data != 32'(frame_commits + 1)) $fatal(1, "mixed Push frame commit sequence");
                frame_commits <= frame_commits + 1;
            end
            if (host.owner_address == 8'h00 && host.owner_write_data != 0) begin
                if (host.owner_write_data != (push_selected ? 32'd1 : 32'd7) || owner_attaches != connection_index)
                    $fatal(1, "mixed wrong device mode at connection %0d", connection_index);
                owner_attaches <= owner_attaches + 1;
            end
            if (host.owner_address == 8'h04 || host.owner_address == 8'h54) begin
                if (owner_writes >= 10 || !attached) $fatal(1, "mixed unexpected owner write");
                if (push_selected) begin
                    if (host.owner_address != 8'h04 || host.owner_write_data != push_packet(push_writes))
                        $fatal(1, "mixed stale Push MIDI route index=%0d", push_writes);
                    push_writes <= push_writes + 1;
                end else begin
                    if (host.owner_address != 8'h54 || host.owner_write_data != {14'd0, expected_event(owner_writes)})
                        $fatal(1, "mixed stale generic MIDI route index=%0d", panel_writes);
                    panel_writes <= panel_writes + 1;
                end
                owner_writes <= owner_writes + 1;
            end
        end
    end
    always @(posedge clk_audio) begin
        audio_phase <= audio_phase + 1'b1;
        if (AUDIO_CORE != 0 && reset_n && applied_note_valid &&
            (applied_notes >= 10 || applied_note != expected_event(applied_notes)))
            $fatal(1, "mixed real parameter application mismatch index=%0d event=%x", applied_notes, applied_note);
        if (previous_stalled && !audio_cancel && (!audio_valid || audio_event != previous_event))
            $fatal(1, "mixed audio changed under backpressure");
        previous_stalled <= audio_valid && !audio_ready; previous_event <= audio_event;
        if (reset_n && audio_valid && audio_ready) begin
            if (audio_lifecycle) begin
                if (audio_event[17:14] != 15) $fatal(1, "mixed lifecycle kind changed");
                case (audio_event[6:0])
                    0: detaches <= detaches + 1;
                    1: begin
                        if (!audio_event[7]) $fatal(1, "mixed attach lost common initialization");
                        attaches <= attaches + 1;
                    end
                    3: barriers <= barriers + 1;
                    default: $fatal(1, "mixed unexpected lifecycle");
                endcase
            end else begin
                if (!attached || audio_received >= 10 || barriers != attaches ||
                    audio_event != expected_event(audio_received))
                    $fatal(1, "mixed audio event %0d connection=%0d got=%x", audio_received, connection_index, audio_event);
                audio_received <= audio_received + 1;
            end
        end
    end
    always @(negedge host.cpu_reset_n)
        if (boot_observed) $fatal(1, "mixed hotplug reset the production CPU");
    initial begin wait(host.cpu_reset_n); boot_observed = 1; end
    task automatic next_connection(input integer expected_audio);
        integer ticks_before, serial_before;
        begin
            if (AUDIO_CORE != 0) begin
                wait(applied_notes == expected_audio && initializations == connection_index + 1 &&
                     serial_nonzero > serial_baseline);
                played_connections = played_connections + 1;
            end
            if (selected_hs != (HIGH_SPEED != 0) || !selected_configured || selected_address != 1 ||
                !phy_ready || !traffic_enable || owner_attaches != connection_index + 1 ||
                attaches != connection_index + 1 || barriers != attaches || audio_received != expected_audio)
                $fatal(1, "mixed incomplete connection %0d", connection_index);
            $display("MIXED HS=%0d connection=%0d device=%s audio=%0d tiles=%0d display=%0d at %0t",
                     HIGH_SPEED, connection_index, push_selected ? "Push" : "25K", audio_received,
                     panel_tiles, display_bytes, $time);
            $fflush();
            @(negedge clk_ulpi); attached = 0;
            wait(!transaction_reset_n && !telemetry[1] && detaches == connection_index + 1);
            ticks_before = sample_ticks; serial_before = serial_sequence;
            #12000000;
            if (audio_received != expected_audio || selected_configured || selected_address != 0)
                $fatal(1, "mixed old peer/session survived unplug");
            if (AUDIO_CORE != 0 && (held_notes != 0 || serial_pcm != 0 || applied_notes != expected_audio ||
                sample_ticks < ticks_before + 500 || serial_sequence < serial_before + 500))
                $fatal(1, "mixed unplug did not clear real notes/serial PCM while preserving sample schedule");
            serial_baseline = serial_nonzero;
            @(negedge clk_ulpi);
            connection_index = connection_index + 1;
            push_selected = !push_selected;
            if (connection_index == 2) panel_target = AUDIO_CORE != 0 ? 4 : 5;
            if (connection_index == 3) push_target = AUDIO_CORE != 0 ? 4 : 5;
            repeat (8) @(negedge clk_ulpi);
            attached = 1;
        end
    endtask
    initial begin #1; reset_n = 0; repeat (10) @(negedge clk_cpu); reset_n = 1; end
    initial begin
        wait(audio_received == 3 && panel_tiles >= 2 && remote_enable);
        first_pl_session = panel.session;
        if (first_pl_session == 0) $fatal(1, "mixed missing initial PL session");
        next_connection(3);
        wait(audio_received == 5 && display_headers != 0 && display_bytes >= 1024 && midi_out_packets != 0);
        if (display_bytes >= 327680 || frame_commits != 0) $fatal(1, "mixed unplug is not interrupting a partial frame");
        @(negedge clk_ulpi); push_target = 3;
        wait(audio_received == 6 && midi_in_acked == 3);
        next_connection(6);
        if (AUDIO_CORE != 0) begin
            wait(applied_notes == 7 && held_notes[61] && serial_nonzero > serial_baseline);
            @(negedge clk_ulpi); panel_target = 5;
        end
        wait(audio_received == 8 && panel_tiles >= 2 && remote_enable);
        if (panel.session == first_pl_session || panel.session == 0)
            $fatal(1, "mixed firmware reused old PL session after Push");
        next_connection(8);
        if (AUDIO_CORE != 0) begin
            wait(applied_notes == 9 && held_notes[37] && serial_nonzero > serial_baseline);
            @(negedge clk_ulpi); push_target = 5;
        end
        wait(audio_received == 10 && display_headers != 0 && display_bytes >= 1024 && midi_out_packets != 0);
        if (COMPLETE_FINAL_FRAME != 0) begin
            wait(display_bytes == 327680 && frame_commits == 1);
            if (display_headers != 1) $fatal(1, "mixed final Push frame was restarted or duplicated");
        end
        if (AUDIO_CORE != 0) begin
            wait(applied_notes == 10 && initializations == 4 && held_notes == 0 && serial_pcm == 0);
            if (played_connections != 3 || serial_nonzero <= serial_baseline)
                $fatal(1, "mixed real audio did not play in every connection");
            $display("MIXED real_audio notes=%0d defaults=%0d audible_connections=4 sample_ticks=%0d serial_frames=%0d nonzero_frames=%0d",
                     applied_notes, initializations, sample_ticks, serial_sequence, serial_nonzero);
        end
        if (owner_writes != 10 || panel_writes != 5 || push_writes != 5 || panel_source != 5 || push_source != 5 ||
            attaches != 4 || barriers != 4 || detaches != 3 || owner_attaches != 4 || midi_in_acked != 2 ||
            !selected_configured || selected_address != 1 || selected_hs != (HIGH_SPEED != 0) ||
            high_speed != (HIGH_SPEED != 0) || !phy_ready || !traffic_enable || !telemetry[1] || total_tiles < 4)
            $fatal(1, "mixed final coverage missing");
        $display("PASS workstation_usb2_mixed_hotplug: HS=%0d one production CPU/ULPI/owner, 25K-Push-25K-Push, 10 events, 4 attaches/barriers, 3 detaches, fresh PL, complete_frames=%0d real_audio=%0d; modeled peers not hardware", HIGH_SPEED, frame_commits, AUDIO_CORE);
        $finish;
    end
    initial begin
        #(COMPLETE_FINAL_FRAME != 0 || AUDIO_CORE != 0 ? 64'd12000000000 : 64'd4000000000);
        $fatal(1, "mixed timeout pc=%x connection=%0d push=%b audio=%0d writes=%0d src=%0d/%0d cfg=%b address=%0d tiles=%0d display=%0d",
               host.host.instruction_address, connection_index, push_selected, audio_received, owner_writes,
               panel_source, push_source, selected_configured, selected_address, panel_tiles, display_bytes);
    end
endmodule
