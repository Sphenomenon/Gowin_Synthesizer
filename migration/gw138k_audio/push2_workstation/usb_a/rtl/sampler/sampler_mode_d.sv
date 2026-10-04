`timescale 1ns/1ps
// Portable mode-D instrument boundary. All signals use the 76.8MHz audio clock.
// DDR UI-clock CDC and the outer tag FIFO are integration responsibilities.
module sampler_mode_d(
  input logic clk,rst_n,restart,panic,enable,sample_tick,
  input logic event_valid,output logic event_ready,input logic [17:0] event_data,
  input logic pad_write,input logic [5:0] pad_index,input sampler_pkg::pad_t pad_config,
  output logic [5:0] descriptor_slot,input sampler_pkg::descriptor_t descriptor,
  output logic [63:0] referenced,
  input logic seq_start,seq_stop,record_enable,metronome_enable,
  input logic [8:0] bpm,input logic [5:0] swing,
  input logic select_valid,input logic [3:0] select_pattern,
  input logic edit_valid,input logic [3:0] edit_pattern,edit_step,input logic [1:0] edit_track,
  input logic [6:0] edit_note,edit_velocity,input logic [31:0] edit_gate_frames,
  input logic chain_write,input logic [3:0] chain_index,chain_pattern,input logic [4:0] chain_length,
  output logic seq_running,output logic [3:0] pattern,step,output logic [63:0] grid,
  output logic [1:0] group_select,
  input logic storage_valid,storage_write,
  input logic [31:0] storage_address,storage_base,storage_capacity,input logic [255:0] storage_data,
  output logic storage_ready,storage_response,
  output logic [255:0] storage_response_data,output logic [7:0] storage_error,
  output logic req_valid,req_write,input logic req_ready,output logic [28:0] req_addr,
  output logic [255:0] req_data,output logic [15:0] req_tag,
  input logic rsp_valid,input logic [15:0] rsp_tag,input logic [255:0] rsp_data,
  output logic pcm_valid,output logic signed [15:0] pcm_l,pcm_r,
  output logic [6:0] delay_send,output logic [15:0] active_mask,output logic [5:0] active_count,
  output logic [31:0] deadline_misses,max_latency,ddr_beats,seq_jitter_samples,
  output logic [7:0] voice_error,ddr_error,seq_error
);
  import sampler_pkg::*;
  pad_t selected_pad;
  logic [$bits(pad_t)-1:0] pads[64];logic [63:0] pad_valid;
  logic push_valid,push_ready,pattern_valid;logic [3:0] pad_pattern;
  logic [17:0] push_event,seq_event,voice_event,buffer_event;
  pad_t buffer_pad;descriptor_t buffer_descriptor;
  logic buffer_valid,buffer_ready;logic seq_valid,seq_ready,voice_valid,voice_ready;
  logic [31:0] seq_timestamp,sample_time,dispatched;
  logic click_trigger;logic signed [15:0] click_pcm,voice_l,voice_r,fx_l,fx_r;
  logic voice_pcm_valid,fx_valid;
  logic v_read,v_ready;
  logic [31:0] v_address,v_base,v_capacity,voice_reads,frame_cycles,stale_responses;
  logic [1:0] client_valid,client_write,client_ready,client_response;
  logic [31:0] address[2],base[2],capacity[2];logic [255:0] data[2],response_data;
  logic [7:0] response_error;
  logic hard_panic,push_in_ready,voice_tick;
  logic [4:0] frame_delay;
  assign event_ready=enable && push_in_ready;
  // Dispatch the timestamped batch before starting this frame's voice scan.
  // Eight off/on events take <=8 clocks; reserve 16 clocks including mapper.
  always_ff @(posedge clk or negedge rst_n) begin
    if(!rst_n) begin frame_delay<=0;voice_tick<=0;end
    else begin
      voice_tick<=0;
      if(sample_tick) frame_delay<=16;
      else if(frame_delay!=0) begin frame_delay<=frame_delay-1;voice_tick<=frame_delay==1;end
      if(restart || hard_panic) begin frame_delay<=0;voice_tick<=0;end
    end
  end
  assign hard_panic=panic || (event_valid && enable && event_data[17:14]==2 && event_data[13:7]==120);
  sampler_push u_push(.clk(clk),.rst_n(rst_n),.panic(hard_panic || restart),
    .in_valid(event_valid && enable),.in_ready(push_in_ready),.in_event(event_data),
    .out_valid(push_valid),.out_ready(push_ready),.out_event(push_event),
    .pattern_valid(pattern_valid),.pattern(pad_pattern),.group_select(group_select));
  sampler_sequencer u_seq(.clk(clk),.rst_n(rst_n),.panic(hard_panic),.restart(restart),.sample_tick(sample_tick),
    .start(seq_start && enable),.stop(seq_stop),.record_enable(record_enable),.bpm(bpm),.swing(swing),
    .select_valid(select_valid || pattern_valid),.select_pattern(pattern_valid ? pad_pattern : select_pattern),
    .edit_valid(edit_valid),.edit_pattern(edit_pattern),.edit_step(edit_step),.edit_track(edit_track),
    .edit_note(edit_note),.edit_velocity(edit_velocity),.edit_gate_frames(edit_gate_frames),
    .chain_write(chain_write),.chain_index(chain_index),.chain_pattern(chain_pattern),.chain_length(chain_length),
    .live_valid(push_valid && push_ready),.live_event(push_event),
    .event_valid(seq_valid),.event_ready(seq_ready),.event_data(seq_event),.event_timestamp(seq_timestamp),
    .sample_time(sample_time),.running(seq_running),.click(click_trigger),.pattern(pattern),.step(step),.grid(grid),
    .max_jitter_samples(seq_jitter_samples),.dispatched(dispatched),.error(seq_error));
  assign voice_event=seq_valid ? seq_event : push_event;
  assign voice_valid=seq_valid || push_valid;
  assign buffer_ready=!buffer_valid || voice_ready;
  assign seq_ready=buffer_ready;
  assign push_ready=buffer_ready && !seq_valid;
  always_comb begin
    selected_pad='0;
    if(voice_event[13:7]>=36 && voice_event[13:7]<=99 && pad_valid[voice_event[13:7]-36]) selected_pad=pad_t'(pads[voice_event[13:7]-36]);
  end
  assign descriptor_slot=selected_pad.slot;
  always_ff @(posedge clk or negedge rst_n) begin
    if(!rst_n) begin buffer_valid<=0;buffer_event<=0;buffer_pad<='0;buffer_descriptor<='0;end
    else begin
      if(buffer_ready) begin
        buffer_valid<=voice_valid;
        if(voice_valid) begin buffer_event<=voice_event;buffer_pad<=selected_pad;buffer_descriptor<=descriptor;end
      end
      if(restart || hard_panic) buffer_valid<=0;
    end
  end
  always_ff @(posedge clk or negedge rst_n) begin
    if(!rst_n) pad_valid<=0;else if(pad_write) pad_valid[pad_index]<=1;
  end
  always_ff @(posedge clk) if(pad_write) pads[pad_index]<=pad_config;
  sampler_voice u_voice(.clk(clk),.rst_n(rst_n),.restart(restart),.panic(hard_panic),.sample_tick(voice_tick),
    .event_valid(buffer_valid),.event_data(buffer_event),.event_pad(buffer_pad),.event_descriptor(buffer_descriptor),
    .event_ready(voice_ready),.read_valid(v_read),.read_ready(v_ready),.read_address(v_address),
    .read_base(v_base),.read_capacity(v_capacity),.response_valid(client_response[0]),
    .response_data(response_data),.response_error(response_error),
    .pcm_valid(voice_pcm_valid),.pcm_l(voice_l),.pcm_r(voice_r),.active_mask(active_mask),
    .referenced(referenced),.active_count(active_count),.deadline_misses(deadline_misses),
    .read_beats(voice_reads),.frame_cycles_max(frame_cycles),.error(voice_error));
  assign client_valid={storage_valid,v_read};assign client_write={storage_write,1'b0};
  assign address[0]=v_address;assign address[1]=storage_address;
  assign base[0]=v_base;assign base[1]=storage_base;assign capacity[0]=v_capacity;assign capacity[1]=storage_capacity;
  assign data[0]=256'd0;assign data[1]=storage_data;
  assign v_ready=client_ready[0];assign storage_ready=client_ready[1];
  assign storage_response=client_response[1];assign storage_response_data=response_data;assign storage_error=response_error;
  sampler_ddr #(.CLIENTS(2),.MAX_WAIT(18)) u_ddr(.clk(clk),.rst_n(rst_n),.restart(restart),
    .valid(client_valid),.write(client_write),.address(address),.base(base),.capacity(capacity),.data(data),
    .ready(client_ready),.response(client_response),.response_data(response_data),.response_error(response_error),
    .req_valid(req_valid),.req_write(req_write),.req_ready(req_ready),.req_addr(req_addr),.req_data(req_data),.req_tag(req_tag),
    .rsp_valid(rsp_valid),.rsp_tag(rsp_tag),.rsp_data(rsp_data),.max_latency(max_latency),.beats(ddr_beats),
    .stale_responses(stale_responses),.fault(ddr_error));
  sampler_fx u_fx(.clk(clk),.rst_n(rst_n),.panic(hard_panic),
    .cc_valid(push_valid && push_ready && push_event[17:14]==2),.cc(push_event[13:7]),.value(push_event[6:0]),
    .pcm_valid(voice_pcm_valid),.pcm_l(voice_l),.pcm_r(voice_r),.out_valid(fx_valid),.out_l(fx_l),.out_r(fx_r),.delay_send(delay_send));
  sampler_click u_click(.clk(clk),.rst_n(rst_n),.panic(hard_panic),.sample_tick(sample_tick),
    .trigger(click_trigger),.enable(metronome_enable && enable),.pcm(click_pcm));
  always_ff @(posedge clk or negedge rst_n) begin
    if(!rst_n) begin pcm_valid<=0;pcm_l<=0;pcm_r<=0;end
    else begin
      pcm_valid<=fx_valid;
      if(fx_valid) begin pcm_l<=sat16(64'(fx_l)+64'(click_pcm));pcm_r<=sat16(64'(fx_r)+64'(click_pcm));end
      if(hard_panic || restart) begin pcm_l<=0;pcm_r<=0;pcm_valid<=0;end
    end
  end
endmodule
