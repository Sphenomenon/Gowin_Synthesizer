`timescale 1ns/1ps

module tb_workstation_playback;
    reg clk = 0;
    always #5 clk = ~clk;
    reg reset_n = 0;
    reg [3:0] model_status = 0;
    reg tf_mode = 0, tf_restart = 0, cancel = 0;
    reg [3:0] tf_track = 0, song_track = 0, track_count = 0;
    reg song_valid = 0, playlist_ready = 0, card_lost = 0, analysis_done = 0;
    wire [8:0] actual, expected;
    integer cycles = 0, restart_cycles = 0, enabled_cycles = 0;
    reg [31:0] random_state = 32'h138ca350;

    workstation_playback_service #(.MODEL_SETTLE_CYCLES(16), .RECOVERY_TIMEOUT_CYCLES(24)) dut (
        .clk_i(clk), .rst_ni(reset_n), .model_status_i(model_status),
        .tf_mode_i(tf_mode), .tf_restart_i(tf_restart), .cancel_i(cancel), .tf_track_i(tf_track),
        .song_valid_i(song_valid), .song_track_i(song_track),
        .playlist_ready_i(playlist_ready), .track_count_i(track_count),
        .card_lost_i(card_lost), .analysis_done_i(analysis_done),
        .analysis_enable_o(actual[8]), .analysis_restart_o(actual[7]),
        .analysis_hold_o(actual[6]), .reader_restart_o(actual[5]),
        .reader_track_o(actual[4:1]), .score_accept_o(actual[0])
    );
    workstation_playback_reference reference (
        .clk_50m(clk), .reset_n(reset_n), .music_model_status(model_status),
        .tf_mode_50(tf_mode), .tf_scope_restart(tf_restart), .tf_scope_cancel(cancel),
        .tf_scope_track(tf_track), .song_cmd_valid(song_valid), .song_cmd_index(song_track),
        .playlist_scan_done(playlist_ready), .tf_track_count(track_count),
        .tf_card_lost(card_lost), .music_analysis_done(analysis_done), .observed_o(expected)
    );

    always @(negedge clk) if (reset_n) begin
        cycles++;
        if (actual !== expected) $fatal(1, "playback mismatch cycle=%0d actual=%h expected=%h", cycles, actual, expected);
        if (actual[5]) restart_cycles++;
        if (actual[8]) enabled_cycles++;
    end

    task tick(input integer count);
        repeat(count) @(negedge clk);
        #1;
    endtask

    task launch(input [3:0] track);
        song_track = track;
        song_valid = 1;
        tick(1);
        song_valid = 0;
        tick(24);
    endtask

    initial begin
        tick(3); reset_n = 1;
        launch(3);
        if (actual[8] || actual[4:1] != 0) $fatal(1, "launch did not wait for model");
        model_status = 14;
        tick(24);
        if (!actual[8] || actual[4:1] != 3) $fatal(1, "queued launch was not applied");
        cancel = 1; tick(1); cancel = 0; tick(8);
        if (actual[8]) $fatal(1, "cancel retained analysis");
        tf_mode = 1; tf_track = 9; launch(5);
        if (actual[8] || actual[4:1] != 9) $fatal(1, "TF mode did not own reader");
        tf_mode = 0; launch(6);
        card_lost = 1; tick(1); card_lost = 0;
        tick(30); playlist_ready = 1; track_count = 10; tick(24);
        if (actual[8]) $fatal(1, "expired recovery resumed playback");
        launch(7);
        card_lost = 1; tick(1); card_lost = 0; tick(24);
        if (!actual[8] || actual[4:1] != 7) $fatal(1, "recovery did not preserve track");
        for (integer iteration = 0; iteration < 4096; iteration++) begin
            random_state = {random_state[30:0], random_state[31] ^ random_state[21] ^ random_state[1] ^ random_state[0]};
            model_status = random_state[4:0] == 0 ? 0 : 14;
            tf_mode = random_state[8:5] == 0;
            tf_restart = random_state[12:9] == 0;
            cancel = random_state[16:13] == 0;
            song_valid = random_state[20:17] == 0;
            card_lost = random_state[24:21] == 0;
            playlist_ready = random_state[25];
            analysis_done = random_state[26];
            song_track = random_state[7:4];
            tf_track = random_state[11:8];
            track_count = random_state[15:12];
            tick(1);
        end
        reset_n = 0; tick(2); reset_n = 1; tick(4);
        if (cycles < 4200 || restart_cycles < 50 || enabled_cycles < 20) $fatal(1, "insufficient playback coverage");
        $display("PASS workstation_playback: cycles=%0d restart_cycles=%0d enabled_cycles=%0d; model wait, queue, cancel, TF isolation, recovery and expiry match old top", cycles, restart_cycles, enabled_cycles);
        $finish;
    end
endmodule
