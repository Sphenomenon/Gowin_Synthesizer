`timescale 1ns/1ps
module pitch_expression #(
    parameter integer SAMPLE_RATE_HZ = 48000
) (
    input logic clk_i, rst_ni, sample_ce_i,
    input logic [21:0] target_ratio_q20_i,
    input logic [15:0] glide_step_q20_i,
    input logic [6:0] vibrato_depth_i,
    output logic [21:0] ratio_q20_o
);
  localparam logic [31:0] LFO_STEP = (64'd4294967296 * 5) / SAMPLE_RATE_HZ;
  logic [21:0] glide_ratio;
  logic [31:0] phase;
  logic signed [16:0] triangle;
  logic signed [24:0] modulation;
  logic signed [24:0] combined;
  always_comb begin
    triangle = phase[31] ? $signed({1'b0, ~phase[30:15]}) - 17'sd32768
                        : $signed({1'b0, phase[30:15]}) - 17'sd32768;
    combined = $signed({3'd0, glide_ratio}) + (modulation >>> 8);
    if (combined < 25'sd524288) ratio_q20_o = 22'd524288;
    else if (combined > 25'sd2097152) ratio_q20_o = 22'd2097152;
    else ratio_q20_o = combined[21:0];
  end
  // Continuous one-clock control pipeline; ratio settles between audio frames.
  // A depth change on the frame edge takes effect from the following frame.
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if(!rst_ni) modulation<=0;
    else modulation<=triangle * $signed({1'b0, vibrato_depth_i});
  end
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      glide_ratio <= 22'd1048576;
      phase <= 32'h40000000;
    end else if (sample_ce_i) begin
      phase <= phase + LFO_STEP;
      if (glide_step_q20_i == 0) glide_ratio <= target_ratio_q20_i;
      else if (target_ratio_q20_i > glide_ratio)
        glide_ratio <= target_ratio_q20_i-glide_ratio > glide_step_q20_i
            ? glide_ratio + glide_step_q20_i : target_ratio_q20_i;
      else glide_ratio <= glide_ratio-target_ratio_q20_i > glide_step_q20_i
            ? glide_ratio - glide_step_q20_i : target_ratio_q20_i;
    end
  end
endmodule
