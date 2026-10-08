`timescale 1ns/1ps
`include "basic_pitch_ddr_map.svh"

// Shared cache for one CNN layer's weights.  The largest layer is contour at
// 7488 int16 words, so all six heads reuse the same eight BSRAM blocks.
module basic_pitch_weight_cache #(
    parameter integer MAX_WORDS = 7488
) (
    input  logic        clk_i,
    input  logic        rst_ni,
    input  logic        start_i,
    input  logic [14:0] blob_word_base_i,
    input  logic [13:0] word_count_i,
    input  logic [17:0] read_addr_i,
    output logic signed [15:0] read_data_o,
    output logic        busy_o,
    output logic        done_o,
    output logic        mem_req_o,
    output logic        mem_write_o,
    output logic [31:0] mem_byte_addr_o,
    output logic [15:0] mem_wdata_o,
    input  logic        mem_ready_i,
    input  logic        mem_rsp_valid_i,
    input  logic [15:0] mem_rdata_i
);
    localparam logic [2:0] S_IDLE=3'd0, S_READ=3'd1, S_WAIT=3'd2,
                           S_DONE=3'd3;
    (* ram_style = "block", syn_ramstyle = "block_ram" *)
    logic signed [15:0] cache [0:MAX_WORDS-1];
    localparam integer READ_ADDR_BITS = MAX_WORDS <= 1 ? 1 : $clog2(MAX_WORDS);
    logic signed [15:0] read_data_q;
    logic read_valid_q;
    logic [2:0] state;
    logic [14:0] blob_base;
    logic [13:0] count;
    logic [13:0] index;

    assign busy_o = state != S_IDLE;
    assign mem_req_o = state == S_READ;
    assign mem_write_o = 1'b0;
    assign mem_byte_addr_o = `BP_DDR_NN_MODEL_BYTE_BASE
                           + (({17'd0, blob_base} + {18'd0, index}) << 1);
    assign mem_wdata_o = 16'd0;

    always_ff @(posedge clk_i) begin
        // Keep the variable address range check off the BSRAM synchronous
        // RESET pin. Data and validity are captured together, preserving the
        // original one-cycle output and invalid-address zero semantics.
        read_data_q <= cache[read_addr_i[READ_ADDR_BITS-1:0]];
        read_valid_q <= read_addr_i < MAX_WORDS;
    end

    assign read_data_o = read_valid_q ? read_data_q : 16'sd0;

    always_ff @(posedge clk_i or negedge rst_ni) begin
        if (!rst_ni) begin
            state <= S_IDLE;
            blob_base <= '0;
            count <= '0;
            index <= '0;
            done_o <= 1'b0;
        end else begin
            done_o <= 1'b0;
            case (state)
                S_IDLE: if (start_i) begin
                    blob_base <= blob_word_base_i;
                    count <= word_count_i;
                    index <= '0;
                    state <= S_READ;
                end
                S_READ: if (mem_ready_i) state <= S_WAIT;
                S_WAIT: if (mem_rsp_valid_i) begin
                    cache[index] <= mem_rdata_i;
                    if (index == count - 1'b1) state <= S_DONE;
                    else begin
                        index <= index + 1'b1;
                        state <= S_READ;
                    end
                end
                S_DONE: begin
                    done_o <= 1'b1;
                    state <= S_IDLE;
                end
                default: state <= S_IDLE;
            endcase
        end
    end
endmodule
