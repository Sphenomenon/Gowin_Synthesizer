`timescale 1ns/1ps
`include "basic_pitch_fixed_pkg.svh"

// Real PCM-to-Basic-Pitch integration boundary.
//
// The first board bring-up uses FRAME_LIMIT=1 so the complete fixed-point
// graph can be observed end to end without waiting for a whole song.  Raising
// FRAME_LIMIT to 172 keeps the same graph and bounded Viterbi interface; the
// storage/layout work is intentionally left for the next pass.
module basic_pitch_pcm_pipeline #(
    parameter integer WIN_LEN       = 43844,
    parameter integer FRAME_LIMIT   = 1,
    parameter integer OCTAVE_LIMIT  = 9,
    parameter integer FRONT_DELAY   = 3200,
    parameter bit USE_EXTERNAL_STATE = 1'b0,
    parameter bit USE_EXTERNAL_PLANE = 1'b0,
    parameter bit USE_EXTERNAL_WEIGHTS = 1'b0,
    parameter bit USE_EXTERNAL_FEATURES = 1'b0,
    parameter bit USE_ALL_DDR = 1'b0,
    parameter bit USE_DDR_SIGNAL = USE_ALL_DDR,
    parameter bit USE_DDR_FRONT_COEFF = USE_ALL_DDR,
    parameter bit USE_DDR_CQT_COEFF = USE_ALL_DDR
) (
    input  logic               clk_i,
    input  logic               rst_ni,
    input  logic               analysis_restart_i,
    input  logic               model_serial_i,
    output logic [3:0]         model_status_o,
    output logic [31:0]        debug_model_expected_crc_o,
    output logic [31:0]        debug_model_actual_crc_o,
    output logic [1:0]         debug_model_error_stage_o,
    input  logic               pcm_valid_i,
    input  logic               pcm_end_i,
    output logic               pcm_ready_o,
    input  logic signed [15:0] pcm_left_i,
    input  logic signed [15:0] pcm_right_i,
    output logic               result_valid_o,
    output logic [6:0]         result_note_o,
    output logic [15:0]        result_conf_o,
    output logic [15:0]        result_frame_o,
    output logic               score_valid_o,
    input  logic               score_ready_i,
    output logic [6:0]         score_note_o,
    output logic [15:0]        debug_onset_o,
    output logic [15:0]        debug_progress_o,
    output logic [15:0]        debug_dwell_o,
    output logic [8:0]         debug_stream_wave_o,
    output logic [191:0]       debug_layer_hashes_o,
    output logic               busy_o,
    output logic               done_o,
    output logic               song_done_o,
    output logic               mem_req_o,
    output logic               mem_write_o,
    output logic [31:0]        mem_byte_addr_o,
    output logic [15:0]        mem_wdata_o,
    input  logic               mem_ready_i,
    input  logic               mem_rsp_valid_i,
    input  logic [15:0]        mem_rdata_i
);
    wire run_rst_ni = rst_ni && !analysis_restart_i;
    localparam integer CQT_BINS = 309;
    localparam integer NOTE_BINS = 88;
    localparam integer CONTOUR_BINS = 264;
    localparam integer CONTOUR_RING_ROWS = 5;
    localparam integer REDUCE_RING_ROWS = 7;
    localparam integer NOTES_RING_ROWS = 7;
    localparam integer NOTE_OUT_RING_ROWS = 3;
    localparam integer ONSET_RING_ROWS = 3;
    localparam integer ONSET_OUT_RING_ROWS = 1;
    localparam integer CONTOUR_N = CONTOUR_RING_ROWS * CONTOUR_BINS * 8;
    localparam integer REDUCE_N = REDUCE_RING_ROWS * CONTOUR_BINS;
    localparam integer NOTES_N = NOTES_RING_ROWS * NOTE_BINS * 32;
    localparam integer NOTE_OUT_N = NOTE_OUT_RING_ROWS * NOTE_BINS;
    localparam integer ONSET_N = ONSET_RING_ROWS * NOTE_BINS * 32;
    localparam integer ONSET_OUT_N = ONSET_OUT_RING_ROWS * NOTE_BINS;
    localparam logic [8:0] FRAME_COUNT = FRAME_LIMIT[8:0];

    localparam logic [5:0] S_CAPTURE = 6'd0, S_START_CQT = 6'd1,
        S_CQT = 6'd2, S_START_NORM = 6'd3, S_NORM = 6'd4,
        S_START_CONTOUR = 6'd5, S_CONTOUR = 6'd6, S_START_REDUCE = 6'd7,
        S_REDUCE = 6'd8, S_START_NOTES = 6'd9, S_NOTES = 6'd10,
        S_START_NOTE_OUT = 6'd11, S_NOTE_OUT = 6'd12,
        S_START_ONSET = 6'd13, S_ONSET = 6'd14,
        S_START_ONSET_OUT = 6'd15, S_ONSET_OUT = 6'd16,
        S_SETTLE = 6'd17, S_START_DP = 6'd18, S_DP = 6'd19,
        S_WAIT_RESULT = 6'd20, S_HOLD = 6'd21,
        S_STREAM_DISPATCH = 6'd22, S_AFTER_CONTOUR = 6'd23,
        S_AFTER_REDUCE = 6'd24, S_AFTER_NOTES = 6'd25,
        S_AFTER_NOTE_OUT = 6'd26, S_AFTER_ONSET = 6'd27,
        S_STREAM_FEED = 6'd28, S_STREAM_NEXT = 6'd29,
        S_CACHE = 6'd30, S_WAIT_CACHE = 6'd31,
        S_PREP_CONTOUR = 6'd32, S_PREP_REDUCE = 6'd33,
        S_PREP_NOTES = 6'd34, S_PREP_NOTE_OUT = 6'd35,
        S_PREP_ONSET = 6'd36, S_PREP_ONSET_OUT = 6'd37,
        S_LOAD_WEIGHT = 6'd38, S_WAIT_WEIGHT = 6'd39,
        S_FEATURE_CACHE = 6'd40, S_WAIT_FEATURE = 6'd41,
        S_READY_NOTE_OUT = 6'd42, S_READY_ONSET_OUT = 6'd43,
        S_READY_REDUCE = 6'd44;
    localparam logic [5:0] S_SCORE_DRAIN = 6'd45,
                           S_WINDOW_RESTART = 6'd46;

    logic [5:0] state, settle_target, cache_target, weight_target, feature_target;
    logic [2:0] settle_count;
    logic [8:0] dp_frame;
    logic [7:0] dp_idx;
    logic dp_have_bins;
    logic cnn_frame_ready;
    logic [8:0] stream_wave;
    logic [3:0] nn_status;
    logic [31:0] layer_hash [0:5];
    assign debug_layer_hashes_o = {layer_hash[5],layer_hash[4],layer_hash[3],
                                   layer_hash[2],layer_hash[1],layer_hash[0]};
    function automatic [31:0] hash_step(input logic [31:0] old_hash,
                                         input logic [15:0] value,
                                         input logic [8:0] row, col, channel);
        logic [31:0] mixed;
        begin
            mixed = old_hash + {16'd0,value} + {7'd0,row,col,channel};
            mixed = mixed + (mixed << 10);
            hash_step = mixed ^ (mixed >> 6);
        end
    endfunction
    always_ff @(posedge clk_i or negedge run_rst_ni) begin
        if (!run_rst_ni) begin
            for (integer i=0;i<6;i=i+1) layer_hash[i] <= 16'd0;
        end else begin
            if (contour_act_valid) layer_hash[0] <= hash_step(layer_hash[0],contour_act_y,contour_row_d2,contour_col_d2,contour_ch_d2);
            if (reduce_act_valid) layer_hash[1] <= hash_step(layer_hash[1],reduce_act_y,reduce_row_d2,reduce_col_d2,0);
            if (notes_act_valid) layer_hash[2] <= hash_step(layer_hash[2],notes_act_y,notes_row_d2,notes_col_d2,notes_ch_d2);
            if (note_out_act_valid) layer_hash[3] <= hash_step(layer_hash[3],note_out_act_y,note_out_row_d2,note_out_col_d2,0);
            if (onset_act_valid) layer_hash[4] <= hash_step(layer_hash[4],onset_act_y,onset_row_d2,onset_col_d2,onset_ch_d2);
            if (onset_out_act_valid) layer_hash[5] <= hash_step(layer_hash[5],onset_out_act_y,onset_out_row_d2,onset_out_col_d2,0);
        end
    end
    assign debug_progress_o = {state, nn_status, nn_idle, read_outstanding,
                               (|nn_sample_req), (|nn_bias_req), nn_feed_valid,
                               nn_mem_req};
    assign debug_stream_wave_o = stream_wave;

    // ------------------------------------------------------------------
    // Per-state dwell telemetry for the B138 NN word.  Eight 25-bit cycle
    // counters bucket the FSM states; a 25M-cycle divider matched to the
    // 0.5 s report tick latches the just-finished window totals and advances
    // the reported page.  debug_dwell_o = {page[1:0], cycles[24:11]} keeps
    // debug_progress_o (and its FSM-state decode) untouched.
    // ------------------------------------------------------------------
    logic [1:0]  dwell_page;
    logic [24:0] dwell_div;
    logic [24:0] dwell_count [0:7];
    logic [24:0] dwell_snap  [0:7];
    function automatic [2:0] dwell_bucket(input logic [5:0] s);
        case (s)
            S_START_CQT, S_CQT: dwell_bucket = 3'd0;
            S_START_NORM, S_NORM, S_CACHE, S_WAIT_CACHE: dwell_bucket = 3'd1;
            S_PREP_CONTOUR, S_START_CONTOUR, S_CONTOUR, S_AFTER_CONTOUR:
                dwell_bucket = 3'd2;
            S_PREP_REDUCE, S_READY_REDUCE, S_START_REDUCE, S_REDUCE,
            S_AFTER_REDUCE, S_PREP_NOTES, S_START_NOTES, S_NOTES, S_AFTER_NOTES:
                dwell_bucket = 3'd3;
            S_PREP_NOTE_OUT, S_READY_NOTE_OUT, S_START_NOTE_OUT, S_NOTE_OUT,
            S_AFTER_NOTE_OUT, S_PREP_ONSET, S_START_ONSET, S_ONSET, S_AFTER_ONSET:
                dwell_bucket = 3'd4;
            S_PREP_ONSET_OUT, S_READY_ONSET_OUT, S_START_ONSET_OUT, S_ONSET_OUT,
            S_STREAM_DISPATCH, S_STREAM_FEED, S_STREAM_NEXT, S_SETTLE:
                dwell_bucket = 3'd5;
            S_START_DP, S_DP, S_WAIT_RESULT, S_SCORE_DRAIN: dwell_bucket = 3'd6;
            default: dwell_bucket = 3'd7;
        endcase
    endfunction
    always_ff @(posedge clk_i or negedge run_rst_ni) begin
        if (!run_rst_ni) begin
            dwell_page <= 2'd0; dwell_div <= 25'd0;
            for (integer i=0;i<8;i=i+1) begin
                dwell_count[i] <= 25'd0; dwell_snap[i] <= 25'd0;
            end
        end else if (dwell_div == 25'd24_999_999) begin
            dwell_div <= 25'd0;
            dwell_page <= dwell_page + 1'b1;
            for (integer i=0;i<8;i=i+1) begin
                dwell_snap[i] <= dwell_count[i];
                dwell_count[i] <= 25'd0;
            end
        end else begin
            dwell_div <= dwell_div + 1'b1;
            dwell_count[dwell_bucket(state)] <= dwell_count[dwell_bucket(state)] + 1'b1;
        end
    end
    assign debug_dwell_o = {dwell_page, dwell_snap[dwell_page][24:11]};

    // ------------------------------------------------------------------
    // PCM resampler and analysis window
    // ------------------------------------------------------------------
    logic front_res_valid, front_win_we, front_win_full, front_ready, front_drained;
    logic front_window_started;
    wire pad_sample = pcm_end_i && front_window_started && !pcm_valid_i;
    logic signed [15:0] front_res_q, front_win_data;
    logic [15:0] front_win_addr;
    logic [13:0] front_coeff_addr;
    logic signed [31:0] front_coeff_data;
    logic front_coeff_req, front_coeff_valid;
    logic front_coeff_mem_req, front_coeff_mem_ready, front_coeff_mem_rsp_valid;
    logic [31:0] front_coeff_mem_addr;
    generate if (USE_DDR_FRONT_COEFF) begin : g_front_coeff_ddr
        logic [15:0] lo, hi;
        basic_pitch_ddr_coeff_pair #(.FIRST_WORD(20871), .SECOND_WORD(20872),
            .STRIDE(2)) u_coeff (
            .clk_i(clk_i), .rst_ni(run_rst_ni), .req_i(front_coeff_req),
            .index_i(front_coeff_addr), .valid_o(front_coeff_valid),
            .first_o(lo), .second_o(hi),
            .mem_req_o(front_coeff_mem_req), .mem_addr_o(front_coeff_mem_addr),
            .mem_ready_i(front_coeff_mem_ready),
            .mem_rsp_valid_i(front_coeff_mem_rsp_valid), .mem_rdata_i(mem_rdata_i));
        assign front_coeff_data = {hi,lo};
    end else begin : g_front_coeff_rom
        (* ram_style = "block", syn_ramstyle = "block_ram" *)
        logic signed [31:0] res_coeff [0:147*44-1];
        initial $readmemh("rtl/music/weights/resampler_poly.mem", res_coeff);
        always_ff @(posedge clk_i) front_coeff_data <= res_coeff[front_coeff_addr];
        assign front_coeff_valid = 1'b1;
        assign front_coeff_mem_req = 1'b0;
        assign front_coeff_mem_addr = 32'd0;
    end endgenerate

    // The UART model upload may take seconds. Hold the decoder before the
    // first sample until DDR is ready, then freeze the completed window so a
    // delayed CNN start cannot wrap and overwrite its PCM input.
    assign pcm_ready_o = (state == S_CAPTURE) && front_ready &&
                        (!USE_ALL_DDR || (model_done && !front_win_full));
    basic_pitch_cqt_frontend #(.WIN_LEN(WIN_LEN), .DELAY(FRONT_DELAY),
        .USE_DDR_COEFF(USE_DDR_FRONT_COEFF)) u_frontend (
        .clk_i(clk_i), .rst_ni(run_rst_ni),
        .next_window_i(state == S_WINDOW_RESTART),
        .sample_valid_i((pcm_valid_i || pad_sample) && pcm_ready_o),
        .left_i(pcm_valid_i ? pcm_left_i : 16'sd0),
        .right_i(pcm_valid_i ? pcm_right_i : 16'sd0),
        .res_valid_o(front_res_valid), .res_q_o(front_res_q),
        .win_we_o(front_win_we), .win_addr_o(front_win_addr),
        .win_data_o(front_win_data), .win_full_o(front_win_full),
        .in_ready_o(front_ready), .drained_o(front_drained),
        .coeff_addr_o(front_coeff_addr),
        .coeff_data_i(front_coeff_data), .coeff_req_o(front_coeff_req),
        .coeff_valid_i(front_coeff_valid)
    );

    // ------------------------------------------------------------------
    // CQT and NormalizedLog
    // ------------------------------------------------------------------
    logic [4:0] cqt_octave_limit;
    logic [8:0] cqt_frame_limit;
    logic cqt_done, cqt_busy, cqt_mag_we;
    logic [13:0] cqt_re_addr, cqt_im_addr;
    logic [7:0] cqt_lp_addr;
    logic [8:0] cqt_norm_addr, cqt_log_addr;
    logic [15:0] cqt_mag_addr;
    logic signed [15:0] cqt_re_data, cqt_im_data, cqt_lp_data;
    logic signed [15:0] cqt_norm_log_data, cqt_log_data, cqt_mag_data;
    logic sig_mem_req, sig_mem_write, sig_mem_ready, sig_mem_rsp_valid;
    logic [31:0] sig_mem_addr;
    logic [15:0] sig_mem_wdata;
    logic sig_overflow;
    logic cqt_coeff_req, cqt_coeff_valid;
    logic cqt_coeff_mem_req, cqt_coeff_mem_ready, cqt_coeff_mem_rsp_valid;
    logic [31:0] cqt_coeff_mem_addr;
    generate if (USE_DDR_CQT_COEFF) begin : g_cqt_coeff_ddr
        basic_pitch_ddr_coeff_pair #(.FIRST_WORD(33807), .SECOND_WORD(43023),
            .STRIDE(1)) u_coeff (
            .clk_i(clk_i), .rst_ni(run_rst_ni), .req_i(cqt_coeff_req),
            .index_i(cqt_re_addr), .valid_o(cqt_coeff_valid),
            .first_o(cqt_re_data), .second_o(cqt_im_data),
            .mem_req_o(cqt_coeff_mem_req), .mem_addr_o(cqt_coeff_mem_addr),
            .mem_ready_i(cqt_coeff_mem_ready),
            .mem_rsp_valid_i(cqt_coeff_mem_rsp_valid), .mem_rdata_i(mem_rdata_i));
    end else begin : g_cqt_coeff_rom
        (* ram_style = "block", syn_ramstyle = "block_ram" *)
        logic signed [15:0] cqt_real_rom [0:36*256-1];
        (* ram_style = "block", syn_ramstyle = "block_ram" *)
        logic signed [15:0] cqt_imag_rom [0:36*256-1];
        initial begin
            $readmemh("rtl/music/weights/cqt_real.mem", cqt_real_rom);
            $readmemh("rtl/music/weights/cqt_imag.mem", cqt_imag_rom);
        end
        always_ff @(posedge clk_i) begin
            cqt_re_data <= cqt_real_rom[cqt_re_addr];
            cqt_im_data <= cqt_imag_rom[cqt_im_addr];
        end
        assign cqt_coeff_valid = 1'b1;
        assign cqt_coeff_mem_req = 1'b0;
        assign cqt_coeff_mem_addr = 32'd0;
    end endgenerate
    logic signed [15:0] cqt_lp_rom [0:255];
    logic signed [15:0] cqt_norm_log_rom [0:CQT_BINS-1];
    logic signed [15:0] log_lut_rom [0:255];
    initial begin
        $readmemh("rtl/music/weights/cqt_lowpass.mem", cqt_lp_rom);
        $readmemh("rtl/music/weights/cqt_norm_log.mem", cqt_norm_log_rom);
        $readmemh("rtl/music/weights/log2_lut.mem", log_lut_rom);
    end
    assign cqt_lp_data = cqt_lp_rom[cqt_lp_addr];
    assign cqt_norm_log_data = cqt_norm_log_rom[cqt_norm_addr];
    assign cqt_log_data = log_lut_rom[cqt_log_addr];

    basic_pitch_cqt_engine #(.WIN_LEN(WIN_LEN), .CQT_BINS(CQT_BINS),
        .USE_DDR_SIGNAL(USE_DDR_SIGNAL), .USE_DDR_COEFF(USE_DDR_CQT_COEFF)) u_cqt (
        .clk_i(clk_i), .rst_ni(run_rst_ni), .start_i(state == S_START_CQT),
        .octave_limit_i(OCTAVE_LIMIT[4:0]), .frame_limit_i(FRAME_COUNT),
        .win_we_i(front_win_we), .win_addr_i(front_win_addr), .win_data_i(front_win_data),
        .win_ready_o(), .kre_addr_o(cqt_re_addr), .kre_data_i(cqt_re_data),
        .kim_addr_o(cqt_im_addr), .kim_data_i(cqt_im_data),
        .coeff_req_o(cqt_coeff_req), .coeff_valid_i(cqt_coeff_valid),
        .klp_addr_o(cqt_lp_addr), .klp_data_i(cqt_lp_data),
        .norm_addr_o(cqt_norm_addr), .norm_log_data_i(cqt_norm_log_data),
        .loglut_addr_o(cqt_log_addr), .loglut_data_i(cqt_log_data),
        .mag_we_o(cqt_mag_we), .mag_addr_o(cqt_mag_addr), .mag_data_o(cqt_mag_data),
        .busy_o(cqt_busy), .done_o(cqt_done),
        .sig_mem_req_o(sig_mem_req), .sig_mem_write_o(sig_mem_write),
        .sig_mem_addr_o(sig_mem_addr), .sig_mem_wdata_o(sig_mem_wdata),
        .sig_mem_ready_i(sig_mem_ready), .sig_mem_rsp_valid_i(sig_mem_rsp_valid),
        .sig_mem_rdata_i(mem_rdata_i), .sig_overflow_o(sig_overflow)
    );

    logic norm_done, norm_busy;
    logic norm_rd_re;
    logic [15:0] norm_rd_addr;
    logic [15:0] norm_feature_rd_addr;
    logic signed [15:0] norm_feature_rd_data;
    logic norm_mem_req, norm_mem_write, norm_mem_ready, norm_mem_rsp_valid;
    logic [31:0] norm_mem_addr;
    logic [15:0] norm_mem_wdata;
    logic norm_overflow;
    logic cache_done, cache_busy;
    logic cache_mem_req, cache_mem_write, cache_mem_ready, cache_mem_rsp_valid;
    logic [31:0] cache_mem_addr;
    logic [15:0] cache_mem_wdata;
    logic [8:0] cache_center;
    logic signed [15:0] bn_scale_q = 16'sd10161;
    logic signed [15:0] bn_offset_q = -16'sd3592;
    generate
        if (USE_EXTERNAL_PLANE) begin : g_ddr_plane
            assign norm_rd_re = 1'b0;
            assign norm_rd_addr = 16'd0;
            basic_pitch_normlog_ddr #(.FRAMES(FRAME_LIMIT), .BINS(CQT_BINS)) u_normlog_ddr (
                .clk_i(clk_i), .rst_ni(run_rst_ni), .start_i(state == S_START_NORM),
                .we_i(cqt_mag_we), .waddr_i(cqt_mag_addr), .wdata_i(cqt_mag_data),
                .bn_scale_q(bn_scale_q), .bn_offset_q(bn_offset_q),
                .busy_o(norm_busy), .done_o(norm_done), .overflow_o(norm_overflow),
                .mem_req_o(norm_mem_req), .mem_write_o(norm_mem_write),
                .mem_byte_addr_o(norm_mem_addr), .mem_wdata_o(norm_mem_wdata),
                .mem_ready_i(norm_mem_ready), .mem_rsp_valid_i(norm_mem_rsp_valid),
                .mem_rdata_i(mem_rdata_i));
            if (USE_ALL_DDR) begin : g_no_plane_cache
                assign norm_feature_rd_data = 16'sd0;
                assign cache_busy = 1'b0;
                assign cache_done = 1'b0;
                assign cache_mem_req = 1'b0;
                assign cache_mem_write = 1'b0;
                assign cache_mem_addr = 32'd0;
                assign cache_mem_wdata = 16'd0;
            end else begin : g_plane_cache
            basic_pitch_plane_cache #(.FRAMES(FRAME_LIMIT), .BINS(CQT_BINS)) u_plane_cache (
                .clk_i(clk_i), .rst_ni(run_rst_ni), .start_i(state == S_CACHE),
                .center_row_i(cache_center), .feature_addr_i(norm_feature_rd_addr),
                .feature_data_o(norm_feature_rd_data), .busy_o(cache_busy), .done_o(cache_done),
                .mem_req_o(cache_mem_req), .mem_write_o(cache_mem_write),
                .mem_byte_addr_o(cache_mem_addr), .mem_wdata_o(cache_mem_wdata),
                .mem_ready_i(cache_mem_ready), .mem_rsp_valid_i(cache_mem_rsp_valid),
                .mem_rdata_i(mem_rdata_i));
            end
        end else begin : g_bsram_plane
            basic_pitch_normlog #(.FRAMES(FRAME_LIMIT), .BINS(CQT_BINS),
                                   .USE_INTERNAL_READ(1'b1)) u_normlog (
                .clk_i(clk_i), .rst_ni(run_rst_ni), .start_i(state == S_START_NORM),
                .we_i(cqt_mag_we), .waddr_i(cqt_mag_addr), .wdata_i(cqt_mag_data),
                .bn_scale_q(bn_scale_q), .bn_offset_q(bn_offset_q),
                .rd_re_o(norm_rd_re), .rd_addr_o(norm_rd_addr), .rd_data_i(16'sd0),
                .feature_rd_addr_i(norm_feature_rd_addr), .feature_rd_data_o(norm_feature_rd_data),
                .busy_o(norm_busy), .done_o(norm_done));
            assign norm_overflow = 1'b0;
            assign norm_mem_req = 1'b0;
            assign norm_mem_write = 1'b0;
            assign norm_mem_addr = 32'd0;
            assign norm_mem_wdata = 16'd0;
            assign cache_done = 1'b0;
            assign cache_busy = 1'b0;
            assign cache_mem_req = 1'b0;
            assign cache_mem_write = 1'b0;
            assign cache_mem_addr = 32'd0;
            assign cache_mem_wdata = 16'd0;
        end
    endgenerate

    // ------------------------------------------------------------------
    // Official fixed-point head weights and feature memories
    // ------------------------------------------------------------------
    (* ram_style = "block" *) logic signed [15:0] contour_mem [0:CONTOUR_N-1];
    (* ram_style = "block" *) logic signed [15:0] reduce_mem [0:REDUCE_N-1];
    (* ram_style = "block" *) logic signed [15:0] notes_mem [0:NOTES_N-1];
    (* ram_style = "block" *) logic signed [15:0] note_post_mem [0:NOTE_OUT_N-1];
    (* ram_style = "block" *) logic signed [15:0] onset_mem [0:ONSET_N-1];
    (* ram_style = "block" *) logic signed [15:0] onset_post_mem [0:ONSET_OUT_N-1];

    logic signed [31:0] contour_b [0:7];
    logic signed [31:0] reduce_b [0:0];
    logic signed [31:0] notes_b [0:31];
    logic signed [31:0] note_out_b [0:0];
    logic signed [31:0] onset_b [0:31];
    logic signed [31:0] onset_out_b [0:0];
    initial begin
        $readmemh("rtl/music/weights/contour_bq.mem", contour_b);
        $readmemh("rtl/music/weights/contour_reduce_bq.mem", reduce_b);
        $readmemh("rtl/music/weights/notes_bq.mem", notes_b);
        $readmemh("rtl/music/weights/note_out_bq.mem", note_out_b);
        $readmemh("rtl/music/weights/onset_bq.mem", onset_b);
        $readmemh("rtl/music/weights/onset_out_bq.mem", onset_out_b);
    end

    // Contour: stacked CQT plane -> 8-channel feature map.
    logic [15:0] contour_pl_addr; logic signed [15:0] contour_pl_data;
    logic [23:0] contour_x_addr; logic signed [15:0] contour_x_data;
    logic [17:0] contour_w_addr; logic [23:0] contour_y_addr; logic [8:0] contour_b_addr;
    logic [8:0] contour_y_row, contour_y_col, contour_y_channel;
    logic signed [15:0] contour_w_data, contour_y_data; logic signed [31:0] contour_b_data;
    logic contour_y_we, contour_done; logic signed [47:0] contour_y_acc;
    always_comb begin
        contour_pl_data = USE_ALL_DDR ? nn_sample_x :
                          ((contour_pl_addr < FRAME_LIMIT*CQT_BINS) ?
                           norm_feature_rd_data : 16'sd0);
        contour_x_data = (contour_x_addr < CONTOUR_N) ? contour_mem[contour_x_addr] : 16'sd0;
    end
    wire [8:0] contour_run_row = (FRAME_LIMIT > 1) ? stream_wave : 9'd0;
    wire [8:0] reduce_run_row = (FRAME_LIMIT > 1) ? stream_wave - 9'd2 : 9'd0;
    wire [8:0] notes_run_row = (FRAME_LIMIT > 1) ? stream_wave - 9'd5 : 9'd0;
    wire [8:0] note_out_run_row = (FRAME_LIMIT > 1) ? stream_wave - 9'd8 : 9'd0;
    wire [8:0] onset_run_row = note_out_run_row;
    wire [8:0] onset_out_run_row = (FRAME_LIMIT > 1) ? stream_wave - 9'd9 : 9'd0;
    assign contour_b_data = USE_ALL_DDR ? nn_bias : contour_b[contour_b_addr];
    basic_pitch_conv2d #(.IN_T(FRAME_LIMIT), .IN_F(CONTOUR_BINS), .IN_C(8),
        .KH(3), .KW(39), .OUT_T(FRAME_LIMIT), .OUT_F(CONTOUR_BINS), .OUT_C(8),
        .STRIDE_T(1), .STRIDE_F(1), .PAD_T(1), .PAD_F(19), .USE_STACK(1), .ACT(1),
        .DDR_FETCH(USE_ALL_DDR)) u_contour (
        .clk_i(clk_i), .rst_ni(run_rst_ni), .start_i(state == S_START_CONTOUR),
        .row_start_i(contour_run_row),
        .row_limit_i((FRAME_LIMIT > 1) ? contour_run_row + 9'd1 : FRAME_COUNT),
        .pl_addr_o(contour_pl_addr), .pl_data_i(contour_pl_data),
        .x_addr_o(contour_x_addr), .x_row_o(), .x_col_o(), .x_data_i(contour_x_data),
        .w_addr_o(contour_w_addr), .w_data_i(contour_w_data),
        .input_in_range_o(nn_input_range[0]), .sample_req_o(nn_sample_req[0]),
        .sample_valid_i(nn_sample_valid),
        .b_addr_o(contour_b_addr), .b_data_i(contour_b_data),
        .bias_req_o(nn_bias_req[0]), .bias_valid_i(nn_bias_valid),
        .y_we_o(contour_y_we), .y_addr_o(contour_y_addr), .y_data_o(contour_y_data),
        .y_row_o(contour_y_row), .y_col_o(contour_y_col), .y_channel_o(contour_y_channel),
        .y_acc_o(contour_y_acc), .busy_o(), .done_o(contour_done)
    );
    logic contour_act_valid; logic [15:0] contour_act_y;
    basic_pitch_activation #(.MUL(17119), .SHIFT(32), .ACT(1)) u_contour_act (
        .clk_i(clk_i), .rst_ni(run_rst_ni), .valid_i(contour_y_we), .acc_i(contour_y_acc),
        .valid_o(contour_act_valid), .y_o(contour_act_y), .sat_o(), .arg_dbg_o()
    );

    // Reusable address/data declarations for the five remaining heads.
    logic [23:0] reduce_x_addr, notes_x_addr, note_out_x_addr, onset_x_addr, onset_out_x_addr;
    logic [23:0] onset_out_cell_addr;
    logic [7:0] onset_out_channel;
    logic [7:0] reduce_x_channel, notes_x_channel, note_out_x_channel;
    logic signed [17:0] reduce_x_row, reduce_x_col, notes_x_row, notes_x_col;
    logic signed [17:0] note_out_x_row, note_out_x_col, onset_out_x_row, onset_out_x_col;
    logic signed [15:0] reduce_x_data, notes_x_data, note_out_x_data, onset_x_data, onset_out_x_data;
    logic [17:0] reduce_w_addr, notes_w_addr, note_out_w_addr, onset_w_addr, onset_out_w_addr;
    logic [23:0] reduce_y_addr, notes_y_addr, note_out_y_addr, onset_y_addr, onset_out_y_addr;
    logic [8:0] reduce_y_row, reduce_y_col, reduce_y_channel;
    logic [8:0] notes_y_row, notes_y_col, notes_y_channel;
    logic [8:0] note_out_y_row, note_out_y_col, note_out_y_channel;
    logic [8:0] onset_y_row, onset_y_col, onset_y_channel;
    logic [8:0] onset_out_y_row, onset_out_y_col, onset_out_y_channel;
    logic [8:0] reduce_b_addr, notes_b_addr, note_out_b_addr, onset_b_addr, onset_out_b_addr;
    logic signed [15:0] reduce_w_data, notes_w_data, note_out_w_data, onset_w_data, onset_out_w_data;
    logic signed [31:0] reduce_b_data, notes_b_data, note_out_b_data, onset_b_data, onset_out_b_data;
    logic reduce_y_we, notes_y_we, note_out_y_we, onset_y_we, onset_out_y_we;
    logic reduce_done, notes_done, note_out_done, onset_done, onset_out_done;
    logic signed [47:0] reduce_y_acc, notes_y_acc, note_out_y_acc, onset_y_acc, onset_out_y_acc;
    logic signed [15:0] reduce_y_data, notes_y_data, note_out_y_data, onset_y_data, onset_out_y_data;
    logic reduce_act_valid, notes_act_valid, note_out_act_valid, onset_act_valid, onset_out_act_valid;
    logic [15:0] reduce_act_y, notes_act_y, note_out_act_y, onset_act_y, onset_out_act_y;
    logic [15:0] onset_pl_addr; logic signed [15:0] onset_pl_data;
    logic reduce_act_busy, note_out_act_busy, onset_out_act_busy;
    logic reduce_lut_req, note_out_lut_req, onset_out_lut_req;
    logic [11:0] reduce_lut_addr, note_out_lut_addr, onset_out_lut_addr;
    logic reduce_lut_ready, note_out_lut_ready, onset_out_lut_ready;
    logic lut_mem_req, lut_mem_ready, lut_mem_rsp_valid;
    logic [31:0] lut_mem_addr;
    logic lut_req_merged, lut_backend_ready, lut_backend_rsp_valid;
    logic [11:0] lut_index_merged;
    logic [15:0] lut_backend_rdata;

    logic model_done, model_mem_req, model_mem_write, model_mem_ready;
    logic [31:0] model_mem_addr;
    logic [15:0] model_mem_wdata;
    logic weight_cache_done, weight_cache_busy;
    logic weight_mem_req, weight_mem_ready, weight_mem_rsp_valid;
    logic [31:0] weight_mem_addr;
    logic [15:0] weight_mem_wdata;
    logic [14:0] weight_blob_base;
    logic [13:0] weight_word_count;
    logic [17:0] weight_cache_read_addr;
    logic signed [15:0] weight_cache_read_data;
    logic [5:0] nn_sample_req, nn_input_range, nn_bias_req;
    logic nn_sample_valid, nn_bias_valid, nn_idle, nn_overflow;
    logic signed [15:0] nn_sample_x, nn_sample_w;
    logic signed [31:0] nn_bias;
    logic [2:0] nn_layer, nn_write_layer;
    logic [15:0] nn_plane_addr;
    logic [23:0] nn_x_addr, nn_x_cell_addr;
    logic [7:0] nn_x_channel;
    logic [17:0] nn_weight_addr;
    logic [8:0] nn_bias_addr, nn_write_row, nn_write_col, nn_write_channel;
    logic nn_write_valid, nn_feed_valid;
    logic [15:0] nn_write_data, nn_feed_note, nn_feed_onset;
    logic nn_mem_req, nn_mem_write, nn_mem_ready, nn_mem_rsp_valid;
    logic [31:0] nn_mem_addr;
    logic [15:0] nn_mem_wdata;
    logic model_mem_rsp_valid;

    always_comb begin
        nn_layer = 3'd0;
        case (state)
            S_START_REDUCE, S_REDUCE: nn_layer = 3'd1;
            S_START_NOTES, S_NOTES: nn_layer = 3'd2;
            S_START_NOTE_OUT, S_NOTE_OUT: nn_layer = 3'd3;
            S_START_ONSET, S_ONSET: nn_layer = 3'd4;
            S_START_ONSET_OUT, S_ONSET_OUT: nn_layer = 3'd5;
            default: nn_layer = 3'd0;
        endcase
        nn_plane_addr = (nn_layer == 3'd4) ? onset_pl_addr : contour_pl_addr;
        nn_x_addr = 0;
        nn_x_cell_addr = 0;
        nn_x_channel = 0;
        nn_weight_addr = contour_w_addr;
        nn_bias_addr = contour_b_addr;
        case (nn_layer)
            1: begin nn_x_addr=reduce_x_addr; nn_x_channel=reduce_x_channel;
                nn_weight_addr=reduce_w_addr; nn_bias_addr=reduce_b_addr; end
            2: begin nn_x_addr=notes_x_addr; nn_x_channel=notes_x_channel;
                nn_weight_addr=notes_w_addr; nn_bias_addr=notes_b_addr; end
            3: begin nn_x_addr=note_out_x_addr; nn_x_channel=note_out_x_channel;
                nn_weight_addr=note_out_w_addr; nn_bias_addr=note_out_b_addr; end
            4: begin nn_weight_addr=onset_w_addr; nn_bias_addr=onset_b_addr; end
            5: begin nn_x_addr=onset_out_x_addr; nn_x_cell_addr=onset_out_cell_addr;
                nn_x_channel=onset_out_channel;
                nn_weight_addr=onset_out_w_addr; nn_bias_addr=onset_out_b_addr; end
            default: begin end
        endcase
        nn_write_valid = 1'b0;
        nn_write_layer = 0;
        nn_write_row = 0;
        nn_write_col = 0;
        nn_write_channel = 0;
        nn_write_data = 0;
        if (contour_act_valid) begin
            nn_write_valid=1'b1; nn_write_layer=0;
            nn_write_row=contour_row_d2; nn_write_col=contour_col_d2;
            nn_write_channel=contour_ch_d2; nn_write_data=contour_act_y;
        end else if (reduce_act_valid) begin
            nn_write_valid=1'b1; nn_write_layer=1;
            nn_write_row=reduce_row_d2; nn_write_col=reduce_col_d2;
            nn_write_channel=reduce_ch_d2; nn_write_data=reduce_act_y;
        end else if (notes_act_valid) begin
            nn_write_valid=1'b1; nn_write_layer=2;
            nn_write_row=notes_row_d2; nn_write_col=notes_col_d2;
            nn_write_channel=notes_ch_d2; nn_write_data=notes_act_y;
        end else if (note_out_act_valid) begin
            nn_write_valid=1'b1; nn_write_layer=3;
            nn_write_row=note_out_row_d2; nn_write_col=note_out_col_d2;
            nn_write_channel=note_out_ch_d2; nn_write_data=note_out_act_y;
        end else if (onset_act_valid) begin
            nn_write_valid=1'b1; nn_write_layer=4;
            nn_write_row=onset_row_d2; nn_write_col=onset_col_d2;
            nn_write_channel=onset_ch_d2; nn_write_data=onset_act_y;
        end else if (onset_out_act_valid) begin
            nn_write_valid=1'b1; nn_write_layer=5;
            nn_write_row=onset_out_row_d2; nn_write_col=onset_out_col_d2;
            nn_write_channel=onset_out_ch_d2; nn_write_data=onset_out_act_y;
        end
    end

    logic [1:0] feature_load_kind;
    logic signed [10:0] feature_load_start_row;
    logic [3:0] feature_load_rows;
    logic feature_cache_done, feature_overflow;
    logic feature_mem_req, feature_mem_write, feature_mem_ready, feature_mem_rsp_valid;
    logic [31:0] feature_mem_addr;
    logic [15:0] feature_mem_wdata;
    logic feature_read_valid;
    logic [14:0] feature_read_addr;
    logic signed [15:0] feature_read_data;
    logic signed [11:0] feature_read_rel;
    logic onset_out_use_note_d;
    logic signed [15:0] onset_out_note_data;
    logic [8:0] contour_row_d1, contour_row_d2, contour_col_d1, contour_col_d2,
                contour_ch_d1, contour_ch_d2;
    logic [8:0] reduce_row_d1, reduce_row_d2, reduce_col_d1, reduce_col_d2,
                reduce_ch_d1, reduce_ch_d2;
    logic [8:0] notes_row_d1, notes_row_d2, notes_col_d1, notes_col_d2,
                notes_ch_d1, notes_ch_d2;
    logic [8:0] note_out_row_d1, note_out_row_d2, note_out_col_d1, note_out_col_d2,
                note_out_ch_d1, note_out_ch_d2;
    logic [8:0] onset_row_d1, onset_row_d2, onset_col_d1, onset_col_d2,
                onset_ch_d1, onset_ch_d2;
    logic [8:0] onset_out_row_d1, onset_out_row_d2, onset_out_col_d1, onset_out_col_d2,
                onset_out_ch_d1, onset_out_ch_d2;

    always_comb begin
        case (state)
            S_START_CONTOUR, S_CONTOUR: weight_cache_read_addr = contour_w_addr;
            S_START_REDUCE, S_REDUCE: weight_cache_read_addr = reduce_w_addr;
            S_START_NOTES, S_NOTES: weight_cache_read_addr = notes_w_addr;
            S_START_NOTE_OUT, S_NOTE_OUT: weight_cache_read_addr = note_out_w_addr;
            S_START_ONSET, S_ONSET: weight_cache_read_addr = onset_w_addr;
            default: weight_cache_read_addr = onset_out_w_addr;
        endcase
    end

    generate
        if (USE_ALL_DDR) begin : g_all_ddr_weights
            basic_pitch_uart_model_loader u_model_loader (
                .clk_i(clk_i), .rst_ni(rst_ni), .serial_i(model_serial_i),
                .done_o(model_done), .status_o(model_status_o),
                .debug_expected_crc_o(debug_model_expected_crc_o),
                .debug_actual_crc_o(debug_model_actual_crc_o),
                .debug_error_stage_o(debug_model_error_stage_o),
                .mem_req_o(model_mem_req), .mem_write_o(model_mem_write),
                .mem_byte_addr_o(model_mem_addr), .mem_wdata_o(model_mem_wdata),
                .mem_ready_i(model_mem_ready), .mem_rsp_valid_i(model_mem_rsp_valid),
                .mem_rdata_i(mem_rdata_i));
            assign contour_w_data=nn_sample_w;
            assign reduce_w_data=nn_sample_w;
            assign notes_w_data=nn_sample_w;
            assign note_out_w_data=nn_sample_w;
            assign onset_w_data=nn_sample_w;
            assign onset_out_w_data=nn_sample_w;
            assign weight_cache_done=1'b0;
            assign weight_cache_busy=1'b0;
            assign weight_mem_req=1'b0;
            assign weight_mem_addr=32'd0;
            assign weight_mem_wdata=16'd0;
        end else if (USE_EXTERNAL_WEIGHTS) begin : g_ddr_weights
            // Board flow: the model image arrives over UART (BPN1 + CRC +
            // DDR readback verification), never a bitstream ROM.
            basic_pitch_uart_model_loader u_model_loader (
                .clk_i(clk_i), .rst_ni(rst_ni), .serial_i(model_serial_i),
                .done_o(model_done), .status_o(model_status_o),
                .debug_expected_crc_o(debug_model_expected_crc_o),
                .debug_actual_crc_o(debug_model_actual_crc_o),
                .debug_error_stage_o(debug_model_error_stage_o),
                .mem_req_o(model_mem_req), .mem_write_o(model_mem_write),
                .mem_byte_addr_o(model_mem_addr), .mem_wdata_o(model_mem_wdata),
                .mem_ready_i(model_mem_ready),
                .mem_rsp_valid_i(model_mem_rsp_valid), .mem_rdata_i(mem_rdata_i));
            basic_pitch_weight_cache u_weight_cache (
                .clk_i(clk_i), .rst_ni(run_rst_ni), .start_i(state == S_LOAD_WEIGHT),
                .blob_word_base_i(weight_blob_base), .word_count_i(weight_word_count),
                .read_addr_i(weight_cache_read_addr), .read_data_o(weight_cache_read_data),
                .busy_o(weight_cache_busy), .done_o(weight_cache_done),
                .mem_req_o(weight_mem_req), .mem_write_o(),
                .mem_byte_addr_o(weight_mem_addr), .mem_wdata_o(weight_mem_wdata),
                .mem_ready_i(weight_mem_ready), .mem_rsp_valid_i(weight_mem_rsp_valid),
                .mem_rdata_i(mem_rdata_i));
            assign contour_w_data = weight_cache_read_data;
            assign reduce_w_data = weight_cache_read_data;
            assign notes_w_data = weight_cache_read_data;
            assign note_out_w_data = weight_cache_read_data;
            assign onset_w_data = weight_cache_read_data;
            assign onset_out_w_data = weight_cache_read_data;
        end else begin : g_rom_weights
            assign model_status_o = 4'd14;
            assign debug_model_expected_crc_o=0;
            assign debug_model_actual_crc_o=0;
            assign debug_model_error_stage_o=0;
            (* ram_style = "block", syn_ramstyle = "block_ram" *) logic signed [15:0] contour_w [0:7487];
            (* ram_style = "block", syn_ramstyle = "block_ram" *) logic signed [15:0] reduce_w [0:199];
            (* ram_style = "block", syn_ramstyle = "block_ram" *) logic signed [15:0] notes_w [0:1567];
            (* ram_style = "block", syn_ramstyle = "block_ram" *) logic signed [15:0] note_out_w [0:671];
            (* ram_style = "block", syn_ramstyle = "block_ram" *) logic signed [15:0] onset_w [0:6399];
            (* ram_style = "block", syn_ramstyle = "block_ram" *) logic signed [15:0] onset_out_w [0:296];
            initial begin
                $readmemh("rtl/music/weights/contour.mem", contour_w);
                $readmemh("rtl/music/weights/contour_reduce.mem", reduce_w);
                $readmemh("rtl/music/weights/notes.mem", notes_w);
                $readmemh("rtl/music/weights/note_out.mem", note_out_w);
                $readmemh("rtl/music/weights/onset.mem", onset_w);
                $readmemh("rtl/music/weights/onset_out.mem", onset_out_w);
            end
            always_ff @(posedge clk_i) begin
                contour_w_data <= contour_w[contour_w_addr];
                reduce_w_data <= reduce_w[reduce_w_addr];
                notes_w_data <= notes_w[notes_w_addr];
                note_out_w_data <= note_out_w[note_out_w_addr];
                onset_w_data <= onset_w[onset_w_addr];
                onset_out_w_data <= onset_out_w[onset_out_w_addr];
            end
            assign model_done = 1'b1;
            assign model_mem_req = 1'b0;
            assign model_mem_write = 1'b0;
            assign model_mem_addr = 32'd0;
            assign model_mem_wdata = 16'd0;
            assign weight_cache_done = 1'b0;
            assign weight_cache_busy = 1'b0;
            assign weight_mem_req = 1'b0;
            assign weight_mem_addr = 32'd0;
            assign weight_mem_wdata = 16'd0;
        end
    endgenerate

    generate
        if (USE_ALL_DDR) begin : g_all_ddr_features
            basic_pitch_nn_ddr u_nn_ddr (
                .clk_i(clk_i), .rst_ni(run_rst_ni), .layer_i(nn_layer),
                .sample_req_i(|nn_sample_req),
                .input_in_range_i(nn_input_range[nn_layer]),
                .plane_addr_i(nn_plane_addr), .x_addr_i(nn_x_addr),
                .x_cell_addr_i(nn_x_cell_addr), .x_channel_i(nn_x_channel),
                .weight_addr_i(nn_weight_addr),
                .sample_valid_o(nn_sample_valid), .sample_x_o(nn_sample_x),
                .sample_w_o(nn_sample_w), .bias_req_i(|nn_bias_req),
                .bias_addr_i(nn_bias_addr), .bias_valid_o(nn_bias_valid),
                .bias_o(nn_bias), .write_valid_i(nn_write_valid),
                .write_layer_i(nn_write_layer), .write_row_i(nn_write_row),
                .write_col_i(nn_write_col), .write_channel_i(nn_write_channel),
                .write_data_i(nn_write_data), .write_overflow_o(nn_overflow),
                .idle_o(nn_idle), .status_o(nn_status),
                .feed_req_i(((state == S_STREAM_FEED) || (state == S_DP)) &&
                            cnn_frame_ready),
                .feed_row_i(dp_frame), .feed_col_i(dp_idx[6:0]),
                .feed_valid_o(nn_feed_valid), .feed_note_o(nn_feed_note),
                .feed_onset_o(nn_feed_onset), .feed_accept_i(dp_have_bins),
                .mem_req_o(nn_mem_req), .mem_write_o(nn_mem_write),
                .mem_byte_addr_o(nn_mem_addr), .mem_wdata_o(nn_mem_wdata),
                .mem_ready_i(nn_mem_ready), .mem_rsp_valid_i(nn_mem_rsp_valid),
                .mem_rdata_i(mem_rdata_i));
            assign feature_cache_done = 1'b0;
            assign feature_overflow = nn_overflow;
            assign feature_mem_req = 1'b0;
            assign feature_mem_write = 1'b0;
            assign feature_mem_addr = 32'd0;
            assign feature_mem_wdata = 16'd0;
            assign feature_read_valid = 1'b0;
            assign feature_read_addr = 15'd0;
            assign feature_read_data = 16'sd0;
            assign reduce_x_data = nn_sample_x;
            assign note_out_x_data = nn_sample_x;
            assign onset_out_x_data = nn_sample_x;
        end else if (USE_EXTERNAL_FEATURES) begin : g_ddr_features
            assign nn_status = 4'd0;
            basic_pitch_feature_ddr #(.FRAMES(FRAME_LIMIT)) u_feature_ddr (
                .clk_i(clk_i), .rst_ni(run_rst_ni),
                .contour_we_i(contour_act_valid), .contour_row_i(contour_row_d2),
                .contour_col_i(contour_col_d2), .contour_ch_i(contour_ch_d2[2:0]),
                .contour_data_i(contour_act_y),
                .notes_we_i(notes_act_valid), .notes_row_i(notes_row_d2),
                .notes_col_i(notes_col_d2[6:0]), .notes_ch_i(notes_ch_d2[4:0]),
                .notes_data_i(notes_act_y),
                .onset_we_i(onset_act_valid), .onset_row_i(onset_row_d2),
                .onset_col_i(onset_col_d2[6:0]), .onset_ch_i(onset_ch_d2[4:0]),
                .onset_data_i(onset_act_y),
                .load_start_i(state == S_FEATURE_CACHE),
                .load_kind_i(feature_load_kind),
                .load_start_row_i(feature_load_start_row), .load_rows_i(feature_load_rows),
                .load_done_o(feature_cache_done), .overflow_o(feature_overflow),
                .read_valid_i(feature_read_valid), .read_addr_i(feature_read_addr),
                .read_data_o(feature_read_data),
                .mem_req_o(feature_mem_req), .mem_write_o(feature_mem_write),
                .mem_byte_addr_o(feature_mem_addr), .mem_wdata_o(feature_mem_wdata),
                .mem_ready_i(feature_mem_ready), .mem_rsp_valid_i(feature_mem_rsp_valid),
                .mem_rdata_i(mem_rdata_i));

            always_comb begin
                feature_read_valid = 1'b0;
                feature_read_addr = 15'd0;
                feature_read_rel = 12'sd0;
                if ((state == S_START_REDUCE) || (state == S_REDUCE)) begin
                    feature_read_rel = reduce_x_row - feature_load_start_row;
                    if ((reduce_x_row >= 0) && (reduce_x_row < FRAME_LIMIT) &&
                        (reduce_x_col >= 0) && (reduce_x_col < CONTOUR_BINS) &&
                        (feature_read_rel >= 0) && (feature_read_rel < 5)) begin
                        feature_read_valid = 1'b1;
                        feature_read_addr = (($unsigned(feature_read_rel) * CONTOUR_BINS +
                                             reduce_x_col[8:0]) * 8) + reduce_x_channel[2:0];
                    end
                end else if ((state == S_START_NOTE_OUT) || (state == S_NOTE_OUT)) begin
                    feature_read_rel = note_out_x_row - feature_load_start_row;
                    if ((note_out_x_row >= 0) && (note_out_x_row < FRAME_LIMIT) &&
                        (note_out_x_col >= 0) && (note_out_x_col < NOTE_BINS) &&
                        (feature_read_rel >= 0) && (feature_read_rel < 7)) begin
                        feature_read_valid = 1'b1;
                        feature_read_addr = (($unsigned(feature_read_rel) * NOTE_BINS +
                                             note_out_x_col[6:0]) * 32) + note_out_x_channel[4:0];
                    end
                end else if ((state == S_START_ONSET_OUT) || (state == S_ONSET_OUT)) begin
                    feature_read_rel = onset_out_x_row - feature_load_start_row;
                    if ((onset_out_channel != 0) && (onset_out_x_row >= 0) &&
                        (onset_out_x_row < FRAME_LIMIT) && (onset_out_x_col >= 0) &&
                        (onset_out_x_col < NOTE_BINS) && (feature_read_rel >= 0) &&
                        (feature_read_rel < 3)) begin
                        feature_read_valid = 1'b1;
                        feature_read_addr = (($unsigned(feature_read_rel) * NOTE_BINS +
                                             onset_out_x_col[6:0]) * 32) + onset_out_channel - 1'b1;
                    end
                end
            end

            always_ff @(posedge clk_i) begin
                onset_out_use_note_d <= (onset_out_channel == 0) &&
                    (onset_out_x_row >= 0) && (onset_out_x_row < FRAME_LIMIT) &&
                    (onset_out_x_col >= 0) && (onset_out_x_col < NOTE_BINS);
                if ((onset_out_x_row >= 0) && (onset_out_x_row < FRAME_LIMIT) &&
                    (onset_out_x_col >= 0) && (onset_out_x_col < NOTE_BINS))
                    onset_out_note_data <= note_post_mem[
                        ($unsigned(onset_out_x_row) % NOTE_OUT_RING_ROWS) * NOTE_BINS +
                        onset_out_x_col[6:0]];
                else
                    onset_out_note_data <= 16'sd0;
            end
            assign reduce_x_data = feature_read_data;
            assign note_out_x_data = feature_read_data;
            assign onset_out_x_data = onset_out_use_note_d ? onset_out_note_data
                                                           : feature_read_data;
        end else begin : g_bsram_features
            assign nn_status = 4'd0;
            assign feature_cache_done = 1'b0;
            assign feature_overflow = 1'b0;
            assign feature_mem_req = 1'b0;
            assign feature_mem_write = 1'b0;
            assign feature_mem_addr = 32'd0;
            assign feature_mem_wdata = 16'd0;
            assign feature_read_valid = 1'b0;
            assign feature_read_addr = 15'd0;
            assign feature_read_data = 16'sd0;
            always_ff @(posedge clk_i) begin
                if ((reduce_x_row >= 0) && (reduce_x_row < FRAME_LIMIT) &&
                    (reduce_x_col >= 0) && (reduce_x_col < CONTOUR_BINS))
                    reduce_x_data <= contour_mem[
                        ((($unsigned(reduce_x_row) % CONTOUR_RING_ROWS) * CONTOUR_BINS +
                          reduce_x_col[8:0]) * 8) + reduce_x_channel[2:0]];
                else
                    reduce_x_data <= 16'sd0;
                if ((note_out_x_row >= 0) && (note_out_x_row < FRAME_LIMIT) &&
                    (note_out_x_col >= 0) && (note_out_x_col < NOTE_BINS))
                    note_out_x_data <= notes_mem[
                        ((($unsigned(note_out_x_row) % NOTES_RING_ROWS) * NOTE_BINS +
                          note_out_x_col[6:0]) * 32) + note_out_x_channel[4:0]];
                else
                    note_out_x_data <= 16'sd0;
                if ((onset_out_x_row < 0) || (onset_out_x_row >= FRAME_LIMIT) ||
                    (onset_out_x_col < 0) || (onset_out_x_col >= NOTE_BINS))
                    onset_out_x_data <= 16'sd0;
                else if (onset_out_channel == 0)
                    onset_out_x_data <= note_post_mem[
                        ($unsigned(onset_out_x_row) % NOTE_OUT_RING_ROWS) * NOTE_BINS +
                        onset_out_x_col[6:0]];
                else
                    onset_out_x_data <= onset_mem[
                        ((($unsigned(onset_out_x_row) % ONSET_RING_ROWS) * NOTE_BINS +
                          onset_out_x_col[6:0]) * 32) + onset_out_channel - 1'b1];
            end
        end
    endgenerate

    generate if (USE_ALL_DDR) begin : g_nn_sample_input
        assign notes_x_data = nn_sample_x;
        assign onset_x_data = nn_sample_x;
    end else begin : g_local_sample_input
    always_ff @(posedge clk_i) begin
        if ((notes_x_row >= 0) && (notes_x_row < FRAME_LIMIT) &&
            (notes_x_col >= 0) && (notes_x_col < CONTOUR_BINS))
            notes_x_data <= reduce_mem[
                ($unsigned(notes_x_row) % REDUCE_RING_ROWS) * CONTOUR_BINS + notes_x_col[8:0]];
        else
            notes_x_data <= 16'sd0;
        onset_x_data <= 16'sd0;
    end
    end endgenerate
    assign reduce_b_data = USE_ALL_DDR ? nn_bias : 32'shf54f7c02;
    assign notes_b_data = USE_ALL_DDR ? nn_bias : notes_b[notes_b_addr];
    assign note_out_b_data = USE_ALL_DDR ? nn_bias : 32'she7d267c2;
    assign onset_b_data = USE_ALL_DDR ? nn_bias : onset_b[onset_b_addr];
    assign onset_out_b_data = USE_ALL_DDR ? nn_bias : 32'shf9a24245;

    basic_pitch_conv2d #(.IN_T(FRAME_LIMIT), .IN_F(CONTOUR_BINS), .IN_C(8), .KH(5), .KW(5),
        .OUT_T(FRAME_LIMIT), .OUT_F(CONTOUR_BINS), .OUT_C(1), .STRIDE_T(1), .STRIDE_F(1),
        .PAD_T(2), .PAD_F(2), .USE_STACK(0), .ACT(2),
        .DDR_FETCH(USE_ALL_DDR)) u_reduce (
        .clk_i(clk_i), .rst_ni(run_rst_ni), .start_i(state == S_START_REDUCE),
        .row_start_i(reduce_run_row), .row_limit_i((FRAME_LIMIT > 1) ? reduce_run_row + 9'd1 : FRAME_COUNT),
        .pl_addr_o(), .pl_data_i(16'sd0), .x_addr_o(reduce_x_addr),
        .x_channel_o(reduce_x_channel), .x_row_o(reduce_x_row), .x_col_o(reduce_x_col),
        .x_data_i(reduce_x_data),
        .w_addr_o(reduce_w_addr), .w_data_i(reduce_w_data), .b_addr_o(reduce_b_addr), .b_data_i(reduce_b_data),
        .input_in_range_o(nn_input_range[1]), .sample_req_o(nn_sample_req[1]),
        .sample_valid_i(nn_sample_valid), .bias_req_o(nn_bias_req[1]), .bias_valid_i(nn_bias_valid),
        .y_we_o(reduce_y_we), .y_addr_o(reduce_y_addr), .y_data_o(reduce_y_data),
        .y_row_o(reduce_y_row), .y_col_o(reduce_y_col), .y_channel_o(reduce_y_channel),
        .y_acc_o(reduce_y_acc), .busy_o(), .done_o(reduce_done));
    basic_pitch_activation #(.MUL(2419), .SHIFT(32), .ACT(2),
        .USE_EXTERNAL_LUT(USE_EXTERNAL_WEIGHTS || USE_EXTERNAL_FEATURES || USE_ALL_DDR)) u_reduce_act (
        .clk_i(clk_i), .rst_ni(run_rst_ni), .valid_i(reduce_y_we), .acc_i(reduce_y_acc),
        .valid_o(reduce_act_valid), .y_o(reduce_act_y), .sat_o(), .arg_dbg_o(),
        .busy_o(reduce_act_busy), .lut_req_o(reduce_lut_req), .lut_addr_o(reduce_lut_addr),
        .lut_ready_i(reduce_lut_ready), .lut_rsp_valid_i(lut_backend_rsp_valid),
        .lut_rdata_i(lut_backend_rdata));

    basic_pitch_conv2d #(.IN_T(FRAME_LIMIT), .IN_F(CONTOUR_BINS), .IN_C(1), .KH(7), .KW(7),
        .OUT_T(FRAME_LIMIT), .OUT_F(NOTE_BINS), .OUT_C(32), .STRIDE_T(1), .STRIDE_F(3),
        .PAD_T(3), .PAD_F(3), .USE_STACK(0), .ACT(1),
        .DDR_FETCH(USE_ALL_DDR)) u_notes (
        .clk_i(clk_i), .rst_ni(run_rst_ni), .start_i(state == S_START_NOTES),
        .row_start_i(notes_run_row), .row_limit_i((FRAME_LIMIT > 1) ? notes_run_row + 9'd1 : FRAME_COUNT),
        .pl_addr_o(), .pl_data_i(16'sd0), .x_addr_o(notes_x_addr),
        .x_channel_o(notes_x_channel), .x_row_o(notes_x_row), .x_col_o(notes_x_col),
        .x_data_i(notes_x_data),
        .w_addr_o(notes_w_addr), .w_data_i(notes_w_data), .b_addr_o(notes_b_addr), .b_data_i(notes_b_data),
        .input_in_range_o(nn_input_range[2]), .sample_req_o(nn_sample_req[2]),
        .sample_valid_i(nn_sample_valid), .bias_req_o(nn_bias_req[2]), .bias_valid_i(nn_bias_valid),
        .y_we_o(notes_y_we), .y_addr_o(notes_y_addr), .y_data_o(notes_y_data),
        .y_row_o(notes_y_row), .y_col_o(notes_y_col), .y_channel_o(notes_y_channel),
        .y_acc_o(notes_y_acc), .busy_o(), .done_o(notes_done));
    basic_pitch_activation #(.MUL(131243), .SHIFT(32), .ACT(1)) u_notes_act (
        .clk_i(clk_i), .rst_ni(run_rst_ni), .valid_i(notes_y_we), .acc_i(notes_y_acc),
        .valid_o(notes_act_valid), .y_o(notes_act_y), .sat_o(), .arg_dbg_o());

    basic_pitch_conv2d #(.IN_T(FRAME_LIMIT), .IN_F(NOTE_BINS), .IN_C(32), .KH(7), .KW(3),
        .OUT_T(FRAME_LIMIT), .OUT_F(NOTE_BINS), .OUT_C(1), .STRIDE_T(1), .STRIDE_F(1),
        .PAD_T(3), .PAD_F(1), .USE_STACK(0), .ACT(2),
        .DDR_FETCH(USE_ALL_DDR)) u_note_out (
        .clk_i(clk_i), .rst_ni(run_rst_ni), .start_i(state == S_START_NOTE_OUT),
        .row_start_i(note_out_run_row), .row_limit_i((FRAME_LIMIT > 1) ? note_out_run_row + 9'd1 : FRAME_COUNT),
        .pl_addr_o(), .pl_data_i(16'sd0), .x_addr_o(note_out_x_addr),
        .x_channel_o(note_out_x_channel), .x_row_o(note_out_x_row), .x_col_o(note_out_x_col),
        .x_data_i(note_out_x_data),
        .w_addr_o(note_out_w_addr), .w_data_i(note_out_w_data), .b_addr_o(note_out_b_addr), .b_data_i(note_out_b_data),
        .input_in_range_o(nn_input_range[3]), .sample_req_o(nn_sample_req[3]),
        .sample_valid_i(nn_sample_valid), .bias_req_o(nn_bias_req[3]), .bias_valid_i(nn_bias_valid),
        .y_we_o(note_out_y_we), .y_addr_o(note_out_y_addr), .y_data_o(note_out_y_data),
        .y_row_o(note_out_y_row), .y_col_o(note_out_y_col), .y_channel_o(note_out_y_channel),
        .y_acc_o(note_out_y_acc), .busy_o(), .done_o(note_out_done));
    basic_pitch_activation #(.MUL(1677), .SHIFT(32), .ACT(2),
        .USE_EXTERNAL_LUT(USE_EXTERNAL_WEIGHTS || USE_EXTERNAL_FEATURES || USE_ALL_DDR)) u_note_out_act (
        .clk_i(clk_i), .rst_ni(run_rst_ni), .valid_i(note_out_y_we), .acc_i(note_out_y_acc),
        .valid_o(note_out_act_valid), .y_o(note_out_act_y), .sat_o(), .arg_dbg_o(),
        .busy_o(note_out_act_busy), .lut_req_o(note_out_lut_req), .lut_addr_o(note_out_lut_addr),
        .lut_ready_i(note_out_lut_ready), .lut_rsp_valid_i(lut_backend_rsp_valid),
        .lut_rdata_i(lut_backend_rdata));

    basic_pitch_conv2d #(.IN_T(FRAME_LIMIT), .IN_F(CONTOUR_BINS), .IN_C(8), .KH(5), .KW(5),
        .OUT_T(FRAME_LIMIT), .OUT_F(NOTE_BINS), .OUT_C(32), .STRIDE_T(1), .STRIDE_F(3),
        .PAD_T(2), .PAD_F(2), .USE_STACK(1), .ACT(1),
        .DDR_FETCH(USE_ALL_DDR)) u_onset (
        .clk_i(clk_i), .rst_ni(run_rst_ni), .start_i(state == S_START_ONSET),
        .row_start_i(onset_run_row), .row_limit_i((FRAME_LIMIT > 1) ? onset_run_row + 9'd1 : FRAME_COUNT),
        .pl_addr_o(onset_pl_addr), .pl_data_i(onset_pl_data), .x_addr_o(onset_x_addr),
        .x_row_o(), .x_col_o(), .x_data_i(onset_x_data),
        .w_addr_o(onset_w_addr), .w_data_i(onset_w_data), .b_addr_o(onset_b_addr), .b_data_i(onset_b_data),
        .input_in_range_o(nn_input_range[4]), .sample_req_o(nn_sample_req[4]),
        .sample_valid_i(nn_sample_valid), .bias_req_o(nn_bias_req[4]), .bias_valid_i(nn_bias_valid),
        .y_we_o(onset_y_we), .y_addr_o(onset_y_addr), .y_data_o(onset_y_data),
        .y_row_o(onset_y_row), .y_col_o(onset_y_col), .y_channel_o(onset_y_channel),
        .y_acc_o(onset_y_acc), .busy_o(), .done_o(onset_done));
    assign onset_pl_data = USE_ALL_DDR ? nn_sample_x :
        ((onset_pl_addr < FRAME_LIMIT*CQT_BINS) ? norm_feature_rd_data : 16'sd0);
    assign norm_feature_rd_addr = (state == S_ONSET) ? onset_pl_addr : contour_pl_addr;
    basic_pitch_activation #(.MUL(38333), .SHIFT(32), .ACT(1)) u_onset_act (
        .clk_i(clk_i), .rst_ni(run_rst_ni), .valid_i(onset_y_we), .acc_i(onset_y_acc),
        .valid_o(onset_act_valid), .y_o(onset_act_y), .sat_o(), .arg_dbg_o());

    basic_pitch_conv2d #(.IN_T(FRAME_LIMIT), .IN_F(NOTE_BINS), .IN_C(33), .KH(3), .KW(3),
        .OUT_T(FRAME_LIMIT), .OUT_F(NOTE_BINS), .OUT_C(1), .STRIDE_T(1), .STRIDE_F(1),
        .PAD_T(1), .PAD_F(1), .USE_STACK(0), .ACT(2),
        .DDR_FETCH(USE_ALL_DDR)) u_onset_out (
        .clk_i(clk_i), .rst_ni(run_rst_ni), .start_i(state == S_START_ONSET_OUT),
        .row_start_i(onset_out_run_row), .row_limit_i((FRAME_LIMIT > 1) ? onset_out_run_row + 9'd1 : FRAME_COUNT),
        .pl_addr_o(), .pl_data_i(16'sd0), .x_addr_o(onset_out_x_addr),
        .x_cell_addr_o(onset_out_cell_addr), .x_channel_o(onset_out_channel),
        .x_row_o(onset_out_x_row), .x_col_o(onset_out_x_col),
        .x_data_i(onset_out_x_data),
        .w_addr_o(onset_out_w_addr), .w_data_i(onset_out_w_data), .b_addr_o(onset_out_b_addr), .b_data_i(onset_out_b_data),
        .input_in_range_o(nn_input_range[5]), .sample_req_o(nn_sample_req[5]),
        .sample_valid_i(nn_sample_valid), .bias_req_o(nn_bias_req[5]), .bias_valid_i(nn_bias_valid),
        .y_we_o(onset_out_y_we), .y_addr_o(onset_out_y_addr), .y_data_o(onset_out_y_data),
        .y_row_o(onset_out_y_row), .y_col_o(onset_out_y_col), .y_channel_o(onset_out_y_channel),
        .y_acc_o(onset_out_y_acc), .busy_o(), .done_o(onset_out_done));
    basic_pitch_activation #(.MUL(3708), .SHIFT(32), .ACT(2),
        .USE_EXTERNAL_LUT(USE_EXTERNAL_WEIGHTS || USE_EXTERNAL_FEATURES || USE_ALL_DDR)) u_onset_out_act (
        .clk_i(clk_i), .rst_ni(run_rst_ni), .valid_i(onset_out_y_we), .acc_i(onset_out_y_acc),
        .valid_o(onset_out_act_valid), .y_o(onset_out_act_y), .sat_o(), .arg_dbg_o(),
        .busy_o(onset_out_act_busy), .lut_req_o(onset_out_lut_req), .lut_addr_o(onset_out_lut_addr),
        .lut_ready_i(onset_out_lut_ready), .lut_rsp_valid_i(lut_backend_rsp_valid),
        .lut_rdata_i(lut_backend_rdata));

    // The sigmoid heads are mutually exclusive and share one backend.  With
    // DDR weights the table follows the model blob; with DDR feature tensors a
    // single local pROM replaces the three formerly duplicated tables.
    always_comb begin
        lut_req_merged = 1'b0;
        lut_index_merged = 12'd0;
        reduce_lut_ready = 1'b0;
        note_out_lut_ready = 1'b0;
        onset_out_lut_ready = 1'b0;
        if (reduce_lut_req) begin
            lut_req_merged = 1'b1;
            lut_index_merged = reduce_lut_addr;
            reduce_lut_ready = lut_backend_ready;
        end else if (note_out_lut_req) begin
            lut_req_merged = 1'b1;
            lut_index_merged = note_out_lut_addr;
            note_out_lut_ready = lut_backend_ready;
        end else if (onset_out_lut_req) begin
            lut_req_merged = 1'b1;
            lut_index_merged = onset_out_lut_addr;
            onset_out_lut_ready = lut_backend_ready;
        end
    end

    generate
        if (USE_EXTERNAL_WEIGHTS || USE_ALL_DDR) begin : g_ddr_sigmoid
            assign lut_mem_req = lut_req_merged;
            assign lut_mem_addr = `BP_DDR_NN_MODEL_BYTE_BASE +
                                  ((32'd16625 + {20'd0, lut_index_merged}) << 1);
            assign lut_backend_ready = lut_mem_ready;
            assign lut_backend_rsp_valid = lut_mem_rsp_valid;
            assign lut_backend_rdata = mem_rdata_i;
        end else if (USE_EXTERNAL_FEATURES) begin : g_shared_sigmoid
            assign lut_mem_req = 1'b0;
            assign lut_mem_addr = 32'd0;
            basic_pitch_shared_sigmoid u_shared_sigmoid (
                .clk_i(clk_i), .rst_ni(run_rst_ni), .req_i(lut_req_merged),
                .addr_i(lut_index_merged), .ready_o(lut_backend_ready),
                .rsp_valid_o(lut_backend_rsp_valid), .rdata_o(lut_backend_rdata));
        end else begin : g_internal_sigmoid
            assign lut_mem_req = 1'b0;
            assign lut_mem_addr = 32'd0;
            assign lut_backend_ready = 1'b0;
            assign lut_backend_rsp_valid = 1'b0;
            assign lut_backend_rdata = 16'd0;
        end
    endgenerate
    // Activation outputs are delayed by one synchronous stage.  Capture the
    // matching addresses so each completed cell lands in the correct feature
    // map before the next head is started.
    always_ff @(posedge clk_i or negedge run_rst_ni) begin
        if (!run_rst_ni) begin
            contour_row_d1 <= 0; contour_row_d2 <= 0; contour_col_d1 <= 0; contour_col_d2 <= 0;
            contour_ch_d1 <= 0; contour_ch_d2 <= 0;
            reduce_row_d1 <= 0; reduce_row_d2 <= 0; reduce_col_d1 <= 0; reduce_col_d2 <= 0;
            reduce_ch_d1 <= 0; reduce_ch_d2 <= 0;
            notes_row_d1 <= 0; notes_row_d2 <= 0; notes_col_d1 <= 0; notes_col_d2 <= 0;
            notes_ch_d1 <= 0; notes_ch_d2 <= 0;
            note_out_row_d1 <= 0; note_out_row_d2 <= 0; note_out_col_d1 <= 0; note_out_col_d2 <= 0;
            note_out_ch_d1 <= 0; note_out_ch_d2 <= 0;
            onset_row_d1 <= 0; onset_row_d2 <= 0; onset_col_d1 <= 0; onset_col_d2 <= 0;
            onset_ch_d1 <= 0; onset_ch_d2 <= 0;
            onset_out_row_d1 <= 0; onset_out_row_d2 <= 0; onset_out_col_d1 <= 0; onset_out_col_d2 <= 0;
            onset_out_ch_d1 <= 0; onset_out_ch_d2 <= 0;
        end else begin
            if (contour_y_we) begin contour_row_d1 <= contour_y_row; contour_col_d1 <= contour_y_col; contour_ch_d1 <= contour_y_channel; end
            if (reduce_y_we) begin reduce_row_d1 <= reduce_y_row; reduce_col_d1 <= reduce_y_col; reduce_ch_d1 <= reduce_y_channel; end
            if (notes_y_we) begin notes_row_d1 <= notes_y_row; notes_col_d1 <= notes_y_col; notes_ch_d1 <= notes_y_channel; end
            if (note_out_y_we) begin note_out_row_d1 <= note_out_y_row; note_out_col_d1 <= note_out_y_col; note_out_ch_d1 <= note_out_y_channel; end
            if (onset_y_we) begin onset_row_d1 <= onset_y_row; onset_col_d1 <= onset_y_col; onset_ch_d1 <= onset_y_channel; end
            if (onset_out_y_we) begin onset_out_row_d1 <= onset_out_y_row; onset_out_col_d1 <= onset_out_y_col; onset_out_ch_d1 <= onset_out_y_channel; end
            contour_row_d2 <= contour_row_d1; contour_col_d2 <= contour_col_d1; contour_ch_d2 <= contour_ch_d1;
            reduce_row_d2 <= reduce_row_d1; reduce_col_d2 <= reduce_col_d1; reduce_ch_d2 <= reduce_ch_d1;
            notes_row_d2 <= notes_row_d1; notes_col_d2 <= notes_col_d1; notes_ch_d2 <= notes_ch_d1;
            note_out_row_d2 <= note_out_row_d1; note_out_col_d2 <= note_out_col_d1; note_out_ch_d2 <= note_out_ch_d1;
            onset_row_d2 <= onset_row_d1; onset_col_d2 <= onset_col_d1; onset_ch_d2 <= onset_ch_d1;
            onset_out_row_d2 <= onset_out_row_d1; onset_out_col_d2 <= onset_out_col_d1; onset_out_ch_d2 <= onset_out_ch_d1;
            if (contour_act_valid && !USE_EXTERNAL_FEATURES && !USE_ALL_DDR)
                contour_mem[((contour_row_d2 % CONTOUR_RING_ROWS) * CONTOUR_BINS + contour_col_d2) * 8 + contour_ch_d2] <= $signed(contour_act_y);
            if (reduce_act_valid && !USE_ALL_DDR)
                reduce_mem[(reduce_row_d2 % REDUCE_RING_ROWS) * CONTOUR_BINS + reduce_col_d2] <= $signed(reduce_act_y);
            if (notes_act_valid && !USE_EXTERNAL_FEATURES && !USE_ALL_DDR)
                notes_mem[((notes_row_d2 % NOTES_RING_ROWS) * NOTE_BINS + notes_col_d2) * 32 + notes_ch_d2] <= $signed(notes_act_y);
            if (note_out_act_valid && !USE_ALL_DDR)
                note_post_mem[(note_out_row_d2 % NOTE_OUT_RING_ROWS) * NOTE_BINS + note_out_col_d2] <= $signed(note_out_act_y);
            if (onset_act_valid && !USE_EXTERNAL_FEATURES && !USE_ALL_DDR)
                onset_mem[((onset_row_d2 % ONSET_RING_ROWS) * NOTE_BINS + onset_col_d2) * 32 + onset_ch_d2] <= $signed(onset_act_y);
            if (onset_out_act_valid && !USE_ALL_DDR)
                onset_post_mem[onset_out_col_d2] <= $signed(onset_out_act_y);
        end
    end

    // ------------------------------------------------------------------
    // Posterior ingress and bounded Viterbi result
    // ------------------------------------------------------------------
    logic cnn_result_valid, cnn_done, cnn_busy, cnn_score_complete;
    logic [6:0] cnn_result_note; logic [15:0] cnn_result_conf, cnn_result_frame;
    logic [6:0] dp_best_note;
    logic [15:0] dp_best_conf;
    logic dp_mem_req, dp_mem_write, dp_mem_ready, dp_mem_rsp_valid;
    logic [31:0] dp_mem_addr;
    logic [15:0] dp_mem_wdata;
    wire dp_active = (state == S_DP) || (state == S_STREAM_FEED);
    assign dp_have_bins = dp_active && cnn_frame_ready && (dp_idx < NOTE_BINS) &&
                          (!USE_ALL_DDR || nn_feed_valid);
    wire dp_frame_valid = dp_have_bins && (dp_idx == NOTE_BINS-1);
    generate
        if (FRAME_LIMIT > 1) begin : g_full_dp
            basic_pitch_cnn_streaming #(.FRAMES(FRAME_LIMIT),
                .USE_EXTERNAL_STATE(USE_EXTERNAL_STATE)) u_cnn_stream (
                .clk_i(clk_i), .rst_ni(run_rst_ni), .start_i(state == S_START_DP), .active_i(1'b1),
                .note_valid_i(dp_have_bins), .note_idx_i(dp_idx[6:0]),
                .note_q_i(USE_ALL_DDR ? nn_feed_note :
                    note_post_mem[(dp_frame % NOTE_OUT_RING_ROWS)*NOTE_BINS + dp_idx]),
                .onset_valid_i(dp_have_bins), .onset_idx_i(dp_idx[6:0]),
                .onset_q_i(USE_ALL_DDR ? nn_feed_onset : onset_post_mem[dp_idx]),
                .contour_valid_i(1'b0), .contour_idx_i(9'd0), .contour_q_i(16'sd0),
                .frame_valid_i(dp_frame_valid), .frame_last_i(dp_frame == FRAME_LIMIT-1),
                .frame_ready_o(cnn_frame_ready), .frame_index_o(), .note_we_o(), .note_addr_o(), .note_data_o(),
                .onset_we_o(), .onset_addr_o(), .onset_data_o(), .contour_we_o(), .contour_addr_o(), .contour_data_o(),
                .result_valid_o(cnn_result_valid), .result_note_o(cnn_result_note), .result_conf_o(cnn_result_conf),
                .result_frame_o(cnn_result_frame),
                .score_valid_o(score_valid_o), .score_ready_i(score_ready_i), .score_note_o(score_note_o),
                .score_complete_o(cnn_score_complete),
                .done_o(cnn_done), .busy_o(cnn_busy),
                .mem_req_o(dp_mem_req), .mem_write_o(dp_mem_write),
                .mem_byte_addr_o(dp_mem_addr), .mem_wdata_o(dp_mem_wdata),
                .mem_ready_i(dp_mem_ready), .mem_rsp_valid_i(dp_mem_rsp_valid),
                .mem_rdata_i(mem_rdata_i)
            );
        end else begin : g_single_dp
            // With one frame there is no temporal transition term.  The
            // Viterbi column is exactly the maximum posterior bin; doing the
            // bounded scan here avoids instantiating the full 89-state DP
            // matrix in the first physical image.
            assign cnn_frame_ready = 1'b1;
            assign cnn_result_valid = 1'b0;
            assign cnn_result_note = 7'd0;
            assign cnn_result_conf = 16'd0;
            assign cnn_result_frame = 16'd0;
            assign score_valid_o = 1'b0;
            assign score_note_o = 7'd0;
            assign cnn_done = 1'b0;
            assign cnn_busy = 1'b0;
            assign cnn_score_complete = 1'b0;
            assign dp_mem_req = 1'b0;
            assign dp_mem_write = 1'b0;
            assign dp_mem_addr = 32'd0;
            assign dp_mem_wdata = 16'd0;
        end
    endgenerate

    // All reads are serialized here, so a delayed DDR response is delivered
    // to the client whose request actually entered the command FIFO.
    logic read_outstanding;
    logic [3:0] request_owner, response_owner;
    // Prefix-OR grants preserve the original sig/front/cqt/.../dp priority.
    // Each client's ready has a balanced parallel qualification instead of an
    // eleven-branch mux chain; no queue, extra request beat or RAM is introduced.
    wire [10:0] client_requests = {dp_mem_req, nn_mem_req, lut_mem_req, weight_mem_req, feature_mem_req, cache_mem_req, model_mem_req, norm_mem_req, cqt_coeff_mem_req, front_coeff_mem_req, sig_mem_req};
    wire [10:0] client_grants;
    assign client_grants[0] = !read_outstanding && client_requests[0];
    for (genvar client = 1; client < 11; client = client + 1) begin : g_ddr_grant
        assign client_grants[client] = !read_outstanding && client_requests[client] &&
                                      !(|client_requests[client-1:0]);
    end
    always_comb begin
        mem_req_o = |client_grants;
        mem_write_o = (client_grants[0] && sig_mem_write) |
                      (client_grants[3] && norm_mem_write) |
                      (client_grants[4] && model_mem_write) |
                      (client_grants[5] && cache_mem_write) |
                      (client_grants[6] && feature_mem_write) |
                      (client_grants[9] && nn_mem_write) |
                      (client_grants[10] && dp_mem_write);
        request_owner = (4'd9 & {4{client_grants[0]}}) |
                        (4'd10 & {4{client_grants[1]}}) |
                        (4'd11 & {4{client_grants[2]}}) |
                        (4'd1 & {4{client_grants[3]}}) |
                        (4'd2 & {4{client_grants[4]}}) |
                        (4'd3 & {4{client_grants[5]}}) |
                        (4'd4 & {4{client_grants[6]}}) |
                        (4'd5 & {4{client_grants[7]}}) |
                        (4'd6 & {4{client_grants[8]}}) |
                        (4'd7 & {4{client_grants[9]}}) |
                        (4'd8 & {4{client_grants[10]}});
        mem_byte_addr_o = ({32{client_grants[0]}} & sig_mem_addr) |
                          ({32{client_grants[1]}} & front_coeff_mem_addr) |
                          ({32{client_grants[2]}} & cqt_coeff_mem_addr) |
                          ({32{client_grants[3]}} & norm_mem_addr) |
                          ({32{client_grants[4]}} & model_mem_addr) |
                          ({32{client_grants[5]}} & cache_mem_addr) |
                          ({32{client_grants[6]}} & feature_mem_addr) |
                          ({32{client_grants[7]}} & weight_mem_addr) |
                          ({32{client_grants[8]}} & lut_mem_addr) |
                          ({32{client_grants[9]}} & nn_mem_addr) |
                          ({32{client_grants[10]}} & dp_mem_addr);
        mem_wdata_o = ({16{client_grants[0]}} & sig_mem_wdata) |
                      ({16{client_grants[3]}} & norm_mem_wdata) |
                      ({16{client_grants[4]}} & model_mem_wdata) |
                      ({16{client_grants[5]}} & cache_mem_wdata) |
                      ({16{client_grants[6]}} & feature_mem_wdata) |
                      ({16{client_grants[7]}} & weight_mem_wdata) |
                      ({16{client_grants[9]}} & nn_mem_wdata) |
                      ({16{client_grants[10]}} & dp_mem_wdata);
        sig_mem_ready = mem_ready_i && client_grants[0];
        front_coeff_mem_ready = mem_ready_i && client_grants[1];
        cqt_coeff_mem_ready = mem_ready_i && client_grants[2];
        norm_mem_ready = mem_ready_i && client_grants[3];
        model_mem_ready = mem_ready_i && client_grants[4];
        cache_mem_ready = mem_ready_i && client_grants[5];
        feature_mem_ready = mem_ready_i && client_grants[6];
        weight_mem_ready = mem_ready_i && client_grants[7];
        lut_mem_ready = mem_ready_i && client_grants[8];
        nn_mem_ready = mem_ready_i && client_grants[9];
        dp_mem_ready = mem_ready_i && client_grants[10];
    end
    always_ff @(posedge clk_i or negedge run_rst_ni) begin
        if (!run_rst_ni) begin
            read_outstanding <= 1'b0;
            response_owner <= 4'd0;
        end else begin
            if (mem_rsp_valid_i) read_outstanding <= 1'b0;
            if (mem_req_o && mem_ready_i && !mem_write_o) begin
                read_outstanding <= 1'b1;
                response_owner <= request_owner;
            end
        end
    end
    assign norm_mem_rsp_valid = mem_rsp_valid_i && response_owner == 4'd1;
    assign sig_mem_rsp_valid = mem_rsp_valid_i && response_owner == 4'd9;
    assign front_coeff_mem_rsp_valid = mem_rsp_valid_i && response_owner == 4'd10;
    assign cqt_coeff_mem_rsp_valid = mem_rsp_valid_i && response_owner == 4'd11;
    assign model_mem_rsp_valid = mem_rsp_valid_i && response_owner == 4'd2;
    assign cache_mem_rsp_valid = mem_rsp_valid_i && response_owner == 4'd3;
    assign feature_mem_rsp_valid = mem_rsp_valid_i && response_owner == 4'd4;
    assign weight_mem_rsp_valid = mem_rsp_valid_i && response_owner == 4'd5;
    assign lut_mem_rsp_valid = mem_rsp_valid_i && response_owner == 4'd6;
    assign nn_mem_rsp_valid = mem_rsp_valid_i && response_owner == 4'd7;
    assign dp_mem_rsp_valid = mem_rsp_valid_i && response_owner == 4'd8;

    assign busy_o = state != S_HOLD;

    always_ff @(posedge clk_i or negedge run_rst_ni) begin
        if (!run_rst_ni) begin
            state <= S_CAPTURE; settle_target <= S_HOLD; settle_count <= 0;
            cache_target <= S_HOLD; cache_center <= 0;
            weight_target <= S_HOLD; weight_blob_base <= 0; weight_word_count <= 0;
            feature_target <= S_HOLD; feature_load_kind <= 2'd0;
            feature_load_start_row <= 0; feature_load_rows <= 0;
            dp_frame <= 0; dp_idx <= 0; result_valid_o <= 1'b0; done_o <= 1'b0;
            song_done_o <= 1'b0; front_window_started <= 1'b0;
            stream_wave <= 0;
            result_note_o <= 0; result_conf_o <= 0; result_frame_o <= 0;
            debug_onset_o <= 0;
        end else begin
            done_o <= 1'b0;
            if (front_win_we || (pcm_valid_i && pcm_ready_o))
                front_window_started <= 1'b1;
            if (onset_out_act_valid) debug_onset_o <= onset_out_act_y;
            case (state)
                S_CAPTURE: begin
                    if (front_win_full &&
                        (!(USE_EXTERNAL_WEIGHTS || USE_ALL_DDR) || model_done))
                        state <= S_START_CQT;
                    else if (pcm_end_i && !front_window_started && front_drained) begin
                        song_done_o <= 1'b1;
                        state <= S_HOLD;
                    end
                end
                S_START_CQT: state <= S_CQT;
                S_CQT: if (cqt_done) state <= S_START_NORM;
                S_START_NORM: state <= S_NORM;
                S_NORM: if (norm_done) begin
                    if (FRAME_LIMIT > 1) begin
                        state <= S_START_DP;
                    end else if (USE_EXTERNAL_PLANE && !USE_ALL_DDR) begin
                        cache_center <= 0;
                        cache_target <= S_PREP_CONTOUR;
                        state <= S_CACHE;
                    end else begin
                        state <= S_PREP_CONTOUR;
                    end
                end
                S_START_CONTOUR: state <= S_CONTOUR;
                S_CONTOUR: if (contour_done) begin
                    settle_target <= (FRAME_LIMIT > 1) ? S_AFTER_CONTOUR : S_PREP_REDUCE;
                    settle_count <= 3; state <= S_SETTLE;
                end
                S_START_REDUCE: state <= S_REDUCE;
                S_REDUCE: if (reduce_done) begin
                    settle_target <= (FRAME_LIMIT > 1) ? S_AFTER_REDUCE : S_PREP_NOTES;
                    settle_count <= 3; state <= S_SETTLE;
                end
                S_START_NOTES: state <= S_NOTES;
                S_NOTES: if (notes_done) begin
                    settle_target <= (FRAME_LIMIT > 1) ? S_AFTER_NOTES : S_PREP_NOTE_OUT;
                    settle_count <= 3; state <= S_SETTLE;
                end
                S_START_NOTE_OUT: state <= S_NOTE_OUT;
                S_NOTE_OUT: if (note_out_done) begin
                    if ((FRAME_LIMIT == 1) && USE_EXTERNAL_PLANE && !USE_ALL_DDR) begin
                        cache_center <= 0;
                        cache_target <= S_PREP_ONSET;
                        settle_target <= S_CACHE;
                    end else begin
                        settle_target <= (FRAME_LIMIT > 1) ? S_AFTER_NOTE_OUT : S_PREP_ONSET;
                    end
                    settle_count <= 3; state <= S_SETTLE;
                end
                S_START_ONSET: state <= S_ONSET;
                S_ONSET: if (onset_done) begin
                    settle_target <= (FRAME_LIMIT > 1) ? S_AFTER_ONSET : S_PREP_ONSET_OUT;
                    settle_count <= 3; state <= S_SETTLE;
                end
                S_START_ONSET_OUT: state <= S_ONSET_OUT;
                S_ONSET_OUT: if (onset_out_done) begin
                    if (FRAME_LIMIT > 1) begin
                        dp_frame <= stream_wave - 9'd9;
                        dp_idx <= 0;
                        settle_target <= S_STREAM_FEED;
                    end else begin
                        settle_target <= S_START_DP;
                    end
                    settle_count <= 3; state <= S_SETTLE;
                end
                S_SETTLE: if (settle_count == 0) begin
                    if (!(reduce_act_busy || note_out_act_busy || onset_out_act_busy) &&
                        (!USE_ALL_DDR || nn_idle))
                        state <= settle_target;
                end else begin
                    settle_count <= settle_count - 1'b1;
                end
                S_START_DP: begin
                    dp_frame <= 0; dp_idx <= 0; dp_best_note <= 0; dp_best_conf <= 0;
                    stream_wave <= 0;
                    state <= (FRAME_LIMIT > 1) ? S_STREAM_DISPATCH : S_DP;
                end
                S_STREAM_DISPATCH:
                    if (stream_wave < FRAME_LIMIT) begin
                        if (USE_EXTERNAL_PLANE && !USE_ALL_DDR) begin
                            cache_center <= stream_wave;
                            cache_target <= S_PREP_CONTOUR;
                            state <= S_CACHE;
                        end else begin
                            state <= S_PREP_CONTOUR;
                        end
                    end else begin
                        state <= S_AFTER_CONTOUR;
                    end
                S_AFTER_CONTOUR:
                    state <= ((stream_wave >= 2) && (stream_wave < FRAME_LIMIT + 2)) ?
                             S_PREP_REDUCE : S_AFTER_REDUCE;
                S_AFTER_REDUCE:
                    state <= ((stream_wave >= 5) && (stream_wave < FRAME_LIMIT + 5)) ?
                             S_PREP_NOTES : S_AFTER_NOTES;
                S_AFTER_NOTES:
                    state <= ((stream_wave >= 8) && (stream_wave < FRAME_LIMIT + 8)) ?
                             S_PREP_NOTE_OUT : S_AFTER_NOTE_OUT;
                S_AFTER_NOTE_OUT:
                    if ((stream_wave >= 8) && (stream_wave < FRAME_LIMIT + 8)) begin
                        if (USE_EXTERNAL_PLANE && !USE_ALL_DDR) begin
                            cache_center <= note_out_run_row;
                            cache_target <= S_PREP_ONSET;
                            state <= S_CACHE;
                        end else begin
                            state <= S_PREP_ONSET;
                        end
                    end else begin
                        state <= S_AFTER_ONSET;
                    end
                S_AFTER_ONSET:
                    state <= ((stream_wave >= 9) && (stream_wave < FRAME_LIMIT + 9)) ?
                             S_PREP_ONSET_OUT : S_STREAM_NEXT;
                S_STREAM_FEED: begin
                    if (dp_have_bins) begin
                        if (dp_idx == NOTE_BINS-1) begin
                            dp_idx <= 0;
                            state <= (dp_frame == FRAME_LIMIT-1) ? S_WAIT_RESULT : S_STREAM_NEXT;
                        end else begin
                            dp_idx <= dp_idx + 1'b1;
                        end
                    end
                end
                S_STREAM_NEXT: begin
                    stream_wave <= stream_wave + 1'b1;
                    state <= S_STREAM_DISPATCH;
                end
                S_CACHE: state <= S_WAIT_CACHE;
                S_WAIT_CACHE: if (cache_done) state <= cache_target;
                S_PREP_CONTOUR: begin
                    if (USE_EXTERNAL_WEIGHTS) begin
                        weight_blob_base <= 15'd0; weight_word_count <= 14'd7488;
                        weight_target <= S_START_CONTOUR; state <= S_LOAD_WEIGHT;
                    end else state <= S_START_CONTOUR;
                end
                S_PREP_REDUCE: begin
                    if (USE_EXTERNAL_FEATURES && !USE_ALL_DDR) begin
                        feature_load_kind <= 2'd0;
                        feature_load_start_row <= $signed({1'b0, reduce_run_row}) - 11'sd2;
                        feature_load_rows <= 4'd5;
                        feature_target <= S_READY_REDUCE;
                        state <= S_FEATURE_CACHE;
                    end else begin
                        state <= S_READY_REDUCE;
                    end
                end
                S_READY_REDUCE: begin
                    if (USE_EXTERNAL_WEIGHTS) begin
                        weight_blob_base <= 15'd7488; weight_word_count <= 14'd200;
                        weight_target <= S_START_REDUCE; state <= S_LOAD_WEIGHT;
                    end else state <= S_START_REDUCE;
                end
                S_PREP_NOTES: begin
                    if (USE_EXTERNAL_WEIGHTS) begin
                        weight_blob_base <= 15'd7688; weight_word_count <= 14'd1568;
                        weight_target <= S_START_NOTES; state <= S_LOAD_WEIGHT;
                    end else state <= S_START_NOTES;
                end
                S_PREP_NOTE_OUT: begin
                    if (USE_EXTERNAL_FEATURES && !USE_ALL_DDR) begin
                        feature_load_kind <= 2'd1;
                        feature_load_start_row <= $signed({1'b0, note_out_run_row}) - 11'sd3;
                        feature_load_rows <= 4'd7;
                        feature_target <= S_READY_NOTE_OUT;
                        state <= S_FEATURE_CACHE;
                    end else begin
                        state <= S_READY_NOTE_OUT;
                    end
                end
                S_READY_NOTE_OUT: begin
                    if (USE_EXTERNAL_WEIGHTS) begin
                        weight_blob_base <= 15'd9256; weight_word_count <= 14'd672;
                        weight_target <= S_START_NOTE_OUT; state <= S_LOAD_WEIGHT;
                    end else state <= S_START_NOTE_OUT;
                end
                S_PREP_ONSET: begin
                    if (USE_EXTERNAL_WEIGHTS) begin
                        weight_blob_base <= 15'd9928; weight_word_count <= 14'd6400;
                        weight_target <= S_START_ONSET; state <= S_LOAD_WEIGHT;
                    end else state <= S_START_ONSET;
                end
                S_PREP_ONSET_OUT: begin
                    if (USE_EXTERNAL_FEATURES && !USE_ALL_DDR) begin
                        feature_load_kind <= 2'd2;
                        feature_load_start_row <= $signed({1'b0, onset_out_run_row}) - 11'sd1;
                        feature_load_rows <= 4'd3;
                        feature_target <= S_READY_ONSET_OUT;
                        state <= S_FEATURE_CACHE;
                    end else begin
                        state <= S_READY_ONSET_OUT;
                    end
                end
                S_READY_ONSET_OUT: begin
                    if (USE_EXTERNAL_WEIGHTS) begin
                        weight_blob_base <= 15'd16328; weight_word_count <= 14'd297;
                        weight_target <= S_START_ONSET_OUT; state <= S_LOAD_WEIGHT;
                    end else state <= S_START_ONSET_OUT;
                end
                S_LOAD_WEIGHT: state <= S_WAIT_WEIGHT;
                S_WAIT_WEIGHT: if (weight_cache_done) state <= weight_target;
                S_FEATURE_CACHE: state <= S_WAIT_FEATURE;
                S_WAIT_FEATURE: if (feature_cache_done) state <= feature_target;
                S_DP: begin
                    if (FRAME_LIMIT == 1) begin
                        if (note_post_mem[dp_idx] >= dp_best_conf) begin
                            dp_best_conf <= note_post_mem[dp_idx];
                            dp_best_note <= dp_idx[6:0];
                        end
                        if (dp_idx == NOTE_BINS-1) begin
                            result_note_o <= (note_post_mem[dp_idx] >= dp_best_conf) ? dp_idx[6:0] : dp_best_note;
                            result_conf_o <= (note_post_mem[dp_idx] >= dp_best_conf) ? note_post_mem[dp_idx] : dp_best_conf;
                            result_frame_o <= 16'd0;
                            result_valid_o <= 1'b1;
                            done_o <= 1'b1;
                            state <= S_HOLD;
                        end else dp_idx <= dp_idx + 1'b1;
                    end else if (dp_have_bins) begin
                        if (dp_idx == NOTE_BINS-1) begin
                            dp_idx <= 0;
                            if (dp_frame != FRAME_LIMIT-1) dp_frame <= dp_frame + 1'b1;
                            else state <= S_WAIT_RESULT;
                        end else dp_idx <= dp_idx + 1'b1;
                    end
                end
                S_WAIT_RESULT: if (cnn_done) begin
                    if (cnn_result_valid) begin
                        result_note_o <= cnn_result_note; result_conf_o <= cnn_result_conf;
                        result_frame_o <= cnn_result_frame; result_valid_o <= 1'b1;
                    end
                    done_o <= 1'b1;
                    state <= cnn_score_complete ? S_WINDOW_RESTART : S_SCORE_DRAIN;
                end
                S_SCORE_DRAIN: if (cnn_score_complete) state <= S_WINDOW_RESTART;
                S_WINDOW_RESTART: begin
                    front_window_started <= 1'b0;
                    result_valid_o <= 1'b0;
                    state <= S_CAPTURE;
                end
                S_HOLD: begin end
                default: state <= S_CAPTURE;
            endcase
        end
    end
endmodule
