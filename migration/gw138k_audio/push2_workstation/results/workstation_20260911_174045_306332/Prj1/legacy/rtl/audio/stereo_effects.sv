`timescale 1ns/1ps
module stereo_effects #(
    parameter integer DELAY_BITS = 14,
    parameter integer ECHO_SAMPLES = 9600,
    parameter integer CHORUS_BASE = 480,
    parameter integer CHORUS_DEPTH = 96,
    parameter integer COMB_A = 1493,
    parameter integer COMB_B = 1877
) (
    input logic clk_i, rst_ni, valid_i,
    input logic signed [31:0] synth_i, pcm_left_i, pcm_right_i,
    input logic [15:0] synth_gain_i, pcm_gain_i,
    input logic [2:0] effect_mask_i,
    output logic ready_o, valid_o,
    output logic signed [31:0] left_o, right_o,
    output logic clip_o
);
  import audio_math_pkg::*;
  localparam integer DEPTH = 1 << DELAY_BITS;
  (* ram_style="block", syn_ramstyle="block_ram" *) logic signed [31:0] delay_l[0:DEPTH-1], delay_r[0:DEPTH-1];
  (* ram_style="block", syn_ramstyle="block_ram" *) logic signed [31:0] comb_a[0:2047], comb_b[0:2047];
  logic [DELAY_BITS-1:0] pointer;
  logic [31:0] frames;
  logic [10:0] comb_pointer;
  logic [15:0] sg, pg, eg, cg, rg;
  logic [23:0] lfo;
  logic [15:0] triangle, chorus_delay;
  logic [3:0] state;
  logic signed [63:0] mix_l, mix_r, wet_l, wet_r;
  logic signed [31:0] dry_l, dry_r, echo_l, echo_r, chorus_l, chorus_r;
  logic signed [31:0] rv_a, rv_b, damping_a, damping_b;
  logic signed [31:0] read_l, read_r, read_a, read_b;
  logic [DELAY_BITS-1:0] read_address;
  logic signed [31:0] feedback_l, feedback_r, feedback_a, feedback_b;
  logic signed [63:0] feedback_wide_l,feedback_wide_r,feedback_wide_a,feedback_wide_b;
  logic signed [48:0] input_s,input_l,input_r;
  logic signed [48:0] echo_product_l,echo_product_r,chorus_product_l,chorus_product_r,rv_product_l,rv_product_r;
  assign ready_o = state == 0;
  assign triangle = lfo[23] ? ~lfo[22:7] : lfo[22:7];
  assign read_address = state == 1 ? pointer-ECHO_SAMPLES : pointer-chorus_delay;
  // Registered reads and unreset memory writes preserve block RAM inference.
  always_ff @(posedge clk_i) begin
    if (state==1 || state==3) begin
      read_l <= delay_l[read_address]; read_r <= delay_r[read_address];
    end
    if (state==1) begin
      read_a <= comb_a[(comb_pointer-COMB_A) & 11'h7ff];
      read_b <= comb_b[(comb_pointer-COMB_B) & 11'h7ff];
    end
    if (state==7) begin
      delay_l[pointer] <= feedback_l; delay_r[pointer] <= feedback_r;
      comb_a[comb_pointer] <= feedback_a; comb_b[comb_pointer] <= feedback_b;
    end
  end
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      state<=0; pointer<=0; comb_pointer<=0; frames<=0; lfo<=0;chorus_delay<=CHORUS_BASE;
      sg<=0; pg<=0; eg<=0; cg<=0; rg<=0; valid_o<=0; clip_o<=0;
      left_o<=0; right_o<=0; dry_l<=0; dry_r<=0; mix_l<=0; mix_r<=0;
      echo_l<=0; echo_r<=0; chorus_l<=0; chorus_r<=0;
      rv_a<=0; rv_b<=0; damping_a<=0; damping_b<=0; wet_l<=0; wet_r<=0;
      feedback_l<=0;feedback_r<=0;feedback_a<=0;feedback_b<=0;
      feedback_wide_l<=0;feedback_wide_r<=0;feedback_wide_a<=0;feedback_wide_b<=0;
      input_s<=0;input_l<=0;input_r<=0;
      echo_product_l<=0;echo_product_r<=0;chorus_product_l<=0;chorus_product_r<=0;
      rv_product_l<=0;rv_product_r<=0;
    end else begin
      valid_o<=0; clip_o<=0;
      case(state)
        0: if(valid_i) begin
          chorus_delay<=16'(CHORUS_BASE + ((triangle * CHORUS_DEPTH) >> 16));
          input_s <= $signed(synth_i)*$signed({1'b0,sg});
          input_l <= $signed(pcm_left_i)*$signed({1'b0,pg});
          input_r <= $signed(pcm_right_i)*$signed({1'b0,pg});
          sg<=slew15(sg,synth_gain_i); pg<=slew15(pg,pcm_gain_i);
          eg<=slew15(eg,effect_mask_i[0] ? 16'd8192:16'd0);
          cg<=slew15(cg,effect_mask_i[1] ? 16'd8192:16'd0);
          rg<=slew15(rg,effect_mask_i[2] ? 16'd8192:16'd0);
          state<=9;
        end
        9:begin mix_l<=input_s+input_l;mix_r<=input_s+input_r;state<=1;end
        1: begin
          dry_l<=sat31(rshift(mix_l,15)); dry_r<=sat31(rshift(mix_r,15));
          state<=2;
        end
        2: begin
          echo_l<=frames >= ECHO_SAMPLES ? read_l:32'sd0;
          echo_r<=frames >= ECHO_SAMPLES ? read_r:32'sd0;
          rv_a<=frames >= COMB_A ? read_a:32'sd0;
          rv_b<=frames >= COMB_B ? read_b:32'sd0;
          state<=3;
        end
        3: state<=4;
        4: begin
          chorus_l<=frames >= chorus_delay ? read_l:32'sd0;
          chorus_r<=frames >= chorus_delay ? read_r:32'sd0;
          damping_a<=sat31(rshift($signed(damping_a)+$signed(rv_a),1));
          damping_b<=sat31(rshift($signed(damping_b)+$signed(rv_b),1));
          state<=5;
        end
        5: begin
          feedback_wide_l <= $signed(dry_l) + rshift($signed(echo_l),1);
          feedback_wide_r <= $signed(dry_r) + rshift($signed(echo_r),1);
          feedback_wide_a <= rshift($signed(dry_l)+$signed(dry_r),2) + rshift($signed(damping_a)*64'sd3,2);
          feedback_wide_b <= rshift($signed(dry_l)+$signed(dry_r),2) + rshift($signed(damping_b)*64'sd3,2);
          echo_product_l<=$signed(echo_l)*$signed({1'b0,eg});
          echo_product_r<=$signed(echo_r)*$signed({1'b0,eg});
          chorus_product_l<=$signed(chorus_l)*$signed({1'b0,cg});
          chorus_product_r<=$signed(chorus_r)*$signed({1'b0,cg});
          rv_product_l<=$signed(rv_a)*$signed({1'b0,rg});
          rv_product_r<=$signed(rv_b)*$signed({1'b0,rg});
          state<=6;
        end
        6: begin
          feedback_l<=sat31(feedback_wide_l);feedback_r<=sat31(feedback_wide_r);
          feedback_a<=sat31(feedback_wide_a);feedback_b<=sat31(feedback_wide_b);
          wet_l<=echo_product_l+chorus_product_l+rv_product_l;
          wet_r<=echo_product_r+chorus_product_r+rv_product_r;
          state<=10;
        end
        10:begin
          mix_l <= $signed(dry_l) + rshift(wet_l,15);
          mix_r <= $signed(dry_r) + rshift(wet_r,15);
          state<=7;
        end
        7: begin
          left_o<=sat31(mix_l); right_o<=sat31(mix_r); valid_o<=1;
          clip_o <= mix_l>64'sd2147483647 || mix_l < -64'sd2147483648 ||
                    mix_r>64'sd2147483647 || mix_r < -64'sd2147483648;
          pointer<=pointer+1'b1; comb_pointer<=comb_pointer+1'b1;
          if(frames != 32'hffffffff) frames<=frames+1;
          lfo<=lfo+24'd349; state<=0;
        end
        default: state<=0;
      endcase
    end
  end
endmodule
