`timescale 1ns/1ps
// Inter-layer requantisation: a wide convolution accumulator in the weight
// quantiser's units -> a bounded signed int16 feature-map sample.
//
//   y_q = clamp( (acc * MUL) >>> SHIFT )      in Q(OUT_FRAC)
//
// With the accumulator A = sum(Wq * Xq) (weights Wq = W/ws, inputs Xq = f*4096)
// the dequantised float value is  v = A * ws / 4096,  so
//
//   v * 2^OUT_FRAC = A * ws * 2^OUT_FRAC / 4096   =>   MUL/2^SHIFT ~= ws / 2^(12-OUT_FRAC)
//
// and the exporter supplies ws per layer, so MUL is derivable per layer.
//
// IMPORTANT: OUT_FRAC must be chosen from the *measured* activation range of
// each layer. A Q12 int16 output spans only +/-8, which is narrower than the
// head activations actually observed, so Q12 silently clips. See the TB.
//
// Status: RTL candidate, unit-simulated; not synthesised or routed here.
module basic_pitch_requant #(
    parameter int MUL      = 68468,   // ~ ws * 2^32 / 2^(12-OUT_FRAC)
    parameter int SHIFT    = 32,
    parameter int OUT_FRAC = 12
) (
    input  logic               clk_i,
    input  logic               rst_ni,
    input  logic               valid_i,
    input  logic signed [47:0] acc_i,
    output logic               valid_o,
    output logic signed [15:0] y_o,
    output logic               sat_o        // 1 when the result was clipped
);
    wire signed [79:0] prod = acc_i * $signed({{32{MUL[31]}}, MUL[31:0]});
    logic signed [79:0] shr;

    always_ff @(posedge clk_i or negedge rst_ni) begin
        if (!rst_ni) begin
            valid_o <= 1'b0; y_o <= '0; sat_o <= 1'b0;
        end else begin
            valid_o <= valid_i;
            if      (shr >  80'sd32767) begin y_o <= 16'sd32767;  sat_o <= 1'b1; end
            else if (shr < -80'sd32768) begin y_o <= -16'sd32768; sat_o <= 1'b1; end
            else                        begin y_o <= shr[15:0];   sat_o <= 1'b0; end
        end
    end

    always_comb shr = prod >>> SHIFT;
endmodule
