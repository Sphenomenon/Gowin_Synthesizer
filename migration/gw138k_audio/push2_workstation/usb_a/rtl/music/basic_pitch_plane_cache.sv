`timescale 1ns/1ps
`include "basic_pitch_ddr_map.svh"

// Five-row read cache for the DDR-backed normalized CQT plane.  A fill is
// performed immediately before either stacked CNN head starts, keeping only
// the latency-critical working set in BSRAM.
module basic_pitch_plane_cache #(
    parameter integer FRAMES = 172,
    parameter integer BINS   = 309,
    parameter integer ROWS   = 5
) (
    input  logic               clk_i,
    input  logic               rst_ni,
    input  logic               start_i,
    input  logic [8:0]         center_row_i,
    input  logic [15:0]        feature_addr_i,
    output logic signed [15:0] feature_data_o,
    output logic               busy_o,
    output logic               done_o,
    output logic               mem_req_o,
    output logic               mem_write_o,
    output logic [31:0]        mem_byte_addr_o,
    output logic [15:0]        mem_wdata_o,
    input  logic               mem_ready_i,
    input  logic               mem_rsp_valid_i,
    input  logic [15:0]        mem_rdata_i
);
    localparam integer CACHE_WORDS = ROWS * BINS;
    localparam logic [2:0] S_IDLE = 3'd0, S_ROW = 3'd1,
        S_READ = 3'd2, S_WAIT = 3'd3, S_DONE = 3'd4;

    (* ram_style = "block", syn_ramstyle = "block_ram" *)
    logic signed [15:0] cache [0:CACHE_WORDS-1];
    logic [2:0] state;
    logic [2:0] slot;
    logic [8:0] col;
    logic signed [10:0] load_row;
    logic signed [17:0] base_word;
    logic signed [18:0] load_byte_offset;
    wire signed [18:0] feature_rel = $signed({3'b000, feature_addr_i})
                                              - $signed(base_word);
    wire signed [17:0] center_base_word =
        ($signed({9'd0, center_row_i}) * BINS) - (2*BINS);

    assign busy_o = state != S_IDLE;
    assign mem_req_o = state == S_READ;
    assign mem_write_o = 1'b0;
    assign mem_byte_addr_o = `BP_DDR_NN_ACT_BYTE_BASE
                             + load_byte_offset + ({10'd0, col} << 1);
    assign mem_wdata_o = 16'd0;

    // The five cached rows are contiguous and ordered.  Subtracting the
    // registered first-row address produces the cache address directly; this
    // deliberately avoids synthesizing /309 and %309 into the 50-MHz path.
    always_ff @(posedge clk_i) begin
        if ((feature_addr_i < FRAMES*BINS) &&
            (feature_rel >= 0) && (feature_rel < CACHE_WORDS))
            feature_data_o <= cache[feature_rel];
        else
            feature_data_o <= 16'sd0;
    end

    always_ff @(posedge clk_i or negedge rst_ni) begin
        if (!rst_ni) begin
            state <= S_IDLE;
            slot <= '0;
            col <= '0;
            load_row <= '0;
            base_word <= '0;
            load_byte_offset <= '0;
            done_o <= 1'b0;
        end else begin
            done_o <= 1'b0;
            case (state)
                S_IDLE: if (start_i) begin
                    slot <= '0;
                    col <= '0;
                    load_row <= $signed({2'b00, center_row_i}) - 11'sd2;
                    base_word <= center_base_word;
                    load_byte_offset <= center_base_word <<< 1;
                    state <= S_ROW;
                end

                S_ROW: begin
                    col <= '0;
                    if ((load_row < 0) || (load_row >= FRAMES)) begin
                        if (slot == ROWS - 1) state <= S_DONE;
                        else begin
                            slot <= slot + 1'b1;
                            load_row <= load_row + 1'b1;
                            load_byte_offset <= load_byte_offset + (2*BINS);
                        end
                    end else begin
                        state <= S_READ;
                    end
                end

                S_READ: if (mem_ready_i) state <= S_WAIT;

                S_WAIT: if (mem_rsp_valid_i) begin
                    cache[slot*BINS + col] <= mem_rdata_i;
                    if (col == BINS - 1) begin
                        if (slot == ROWS - 1) state <= S_DONE;
                        else begin
                            slot <= slot + 1'b1;
                            load_row <= load_row + 1'b1;
                            load_byte_offset <= load_byte_offset + (2*BINS);
                            state <= S_ROW;
                        end
                    end else begin
                        col <= col + 1'b1;
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
