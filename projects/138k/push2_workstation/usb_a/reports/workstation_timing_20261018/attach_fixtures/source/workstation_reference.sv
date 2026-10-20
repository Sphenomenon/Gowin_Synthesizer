`timescale 1ns/1ps
`ifndef AUDIO_BEND_MEM_FILE
`define AUDIO_BEND_MEM_FILE "sim/data/audio_chain/pitch_bend_q20.mem"
`endif
// Portable, CPU-free MIDI -> synthesis -> stereo PCM/effects boundary.
module gw138k_event_workstation_reference #(
    parameter integer SAMPLE_RATE_HZ=48000,
    parameter integer DELAY_BITS=14,
    parameter integer ECHO_SAMPLES=9600
) (
    input logic clk_i, rst_ni,
    input logic midi_byte_valid_i,
    input logic [7:0] midi_byte_i,
    input logic pc_byte_valid_i,
    input logic [7:0] pc_byte_i,
    output wire [127:0] held_notes_o,
    output logic [31:0] applied_events_o,
    output wire [31:0] pc_overflow_o,control_options_o,
    output logic [9:0] panic_epoch_o,
    input logic cpu_event_valid_i,
    input logic [17:0] cpu_event_i,
    output wire cpu_event_ready_o,
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
    output logic [1:0] route_o,
    output wire [2:0] profile_o,
    output wire [2:0] effect_mask_o,
    output logic [5:0] effect_order_o,
    output logic panel_event_valid_o,
    output wire [31:0] scope_status_o,tf_scope_control_o,
    output logic [6:0] panel_command_o,
    // P10 delay DDR ring bridge (memory-domain side, see delay_ddr_dma)
    input logic delay_mem_clk_i, delay_mem_rst_ni,
    output logic delay_dwr_valid_o,
    output logic [64:0] delay_dwr_data_o,
    input logic delay_dwr_pop_i,
    input logic delay_drd_push_i,
    input logic [64:0] delay_drd_data_i,
    output logic delay_drd_ready_o
);
  initial begin
    if(SAMPLE_RATE_HZ!=48000) $fatal(1,"scope integration requires exact 48 kHz");
  end
  logic [1:0] effect_count;
  logic [2:0] effect_selected;
  logic effect_master;
  assign effect_mask_o=effect_master ? effect_selected : 3'b000;
  logic event_valid, event_ready;
  logic [17:0] event_data;
  logic fifo_event_valid,fifo_event_ready;
  wire cue_valid,cue_ready,cue_running,cue_done,cue_error;
  wire [17:0] cue_event;
  wire [31:0] cue_late,cue_time;
  logic [6:0] cue_speed;
  wire register_room=!event_valid || event_ready;
  // Kind 15 belongs only to the on-chip USB lifecycle link. Ordinary MIDI
  // decoders cannot generate it. Detach/PANIC bypass the initialization wait.
  wire usb_internal=cpu_event_i[17:14]==4'd15;
  wire usb_lifecycle=cpu_event_valid_i && usb_internal && cpu_event_i[6:0]<3;
  wire usb_attach=usb_lifecycle && cpu_event_i[6:0]==7'd1;
  logic attach_initializing;
  logic [3:0] attach_step;
  wire arbiter_cpu_ready;
  assign cpu_event_ready_o=usb_lifecycle || (!attach_initializing && (usb_internal || arbiter_cpu_ready));
  function automatic [17:0] attach_event(input [3:0] step);
    case(step)
      0: attach_event={4'd2,7'd96,7'd0}; // stop cue
      1: attach_event={4'd2,7'd104,7'd0}; // leave TF
      2: attach_event={4'd2,7'd90,7'd0}; // leave live vector after PANIC
      3: attach_event={4'd4,7'd0,7'd64}; // center bend
      4: attach_event={4'd2,7'd64,7'd0};
      5: attach_event={4'd2,7'd11,7'd127};
      6: attach_event={4'd2,7'd1,7'd0};
      7: attach_event={4'd2,7'd5,7'd0};
      8: attach_event={4'd2,7'd82,7'd0};
      9: attach_event={4'd2,7'd7,7'd127};
      10:attach_event={4'd3,7'd73,7'd0};
      11:attach_event={4'd2,7'd80,7'd2};
      default:attach_event={4'd2,7'd81,7'd0};
    endcase
  endfunction
  wire cue_start=event_valid && event_ready && kind==2 && a==96 && b==127 && !tf_scope_control_o[12] && (scope_enable || legacy_active_mask==0);
  wire cue_stop=usb_lifecycle || (event_valid && event_ready && kind==2 && ((a==96 && b==0) || a==120 || a==123));
  assign cue_ready=register_room && !attach_initializing && !fifo_event_valid && !cue_stop;
  scope_control_player cue_player(
      .clk_i,.rst_ni,.sample_ce_i(core_ce),.start_i(cue_start),.stop_i(cue_stop),
      .speed_q8_i(cue_speed==127 ? 10'd512 : {cue_speed,2'b00}),
      .event_valid_o(cue_valid),.event_ready_i(cue_ready),.event_o(cue_event),
      .running_o(cue_running),.done_o(cue_done),.config_error_o(cue_error),
      .late_events_o(cue_late),.time_samples_o(cue_time));
  logic [17:0] fifo_event_data;
  wire [3:0] kind = event_data[17:14];
  wire [6:0] a = event_data[13:7];
  wire [6:0] b = event_data[6:0];
  logic [2:0] profile;
  assign profile_o=profile;
  wire signed [31:0] effect_left,effect_right;
  assign left_o=(route_o==2 || route_o==3)?32'sd0:effect_left;
  assign right_o=(route_o==1 || route_o==3)?32'sd0:effect_right;
  logic [1:0] requested_mode;
  logic mode_pending, mode_ready, mode_valid;
  wire [1:0] mode_cycle_base=mode_pending ? requested_mode : mode_o;
  logic [15:0] volume, expression_gain;
  logic [31:0] volume_product;
  logic [21:0] target_ratio;
  logic [21:0] bend_rom[0:255];
  logic [15:0] glide_step;
  logic [6:0] vibrato_depth, glide_cc;
  logic [7:0] bend_index;
  logic [5:0] snapshot_request;
  logic sustain, releasing;
  assign control_options_o={snapshot_request,bend_index,glide_cc,vibrato_depth,sustain,target_ratio!=22'd1048576,glide_step!=0,vibrato_depth!=0};
  logic [6:0] release_index;
  logic [127:0] held, deferred;
  assign held_notes_o=held;
  logic core_event_valid, core_event_ready, core_note_on;
  logic core_expression_valid, core_expression_ready;
  logic [6:0] core_note, core_velocity;
  logic [6:0] core_expression_note, core_expression_value;
  logic core_sample_ready, core_ce, load_busy, mix_busy;
  logic pending, frame_inflight;
  logic [31:0] allocated;
  wire [31:0] legacy_active_mask;
  wire [5:0] legacy_active_count;
  logic [7:0] issued;
  logic [31:0] held_pcm_l, held_pcm_r;
  logic fx_ready;
  logic scope_enable,scope_muted,scope_control_error;
  logic [2:0] scope_morph_shape;
  logic [6:0] scope_shape,scope_morph,scope_scale,scope_rotation;
  scope_tf_control tf_controls(
      .clk_i,.rst_ni,.event_valid_i(usb_lifecycle || (event_valid && event_ready && kind==2)),
      .cc_i(usb_lifecycle ? 7'd120 : a),.value_i(usb_lifecycle ? 7'd0 : b),.live_enable_i(scope_enable),
      .voices_idle_i(legacy_active_mask==0 && vec_active==0),.control_o(tf_scope_control_o));
  wire scope_enable_target=b==64 ? !scope_enable : b==127;
  logic [6:0] scope_cal_x,scope_cal_y,scope_offset_x,scope_offset_y;
  wire vec_ready,vec_event_ready,vec_valid,vec_busy,vec_config_error,vec_frequency_error,vec_clip,fx_clip;
  wire [7:0] vec_active;
  wire [3:0] vec_count;
  wire [31:0] vec_rejected;
  wire signed [31:0] vec_left,vec_right;
  logic synth_joined,vec_joined,held_vec_clip;
  assign clip_o=fx_clip || (sample_valid_o && held_vec_clip);
  logic [31:0] vec_previous_rejected;
  logic vec_previous_frequency_error;
  logic signed [31:0] held_synth,held_vec_l,held_vec_r;
  wire effects_valid=synth_joined && vec_joined;
  wire [15:0] scope_morph_q15=scope_morph==127 ? 16'd32768 : {1'b0,scope_morph,8'd0};
  wire [15:0] scope_scale_q15=scope_muted ? 16'd0 : scope_scale==127 ? 16'd32768 : {1'b0,scope_scale,8'd0};
  assign scope_status_o={vec_rejected[15:0],cue_running,cue_done,cue_error,|cue_late,(scope_control_error || tf_scope_control_o[15]),vec_frequency_error,vec_config_error,scope_enable,vec_active};

  logic panic_muted;
  logic dispatch, full;
  // Drain the arbiter's one registered event on a USB boundary. The local
  // register is cleared on that edge, so an already accepted old USB event
  // cannot emerge after reconnect. Keep the arbiter tied to its original
  // system reset; other source parsers retain their state.
  assign fifo_event_ready=usb_lifecycle || (register_room && !attach_initializing);
  // Register the FIFO output before MIDI routing and 32-way note matching.
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if(!rst_ni) begin event_valid<=0;event_data<=0;attach_initializing<=0;attach_step<=0;end
    else if(usb_lifecycle) begin
      event_valid<=0;event_data<=0;
      // A user PANIC during init restarts the defaults, but never starts a
      // fresh initialization during ordinary performance.
      attach_initializing<=(usb_attach && cpu_event_i[7]) ||
          (cpu_event_i[6:0]==7'd2 && attach_initializing);
      attach_step<=0;
    end else if(attach_initializing) begin
      if(register_room) begin
        event_valid<=attach_step<13;
        if(attach_step<13) begin event_data<=attach_event(attach_step);attach_step<=attach_step+1'b1;end
      end
      // FIFO acceptance alone is insufficient: wait for the actual C commit.
      if(attach_step==13 && !event_valid && !mode_pending && mode_o==2)
        attach_initializing<=0;
    end else if(fifo_event_ready) begin
      event_valid<=fifo_event_valid || (cue_valid && !cue_stop);
      if(fifo_event_valid) event_data<=fifo_event_data;
      else if(cue_valid && !cue_stop) event_data<=cue_event;
    end
  end
  initial $readmemh(`AUDIO_BEND_MEM_FILE,bend_rom);
  assign volume_product=volume*expression_gain;
  assign synth_gain_o=volume_product[30:15];
  assign mode_valid=mode_pending && mode_ready && !pending && !sample_ce_i && !usb_lifecycle;
  assign full = scope_enable ? &vec_active : &allocated;
  assign dispatch=!usb_lifecycle && !pending && !sample_ce_i && !load_busy && !mix_busy && !vec_busy && !mode_valid;
  wire panic_accept=usb_lifecycle || (event_valid && event_ready && kind==2 && a==120);
  assign core_ce=(pending || sample_ce_i) && core_sample_ready && vec_ready && fx_ready && !synth_joined && !vec_joined;
  always_comb begin
    core_event_valid=0; core_note_on=0; core_note=a; core_velocity=b;
    core_expression_valid=0; core_expression_note=a; core_expression_value=b;
    event_ready=0;
    if(releasing) begin
      core_note=release_index; core_velocity=0;
      core_event_valid=dispatch && deferred[release_index];
    end else if(event_valid) begin
      if(tf_scope_control_o[12] && (kind==0 || kind==1 || kind==5)) event_ready=dispatch;
      else if(kind==0 && sustain) event_ready=dispatch;
      else if(kind==0 || kind==1) begin
        core_note_on=kind==1;
        core_event_valid=dispatch && !(kind==1 && full);
        event_ready=dispatch && ((kind==1 && full) || (scope_enable ? vec_event_ready : core_event_ready));
      end else if(kind==5) begin
        core_expression_valid=dispatch && core_expression_ready;
        event_ready=dispatch && core_expression_ready;
      end else event_ready=dispatch;
    end
  end
  wire decoder_valid,decoder_ready;
  wire [17:0] decoder_data;
  wire pc_valid,pc_ready;
  wire [17:0] pc_data;
  midi_stream_decoder pc_decoder(.clk_i,.rst_ni,.byte_valid_i(pc_byte_valid_i),
      .byte_i(pc_byte_i),.event_valid_o(pc_valid),.event_ready_i(pc_ready),
      .event_o(pc_data),.overflow_count_o(pc_overflow_o));
  gw138k_three_event_arbiter u_events(.clk(clk_i),.reset_n(rst_ni),
      .g1_valid(decoder_valid),.g1_ready(decoder_ready),.g1_data(decoder_data),
      .pc_valid(pc_valid),.pc_ready(pc_ready),.pc_data(pc_data),
      .cpu_valid(cpu_event_valid_i && !usb_internal && !attach_initializing),.cpu_ready(arbiter_cpu_ready),.cpu_data(cpu_event_i),
      .event_valid(fifo_event_valid),.event_ready(fifo_event_ready),.event_data(fifo_event_data));
  midi_stream_decoder decoder(.clk_i,.rst_ni,.byte_valid_i(midi_byte_valid_i),
      .byte_i(midi_byte_i),.event_valid_o(decoder_valid),.event_ready_i(decoder_ready),
      .event_o(decoder_data),.overflow_count_o(midi_overflow_o));
  pitch_expression #(.SAMPLE_RATE_HZ(SAMPLE_RATE_HZ)) pitch(
      .clk_i,.rst_ni,.sample_ce_i(core_ce),.target_ratio_q20_i(target_ratio),
      .glide_step_q20_i(glide_step),.vibrato_depth_i(vibrato_depth),.ratio_q20_o(pitch_q20_o));
  unified_oscillator_engine #(.EXPRESSION_ENABLE(1),.SAMPLE_RATE_HZ(SAMPLE_RATE_HZ)) engine(
      .clk_i,.rst_ni,.mode_set_valid_i(mode_valid),.mode_set_ready_o(mode_ready),
      .mode_i(requested_mode),.current_mode_o(mode_o),
      .panic_i(panic_accept),
      .event_valid_i(core_event_valid && !scope_enable),.event_ready_o(core_event_ready),
      .event_note_on_i(core_note_on),.event_profile_i(profile),
      .event_midi_note_i(core_note),.event_velocity_i(core_velocity),
      .expression_valid_i(core_expression_valid && !scope_enable),.expression_ready_o(core_expression_ready),
      .expression_note_i(core_expression_note),.expression_value_i(core_expression_value),
      .pitch_ratio_q20_i(pitch_q20_o),.sample_ce_i(core_ce),
      .sample_ready_o(core_sample_ready),.sample_valid_o(synth_valid_o),.sample_o(synth_o),
      .allocated_mask_o(allocated),.active_mask_o(legacy_active_mask),.active_voice_count_o(legacy_active_count),
      .load_busy_o(load_busy),.mix_busy_o(mix_busy),.issued_slot_count_o(issued));
  scope_vec_engine vector_engine(
      .clk_i,.rst_ni,.panic_i(panic_accept),.sample_ce_i(core_ce),.sample_ready_o(vec_ready),
      .sample_valid_o(vec_valid),.left_o(vec_left),.right_o(vec_right),
      .event_valid_i(core_event_valid && scope_enable),.event_note_on_i(core_note_on),.event_ready_o(vec_event_ready),
      .event_note_i(core_note),.event_velocity_i(core_velocity),.event_profile_i(profile),
      .event_shape_i(scope_shape==127 ? core_note[2:0]-3'd4 : scope_shape[2:0]),
      .event_morph_shape_i(scope_morph_shape),.event_pitch_q20_i(22'd1048576),.pitch_q20_i(pitch_q20_o),
      .morph_q15_i(scope_morph_q15),.scale_q15_i(scope_scale_q15),.rotation_i(scope_rotation),
      .cal_x_q14_i(16'sd12288+$signed({7'd0,scope_cal_x,2'd0})*16'sd16),
      .cal_y_q14_i(16'sd12288+$signed({7'd0,scope_cal_y,2'd0})*16'sd16),
      .offset_x_i(($signed({25'd0,scope_offset_x})-32'sd64)<<<18),
      .offset_y_i(($signed({25'd0,scope_offset_y})-32'sd64)<<<18),
      .active_mask_o(vec_active),.active_count_o(vec_count),.rejected_events_o(vec_rejected),
      .config_error_o(vec_config_error),.frequency_error_o(vec_frequency_error),.clip_o(vec_clip),.busy_o(vec_busy));
  assign active_mask_o=scope_enable ? {24'd0,vec_active} : legacy_active_mask;
  assign active_voice_count_o=scope_enable ? {2'd0,vec_count} : legacy_active_count;
  // Join independently scheduled engines before the existing P10 input mixer.
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if(!rst_ni) begin synth_joined<=0;vec_joined<=0;held_synth<=0;held_vec_l<=0;held_vec_r<=0;held_vec_clip<=0;end
    else if(panic_accept) begin synth_joined<=0;vec_joined<=0;held_synth<=0;held_vec_l<=0;held_vec_r<=0;held_vec_clip<=0;end
    else begin
      if(synth_valid_o) begin synth_joined<=1;held_synth<=synth_o;end
      if(vec_valid) begin vec_joined<=1;held_vec_l<=vec_left;held_vec_r<=vec_right;held_vec_clip<=vec_clip;end
      if(effects_valid && fx_ready) begin synth_joined<=0;vec_joined<=0;end
    end
  end
  stereo_effects #(.VECTOR_ENABLE(1),.DELAY_BITS(DELAY_BITS),.ECHO_SAMPLES(ECHO_SAMPLES)) effects(
      .clk_i,.rst_ni,.clear_i(panic_accept),.valid_i(effects_valid),.synth_i(panic_muted?32'sd0:held_synth),
      .vector_left_i(panic_muted?32'sd0:held_vec_l),.vector_right_i(panic_muted?32'sd0:held_vec_r),
      .pcm_left_i($signed(held_pcm_l)),.pcm_right_i($signed(held_pcm_r)),
      .synth_gain_i(synth_gain_o),.pcm_gain_i(pcm_gain_o),.effect_mask_i(effect_mask_o),.effect_order_i(effect_order_o),
      .ready_o(fx_ready),.valid_o(sample_valid_o),.left_o(effect_left),.right_o(effect_right),.clip_o(fx_clip),
      .mem_clk_i(delay_mem_clk_i),.mem_rst_ni(delay_mem_rst_ni),
      .dwr_valid_o(delay_dwr_valid_o),.dwr_data_o(delay_dwr_data_o),.dwr_pop_i(delay_dwr_pop_i),
      .drd_push_i(delay_drd_push_i),.drd_data_i(delay_drd_data_i),.drd_ready_o(delay_drd_ready_o));
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if(!rst_ni) begin
      applied_events_o<=0;pending<=0; frame_inflight<=0; deadline_miss_o<=0; note_drop_o<=0;
      held_pcm_l<=0; held_pcm_r<=0; profile<=0; requested_mode<=2;
      mode_pending<=0; volume<=32768; expression_gain<=32768; pcm_gain_o<=0;
      route_o<=0; target_ratio<=1048576; glide_step<=0; vibrato_depth<=0;
      effect_selected<=0;effect_master<=1;effect_order_o<=6'b10_01_00;effect_count<=0;
      glide_cc<=0; bend_index<=128; snapshot_request<=0;
      sustain<=0; held<=0; deferred<=0; releasing<=0; release_index<=0;
      panic_epoch_o<=0;panic_muted<=0;
      panel_event_valid_o<=0;panel_command_o<=0;
      cue_speed<=64;scope_enable<=0;scope_muted<=0;scope_control_error<=0;scope_morph_shape<=0;
      scope_shape<=127;scope_morph<=0;scope_scale<=127;scope_rotation<=0;
      scope_cal_x<=64;scope_cal_y<=64;scope_offset_x<=64;scope_offset_y<=64;
      vec_previous_rejected<=0;vec_previous_frequency_error<=0;
    end else begin
      panel_event_valid_o<=0;
      vec_previous_rejected<=vec_rejected;vec_previous_frequency_error<=vec_frequency_error;
      if(vec_rejected!=vec_previous_rejected || (vec_frequency_error && !vec_previous_frequency_error))
        note_drop_o<=note_drop_o+(vec_rejected-vec_previous_rejected)+(vec_frequency_error && !vec_previous_frequency_error);
      // PANIC intentionally cancels the joined/effect frame. Its discarded
      // valid must not leave frame_inflight set and falsely report a deadline
      // miss at the next 48-kHz tick (real USB events can arrive in this gap).
      if(panic_accept) begin pending<=0;frame_inflight<=0;end
      else begin
        if(sample_valid_o) frame_inflight<=0;
        if(sample_ce_i) begin
          pending<=1;
          if(frame_inflight || pending) deadline_miss_o<=deadline_miss_o+1;
          frame_inflight<=1;
        end
        if(core_ce) begin pending<=0; held_pcm_l<=pcm_left_i; held_pcm_r<=pcm_right_i; end
        if(effects_valid && !fx_ready) deadline_miss_o<=deadline_miss_o+1;
      end
      if(mode_valid) mode_pending<=0;
      if(releasing && dispatch && (!deferred[release_index] || (scope_enable ? vec_event_ready : core_event_ready))) begin
        deferred[release_index]<=0;
        if(release_index==127) releasing<=0;
        else release_index<=release_index+1'b1;
      end
      if(usb_lifecycle) begin
        held<=0;deferred<=0;sustain<=0;releasing<=0;release_index<=0;
        mode_pending<=0;panic_epoch_o<=panic_epoch_o+1'b1;panic_muted<=1;
      end
      if(event_valid && event_ready) begin
        applied_events_o<=applied_events_o+1'b1;
        case(kind)
          0: begin held[a]<=0; if(sustain) deferred[a]<=1; end
          1: if(tf_scope_control_o[12] || full) note_drop_o<=note_drop_o+1; else if(scope_enable && a>95) begin end else begin held[a]<=1; deferred[a]<=0; panic_muted<=0; end
          2: case(a)
            1: vibrato_depth<=b;
            5: begin glide_cc<=b;glide_step<=b==0 ? 16'd0 : 16'd256-({9'd0,b}<<1);end
            7: volume<=b==127 ? 16'd32768 : {b,8'd0};
            11: expression_gain<=b==127 ? 16'd32768 : {b,8'd0};
            16: pcm_gain_o<=b==127 ? 16'd32768 : {b,8'd0};
            64: begin
              sustain<=b>=64;
              if(b<64 && sustain) begin releasing<=1; release_index<=0; end
            end
            80: if(b<3) begin requested_mode<=b[1:0]; mode_pending<=1; end
            81: begin effect_selected<=b[2:0];effect_master<=1;effect_count<=0;effect_order_o<=6'b10_01_00;end
            84: if(b<3) effect_order_o[1:0]<=b[1:0];
            85: if(b<3) effect_order_o[3:2]<=b[1:0];
            86: if(b<3) effect_order_o[5:4]<=b[1:0];
            // A queue contains each effect at most once. After three distinct
            // selections the next press clears the queue and all effect enables.
            // A later press starts again; duplicates before full do nothing.
            87: if(b<3) begin
              if(effect_count==3) begin
                effect_order_o<=6'b11_11_11;effect_selected<=3'b000;effect_count<=0;
              end else if(effect_count==0) begin
                effect_order_o<={4'b1111,b[1:0]};effect_selected<=3'b001<<b[1:0];effect_count<=1;effect_master<=1;
              end else if(effect_order_o[1:0]!=b[1:0] &&
                          (effect_count!=2 || effect_order_o[3:2]!=b[1:0])) begin
                if(effect_count==1) begin
                  effect_order_o[3:2]<=b[1:0]; effect_count<=2;
                end else begin
                  effect_order_o[5:4]<=b[1:0]; effect_count<=3;
                end
                effect_selected<=effect_selected | (3'b001<<b[1:0]);effect_master<=1;
              end
            end
            88: effect_master<=~effect_master;
            89: if(b<2) begin
              if(b[0]) requested_mode<=mode_cycle_base==2 ? 0 : mode_cycle_base+1'b1;
              else requested_mode<=mode_cycle_base==0 ? 2 : mode_cycle_base-1'b1;
              mode_pending<=1;
            end
            90: begin
              if((b==0 || b==64 || b==127) && (scope_enable_target==scope_enable || (legacy_active_mask==0 && vec_active==0))) begin
                scope_enable<=scope_enable_target;scope_muted<=0;
                if(scope_enable_target) begin effect_selected<=0;effect_master<=1;end
              end else begin scope_control_error<=1;note_drop_o<=note_drop_o+1'b1;end
            end
            104: if((b==64 || b==127) &&
                    (tf_scope_control_o[12] || (legacy_active_mask==0 && vec_active==0))) begin
              scope_enable<=0;scope_muted<=0;effect_selected<=0;effect_master<=1;
            end
            91: if(b<8) scope_morph_shape<=b[2:0];else begin scope_control_error<=1;note_drop_o<=note_drop_o+1'b1;end
            92: scope_morph<=b;
            93: scope_scale<=b;
            94: scope_rotation<=b;
            95: if(b==0 || b==64 || b==127) scope_muted<=b==64 ? ~scope_muted : b==127;else begin scope_control_error<=1;note_drop_o<=note_drop_o+1'b1;end
            96: if((b!=0 && b!=127) || (b==127 && (tf_scope_control_o[12] || cue_running || (!scope_enable && legacy_active_mask!=0)))) begin scope_control_error<=1;note_drop_o<=note_drop_o+1'b1;end
            103: if(b!=0) cue_speed<=b;else begin scope_control_error<=1;note_drop_o<=note_drop_o+1'b1;end
            97: if(b<8 || b==127) scope_shape<=b;else begin scope_control_error<=1;note_drop_o<=note_drop_o+1'b1;end
            98: scope_cal_x<=b;
            99: scope_offset_x<=b;
            100: scope_cal_y<=b;
            101: scope_offset_y<=b;
            82: if(b<4) route_o<=b[1:0];
            83: if(b==127) snapshot_request<=snapshot_request+1'b1;
            120: begin
              held<=0; deferred<=0; sustain<=0; releasing<=0; release_index<=0;
              panic_epoch_o<=panic_epoch_o+1'b1; panic_muted<=1;
            end
            123: begin
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
          4: begin target_ratio<=bend_rom[{b,a[6]}];bend_index<={b,a[6]};end
          6: begin panel_event_valid_o<=1;panel_command_o<=a;end
          default: begin end
        endcase
      end
    end
  end
endmodule
