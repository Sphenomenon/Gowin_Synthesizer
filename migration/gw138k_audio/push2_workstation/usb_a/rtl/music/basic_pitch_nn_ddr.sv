`timescale 1ns/1ps
`include "basic_pitch_ddr_map.svh"

// Cacheless CNN backing store. One 16-bit DDR transaction is issued at a time;
// the only local model/feature storage is the current MAC operands and one
// pending output word. Layer ids follow pipeline execution order.
module basic_pitch_nn_ddr (
    input  logic        clk_i,
    input  logic        rst_ni,
    input  logic [2:0]  layer_i,
    input  logic        sample_req_i,
    input  logic        input_in_range_i,
    input  logic [15:0] plane_addr_i,
    input  logic [23:0] x_addr_i,
    input  logic [23:0] x_cell_addr_i,
    input  logic [7:0]  x_channel_i,
    input  logic [17:0] weight_addr_i,
    output logic        sample_valid_o,
    output logic signed [15:0] sample_x_o,
    output logic signed [15:0] sample_w_o,
    input  logic        bias_req_i,
    input  logic [8:0]  bias_addr_i,
    output logic        bias_valid_o,
    output logic signed [31:0] bias_o,
    input  logic        write_valid_i,
    input  logic [2:0]  write_layer_i,
    input  logic [8:0]  write_row_i,
    input  logic [8:0]  write_col_i,
    input  logic [8:0]  write_channel_i,
    input  logic [15:0] write_data_i,
    output logic        write_overflow_o,
    output logic        idle_o,
    output logic [3:0]  status_o,
    input  logic        feed_req_i,
    input  logic [8:0]  feed_row_i,
    input  logic [6:0]  feed_col_i,
    output logic        feed_valid_o,
    output logic [15:0] feed_note_o,
    output logic [15:0] feed_onset_o,
    input  logic        feed_accept_i,
    output logic        mem_req_o,
    output logic        mem_write_o,
    output logic [31:0] mem_byte_addr_o,
    output logic [15:0] mem_wdata_o,
    input  logic        mem_ready_i,
    input  logic        mem_rsp_valid_i,
    input  logic [15:0] mem_rdata_i
);
    localparam logic [3:0] IDLE=0, SEND_W=1, WAIT_W=2,
        SEND_X=3, WAIT_X=4, SAMPLE_READY=5,
        SEND_B0=6, WAIT_B0=7, SEND_B1=8, WAIT_B1=9,
        BIAS_READY=10, SEND_NOTE=11, WAIT_NOTE=12,
        SEND_ONSET=13, WAIT_ONSET=14, FEED_READY=15;
    logic [3:0] state;
    logic write_pending;
    logic [31:0] write_addr;
    logic [15:0] write_data;
    logic [31:0] weight_byte_addr, input_byte_addr, bias_byte_addr;
    logic [31:0] read_addr;

    function automatic [14:0] weight_base(input logic [2:0] layer);
        case (layer)
            0: weight_base = 15'd0;
            1: weight_base = 15'd7488;
            2: weight_base = 15'd7688;
            3: weight_base = 15'd9256;
            4: weight_base = 15'd9928;
            default: weight_base = 15'd16328;
        endcase
    endfunction

    function automatic [6:0] bias_base(input logic [2:0] layer);
        case (layer)
            0: bias_base = 7'd0;
            1: bias_base = 7'd8;
            2: bias_base = 7'd9;
            3: bias_base = 7'd41;
            4: bias_base = 7'd42;
            default: bias_base = 7'd74;
        endcase
    endfunction

    function automatic [31:0] feature_base(input logic [2:0] layer);
        case (layer)
            0: feature_base = `BP_DDR_NN_CONTOUR_BYTE_BASE;
            1: feature_base = `BP_DDR_NN_REDUCE_BYTE_BASE;
            2: feature_base = `BP_DDR_NN_NOTES_BYTE_BASE;
            3: feature_base = `BP_DDR_NN_NOTE_POST_BYTE_BASE;
            4: feature_base = `BP_DDR_NN_ONSET_BYTE_BASE;
            default: feature_base = `BP_DDR_NN_ONSET_POST_BYTE_BASE;
        endcase
    endfunction

    function automatic [5:0] channels(input logic [2:0] layer);
        case (layer)
            0: channels = 6'd8;
            2, 4: channels = 6'd32;
            default: channels = 6'd1;
        endcase
    endfunction

    function automatic [8:0] layer_bins(input logic [2:0] layer);
        case (layer)
            0, 1: layer_bins = 9'd264;
            default: layer_bins = 9'd88;
        endcase
    endfunction

    always_comb begin
        weight_byte_addr = `BP_DDR_NN_MODEL_BYTE_BASE +
            (({17'd0, weight_base(layer_i)} + weight_addr_i) << 1);
        bias_byte_addr = `BP_DDR_NN_MODEL_BYTE_BASE +
            ((32'd20721 + ((bias_base(layer_i) + bias_addr_i) << 1)) << 1);
        case (layer_i)
            0, 4: input_byte_addr = `BP_DDR_NN_ACT_BYTE_BASE + (plane_addr_i << 1);
            1: input_byte_addr = `BP_DDR_NN_CONTOUR_BYTE_BASE + (x_addr_i << 1);
            2: input_byte_addr = `BP_DDR_NN_REDUCE_BYTE_BASE + (x_addr_i << 1);
            3: input_byte_addr = `BP_DDR_NN_NOTES_BYTE_BASE + (x_addr_i << 1);
            default: input_byte_addr = (x_channel_i == 0) ?
                (`BP_DDR_NN_NOTE_POST_BYTE_BASE + (x_cell_addr_i << 1)) :
                (`BP_DDR_NN_ONSET_BYTE_BASE +
                 (((x_cell_addr_i * 32) + x_channel_i - 1'b1) << 1));
        endcase
        case (state)
            SEND_W:     read_addr = weight_byte_addr;
            SEND_X:     read_addr = input_byte_addr;
            SEND_B0:    read_addr = bias_byte_addr;
            SEND_B1:    read_addr = bias_byte_addr + 32'd2;
            SEND_NOTE:  read_addr = `BP_DDR_NN_NOTE_POST_BYTE_BASE +
                (((feed_row_i * 88) + feed_col_i) << 1);
            default:    read_addr = `BP_DDR_NN_ONSET_POST_BYTE_BASE +
                (((feed_row_i * 88) + feed_col_i) << 1);
        endcase
        mem_req_o = write_pending || state == SEND_W || state == SEND_X ||
            state == SEND_B0 || state == SEND_B1 || state == SEND_NOTE ||
            state == SEND_ONSET;
        mem_write_o = write_pending;
        mem_byte_addr_o = write_pending ? write_addr : read_addr;
        mem_wdata_o = write_data;
    end

    assign sample_valid_o = state == SAMPLE_READY;
    assign bias_valid_o = state == BIAS_READY;
    assign feed_valid_o = state == FEED_READY;
    assign idle_o = !write_pending && state == IDLE;
    assign status_o = state;

    always_ff @(posedge clk_i or negedge rst_ni) begin
        if (!rst_ni) begin
            state <= IDLE;
            write_pending <= 1'b0;
            write_addr <= 0;
            write_data <= 0;
            write_overflow_o <= 1'b0;
            sample_x_o <= 0;
            sample_w_o <= 0;
            bias_o <= 0;
            feed_note_o <= 0;
            feed_onset_o <= 0;
        end else begin
            if (write_pending && mem_ready_i) write_pending <= 1'b0;
            if (write_valid_i) begin
                if (write_pending && !mem_ready_i) write_overflow_o <= 1'b1;
                write_pending <= 1'b1;
                write_addr <= feature_base(write_layer_i) +
                    (((((write_row_i * layer_bins(write_layer_i)) + write_col_i) *
                        channels(write_layer_i)) + write_channel_i) << 1);
                write_data <= write_data_i;
            end
            case (state)
                IDLE: begin
                    if (sample_req_i) state <= SEND_W;
                    else if (bias_req_i) state <= SEND_B0;
                    else if (feed_req_i && !write_pending) state <= SEND_NOTE;
                end
                SEND_W: if (!write_pending && mem_ready_i) state <= WAIT_W;
                WAIT_W: if (mem_rsp_valid_i) begin
                    sample_w_o <= mem_rdata_i;
                    if (input_in_range_i) state <= SEND_X;
                    else begin sample_x_o <= 16'sd0; state <= SAMPLE_READY; end
                end
                SEND_X: if (!write_pending && mem_ready_i) state <= WAIT_X;
                WAIT_X: if (mem_rsp_valid_i) begin
                    sample_x_o <= mem_rdata_i;
                    state <= SAMPLE_READY;
                end
                SAMPLE_READY: if (!sample_req_i) state <= IDLE;
                SEND_B0: if (!write_pending && mem_ready_i) state <= WAIT_B0;
                WAIT_B0: if (mem_rsp_valid_i) begin
                    bias_o[15:0] <= mem_rdata_i;
                    state <= SEND_B1;
                end
                SEND_B1: if (!write_pending && mem_ready_i) state <= WAIT_B1;
                WAIT_B1: if (mem_rsp_valid_i) begin
                    bias_o[31:16] <= mem_rdata_i;
                    state <= BIAS_READY;
                end
                BIAS_READY: if (!bias_req_i) state <= IDLE;
                SEND_NOTE: if (!write_pending && mem_ready_i) state <= WAIT_NOTE;
                WAIT_NOTE: if (mem_rsp_valid_i) begin
                    feed_note_o <= mem_rdata_i;
                    state <= SEND_ONSET;
                end
                SEND_ONSET: if (!write_pending && mem_ready_i) state <= WAIT_ONSET;
                WAIT_ONSET: if (mem_rsp_valid_i) begin
                    feed_onset_o <= mem_rdata_i;
                    state <= FEED_READY;
                end
                // The pipeline may leave the feed phase on the same edge that
                // consumes its final bin. Release a held result once that
                // phase is over so the next row can request CNN operands.
                FEED_READY: if (feed_accept_i || !feed_req_i) state <= IDLE;
                default: state <= IDLE;
            endcase
        end
    end
endmodule
