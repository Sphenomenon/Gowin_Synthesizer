`timescale 1ns/1ps

module tb_workstation_output;
    reg clk = 0;
    always #5 clk = ~clk;
    reg reset_n = 0, scope_enable = 0, tf_active = 0;
    wire synth_tick, tf_tick, synth_bck, synth_ws, synth_data, synth_pa;
    wire tf_bck, tf_ws, tf_data, tf_pa;
    wire [3:0] actual_pins, expected_pins;
    wire actual_valid, expected_valid, expected_sample_valid, switching, selected_tf;
    wire [127:0] actual_snapshot, expected_snapshot;
    wire [31:0] expected_pcm, expected_reference;
    integer cycles = 0, synth_frames = 0, tf_frames = 0, muted_cycles = 0;

    pt8211_tx #(.BCK_HALF_CYCLES(2), .STEREO_ENABLE(1)) synth (
        .clk(clk), .reset_n(reset_n), .sample_data(32'sh12340000), .sample_right(-32'sh23450000),
        .sample_valid(1'b1), .sample_tick(synth_tick),
        .hp_bck(synth_bck), .hp_ws(synth_ws), .hp_din(synth_data), .pa_en(synth_pa),
        .sample_revision(24'd0), .sample_nonzero_voices(32'd3), .sample_trigger_reference(32'h1234)
    );
    pt8211_tx #(.BCK_HALF_CYCLES(3), .STEREO_ENABLE(1)) tf_source (
        .clk(clk), .reset_n(reset_n), .sample_data(-32'sh34560000), .sample_right(32'sh45670000),
        .sample_valid(1'b1), .sample_tick(tf_tick),
        .hp_bck(tf_bck), .hp_ws(tf_ws), .hp_din(tf_data), .pa_en(tf_pa),
        .sample_revision(24'd0), .sample_nonzero_voices(32'd0), .sample_trigger_reference(32'd0)
    );
    workstation_output_router dut (
        .clk_i(clk), .rst_ni(reset_n), .scope_enable_i(scope_enable), .tf_active_i(tf_active),
        .synth_tick_i(synth_tick), .tf_tick_i(tf_tick),
        .synth_bck_i(synth_bck), .synth_ws_i(synth_ws), .synth_data_i(synth_data), .synth_pa_i(synth_pa),
        .tf_bck_i(tf_bck), .tf_ws_i(tf_ws), .tf_data_i(tf_data), .tf_pa_i(tf_pa),
        .synth_reference_i(32'h1234), .synth_voices_i(32'd3), .synth_health_i(32'h55aa),
        .bck_o(actual_pins[3]), .ws_o(actual_pins[2]), .data_o(actual_pins[1]), .pa_o(actual_pins[0]),
        .tap_valid_o(actual_valid), .tap_snapshot_o(actual_snapshot)
    );
    scope_dac_select old_selector (
        .clk_i(clk), .rst_ni(reset_n), .scope_enable_i(scope_enable), .tf_source_active_i(tf_active),
        .synth_frame_tick_i(synth_tick), .tf_frame_tick_i(tf_tick),
        .synth_bck_i(synth_bck), .synth_ws_i(synth_ws), .synth_din_i(synth_data), .synth_pa_i(synth_pa),
        .tf_bck_i(tf_bck), .tf_ws_i(tf_ws), .tf_din_i(tf_data), .tf_pa_i(tf_pa),
        .hp_bck_o(expected_pins[3]), .hp_ws_o(expected_pins[2]), .hp_din_o(expected_pins[1]), .pa_en_o(expected_pins[0]),
        .tf_selected_o(selected_tf), .switching_o(switching)
    );
    pt8211_observer old_observer (
        .clk(clk), .reset_n(reset_n && !switching),
        .bck(expected_pins[3]), .ws(expected_pins[2]), .din(expected_pins[1]),
        .frame_reference(selected_tf ? 32'd0 : 32'h1234),
        .pcm_pair(expected_pcm), .sample_valid(expected_sample_valid), .trigger_reference(expected_reference)
    );
    assign expected_valid = expected_sample_valid && !switching;
    assign expected_snapshot = {expected_pcm, expected_reference, selected_tf ? 32'd0 : 32'd3, 32'h55aa};

    always @(negedge clk) if (reset_n) begin
        cycles++;
        if ({actual_pins, actual_valid, actual_snapshot} !== {expected_pins, expected_valid, expected_snapshot})
            $fatal(1, "output route differs from old top at cycle %0d", cycles);
        if (actual_valid) begin
            if (selected_tf) begin
                tf_frames++;
                if (actual_snapshot[127:96] != 32'hcbaa4567 || actual_snapshot[95:32] != 0)
                    $fatal(1, "TF observation tap or metadata incorrect");
            end else begin
                synth_frames++;
                if (actual_snapshot[127:96] != 32'h1234dcbb || actual_snapshot[95:32] != {32'h1234, 32'd3})
                    $fatal(1, "synth observation tap or metadata incorrect");
            end
        end
        if (actual_pins[0]) muted_cycles++;
    end

    task run_cycles(input integer count);
        repeat(count) @(negedge clk);
        #1;
    endtask

    initial begin
        run_cycles(4); reset_n = 1; run_cycles(5000);
        tf_active = 1; run_cycles(5000);
        scope_enable = 1; run_cycles(5000);
        scope_enable = 0; run_cycles(5000);
        tf_active = 0; run_cycles(5000);
        for (integer iteration = 0; iteration < 80; iteration++) begin
            tf_active = !tf_active;
            scope_enable = iteration % 3 == 0;
            run_cycles(17 + iteration * 13);
        end
        reset_n = 0; run_cycles(3); reset_n = 1; run_cycles(5000);
        if (synth_frames < 30 || tf_frames < 20 || muted_cycles < 100)
            $fatal(1, "insufficient output coverage");
        $display("PASS workstation_output: cycles=%0d synth_frames=%0d tf_frames=%0d muted_cycles=%0d; pins, stereo PCM, metadata, scope priority, reset and rapid switching match old top", cycles, synth_frames, tf_frames, muted_cycles);
        $finish;
    end
endmodule
