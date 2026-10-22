`timescale 1ns/1ps
`define AUDIO_CORE host.audio.u_audio.u_workstation
module tb_workstation_usb2_audio_25k #(parameter integer HIGH_SPEED = 1);
    reg clk_cpu = 0, clk_ref = 0, clk_ulpi = 0, clk_audio = 0, clk_memory = 0, reset_n = 1, attached = 1;
    always #10.417 clk_cpu = !clk_cpu;
    always #10 clk_ref = !clk_ref;
    always #8.333 clk_ulpi = !clk_ulpi;
    always #6.510417 clk_audio = !clk_audio;
    always #5 clk_memory = !clk_memory;
    wire [7:0] host_data, phy_data;
    wire host_oe, host_stp, phy_oe, phy_dir, phy_nxt;
    tri [7:0] physical_data;
    assign physical_data = host_oe ? host_data : 8'hzz;
    assign physical_data = phy_oe ? phy_data : 8'hzz;
    wire [3:0] cpu_fault;
    wire [31:0] cpu_fault_address, sof_count, normal_packets, canceled_requests;
    wire transaction_reset_n, phy_ready, failed, high_speed, traffic_enable;
    wire [223:0] telemetry;
    wire [447:0] performance_words;
    wire performance_valid, sample_ce, sample_valid, display_valid;
    wire signed [31:0] audio_left, audio_right;
    wire [31:0] active_mask, deadline, overflow, drops, underruns, midi_cdc_drop, observation_drop, feedback_drop, dac_health;
    wire [31:0] display_pcm;
    reg psel = 0, penable = 0, pwrite = 0;
    reg [11:0] paddr = 0;
    reg [31:0] pwdata = 0;
    wire pready, pslverr;
    wire [31:0] prdata;
    wire ddr_request, ddr_write;
    wire [28:0] ddr_address;
    wire [255:0] ddr_data;
    wire [31:0] ddr_mask;
    reg [31:0] memory_cycle = 0;
    wire ddr_ready = memory_cycle[3:0] > 2;
    reg ddr_response = 0;
    reg [255:0] ddr_read_data = 0, pending_read_data;
    reg [255:0] memory [0:4095];
    reg [4095:0] written = 0;
    integer memory_delay = 0, memory_reads = 0, memory_writes = 0;
    integer phase = 0, source_index = 0, source_target = 1, note_starts = 0;
    integer frames = 0, nonzero = 0, serial_frames = 0, feedback_frames = 0, audio_cycles = 0, last_tick = -1;
    integer tiles = 0, tile_delay = 0;
    reg tile_done = 0;
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
        case (index)
            0: midi_word = {8'd100, 8'd60, 8'h90, 8'h09};
            1: midi_word = {8'd19, 8'd7, 8'hb0, 8'h0b};
            2: midi_word = {8'd23, 8'd11, 8'hb0, 8'h0b};
            3: midi_word = {8'd65, 8'd1, 8'hb0, 8'h0b};
            4: midi_word = {8'd17, 8'd5, 8'hb0, 8'h0b};
            5: midi_word = {8'd96, 8'd0, 8'he0, 8'h0e};
            6: midi_word = {8'd127, 8'd64, 8'hb0, 8'h0b};
            7: midi_word = {8'd0, 8'd0, 8'hc0, 8'h0c};
            8: midi_word = {8'd0, 8'd120, 8'hb0, 8'h0b};
            9: midi_word = {8'd0, 8'd80, 8'hb0, 8'h0b};
            10: midi_word = {8'd90, 8'd67, 8'h90, 8'h09};
            11: midi_word = {8'd85, 8'd69, 8'h90, 8'h09};
            12: midi_word = {8'd110, 8'd62, 8'h90, 8'h09};
            13: midi_word = {8'd0, 8'd62, 8'h80, 8'h08};
            14: midi_word = {8'd0, 8'd120, 8'hb0, 8'h0b};
            default: midi_word = 0;
        endcase
    endfunction

    workstation_usb2_audio #(.ATTACH_DEBOUNCE_US(100)) host (
        .clk_cpu(clk_cpu), .clk_ref(clk_ref), .clk_ulpi(clk_ulpi), .clk_audio(clk_audio), .clk_memory(clk_memory),
        .reset_n(reset_n), .audio_reset_n(reset_n), .memory_reset_n(reset_n), .control_reset_n(reset_n),
        .uart_rx_i(1'b1), .midi_rx_i(1'b1), .pc_uart_rx_i(1'b1), .uart_tx_o(),
        .ulpi_data_i(physical_data), .ulpi_dir_i(phy_dir), .ulpi_nxt_i(phy_nxt),
        .ulpi_data_o(host_data), .ulpi_data_oe_o(host_oe), .ulpi_stp_o(host_stp),
        .display_meta_data_i(64'd0), .display_meta_valid_i(1'b0), .service_state_data_i(34'd0), .service_state_valid_i(1'b0),
        .score_valid_i(1'b0), .analysis_done_i(1'b0), .score_ready_o(), .score_note_i(7'd0), .playlist_valid_i(1'b0),
        .playlist_ready_o(), .playlist_word_i(16'd0), .track_launch_o(), .track_index_o(),
        .psel_i(psel), .penable_i(penable), .pwrite_i(pwrite), .paddr_i(paddr), .pwdata_i(pwdata), .pstrb_i(4'hf),
        .pready_o(pready), .pslverr_o(pslverr), .prdata_o(prdata), .telemetry_o(telemetry),
        .performance_words_o(performance_words), .performance_valid_o(performance_valid), .feedback_drop_o(feedback_drop),
        .canceled_requests_o(canceled_requests), .cpu_fault_o(cpu_fault), .cpu_fault_address_o(cpu_fault_address),
        .transaction_reset_n_o(transaction_reset_n), .phy_ready_o(phy_ready), .failed_o(failed), .high_speed_o(high_speed),
        .traffic_enable_o(traffic_enable), .sof_count_o(sof_count), .reference_bck_o(), .reference_ws_o(), .reference_din_o(),
        .reference_pa_en_o(), .sample_ce_o(sample_ce), .sample_valid_o(sample_valid), .audio_left_o(audio_left),
        .audio_right_o(audio_right), .active_mask_o(active_mask), .deadline_miss_o(deadline), .midi_overflow_o(overflow),
        .note_drop_o(drops), .underrun_count_o(underruns), .midi_cdc_drop_o(midi_cdc_drop), .observation_drop_o(observation_drop),
        .uart_error_o(), .record_drop_o(), .led_mask_o(), .score_frame_o(), .score_running_o(), .score_done_o(), .record_enabled_o(),
        .display_valid_o(display_valid), .display_pcm_o(display_pcm), .display_reference_o(), .display_voices_o(), .display_status_o(),
        .effect_mask_o(), .effect_order_o(), .scope_status_o(), .tf_scope_control_o(), .dac_reference_o(), .dac_voices_o(),
        .dac_health_o(dac_health), .delay_ddr_request_o(ddr_request), .delay_ddr_write_o(ddr_write),
        .delay_ddr_address_o(ddr_address), .delay_ddr_data_o(ddr_data), .delay_ddr_mask_o(ddr_mask),
        .delay_ddr_ready_i(ddr_ready), .delay_ddr_response_i(ddr_response), .delay_ddr_read_data_i(ddr_read_data), .delay_ddr_debug_o()
    );
    usb3300_host_model #(.HIGH_SPEED(HIGH_SPEED)) phy (
        .clk_ulpi(clk_ulpi), .reset_n(reset_n), .runtime_i(transaction_reset_n), .attached_i(attached), .stall_i(1'b0),
        .link_data_i(physical_data), .link_oe_i(host_oe), .link_stp_i(host_stp), .phy_data_o(phy_data), .phy_oe_o(phy_oe),
        .phy_dir_o(phy_dir), .phy_nxt_o(phy_nxt), .device_txdata_i(device_txdata), .device_txvalid_i(device_txvalid),
        .device_chirp_i(device.chirp), .device_xcvr_i(device_xcvr), .device_term_i(device_term), .device_txready_o(device_txready),
        .device_rxdata_o(device_rxdata), .device_rxvalid_o(device_rxvalid), .device_rxactive_o(device_rxactive),
        .device_line_o(device_line), .function_o(), .normal_packets_o(normal_packets)
    );
    midi_usb_device device (
        .clk(clk_ulpi), .reset(!reset_n), .enable(reset_n), .utmi_rxdata(device_rxdata), .utmi_rxvalid(device_rxvalid),
        .utmi_rxactive(device_rxactive), .utmi_rxerror(1'b0), .utmi_linestate(device_line), .utmi_txready(device_txready),
        .utmi_txdata(device_txdata), .utmi_txvalid(device_txvalid), .utmi_opmode(), .utmi_xcvr(device_xcvr),
        .utmi_termsel(device_term), .utmi_dppd(), .utmi_dmpd(),
        .midi_tx_valid(attached && device_configured && source_index < source_target),
        .midi_tx_ready(midi_ready), .midi_tx_data(midi_word(source_index)), .midi_rx_valid(unexpected_midi_valid),
        .midi_rx_ready(1'b1), .midi_rx_data(unused_midi_data), .control_tx_valid(control_txvalid),
        .control_tx_ready(control_txready), .control_tx_data(control_txdata), .control_rx_valid(control_rxvalid),
        .control_rx_ready(control_rxready), .control_rx_data(control_rxdata), .configured(device_configured),
        .session_reset(), .midi_session_reset(), .control_session_reset(control_reset), .hs_active(device_hs),
        .phy_state(), .device_address(device_address)
    );
    panel_display_endpoint #(.CLK_HZ(60000000)) panel (
        .clk(clk_ulpi), .reset(!reset_n), .link_reset(control_reset), .rx_valid(control_rxvalid), .rx_ready(control_rxready),
        .rx_data(control_rxdata), .tx_valid(control_txvalid), .tx_ready(control_txready), .tx_data(control_txdata),
        .settings_toggle(1'b0), .remote_enable(remote_enable), .manual_settings(), .redraw_required(), .protocol_errors(protocol_errors),
        .tile_valid(tile_valid), .tile_ready(tile_delay == 0), .tile_x(tile_x), .tile_y(tile_y), .tile_width(tile_width),
        .tile_height(tile_height), .tile_read_addr(8'd0), .tile_read_data(), .tile_done(tile_done)
    );

    always @(posedge clk_ulpi) begin
        if (host_oe && phy_oe) $fatal(1, "audio ULPI contention");
        if (attached && device_configured && source_index < source_target && midi_ready) source_index <= source_index + 1;
        tile_done <= tile_delay == 1;
        if (tile_delay > 0) tile_delay <= tile_delay - 1;
        if (tile_valid && tile_delay == 0) begin
            if (tile_width != 62 || tile_height != 4) $fatal(1, "audio PL tile dimensions");
            if (tiles < 2 && (tile_x != 9'(tiles * 62) || tile_y != 0)) $fatal(1, "audio PL tile coordinates");
            tiles <= tiles + 1;
            tile_delay <= 20;
        end
        if (unexpected_midi_valid) $fatal(1, "audio PL leaked into MIDI OUT");
    end
    always @(posedge clk_memory) begin
        memory_cycle <= memory_cycle + 1;
        ddr_response <= 0;
        if (memory_delay > 0) memory_delay <= memory_delay - 1;
        if (memory_delay == 1) begin ddr_response <= 1; ddr_read_data <= pending_read_data; end
        if (reset_n && ddr_request && ddr_ready) begin
            if (ddr_address < 29'h0c000000 || ddr_address >= 29'h0c008000 || ddr_address[2:0] || ddr_mask)
                $fatal(1, "delay escaped authoritative native-word ring: %x mask=%x", ddr_address, ddr_mask);
            if (ddr_write) begin
                memory[ddr_address[14:3]] <= ddr_data;
                written[ddr_address[14:3]] <= 1;
                memory_writes <= memory_writes + 1;
            end else begin
                if (memory_delay || !written[ddr_address[14:3]]) $fatal(1, "invalid delay DDR read");
                pending_read_data <= memory[ddr_address[14:3]];
                memory_delay <= 7;
                memory_reads <= memory_reads + 1;
            end
        end
    end
    always @(posedge clk_ref) begin
        if (reset_n && display_valid) serial_frames <= serial_frames + 1;
        if (reset_n && performance_valid) feedback_frames <= feedback_frames + 1;
    end
    always @(posedge clk_audio) if (reset_n) begin
        audio_cycles <= audio_cycles + 1;
        if (sample_ce) begin
            if (last_tick >= 0 && audio_cycles - last_tick != 1600) $fatal(1, "audio sample schedule stalled");
            last_tick <= audio_cycles;
        end
        if (sample_valid) begin
            frames <= frames + 1;
            if (audio_left || audio_right) nonzero <= nonzero + 1;
        end
        if (deadline || overflow || drops || underruns || dac_health || midi_cdc_drop || observation_drop || feedback_drop)
            $fatal(1, "real audio health fault deadline=%0d overflow=%0d drops=%0d underruns=%0d dac=%x", deadline, overflow, drops, underruns, dac_health);
        if (`AUDIO_CORE.core_event_valid && `AUDIO_CORE.core_event_ready && `AUDIO_CORE.core_note_on) begin
            if (`AUDIO_CORE.attach_initializing) $fatal(1, "note entered DSP before initialization");
            case (note_starts)
                0: begin if (`AUDIO_CORE.core_note != 60) $fatal(1, "initial note changed"); defaults(); end
                1: if (`AUDIO_CORE.core_note != 67 || phase != 1) $fatal(1, "dirty note 67 changed");
                2: if (`AUDIO_CORE.core_note != 69 || phase != 1) $fatal(1, "dirty note 69 changed");
                3: begin if (`AUDIO_CORE.core_note != 62 || phase != 3) $fatal(1, "stale note after reconnect"); defaults(); end
                default: $fatal(1, "duplicated DSP note");
            endcase
            note_starts <= note_starts + 1;
        end
    end
    task automatic defaults;
        if (`AUDIO_CORE.mode_o != 2 || `AUDIO_CORE.profile != 0 || `AUDIO_CORE.synth_gain_o != 32768 ||
            `AUDIO_CORE.effect_mask_o || !`AUDIO_CORE.effect_master || `AUDIO_CORE.bend_index != 128 ||
            `AUDIO_CORE.sustain || `AUDIO_CORE.expression_gain != 32768 || `AUDIO_CORE.vibrato_depth ||
            `AUDIO_CORE.glide_cc || `AUDIO_CORE.route_o || `AUDIO_CORE.scope_enable ||
            `AUDIO_CORE.tf_scope_control_o[13:12] || `AUDIO_CORE.cue_running || `AUDIO_CORE.mode_pending)
            $fatal(1, "real attach defaults incomplete");
    endtask
    task automatic apb_access(input bit write_access, input [11:0] address, input [31:0] data, input bit expected_error,
                              output [31:0] reply);
        @(negedge clk_ref); psel = 1; penable = 0; pwrite = write_access; paddr = address; pwdata = data;
        @(negedge clk_ref); penable = 1;
        do @(posedge clk_ref); while (!pready);
        if (pslverr != expected_error) $fatal(1, "APB error mismatch at %x", address);
        reply = prdata;
        @(negedge clk_ref); psel = 0; penable = 0;
    endtask
    integer previous_nonzero, previous_epoch, target_frames;
    reg [31:0] reply;
    initial begin #1; reset_n = 0; repeat (10) @(negedge clk_cpu); reset_n = 1; end
    initial begin
        wait(note_starts == 1 && nonzero >= 8 && tiles >= 2);
        phase = 1; source_target = 8;
        wait(`AUDIO_CORE.volume == 19 * 256 && `AUDIO_CORE.expression_gain == 23 * 256 &&
             `AUDIO_CORE.vibrato_depth == 65 && `AUDIO_CORE.glide_cc == 17 && `AUDIO_CORE.bend_index == 192 &&
             `AUDIO_CORE.sustain && `AUDIO_CORE.profile == 4);
        apb_access(1, 12'h180, {14'd0, 4'd2, 7'd7, 7'd37}, 0, reply);
        wait(`AUDIO_CORE.volume == 37 * 256);
        apb_access(1, 12'h180, 32'h80000000, 1, reply);
        wait(performance_words[63:48] == `AUDIO_CORE.synth_gain_o);
        apb_access(0, 12'h184, 0, 0, reply);
        if (reply != performance_words[63:32]) $fatal(1, "APB/feedback parameter authority diverged");
        previous_epoch = `AUDIO_CORE.panic_epoch_o; source_target = 9;
        wait(`AUDIO_CORE.panic_epoch_o != previous_epoch && active_mask == 0 && `AUDIO_CORE.held_notes_o == 0);
        source_target = 10;
        wait(`AUDIO_CORE.mode_o == 0 && !`AUDIO_CORE.mode_pending);
        previous_nonzero = nonzero; source_target = 12;
        wait(note_starts == 3 && `AUDIO_CORE.held_notes_o[67] && `AUDIO_CORE.held_notes_o[69] && nonzero >= previous_nonzero + 8);
        $display("AUDIO HS=%0d actual parameters/APB/PCM/DDR before detach at %0t", HIGH_SPEED, $time);
        phase = 2; previous_epoch = `AUDIO_CORE.panic_epoch_o;
        @(negedge clk_cpu); attached = 0;
        wait(!transaction_reset_n); repeat (8) @(negedge clk_cpu);
        if (telemetry[1]) $fatal(1, "real audio owner did not detach independently of firmware");
        wait(`AUDIO_CORE.panic_epoch_o != previous_epoch && active_mask == 0 && `AUDIO_CORE.held_notes_o == 0);
        #12000000;
        if (device_configured || device_address != 0 || `AUDIO_CORE.deferred || `AUDIO_CORE.sustain)
            $fatal(1, "stale real audio state survived detach");
        phase = 3; previous_nonzero = nonzero; attached = 1; source_target = 13;
        wait(note_starts == 4 && nonzero >= previous_nonzero + 8 && tiles >= 4);
        source_target = 14;
        wait(!`AUDIO_CORE.held_notes_o[62]);
        previous_epoch = `AUDIO_CORE.panic_epoch_o; source_target = 15;
        wait(`AUDIO_CORE.panic_epoch_o != previous_epoch && active_mask == 0);
        target_frames = serial_frames + 8;
        wait(serial_frames >= target_frames);
        if (cpu_fault || failed || !phy_ready || !traffic_enable || high_speed != (HIGH_SPEED != 0) ||
            device_hs != (HIGH_SPEED != 0) || !device_configured || !remote_enable || protocol_errors ||
            !telemetry[1] || source_index != 15 || display_pcm || feedback_frames < 100 || memory_reads == 0 || memory_writes < 100)
            $fatal(1, "real audio final acceptance fault=%x pc=%x display=%x", cpu_fault, cpu_fault_address, display_pcm);
        $display("PASS workstation_usb2_audio_25k: HS=%0d production CPU, session/defaults/parameters/DSP/serial, APB authority, DDR ring, continuous 48k schedule, detach/reattach, PANIC, PL; frames=%0d serial=%0d", HIGH_SPEED, frames, serial_frames);
        $finish;
    end
    initial begin #2000000000; $fatal(1, "real audio timeout phase=%0d source=%0d notes=%0d frames=%0d nonzero=%0d tiles=%0d fault=%x mode=%0d init=%0d", phase, source_index, note_starts, frames, nonzero, tiles, cpu_fault, `AUDIO_CORE.mode_o, `AUDIO_CORE.attach_initializing); end
endmodule
`undef AUDIO_CORE
