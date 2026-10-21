`timescale 1ns/1ps
`include "basic_pitch_fixed_pkg.svh"
// Finite-window Basic Pitch CNN/DP boundary.
//
// The front-end/CNN scheduler presents one frame's fixed-point head results
// on the note/onset/contour ingress ports.  This block owns the bounded
// posterior lifetime: note and onset bins are consumed immediately by the
// Viterbi engine, while contour is retained only in a 19-row rolling buffer.
// No song-sized note table or path is created here.  The production scheduler
// may drive the ingress from basic_pitch_cqt_engine + the six time-multiplexed
// head layers; the interface is deliberately identical to the frame stream
// used by the software/RTL guidance testbench.
//
// A separate ingress boundary is useful in the 138K design: it lets the CQT
// and head engines run with back-pressure while this module remains a small,
// timing-friendly DP consumer.  `frame_valid_i` closes one frame only after
// all selected bins have been presented.
module basic_pitch_cnn_streaming #(
    parameter integer FRAMES = 172,
    parameter integer NOTE_BINS = 88,
    parameter integer CONTOUR_BINS = 264,
    parameter integer ROW_BUFFER_ROWS = 19,
    parameter bit COARSE_GUIDANCE=1'b0,
    parameter bit USE_EXTERNAL_STATE = 1'b0
) (
    input  logic clk_i,
    input  logic rst_ni,
    input  logic start_i,
    input  logic active_i,
    input  logic note_valid_i,
    input  logic [6:0] note_idx_i,
    input  logic signed [15:0] note_q_i,
    input  logic onset_valid_i,
    input  logic [6:0] onset_idx_i,
    input  logic signed [15:0] onset_q_i,
    input  logic contour_valid_i,
    input logic [8:0] contour_idx_i,
    input logic signed [15:0] contour_q_i,
    input logic frame_valid_i,
    input logic frame_last_i,
    output logic frame_ready_o,
    output logic [7:0] frame_index_o,
    output logic note_we_o,
    output logic [6:0] note_addr_o,
    output logic signed [15:0] note_data_o,
    output logic onset_we_o,
    output logic [6:0] onset_addr_o,
    output logic signed [15:0] onset_data_o,
    output logic contour_we_o,
    output logic [8:0] contour_addr_o,
    output logic signed [15:0] contour_data_o,
    output logic result_valid_o,
    output logic [6:0] result_note_o,
    output logic [15:0] result_conf_o,
    output logic [15:0] result_frame_o,
    output logic score_valid_o,
    input  logic score_ready_i,
    output logic [6:0] score_note_o,
    output logic score_complete_o,
    output logic done_o,
    output logic busy_o,
    output logic mem_req_o,
    output logic mem_write_o,
    output logic [31:0] mem_byte_addr_o,
    output logic [15:0] mem_wdata_o,
    input  logic mem_ready_i,
    input  logic mem_rsp_valid_i,
    input  logic [15:0] mem_rdata_i
);
    localparam integer ROW_AW = (ROW_BUFFER_ROWS <= 1) ? 1 : $clog2(ROW_BUFFER_ROWS);
    localparam integer CONTOUR_AW = (CONTOUR_BINS <= 1) ? 1 : $clog2(CONTOUR_BINS);

    logic [7:0] frame_index_q;
    logic [ROW_AW-1:0] contour_row_q;
    logic contour_read;
    logic signed [15:0] contour_read_data;

    // The contour output is not needed by the DP, but retaining it in this
    // bounded store makes the output head observable without allocating the
    // complete 172x264 tensor.  A 19-row window covers the documented maximum
    // chained convolution dependency radius.
    basic_pitch_row_buffer #(
        .ROWS(ROW_BUFFER_ROWS), .COLS(CONTOUR_BINS), .DATA_WIDTH(16)
    ) u_contour_rows (
        .clk_i(clk_i), .rst_ni(rst_ni),
        .write_i(contour_valid_i && frame_ready_o),
        .write_row_i(contour_row_q), .write_col_i(contour_idx_i[CONTOUR_AW-1:0]),
        .write_data_i(contour_q_i),
        .read_i(contour_read), .read_row_i(contour_row_q),
        .read_col_i(contour_idx_i[CONTOUR_AW-1:0]),
        .read_data_o(contour_read_data)
    );

    basic_pitch_viterbi #(.NOTE_BINS(NOTE_BINS), .FRAMES(FRAMES),
                          .COARSE_GUIDANCE(COARSE_GUIDANCE),.USE_EXTERNAL_STATE(USE_EXTERNAL_STATE)) u_viterbi (
        .clk_i(clk_i), .rst_ni(rst_ni), .start_i(start_i), .active_i(active_i),
        .note_valid_i(note_valid_i && frame_ready_o), .note_idx_i(note_idx_i), .note_q_i(note_q_i),
        .onset_valid_i(onset_valid_i && frame_ready_o), .onset_idx_i(onset_idx_i), .onset_q_i(onset_q_i),
        .frame_valid_i(frame_valid_i && frame_ready_o), .frame_last_i(frame_last_i),
        .frame_ready_o(frame_ready_o), .result_valid_o(result_valid_o),
        .result_note_o(result_note_o), .result_conf_o(result_conf_o),
        .result_frame_o(result_frame_o),
        .score_valid_o(score_valid_o), .score_ready_i(score_ready_i),
        .score_note_o(score_note_o), .score_complete_o(score_complete_o),
        .done_o(done_o), .busy_o(busy_o),
        .mem_req_o(mem_req_o), .mem_write_o(mem_write_o),
        .mem_byte_addr_o(mem_byte_addr_o), .mem_wdata_o(mem_wdata_o),
        .mem_ready_i(mem_ready_i), .mem_rsp_valid_i(mem_rsp_valid_i),
        .mem_rdata_i(mem_rdata_i)
    );

    assign note_we_o = note_valid_i && frame_ready_o;
    assign note_addr_o = note_idx_i;
    assign note_data_o = note_q_i;
    assign onset_we_o = onset_valid_i && frame_ready_o;
    assign onset_addr_o = onset_idx_i;
    assign onset_data_o = onset_q_i;
    assign contour_we_o = contour_valid_i && frame_ready_o;
    assign contour_addr_o = contour_idx_i;
    assign contour_data_o = contour_q_i;
    assign frame_index_o = frame_index_q;
    assign contour_read = 1'b0;

    always_ff @(posedge clk_i or negedge rst_ni) begin
        if (!rst_ni) begin
            frame_index_q <= 8'd0;
            contour_row_q <= '0;
        end else if (start_i) begin
            frame_index_q <= 8'd0;
            contour_row_q <= '0;
        end else if (frame_valid_i && frame_ready_o) begin
            frame_index_q <= frame_index_q + 1'b1;
            if (contour_row_q == ROW_BUFFER_ROWS - 1)
                contour_row_q <= '0;
            else
                contour_row_q <= contour_row_q + 1'b1;
        end
    end
endmodule
