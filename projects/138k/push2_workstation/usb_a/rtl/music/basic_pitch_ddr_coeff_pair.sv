`timescale 1ns/1ps
`include "basic_pitch_ddr_map.svh"

// Fetch two 16-bit coefficient words from the uploaded model image.
// valid_o remains asserted until the consumer drops req_i.
module basic_pitch_ddr_coeff_pair #(
    parameter integer FIRST_WORD = 0,
    parameter integer SECOND_WORD = 1,
    parameter integer STRIDE = 1
) (
    input  logic        clk_i,
    input  logic        rst_ni,
    input  logic        req_i,
    input  logic [13:0] index_i,
    output logic        valid_o,
    output logic [15:0] first_o,
    output logic [15:0] second_o,
    output logic        mem_req_o,
    output logic [31:0] mem_addr_o,
    input  logic        mem_ready_i,
    input  logic        mem_rsp_valid_i,
    input  logic [15:0] mem_rdata_i
);
    localparam logic [2:0] IDLE=0, FIRST_REQ=1, FIRST_WAIT=2,
                           SECOND_REQ=3, SECOND_WAIT=4, READY=5;
    logic [2:0] state;
    logic [13:0] index;
    wire [31:0] word_index = (state == SECOND_REQ ? SECOND_WORD : FIRST_WORD)
                             + ({18'd0,index} * STRIDE);
    assign mem_req_o = (state == FIRST_REQ || state == SECOND_REQ);
    assign mem_addr_o = `BP_DDR_NN_MODEL_BYTE_BASE + (word_index << 1);
    assign valid_o = (state == READY);

    always_ff @(posedge clk_i or negedge rst_ni) begin
        if (!rst_ni) begin
            state <= IDLE;
            index <= 0;
            first_o <= 0;
            second_o <= 0;
        end else case (state)
            IDLE: if (req_i) begin index <= index_i; state <= FIRST_REQ; end
            FIRST_REQ: if (mem_ready_i) state <= FIRST_WAIT;
            FIRST_WAIT: if (mem_rsp_valid_i) begin
                first_o <= mem_rdata_i;
                state <= SECOND_REQ;
            end
            SECOND_REQ: if (mem_ready_i) state <= SECOND_WAIT;
            SECOND_WAIT: if (mem_rsp_valid_i) begin
                second_o <= mem_rdata_i;
                state <= READY;
            end
            READY: if (!req_i) state <= IDLE;
            default: state <= IDLE;
        endcase
    end
endmodule
