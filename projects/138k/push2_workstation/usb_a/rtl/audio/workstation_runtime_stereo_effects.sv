`timescale 1ns/1ps
// Native independent runtime composition of exact prepared effects policy.
// A broadcast rate transaction must finish with matching child ACKs or fail
// sticky. PANIC coalesces history clearing and cannot retract a partial apply.
// Caller retains final serial schedule through controlled zero while closed.
module workstation_runtime_stereo_effects #(
    parameter integer VECTOR_ENABLE=0,
    parameter integer DELAY_BITS=14,
    parameter integer ECHO_SAMPLES=9600,
    parameter integer CHORUS_BASE=480,
    parameter integer CHORUS_DEPTH=96,
    parameter integer COMB_A=1493,
    parameter integer COMB_B=1877,
    parameter integer FIFO_ADDRESS_BITS=9,
    parameter integer TRANSACTION_TIMEOUT_CYCLES=1048576,
    parameter integer PEER_TIMEOUT_CYCLES=1048576
) (
    input logic clk_i,rst_ni,clear_i,valid_i,
    input logic signed [31:0] synth_i,pcm_left_i,pcm_right_i,
    input logic signed [31:0] vector_left_i,vector_right_i,
    input logic [15:0] synth_gain_i,pcm_gain_i,
    input logic [2:0] effect_mask_i,
    input logic [5:0] effect_order_i,
    output logic ready_o,valid_o,
    output logic signed [31:0] left_o,right_o,
    output logic clip_o,
    // P10 delay DDR ring bridge (memory-domain side, see delay_ddr_dma)
    input logic mem_clk_i,mem_rst_ni,
    output logic dwr_valid_o,
    output logic [64:0] dwr_data_o,
    input logic dwr_pop_i,
    input logic drd_push_i,
    input logic [64:0] drd_data_i,
    output logic drd_ready_o,
    input logic config_valid_i,rate_44100_i,history_clear_i,
    output logic config_ready_o,config_applied_o,history_ready_o,history_done_o,
    output logic quiescent_o,fault_o,applied_rate_44100_o,
    output logic [31:0] applied_transaction_o,
    input logic peer_heartbeat_i,delay_dma_fault_i,
    output logic heartbeat_o
);
  import audio_math_pkg::*;
  localparam [3:0] IDLE=0,SCALE=1,DRY=2,SELECT=3,SEND=4,WAIT=5,FINISH=6;
  logic [3:0] state;
  logic [15:0] sg,pg,synth_target,pcm_target;
  logic signed [48:0] input_s,input_l,input_r,input_vl,input_vr;
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
  logic barrier_busy,barrier_is_config,pending_rate,panic_coalesced,transaction_fault;
  logic [2:0] barrier_seen;
  logic [31:0] barrier_wait;
  logic [7:0] gain_remainder;
  (* ASYNC_REG="TRUE" *) logic dma_fault_meta,dma_fault_sync;
  wire [2:0] stage_config_ready,stage_history_ready,stage_done,stage_quiet,stage_rate;
  wire delay_fault;
  wire config_accept=config_valid_i && config_ready_o;
  wire history_accept=history_clear_i && history_ready_o;
  wire clear_start=clear_i && !barrier_busy;
  wire [2:0] next_seen=clear_i ? ((barrier_seen|stage_done)&3'b110) : barrier_seen|stage_done;
  wire all_rates_match=stage_rate=={3{pending_rate}};
  wire complete_barrier=barrier_busy && !clear_i && (&next_seen) && (&stage_quiet);
  wire [7:0] gain_fraction_sum=gain_remainder+8'd47;
  wire [15:0] gain_delta=applied_rate_44100_o ?
      16'd139+{15'd0,gain_fraction_sum>=8'd147} : 16'd128;
  function automatic [15:0] runtime_slew(input [15:0] value,target,delta);
    logic [15:0] upper,lower;
    begin
      upper=value>16'hffff-delta ? 16'hffff : value+delta;
      lower=value<delta ? 16'd0 : value-delta;
      if(target>upper)runtime_slew=upper;
      else if(target<lower)runtime_slew=lower;
      else runtime_slew=target;
    end
  endfunction
  assign applied_rate_44100_o=stage_rate[0];
  assign fault_o=transaction_fault || delay_fault || dma_fault_sync;
  assign quiescent_o=state==IDLE && !valid_o && !barrier_busy && (&stage_quiet) && !clear_i && !fault_o;
  assign config_ready_o=quiescent_o && (&stage_config_ready) && !valid_i;
  assign history_ready_o=quiescent_o && (&stage_history_ready) && !valid_i && !config_valid_i;
  assign ready_o=state==IDLE && !barrier_busy && !fault_o && !clear_i && !config_accept && !history_accept;
  always_ff @(posedge clk_i or negedge rst_ni)begin
    if(!rst_ni)begin
      barrier_busy<=0;barrier_is_config<=0;pending_rate<=0;panic_coalesced<=0;
      transaction_fault<=0;barrier_seen<=0;barrier_wait<=0;
      config_applied_o<=0;history_done_o<=0;gain_remainder<=0;
      dma_fault_meta<=0;dma_fault_sync<=0;
    end else begin
      dma_fault_meta<=delay_dma_fault_i;dma_fault_sync<=dma_fault_meta;
      config_applied_o<=0;history_done_o<=0;
      if(delay_fault || dma_fault_sync)transaction_fault<=1;
      // Dry synth/PCM gains keep the prepared update edge, even if PANIC
      // cancels SCALE. Their fractional state is not a public rate authority.
      if(state==SCALE && applied_rate_44100_o)
        gain_remainder<=gain_fraction_sum>=8'd147 ? gain_fraction_sum-8'd147 : gain_fraction_sum;
      if(config_accept || history_accept || clear_start)begin
        barrier_busy<=1;barrier_is_config<=config_accept;
        pending_rate<=config_accept ? rate_44100_i : applied_rate_44100_o;
        barrier_seen<=clear_start ? 3'b110 : 3'b000;
        panic_coalesced<=clear_i;barrier_wait<=0;
      end else if(barrier_busy)begin
        barrier_seen<=next_seen;
        if(clear_i)panic_coalesced<=1;
        if(complete_barrier && !fault_o)begin
          if(all_rates_match)begin
            barrier_busy<=0;history_done_o<=1;config_applied_o<=barrier_is_config;
          end else transaction_fault<=1;
        end else begin
          if(barrier_wait<32'(TRANSACTION_TIMEOUT_CYCLES))barrier_wait<=barrier_wait+1'b1;
          if(barrier_wait>=32'(TRANSACTION_TIMEOUT_CYCLES)-1)transaction_fault<=1;
        end
      end
      if(!barrier_busy && stage_rate!={3{stage_rate[0]}})transaction_fault<=1;
    end
  end

  workstation_runtime_delay_effect_ddr #(.DELAY_BITS(DELAY_BITS),.ECHO_SAMPLES(ECHO_SAMPLES),
      .FIFO_ADDRESS_BITS(FIFO_ADDRESS_BITS),.TRANSACTION_TIMEOUT_CYCLES(TRANSACTION_TIMEOUT_CYCLES),
      .PEER_TIMEOUT_CYCLES(PEER_TIMEOUT_CYCLES)) delay_stage(
      .clk_i,.rst_ni,.clear_i,.valid_i(state==SEND&&work_id==0),.enabled_i(work_enabled),.left_i(work_l),.right_i(work_r),
      .ready_o(delay_ready),.valid_o(delay_valid),.active_o(delay_active),.left_o(delay_l),.right_o(delay_r),.clip_o(delay_clip),
      .mem_clk_i,.mem_rst_ni,
      .dwr_valid_o,.dwr_data_o,.dwr_pop_i,
      .drd_push_i,.drd_data_i,.drd_ready_o,
      .debug_status_o(),.config_valid_i(config_accept),.rate_44100_i(rate_44100_i),
      .history_clear_i(history_accept),.config_ready_o(stage_config_ready[0]),.config_applied_o(),
      .history_ready_o(stage_history_ready[0]),.history_done_o(stage_done[0]),
      .quiescent_o(stage_quiet[0]),.fault_o(delay_fault),.applied_rate_44100_o(stage_rate[0]),
      .applied_transaction_o(applied_transaction_o),.peer_heartbeat_i,.heartbeat_o);
  workstation_runtime_chorus_effect #(.CHORUS_BASE(CHORUS_BASE),.CHORUS_DEPTH(CHORUS_DEPTH)) chorus_stage(
      .clk_i,.rst_ni,.clear_i,.valid_i(state==SEND&&work_id==1),.enabled_i(work_enabled),.left_i(work_l),.right_i(work_r),
      .ready_o(chorus_ready),.valid_o(chorus_valid),.active_o(chorus_active),.left_o(chorus_l),.right_o(chorus_r),.clip_o(chorus_clip),
      .config_valid_i(config_accept),.rate_44100_i(rate_44100_i),.history_clear_i(history_accept),
      .config_ready_o(stage_config_ready[1]),.config_applied_o(),.history_ready_o(stage_history_ready[1]),
      .history_done_o(stage_done[1]),.quiescent_o(stage_quiet[1]),.applied_rate_44100_o(stage_rate[1]));
  workstation_runtime_spatial_reverb reverb_stage(
      .clk_i,.rst_ni,.clear_i,.valid_i(state==SEND&&work_id==2),.enabled_i(work_enabled),.left_i(work_l),.right_i(work_r),
      .ready_o(reverb_ready),.valid_o(reverb_valid),.active_o(reverb_active),.left_o(reverb_l),.right_o(reverb_r),.clip_o(reverb_clip),
      .config_valid_i(config_accept),.rate_44100_i(rate_44100_i),.history_clear_i(history_accept),
      .config_ready_o(stage_config_ready[2]),.config_applied_o(),.history_ready_o(stage_history_ready[2]),
      .history_done_o(stage_done[2]),.quiescent_o(stage_quiet[2]),.applied_rate_44100_o(stage_rate[2]));

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if(!rst_ni) begin
      state<=IDLE;sg<=0;pg<=0;synth_target<=0;pcm_target<=0;input_s<=0;input_l<=0;input_r<=0;input_vl<=0;input_vr<=0;input_mix_l<=0;input_mix_r<=0;
      dry_l<=0;dry_r<=0;chain_l<=0;chain_r<=0;work_l<=0;work_r<=0;frame_mask<=0;processed<=0;
      applied_order<=6'b11_11_11;frame_order<=6'b11_11_11;slot_index<=0;maintenance_id<=0;work_id<=0;
      maintenance<=0;work_apply<=0;work_enabled<=0;frame_clip<=0;valid_o<=0;left_o<=0;right_o<=0;clip_o<=0;
    end else begin
      valid_o<=0;clip_o<=0;
      // Complete the previous sample's gain update even if clear aborts
      // SCALE; the original update occurred on its preceding IDLE edge.
      if(state==SCALE)begin
        sg<=runtime_slew(sg,synth_target,gain_delta);pg<=runtime_slew(pg,pcm_target,gain_delta);
      end
      if(clear_i || barrier_busy || config_accept || history_accept || fault_o) begin
        state<=IDLE;valid_o<=0;clip_o<=0;left_o<=0;right_o<=0;
      end else case(state)
        IDLE:if(valid_i && ready_o) begin
          input_s<=$signed(synth_i)*$signed({1'b0,sg});
          input_vl<=$signed(VECTOR_ENABLE?vector_left_i:32'sd0)*$signed({1'b0,sg});
          input_vr<=$signed(VECTOR_ENABLE?vector_right_i:32'sd0)*$signed({1'b0,sg});
          input_l<=$signed(pcm_left_i)*$signed({1'b0,pg});input_r<=$signed(pcm_right_i)*$signed({1'b0,pg});
          synth_target<=synth_gain_i;pcm_target<=pcm_gain_i;frame_mask<=effect_mask_i;
          if(effect_mask_i!=0)begin applied_order<=effect_order_i;frame_order<=effect_order_i;end
          else frame_order<=applied_order;
          frame_clip<=0;state<=SCALE;
        end
        SCALE:begin input_mix_l<=input_s+input_l+input_vl;input_mix_r<=input_s+input_r+input_vr;state<=DRY;end
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
