`timescale 1ns/1ps
// Transaction coordinator shared by TF import and the approved single-note loopback.
// Capture occurs AFTER reservation, never before. Commit only on exact CRC/length.
module sampler_storage(
  input logic clk,rst_n,restart,load_start,capture_start,capture_stop,
  input logic [5:0] slot,input logic [7:0] owner,
  input logic [31:0] expected_frames,expected_crc,
  input logic [1:0] granularity,input logic contains_rhythm,contains_melody,contains_arrangement,normalize,
  input logic approved_single_note,sequencer_running,input logic [5:0] active_voices,
  input logic sample_valid,input logic signed [15:0] pcm_l,pcm_r,
  input logic [7:0] source_error,
  input logic in_valid,input logic [7:0] in_byte,input logic in_last,output logic in_ready,
  input logic [63:0] referenced,input logic free_slot,
  input logic [5:0] query_slot,output sampler_pkg::descriptor_t descriptor,
  output logic busy,done,output logic [7:0] error,
  output logic [31:0] committed_frames,committed_gain,committed_crc,
  output logic write_valid,input logic write_ready,
  output logic [31:0] write_address,write_base,write_capacity,
  output logic [255:0] write_data,
  input logic response_valid,input logic [7:0] response_error
);
  import sampler_pkg::*;
  typedef enum logic [2:0] {IDLE,RESERVE,LAUNCH,RUN,COMMIT,ABORT,COMPLETE} state_t;
  state_t state;logic capturing;
  logic [5:0] target_slot;logic [7:0] target_owner;
  logic pool_done,reserve_sent;logic [7:0] pool_error,epoch;
  logic [31:0] base,capacity,imp_frames,imp_gain,imp_crc,cap_frames,cap_crc;
  logic imp_busy,imp_done,cap_busy,cap_done,imp_valid,cap_valid;
  logic [7:0] imp_error,cap_error;
  logic [31:0] imp_addr,cap_addr,imp_base,cap_base,imp_capacity,cap_capacity;
  logic [255:0] imp_data,cap_data;
  assign busy=state!=IDLE;assign write_valid=capturing ? cap_valid : imp_valid;
  assign write_address=capturing ? cap_addr : imp_addr;
  assign write_base=capturing ? cap_base : imp_base;assign write_capacity=capturing ? cap_capacity : imp_capacity;
  assign write_data=capturing ? cap_data : imp_data;
  sampler_pool u_pool(.clk(clk),.rst_n(rst_n),.restart(restart),.reserve(state==RESERVE && !reserve_sent),
    .slot(state==IDLE ? slot : target_slot),.owner(state==IDLE ? owner : target_owner),
    .bytes(expected_frames<=288000 ? expected_frames*2 : 0),
    .commit(state==COMMIT && !pool_done),.abort_slot(state==ABORT && !pool_done),.free_slot(free_slot && state==IDLE),
    .frames(committed_frames),.gain_q16(committed_gain),.crc32(committed_crc),.referenced(referenced),
    .done(pool_done),.error(pool_error),.query_slot(query_slot),.descriptor(descriptor),
    .reserved_base(base),.reserved_capacity(capacity),.epoch(epoch));
  sampler_import u_import(.clk(clk),.rst_n(rst_n),.restart(restart || (state==RUN && source_error!=OK && !capturing)),.start(state==LAUNCH && !capturing),
    .granularity(granularity),.contains_rhythm(contains_rhythm),.contains_melody(contains_melody),
    .contains_arrangement(contains_arrangement),.normalize(normalize),.expected_frames(expected_frames),
    .expected_crc(expected_crc),.base_bytes(base),.capacity_bytes(capacity),
    .in_valid(in_valid),.in_byte(in_byte),.in_last(in_last),.in_ready(in_ready),
    .write_valid(imp_valid),.write_ready(write_ready && !capturing),.write_address(imp_addr),
    .write_base(imp_base),.write_capacity(imp_capacity),.write_data(imp_data),
    .response_valid(response_valid && !capturing),.response_error(response_error),
    .busy(imp_busy),.done(imp_done),.error(imp_error),.frames(imp_frames),.gain_q16(imp_gain),.crc32(imp_crc));
  sampler_resample u_capture(.clk(clk),.rst_n(rst_n),.restart(restart),.start(state==LAUNCH && capturing),
    .stop(capture_stop),.approved_single_note(approved_single_note),.sequencer_running(sequencer_running),
    .active_voices(active_voices),.sample_valid(sample_valid),.pcm_l(pcm_l),.pcm_r(pcm_r),
    .base_bytes(base),.capacity_bytes(capacity),.max_frames(expected_frames),
    .write_valid(cap_valid),.write_ready(write_ready && capturing),.write_address(cap_addr),
    .write_base(cap_base),.write_capacity(cap_capacity),.write_data(cap_data),
    .response_valid(response_valid && capturing),.response_error(response_error),
    .busy(cap_busy),.done(cap_done),.error(cap_error),.frames(cap_frames),.crc32(cap_crc));
  always_ff @(posedge clk or negedge rst_n) begin
    if(!rst_n) begin state<=IDLE;done<=0;error<=0;capturing<=0;target_slot<=0;target_owner<=0;
      committed_frames<=0;committed_gain<=65536;committed_crc<=0;reserve_sent<=0;end
    else begin
      done<=0;
      if(restart) begin state<=IDLE;reserve_sent<=0;end
      else case(state)
        IDLE: if(load_start || capture_start) begin
          reserve_sent<=0;capturing<=capture_start;target_slot<=slot;target_owner<=owner;error<=OK;
          if(load_start && capture_start) begin done<=1;error<=E_BUSY;end
          else state<=RESERVE;
        end
        RESERVE: begin reserve_sent<=1;if(pool_done) begin if(pool_error!=OK) begin error<=pool_error;state<=COMPLETE;end else state<=LAUNCH;end end
        LAUNCH:state<=RUN;
        RUN: if(!capturing && source_error!=OK) begin error<=source_error;state<=ABORT;end
        else if(capturing ? cap_done : imp_done) begin
          error<=capturing ? cap_error : imp_error;
          committed_frames<=capturing ? cap_frames : imp_frames;
          committed_gain<=capturing ? 65536 : imp_gain;
          committed_crc<=capturing ? cap_crc : imp_crc;
          state<=(capturing ? cap_error : imp_error)==OK ? COMMIT : ABORT;
        end
        COMMIT:if(pool_done) begin error<=pool_error;state<=COMPLETE;end
        ABORT:if(pool_done) state<=COMPLETE;
        COMPLETE:begin done<=1;state<=IDLE;end
        default:state<=IDLE;
      endcase
    end
  end
endmodule
