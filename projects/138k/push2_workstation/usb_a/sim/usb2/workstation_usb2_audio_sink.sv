`timescale 1ns/1ps
module workstation_usb2_audio_sink (
    input wire clk_cpu, clk_ref, clk_audio, clk_memory, clk_dac_reference, reset_n,
    input wire event_valid_i, lifecycle_i, cancel_i,
    input wire [17:0] event_i,
    output wire event_ready_o,
    output wire [447:0] feedback_o,
    output wire [127:0] held_o,
    output reg [31:0] initialization_count_o = 0,
    output reg [31:0] note_count_o = 0,
    output wire applied_note_valid_o,
    output wire [17:0] applied_note_o,
    output reg [31:0] sample_ticks_o = 0,
    output reg [31:0] serial_nonzero_o = 0,
    output wire [31:0] serial_sequence_o, serial_pcm_o
);
    wire [447:0] performance;
    assign feedback_o = performance;
    wire [15:0] master_volume;
    wire sample_tick, sample_valid, synth_bck, synth_ws, synth_data, synth_pa;
    wire [31:0] active, deadline, overflow, note_drop, underrun, midi_drop, observation_drop, record_drop;
    wire [31:0] scope_status, tf_control, reference_value, voice_value, health;
    wire uart_error;
    wire delay_write_valid, delay_write_pop, delay_read_push, delay_read_ready;
    wire [64:0] delay_write_data, delay_read_data;
    gw138k_usb_controlled_audio #(.EXTERNAL_MASTER_VOLUME(1)) managed (
        .usb_event_valid(event_valid_i), .usb_lifecycle(lifecycle_i), .usb_cancel(cancel_i),
        .usb_event_data(event_i), .usb_event_ready(event_ready_o),
        .clk_50m(clk_ref), .audio_clk(clk_audio), .reset_n(reset_n), .midi_rx_i(1'b1), .pc_uart_rx_i(1'b1),
        .performance_words_o(performance), .pclk(clk_ref), .preset_n(reset_n),
        .psel(1'b0), .penable(1'b0), .pwrite(1'b0), .paddr(12'd0), .pwdata(32'd0), .pstrb(4'd0),
        .pready(), .pslverr(), .prdata(), .hp_bck(synth_bck), .hp_ws(synth_ws), .hp_din(synth_data), .pa_en(synth_pa),
        .master_volume_o(master_volume), .scope_status_o(scope_status), .tf_scope_control_o(tf_control),
        .dac_reference_o(reference_value), .dac_voices_o(voice_value), .dac_health_o(health),
        .sample_ce_o(sample_tick), .sample_valid_o(sample_valid), .audio_left_o(), .audio_right_o(),
        .active_mask_o(active), .deadline_miss_o(deadline), .midi_overflow_o(overflow), .note_drop_o(note_drop),
        .underrun_count_o(underrun), .midi_cdc_drop_o(midi_drop), .observation_drop_o(observation_drop),
        .uart_error_o(uart_error), .record_drop_o(record_drop), .led_mask_o(), .score_frame_o(),
        .score_running_o(), .score_done_o(), .record_enabled_o(), .display_valid_o(), .display_pcm_o(),
        .display_reference_o(), .display_voices_o(), .display_status_o(), .effect_mask_o(), .effect_order_o(),
        .delay_mem_clk_i(clk_memory), .delay_mem_rst_ni(reset_n), .delay_dwr_valid_o(delay_write_valid),
        .delay_dwr_data_o(delay_write_data), .delay_dwr_pop_i(delay_write_pop), .delay_drd_push_i(delay_read_push),
        .delay_drd_data_i(delay_read_data), .delay_drd_ready_o(delay_read_ready)
    );
    gw138k_push_performance_uart feedback (
        .clk_50m(clk_ref), .reset_n(reset_n), .audio_clk(clk_audio), .audio_reset_n(reset_n), .audio_locked(1'b1),
        .sample_valid(sample_valid), .memory_flags(8'd0), .audio_status(32'd0), .video_diagnostics(128'd0),
        .cpu_clk(clk_cpu), .cpu_reset_n(reset_n), .cpu_words(224'd0), .performance_words(performance),
        .usb_clk(clk_cpu), .usb_reset_n(reset_n), .usb_words(224'd0), .push_words(224'd0),
        .performance_feedback(), .serial_out()
    );
    wire final_bck, final_ws, final_data, final_pa, final_valid;
    wire [127:0] final_snapshot;
    workstation_output_router router (
        .clk_i(clk_audio), .rst_ni(reset_n), .scope_enable_i(scope_status[8]), .tf_active_i(1'b0),
        .synth_tick_i(sample_tick), .tf_tick_i(1'b0), .synth_bck_i(synth_bck), .synth_ws_i(synth_ws),
        .synth_data_i(synth_data), .synth_pa_i(synth_pa), .tf_bck_i(1'b0), .tf_ws_i(1'b0),
        .tf_data_i(1'b0), .tf_pa_i(1'b0), .synth_reference_i(reference_value), .synth_voices_i(voice_value),
        .synth_health_i(health), .bck_o(final_bck), .ws_o(final_ws), .data_o(final_data), .pa_o(final_pa),
        .tap_valid_o(final_valid), .tap_snapshot_o(final_snapshot)
    );
    wire dac_mclk, dac_bck, dac_lrck, dac_data, dac_pdn_n, dac_mute, dac_frame_clk, dac_frame_valid;
    workstation_fpc_audio fpc (
        .clk_50m_i(clk_ref), .dac_reference_clk_i(clk_dac_reference), .audio_clk_i(clk_audio),
        .rst_ni(reset_n), .audio_rst_ni(reset_n), .master_volume_i(master_volume),
        .sample_valid_i(final_valid), .enable_i(!final_pa), .pcm_pair_i(final_snapshot[127:96]),
        .mclk_o(dac_mclk), .bck_o(dac_bck), .lrck_o(dac_lrck), .data_o(dac_data), .pdn_no(dac_pdn_n),
        .smute_o(dac_mute), .sslow_o(), .sd_o(), .slow_o(), .frame_clock_o(dac_frame_clk),
        .frame_valid_o(dac_frame_valid), .frame_pcm_o(serial_pcm_o), .frame_sequence_o(serial_sequence_o),
        .mailbox_drop_count_o()
    );
    wire ddr_req, ddr_write, ddr_response, ddr_ready;
    wire [28:0] ddr_address;
    wire [255:0] ddr_write_data, ddr_read_data;
    wire [31:0] ddr_mask;
    wire [7:0] dma_status;
    delay_ddr_dma dma (
        .clk_i(clk_memory), .rst_ni(reset_n), .dwr_valid_i(delay_write_valid), .dwr_data_i(delay_write_data),
        .dwr_pop_o(delay_write_pop), .drd_push_o(delay_read_push), .drd_data_o(delay_read_data),
        .drd_ready_i(delay_read_ready), .ddr_req_o(ddr_req), .ddr_write_o(ddr_write), .ddr_address_o(ddr_address),
        .ddr_data_o(ddr_write_data), .ddr_mask_o(ddr_mask), .ddr_ready_i(ddr_ready),
        .ddr_response_i(ddr_response), .ddr_read_data_i(ddr_read_data), .debug_status_o(dma_status)
    );
    reg [255:0] memory [0:4095];
    reg [4095:0] written = 0;
    reg [1:0] read_delay = 0;
    reg [255:0] pending_read = 0;
    assign ddr_ready = read_delay == 0;
    assign ddr_response = read_delay == 1;
    assign ddr_read_data = pending_read;
    wire [28:0] relative_address = ddr_address - 29'h0c000000;
    always @(posedge clk_memory) begin
        if (!reset_n) begin written <= 0; read_delay <= 0; end
        else begin
            if (read_delay != 0) read_delay <= read_delay - 1'b1;
            if (ddr_req && ddr_ready) begin
                if (relative_address >= 32768 || relative_address[2:0] != 0)
                    $fatal(1, "audio delay DMA native-word address outside the existing 128 KiB ring");
                if (ddr_write) begin
                    if (ddr_mask != 0) $fatal(1, "audio delay DMA partial memory write");
                    memory[relative_address[14:3]] <= ddr_write_data;
                    written[relative_address[14:3]] <= 1;
                end else begin
                    if (!written[relative_address[14:3]]) $fatal(1, "audio delay DMA read before write");
                    pending_read <= memory[relative_address[14:3]];
                    read_delay <= 2;
                end
            end
        end
    end

    wire initializing = managed.u_audio.u_workstation.attach_initializing;
    wire parameter_commit = managed.u_audio.u_workstation.parameter_commit;
    wire [17:0] committed_event = managed.u_audio.u_workstation.event_data;
    assign held_o = managed.held_notes;
    assign applied_note_valid_o = parameter_commit && !initializing && committed_event[17:14] < 2;
    assign applied_note_o = committed_event;
    reg previous_initializing = 0;
    integer ticks_between = 0, initialization_events = 0, silent_held_ticks = 0;
    reg [31:0] previous_nonzero = 0;
    function automatic [17:0] default_event(input integer index);
        case (index)
            0: default_event = {4'd2, 7'd96, 7'd0};
            1: default_event = {4'd2, 7'd104, 7'd0};
            2: default_event = {4'd2, 7'd90, 7'd0};
            3: default_event = {4'd4, 7'd0, 7'd64};
            4: default_event = {4'd2, 7'd64, 7'd0};
            5: default_event = {4'd2, 7'd11, 7'd127};
            6: default_event = {4'd2, 7'd1, 7'd0};
            7: default_event = {4'd2, 7'd5, 7'd0};
            8: default_event = {4'd2, 7'd82, 7'd0};
            9: default_event = {4'd2, 7'd7, 7'd127};
            10: default_event = {4'd3, 7'd73, 7'd0};
            11: default_event = {4'd2, 7'd80, 7'd2};
            default: default_event = {4'd2, 7'd81, 7'd0};
        endcase
    endfunction
    always @(posedge clk_audio) begin
        if (!reset_n) begin
            previous_initializing <= 0; initialization_events <= 0; ticks_between <= 0;
            silent_held_ticks <= 0; previous_nonzero <= 0;
            initialization_count_o <= 0; note_count_o <= 0; sample_ticks_o <= 0;
        end else begin
            previous_initializing <= initializing;
            if (!previous_initializing && initializing) initialization_events <= 0;
            if (parameter_commit && initializing) begin
                if (initialization_events >= 13 || committed_event != default_event(initialization_events))
                    $fatal(1, "real audio initialization event order index=%0d event=%x", initialization_events, committed_event);
                initialization_events <= initialization_events + 1;
            end
            if (previous_initializing && !initializing) begin
                if (initialization_events != 13 || managed.u_audio.u_workstation.mode_o != 2 ||
                    managed.u_audio.u_workstation.mode_pending || master_volume != 32768 ||
                    managed.u_audio.u_workstation.profile_o != 0 || managed.u_audio.u_workstation.effect_mask_o != 0 ||
                    !managed.u_audio.u_workstation.effect_master || managed.u_audio.u_workstation.bend_index != 128 ||
                    managed.u_audio.u_workstation.sustain || managed.u_audio.u_workstation.expression_gain != 32768 ||
                    managed.u_audio.u_workstation.vibrato_depth != 0 || managed.u_audio.u_workstation.glide_cc != 0 ||
                    managed.u_audio.u_workstation.route_o != 0 || managed.u_audio.u_workstation.scope_enable ||
                    tf_control[13:12] != 0 || managed.u_audio.u_workstation.cue_running)
                    $fatal(1, "real audio common defaults not committed after initialization");
                initialization_count_o <= initialization_count_o + 1;
                $display("AUDIO committed defaults=%0d at %0t", initialization_count_o + 1, $time);
                $fflush();
            end
            if (applied_note_valid_o) begin
                if (managed.u_audio.u_workstation.mode_pending || managed.u_audio.u_workstation.mode_o != 2)
                    $fatal(1, "note applied before real mode commit");
                note_count_o <= note_count_o + 1;
            end
            if (sample_tick) begin
                previous_nonzero <= serial_nonzero_o;
                if (held_o == 0 || serial_nonzero_o != previous_nonzero) silent_held_ticks <= 0;
                else silent_held_ticks <= silent_held_ticks + 1;
                if (silent_held_ticks >= 4096)
                    $fatal(1, "held note has no decoded FPC audio: voices=%x shutdown=%b mute=%b gain=%0d pcm=%x",
                           active, final_pa, dac_mute, fpc.gain, serial_pcm_o);
                if (sample_ticks_o != 0 && ticks_between != 1599) $fatal(1, "audio schedule paused during USB work");
                ticks_between <= 0;
                sample_ticks_o <= sample_ticks_o + 1;
                if (sample_ticks_o != 0 && sample_ticks_o % 48000 == 0) begin
                    $display("AUDIO ticks=%0d notes=%0d init=%0d serial_nonzero=%0d at %0t",
                             sample_ticks_o, note_count_o, initialization_count_o, serial_nonzero_o, $time);
                    $fflush();
                end
            end else ticks_between <= ticks_between + 1;
            if (deadline != 0 || overflow != 0 || note_drop != 0 || midi_drop != 0 || observation_drop != 0 ||
                record_drop != 0 || uart_error || managed.u_audio.delivery_faults != 0 ||
                (sample_ticks_o > 8 && underrun != 0))
                $fatal(1, "real audio pipeline fault deadline=%0d overflow=%0d drops=%0d underrun=%0d delivery=%0d",
                       deadline, overflow, note_drop, underrun, managed.u_audio.delivery_faults);
        end
    end
    reg previous_ws = 0, aligned = 0;
    reg [31:0] serial_word = 0, left_word = 0, previous_tap = 0, current_tap = 0;
    reg previous_mute = 1, current_mute = 1;
    integer bits_seen = 0;
    realtime previous_lrck = 0;
    always @(posedge dac_frame_clk) begin
        #1;
        if (!dac_pdn_n) begin
            previous_tap = 0; current_tap = 0; previous_mute = 1; current_mute = 1;
        end
        else if (dac_frame_valid) begin
            previous_tap = current_tap; current_tap = serial_pcm_o;
            previous_mute = current_mute; current_mute = dac_mute;
        end
    end
    always @(negedge dac_pdn_n) begin
        aligned = 0; bits_seen = 0; previous_lrck = 0;
    end
    always @(posedge dac_lrck) begin
        if (dac_pdn_n && previous_lrck != 0 && ($realtime - previous_lrck < 20800 || $realtime - previous_lrck > 20860))
            $fatal(1, "FPC LRCK stopped or changed rate during hotplug");
        previous_lrck = $realtime;
    end
    always @(posedge dac_bck) begin
        serial_word = {serial_word[30:0], dac_data};
        if (dac_lrck != previous_ws) begin
            if (aligned) begin
                if (bits_seen != 31 || serial_word[15:0] != 0) $fatal(1, "real FPC I2S slot/padding error");
                if (!previous_ws) left_word = serial_word;
                else begin
                    if (serial_sequence_o > 6 && previous_tap !== (previous_mute ? 32'd0 : {left_word[31:16], serial_word[31:16]}))
                        $fatal(1, "real FPC tap differs from independently decoded serial PCM");
                    if (!previous_mute && {left_word[31:16], serial_word[31:16]} != 0)
                        serial_nonzero_o = serial_nonzero_o + 1;
                end
            end
            previous_ws = dac_lrck;
            aligned = dac_pdn_n; bits_seen = 0; serial_word = 0;
        end else bits_seen = bits_seen + 1;
    end
endmodule
