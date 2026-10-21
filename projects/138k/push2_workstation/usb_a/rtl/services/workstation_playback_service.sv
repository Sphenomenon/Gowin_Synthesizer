`timescale 1ns/1ps

module workstation_playback_service #(
    parameter integer MODEL_SETTLE_CYCLES = 2_500_000,
    parameter integer RECOVERY_TIMEOUT_CYCLES = 480_000_000
) (
    input wire clk_i, rst_ni,
    input wire [3:0] model_status_i,
    input wire tf_mode_i, tf_restart_i, cancel_i,
    input wire [3:0] tf_track_i,
    input wire song_valid_i,
    input wire [3:0] song_track_i,
    input wire playlist_ready_i,
    input wire [3:0] track_count_i,
    input wire card_lost_i, analysis_done_i,
    output wire analysis_enable_o, analysis_restart_o, analysis_hold_o,
    output wire reader_restart_o,
    output wire [3:0] reader_track_o,
    output wire score_accept_o
);
    logic model_ready_q;
    logic [21:0] restart_delay;
    logic [2:0] run_reset_count;
    logic song_started, song_restart, song_pending;
    logic recovering;
    logic [28:0] recovery_wait;
    logic [3:0] selected_track, pending_track;
    wire model_ready = model_status_i == 4'd14;
    wire model_became_ready = model_ready && !model_ready_q;

    assign analysis_restart_o = run_reset_count != 0;
    assign analysis_enable_o = model_ready_q && song_started && restart_delay == 0 &&
        !analysis_restart_o && !tf_mode_i;
    assign analysis_hold_o = !tf_mode_i && model_ready_q && song_started && !analysis_done_i;
    assign reader_restart_o = tf_restart_i || (!tf_mode_i && (model_became_ready || song_restart));
    assign reader_track_o = tf_mode_i ? tf_track_i : selected_track;
    assign score_accept_o = !song_pending && !song_valid_i && !card_lost_i;

    initial begin
        if (MODEL_SETTLE_CYCLES < 1 || MODEL_SETTLE_CYCLES >= 2**22)
            $fatal(1, "model settle cycles exceed counter capacity");
        if (RECOVERY_TIMEOUT_CYCLES < 1 || RECOVERY_TIMEOUT_CYCLES >= 2**29)
            $fatal(1, "recovery timeout exceeds counter capacity");
    end

    always_ff @(posedge clk_i or negedge rst_ni) begin
        if (!rst_ni) begin
            model_ready_q <= 0;
            restart_delay <= 0;
            run_reset_count <= 0;
            song_started <= 0;
            song_restart <= 0;
            song_pending <= 0;
            selected_track <= 0;
            pending_track <= 0;
            recovering <= 0;
            recovery_wait <= 0;
        end else begin
            model_ready_q <= model_ready;
            song_restart <= 0;
            if (run_reset_count != 0) run_reset_count <= run_reset_count - 1'b1;
            if (model_became_ready) restart_delay <= 22'(MODEL_SETTLE_CYCLES);
            else if (restart_delay != 0) restart_delay <= restart_delay - 1'b1;
            if (cancel_i) begin
                song_pending <= 0;
                song_started <= 0;
                recovering <= 0;
                run_reset_count <= 4;
                restart_delay <= 0;
            end else if (card_lost_i) begin
                song_pending <= 0;
                song_started <= 0;
                run_reset_count <= 4;
                restart_delay <= 0;
                recovering <= song_started;
                recovery_wait <= 29'(RECOVERY_TIMEOUT_CYCLES);
            end else if (recovering) begin
                if (playlist_ready_i && track_count_i != 0) begin
                    recovering <= 0;
                    song_started <= 1;
                    run_reset_count <= 4;
                    restart_delay <= 22'(MODEL_SETTLE_CYCLES);
                end else if (recovery_wait == 0) recovering <= 0;
                else recovery_wait <= recovery_wait - 1'b1;
            end else if (song_valid_i && !tf_mode_i) begin
                song_pending <= 1;
                pending_track <= song_track_i;
            end else if (song_pending && model_ready && !tf_mode_i) begin
                song_pending <= 0;
                song_started <= 1;
                selected_track <= pending_track;
                song_restart <= 1;
                run_reset_count <= 4;
                restart_delay <= 22'(MODEL_SETTLE_CYCLES);
            end
        end
    end
endmodule
