`timescale 1ns/1ps

// Native dual-rate control DSP. Canonical state is never reset by rate changes.
// The caller commits rate only between complete renders; this block consumes
// the same committed value as the oscillator at each sample enable.
module workstation_rate_pitch_expression #(
    parameter bit COMMITTED_GLIDE_COEFFICIENT=0
) (
    input logic clk_i, rst_ni, sample_ce_i, rate_44k1_i,
    input logic [21:0] target_ratio_q20_i,
    input logic [15:0] glide_step_q20_i,
    input logic [20:0] glide_div147_i,
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
    // Divide13*s+r by147 without serial constant multipliers. Each nibble
    // contributes an elaboration-time quotient and remainder. The four
    // remainders plus the old fraction total at most839, so five parallel
    // ten-bit trials select the exact final carry. All state and sample
    // edges are unchanged; unknown table inputs retain unknown arithmetic.
    wire [12:0] glide_digit_quotient[0:3];
    wire [7:0] glide_digit_remainder[0:3];
    for(genvar digit=0;digit<4;digit=digit+1)begin:g_glide_digit
        localparam integer WEIGHT=13*(1<<(digit*4));
        reg [20:0] divided_digit;
        always_comb begin
            case(glide_step_q20_i[digit*4+:4])
                4'd0: divided_digit={13'((0*WEIGHT)/147),8'((0*WEIGHT)%147)};
                4'd1: divided_digit={13'((1*WEIGHT)/147),8'((1*WEIGHT)%147)};
                4'd2: divided_digit={13'((2*WEIGHT)/147),8'((2*WEIGHT)%147)};
                4'd3: divided_digit={13'((3*WEIGHT)/147),8'((3*WEIGHT)%147)};
                4'd4: divided_digit={13'((4*WEIGHT)/147),8'((4*WEIGHT)%147)};
                4'd5: divided_digit={13'((5*WEIGHT)/147),8'((5*WEIGHT)%147)};
                4'd6: divided_digit={13'((6*WEIGHT)/147),8'((6*WEIGHT)%147)};
                4'd7: divided_digit={13'((7*WEIGHT)/147),8'((7*WEIGHT)%147)};
                4'd8: divided_digit={13'((8*WEIGHT)/147),8'((8*WEIGHT)%147)};
                4'd9: divided_digit={13'((9*WEIGHT)/147),8'((9*WEIGHT)%147)};
                4'd10: divided_digit={13'((10*WEIGHT)/147),8'((10*WEIGHT)%147)};
                4'd11: divided_digit={13'((11*WEIGHT)/147),8'((11*WEIGHT)%147)};
                4'd12: divided_digit={13'((12*WEIGHT)/147),8'((12*WEIGHT)%147)};
                4'd13: divided_digit={13'((13*WEIGHT)/147),8'((13*WEIGHT)%147)};
                4'd14: divided_digit={13'((14*WEIGHT)/147),8'((14*WEIGHT)%147)};
                4'd15: divided_digit={13'((15*WEIGHT)/147),8'((15*WEIGHT)%147)};
                default:divided_digit=21'bx;
            endcase
        end
        assign glide_digit_quotient[digit]=divided_digit[20:8];
        assign glide_digit_remainder[digit]=divided_digit[7:0];
    end
    wire [12:0] glide_quotient_low=glide_digit_quotient[0]+glide_digit_quotient[1];
    wire [12:0] glide_quotient_high=glide_digit_quotient[2]+glide_digit_quotient[3];
    wire [9:0] glide_remainder_low={2'd0,glide_digit_remainder[0]}+{2'd0,glide_digit_remainder[1]};
    wire [9:0] glide_remainder_high={2'd0,glide_digit_remainder[2]}+{2'd0,glide_digit_remainder[3]};
    wire [9:0] glide_remainder_sum=COMMITTED_GLIDE_COEFFICIENT
        ? {2'd0,glide_div147_i[7:0]}+{2'd0,glide_remainder}
        : glide_remainder_low+glide_remainder_high+{2'd0,glide_remainder};
    wire [10:0] glide_trial[1:5];
    for(genvar carry=1;carry<=5;carry=carry+1)begin:g_glide_trial
        assign glide_trial[carry]={1'b0,glide_remainder_sum}-11'(carry*147);
    end
    wire [2:0] glide_carry=!glide_trial[5][10] ? 3'd5 : !glide_trial[4][10] ? 3'd4 :
        !glide_trial[3][10] ? 3'd3 : !glide_trial[2][10] ? 3'd2 : !glide_trial[1][10] ? 3'd1 : 3'd0;
    wire [12:0] glide_extra_step=COMMITTED_GLIDE_COEFFICIENT
        ? glide_div147_i[20:8]+{10'd0,glide_carry}
        : glide_quotient_low+glide_quotient_high+{10'd0,glide_carry};
    wire [7:0] next_glide_remainder=!glide_trial[5][10] ? glide_trial[5][7:0] :
        !glide_trial[4][10] ? glide_trial[4][7:0] : !glide_trial[3][10] ? glide_trial[3][7:0] :
        !glide_trial[2][10] ? glide_trial[2][7:0] : !glide_trial[1][10] ? glide_trial[1][7:0] : glide_remainder_sum[7:0];
    // Carry the fractional increment, so even small CC5 increments preserve
    // physical glide time. Initial73 rounds the cumulative sum to nearest.
    // Seventeen bits retain the full16-bit API range after160/147.
    wire [16:0] current_glide_step = rate_44k1_i
        ? {1'b0,glide_step_q20_i} + {4'd0,glide_extra_step}
        : {1'b0,glide_step_q20_i};
    // A strict magnitude comparison is the borrow of distance-step-1. Keep
    // it on the carry chain instead of a wide comparator after the reciprocal
    // multiply. The selected direction always gives a nonnegative distance.
    wire [21:0] upward_distance=target_ratio_q20_i-glide_ratio;
    wire [21:0] downward_distance=glide_ratio-target_ratio_q20_i;
    wire [22:0] upward_test={1'b0,upward_distance}-{6'd0,current_glide_step}-23'd1;
    wire [22:0] downward_test={1'b0,downward_distance}-{6'd0,current_glide_step}-23'd1;
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
            if (glide_step_q20_i == 0) glide_ratio <= target_ratio_q20_i;
            else if (target_ratio_q20_i > glide_ratio)
                glide_ratio <= !upward_test[22]
                    ? glide_ratio + {5'd0,current_glide_step} : target_ratio_q20_i;
            else glide_ratio <= !downward_test[22]
                    ? glide_ratio - {5'd0,current_glide_step} : target_ratio_q20_i;
        end
    end
endmodule
