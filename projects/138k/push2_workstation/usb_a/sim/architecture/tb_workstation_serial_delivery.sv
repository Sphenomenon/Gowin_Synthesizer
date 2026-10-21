`timescale 1ns/1ps

module tb_workstation_serial_delivery;
    logic clk = 0, reset_n = 0, event_valid = 0;
    always #6.510416 clk = ~clk;
    logic [17:0] event_data = 0;
    wire event_ready, tick, render_valid;
    wire panic_muted;
    wire signed [31:0] left, right;
    wire [31:0] active, deadline, overflow, drops;
    wire [1:0] actual_mode;
    wire [5:0] active_count;
    wire [127:0] held_notes;
    wire [9:0] cancel_epoch;
    wire [31:0] raw_underruns, raw_frames, guarded_underruns, guarded_frames;
    wire bck, word_select, serial_data, amplifier_enable;
    wire guarded_bck, guarded_word_select, guarded_serial_data, guarded_tick;
    wire offered_valid;
    wire signed [31:0] offered_left, offered_right;
    wire [31:0] offered_reference, offered_voices, duplicate_faults;
    integer startup_underruns, after_cc_underruns, after_lifecycle_underruns;
    integer cc_cases = 0, lifecycle_cases = 0, elapsed_cycles = 0, last_tick = -1;
    integer total_raw_cc = 0, total_raw_lifecycle = 0;

    gw138k_event_workstation #(.TIMING_OPTIMIZED(1)) dut(
        .clk_i(clk), .rst_ni(reset_n), .midi_byte_valid_i(1'b0), .midi_byte_i(8'd0),
        .pc_byte_valid_i(1'b0), .pc_byte_i(8'd0),
        .cpu_event_valid_i(event_valid), .cpu_event_i(event_data), .cpu_event_ready_o(event_ready),
        .sample_ce_i(tick), .pcm_left_i(32'sd0), .pcm_right_i(32'sd0),
        .sample_valid_o(render_valid), .left_o(left), .right_o(right), .active_mask_o(active), .mode_o(actual_mode),
        .active_voice_count_o(active_count), .held_notes_o(held_notes),
        .deadline_miss_o(deadline), .midi_overflow_o(overflow), .note_drop_o(drops),
        .panic_epoch_o(cancel_epoch), .panic_muted_o(panic_muted), .delay_mem_clk_i(clk), .delay_mem_rst_ni(reset_n),
        .delay_dwr_pop_i(1'b0), .delay_drd_push_i(1'b0), .delay_drd_data_i(65'd0));

    pt8211_tx #(.BCK_HALF_CYCLES(25), .STEREO_ENABLE(1)) raw_tx(
        .clk(clk), .reset_n(reset_n), .sample_data(left), .sample_right(right),
        .sample_valid(render_valid), .sample_tick(tick), .hp_bck(bck), .hp_ws(word_select),
        .hp_din(serial_data), .pa_en(amplifier_enable), .underrun_count(raw_underruns),
        .frame_count(raw_frames), .sample_revision(24'd0), .sample_nonzero_voices(active),
        .sample_trigger_reference(32'd0));

    workstation_frame_delivery delivery(
        .clk_i(clk), .rst_ni(reset_n), .sample_ce_i(tick), .muted_i(panic_muted), .cancel_epoch_i(cancel_epoch),
        .render_valid_i(render_valid), .left_i(left), .right_i(right),
        .reference_i(32'd0), .voices_i(active), .valid_o(offered_valid),
        .left_o(offered_left), .right_o(offered_right),
        .reference_o(offered_reference), .voices_o(offered_voices),
        .duplicate_frames_o(duplicate_faults));

    pt8211_tx #(.BCK_HALF_CYCLES(25), .STEREO_ENABLE(1)) guarded_tx(
        .clk(clk), .reset_n(reset_n), .sample_data(offered_left), .sample_right(offered_right),
        .sample_valid(offered_valid), .sample_tick(guarded_tick), .hp_bck(guarded_bck),
        .hp_ws(guarded_word_select), .hp_din(guarded_serial_data), .pa_en(),
        .underrun_count(guarded_underruns), .frame_count(guarded_frames),
        .sample_revision(24'd0), .sample_nonzero_voices(offered_voices),
        .sample_trigger_reference(offered_reference));

    always @(negedge clk) if (reset_n) begin
        elapsed_cycles++;
        if ({tick, bck, word_select, raw_frames} !==
            {guarded_tick, guarded_bck, guarded_word_select, guarded_frames})
            $fatal(1, "serial schedule changed");
        if (tick) begin
            if (last_tick >= 0 && elapsed_cycles - last_tick != 1600)
                $fatal(1, "sample cadence changed");
            last_tick = elapsed_cycles;
        end
        if (deadline || overflow || drops || duplicate_faults || guarded_underruns)
            $fatal(1, "guarded delivery health failure %0d %0d %0d %0d %0d",
                   deadline, overflow, drops, duplicate_faults, guarded_underruns);
    end

    task automatic send(input integer event_kind, event_address, event_value);
        @(negedge clk);
        event_data = {4'(event_kind), 7'(event_address), 7'(event_value)};
        event_valid = 1;
        do @(posedge clk); while (!event_ready);
        @(negedge clk); event_valid = 0;
    endtask

    task automatic frame();
        @(posedge tick); @(negedge clk);
    endtask

    initial begin
        repeat (6) @(negedge clk); reset_n = 1;
        repeat (32) frame(); startup_underruns = raw_underruns;
        for (integer source_mode = 0; source_mode < 4; source_mode++) begin
            send(2, 90, 0);
            send(2, 80, source_mode < 3 ? source_mode : 2);
            wait(actual_mode == (source_mode < 3 ? source_mode : 2));
            if (source_mode == 3) send(2, 90, 127);
            repeat (4) frame();
            if (dut.scope_enable !== (source_mode == 3)) $fatal(1, "wrong audio source exercised");
            startup_underruns = raw_underruns;
            for (integer offset = 0; offset < 1600; offset++) begin
                send(1, 60, 96); repeat (3) frame();
                if (active_count != 1 || held_notes != (128'd1 << 60)) $fatal(1, "CC probe note was not active");
                repeat (offset) @(negedge clk);
                send(2, 120, 0); repeat (3) frame(); cc_cases++;
                if (active_count || held_notes) $fatal(1, "CC PANIC did not cancel voices");
            end
            after_cc_underruns = raw_underruns;
            for (integer offset = 0; offset < 1600; offset++) begin
                send(1, 60, 96); repeat (3) frame();
                if (active_count != 1 || held_notes != (128'd1 << 60)) $fatal(1, "lifecycle probe note was not active");
                repeat (offset) @(negedge clk);
                send(15, 0, 0); repeat (3) frame(); lifecycle_cases++;
                if (active_count || held_notes) $fatal(1, "lifecycle did not cancel voices");
            end
            after_lifecycle_underruns = raw_underruns;
            if (after_cc_underruns == startup_underruns ||
                after_lifecycle_underruns == after_cc_underruns)
                $fatal(1, "negative control failed to reproduce cancellation gaps");
            $display("METRIC source_mode=%0d raw_cc_underruns=%0d raw_lifecycle_underruns=%0d", source_mode, after_cc_underruns-startup_underruns, after_lifecycle_underruns-after_cc_underruns);
            total_raw_cc += after_cc_underruns - startup_underruns;
            total_raw_lifecycle += after_lifecycle_underruns - after_cc_underruns;
        end
        $display("PASS workstation_serial_delivery: cycles=%0d cc_cases=%0d lifecycle_cases=%0d raw_cc_underruns=%0d raw_lifecycle_underruns=%0d guarded_underruns=%0d duplicate_faults=%0d frame_cycles=1600", elapsed_cycles, cc_cases, lifecycle_cases, total_raw_cc, total_raw_lifecycle, guarded_underruns, duplicate_faults);
        $finish;
    end
    initial begin #3000000000; $fatal(1, "serial delivery timeout"); end
endmodule
