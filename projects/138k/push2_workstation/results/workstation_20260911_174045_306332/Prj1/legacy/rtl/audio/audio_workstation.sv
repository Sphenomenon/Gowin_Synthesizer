`timescale 1ns/1ps
`ifndef AUDIO_BEND_MEM_FILE
`define AUDIO_BEND_MEM_FILE "sim/data/audio_chain/pitch_bend_q20.mem"
`endif
// Portable, CPU-free MIDI -> synthesis -> stereo PCM/effects boundary.
module audio_workstation #(
    parameter integer SAMPLE_RATE_HZ=48000,
    parameter integer DELAY_BITS=14,
    parameter integer ECHO_SAMPLES=9600
) (
    input logic clk_i, rst_ni,
    input logic midi_byte_valid_i,
    input logic [7:0] midi_byte_i,
    input logic sample_ce_i,
    input logic signed [31:0] pcm_left_i, pcm_right_i,
    output logic sample_valid_o,
    output logic signed [31:0] left_o, right_o,
    output logic synth_valid_o,
    output logic signed [31:0] synth_o,
    output logic [31:0] active_mask_o,
    output logic [5:0] active_voice_count_o,
    output logic [1:0] mode_o,
    output logic [21:0] pitch_q20_o,
    output logic [31:0] deadline_miss_o, midi_overflow_o, note_drop_o,
    output logic clip_o,
    output logic [15:0] synth_gain_o, pcm_gain_o,
    output logic [2:0] effect_mask_o
);
  logic event_valid, event_ready;
  logic [17:0] event_data;
  logic fifo_event_valid,fifo_event_ready;
  logic [17:0] fifo_event_data;
  wire [3:0] kind = event_data[17:14];
  wire [6:0] a = event_data[13:7];
  wire [6:0] b = event_data[6:0];
  logic [2:0] profile;
  logic [1:0] requested_mode;
  logic mode_pending, mode_ready, mode_valid;
  logic [15:0] volume, expression_gain;
  logic [31:0] volume_product;
  logic [21:0] target_ratio;
  logic [21:0] bend_rom[0:255];
  logic [15:0] glide_step;
  logic [6:0] vibrato_depth;
  logic sustain, releasing;
  logic [6:0] release_index;
  logic [127:0] held, deferred;
  logic core_event_valid, core_event_ready, core_note_on;
  logic [6:0] core_note, core_velocity;
  logic core_sample_ready, core_ce, load_busy, mix_busy;
  logic pending, frame_inflight;
  logic [31:0] allocated;
  logic [7:0] issued;
  logic [31:0] held_pcm_l, held_pcm_r;
  logic fx_ready;
  logic dispatch, full;
  assign fifo_event_ready=!event_valid || event_ready;
  // Register the FIFO output before MIDI routing and 32-way note matching.
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if(!rst_ni) begin event_valid<=0;event_data<=0;end
    else if(fifo_event_ready) begin
      event_valid<=fifo_event_valid;
      if(fifo_event_valid) event_data<=fifo_event_data;
    end
  end
  initial $readmemh(`AUDIO_BEND_MEM_FILE,bend_rom);
  assign volume_product=volume*expression_gain;
  assign synth_gain_o=volume_product[30:15];
  assign mode_valid=mode_pending && mode_ready && !pending && !sample_ce_i;
  assign full= mode_o==2 ? &allocated[3:0] : &allocated;
  assign dispatch=!pending && !sample_ce_i && !load_busy && !mix_busy && !mode_valid;
  assign core_ce=(pending || sample_ce_i) && core_sample_ready;
  always_comb begin
    core_event_valid=0; core_note_on=0; core_note=a; core_velocity=b;
    event_ready=0;
    if(releasing) begin
      core_note=release_index; core_velocity=0;
      core_event_valid=dispatch && deferred[release_index];
    end else if(event_valid) begin
      if(kind==0 && sustain) event_ready=dispatch;
      else if(kind==0 || kind==1) begin
        core_note_on=kind==1;
        core_event_valid=dispatch && !(kind==1 && full);
        event_ready=dispatch && ((kind==1 && full) || core_event_ready);
      end else event_ready=dispatch;
    end
  end
  midi_stream_decoder decoder(.clk_i,.rst_ni,.byte_valid_i(midi_byte_valid_i),
      .byte_i(midi_byte_i),.event_valid_o(fifo_event_valid),.event_ready_i(fifo_event_ready),
      .event_o(fifo_event_data),.overflow_count_o(midi_overflow_o));
  pitch_expression #(.SAMPLE_RATE_HZ(SAMPLE_RATE_HZ)) pitch(
      .clk_i,.rst_ni,.sample_ce_i(core_ce),.target_ratio_q20_i(target_ratio),
      .glide_step_q20_i(glide_step),.vibrato_depth_i(vibrato_depth),.ratio_q20_o(pitch_q20_o));
  unified_oscillator_engine #(.EXPRESSION_ENABLE(1),.SAMPLE_RATE_HZ(SAMPLE_RATE_HZ)) engine(
      .clk_i,.rst_ni,.mode_set_valid_i(mode_valid),.mode_set_ready_o(mode_ready),
      .mode_i(requested_mode),.current_mode_o(mode_o),
      .event_valid_i(core_event_valid),.event_ready_o(core_event_ready),
      .event_note_on_i(core_note_on),.event_profile_i(profile),
      .event_midi_note_i(core_note),.event_velocity_i(core_velocity),
      .pitch_ratio_q20_i(pitch_q20_o),.sample_ce_i(core_ce),
      .sample_ready_o(core_sample_ready),.sample_valid_o(synth_valid_o),.sample_o(synth_o),
      .allocated_mask_o(allocated),.active_mask_o,.active_voice_count_o,
      .load_busy_o(load_busy),.mix_busy_o(mix_busy),.issued_slot_count_o(issued));
  stereo_effects #(.DELAY_BITS(DELAY_BITS),.ECHO_SAMPLES(ECHO_SAMPLES)) effects(
      .clk_i,.rst_ni,.valid_i(synth_valid_o),.synth_i(synth_o),
      .pcm_left_i($signed(held_pcm_l)),.pcm_right_i($signed(held_pcm_r)),
      .synth_gain_i(synth_gain_o),.pcm_gain_i(pcm_gain_o),.effect_mask_i(effect_mask_o),.effect_order_i(6'b10_01_00),
      .ready_o(fx_ready),.valid_o(sample_valid_o),.left_o,.right_o,.clip_o);
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if(!rst_ni) begin
      pending<=0; frame_inflight<=0; deadline_miss_o<=0; note_drop_o<=0;
      held_pcm_l<=0; held_pcm_r<=0; profile<=0; requested_mode<=2;
      mode_pending<=0; volume<=32768; expression_gain<=32768; pcm_gain_o<=0;
      target_ratio<=1048576; glide_step<=0; vibrato_depth<=0; effect_mask_o<=0;
      sustain<=0; held<=0; deferred<=0; releasing<=0; release_index<=0;
    end else begin
      if(sample_valid_o) frame_inflight<=0;
      if(sample_ce_i) begin
        pending<=1;
        if(frame_inflight || pending) deadline_miss_o<=deadline_miss_o+1;
        frame_inflight<=1;
      end
      if(core_ce) begin pending<=0; held_pcm_l<=pcm_left_i; held_pcm_r<=pcm_right_i; end
      if(synth_valid_o && !fx_ready) deadline_miss_o<=deadline_miss_o+1;
      if(mode_valid) mode_pending<=0;
      if(releasing && dispatch && (!deferred[release_index] || core_event_ready)) begin
        deferred[release_index]<=0;
        if(release_index==127) releasing<=0;
        else release_index<=release_index+1'b1;
      end
      if(event_valid && event_ready) begin
        case(kind)
          0: begin held[a]<=0; if(sustain) deferred[a]<=1; end
          1: if(full) note_drop_o<=note_drop_o+1; else begin held[a]<=1; deferred[a]<=0; end
          2: case(a)
            1: vibrato_depth<=b;
            5: glide_step<=b==0 ? 16'd0 : 16'd256-({9'd0,b}<<1);
            7: volume<=b==127 ? 16'd32768 : {b,8'd0};
            11: expression_gain<=b==127 ? 16'd32768 : {b,8'd0};
            16: pcm_gain_o<=b==127 ? 16'd32768 : {b,8'd0};
            64: begin
              sustain<=b>=64;
              if(b<64 && sustain) begin releasing<=1; release_index<=0; end
            end
            80: if(b<3) begin requested_mode<=b[1:0]; mode_pending<=1; end
            81: effect_mask_o<=b[2:0];
            120,123: begin
              deferred<=held|deferred; held<=0; sustain<=0;
              releasing<=1; release_index<=0;
            end
            default: begin end
          endcase
          3: begin
            if(a<8) profile<=4;
            else if(a<16) profile<=3;
            else if(a>=40 && a<48) profile<=1;
            else if(a>=56 && a<64) profile<=2;
            else profile<=0;
          end
          4: target_ratio<=bend_rom[{b,a[6]}];
          default: begin end
        endcase
      end
    end
  end
endmodule
