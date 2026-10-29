`timescale 1ns/1ps
// Independent native runtime delay consumer. PCM and ordered configuration
// markers share65bit FIFOs. A matching ACK is emitted only after the paired
// DMA drains old reads and completes an ordered post-write fence read.
// Payload[32:1] is a private transaction ID, payload[0] is rate44;
// payload[63:33] must be0. No public event layout is changed.
// history_clear is a backpressured request preserving wet gain; legacy clear
// aborts immediately and resets gain. Both wait for an actual roundtrip ACK.
// During that wait the caller must keep the final sample schedule running
// through controlled mute. Transaction/clock faults require coordinated reset;
// stream under/overflow remains observable and legacy clear can reset it.
module workstation_runtime_delay_effect_ddr #(
    parameter integer DELAY_BITS=14,
    parameter integer ECHO_SAMPLES=9600,
    parameter integer FIFO_ADDRESS_BITS=9,
    parameter integer TRANSACTION_TIMEOUT_CYCLES=1048576,
    parameter integer PEER_TIMEOUT_CYCLES=1048576
) (
    input logic clk_i,rst_ni,clear_i,valid_i,enabled_i,
    input logic signed [31:0] left_i,right_i,
    output logic ready_o,valid_o,active_o,
    output logic signed [31:0] left_o,right_o,
    output logic clip_o,
    // memory-domain bridge (delay_ddr_dma side)
    input logic mem_clk_i,mem_rst_ni,
    output logic dwr_valid_o,
    output logic [64:0] dwr_data_o,
    input logic dwr_pop_i,
    input logic drd_push_i,
    input logic [64:0] drd_data_i,
    output logic drd_ready_o,
    output logic [7:0] debug_status_o,
    input logic config_valid_i,rate_44100_i,history_clear_i,
    output logic config_ready_o,config_applied_o,
    output logic history_ready_o,history_done_o,quiescent_o,fault_o,
    output logic applied_rate_44100_o,
    output logic [31:0] applied_transaction_o,
    input logic peer_heartbeat_i,
    output logic heartbeat_o
);
  import audio_math_pkg::*;
  initial begin
    if(DELAY_BITS!=14 || ECHO_SAMPLES!=9600 || FIFO_ADDRESS_BITS<7 ||
       FIFO_ADDRESS_BITS>9 || TRANSACTION_TIMEOUT_CYCLES<2 || PEER_TIMEOUT_CYCLES<128)
      $fatal(1,"runtime delay consumer requires audited ring, FIFO and watchdog limits");
  end
  logic [31:0] frames;
  logic [2:0] state;
  logic [15:0] gain;
  logic signed [31:0] input_l,input_r,read_l,read_r,feedback_l,feedback_r;
  logic signed [48:0] product_l,product_r;
  logic signed [63:0] feedback_wide_l,feedback_wide_r,mixed_l,mixed_r;
  logic transaction_busy,transaction_fault,peer_fault;
  logic pending_rate,pending_is_config;
  logic [31:0] transaction_id,pending_id,transaction_wait,peer_wait;
  logic [4:0] heartbeat_counter;
  (* ASYNC_REG="TRUE" *) logic peer_meta,peer_sync;
  logic peer_last;
  logic [7:0] gain_remainder;
  wire [31:0] echo_samples=applied_rate_44100_o ? 32'd8820 : 32'(ECHO_SAMPLES);
  wire config_accept=config_valid_i && config_ready_o;
  wire history_accept=history_clear_i && history_ready_o;
  wire transaction_start=(clear_i && !transaction_busy)||config_accept||history_accept;
  wire local_history_clear=clear_i||config_accept||history_accept;
  assign ready_o=state==0 && !transaction_busy && !transaction_fault && !peer_fault && !clear_i;
  assign quiescent_o=state==0 && !valid_o && !transaction_busy &&
      !wr_flush_pending && !transaction_fault && !peer_fault;
  assign config_ready_o=quiescent_o && !valid_i && !clear_i;
  assign history_ready_o=config_ready_o && !config_valid_i;
  assign heartbeat_o=heartbeat_counter[4];
  assign fault_o=transaction_fault||peer_fault||underflow_sticky||overflow_sticky;

  //128/frame is the actual prepared wet slew. Preserve48k exactly; the
  //44.1 branch carries47/147 so its average increment is128*160/147.
  wire [7:0] gain_fraction_sum=gain_remainder+8'd47;
  wire [15:0] gain_delta=applied_rate_44100_o ?
      16'd139+{15'd0,gain_fraction_sum>=8'd147} : 16'd128;
  function automatic [15:0] wet_slew(input [15:0] now_value,target_value,delta);
    logic [15:0] upper,lower;
    begin
      upper=now_value>16'hffff-delta ? 16'hffff : now_value+delta;
      lower=now_value<delta ? 16'd0 : now_value-delta;
      if(target_value>upper)wet_slew=upper;
      else if(target_value<lower)wet_slew=lower;
      else wet_slew=target_value;
    end
  endfunction
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if(!rst_ni)begin heartbeat_counter<=0;peer_meta<=0;peer_sync<=0;
      peer_last<=0;peer_wait<=0;peer_fault<=0;gain_remainder<=0;end
    else begin
      heartbeat_counter<=heartbeat_counter+1'b1;
      peer_meta<=peer_heartbeat_i;peer_sync<=peer_meta;
      if(peer_sync!=peer_last)begin peer_wait<=0;peer_last<=peer_sync;end
      else if(peer_wait<32'(PEER_TIMEOUT_CYCLES))peer_wait<=peer_wait+1'b1;
      if(peer_wait>=32'(PEER_TIMEOUT_CYCLES)-1)peer_fault<=1;
      if(clear_i)gain_remainder<=0;
      else if(state==0 && valid_i && ready_o && applied_rate_44100_o)
        gain_remainder<=gain_fraction_sum>=8'd147 ? gain_fraction_sum-8'd147 : gain_fraction_sum;
    end
  end
  assign active_o=gain!=0||enabled_i;
  wire warm=frames>=echo_samples;

  // Write FIFO: audio domain pushes feedback pairs (and flush markers),
  // memory domain pops.  65 bits = {flush, right, left}.
  logic wr_fifo_ready,wr_flush_pending;
  wire wr_data_push=!local_history_clear && state==4 && !wr_flush_pending && !transaction_busy;
  wire wr_flush_push=wr_flush_pending;
  music_async_fifo #(.WIDTH(65),.ADDRESS_BITS(FIFO_ADDRESS_BITS)) u_write_fifo(
      .write_clk_i(clk_i),.write_rst_ni(rst_ni),
      .write_valid_i(wr_data_push||wr_flush_push),
      .write_data_i(wr_flush_push?{1'b1,31'd0,pending_id,pending_rate}:{1'b0,feedback_r,feedback_l}),
      .write_ready_o(wr_fifo_ready),
      .read_clk_i(mem_clk_i),.read_rst_ni(mem_rst_ni),
      .read_valid_o(dwr_valid_o),.read_data_o(dwr_data_o),.read_ready_i(dwr_pop_i));

  // Read FIFO: memory domain pushes ring reads, audio domain pops the wet
  // sample at state 1.  65 bits = {generation marker, right, left}.
  wire rd_head_valid;
  wire [64:0] rd_head;
  wire rd_pop;
  music_async_fifo #(.WIDTH(65),.ADDRESS_BITS(FIFO_ADDRESS_BITS)) u_read_fifo(
      .write_clk_i(mem_clk_i),.write_rst_ni(mem_rst_ni),
      .write_valid_i(drd_push_i),.write_data_i(drd_data_i),.write_ready_o(drd_ready_o),
      .read_clk_i(clk_i),.read_rst_ni(rst_ni),
      .read_valid_o(rd_head_valid),.read_data_o(rd_head),.read_ready_i(rd_pop));

  // Generation tracking: entries below the newest marker are stale and are
  // discarded one per cycle; the first post-marker entry serves sample 9600.
  // Reset starts in the current generation (marker_seen=1): both FIFOs are
  // empty after reset, so there is nothing stale to discard.  clear_i
  // re-arms discard mode until the DMA answers with a fresh marker.
  logic marker_seen,underflow_sticky,overflow_sticky;
  wire marker_pop=!local_history_clear && rd_head_valid && rd_head[64];
  wire matching_marker=marker_pop && transaction_busy &&
      rd_head[63:33]==31'd0 && rd_head[32:1]==pending_id && rd_head[0]==pending_rate;
  wire use_pop=!local_history_clear && !transaction_busy && state==1 && warm && marker_seen &&
               rd_head_valid && !rd_head[64];
  wire discard_pop=!local_history_clear && rd_head_valid && !marker_seen && !rd_head[64];
  assign rd_pop=marker_pop||use_pop||discard_pop;

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if(!rst_ni) begin
      marker_seen<=1;underflow_sticky<=0;overflow_sticky<=0;wr_flush_pending<=0;
      transaction_busy<=0;transaction_fault<=0;transaction_id<=0;pending_id<=0;
      pending_rate<=0;pending_is_config<=0;applied_rate_44100_o<=0;
      applied_transaction_o<=0;transaction_wait<=0;history_done_o<=0;config_applied_o<=0;
    end else begin
      history_done_o<=0;config_applied_o<=0;
      if(wr_flush_pending && wr_fifo_ready)wr_flush_pending<=0;
      if(clear_i)begin underflow_sticky<=0;overflow_sticky<=0;end
      if(transaction_start)begin
        marker_seen<=0;wr_flush_pending<=1;transaction_busy<=1;
        transaction_id<=transaction_id+1'b1;pending_id<=transaction_id+1'b1;
        pending_rate<=config_accept ? rate_44100_i : applied_rate_44100_o;
        pending_is_config<=config_accept;transaction_wait<=0;
      end else if(transaction_busy && !matching_marker)begin
        if(transaction_wait<32'(TRANSACTION_TIMEOUT_CYCLES))transaction_wait<=transaction_wait+1'b1;
        if(transaction_wait>=32'(TRANSACTION_TIMEOUT_CYCLES)-1)transaction_fault<=1;
      end
      if(marker_pop)begin
        if(matching_marker && !transaction_fault && !peer_fault)begin
          marker_seen<=1;transaction_busy<=0;applied_rate_44100_o<=pending_rate;
          applied_transaction_o<=pending_id;history_done_o<=1;config_applied_o<=pending_is_config;
        end else transaction_fault<=1;
      end
      if(state==1 && warm && !use_pop && !local_history_clear)underflow_sticky<=1;
      if(wr_data_push && !wr_fifo_ready)overflow_sticky<=1;
    end
  end

  // state 1 wet read: same cycle position as the original BRAM read, so
  // read_l/read_r are stable at state 2 exactly as before.
  always_ff @(posedge clk_i) begin
    if(!local_history_clear && state==1) begin
      if(use_pop) begin read_l<=rd_head[31:0];read_r<=rd_head[63:32];end
      else begin read_l<=32'sd0;read_r<=32'sd0;end
    end
  end

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if(!rst_ni) begin
      frames<=0;state<=0;gain<=0;valid_o<=0;clip_o<=0;
      input_l<=0;input_r<=0;feedback_l<=0;feedback_r<=0;
      product_l<=0;product_r<=0;feedback_wide_l<=0;feedback_wide_r<=0;mixed_l<=0;mixed_r<=0;left_o<=0;right_o<=0;
    end else begin
      valid_o<=0;clip_o<=0;
      if(local_history_clear) begin
        frames<=0;state<=0;if(clear_i)gain<=0;valid_o<=0;clip_o<=0;
      end else case(state)
        0:if(valid_i && ready_o) begin
          input_l<=left_i;input_r<=right_i;
          gain<=wet_slew(gain,enabled_i?16'd8192:16'd0,gain_delta);state<=1;
        end
        1:state<=2;
        2:begin
          product_l<=$signed(frames>=echo_samples?read_l:32'sd0)*$signed({1'b0,gain});
          product_r<=$signed(frames>=echo_samples?read_r:32'sd0)*$signed({1'b0,gain});
          feedback_wide_l<=$signed(input_l)+rshift($signed(frames>=echo_samples?read_l:32'sd0),1);
          feedback_wide_r<=$signed(input_r)+rshift($signed(frames>=echo_samples?read_r:32'sd0),1);state<=3;
        end
        3:begin
          feedback_l<=sat31(feedback_wide_l);feedback_r<=sat31(feedback_wide_r);
          mixed_l<=$signed(input_l)+rshift(product_l,15);mixed_r<=$signed(input_r)+rshift(product_r,15);state<=4;
        end
        4:begin
          left_o<=sat31(mixed_l);right_o<=sat31(mixed_r);valid_o<=1;
          clip_o<=mixed_l>64'sd2147483647||mixed_l< -64'sd2147483648||mixed_r>64'sd2147483647||mixed_r< -64'sd2147483648;
          if(frames!=32'hffffffff)frames<=frames+1'b1;state<=0;
        end
        default:state<=0;
      endcase
    end
  end

  assign debug_status_o={3'b0,marker_seen,overflow_sticky,underflow_sticky,2'b00};
endmodule
