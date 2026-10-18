`timescale 1ns/1ps
`include "basic_pitch_fixed_pkg.svh"
// Basic Pitch NormalizedLog followed by the folded BatchNorm.
//
// Operates in place on the 172 x 309 log2-magnitude plane produced by
// basic_pitch_cqt_engine (int16 Q8.8). Two passes:
//   1. find the minimum and maximum over the whole plane,
//   2. per element: v -> (v - min) * 32767 / (max - min)   (Q15, the [0,1] map)
//                        -> v * bn_scale + bn_offset        (Q12 activation)
//
// Using the log2 plane is sufficient: NormalizedLog computes
// (10*log10(p^2) - min) / (max - min), which is affine, so the result is the
// same whether it is formed from log2 or log10.
//
// Harmonic stacking needs no storage: stack[t][f][h] == plane[t][f + shift[h]],
// zero outside [0,309). The head engine applies the shifts in its address
// generation; see BP_HARM_SHIFT_* in the generated weights header.
//
// Status: RTL candidate, unit-simulated; not synthesised or routed here.
module basic_pitch_normlog #(
    parameter int FRAMES = 172,
    parameter int BINS   = 309,
    // Production can use the plane RAM owned by this block directly.  The
    // external read port remains available for the original unit test and for
    // a future dual-port BRAM implementation.
    parameter bit USE_INTERNAL_READ = 1'b0
) (
    input  logic               clk_i,
    input  logic               rst_ni,
    input  logic               start_i,
    input  logic               we_i,          // plane preload / head read port
    input  logic [15:0]        waddr_i,
    input  logic signed [15:0] wdata_i,
    input  logic signed [15:0] bn_scale_q,    // Q4.12
    input  logic signed [15:0] bn_offset_q,   // Q4.12
    output logic               rd_re_o,
    output logic [15:0]        rd_addr_o,
    input  logic signed [15:0] rd_data_i,
    input  logic [15:0]        feature_rd_addr_i,
    output logic signed [15:0] feature_rd_data_o,
    output logic               busy_o,
    output logic               done_o
);
    localparam int N = FRAMES * BINS;

    (* ram_style = "block", syn_ramstyle = "block_ram" *)
    logic signed [15:0] plane [0:N-1];

    localparam logic [3:0] S_IDLE       = 4'd0,
                           S_MINMAX_REQ = 4'd1,
                           S_MINMAX     = 4'd2,
                           S_SETUP_REQ  = 4'd3,
                           S_SETUP      = 4'd4,
                           S_DIV        = 4'd5,
                           S_STORE      = 4'd6,
                           S_DONE       = 4'd7;

    logic [3:0]         state;
    logic [17:0]        idx;
    logic signed [15:0] vmin, vmax;
    logic signed [39:0] num, den, quot, rem;
    logic [5:0]         dbit;
    logic signed [39:0] bn_c;

    assign busy_o    = (state != S_IDLE);
    assign rd_re_o   = (state == S_MINMAX_REQ) || (state == S_MINMAX)
                    || (state == S_SETUP_REQ)  || (state == S_SETUP);
    assign rd_addr_o = idx[15:0];

    wire signed [39:0] vv = $signed({{24{rd_data_i[15]}}, rd_data_i});
    logic signed [15:0] plane_rd_data;
    wire [15:0] plane_rd_addr = (state == S_IDLE || state == S_DONE)
                                ? feature_rd_addr_i : idx[15:0];
    assign feature_rd_data_o = plane_rd_data;
    wire signed [15:0] value_i = USE_INTERNAL_READ ? plane_rd_data : rd_data_i;
    wire signed [39:0] value_ext = $signed({{24{value_i[15]}}, value_i});
    wire signed [39:0] vminx = $signed({{24{vmin[15]}}, vmin});
    wire signed [39:0] vmaxx = $signed({{24{vmax[15]}}, vmax});

    // BatchNorm on the Q15 normalised value, saturated to the Q12 activation range
    // NOTE: in Verilog '>>>' binds looser than '+', so the shift amount MUST be
    // parenthesised.  `a >>> 12 + b` means `a >>> (12 + b)`, which with a
    // negative b shifts by a negative amount and silently yields zero.
    wire signed [39:0] bn_w = ((quot * $signed({{24{bn_scale_q[15]}}, bn_scale_q})) >>> 12)
                              + $signed({{24{bn_offset_q[15]}}, bn_offset_q});
    wire signed [15:0] sat_w = (bn_w > 40'sd32767)      ? 16'sd32767 :
                               (bn_w < -40'sd32768)     ? -16'sd32768 : bn_w[15:0];
    // restoring-division trial remainder, formed combinationally so the
    // comparison below sees this cycle's value, not the previous one
    // restoring division consumes the dividend MSB-first, so the bit index is
    // dbit itself, not (31 - dbit)
    wire signed [39:0] rem2 = (rem << 1) | {{39{1'b0}}, num[dbit[4:0]]};

    always_ff @(posedge clk_i or negedge rst_ni) begin
        if (!rst_ni) begin
            state <= S_IDLE; idx <= '0; done_o <= 1'b0;
            vmin <= 16'sd32767; vmax <= -16'sd32768;
            num <= '0; den <= '0; quot <= '0; rem <= '0; dbit <= '0;
        end else begin
            done_o <= 1'b0;
            // One registered read port plus one write port is a legal BSRAM
            // pattern.  The request states below account for the read latency.
            if (plane_rd_addr < N) plane_rd_data <= plane[plane_rd_addr];
            else                   plane_rd_data <= 16'sd0;
            if (we_i)                  plane[waddr_i[15:0]] <= wdata_i;
            else if (state == S_STORE) plane[idx[15:0]] <= sat_w;

            case (state)
                S_IDLE: if (start_i) begin
                    idx  <= '0;
                    vmin <= 16'sd32767;
                    vmax <= -16'sd32768;
                    state <= S_MINMAX_REQ;
                end

                S_MINMAX_REQ: state <= S_MINMAX;

                // pass 1: global min / max over the whole plane
                S_MINMAX: begin
                    if (value_i < vmin) vmin <= value_i;
                    if (value_i > vmax) vmax <= value_i;
                    if (idx == N - 1) begin
                        idx   <= '0;
                        state <= S_SETUP_REQ;
                    end else begin
                        idx <= idx + 1'b1;
                        state <= S_MINMAX_REQ;
                    end
                end

                S_SETUP_REQ: state <= S_SETUP;

                // pass 2, per element: latch dividend/divisor, start the divide
                S_SETUP: begin
                    num  <= (value_ext - vminx) * 40'sd32767;
                    den  <= vmaxx - vminx;
                    rem  <= '0;
                    quot <= '0;
                    dbit <= 6'd31;
                    state <= S_DIV;
                end

                S_DIV: begin
                    if (den == 0) begin
                        quot  <= 40'sd32767;          // flat plane
                        state <= S_STORE;
                    end else begin
                        if (rem2 >= den) begin
                            rem  <= rem2 - den;
                            quot <= (quot << 1) | 40'sd1;
                        end else begin
                            rem  <= rem2;
                            quot <= quot << 1;
                        end
                        if (dbit == 6'd0) state <= S_STORE;   // 32 bits, 31..0
                        else              dbit  <= dbit - 6'd1;
                    end
                end

                S_STORE: begin
                    if (idx == N - 1) begin
                        state <= S_DONE;
                    end else begin
                        idx   <= idx + 1'b1;
                        state <= S_SETUP_REQ;
                    end
                end

                S_DONE: begin
                    done_o <= 1'b1;
                    state  <= S_IDLE;
                end

                default: state <= S_IDLE;
            endcase
        end
    end
endmodule
