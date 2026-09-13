`timescale 1ns/1ps

module serial_delay_effect #(
    parameter integer DELAY_BITS=14,
    parameter integer ECHO_SAMPLES=9600
) (
    input logic clk_i,rst_ni,valid_i,enabled_i,
    input logic signed [31:0] left_i,right_i,
    output logic ready_o,valid_o,active_o,
    output logic signed [31:0] left_o,right_o,
    output logic clip_o
);
  import audio_math_pkg::*;
  localparam integer DEPTH=1<<DELAY_BITS;
  (* ram_style="block",syn_ramstyle="block_ram" *) logic signed [31:0] memory_l[0:DEPTH-1],memory_r[0:DEPTH-1];
  logic [DELAY_BITS-1:0] pointer,read_address;
  logic [31:0] frames;
  logic [2:0] state;
  logic [15:0] gain;
  logic signed [31:0] input_l,input_r,read_l,read_r,feedback_l,feedback_r;
  logic signed [48:0] product_l,product_r;
  logic signed [63:0] feedback_wide_l,feedback_wide_r,mixed_l,mixed_r;
  assign ready_o=state==0;
  assign active_o=gain!=0||enabled_i;
  always_ff @(posedge clk_i) begin
    if(state==1) begin read_l<=memory_l[read_address];read_r<=memory_r[read_address];end
    if(state==4) begin memory_l[pointer]<=feedback_l;memory_r[pointer]<=feedback_r;end
  end
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if(!rst_ni) begin
      pointer<=0;read_address<=0;frames<=0;state<=0;gain<=0;valid_o<=0;clip_o<=0;
      input_l<=0;input_r<=0;feedback_l<=0;feedback_r<=0;
      product_l<=0;product_r<=0;feedback_wide_l<=0;feedback_wide_r<=0;mixed_l<=0;mixed_r<=0;left_o<=0;right_o<=0;
    end else begin
      valid_o<=0;clip_o<=0;
      case(state)
        0:if(valid_i) begin
          input_l<=left_i;input_r<=right_i;read_address<=pointer-DELAY_BITS'(ECHO_SAMPLES);
          gain<=slew15(gain,enabled_i?16'd8192:16'd0);state<=1;
        end
        1:state<=2;
        2:begin
          product_l<=$signed(frames>=ECHO_SAMPLES?read_l:32'sd0)*$signed({1'b0,gain});
          product_r<=$signed(frames>=ECHO_SAMPLES?read_r:32'sd0)*$signed({1'b0,gain});
          feedback_wide_l<=$signed(input_l)+rshift($signed(frames>=ECHO_SAMPLES?read_l:32'sd0),1);
          feedback_wide_r<=$signed(input_r)+rshift($signed(frames>=ECHO_SAMPLES?read_r:32'sd0),1);state<=3;
        end
        3:begin
          feedback_l<=sat31(feedback_wide_l);feedback_r<=sat31(feedback_wide_r);
          mixed_l<=$signed(input_l)+rshift(product_l,15);mixed_r<=$signed(input_r)+rshift(product_r,15);state<=4;
        end
        4:begin
          left_o<=sat31(mixed_l);right_o<=sat31(mixed_r);valid_o<=1;
          clip_o<=mixed_l>64'sd2147483647||mixed_l< -64'sd2147483648||mixed_r>64'sd2147483647||mixed_r< -64'sd2147483648;
          pointer<=pointer+1'b1;if(frames!=32'hffffffff)frames<=frames+1'b1;state<=0;
        end
        default:state<=0;
      endcase
    end
  end
endmodule

module serial_chorus_effect #(
    parameter integer CHORUS_BITS=10,
    parameter integer CHORUS_BASE=480,
    parameter integer CHORUS_DEPTH=96
) (
    input logic clk_i,rst_ni,valid_i,enabled_i,
    input logic signed [31:0] left_i,right_i,
    output logic ready_o,valid_o,active_o,
    output logic signed [31:0] left_o,right_o,
    output logic clip_o
);
  import audio_math_pkg::*;
  localparam integer DEPTH=1<<CHORUS_BITS;
  (* ram_style="block",syn_ramstyle="block_ram" *) logic signed [31:0] memory_l[0:DEPTH-1],memory_r[0:DEPTH-1];
  logic [CHORUS_BITS-1:0] pointer,read_address;
  logic [31:0] frames;
  logic [2:0] state;
  logic [15:0] gain,triangle,chorus_delay;
  logic [23:0] lfo;
  logic signed [31:0] input_l,input_r,read_l,read_r;
  logic signed [48:0] product_l,product_r;
  logic signed [63:0] mixed_l,mixed_r;
  assign ready_o=state==0;
  assign active_o=gain!=0||enabled_i;
  assign triangle=lfo[23]?~lfo[22:7]:lfo[22:7];
  wire [15:0] next_chorus_delay=16'(CHORUS_BASE+((triangle*CHORUS_DEPTH)>>16));
  always_ff @(posedge clk_i) begin
    if(state==1) begin read_l<=memory_l[read_address];read_r<=memory_r[read_address];end
    if(state==3) begin memory_l[pointer]<=input_l;memory_r[pointer]<=input_r;end
  end
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if(!rst_ni) begin
      pointer<=0;read_address<=0;frames<=0;state<=0;gain<=0;lfo<=0;chorus_delay<=CHORUS_BASE;
      valid_o<=0;clip_o<=0;input_l<=0;input_r<=0;product_l<=0;product_r<=0;
      mixed_l<=0;mixed_r<=0;left_o<=0;right_o<=0;
    end else begin
      valid_o<=0;clip_o<=0;
      case(state)
        0:if(valid_i) begin
          input_l<=left_i;input_r<=right_i;chorus_delay<=next_chorus_delay;
          read_address<=pointer-CHORUS_BITS'(next_chorus_delay);gain<=slew15(gain,enabled_i?16'd8192:16'd0);state<=1;
        end
        1:state<=2;
        2:begin
          product_l<=$signed(frames>=chorus_delay?read_l:32'sd0)*$signed({1'b0,gain});
          product_r<=$signed(frames>=chorus_delay?read_r:32'sd0)*$signed({1'b0,gain});state<=3;
        end
        3:begin mixed_l<=$signed(input_l)+rshift(product_l,15);mixed_r<=$signed(input_r)+rshift(product_r,15);state<=4;end
        4:begin
          left_o<=sat31(mixed_l);right_o<=sat31(mixed_r);valid_o<=1;
          clip_o<=mixed_l>64'sd2147483647||mixed_l< -64'sd2147483648||mixed_r>64'sd2147483647||mixed_r< -64'sd2147483648;
          pointer<=pointer+1'b1;if(frames!=32'hffffffff)frames<=frames+1'b1;lfo<=lfo+24'd349;state<=0;
        end
        default:state<=0;
      endcase
    end
  end
endmodule

module serial_reverb_effect #(
    parameter integer COMB_A=1493,
    parameter integer COMB_B=1877
) (
    input logic clk_i,rst_ni,valid_i,enabled_i,
    input logic signed [31:0] left_i,right_i,
    output logic ready_o,valid_o,active_o,
    output logic signed [31:0] left_o,right_o,
    output logic clip_o
);
  import audio_math_pkg::*;
  (* ram_style="block",syn_ramstyle="block_ram" *) logic signed [31:0] comb_a[0:2047],comb_b[0:2047];
  logic [10:0] pointer;
  logic [31:0] frames;
  logic [2:0] state;
  logic [15:0] gain;
  logic signed [31:0] input_l,input_r,read_a,read_b,rv_a,rv_b,damping_a,damping_b,feedback_a,feedback_b;
  logic signed [48:0] product_l,product_r;
  logic signed [63:0] feedback_wide_a,feedback_wide_b,mixed_l,mixed_r;
  assign ready_o=state==0;
  assign active_o=gain!=0||enabled_i;
  always_ff @(posedge clk_i) begin
    if(state==1) begin read_a<=comb_a[(pointer-COMB_A)&11'h7ff];read_b<=comb_b[(pointer-COMB_B)&11'h7ff];end
    if(state==6) begin comb_a[pointer]<=feedback_a;comb_b[pointer]<=feedback_b;end
  end
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if(!rst_ni) begin
      pointer<=0;frames<=0;state<=0;gain<=0;valid_o<=0;clip_o<=0;input_l<=0;input_r<=0;
      rv_a<=0;rv_b<=0;damping_a<=0;damping_b<=0;feedback_a<=0;feedback_b<=0;
      product_l<=0;product_r<=0;feedback_wide_a<=0;feedback_wide_b<=0;mixed_l<=0;mixed_r<=0;left_o<=0;right_o<=0;
    end else begin
      valid_o<=0;clip_o<=0;
      case(state)
        0:if(valid_i) begin input_l<=left_i;input_r<=right_i;gain<=slew15(gain,enabled_i?16'd8192:16'd0);state<=1;end
        1:state<=2;
        2:begin rv_a<=frames>=COMB_A?read_a:32'sd0;rv_b<=frames>=COMB_B?read_b:32'sd0;state<=3;end
        3:begin damping_a<=sat31(rshift($signed(damping_a)+$signed(rv_a),1));damping_b<=sat31(rshift($signed(damping_b)+$signed(rv_b),1));state<=4;end
        4:begin
          feedback_wide_a<=rshift($signed(input_l)+$signed(input_r),2)+rshift($signed(damping_a)*64'sd3,2);
          feedback_wide_b<=rshift($signed(input_l)+$signed(input_r),2)+rshift($signed(damping_b)*64'sd3,2);
          product_l<=$signed(rv_a)*$signed({1'b0,gain});product_r<=$signed(rv_b)*$signed({1'b0,gain});state<=5;
        end
        5:begin
          feedback_a<=sat31(feedback_wide_a);feedback_b<=sat31(feedback_wide_b);
          mixed_l<=$signed(input_l)+rshift(product_l,15);mixed_r<=$signed(input_r)+rshift(product_r,15);state<=6;
        end
        6:begin
          left_o<=sat31(mixed_l);right_o<=sat31(mixed_r);valid_o<=1;
          clip_o<=mixed_l>64'sd2147483647||mixed_l< -64'sd2147483648||mixed_r>64'sd2147483647||mixed_r< -64'sd2147483648;
          pointer<=pointer+1'b1;if(frames!=32'hffffffff)frames<=frames+1'b1;state<=0;
        end
        default:state<=0;
      endcase
    end
  end
endmodule

module stereo_effects #(
    parameter integer DELAY_BITS=14,
    parameter integer ECHO_SAMPLES=9600,
    parameter integer CHORUS_BASE=480,
    parameter integer CHORUS_DEPTH=96,
    parameter integer COMB_A=1493,
    parameter integer COMB_B=1877
) (
    input logic clk_i,rst_ni,valid_i,
    input logic signed [31:0] synth_i,pcm_left_i,pcm_right_i,
    input logic [15:0] synth_gain_i,pcm_gain_i,
    input logic [2:0] effect_mask_i,
    input logic [5:0] effect_order_i,
    output logic ready_o,valid_o,
    output logic signed [31:0] left_o,right_o,
    output logic clip_o
);
  import audio_math_pkg::*;
  localparam [3:0] IDLE=0,SCALE=1,DRY=2,SELECT=3,SEND=4,WAIT=5,FINISH=6;
  logic [3:0] state;
  logic [15:0] sg,pg;
  logic signed [48:0] input_s,input_l,input_r;
  logic signed [63:0] input_mix_l,input_mix_r;
  logic signed [31:0] dry_l,dry_r,chain_l,chain_r,work_l,work_r;
  logic [2:0] frame_mask,processed;
  logic [5:0] applied_order,frame_order;
  logic [1:0] slot_index,maintenance_id,work_id;
  logic maintenance,work_apply,work_enabled,frame_clip;
  logic delay_ready,delay_valid,delay_clip,delay_active,chorus_ready,chorus_valid,chorus_clip,chorus_active;
  logic reverb_ready,reverb_valid,reverb_clip,reverb_active;
  logic signed [31:0] delay_l,delay_r,chorus_l,chorus_r,reverb_l,reverb_r;
  wire selected_ready=work_id==0?delay_ready:work_id==1?chorus_ready:reverb_ready;
  wire selected_valid=work_id==0?delay_valid:work_id==1?chorus_valid:reverb_valid;
  wire selected_clip=work_id==0?delay_clip:work_id==1?chorus_clip:reverb_clip;
  wire selected_active=selected_id==0?delay_active:selected_id==1?chorus_active:reverb_active;
  wire signed [31:0] selected_l=work_id==0?delay_l:work_id==1?chorus_l:reverb_l;
  wire signed [31:0] selected_r=work_id==0?delay_r:work_id==1?chorus_r:reverb_r;
  wire [1:0] selected_id=slot_index==0?frame_order[1:0]:slot_index==1?frame_order[3:2]:frame_order[5:4];
  assign ready_o=state==IDLE;

  serial_delay_effect #(.DELAY_BITS(DELAY_BITS),.ECHO_SAMPLES(ECHO_SAMPLES)) delay_stage(
      .clk_i,.rst_ni,.valid_i(state==SEND&&work_id==0),.enabled_i(work_enabled),.left_i(work_l),.right_i(work_r),
      .ready_o(delay_ready),.valid_o(delay_valid),.active_o(delay_active),.left_o(delay_l),.right_o(delay_r),.clip_o(delay_clip));
  serial_chorus_effect #(.CHORUS_BASE(CHORUS_BASE),.CHORUS_DEPTH(CHORUS_DEPTH)) chorus_stage(
      .clk_i,.rst_ni,.valid_i(state==SEND&&work_id==1),.enabled_i(work_enabled),.left_i(work_l),.right_i(work_r),
      .ready_o(chorus_ready),.valid_o(chorus_valid),.active_o(chorus_active),.left_o(chorus_l),.right_o(chorus_r),.clip_o(chorus_clip));
  serial_reverb_effect #(.COMB_A(COMB_A),.COMB_B(COMB_B)) reverb_stage(
      .clk_i,.rst_ni,.valid_i(state==SEND&&work_id==2),.enabled_i(work_enabled),.left_i(work_l),.right_i(work_r),
      .ready_o(reverb_ready),.valid_o(reverb_valid),.active_o(reverb_active),.left_o(reverb_l),.right_o(reverb_r),.clip_o(reverb_clip));

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if(!rst_ni) begin
      state<=IDLE;sg<=0;pg<=0;input_s<=0;input_l<=0;input_r<=0;input_mix_l<=0;input_mix_r<=0;
      dry_l<=0;dry_r<=0;chain_l<=0;chain_r<=0;work_l<=0;work_r<=0;frame_mask<=0;processed<=0;
      applied_order<=6'b11_11_11;frame_order<=6'b11_11_11;slot_index<=0;maintenance_id<=0;work_id<=0;
      maintenance<=0;work_apply<=0;work_enabled<=0;frame_clip<=0;valid_o<=0;left_o<=0;right_o<=0;clip_o<=0;
    end else begin
      valid_o<=0;clip_o<=0;
      case(state)
        IDLE:if(valid_i) begin
          input_s<=$signed(synth_i)*$signed({1'b0,sg});
          input_l<=$signed(pcm_left_i)*$signed({1'b0,pg});input_r<=$signed(pcm_right_i)*$signed({1'b0,pg});
          sg<=slew15(sg,synth_gain_i);pg<=slew15(pg,pcm_gain_i);frame_mask<=effect_mask_i;
          if(effect_mask_i!=0)begin applied_order<=effect_order_i;frame_order<=effect_order_i;end
          else frame_order<=applied_order;
          frame_clip<=0;state<=SCALE;
        end
        SCALE:begin input_mix_l<=input_s+input_l;input_mix_r<=input_s+input_r;state<=DRY;end
        DRY:begin
          dry_l<=sat31(rshift(input_mix_l,15));dry_r<=sat31(rshift(input_mix_r,15));
          chain_l<=sat31(rshift(input_mix_l,15));chain_r<=sat31(rshift(input_mix_r,15));
          processed<=0;slot_index<=0;maintenance_id<=0;maintenance<=0;state<=SELECT;
        end
        SELECT:begin
          if(!maintenance) begin
            if(slot_index==3) begin maintenance<=1;maintenance_id<=0;end
            else if(selected_id<3&&(frame_mask[selected_id]||selected_active)&&!processed[selected_id]) begin
              work_id<=selected_id;work_l<=chain_l;work_r<=chain_r;work_apply<=1;
              work_enabled<=frame_mask[selected_id];state<=SEND;
            end else slot_index<=slot_index+1'b1;
          end else if(maintenance_id==3) state<=FINISH;
          else if(!processed[maintenance_id]) begin
            work_id<=maintenance_id;work_l<=dry_l;work_r<=dry_r;work_apply<=0;
            work_enabled<=frame_mask[maintenance_id];state<=SEND;
          end else maintenance_id<=maintenance_id+1'b1;
        end
        SEND:if(selected_ready)state<=WAIT;
        WAIT:if(selected_valid)begin
          if(work_apply)begin chain_l<=selected_l;chain_r<=selected_r;end
          processed[work_id]<=1;frame_clip<=frame_clip|selected_clip;
          if(maintenance)maintenance_id<=maintenance_id+1'b1;else slot_index<=slot_index+1'b1;
          state<=SELECT;
        end
        FINISH:begin left_o<=chain_l;right_o<=chain_r;clip_o<=frame_clip;valid_o<=1;state<=IDLE;end
        default:state<=IDLE;
      endcase
    end
  end
endmodule
