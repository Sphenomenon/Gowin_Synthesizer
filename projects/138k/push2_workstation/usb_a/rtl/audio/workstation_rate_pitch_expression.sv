`timescale 1ns/1ps

// Native dual-rate control DSP. Canonical state is never reset by rate changes.
// The caller commits rate only between complete renders; this block consumes
// the same committed value as the oscillator at each sample enable.
module workstation_rate_pitch_expression (
    input logic clk_i, rst_ni, sample_ce_i, rate_44k1_i,
    input logic [21:0] target_ratio_q20_i,
    input logic [15:0] glide_step_q20_i,
    input logic [6:0] vibrato_depth_i,
    output logic [21:0] ratio_q20_o
);
    // Preserve the original 48k floor, including its numerical LFO error.
    localparam logic [31:0] LFO_STEP_48 = 32'((64'd4294967296 * 5) / 48000);
    localparam logic [31:0] LFO_STEP_44 = 32'((64'd4294967296 * 5) / 44100);
    logic [21:0] glide_ratio;
    logic [31:0] phase;
    logic signed [16:0] triangle;
    logic signed [24:0] modulation, combined;
    logic [7:0] glide_remainder;
    // 160*s+r = 147*s+(13*s+r). The remainder is reachable only in0..146,
    // so the residual numerator is at most852101 and fits20 bits. For that
    // entire range floor(t/147) == (t*456523)>>26: 147*456523=2^26+17,
    // and852101*17<2^26. See the independent exhaustive arithmetic regression.
    wire [19:0] glide_residual = {4'd0,glide_step_q20_i} * 20'd13 + {12'd0,glide_remainder};
    wire [38:0] glide_reciprocal_product = glide_residual * 19'd456523;
    wire [12:0] glide_extra_step = glide_reciprocal_product[38:26];
    wire [19:0] glide_residual_multiple = {7'd0,glide_extra_step} * 20'd147;
    wire [19:0] glide_residual_remainder = glide_residual - glide_residual_multiple;
    wire [7:0] next_glide_remainder = glide_residual_remainder[7:0];
    // Carry the fractional increment, so even small CC5 increments preserve
    // physical glide time. Initial73 rounds the cumulative sum to nearest.
    // Seventeen bits retain the full16-bit API range after160/147.
    wire [16:0] current_glide_step = rate_44k1_i
        ? {1'b0,glide_step_q20_i} + {4'd0,glide_extra_step}
        : {1'b0,glide_step_q20_i};
    always_comb begin
        triangle = phase[31] ? $signed({1'b0,~phase[30:15]}) - 17'sd32768
                             : $signed({1'b0,phase[30:15]}) - 17'sd32768;
        combined = $signed({3'd0,glide_ratio}) + (modulation >>> 8);
        if (combined < 25'sd524288) ratio_q20_o = 22'd524288;
        else if (combined > 25'sd2097152) ratio_q20_o = 22'd2097152;
        else ratio_q20_o = combined[21:0];
    end
    // Preserve the original continuous one-clock control pipeline and its
    // frame-edge depth semantics. Vibrato depth remains dimensionless.
    always_ff @(posedge clk_i or negedge rst_ni)
        if (!rst_ni) modulation <= 0;
        else modulation <= triangle * $signed({1'b0,vibrato_depth_i});
    always_ff @(posedge clk_i or negedge rst_ni) begin
        if (!rst_ni) begin
            glide_ratio <= 22'd1048576;
            phase <= 32'h40000000;
            glide_remainder <= 8'd73;
        end else if (sample_ce_i) begin
            phase <= phase + (rate_44k1_i ? LFO_STEP_44 : LFO_STEP_48);
            if (rate_44k1_i && glide_step_q20_i != 0)
                glide_remainder <= next_glide_remainder;
            if (current_glide_step == 0) glide_ratio <= target_ratio_q20_i;
            else if (target_ratio_q20_i > glide_ratio)
                glide_ratio <= target_ratio_q20_i-glide_ratio > {5'd0,current_glide_step}
                    ? glide_ratio + {5'd0,current_glide_step} : target_ratio_q20_i;
            else glide_ratio <= glide_ratio-target_ratio_q20_i > {5'd0,current_glide_step}
                    ? glide_ratio - {5'd0,current_glide_step} : target_ratio_q20_i;
        end
    end
endmodule
