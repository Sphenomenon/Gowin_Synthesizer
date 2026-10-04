`timescale 1ns/1ps
`include "basic_pitch_ddr_map.svh"

// DDR-backed NormalizedLog plane.
//
// CQT results arrive slowly enough that a one-entry write skid buffer can
// commit each raw Q8.8 log magnitude directly to DDR.  Min/max is accumulated
// on that same stream, so normalization only needs one read/modify/write pass.
// The normalized plane remains in DDR; basic_pitch_plane_cache fetches the
// five rows needed by each stacked convolution.
module basic_pitch_normlog_ddr #(
    parameter integer FRAMES = 172,
    parameter integer BINS   = 309
) (
    input  logic               clk_i,
    input  logic               rst_ni,
    input  logic               start_i,
    input  logic               we_i,
    input  logic [15:0]        waddr_i,
    input  logic signed [15:0] wdata_i,
    input  logic signed [15:0] bn_scale_q,
    input  logic signed [15:0] bn_offset_q,
    output logic               busy_o,
    output logic               done_o,
    output logic               overflow_o,
    output logic               mem_req_o,
    output logic               mem_write_o,
    output logic [31:0]        mem_byte_addr_o,
    output logic [15:0]        mem_wdata_o,
    input  logic               mem_ready_i,
    input  logic               mem_rsp_valid_i,
    input  logic [15:0]        mem_rdata_i
);
    localparam integer N = FRAMES * BINS;
    localparam logic [2:0] S_IDLE = 3'd0, S_DRAIN = 3'd1,
        S_READ = 3'd2, S_WAIT = 3'd3, S_DIV = 3'd4,
        S_WRITE = 3'd5, S_DONE = 3'd6;

    logic [2:0] state;
    logic [17:0] idx;
    logic signed [15:0] vmin, vmax;
    logic signed [39:0] num, den, quot, rem;
    logic [5:0] dbit;
    logic raw_pending;
    logic [15:0] raw_addr;
    logic [15:0] raw_data;

    wire signed [39:0] vminx = $signed({{24{vmin[15]}}, vmin});
    wire signed [39:0] vmaxx = $signed({{24{vmax[15]}}, vmax});
    wire signed [39:0] rspx = $signed({{24{mem_rdata_i[15]}}, mem_rdata_i});
    wire signed [39:0] rem2 = (rem << 1) | {{39{1'b0}}, num[dbit[4:0]]};
    wire signed [39:0] bn_w =
        ((quot * $signed({{24{bn_scale_q[15]}}, bn_scale_q})) >>> 12)
        + $signed({{24{bn_offset_q[15]}}, bn_offset_q});
    wire signed [15:0] sat_w = (bn_w > 40'sd32767)  ? 16'sd32767 :
                               (bn_w < -40'sd32768) ? -16'sd32768 : bn_w[15:0];

    assign busy_o = (state != S_IDLE) || raw_pending;

    always_comb begin
        mem_req_o       = 1'b0;
        mem_write_o     = 1'b0;
        mem_byte_addr_o = `BP_DDR_NN_ACT_BYTE_BASE;
        mem_wdata_o     = 16'd0;
        if (((state == S_IDLE) || (state == S_DRAIN)) && raw_pending) begin
            mem_req_o       = 1'b1;
            mem_write_o     = 1'b1;
            mem_byte_addr_o = `BP_DDR_NN_ACT_BYTE_BASE + ({16'd0, raw_addr} << 1);
            mem_wdata_o     = raw_data;
        end else if (state == S_READ) begin
            mem_req_o       = 1'b1;
            mem_byte_addr_o = `BP_DDR_NN_ACT_BYTE_BASE + (idx << 1);
        end else if (state == S_WRITE) begin
            mem_req_o       = 1'b1;
            mem_write_o     = 1'b1;
            mem_byte_addr_o = `BP_DDR_NN_ACT_BYTE_BASE + (idx << 1);
            mem_wdata_o     = sat_w;
        end
    end

    always_ff @(posedge clk_i or negedge rst_ni) begin
        if (!rst_ni) begin
            state <= S_IDLE;
            idx <= '0;
            vmin <= 16'sd32767;
            vmax <= -16'sd32768;
            num <= '0;
            den <= '0;
            quot <= '0;
            rem <= '0;
            dbit <= '0;
            raw_pending <= 1'b0;
            raw_addr <= '0;
            raw_data <= '0;
            overflow_o <= 1'b0;
            done_o <= 1'b0;
        end else begin
            done_o <= 1'b0;

            // An accepted old write and a new CQT sample may coincide; the
            // latter replaces the just-drained skid entry without a bubble.
            if (raw_pending && mem_ready_i &&
                ((state == S_IDLE) || (state == S_DRAIN)))
                raw_pending <= 1'b0;
            if (we_i) begin
                if (raw_pending && !mem_ready_i) overflow_o <= 1'b1;
                raw_pending <= 1'b1;
                raw_addr <= waddr_i;
                raw_data <= wdata_i;
                if (wdata_i < vmin) vmin <= wdata_i;
                if (wdata_i > vmax) vmax <= wdata_i;
            end

            case (state)
                S_IDLE: if (start_i) state <= S_DRAIN;

                S_DRAIN: if (!raw_pending) begin
                    idx <= '0;
                    state <= S_READ;
                end

                S_READ: if (mem_ready_i) state <= S_WAIT;

                S_WAIT: if (mem_rsp_valid_i) begin
                    num  <= (rspx - vminx) * 40'sd32767;
                    den  <= vmaxx - vminx;
                    rem  <= '0;
                    quot <= '0;
                    dbit <= 6'd31;
                    state <= S_DIV;
                end

                S_DIV: begin
                    if (den == 0) begin
                        quot <= 40'sd32767;
                        state <= S_WRITE;
                    end else begin
                        if (rem2 >= den) begin
                            rem <= rem2 - den;
                            quot <= (quot << 1) | 40'sd1;
                        end else begin
                            rem <= rem2;
                            quot <= quot << 1;
                        end
                        if (dbit == 0) state <= S_WRITE;
                        else dbit <= dbit - 1'b1;
                    end
                end

                S_WRITE: if (mem_ready_i) begin
                    if (idx == N - 1) state <= S_DONE;
                    else begin
                        idx <= idx + 1'b1;
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
