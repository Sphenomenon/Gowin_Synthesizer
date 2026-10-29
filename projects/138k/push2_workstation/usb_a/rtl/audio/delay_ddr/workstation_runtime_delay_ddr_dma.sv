`timescale 1ns/1ps
// Independent native runtime owner6 delay DMA. Ring allocation remains
// byte0x30000000,128KiB; app addresses are32bit WORD units.
// Config marker[64]=1,payload[32:1]=transaction,payload[0]=rate44.
// On flush, old reads are drained/discarded, then an ordered fence read of
// last accepted write-address must RETURN before the matching ACK is queued.
// This isolates old posted commands through the stable owner6 client slot
// and single-command native queue; write-ready alone is not completion.
// Mandatory peer heartbeat detects a stopped audio clock while memory runs.
module workstation_runtime_delay_ddr_dma #(
    parameter integer DELAY_BITS=14,
    parameter integer ECHO_SAMPLES=9600,
    // = `PRJ1_DDR_BULK_POOL_APP_BASE (byte 0x3000_0000 >> 2, word units)
    parameter [28:0] RING_APP_BASE=29'h0c00_0000,
    parameter integer FIFO_ADDRESS_BITS=9,
    parameter integer TRANSACTION_TIMEOUT_CYCLES=1048576,
    parameter integer PEER_TIMEOUT_CYCLES=1048576
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
    output logic [7:0] debug_status_o,
    output logic flush_done_o,fault_o,
    output logic applied_rate_44100_o,
    output logic [31:0] applied_transaction_o,
    input logic peer_heartbeat_i,
    output logic heartbeat_o
);
  localparam integer DEPTH=1<<DELAY_BITS;              // samples per ring
  localparam integer RING_CHUNKS=DEPTH/4;              // 256-bit chunks
  // Keep the read FIFO this far below full so a 4-entry push burst and CDC
  // skew can never overflow it; also the startup prefetch plateau (9.3 ms).
  localparam integer PREFETCH_KEEP=(1<<FIFO_ADDRESS_BITS)-64;
  localparam [3:0] S_IDLE=4'd0,S_WR_REQ=4'd1,S_RD_REQ=4'd2,S_RD_WAIT=4'd3,
                   S_RD_PUSH=4'd4,S_FLUSH_DRAIN=4'd5,S_RD_MARKER=4'd6,S_PACK=4'd7,
                   S_FENCE_REQ=4'd8,S_FENCE_WAIT=4'd9;
  logic [3:0] state;
  logic [31:0] wptr,rptr;
  logic [255:0] chunk_buf;
  logic [63:0] popped_sample;
  logic [255:0] rsp_hold;
  logic [1:0] push_lane;
  logic [28:0] req_addr,last_write_address;
  logic read_outstanding,flush_seen,flush_done;
  logic [63:0] pending_marker;
  logic [31:0] wait_cycles,peer_wait;
  logic [4:0] heartbeat_counter;
  (* ASYNC_REG="TRUE" *) logic peer_meta,peer_sync;
  logic peer_last,watchdog_fault,protocol_fault,peer_fault;
  wire [31:0] echo_samples=applied_rate_44100_o ? 32'd8820 : 32'(ECHO_SAMPLES);
  wire [11:0] wr_chunk=wptr[13:2];
  wire [11:0] rd_chunk=rptr[13:2];
  wire rd_fetch_due=(wptr-rptr)>=(echo_samples-32'(PREFETCH_KEEP)) && !read_outstanding && drd_ready_i;
  wire pop_data=dwr_valid_i && !dwr_data_i[64] && state==S_IDLE;
  wire pop_flush=dwr_valid_i && dwr_data_i[64] &&
      (state==S_IDLE || state==S_RD_WAIT || state==S_RD_PUSH);
  wire progress=pop_data||pop_flush||state==S_PACK||
      ((state==S_WR_REQ||state==S_RD_REQ||state==S_FENCE_REQ)&&ddr_ready_i)||
      ((state==S_RD_WAIT||state==S_FLUSH_DRAIN||state==S_FENCE_WAIT)&&ddr_response_i)||
      ((state==S_RD_PUSH||state==S_RD_MARKER)&&drd_ready_i);
  assign heartbeat_o=heartbeat_counter[4];
  assign fault_o=watchdog_fault||protocol_fault||peer_fault;
  initial begin
    if(DELAY_BITS!=14 || ECHO_SAMPLES!=9600 || FIFO_ADDRESS_BITS<7 ||
       FIFO_ADDRESS_BITS>9 || TRANSACTION_TIMEOUT_CYCLES<2 || PEER_TIMEOUT_CYCLES<128)
      $fatal(1,"runtime delay DMA requires the audited128KiB ring and200ms baseline");
  end
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if(!rst_ni)begin heartbeat_counter<=0;peer_meta<=0;peer_sync<=0;peer_last<=0;
      peer_wait<=0;wait_cycles<=0;watchdog_fault<=0;peer_fault<=0;end
    else begin
      heartbeat_counter<=heartbeat_counter+1'b1;
      peer_meta<=peer_heartbeat_i;peer_sync<=peer_meta;
      if(peer_sync!=peer_last)begin peer_wait<=0;peer_last<=peer_sync;end
      else if(peer_wait<32'(PEER_TIMEOUT_CYCLES))peer_wait<=peer_wait+1'b1;
      if(peer_wait>=32'(PEER_TIMEOUT_CYCLES)-1)peer_fault<=1;
      if(state==S_IDLE || progress)wait_cycles<=0;
      else begin
        if(wait_cycles<32'(TRANSACTION_TIMEOUT_CYCLES))wait_cycles<=wait_cycles+1'b1;
        if(wait_cycles>=32'(TRANSACTION_TIMEOUT_CYCLES)-1)watchdog_fault<=1;
      end
    end
  end
  assign dwr_pop_o=pop_data||pop_flush;
  assign ddr_mask_o=32'h0000_0000;              // active-low lanes: write all 32 bytes
  assign ddr_req_o=(state==S_WR_REQ)||(state==S_RD_REQ)||(state==S_FENCE_REQ);
  assign ddr_write_o=(state==S_WR_REQ);
  assign ddr_address_o=req_addr;
  assign ddr_data_o=chunk_buf;
  assign drd_push_o=(state==S_RD_PUSH && !pop_flush)||(state==S_RD_MARKER && !fault_o);
  assign drd_data_o=(state==S_RD_MARKER)?{1'b1,pending_marker}:{1'b0,rsp_hold[push_lane*64+:64]};

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if(!rst_ni) begin
      state<=S_IDLE;wptr<=0;rptr<=0;chunk_buf<=0;rsp_hold<=0;push_lane<=0;
      popped_sample<=0;req_addr<=0;last_write_address<=RING_APP_BASE;
      read_outstanding<=0;flush_seen<=0;flush_done<=0;pending_marker<=0;
      applied_rate_44100_o<=0;applied_transaction_o<=0;flush_done_o<=0;protocol_fault<=0;
    end else begin
      flush_done_o<=0;
      if(ddr_response_i && !(state==S_RD_WAIT || state==S_FLUSH_DRAIN || state==S_FENCE_WAIT))
        protocol_fault<=1;
      // Preempt a pending read burst only at an accepted in-band marker.
      // Any same-cycle response is discarded, never forwarded past the ACK.
      if(pop_flush)begin
        flush_seen<=1;flush_done<=0;pending_marker<=dwr_data_i[63:0];
        if(dwr_data_i[63:33]!=31'd0)protocol_fault<=1;
        req_addr<=last_write_address;
        if(read_outstanding && !ddr_response_i)state<=S_FLUSH_DRAIN;
        else begin read_outstanding<=0;state<=S_FENCE_REQ;end
      end else case(state)
        S_IDLE:begin
          if(pop_data) begin
            popped_sample<=dwr_data_i[63:0];state<=S_PACK;
          end else if(rd_fetch_due)begin
            req_addr<=RING_APP_BASE+{14'd0,rd_chunk,3'b000};
            read_outstanding<=1;state<=S_RD_REQ;
          end
        end
        S_PACK:begin
          state<=S_IDLE;chunk_buf[wptr[1:0]*64+:64]<=popped_sample;
          wptr<=wptr+1'b1;
          if(wptr[1:0]==2'b11)begin
            req_addr<=RING_APP_BASE+{14'd0,wr_chunk,3'b000};state<=S_WR_REQ;
          end
        end
        S_WR_REQ:if(ddr_ready_i)begin last_write_address<=req_addr;state<=S_IDLE;end
        S_RD_REQ:if(ddr_ready_i)state<=S_RD_WAIT;
        S_RD_WAIT:if(ddr_response_i)begin
          rsp_hold<=ddr_read_data_i;read_outstanding<=0;push_lane<=0;state<=S_RD_PUSH;
        end
        S_RD_PUSH:if(drd_ready_i)begin
          if(push_lane==2'b11)begin rptr<=rptr+4;state<=S_IDLE;end
          else push_lane<=push_lane+1'b1;
        end
        S_FLUSH_DRAIN:if(ddr_response_i)begin
          read_outstanding<=0;state<=S_FENCE_REQ;
        end
        S_FENCE_REQ:if(ddr_ready_i)begin read_outstanding<=1;state<=S_FENCE_WAIT;end
        S_FENCE_WAIT:if(ddr_response_i)begin
          read_outstanding<=0;state<=S_RD_MARKER;
        end
        S_RD_MARKER:if(drd_ready_i && !fault_o)begin
          wptr<=0;rptr<=0;chunk_buf<=0;rsp_hold<=0;popped_sample<=0;
          applied_rate_44100_o<=pending_marker[0];applied_transaction_o<=pending_marker[32:1];
          flush_done<=1;flush_done_o<=1;state<=S_IDLE;
        end
        default:state<=S_IDLE;
      endcase
    end
  end

  assign debug_status_o={4'b0,flush_done,flush_seen,2'b00};
endmodule
