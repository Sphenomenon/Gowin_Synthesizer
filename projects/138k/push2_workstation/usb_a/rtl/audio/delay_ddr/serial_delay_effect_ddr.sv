`timescale 1ns/1ps
// DDR-backed drop-in replacement for serial_delay_effect (BSRAM migration,
// Plan B).  The 5-state FSM arithmetic (gain slew, 50% feedback, saturation,
// clip) is preserved bit-for-bit; only the sample storage moves off-chip:
// state 1 pops the wet sample from a read FIFO instead of a BRAM read and
// state 4 pushes the feedback into a write FIFO instead of a BRAM write.
//
// Stream discipline (this is what keeps the DDR ring bit-exact):
//   - Every completed sample pushes exactly one write-FIFO entry
//     {flush=0, right, left}.  The DMA writes it to ring slot wptr and
//     later re-reads slot rptr into the read FIFO; read-FIFO entry #m
//     serves audio sample m+ECHO_SAMPLES, matching the original
//     read_address = pointer - ECHO_SAMPLES.
//   - clear_i pushes a flush marker through the SAME write FIFO (in-band,
//     ordered behind all pre-clear samples).  The DMA answers by dropping
//     its in-flight read, resetting both ring pointers and pushing a
//     generation marker into the read FIFO.  Entries pushed before that
//     marker are stale generations: this side discards them (1/cycle)
//     and only consumes entries after the marker, so pops stay 1:1 with
//     the restarted stream.
//   - Underrun (a warm state-1 with nothing consumable at the read FIFO
//     head) emits wet=0, matching the frames>=ECHO_SAMPLES gate; the
//     stream shifts by one sample until the next clear.  Unreachable in
//     normal operation: the DMA prefetch keeps ~448 entries (9.3 ms)
//     buffered against a single-outstanding ~us DDR round trip.  Sticky
//     flag records it if it ever happens.
//   - Overflow (write FIFO full, i.e. the DMA is >10 ms behind) drops the
//     new sample and sets a sticky flag rather than backpressuring the
//     synthesis path, mirroring the original never-blocks contract.
module serial_delay_effect_ddr #(
    parameter integer DELAY_BITS=14,
    parameter integer ECHO_SAMPLES=9600,
    parameter integer FIFO_ADDRESS_BITS=9
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
    output logic [7:0] debug_status_o
);
  import audio_math_pkg::*;
  logic [31:0] frames;
  logic [2:0] state;
  logic [15:0] gain;
  logic signed [31:0] input_l,input_r,read_l,read_r,feedback_l,feedback_r;
  logic signed [48:0] product_l,product_r;
  logic signed [63:0] feedback_wide_l,feedback_wide_r,mixed_l,mixed_r;
  assign ready_o=state==0;
  assign active_o=gain!=0||enabled_i;
  wire warm=frames>=ECHO_SAMPLES;

  // Write FIFO: audio domain pushes feedback pairs (and flush markers),
  // memory domain pops.  65 bits = {flush, right, left}.
  logic wr_fifo_ready,wr_flush_pending;
  wire wr_data_push=!clear_i && state==4 && !wr_flush_pending;
  wire wr_flush_push=wr_flush_pending;
  music_async_fifo #(.WIDTH(65),.ADDRESS_BITS(FIFO_ADDRESS_BITS)) u_write_fifo(
      .write_clk_i(clk_i),.write_rst_ni(rst_ni),
      .write_valid_i(wr_data_push||wr_flush_push),
      .write_data_i(wr_flush_push?{1'b1,64'd0}:{1'b0,feedback_r,feedback_l}),
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
  wire marker_pop=!clear_i && rd_head_valid && rd_head[64];
  wire use_pop=!clear_i && state==1 && warm && marker_seen &&
               rd_head_valid && !rd_head[64];
  wire discard_pop=!clear_i && rd_head_valid && !marker_seen && !rd_head[64];
  assign rd_pop=marker_pop||use_pop||discard_pop;

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if(!rst_ni) begin
      marker_seen<=1;underflow_sticky<=0;overflow_sticky<=0;wr_flush_pending<=0;
    end else if(clear_i) begin
      marker_seen<=0;underflow_sticky<=0;overflow_sticky<=0;wr_flush_pending<=1;
    end else begin
      if(wr_flush_pending && wr_fifo_ready) wr_flush_pending<=0;
      if(marker_pop) marker_seen<=1;
      if(state==1 && warm && !use_pop) underflow_sticky<=1;
      if(wr_data_push && !wr_fifo_ready) overflow_sticky<=1;
    end
  end

  // state 1 wet read: same cycle position as the original BRAM read, so
  // read_l/read_r are stable at state 2 exactly as before.
  always_ff @(posedge clk_i) begin
    if(!clear_i && state==1) begin
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
      if(clear_i) begin
        frames<=0;state<=0;gain<=0;valid_o<=0;clip_o<=0;
      end else case(state)
        0:if(valid_i) begin
          input_l<=left_i;input_r<=right_i;
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
          if(frames!=32'hffffffff)frames<=frames+1'b1;state<=0;
        end
        default:state<=0;
      endcase
    end
  end

  assign debug_status_o={3'b0,marker_seen,overflow_sticky,underflow_sticky,2'b00};
endmodule
