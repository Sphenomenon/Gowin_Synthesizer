`timescale 1ns/1ps
`include "basic_pitch_fixed_pkg.svh"
`include "basic_pitch_ddr_map.svh"
// Bounded-window single-voice Viterbi over the Basic Pitch note/onset
// posteriors. 88 note states plus silence. Only the current window's
// back-pointer table and note posteriors are retained, and they are
// overwritten on every window, so no whole-song path or note table is stored.
//
// Interface: while frame_ready_o is high the producer streams 88 note bins in
// ascending index order, then 88 onset bins, then pulses frame_valid_i. The DP
// pulls one (destination, predecessor) cell per cycle, so a 172-frame window
// costs 172 * 89 * 89 cycles plus backtrace/commit. The practice session is
// blocking, so that latency is legal.
//
// Status: RTL candidate. Lint-clean, unit-simulated, and included in the
// standalone Gowin synthesis probe; no completed route/timing evidence yet.
module basic_pitch_viterbi #(
    parameter int NOTE_BINS = 88,
    parameter int FRAMES    = 172,
    parameter bit COARSE_GUIDANCE=1'b0,
    parameter bit USE_EXTERNAL_STATE = 1'b0
) (
    input  logic               clk_i,
    input  logic               rst_ni,
    input  logic               start_i,        // pulse: start a new window
    input  logic               active_i,       // 0 => activity gate says silence
    input  logic               note_valid_i,
    input  logic [6:0]         note_idx_i,
    input  logic signed [15:0] note_q_i,
    input  logic               onset_valid_i,
    input  logic [6:0]         onset_idx_i,
    input  logic signed [15:0] onset_q_i,
    input  logic               frame_valid_i,  // pulse: frame complete
    input  logic               frame_last_i,   // this frame is the window's last
    output logic               frame_ready_o,
    output logic               result_valid_o,
    output logic [6:0]         result_note_o,
    output logic [15:0]        result_conf_o,
    output logic [15:0]        result_frame_o,
    output logic               score_valid_o,
    input  logic               score_ready_i,
    output logic [6:0]         score_note_o,
    output logic               score_complete_o,
    output logic               done_o,
    output logic               busy_o,
    output logic               mem_req_o,
    output logic               mem_write_o,
    output logic [31:0]        mem_byte_addr_o,
    output logic [15:0]        mem_wdata_o,
    input  logic               mem_ready_i,
    input  logic               mem_rsp_valid_i,
    input  logic [15:0]        mem_rdata_i
);
    localparam int        STATES  = NOTE_BINS + 1;
    localparam logic [7:0] SIL_IDX = NOTE_BINS[7:0];

    localparam logic [4:0] S_IDLE = 5'd0, S_BINS = 5'd1, S_LOAD = 5'd2,
                           S_SEED = 5'd3, S_FRAME= 5'd4, S_NEXT = 5'd5,
                           S_ARG  = 5'd6, S_BACK = 5'd7, S_CMMT = 5'd8,
                           S_DONE = 5'd9, S_EXT_NOTE = 5'd10,
                           S_EXT_ONSET = 5'd11, S_EXT_BPTR = 5'd12,
                           S_EXT_BACK_REQ = 5'd13, S_EXT_BACK_WAIT = 5'd14,
                           S_EXT_CMT_ONSET_REQ = 5'd15,
                           S_EXT_CMT_ONSET_WAIT = 5'd16,
                           S_EXT_CMT_NOTE_REQ = 5'd17,
                           S_EXT_CMT_NOTE_WAIT = 5'd18,
                           S_SCORE = 5'd19, S_SCORE_ONSET_REQ = 5'd20,
                           S_SCORE_ONSET_WAIT = 5'd21, S_SCORE_EMIT = 5'd22,
                           S_SCORE_FIRST = 5'd23,
                           S_DP_SUM = 5'd24, S_DP_SELECT = 5'd25,
                           S_DP_COMMIT = 5'd26;

    logic [4:0]         state;
    logic               last_frame_q;
    logic [7:0]         frame_cnt, d_cnt, p_cnt, bt_cnt, cmt_idx;
    logic signed [31:0] score    [0:STATES-1];
    logic signed [31:0] prev_score[0:STATES-1];
    logic signed [31:0] emission [0:STATES-1];
    logic signed [47:0] emit_note_product, emit_onset_product;
    logic signed [31:0] emit_one_comb;
    // Scalar pipeline only: keep the existing score/history RAMs unchanged.
    // p_cnt stays fixed through READ -> SUM -> SELECT, so the predecessor
    // index and its candidate remain aligned even when DDR later stalls.
    logic signed [31:0] dp_prev_q, dp_trans_q, dp_candidate_q;
    logic signed [31:0] best_val;
    logic signed [31:0] arg_val;
    logic [6:0]         best_idx;
    logic signed [15:0] cur_note [0:NOTE_BINS-1];
    logic signed [15:0] cur_onset[0:NOTE_BINS-1];
    logic signed [15:0] peak_note;

    logic [6:0]         bptr_mem [0:FRAMES*STATES-1];
    logic signed [15:0] note_mem [0:FRAMES*NOTE_BINS-1];
    logic               onset_hot_mem[0:FRAMES*NOTE_BINS-1];
    logic [6:0]         path_mem [0:FRAMES-1];
    logic               cmt_found;
    logic [6:0]         cmt_note;
    logic [15:0]        cmt_conf, cmt_frame;
    logic [7:0]         score_scan;
    logic [6:0]         score_previous;
    logic               score_previous_valid;
    logic               score_onset_hot, score_onset_previous;
    wire [7:0] score_midi =
        (state == S_SCORE_FIRST ? {1'b0,cmt_note} : {1'b0,path_mem[score_scan]}) + 8'd21;
    wire score_pair = score_scan <= frame_cnt && path_mem[score_scan] != SIL_IDX &&
        (COARSE_GUIDANCE || (score_scan < frame_cnt &&
         path_mem[score_scan] == path_mem[score_scan + 8'd1]));
    wire score_new = !score_previous_valid ||
        path_mem[score_scan] != score_previous ||
        (score_onset_hot && !score_onset_previous);
    // Push 2 has physical pads 36..99. Fold the extreme MIDI octaves into
    // that playable range; the DP path and first-note report stay untouched.
    assign score_note_o = score_midi < 8'd24 ? score_midi + 8'd24 :
                          score_midi < 8'd36 ? score_midi + 8'd12 :
                          score_midi > 8'd99 ? score_midi - 8'd12 : score_midi;
    assign score_valid_o = state == S_SCORE_FIRST ||
                           (state == S_SCORE_EMIT && score_new);

    logic signed [31:0] trans_comb, cand_comb;
    logic [6:0]         bt_state, bt_next, arg_state;
    logic [6:0]         ext_bin_idx, ext_bptr;
    logic signed [15:0] ext_note_q, ext_onset_q;
    logic               ext_do_note, ext_do_onset, ext_frame_valid, ext_frame_last;

    function automatic logic signed [31:0] trans_note(input logic [6:0] dp);
        logic signed [31:0] c;
        begin
            if (dp == 7'd0)
                trans_note = `BP_TRANS_STAY;
            else begin
                c = -(`BP_TRANS_STEP_SLOPE * dp);
                if (32'(dp) > `BP_TRANS_JUMP_KNEE)
                    c = c - (`BP_TRANS_JUMP_SLOPE * (32'(dp) - `BP_TRANS_JUMP_KNEE));
                trans_note = c;
            end
        end
    endfunction

    always_comb begin
        emit_note_product  = 48'sd0;
        emit_onset_product = 48'sd0;
        if (d_cnt < NOTE_BINS) begin
            emit_note_product  = $signed(cur_note[d_cnt])  * `BP_EMIT_NOTE_W;
            emit_onset_product = $signed(cur_onset[d_cnt]) * `BP_EMIT_ONSET_W;
            emit_one_comb = (emit_note_product >>> 15) +
                            (emit_onset_product >>> 15);
        end else begin
            emit_one_comb = (peak_note >= `BP_SILENCE_THRESHOLD) ?
                            `BP_EMIT_SIL_ACTIVE : `BP_EMIT_SIL_IDLE;
        end
    end

    always_comb begin
        if (d_cnt == SIL_IDX)
            trans_comb = (p_cnt == SIL_IDX) ? `BP_TRANS_SIL_STAY : `BP_TRANS_NOTE_TO_SIL;
        else if (p_cnt == SIL_IDX)
            trans_comb = `BP_TRANS_SIL_TO_NOTE;
        else
            trans_comb = trans_note((p_cnt > d_cnt) ? (p_cnt[6:0] - d_cnt[6:0])
                                                    : (d_cnt[6:0] - p_cnt[6:0]));
    end

    assign cand_comb     = dp_prev_q + dp_trans_q;
    assign frame_ready_o = (state == S_BINS);
    assign bt_next       = USE_EXTERNAL_STATE ? 7'd0 :
                           bptr_mem[bt_cnt*STATES + bt_state];

    // External DP history is deliberately uncached: CNN latency dominates,
    // and the native controller can update one 16-bit field with byte masks.
    // This keeps only score/emission working sets and the short path in BSRAM.
    always_comb begin
        mem_req_o = 1'b0;
        mem_write_o = 1'b0;
        mem_byte_addr_o = 32'd0;
        mem_wdata_o = 16'd0;
        case (state)
            S_EXT_NOTE: begin
                mem_req_o = 1'b1; mem_write_o = 1'b1;
                mem_byte_addr_o = `BP_DDR_NOTE_BYTE_BASE +
                    (((frame_cnt * NOTE_BINS) + ext_bin_idx) << 1);
                mem_wdata_o = ext_note_q;
            end
            S_EXT_ONSET: begin
                mem_req_o = 1'b1; mem_write_o = 1'b1;
                mem_byte_addr_o = `BP_DDR_ONSET_BYTE_BASE +
                    (((frame_cnt * NOTE_BINS) + ext_bin_idx) << 1);
                mem_wdata_o = {15'd0, ext_onset_q >= `BP_REPEAT_ONSET_THRESH};
            end
            S_EXT_BPTR: begin
                mem_req_o = 1'b1; mem_write_o = 1'b1;
                mem_byte_addr_o = `BP_DDR_BPTR_BYTE_BASE +
                    (((frame_cnt * STATES) + d_cnt) << 1);
                mem_wdata_o = {9'd0, ext_bptr};
            end
            S_EXT_BACK_REQ: begin
                mem_req_o = 1'b1;
                mem_byte_addr_o = `BP_DDR_BPTR_BYTE_BASE +
                    (((bt_cnt * STATES) + bt_state) << 1);
            end
            S_EXT_CMT_ONSET_REQ: begin
                mem_req_o = 1'b1;
                mem_byte_addr_o = `BP_DDR_ONSET_BYTE_BASE +
                    (((cmt_idx * NOTE_BINS) + path_mem[cmt_idx]) << 1);
            end
            S_EXT_CMT_NOTE_REQ: begin
                mem_req_o = 1'b1;
                mem_byte_addr_o = `BP_DDR_NOTE_BYTE_BASE +
                    (((cmt_idx * NOTE_BINS) + path_mem[cmt_idx]) << 1);
            end
            S_SCORE_ONSET_REQ: begin
                mem_req_o = 1'b1;
                mem_byte_addr_o = `BP_DDR_ONSET_BYTE_BASE +
                    (((score_scan * NOTE_BINS) + path_mem[score_scan]) << 1);
            end
            default: begin end
        endcase
    end

    always_ff @(posedge clk_i or negedge rst_ni) begin
        if (!rst_ni) begin
            state <= S_IDLE;
            busy_o <= 1'b0; done_o <= 1'b0; result_valid_o <= 1'b0;
            score_complete_o <= 1'b0;
            result_note_o <= 7'd0; result_conf_o <= 16'd0; result_frame_o <= 16'd0;
            frame_cnt <= 8'd0; peak_note <= 16'sd0;
            dp_prev_q <= 32'sd0; dp_trans_q <= 32'sd0;
            dp_candidate_q <= 32'sd0;
            score_scan <= 8'd0; score_previous <= 7'd0;
            score_previous_valid <= 1'b0;
            score_onset_hot <= 1'b0; score_onset_previous <= 1'b0;
        end else begin
            score_complete_o <= 1'b0;
            case (state)
                S_IDLE: if (start_i) begin
                    busy_o    <= 1'b1;
                    done_o    <= 1'b0;
                    // Keep the completed target stable for the trainer until
                    // the next window is explicitly started.  The trainer's
                    // waiting state makes this a level-safe handshake rather
                    // than a repeated acceptance event.
                    result_valid_o <= 1'b0;
                    frame_cnt <= 8'd0;
                    peak_note <= 16'sd0;
                    state     <= S_BINS;
                end

                S_BINS: begin
                    if (note_valid_i) begin
                        cur_note[note_idx_i] <= note_q_i;
                        if (!USE_EXTERNAL_STATE)
                            note_mem[frame_cnt*NOTE_BINS + note_idx_i] <= note_q_i;
                        if (note_q_i > peak_note) peak_note <= note_q_i;
                    end
                    if (onset_valid_i) begin
                        cur_onset[onset_idx_i] <= onset_q_i;
                        if (!USE_EXTERNAL_STATE)
                            onset_hot_mem[frame_cnt*NOTE_BINS + onset_idx_i] <=
                                onset_q_i >= `BP_REPEAT_ONSET_THRESH;
                    end
                    if (USE_EXTERNAL_STATE && (note_valid_i || onset_valid_i)) begin
                        ext_bin_idx <= note_valid_i ? note_idx_i : onset_idx_i;
                        ext_note_q <= note_q_i;
                        ext_onset_q <= onset_q_i;
                        ext_do_note <= note_valid_i;
                        ext_do_onset <= onset_valid_i;
                        ext_frame_valid <= frame_valid_i;
                        ext_frame_last <= frame_last_i;
                        state <= note_valid_i ? S_EXT_NOTE : S_EXT_ONSET;
                    end else if (frame_valid_i) begin
                        last_frame_q <= frame_last_i;
                        d_cnt        <= 8'd0;
                        state        <= S_LOAD;
                    end
                end

                S_EXT_NOTE: if (mem_ready_i) begin
                    if (ext_do_onset) begin
                        state <= S_EXT_ONSET;
                    end else if (ext_frame_valid) begin
                        last_frame_q <= ext_frame_last;
                        d_cnt <= 8'd0;
                        state <= S_LOAD;
                    end else begin
                        state <= S_BINS;
                    end
                end

                S_EXT_ONSET: if (mem_ready_i) begin
                    if (ext_frame_valid) begin
                        last_frame_q <= ext_frame_last;
                        d_cnt <= 8'd0;
                        state <= S_LOAD;
                    end else begin
                        state <= S_BINS;
                    end
                end

                S_LOAD: begin
                    emission[d_cnt]   <= emit_one_comb;
                    prev_score[d_cnt] <= score[d_cnt];
                    if (d_cnt == STATES-1) begin
                        d_cnt    <= 8'd0;
                        p_cnt    <= 8'd0;
                        best_val <= 32'sh80000000;
                        state    <= (frame_cnt == 8'd0) ? S_SEED : S_FRAME;
                    end else begin
                        d_cnt <= d_cnt + 8'd1;
                    end
                end

                S_SEED: begin
                    score[d_cnt] <= emission[d_cnt];
                    if (d_cnt == STATES-1) begin
                        d_cnt     <= 8'd0;
                        arg_state <= 7'd0;
                        arg_val   <= 32'sh80000000;
                        state     <= last_frame_q ? S_ARG : S_NEXT;
                    end else begin
                        d_cnt <= d_cnt + 8'd1;
                    end
                end

                S_FRAME: begin
                    // Register the RAM/mux read and transition arithmetic.
                    dp_prev_q <= prev_score[p_cnt];
                    dp_trans_q <= trans_comb;
                    state <= S_DP_SUM;
                end

                S_DP_SUM: begin
                    dp_candidate_q <= cand_comb;
                    state <= S_DP_SELECT;
                end

                S_DP_SELECT: begin
                    // Strict > preserves the first predecessor on ties.
                    if (dp_candidate_q > best_val) begin
                        best_val <= dp_candidate_q;
                        best_idx <= p_cnt[6:0];
                    end
                    if (p_cnt == STATES-1) begin
                        // Include the final candidate before the RAM write.
                        state <= S_DP_COMMIT;
                    end else begin
                        p_cnt <= p_cnt + 8'd1;
                        state <= S_FRAME;
                    end
                end

                S_DP_COMMIT: begin
                    score[d_cnt] <= emission[d_cnt] + best_val;
                    p_cnt <= 8'd0;
                    best_val <= 32'sh80000000;
                    if (USE_EXTERNAL_STATE) begin
                        ext_bptr <= best_idx;
                        state <= S_EXT_BPTR;
                    end else begin
                        bptr_mem[frame_cnt*STATES + d_cnt] <= best_idx;
                        if (d_cnt == STATES-1) begin
                            d_cnt <= 8'd0;
                            arg_state <= 7'd0;
                            arg_val <= 32'sh80000000;
                            state <= last_frame_q ? S_ARG : S_NEXT;
                        end else begin
                            d_cnt <= d_cnt + 8'd1;
                            state <= S_FRAME;
                        end
                    end
                end

                S_EXT_BPTR: if (mem_ready_i) begin
                    if (d_cnt == STATES-1) begin
                        d_cnt <= 8'd0;
                        arg_state <= 7'd0;
                        arg_val <= 32'sh80000000;
                        state <= last_frame_q ? S_ARG : S_NEXT;
                    end else begin
                        d_cnt <= d_cnt + 8'd1;
                        state <= S_FRAME;
                    end
                end

                S_NEXT: begin
                    frame_cnt <= frame_cnt + 8'd1;
                    peak_note <= 16'sd0;
                    state     <= S_BINS;
                end

                S_ARG: begin
                    if (score[d_cnt] > arg_val) begin
                        arg_val   <= score[d_cnt];
                        arg_state <= d_cnt[6:0];
                    end
                    if (d_cnt == STATES-1) begin
                        bt_state <= (score[d_cnt] > arg_val) ? d_cnt[6:0] : arg_state;
                        bt_cnt   <= frame_cnt;
                        path_mem[frame_cnt] <=
                            (score[d_cnt] > arg_val) ? d_cnt[6:0] : arg_state;
                        state <= S_BACK;
                    end else begin
                        d_cnt <= d_cnt + 8'd1;
                    end
                end

                S_BACK: begin
                    if (bt_cnt == 8'd0) begin
                        cmt_idx   <= 8'd0;
                        cmt_found <= 1'b0;
                        state     <= S_CMMT;
                    end else if (USE_EXTERNAL_STATE) begin
                        state <= S_EXT_BACK_REQ;
                    end else begin
                        path_mem[bt_cnt - 8'd1] <= bt_next;
                        bt_state <= bt_next;
                        bt_cnt   <= bt_cnt - 8'd1;
                    end
                end

                S_EXT_BACK_REQ: if (mem_ready_i) state <= S_EXT_BACK_WAIT;

                S_EXT_BACK_WAIT: if (mem_rsp_valid_i) begin
                    path_mem[bt_cnt - 8'd1] <= mem_rdata_i[6:0];
                    bt_state <= mem_rdata_i[6:0];
                    bt_cnt <= bt_cnt - 8'd1;
                    state <= S_BACK;
                end

                S_CMMT: begin
                    if (COARSE_GUIDANCE ? (cmt_idx > frame_cnt) : (cmt_idx >= frame_cnt)) begin
                        state <= S_DONE;
                    end else if (path_mem[cmt_idx] == SIL_IDX) begin
                        cmt_idx <= cmt_idx + 8'd1;
                    end else if (COARSE_GUIDANCE) begin
                        if (USE_EXTERNAL_STATE) state<=S_EXT_CMT_NOTE_REQ;
                        else begin
                            cmt_found<=1'b1;cmt_note<=path_mem[cmt_idx];
                            cmt_conf<=note_mem[cmt_idx*NOTE_BINS+path_mem[cmt_idx]];
                            cmt_frame<={8'd0,cmt_idx};state<=S_DONE;
                        end
                    end else if ((cmt_idx + 8'd1 <= frame_cnt) &&
                                 (path_mem[cmt_idx + 8'd1] == path_mem[cmt_idx])) begin
                        if (USE_EXTERNAL_STATE) begin
                            state <= S_EXT_CMT_ONSET_REQ;
                        end else if (!((cmt_idx >= `BP_MIN_RUN_FRAMES) &&
                                      onset_hot_mem[cmt_idx*NOTE_BINS + path_mem[cmt_idx]])) begin
                            cmt_found <= 1'b1;
                            cmt_note  <= path_mem[cmt_idx];
                            cmt_conf  <= note_mem[cmt_idx*NOTE_BINS + path_mem[cmt_idx]];
                            cmt_frame <= {8'd0, cmt_idx};
                            state     <= S_DONE;
                        end else begin
                            cmt_idx <= cmt_idx + 8'd2;
                        end
                    end else begin
                        cmt_idx <= cmt_idx + 8'd2;
                    end
                end

                S_EXT_CMT_ONSET_REQ: if (mem_ready_i) state <= S_EXT_CMT_ONSET_WAIT;

                S_EXT_CMT_ONSET_WAIT: if (mem_rsp_valid_i) begin
                    if ((cmt_idx >= `BP_MIN_RUN_FRAMES) && mem_rdata_i[0]) begin
                        cmt_idx <= cmt_idx + 8'd2;
                        state <= S_CMMT;
                    end else begin
                        state <= S_EXT_CMT_NOTE_REQ;
                    end
                end

                S_EXT_CMT_NOTE_REQ: if (mem_ready_i) state <= S_EXT_CMT_NOTE_WAIT;

                S_EXT_CMT_NOTE_WAIT: if (mem_rsp_valid_i) begin
                    cmt_found <= 1'b1;
                    cmt_note <= path_mem[cmt_idx];
                    cmt_conf <= mem_rdata_i;
                    cmt_frame <= {8'd0, cmt_idx};
                    state <= S_DONE;
                end

                S_DONE: begin
                    if (cmt_found && active_i) begin
                        result_valid_o <= 1'b1;
                        result_note_o  <= cmt_note + 7'd21;   // MIDI offset
                        result_conf_o  <= cmt_conf;
                        result_frame_o <= cmt_frame;
                    end
                    done_o <= 1'b1;
                    busy_o <= 1'b0;
                    score_scan <= cmt_frame[7:0] + 8'd1;
                    score_previous_valid <= 1'b0;
                    score_onset_previous <= 1'b0;
                    state  <= cmt_found && active_i ? S_SCORE_FIRST : S_IDLE;
                    if (!(cmt_found && active_i)) score_complete_o <= 1'b1;
                end
                // The existing commit filter is the authority for the first
                // target. Begin the remaining path scan after that frame.
                S_SCORE_FIRST: if (score_ready_i) begin
                    score_previous <= cmt_note;
                    score_previous_valid <= 1'b1;
                    state <= S_SCORE;
                end

                // Walk the completed path once. Each stable pitch run and
                // each fresh onset within a run becomes one score step. The
                // onset flags already live in the Viterbi DDR state.
                S_SCORE: begin
                    if (COARSE_GUIDANCE ? (score_scan > frame_cnt) : (score_scan >= frame_cnt)) begin
                        state <= S_IDLE;
                        score_complete_o <= 1'b1;
                    end else if (score_pair) begin
                        if (USE_EXTERNAL_STATE)
                            state <= S_SCORE_ONSET_REQ;
                        else begin
                            score_onset_hot <= onset_hot_mem[score_scan*NOTE_BINS + path_mem[score_scan]];
                            state <= S_SCORE_EMIT;
                        end
                    end else begin
                        if (path_mem[score_scan] != score_previous ||
                            path_mem[score_scan] == SIL_IDX) begin
                            score_previous_valid <= 1'b0;
                            score_onset_previous <= 1'b0;
                        end
                        score_scan <= score_scan + 8'd1;
                    end
                end
                S_SCORE_ONSET_REQ: if (mem_ready_i) state <= S_SCORE_ONSET_WAIT;
                S_SCORE_ONSET_WAIT: if (mem_rsp_valid_i) begin
                    score_onset_hot <= mem_rdata_i[0];
                    state <= S_SCORE_EMIT;
                end
                S_SCORE_EMIT: if (!score_new || score_ready_i) begin
                    score_previous <= path_mem[score_scan];
                    score_previous_valid <= 1'b1;
                    score_onset_previous <= score_onset_hot;
                    score_scan <= score_scan + 8'd1;
                    state <= S_SCORE;
                end

                default: state <= S_IDLE;
            endcase
        end
    end
endmodule
