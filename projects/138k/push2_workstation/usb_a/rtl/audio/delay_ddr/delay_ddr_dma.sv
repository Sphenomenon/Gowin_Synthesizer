`timescale 1ns/1ps
// Memory-domain DMA for the DDR delay ring (arbiter owner 6, Plan B).
//
// The ring lives at PRJ1_DDR_BULK_POOL (byte 0x3000_0000, first granule):
// 16384 stereo samples x 8 bytes = 128 KiB, stored as 4-sample 256-bit
// chunks (app_addr counts 32-bit words, so chunk c sits at RING_APP_BASE
// + c*8 with the low three bits zero for one aligned BL8).
//
// Both pointers count absolute completed samples and never wrap for any
// practical run time; ring positions are their low DELAY_BITS.  The read
// pointer trails the write pointer by ECHO_SAMPLES by construction:
// entry #m is written when sample m completes and is prefetched into the
// read FIFO only when the audio side is within PREFETCH_KEEP samples of
// needing it (wptr >= rptr + ECHO_SAMPLES - PREFETCH_KEEP), which caps
// the read FIFO level near PREFETCH_KEEP and keeps the write path
// popping at all times.
//
// Flush protocol (see serial_delay_effect_ddr): a flush entry popped from
// the write FIFO makes the DMA drop any in-flight read response, reset
// both pointers and push one generation marker into the read FIFO; the
// audio side discards everything below that marker.
module delay_ddr_dma #(
    parameter integer DELAY_BITS=14,
    parameter integer ECHO_SAMPLES=9600,
    // = `PRJ1_DDR_BULK_POOL_APP_BASE (byte 0x3000_0000 >> 2, word units)
    parameter [28:0] RING_APP_BASE=29'h0c00_0000,
    parameter integer FIFO_ADDRESS_BITS=9
) (
    input logic clk_i,rst_ni,
    // write FIFO pop side (audio-side feedback stream)
    input logic dwr_valid_i,
    input logic [64:0] dwr_data_i,
    output logic dwr_pop_o,
    // read FIFO push side (wet samples for the audio side)
    output logic drd_push_o,
    output logic [64:0] drd_data_o,
    input logic drd_ready_i,
    // arbiter owner-6 channel
    output logic ddr_req_o,
    output logic ddr_write_o,
    output logic [28:0] ddr_address_o,
    output logic [255:0] ddr_data_o,
    output logic [31:0] ddr_mask_o,
    input logic ddr_ready_i,
    input logic ddr_response_i,
    input logic [255:0] ddr_read_data_i,
    output logic [7:0] debug_status_o
);
  localparam integer DEPTH=1<<DELAY_BITS;              // samples per ring
  localparam integer RING_CHUNKS=DEPTH/4;              // 256-bit chunks
  // Keep the read FIFO this far below full so a 4-entry push burst and CDC
  // skew can never overflow it; also the startup prefetch plateau (9.3 ms).
  localparam integer PREFETCH_KEEP=(1<<FIFO_ADDRESS_BITS)-64;
  localparam [2:0] S_IDLE=3'd0,S_WR_REQ=3'd1,S_RD_REQ=3'd2,S_RD_WAIT=3'd3,
                   S_RD_PUSH=3'd4,S_FLUSH_DRAIN=3'd5,S_RD_MARKER=3'd6;
  logic [2:0] state;
  logic [31:0] wptr,rptr;
  logic [255:0] chunk_buf;
  logic [255:0] rsp_hold;
  logic [1:0] push_lane;
  logic [28:0] req_addr;
  logic read_outstanding,flush_seen,flush_done;

  wire [11:0] wr_chunk=wptr[13:2];
  wire [11:0] rd_chunk=rptr[13:2];
  // Prefetch chunk rd_chunk once the audio side is PREFETCH_KEEP samples
  // away from consuming its first entry; wptr-rptr>=4 (chunk fully
  // written) is implied because ECHO_SAMPLES >> PREFETCH_KEEP.
  wire rd_fetch_due=(wptr-rptr)>=(ECHO_SAMPLES-PREFETCH_KEEP) && !read_outstanding && drd_ready_i;
  wire pop_data=dwr_valid_i && !dwr_data_i[64] && state==S_IDLE;
  wire pop_flush=dwr_valid_i && dwr_data_i[64] && state==S_IDLE;

  assign dwr_pop_o=pop_data||pop_flush;
  assign ddr_mask_o=32'h0000_0000;              // active-low lanes: write all 32 bytes
  assign ddr_req_o=(state==S_WR_REQ)||(state==S_RD_REQ);
  assign ddr_write_o=(state==S_WR_REQ);
  assign ddr_address_o=req_addr;
  assign ddr_data_o=chunk_buf;
  assign drd_push_o=(state==S_RD_PUSH)||(state==S_RD_MARKER);
  assign drd_data_o=(state==S_RD_MARKER)?{1'b1,64'd0}:{1'b0,rsp_hold[push_lane*64+:64]};

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if(!rst_ni) begin
      state<=S_IDLE;wptr<=0;rptr<=0;chunk_buf<=0;rsp_hold<=0;push_lane<=0;
      req_addr<=0;read_outstanding<=0;flush_seen<=0;flush_done<=0;
    end else begin
      case(state)
        S_IDLE:begin
          if(pop_flush) begin
            flush_seen<=1;
            state<=read_outstanding?S_FLUSH_DRAIN:S_RD_MARKER;
          end else if(pop_data) begin
            chunk_buf[wptr[1:0]*64 +: 64] <= dwr_data_i[63:0];
            wptr<=wptr+1'b1;
            if(wptr[1:0]==2'b11) begin
              req_addr<=RING_APP_BASE+{16'd0,wr_chunk,3'b000};
              state<=S_WR_REQ;
            end
          end else if(rd_fetch_due) begin
            req_addr<=RING_APP_BASE+{16'd0,rd_chunk,3'b000};
            read_outstanding<=1;
            state<=S_RD_REQ;
          end
        end
        S_WR_REQ:if(ddr_ready_i) state<=S_IDLE;
        S_RD_REQ:if(ddr_ready_i) state<=S_RD_WAIT;
        S_RD_WAIT:if(ddr_response_i) begin
          rsp_hold<=ddr_read_data_i;
          read_outstanding<=0;
          push_lane<=0;
          state<=S_RD_PUSH;
        end
        // Four pushes per fetched chunk; stall burst if the FIFO backs up.
        S_RD_PUSH:if(drd_ready_i) begin
          if(push_lane==2'b11) begin
            rptr<=rptr+4;
            state<=S_IDLE;
          end else push_lane<=push_lane+1'b1;
        end
        S_FLUSH_DRAIN:if(ddr_response_i) begin
          read_outstanding<=0;
          state<=S_RD_MARKER;
        end
        S_RD_MARKER:if(drd_ready_i) begin
          wptr<=0;rptr<=0;flush_done<=1;
          state<=S_IDLE;
        end
        default:state<=S_IDLE;
      endcase
    end
  end

  assign debug_status_o={3'b0,flush_done,flush_seen,2'b00};
endmodule
