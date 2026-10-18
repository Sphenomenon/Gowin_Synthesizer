`timescale 1ns/1ps
// Basic Pitch head activation: requantise a wide accumulator to a bounded
// Q8.8 argument, then apply ReLU or a sigmoid ROM.
//
//   arg_q (Q8.8) = (acc * MUL) >>> SHIFT          with MUL/2^SHIFT ~= ws/16
//   sigmoid      = LUT[clamp(arg_q, -2048, 2047) + 2048]   (Q0.16 out)
//
// ws is the per-tensor weight scale used by the exporter, and the factor 16
// turns `acc * ws / 4096` (the dequantised float activation, since the inputs
// are Q12) into the Q8.8 argument directly.
//
// NOTE: the clamp at +/-8 is safe because sigmoid saturates there
// (|1 - sigmoid(8)| < 1e-4) but it is a real approximation, not an identity.
// The measured error against the float reference is reported in the TB.
//
// Status: RTL candidate, unit-simulated; not synthesised or routed here.
module basic_pitch_activation #(
    parameter int MUL   = 4280,
    parameter int SHIFT = 32,
    parameter int ACT   = 2,      // 1 = ReLU, 2 = sigmoid
    parameter bit USE_EXTERNAL_LUT = 1'b0
) (
    input  logic               clk_i,
    input  logic               rst_ni,
    input  logic               valid_i,
    input  logic signed [47:0] acc_i,
    output logic               valid_o,
    output logic [15:0]        y_o,        // sigmoid: Q0.16,  ReLU: Q(head_frac)
    output logic               sat_o,      // ReLU output clipped to int16
    output logic signed [31:0] arg_dbg_o,  // Q8.8 requantised argument
    output logic               busy_o,
    output logic               lut_req_o,
    output logic [11:0]        lut_addr_o,
    input  logic               lut_ready_i,
    input  logic               lut_rsp_valid_i,
    input  logic [15:0]        lut_rdata_i
);
    localparam int LUT_N = 4096;

    (* ram_style = "block", syn_ramstyle = "block_ram" *)
    logic [15:0]       lut [0:LUT_N-1];
    logic              v1, v2;
    logic signed [47:0] arg_r;
    logic [11:0]       idx;
    logic [11:0]       lut_addr_r;
    logic              lut_req_pending, lut_waiting;

    initial $readmemh("rtl/music/weights/sigmoid_lut.mem", lut);

    wire signed [79:0] prod = acc_i * $signed({{32{MUL[31]}}, MUL[31:0]});

    always_ff @(posedge clk_i or negedge rst_ni) begin
        if (!rst_ni) begin
            v1 <= 1'b0; v2 <= 1'b0; arg_r <= '0; y_o <= '0; sat_o <= 1'b0;
            lut_addr_r <= '0; lut_req_pending <= 1'b0; lut_waiting <= 1'b0;
        end else begin
            // stage 1: requantise
            arg_r <= prod >>> SHIFT;
            v1    <= valid_i;
            v2    <= 1'b0;

            // stage 2: clamp + activation
            if (ACT == 2) begin
                sat_o <= 1'b0;
                if (USE_EXTERNAL_LUT) begin
                    if (v1) begin
                        lut_addr_r <= idx;
                        lut_req_pending <= 1'b1;
                    end
                    if (lut_req_pending && lut_ready_i) begin
                        lut_req_pending <= 1'b0;
                        lut_waiting <= 1'b1;
                    end
                    if (lut_rsp_valid_i && lut_waiting) begin
                        y_o <= lut_rdata_i;
                        v2 <= 1'b1;
                        lut_waiting <= 1'b0;
                    end
                end else begin
                    y_o <= lut[idx];
                    v2 <= v1;
                end
            end else begin
                v2 <= v1;
                // ReLU. NOTE: `arg_r[15:0]` alone wraps on overflow, which
                // silently turns large activations into wrong small ones. The
                // range is layer dependent (the onset layer reaches +/-108 at
                // Q10, i.e. beyond int16) so it must saturate and be reported.
                if      (arg_r <= 48'sd0)     begin y_o <= 16'sd0;     sat_o <= 1'b0; end
                else if (arg_r >  48'sd32767) begin y_o <= 16'sd32767; sat_o <= 1'b1; end
                else                          begin y_o <= arg_r[15:0]; sat_o <= 1'b0; end
            end
        end
    end

    always_comb begin
        if      (arg_r >  48'sd2047) idx = 12'd4095;
        else if (arg_r < -48'sd2048) idx = 12'd0;
        else                         idx = arg_r + 48'sd2048;
    end

    assign valid_o   = v2;
    assign arg_dbg_o = arg_r[31:0];
    assign busy_o = valid_i || v1 || lut_req_pending || lut_waiting;
    assign lut_req_o = (ACT == 2) && USE_EXTERNAL_LUT && lut_req_pending;
    assign lut_addr_o = lut_addr_r;
endmodule
