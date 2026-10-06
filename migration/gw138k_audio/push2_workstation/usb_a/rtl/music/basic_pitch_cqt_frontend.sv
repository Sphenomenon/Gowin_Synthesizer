`timescale 1ns/1ps
`include "basic_pitch_fixed_pkg.svh"
// Basic Pitch CQT frontend.
//
// IMPLEMENTED IN THIS REVISION
//   * 48 kHz stereo S16LE -> mono -> 22.05 kHz integer polyphase resampler
//     (147/320, group-delay compensated; coefficients from
//     rtl/music/weights/resampler_poly.mem produced by the exporter).
//   * analysis-window capture into an external window RAM.
//
// NOT IMPLEMENTED IN THIS REVISION -- see BASIC_PITCH_CNN_VITERBI_138K_STATUS.md
//   * the CQT2010v2 filterbank cascade, NormalizedLog, folded BatchNorm and
//     harmonic stacking. The fixed-point CQT/NormalizedLog arithmetic is
//     validated on the host (music/basic_pitch_fixed_reference.py matches the
//     FP32 ONNX CQT magnitude at correlation 1.00000); moving it into RTL is
//     the outstanding datapath work.
//
// Status: RTL candidate (resampler simulated here; no synthesis/P&R available).
module basic_pitch_cqt_frontend #(
    parameter int PHASES  = 147,
    parameter int DOWN    = 320,
    parameter int DELAY   = 3200,   // (numtaps-1)/2, group delay
    parameter int TAPS    = 44,
    // The delay line must survive one whole 44-cycle tap chain: samples keep
    // arriving while a tap chain runs, so the buffer needs room for the start
    // lag plus TAPS plus up to TAPS newly written samples. 256 entries with a
    // 160-sample start limit gives base-43+B > n_recv_final always.
    parameter int BUF_AW  = 8,
    parameter int WIN_LEN = 43844,
    parameter bit USE_DDR_COEFF = 1'b0
) (
    input  logic               clk_i,
    input  logic               rst_ni,
    input  logic               next_window_i,
    input  logic               sample_valid_i,
    input  logic signed [15:0] left_i,
    input  logic signed [15:0] right_i,
    output logic               res_valid_o,
    output logic signed [15:0] res_q_o,
    output logic               win_we_o,
    output logic [15:0]        win_addr_o,
    output logic signed [15:0] win_data_o,
    output logic               win_full_o,
    output logic               in_ready_o,   // source backpressure
    output logic               drained_o,
    output logic [13:0]        coeff_addr_o,
    input  logic signed [31:0] coeff_data_i,
    output logic               coeff_req_o,
    input  logic               coeff_valid_i
);
    localparam int WIN_AW = $clog2(WIN_LEN);

    (* ram_style = "block" *) logic signed [15:0] dline [0:(1<<BUF_AW)-1];
    logic [BUF_AW-1:0]  wr_ptr;
    // Register the one-hot write decode before driving the 256x16 delay line.
    // Keep the small decode registers so synthesis cannot fold the high-fanout
    // address path back into each data bit. No new storage array is introduced.
    (* syn_keep = 1, syn_romstyle = "logic" *) logic [(1<<BUF_AW)-1:0] dline_we_q;
    logic signed [15:0] dline_data_q;
    (* syn_keep = 1 *) logic dline_valid_q;
    logic [31:0]        n_recv;
    logic [16:0]        out_cnt;
    logic [31:0]        base_val;
    logic [13:0]        phase;
    logic [7:0]         tap_cnt;
    logic signed [47:0] acc;
    logic signed [47:0] tap_product_q;
    logic               busy;
    logic               tap_wait;
    logic [31:0]        lag;

    assign lag = (n_recv <= base_val) ? 32'd0 : (n_recv - 32'd1 - base_val);
    localparam int TAPS_C = TAPS;
    assign coeff_addr_o = phase * TAPS_C[13:0] + tap_cnt[6:0];
    assign coeff_req_o = USE_DDR_COEFF && busy && tap_wait;
    // absolute sample index (base - tap) maps to a stable circular-buffer slot,
    // so the read address does not move while a tap chain is accumulating
    wire [BUF_AW-1:0] rd_idx = base_val[BUF_AW-1:0] - tap_cnt[BUF_AW-1:0];
    assign in_ready_o = !win_full_o && (lag < 32'd160);
    assign drained_o = !busy && (base_val >= n_recv);
    wire sample_ready = !win_full_o && (base_val < n_recv) && (lag < 32'd160);
    wire tap_in_range = (base_val >= {24'd0, tap_cnt});

    // >>15 removes the Q15 coefficient scale; saturate to Q1.15
    // The emitted sample must include the tap presented in the same cycle:
    // `acc` is registered and does not yet contain it, so accumulate
    // combinationally before requantizing.
    wire signed [47:0] kx_f = $signed({{32{dline[rd_idx][15]}}, dline[rd_idx]});
    // out-of-range taps read slots that were never written, so they must not
    // contribute (they also must not propagate X)
    wire signed [47:0] tap_product = tap_in_range ? ($signed(coeff_data_i) * kx_f) : 48'sd0;
    // DDR coefficients are stable when coeff_valid_i is observed. Reuse
    // the existing coefficient-wait beat to register the multiply, without
    // inserting a tap/output cycle. Local synchronous ROM retains its read
    // latency and original arithmetic path.
    wire signed [47:0] add_f = USE_DDR_COEFF ? tap_product_q : tap_product;
    wire signed [47:0] acc_f = acc + add_f;
    wire signed [24:0] sh = acc_f[39:15];
    wire signed [15:0] sat_q = (sh > 25'sd32767)  ? 16'sd32767 :
                               (sh < -25'sd32768) ? -16'sd32768 : sh[15:0];

    // Advance floor((m*DOWN+DELAY)/PHASES) without synthesizing a divider.
    // DOWN = DOWN_QUOT*PHASES + DOWN_REM, so each output advances the
    // integer base by DOWN_QUOT plus one only when the phase wraps.
    localparam integer DOWN_QUOT = DOWN / PHASES;
    localparam integer DOWN_REM  = DOWN % PHASES;
    wire [14:0] phase_sum = {1'b0, phase} + DOWN_REM;
    wire phase_wrap = phase_sum >= PHASES;
    wire [31:0] base_next = base_val + DOWN_QUOT + phase_wrap;
    wire [13:0] phase_next = phase_wrap ? phase_sum - PHASES : phase_sum[13:0];

    // 17-bit stereo downmix: sign-extend both channels before adding. Writing
    // `(left_i + right_i) >>> 1` evaluates the sum at 16 bits, which overflows
    // for any pair beyond +-16383 and silently corrupts loud audio.
    wire signed [16:0] mono_sum = $signed({left_i[15], left_i}) + $signed({right_i[15], right_i});

    // A queued sample commits on the next edge, including next_window_i: the
    // latter resets only output-window bookkeeping and must preserve PCM history.
    // The first tap is consumed after sample_ready and the coefficient wait,
    // so even the newest sample has committed before the delay line is read.
    for (genvar slot = 0; slot < (1<<BUF_AW); slot = slot + 1) begin : g_dline_write
        always_ff @(posedge clk_i) begin
            if (rst_ni && dline_valid_q && dline_we_q[slot]) dline[slot] <= dline_data_q;
        end
    end
    always_ff @(posedge clk_i or negedge rst_ni) begin
        if (!rst_ni) begin
            dline_we_q <= '0;
            dline_data_q <= '0; dline_valid_q <= 1'b0;
        end else begin
            // Validity ends at one scalar FF rather than passing through
            // all 256 address decoders. Data/address/valid still queue the
            // same sample on the same beat and commit on the next edge.
            dline_valid_q <= !next_window_i && sample_valid_i;
            for (integer slot = 0; slot < (1<<BUF_AW); slot = slot + 1)
                dline_we_q[slot] <= (wr_ptr == slot);
            if (!next_window_i && sample_valid_i)
                dline_data_q <= mono_sum[16:1];
        end
    end

    always_ff @(posedge clk_i or negedge rst_ni) begin
        if (!rst_ni) begin
            wr_ptr <= '0; n_recv <= '0; out_cnt <= '0;
            base_val <= DELAY/PHASES; phase <= DELAY%PHASES; tap_cnt <= '0;
            acc <= '0; tap_product_q <= '0; busy <= 1'b0; tap_wait <= 1'b0;
            res_valid_o <= 1'b0; win_we_o <= 1'b0; win_full_o <= 1'b0;
            win_addr_o <= '0; win_data_o <= '0; res_q_o <= '0;
        end else if (next_window_i) begin
            // Preserve the delay line, input count and resampling phase.
            out_cnt <= '0;
            win_full_o <= 1'b0;
            res_valid_o <= 1'b0;
            win_we_o <= 1'b0;
        end else begin
            res_valid_o <= 1'b0;
            win_we_o    <= 1'b0;

            if (sample_valid_i) begin
                // Widen before adding: (l+r) evaluated at 16 bits overflows for
                // any pair beyond +-16383, which silently corrupts loud audio.
                wr_ptr      <= wr_ptr + 1'b1;
                n_recv      <= n_recv + 1'b1;
            end

            if (busy && tap_wait) begin
                if (!USE_DDR_COEFF || coeff_valid_i) begin
                    tap_wait <= 1'b0;
                    if (USE_DDR_COEFF) tap_product_q <= tap_product;
                end
            end else if (busy) begin
                if (tap_in_range)
                    acc <= acc_f;
                if (tap_cnt == TAPS - 1) begin
                    busy        <= 1'b0;
                    tap_wait    <= 1'b0;
                    tap_cnt     <= '0;
                    base_val    <= base_next;
                    phase       <= phase_next;
                    res_valid_o <= 1'b1;
                    res_q_o     <= sat_q;
                    win_we_o    <= 1'b1;
                    win_addr_o  <= out_cnt[WIN_AW-1:0];
                    win_data_o  <= sat_q;
                    out_cnt     <= out_cnt + 1'b1;
                    if (out_cnt == WIN_LEN - 1) win_full_o <= 1'b1;
                end else begin
                    tap_cnt <= tap_cnt + 1'b1;
                    tap_wait <= 1'b1;
                end
            end else if (sample_ready) begin
                busy    <= 1'b1;
                tap_wait <= 1'b1;
                tap_cnt <= '0;
                acc     <= '0;
            end
        end
    end
endmodule
