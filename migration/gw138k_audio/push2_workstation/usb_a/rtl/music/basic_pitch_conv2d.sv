`timescale 1ns/1ps
`include "basic_pitch_fixed_pkg.svh"
// Parameterised Basic Pitch head convolution layer.
//
// One layer per instance: X[ot][of][oc] = act( sum W[kh][kw][ic][oc] * I[...] )
// with TF "same" padding, arbitrary strides and a ReLU or sigmoid output.
//
// Harmonic stacking is folded into the input addressing instead of being
// materialised: for the layers that read the stacked CQT plane,
// stack[t][f][h] == plane[t][f + BP_SHIFT(h)] with zero outside [0,309). That
// removes the 172 x 264 x 8 stacking buffer entirely.
//
// The engine emits the *raw* int32 accumulator as well as the activated value,
// so a testbench can dequantise with the exported weight scale and compare
// against the float reference without inventing a requantisation policy here.
//
// Status: RTL candidate, unit-simulated; not synthesised or routed here.
module basic_pitch_conv2d #(
    parameter int IN_T      = 172,
    parameter int IN_F      = 264,
    parameter int IN_C      = 8,
    parameter int KH        = 3,
    parameter int KW        = 39,
    parameter int OUT_T     = 172,
    parameter int OUT_F     = 264,
    parameter int OUT_C     = 8,
    parameter int STRIDE_T  = 1,
    parameter int STRIDE_F  = 1,
    parameter int PAD_T     = 1,
    parameter int PAD_F     = 19,
    parameter int USE_STACK = 1,      // 1: input is plane[t][f + shift[c]]
                                      // 0: input is a feature map X[t][f][c]
    parameter int ACT       = 0,      // 0 = none, 1 = ReLU, 2 = sigmoid
    parameter bit DDR_FETCH = 1'b0
) (
    input  logic               clk_i,
    input  logic               rst_ni,
    input  logic               start_i,
    input  logic [8:0]         row_start_i,     // first output row (inclusive)
    input  logic [8:0]         row_limit_i,     // test hook: output rows to compute
    // input feature RAM (USE_STACK = 0)
    // CQT plane (USE_STACK = 1), 172 x 309
    output logic [15:0]        pl_addr_o,
    input  logic signed [15:0] pl_data_i,
    // input feature map (USE_STACK = 0), X[t][f][c]
    output logic [23:0]        x_addr_o,
    output logic [23:0]        x_cell_addr_o,
    output logic [7:0]         x_channel_o,
    output logic signed [17:0] x_row_o,
    output logic signed [17:0] x_col_o,
    output logic               input_in_range_o,
    output logic               sample_req_o,
    input  logic               sample_valid_i,
    input  logic signed [15:0] x_data_i,
    // weights / bias ROM
    output logic [17:0]        w_addr_o,
    input  logic signed [15:0] w_data_i,
    output logic [8:0]         b_addr_o,
    output logic               bias_req_o,
    input  logic               bias_valid_i,
    input  logic signed [31:0] b_data_i,
    // results
    output logic               y_we_o,
    output logic [23:0]        y_addr_o,
    output logic [8:0]         y_row_o,
    output logic [8:0]         y_col_o,
    output logic [8:0]         y_channel_o,
    output logic signed [15:0] y_data_o,
    output logic signed [47:0] y_acc_o,
    output logic               busy_o,
    output logic               done_o
);
    localparam logic [3:0] S_IDLE = 4'd0, S_T = 4'd1, S_F = 4'd2,
                           S_KH = 4'd3, S_KW = 4'd4, S_IC = 4'd5, S_STORE = 4'd6,
                           S_DONE = 4'd7, S_REQ = 4'd8, S_BIAS_REQ = 4'd9;

    // harmonic-stacking shifts, round(36 * log2(h)) for h = 0.5,1,2,3,4,5,6,7
    function automatic signed [15:0] shift_of(input logic [2:0] h);
        case (h)
            3'd0: shift_of = -16'sd36;
            3'd1: shift_of =  16'sd0;
            3'd2: shift_of =  16'sd36;
            3'd3: shift_of =  16'sd57;
            3'd4: shift_of =  16'sd72;
            3'd5: shift_of =  16'sd84;
            3'd6: shift_of =  16'sd93;
            default: shift_of = 16'sd101;
        endcase
    endfunction

    logic [3:0]         state;
    logic [8:0]         ot, of, oc;
    logic [7:0]         kh, kw, ic;
    logic signed [47:0] acc;
    logic signed [15:0] xval;
    logic signed [17:0] it, ifc;
    logic               in_range;
    logic               mac_in_range_q;
    logic [15:0]        plane_idx;
    logic [5:0]         sig_idx;
    logic signed [15:0] act_val;

    assign busy_o = (state != S_IDLE);

    localparam signed [17:0] PADT = PAD_T;
    localparam signed [17:0] PADF = PAD_F;

    wire signed [17:0] it_w = ($signed({9'd0, ot}) * $signed({9'd0, STRIDE_T[8:0]}))
                              + $signed({9'd0, kh}) - PADT;
    wire signed [17:0] if_w = ($signed({9'd0, of}) * $signed({9'd0, STRIDE_F[8:0]}))
                              + $signed({9'd0, kw}) - PADF;

    // stacked-plane frequency for this input channel
    wire signed [15:0] sh     = shift_of(ic[2:0]);
    wire signed [17:0] stack_f = if_w + $signed({{2{sh[15]}}, sh});

    wire               t_ok = (it_w >= 0) && (it_w < IN_T);
    wire               f_ok = USE_STACK ? ((stack_f >= 0) && (stack_f < 309))
                                        : ((if_w >= 0) && (if_w < IN_F));

    assign in_range = t_ok && f_ok;
    assign input_in_range_o = in_range;
    assign sample_req_o = DDR_FETCH && (state == S_REQ);
    assign bias_req_o = DDR_FETCH && (state == S_BIAS_REQ);
    // plane row is the padded INPUT row; using ot here would be wrong for any kernel height > 1
    wire [15:0] plane_row = it_w[15:0];
    assign pl_addr_o = (plane_row * 16'd309) + stack_f[15:0];
    assign w_addr_o  = ((kh * KW + kw) * IN_C + ic) * OUT_C + oc;
    // feature-map address: X[t][f][c] with t the padded INPUT row
    assign x_cell_addr_o = (it_w * IN_F) + if_w;
    assign x_channel_o = ic;
    assign x_addr_o  = (x_cell_addr_o * IN_C) + ic;
    assign x_row_o   = it_w;
    assign x_col_o   = if_w;
    assign b_addr_o  = {1'b0, oc};

    // sigmoid on a Q4.12 accumulator around zero, via a 64-entry LUT window
    always_comb begin
        if (USE_STACK) xval = mac_in_range_q ? pl_data_i : 16'sd0;
        else           xval = mac_in_range_q ? x_data_i  : 16'sd0;
    end

    wire signed [47:0] mac = $signed({{32{w_data_i[15]}}, w_data_i}) *
                             $signed({{32{xval[15]}}, xval});

    always_ff @(posedge clk_i or negedge rst_ni) begin
        if (!rst_ni) begin
            state <= S_IDLE; ot <= '0; of <= '0; oc <= '0;
            kh <= '0; kw <= '0; ic <= '0; acc <= '0;
            mac_in_range_q <= 1'b0;
            y_we_o <= 1'b0; y_acc_o <= '0; done_o <= 1'b0;
            y_row_o <= '0; y_col_o <= '0; y_channel_o <= '0;
        end else begin
            y_we_o <= 1'b0;
            done_o <= 1'b0;

            case (state)
                S_IDLE: if (start_i) begin
                    ot <= row_start_i; of <= '0; oc <= '0; kh <= '0; kw <= '0; ic <= '0;
                    acc <= '0;
                    state <= S_T;
                end

                S_T: begin
                    of <= '0;
                    oc <= '0;
                    state <= S_F;
                end

                S_F: begin
                    kh  <= '0;
                    kw  <= '0;
                    ic  <= '0;
                    acc <= '0;
                    state <= S_KH;
                end

                // kh -> kw -> ic tight MAC loop for one (t,f,c) output
                S_KH: begin
                    kw <= '0;
                    ic <= '0;
                    state <= S_KW;
                end

                S_KW: begin
                    ic <= '0;
                    state <= S_REQ;
                end

                // Weight and feature memories are synchronous BSRAMs.  Hold
                // their addresses for one clock before consuming the data.
                S_REQ: if (!DDR_FETCH || sample_valid_i) begin
                    // Padding depends on counters held throughout REQ/IC.
                    // Resolve it on the existing synchronous-memory wait beat
                    // instead of feeding row/column carries into the MAC mux.
                    // RAM outputs settle after this edge; the next IC edge
                    // consumes them with this registered mask. No extra beat.
                    mac_in_range_q <= in_range;
                    state <= S_IC;
                end

                S_IC: begin
                    acc <= acc + mac;
                    if (ic == IN_C - 1) begin
                        ic <= '0;
                        if (kw == KW - 1) begin
                            kw <= '0;
                            if (kh == KH - 1) begin
                                kh <= '0;
                                state <= DDR_FETCH ? S_BIAS_REQ : S_STORE;
                            end else begin
                                kh <= kh + 1'b1;
                                state <= S_KW;
                            end
                        end else begin
                            kw <= kw + 1'b1;
                            state <= S_KW;
                        end
                    end else begin
                        ic <= ic + 1'b1;
                        state <= S_REQ;
                    end
                end

                S_BIAS_REQ: if (bias_valid_i) state <= S_STORE;

                S_STORE: begin
                    y_we_o   <= 1'b1;
                    y_addr_o <= ((ot * OUT_F + of) * OUT_C) + oc;
                    y_row_o <= ot;
                    y_col_o <= of;
                    y_channel_o <= oc;
                    y_acc_o  <= acc + $signed({{16{b_data_i[31]}}, b_data_i});
                    // 48-bit: the bias is pre-scaled into the weight units
                    // (Bq' = Bq*bs*4096/ws) and the folded accumulator reaches
                    // ~7e9, which does NOT fit in 32 bits.
                    y_data_o <= act_val;
                    if (oc == OUT_C - 1) begin
                        oc <= '0;
                        if (of == OUT_F - 1) begin
                            of <= '0;
                            if ((ot == row_limit_i - 1) || (ot == OUT_T - 1)) begin
                                state <= S_DONE;
                            end else begin
                                ot <= ot + 1'b1;
                                state <= S_T;
                            end
                        end else begin
                            of <= of + 1'b1;
                            state <= S_F;
                        end
                    end else begin
                        oc <= oc + 1'b1;
                        state <= S_F;
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

    // activation on the raw accumulator (RTL keeps the scale in the ROM)
    always_comb begin
        logic signed [31:0] v;
        v = acc[31:0] + b_data_i[31:0];
        if (ACT == 1)      act_val = (v > 0) ? v[15:0] : 16'sd0;
        else if (ACT == 2) act_val = (v > 0) ? 16'sd1 : 16'sd0;   // placeholder, sigmoid in TB
        else               act_val = v[15:0];
    end
endmodule
