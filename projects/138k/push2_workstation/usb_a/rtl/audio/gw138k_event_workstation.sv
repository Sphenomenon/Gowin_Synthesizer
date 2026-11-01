`timescale 1ns/1ps
`ifndef AUDIO_BEND_MEM_FILE
`define AUDIO_BEND_MEM_FILE "sim/data/audio_chain/pitch_bend_q20.mem"
`endif
// Portable, CPU-free MIDI -> synthesis -> stereo PCM/effects boundary.
module gw138k_event_workstation #(
    parameter integer SAMPLE_RATE_HZ=48000,
    parameter bit TIMING_OPTIMIZED=0,
    parameter bit EXTERNAL_MASTER_VOLUME=0,
    parameter bit REQUEST_DRIVEN_RENDER=0,
    parameter bit RUNTIME_RATE_ENABLE=0,
    parameter bit RUNTIME_EFFECTS_ENABLE=0,
    parameter bit EVENT_CONFIG_COFACTOR_ENABLE=0,
    parameter bit SYNTH_ENGINES_ENABLE=1,
    parameter bit D_ONLY_ENABLE=0,
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
    // This is the exact cancellation edge that advances the sole epoch owner.
    // Internal request services may cache epoch equality without a second counter.
    output wire panic_accept_o,
    output wire panic_muted_o,
    output wire cancel_delivery_pending_o,
    // Read-only render admission status; PANIC clears frame_inflight before
    // the legacy oscillator's unreset ROM/valid pipelines have drained.
    output wire render_idle_o,
    // Complete runtime rate changes are an explicit opt-in transaction.
    // The public rate commits only after engines and all effects acknowledge.
    input logic rate_commit_i, rate_44100_i,
    // Internal request-service cofactor, selected explicitly below. When
    // sample_ce_i is zero this must equal rate_commit_i; it omits only a
    // configuration request caused by accepting this cycle's new sample.
    input logic event_rate_commit_i,
    output wire rate_ready_o, applied_rate_44100_o,
    output wire rate_applied_o,rate_busy_o,rate_fault_o,
    input logic history_clear_i,
    output wire history_ready_o,history_done_o,
    input logic delay_peer_heartbeat_i,delay_dma_fault_i,
    output wire delay_heartbeat_o,
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
    output wire [15:0] master_volume_o,
    output logic [1:0] route_o,
    output wire [2:0] profile_o,
    output wire [2:0] effect_mask_o,
    output logic [5:0] effect_order_o,
    output wire [31:0] effect_state_o,
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
    if(RUNTIME_EFFECTS_ENABLE && !RUNTIME_RATE_ENABLE)
      $fatal(1,"runtime effects require runtime engines");
    if(EVENT_CONFIG_COFACTOR_ENABLE && (!RUNTIME_EFFECTS_ENABLE || !REQUEST_DRIVEN_RENDER))
      $fatal(1,"event configuration cofactor requires native request-driven effects");
    if(D_ONLY_ENABLE && (SYNTH_ENGINES_ENABLE || !RUNTIME_EFFECTS_ENABLE))
      $fatal(1,"D-only requires native effects and no instrument engines");
  end
  logic [1:0] effect_count;
  logic [2:0] effect_selected;
  logic effect_master;
  logic event_valid, event_ready;
  logic [17:0] event_data;
  logic fifo_event_valid,fifo_event_ready;
  logic core_ce; // Declare before cue_player: Gowin otherwise creates an implicit net.
  wire native_clear,engine_clear;
  wire cue_valid,cue_ready,cue_running,cue_done,cue_error;
  wire [17:0] cue_event;
  wire [31:0] cue_late,cue_time;
  wire [6:0] cue_speed;
  wire usb_internal,usb_lifecycle,attach_initializing;
  wire [3:0] attach_step;
  wire arbiter_cpu_ready;
  wire cue_start=event_valid && event_ready && kind==2 && a==96 && b==127 && !tf_scope_control_o[12] && (scope_enable || legacy_active_mask==0);
  wire cue_stop=usb_lifecycle || (event_valid && event_ready && kind==2 && ((a==96 && b==0) || a==120 || a==123));
  generate if(SYNTH_ENGINES_ENABLE)begin: instrument_cue
  scope_control_player cue_player(
      .clk_i,.rst_ni,.sample_ce_i(core_ce),.start_i(cue_start),.stop_i(cue_stop),
      .speed_q8_i(cue_speed==127 ? 10'd512 : {cue_speed,2'b00}),
      .event_valid_o(cue_valid),.event_ready_i(cue_ready),.event_o(cue_event),
      .running_o(cue_running),.done_o(cue_done),.config_error_o(cue_error),
      .late_events_o(cue_late),.time_samples_o(cue_time));
  end else begin: no_instrument_cue
    assign cue_valid=0;assign cue_event=0;assign cue_running=0;assign cue_done=0;
    assign cue_error=0;assign cue_late=0;assign cue_time=0;
  end endgenerate
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
  logic [15:0] volume, expression_gain;
  assign master_volume_o=volume;
  logic [21:0] target_ratio;
  logic [15:0] glide_step;
  logic [6:0] vibrato_depth, glide_cc;
  logic [7:0] bend_index;
  logic sustain, releasing;
  logic [6:0] release_index;
  logic deferred_current;
  wire [6:0] next_release_index=release_index+7'd1;
  // Only this cursor is modified during a release sweep. Pre-read its next
  // held bit while the current event executes; retain every original cycle.
  logic [127:0] held, deferred;
  assign held_notes_o=held;
  logic core_event_valid, core_event_ready, core_note_on;
  logic core_expression_valid, core_expression_ready;
  logic [6:0] core_note, core_velocity;
  logic [6:0] core_expression_note, core_expression_value;
  logic core_sample_ready, load_busy, mix_busy;
  wire runtime_quiescent, runtime_rate_ready,engine_rate;
  wire runtime_config_block,runtime_config_busy,runtime_fault;
  (* syn_keep=1 *) logic event_config_block;
  wire engine_rate_commit;
  wire fx_config_ready,fx_config_applied,fx_history_ready,fx_history_done,fx_quiet,fx_fault,fx_rate;
  logic pending, frame_inflight;
  logic [31:0] allocated;
  wire [31:0] legacy_active_mask;
  wire [5:0] legacy_active_count;
  logic [7:0] issued;
  logic [31:0] held_pcm_l, held_pcm_r;
  logic fx_ready;
  wire fx_sample_slot_ready;
  logic scope_enable,scope_muted,scope_control_error;
  logic [2:0] scope_morph_shape;
  logic [6:0] scope_shape,scope_morph,scope_scale,scope_rotation;
  logic [6:0] scope_cal_x,scope_cal_y,scope_offset_x,scope_offset_y;
  wire vec_ready,vec_event_ready,vec_valid,vec_busy,vec_config_error,vec_frequency_error,vec_clip,fx_clip;
  // Runtime vector event_ready adds only !core_ce to its stored ready state.
  // Dispatch already implies !core_ce: it excludes sample_ce_i and requires
  // !pending || runtime_config_busy, while core_ce needs a pending/new sample
  // and !runtime_config_busy. Use that same-cycle exclusion at this boundary
  // so event acceptance does not feed through the render/configuration cone.
  wire vec_dispatch_ready=RUNTIME_RATE_ENABLE ? vec_ready : vec_event_ready;
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
  assign panic_muted_o=panic_muted;
  logic dispatch, full;
  wire control_rejected;
  wire parameter_commit=event_valid && (TIMING_OPTIMIZED ? (dispatch && !releasing) : event_ready);
  workstation_session #(.D_ONLY_ENABLE(D_ONLY_ENABLE)) session (
      .clk_i(clk_i),
      .rst_ni(rst_ni),
      .cpu_valid_i(cpu_event_valid_i),
      .cpu_event_i(cpu_event_i),
      .arbiter_ready_i(arbiter_cpu_ready),
      .cpu_ready_o(cpu_event_ready_o),
      .internal_o(usb_internal),
      .lifecycle_o(usb_lifecycle),
      .fifo_valid_i(fifo_event_valid),
      .fifo_event_i(fifo_event_data),
      .fifo_ready_o(fifo_event_ready),
      .cue_valid_i(cue_valid),
      .cue_stop_i(cue_stop),
      .cue_event_i(cue_event),
      .cue_ready_o(cue_ready),
      .event_ready_i(event_ready),
      .event_valid_o(event_valid),
      .event_o(event_data),
      .mode_pending_i(mode_pending),
      .mode_i(mode_o),
      .initializing_o(attach_initializing),
      .initialization_step_o(attach_step)
  );
  wire [6:0] d_crush,d_drive,d_delay_send;
  workstation_parameters #(.D_ONLY_ENABLE(D_ONLY_ENABLE)) parameters (
      .clk_i(clk_i),
      .rst_ni(rst_ni),
      .commit_i(parameter_commit),
      .lifecycle_i(usb_lifecycle),
      .mode_applied_i(mode_valid),
      .kind_i(kind),
      .address_i(a),
      .value_i(b),
      .mode_i(mode_o),
      .legacy_active_i(legacy_active_mask),
      .vector_active_i(vec_active),
      .cue_running_i(cue_running),
      .requested_mode_o(requested_mode),
      .mode_pending_o(mode_pending),
      .volume_o(volume),
      .expression_gain_o(expression_gain),
      .pcm_gain_o(pcm_gain_o),
      .synth_gain_o(synth_gain_o),
      .route_o(route_o),
      .profile_o(profile),
      .effect_selected_o(effect_selected),
      .effect_master_o(effect_master),.effect_state_o(effect_state_o),
      .effect_count_o(effect_count),
      .effect_mask_o(effect_mask_o),
      .effect_order_o(effect_order_o),
      .target_ratio_o(target_ratio),
      .glide_step_o(glide_step),
      .vibrato_depth_o(vibrato_depth),
      .glide_cc_o(glide_cc),
      .bend_index_o(bend_index),
      .sustain_o(sustain),
      .options_o(control_options_o),
      .tf_control_o(tf_scope_control_o),
      .panel_event_valid_o(panel_event_valid_o),
      .panel_command_o(panel_command_o),
      .scope_enable_o(scope_enable),
      .scope_muted_o(scope_muted),
      .scope_error_o(scope_control_error),
      .scope_morph_shape_o(scope_morph_shape),
      .scope_shape_o(scope_shape),
      .scope_morph_o(scope_morph),
      .scope_scale_o(scope_scale),
      .scope_rotation_o(scope_rotation),
      .scope_cal_x_o(scope_cal_x),
      .scope_cal_y_o(scope_cal_y),
      .scope_offset_x_o(scope_offset_x),
      .scope_offset_y_o(scope_offset_y),
      .cue_speed_o(cue_speed),
      .d_crush_o(d_crush),.d_drive_o(d_drive),.d_delay_send_o(d_delay_send),
      .rejected_o(control_rejected)
  );
  // A known sample edge excludes both event and mode admission. At zero,
  // the service cofactor equals the complete rate request; at one its value
  // is unobservable here. Unknown sample controls retain the original full
  // fence and four-state behavior. Core rendering and the real broadcast
  // continue to consume runtime_config_block, never this event-only fence.
  generate if(EVENT_CONFIG_COFACTOR_ENABLE)begin: sample_event_config_fence
    always_comb begin
      case(sample_ce_i)
        1'b0,1'b1: event_config_block=!runtime_config_busy &&
            (event_rate_commit_i || history_clear_i);
        default: event_config_block=runtime_config_block;
      endcase
    end
  end else begin: full_event_config_fence
    assign event_config_block=runtime_config_block;
  end endgenerate
  assign mode_valid=mode_pending && mode_ready && !pending && !sample_ce_i && !usb_lifecycle && !event_config_block && !native_clear;
  assign full = scope_enable ? &vec_active : &allocated;
  assign dispatch=!usb_lifecycle && (!pending || runtime_config_busy) && !sample_ce_i && !event_config_block && !native_clear && !load_busy && !mix_busy && !vec_busy && !(TIMING_OPTIMIZED ? (mode_pending && allocated==0) : mode_valid);
  // CC120 uses the control-event dispatch condition directly. It never needs
  // engine event_ready; keeping that dependency out of cancellation also
  // avoids a PANIC/configuration/sample-ready combinational cycle.
  wire panic_accept=usb_lifecycle ||
      (event_valid && !releasing && dispatch && kind==2 && a==120);
  assign panic_accept_o=panic_accept;
  // Epoch/held-note/frame cancellation still commits on panic_accept. The
  // large native engine/effect clear tree starts from a local register one
  // cycle later, rather than from config/event admission's combinational
  // cone. Reserve that edge: queued events, modes and samples wait and cannot
  // be accepted then erased by the delayed clear. No serial clock is gated.
  generate if(RUNTIME_EFFECTS_ENABLE)begin: native_cancel_delivery
    logic pending_clear;
    always_ff @(posedge clk_i or negedge rst_ni)
      if(!rst_ni)pending_clear<=0;else pending_clear<=panic_accept;
    assign native_clear=pending_clear;
  end else begin: immediate_cancel_delivery
    assign native_clear=1'b0;
  end endgenerate
  assign engine_clear=RUNTIME_EFFECTS_ENABLE ? native_clear:panic_accept;
  assign cancel_delivery_pending_o=native_clear;
  // Legacy partial loading can start on the cancellation edge: 32 issues,
  // three generator-valid stages, one timbre-ROM stage, plus edge margin.
  // The render tail is shorter: five sine, three mix, six quantizer stages.
  // This fence is cancellation-only and does not change existing scheduling.
  // A native oscillator with an actual pipeline-empty output can replace it.
  localparam integer LEGACY_CANCEL_TAIL_CYCLES=40;
  logic [5:0] legacy_cancel_tail;
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if(!rst_ni) legacy_cancel_tail<=0;
    else if(panic_accept) legacy_cancel_tail<=6'(LEGACY_CANCEL_TAIL_CYCLES);
    else if(legacy_cancel_tail!=0) legacy_cancel_tail<=legacy_cancel_tail-1'b1;
  end
  // Use stored datapath state, not core_sample_ready/panic_accept: those
  // depend on this cycle's sample_ce through event dispatch. Feeding them
  // back to an external request-ready gate would create a combinational loop.
  // Normal envelope/quantizer tails remain covered by frame_inflight through
  // the joined effects completion; cancellation uses the explicit tail fence.
  assign render_idle_o=rst_ni && (RUNTIME_RATE_ENABLE ? runtime_quiescent : legacy_cancel_tail==0) &&
      !native_clear && !pending && !frame_inflight && !synth_joined && !vec_joined &&
      // Runtime readiness also vetoes this cycle's configuration accept.
      // Idle observes stored work/history instead, so a held config request
      // cannot feed through effect admission and back to its drain fence.
      !load_busy && !mix_busy && vec_ready && (RUNTIME_EFFECTS_ENABLE ? fx_quiet : fx_ready) &&
      !synth_valid_o && !vec_valid && !sample_valid_o && !runtime_config_busy && !runtime_fault;
  // The outer runtime fences below already exclude effect fault/clear and
  // both configuration request inputs. Use stored effect-slot state here so
  // core_ce does not re-enter the complete configuration admission cone.
  // All other effect consumers retain the full fx_ready handshake.
  // Native request-driven rendering and dispatch reserve disjoint edges.
  // For known render-eligible controls, dispatch and mode_valid are zero;
  // runtime_quiescent already contains the oscillator's stored ready state.
  // Keep current event/config acceptance out of this same-cycle sample CE.
  // Unknown controls retain the complete original four-state expression.
  generate if(REQUEST_DRIVEN_RENDER && RUNTIME_RATE_ENABLE && RUNTIME_EFFECTS_ENABLE)begin: native_sample_admission
    always_comb begin
      case({pending,sample_ce_i,runtime_config_busy})
        3'b100,3'b010,3'b110: core_ce=vec_ready && fx_sample_slot_ready &&
              !synth_joined && !vec_joined && !usb_lifecycle && !native_clear &&
              !runtime_config_block && !runtime_fault && runtime_quiescent;
        3'b000,3'b001,3'b011,3'b101,3'b111: core_ce=1'b0;
        default: core_ce=(pending || sample_ce_i) && core_sample_ready && vec_ready &&
      (RUNTIME_EFFECTS_ENABLE ? fx_sample_slot_ready : fx_ready) &&
      !synth_joined && !vec_joined && !panic_accept && !native_clear && !runtime_config_block && !runtime_config_busy && !runtime_fault &&
      (!REQUEST_DRIVEN_RENDER || (RUNTIME_RATE_ENABLE ? runtime_quiescent : legacy_cancel_tail==0));
      endcase
    end
  end else begin: original_sample_admission
    assign core_ce=(pending || sample_ce_i) && core_sample_ready && vec_ready &&
      (RUNTIME_EFFECTS_ENABLE ? fx_sample_slot_ready : fx_ready) &&
      !synth_joined && !vec_joined && !panic_accept && !native_clear && !runtime_config_block && !runtime_config_busy && !runtime_fault &&
      (!REQUEST_DRIVEN_RENDER || (RUNTIME_RATE_ENABLE ? runtime_quiescent : legacy_cancel_tail==0));
  end endgenerate
  generate if(RUNTIME_EFFECTS_ENABLE) begin: runtime_configuration
    logic busy,is_config,pending_rate,committed_rate,failed;
    logic applied,history_done;
    // Pending is a registered, not-yet-started sample. It may keep its identity
    // while configuration drains, but no started frame may be reconfigured.
    wire pipeline_quiet=runtime_quiescent && fx_quiet && !load_busy && !mix_busy &&
        vec_ready && !synth_joined && !vec_joined && !synth_valid_o && !vec_valid &&
        !sample_valid_o && !native_clear && (!frame_inflight || pending);
    // A real broadcast already blocks dispatch through runtime_config_block.
    // Use that cofactor here, keeping queued event qualification out of the
    // engine/effect broadcast. Unknown request/busy values retain the public
    // ready expression and its original four-state behavior.
    logic config_accept;
    always_comb begin
      case ({rate_commit_i,busy})
        2'b00,2'b01,2'b11: config_accept=1'b0;
        2'b10: config_accept=rst_ni && !runtime_fault && pipeline_quiet &&
            !usb_lifecycle && fx_config_ready;
        default: config_accept=rate_commit_i && rate_ready_o;
      endcase
    end
    wire history_accept=history_clear_i && history_ready_o;
    assign runtime_config_busy=busy;
    assign runtime_fault=failed || fx_fault;
    // Block event admission on the broadcast edge so engine rate_ready is
    // independent of a queued NoteOn. During the fenced wait, ordinary event
    // dispatch resumes, including NoteOff/PANIC and existing loader pressure.
    assign runtime_config_block=!busy && (rate_commit_i || history_clear_i);
    logic public_rate_ready;
    assign rate_ready_o=public_rate_ready;
    // A held event-fenced rate request excludes dispatch/mode admission.
    // Keep the original ready expression for every other/unknown control.
    always_comb begin
      case ({rate_commit_i,busy,event_rate_commit_i})
        3'b101: public_rate_ready=rst_ni && !runtime_fault && pipeline_quiet &&
            !usb_lifecycle && fx_config_ready;
        default: public_rate_ready=rst_ni && !busy && !runtime_fault && pipeline_quiet &&
            !panic_accept && !core_event_valid && !core_expression_valid && !mode_valid && fx_config_ready;
      endcase
    end
    assign history_ready_o=rst_ni && !busy && !runtime_fault && pipeline_quiet &&
        fx_history_ready && !rate_commit_i;
    assign engine_rate_commit=config_accept;
    assign applied_rate_44100_o=committed_rate;
    assign rate_applied_o=applied;
    assign rate_busy_o=busy;
    assign rate_fault_o=runtime_fault;
    assign history_done_o=history_done && !runtime_fault;
    always_ff @(posedge clk_i or negedge rst_ni)begin
      if(!rst_ni)begin busy<=0;is_config<=0;pending_rate<=0;committed_rate<=0;failed<=0;applied<=0;history_done<=0;end
      else begin
        applied<=0;history_done<=0;
        if(!busy && fx_history_done && !config_accept && !history_accept && !runtime_fault)history_done<=1;
        if(fx_fault)failed<=1;
        if(config_accept || history_accept)begin
          busy<=1;is_config<=config_accept;
          pending_rate<=config_accept ? rate_44100_i : committed_rate;
        end else if(busy && fx_history_done && !runtime_fault)begin
          if(engine_rate==pending_rate && fx_rate==pending_rate && (!is_config || fx_config_applied))begin
            busy<=0;committed_rate<=pending_rate;applied<=is_config;history_done<=1;
          end else failed<=1;
        end
      end
    end
  end else begin: fixed_configuration
    assign runtime_config_busy=1'b0;
    assign runtime_config_block=1'b0;
    assign runtime_fault=1'b0;
    assign rate_ready_o=RUNTIME_RATE_ENABLE && !rate_44100_i &&
        runtime_rate_ready && render_idle_o && !sample_ce_i;
    assign engine_rate_commit=rate_commit_i && rate_ready_o;
    assign applied_rate_44100_o=engine_rate;
    assign rate_applied_o=1'b0;
    assign rate_busy_o=1'b0;
    assign rate_fault_o=1'b0;
    assign history_ready_o=1'b0;
    assign history_done_o=1'b0;
  end endgenerate
  always_comb begin
    core_event_valid=0; core_note_on=0; core_note=a; core_velocity=b;
    core_expression_valid=0; core_expression_note=a; core_expression_value=b;
    event_ready=0;
    if(releasing) begin
      core_note=release_index; core_velocity=0;
      core_event_valid=dispatch && deferred_current;
    end else if(event_valid) begin
      if(tf_scope_control_o[12] && (kind==0 || kind==1 || kind==5)) event_ready=dispatch;
      else if(kind==0 && sustain) event_ready=dispatch;
      else if(kind==0 || kind==1) begin
        core_note_on=kind==1;
        core_event_valid=dispatch && !(kind==1 && full);
        // Runtime arithmetic carries work beyond the legacy busy signals.
        // A public NoteOn/Off is accepted only with the owning engine's
        // handshake, so held state cannot advance while its event is rejected.
        event_ready=dispatch && ((TIMING_OPTIMIZED && !RUNTIME_RATE_ENABLE) ||
            (kind==1 && full) || (scope_enable ? vec_dispatch_ready : core_event_ready));
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
  generate if(!SYNTH_ENGINES_ENABLE)begin: external_media_only
    // The real PCM source still traverses the complete effects and final
    // serializer. This empty engine handshake owns no voice or sample RAM.
    logic rendered,applied_rate;
    always_ff @(posedge clk_i or negedge rst_ni)begin
      if(!rst_ni)begin rendered<=0;applied_rate<=0;end
      else begin rendered<=core_ce && !panic_accept;
        if(engine_rate_commit)applied_rate<=rate_44100_i;
      end
    end
    assign runtime_quiescent=!rendered;assign runtime_rate_ready=!rendered;assign engine_rate=applied_rate;
    assign core_sample_ready=1;assign core_event_ready=1;assign core_expression_ready=1;
    assign vec_event_ready=1;assign vec_ready=1;assign vec_busy=0;
    assign synth_valid_o=rendered;assign synth_o=0;assign vec_valid=rendered;
    assign vec_left=0;assign vec_right=0;assign vec_active=0;assign vec_count=0;assign vec_rejected=0;
    assign vec_config_error=0;assign vec_frequency_error=0;assign vec_clip=0;
    assign allocated=0;assign legacy_active_mask=0;assign legacy_active_count=0;
    assign load_busy=0;assign mix_busy=0;assign issued=0;assign pitch_q20_o=22'd1048576;
    assign mode_ready=1;assign mode_o=D_ONLY_ENABLE ? 2'd3 : 2'd2;
  end else if(RUNTIME_RATE_ENABLE) begin: runtime_engines
    workstation_runtime_render_engines #(.RUNTIME_RATE_ENABLE(1)) engines(
      .clk_i,.rst_ni,.panic_i(engine_clear),.sample_ce_i(core_ce),
      .rate_commit_i(engine_rate_commit),.rate_44100_i,
      .rate_ready_o(runtime_rate_ready),.applied_rate_44100_o(engine_rate),
      .quiescent_o(runtime_quiescent),
      .target_ratio_q20_i(target_ratio),.glide_step_q20_i(glide_step),
      .vibrato_depth_i(vibrato_depth),.pitch_q20_o,
      .mode_set_valid_i(mode_valid),.mode_set_ready_o(mode_ready),
      .mode_i(requested_mode),.current_mode_o(mode_o),
      .event_valid_i(core_event_valid),.event_note_on_i(core_note_on),
      .scope_enable_i(scope_enable),.event_profile_i(profile),
      .event_note_i(a),.event_off_note_i(core_note),.event_velocity_i(core_velocity),
      .synth_event_ready_o(core_event_ready),.vector_event_ready_o(vec_event_ready),
      .expression_valid_i(core_expression_valid),.expression_ready_o(core_expression_ready),
      .expression_note_i(core_expression_note),.expression_value_i(core_expression_value),
      .synth_sample_ready_o(core_sample_ready),.synth_valid_o,.synth_o,
      .allocated_mask_o(allocated),.synth_active_mask_o(legacy_active_mask),
      .synth_active_count_o(legacy_active_count),.load_busy_o(load_busy),.mix_busy_o(mix_busy),
      .issued_slot_count_o(issued),
      .vector_shape_i(scope_shape==127 ? a[2:0]-3'd4 : scope_shape[2:0]),
      .vector_morph_shape_i(scope_morph_shape),.vector_morph_q15_i(scope_morph_q15),
      .vector_scale_q15_i(scope_scale_q15),.vector_rotation_i(scope_rotation),
      .vector_cal_x_q14_i(16'sd12288+$signed({7'd0,scope_cal_x,2'd0})*16'sd16),
      .vector_cal_y_q14_i(16'sd12288+$signed({7'd0,scope_cal_y,2'd0})*16'sd16),
      .vector_offset_x_i(($signed({25'd0,scope_offset_x})-32'sd64)<<<18),
      .vector_offset_y_i(($signed({25'd0,scope_offset_y})-32'sd64)<<<18),
      .vector_sample_ready_o(vec_ready),.vector_valid_o(vec_valid),.vector_busy_o(vec_busy),
      .vector_left_o(vec_left),.vector_right_o(vec_right),
      .vector_active_mask_o(vec_active),.vector_active_count_o(vec_count),
      .vector_rejected_o(vec_rejected),.vector_config_error_o(vec_config_error),
      .vector_frequency_error_o(vec_frequency_error),.vector_clip_o(vec_clip));
  end else begin: legacy_engines
    assign runtime_quiescent=1'b0;
    assign runtime_rate_ready=1'b0;
    assign engine_rate=1'b0;
  pitch_expression #(.SAMPLE_RATE_HZ(SAMPLE_RATE_HZ)) pitch(
      .clk_i,.rst_ni,.sample_ce_i(core_ce),.target_ratio_q20_i(target_ratio),
      .glide_step_q20_i(glide_step),.vibrato_depth_i(vibrato_depth),.ratio_q20_o(pitch_q20_o));
  unified_oscillator_engine #(.EXPRESSION_ENABLE(1),.SAMPLE_RATE_HZ(SAMPLE_RATE_HZ),.SEPARATE_OFF_NOTE(1)) engine(
      .clk_i,.rst_ni,.mode_set_valid_i(mode_valid),.mode_set_ready_o(mode_ready),
      .mode_i(requested_mode),.current_mode_o(mode_o),
      .panic_i(panic_accept),
      .event_valid_i(core_event_valid && !scope_enable),.event_ready_o(core_event_ready),
      .event_note_on_i(core_note_on),.event_profile_i(profile),
      .event_midi_note_i(a),.event_off_note_i(core_note),.event_velocity_i(core_velocity),
      .expression_valid_i(core_expression_valid && !scope_enable),.expression_ready_o(core_expression_ready),
      .expression_note_i(core_expression_note),.expression_value_i(core_expression_value),
      .pitch_ratio_q20_i(pitch_q20_o),.sample_ce_i(core_ce),
      .sample_ready_o(core_sample_ready),.sample_valid_o(synth_valid_o),.sample_o(synth_o),
      .allocated_mask_o(allocated),.active_mask_o(legacy_active_mask),.active_voice_count_o(legacy_active_count),
      .load_busy_o(load_busy),.mix_busy_o(mix_busy),.issued_slot_count_o(issued));
  scope_vec_engine #(.SEPARATE_OFF_NOTE(1)) vector_engine(
      .clk_i,.rst_ni,.panic_i(panic_accept),.sample_ce_i(core_ce),.sample_ready_o(vec_ready),
      .sample_valid_o(vec_valid),.left_o(vec_left),.right_o(vec_right),
      .event_valid_i(core_event_valid && scope_enable),.event_note_on_i(core_note_on),.event_ready_o(vec_event_ready),
      .event_note_i(a),.event_off_note_i(core_note),.event_velocity_i(core_velocity),.event_profile_i(profile),
      .event_shape_i(scope_shape==127 ? a[2:0]-3'd4 : scope_shape[2:0]),
      .event_morph_shape_i(scope_morph_shape),.event_pitch_q20_i(22'd1048576),.pitch_q20_i(pitch_q20_o),
      .morph_q15_i(scope_morph_q15),.scale_q15_i(scope_scale_q15),.rotation_i(scope_rotation),
      .cal_x_q14_i(16'sd12288+$signed({7'd0,scope_cal_x,2'd0})*16'sd16),
      .cal_y_q14_i(16'sd12288+$signed({7'd0,scope_cal_y,2'd0})*16'sd16),
      .offset_x_i(($signed({25'd0,scope_offset_x})-32'sd64)<<<18),
      .offset_y_i(($signed({25'd0,scope_offset_y})-32'sd64)<<<18),
      .active_mask_o(vec_active),.active_count_o(vec_count),.rejected_events_o(vec_rejected),
      .config_error_o(vec_config_error),.frequency_error_o(vec_frequency_error),.clip_o(vec_clip),.busy_o(vec_busy));
  end endgenerate
  assign active_mask_o=scope_enable ? {24'd0,vec_active} : legacy_active_mask;
  assign active_voice_count_o=scope_enable ? {2'd0,vec_count} : legacy_active_count;
  // Join independently scheduled engines before the existing P10 input mixer.
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if(!rst_ni) begin synth_joined<=0;vec_joined<=0;held_synth<=0;held_vec_l<=0;held_vec_r<=0;held_vec_clip<=0;end
    else if(panic_accept) begin synth_joined<=0;vec_joined<=0;held_synth<=0;held_vec_l<=0;held_vec_r<=0;held_vec_clip<=0;end
    else begin
      if(synth_valid_o && frame_inflight) begin synth_joined<=1;held_synth<=synth_o;end
      if(vec_valid && frame_inflight) begin vec_joined<=1;held_vec_l<=vec_left;held_vec_r<=vec_right;held_vec_clip<=vec_clip;end
      if(effects_valid && fx_ready) begin synth_joined<=0;vec_joined<=0;end
    end
  end
  generate if(RUNTIME_EFFECTS_ENABLE) begin: runtime_effects
    workstation_runtime_stereo_effects #(.VECTOR_ENABLE(SYNTH_ENGINES_ENABLE),.D_DELAY_SEND_ENABLE(D_ONLY_ENABLE),.DELAY_BITS(DELAY_BITS),.ECHO_SAMPLES(ECHO_SAMPLES)) effects(
      .clk_i,.rst_ni,.clear_i(engine_clear),.valid_i(effects_valid),.synth_i(panic_muted?32'sd0:held_synth),
      .vector_left_i(panic_muted?32'sd0:held_vec_l),.vector_right_i(panic_muted?32'sd0:held_vec_r),
      .pcm_left_i($signed(held_pcm_l)),.pcm_right_i($signed(held_pcm_r)),
      .synth_gain_i(EXTERNAL_MASTER_VOLUME ? expression_gain : synth_gain_o),.pcm_gain_i(pcm_gain_o),.effect_mask_i(effect_mask_o),.effect_order_i(effect_order_o),
      .delay_send_i(d_delay_send),
      .ready_o(fx_ready),.sample_slot_ready_o(fx_sample_slot_ready),.valid_o(sample_valid_o),.left_o(effect_left),.right_o(effect_right),.clip_o(fx_clip),
      .mem_clk_i(delay_mem_clk_i),.mem_rst_ni(delay_mem_rst_ni),
      .dwr_valid_o(delay_dwr_valid_o),.dwr_data_o(delay_dwr_data_o),.dwr_pop_i(delay_dwr_pop_i),
      .drd_push_i(delay_drd_push_i),.drd_data_i(delay_drd_data_i),.drd_ready_o(delay_drd_ready_o),
      .config_valid_i(engine_rate_commit),.rate_44100_i,
      .history_clear_i(history_clear_i && history_ready_o),
      .config_ready_o(fx_config_ready),.config_applied_o(fx_config_applied),
      .history_ready_o(fx_history_ready),.history_done_o(fx_history_done),
      .quiescent_o(fx_quiet),.fault_o(fx_fault),.applied_rate_44100_o(fx_rate),
      .applied_transaction_o(),.peer_heartbeat_i(delay_peer_heartbeat_i),
      .delay_dma_fault_i,.heartbeat_o(delay_heartbeat_o));
  end else begin: legacy_effects
    assign fx_config_ready=1'b0;assign fx_config_applied=1'b0;
    assign fx_history_ready=1'b0;assign fx_history_done=1'b0;
    assign fx_quiet=1'b0;assign fx_fault=1'b0;assign fx_rate=1'b0;
    assign delay_heartbeat_o=1'b0;
  stereo_effects #(.VECTOR_ENABLE(1),.DELAY_BITS(DELAY_BITS),.ECHO_SAMPLES(ECHO_SAMPLES)) effects(
      .clk_i,.rst_ni,.clear_i(panic_accept),.valid_i(effects_valid),.synth_i(panic_muted?32'sd0:held_synth),
      .vector_left_i(panic_muted?32'sd0:held_vec_l),.vector_right_i(panic_muted?32'sd0:held_vec_r),
      .pcm_left_i($signed(held_pcm_l)),.pcm_right_i($signed(held_pcm_r)),
      .synth_gain_i(EXTERNAL_MASTER_VOLUME ? expression_gain : synth_gain_o),.pcm_gain_i(pcm_gain_o),.effect_mask_i(effect_mask_o),.effect_order_i(effect_order_o),
      .ready_o(fx_ready),.valid_o(sample_valid_o),.left_o(effect_left),.right_o(effect_right),.clip_o(fx_clip),
      .mem_clk_i(delay_mem_clk_i),.mem_rst_ni(delay_mem_rst_ni),
      .dwr_valid_o(delay_dwr_valid_o),.dwr_data_o(delay_dwr_data_o),.dwr_pop_i(delay_dwr_pop_i),
      .drd_push_i(delay_drd_push_i),.drd_data_i(delay_drd_data_i),.drd_ready_o(delay_drd_ready_o));
  end endgenerate
  // Same saturating drive/bit-reduction arithmetic as sampler_fx, operating
  // on the real decoder PCM. Control values are committed only in parameters.
  function automatic signed [31:0] d_process(input signed [31:0] x,input [6:0] crush,drive);
    reg signed [63:0] amplified;
    reg signed [31:0] clipped;
    reg [31:0] keep_mask;
    begin
      // Cancel the exact common factor eight before the signed multiply.
      // Keep the 64-bit context: no product truncation or added sample stage.
      amplified=($signed(x)*$signed({1'b0,8'(16+int'(drive))}))>>>4;
      if(amplified[63:31]=={33{amplified[31]}})clipped=amplified[31:0];
      else clipped=amplified[63] ? 32'sh80000000 : 32'sh7fffffff;
      // (clipped >>> (16+floor(12*crush/127))) <<< that same shift
      // clears a constant prefix. These exact thresholds avoid a divide and
      // two variable shifters; crush zero still retains every original bit.
      keep_mask={4'hf,crush<=7'd126,crush<=7'd116,crush<=7'd105,
          crush<=7'd95,crush<=7'd84,crush<=7'd74,crush<=7'd63,
          crush<=7'd52,crush<=7'd42,crush<=7'd31,crush<=7'd21,
          crush<=7'd10,16'd0};
      if(crush==0)keep_mask=32'hffffffff;
      d_process=clipped & keep_mask;
    end
  endfunction
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if(!rst_ni) begin
      applied_events_o<=0;pending<=0;frame_inflight<=0;deadline_miss_o<=0;note_drop_o<=0;
      held_pcm_l<=0;held_pcm_r<=0;
      held<=0;deferred<=0;releasing<=0;release_index<=0;deferred_current<=0;
      panic_epoch_o<=0;panic_muted<=0;
      vec_previous_rejected<=0;vec_previous_frequency_error<=0;
    end else begin
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
        if(core_ce) begin pending<=0;
          held_pcm_l<=D_ONLY_ENABLE ? d_process(pcm_left_i,d_crush,d_drive) : pcm_left_i;
          held_pcm_r<=D_ONLY_ENABLE ? d_process(pcm_right_i,d_crush,d_drive) : pcm_right_i;
        end
        if(effects_valid && !fx_ready) deadline_miss_o<=deadline_miss_o+1;
      end
      if(releasing && dispatch && (!deferred_current || (scope_enable ? vec_dispatch_ready : core_event_ready))) begin
        deferred[release_index]<=0;
        if(release_index==127) begin releasing<=0;deferred_current<=0;end
        else begin release_index<=next_release_index;deferred_current<=deferred[next_release_index];end
      end
      if(usb_lifecycle) begin
        held<=0;deferred<=0;releasing<=0;release_index<=0;deferred_current<=0;
        panic_epoch_o<=panic_epoch_o+1'b1;panic_muted<=D_ONLY_ENABLE ? 1'b0 : 1'b1;
      end
      if(event_valid && event_ready) begin
        applied_events_o<=applied_events_o+1'b1;
        case(kind)
          0: begin held[a]<=0; if(sustain) deferred[a]<=1; end
          1: if(tf_scope_control_o[12] || full) note_drop_o<=note_drop_o+1; else if(scope_enable && a>95) begin end else begin held[a]<=1; deferred[a]<=0; panic_muted<=0; end
          2: begin
            if(control_rejected) note_drop_o<=note_drop_o+1'b1;
            case(a)
              64: if(b<64 && sustain) begin releasing<=1;release_index<=0;deferred_current<=deferred[0];end
              120: begin
                held<=0;deferred<=0;releasing<=0;release_index<=0;deferred_current<=0;
                panic_epoch_o<=panic_epoch_o+1'b1;panic_muted<=1;
              end
              123: begin deferred<=held|deferred;held<=0;releasing<=1;release_index<=0;deferred_current<=held[0] || deferred[0];end
              default: begin end
            endcase
          end
          default: begin end
        endcase
      end
    end
  end
endmodule
