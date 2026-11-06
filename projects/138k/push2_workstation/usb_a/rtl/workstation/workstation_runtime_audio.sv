`timescale 1ns/1ps

// Explicit opt-in native composition. No accepted profile selects this module.
// Command authorization and TF/record lifecycle policy belong to the caller.
module workstation_runtime_audio #(
    parameter integer WINDOW_CYCLES=50000, STABLE_WINDOWS=4,
    parameter integer TOLERANCE_PPM=2000, LOSS_TIMEOUT_CYCLES=500,
    parameter integer STOP_LOW_CYCLES=16, COUNTER_BITS=32,
    parameter integer SWITCH_TIMEOUT_CYCLES=2000000,
    parameter integer PDN_HOLD_FRAMES=4, STARTUP_MUTE_FRAMES=1028,
    parameter integer DMA_TIMEOUT_CYCLES=1048576,
    parameter bit RESERVE_ZERO_EPOCH=0,
    parameter bit ENABLE_AE350_PCM=0,
    parameter bit SYNTH_ENGINES_ENABLE=1,
    parameter bit D_ONLY_ENABLE=0,
    parameter bit TF_CONTROL_ENABLE=1,
    parameter bit TF_DIRECT_ENABLE=0,
    parameter bit TF_TAIL_LOCAL_RESET_ENABLE=0,
    parameter [31:0] INITIAL_STREAM_EPOCH=RESERVE_ZERO_EPOCH ? 32'd1 : 32'd0,
    parameter bit SEPARATE_COMMON_RESET=0,
    parameter bit PCM_SNAPSHOT_ENABLE=0
) (
    input wire rst_ni, clk_50m_i, compute_clk_i, memory_clk_i,
    input wire reference_48_i, reference_44_i,
    // 50-MHz policy-qualified request; no queue, CPU/CC mapping or busy policy.
    input wire request_i, request_44k1_i, switch_permit_i, recover_i,
    input wire media_quiescent_i,
    output wire request_ready_o, busy_o, fault_o, accepted_o, applied_o,
    output wire rejected_o, failed_o,
    output reg policy_rejected_o,
    output wire [2:0] reject_code_o,
    output wire [3:0] fault_code_o, clock_select_o,
    output wire active_44k1_o, active_valid_o,
    output wire [31:0] stream_epoch_o,
    output wire [1:0] source_qualified_o,
    output wire quiesce_o, stream_flush_o,
    output wire dsp_fault_o, context_ready_o,
    // Compute-domain event/control boundary, identical existing 18-bit events.
    input wire midi_byte_valid_i, pc_byte_valid_i, cpu_event_valid_i,
    input wire [7:0] midi_byte_i, pc_byte_i,
    input wire [17:0] cpu_event_i,
    output wire cpu_event_ready_o,
    input wire signed [31:0] pcm_left_i, pcm_right_i,
    input wire output_mute_i,
    // Explicit F806 page, already crossed as immutable commands to compute.
    input wire pcm_cpu_ready_i,pcm_command_valid_i,pcm_command_write_i,
    input wire [11:0] pcm_command_address_i,
    input wire [31:0] pcm_command_data_i,
    input wire [3:0] pcm_command_strobes_i,
    output wire pcm_command_ready_o,pcm_response_error_o,
    output wire pcm_owner_idle_o,
    output wire [31:0] pcm_response_data_o,
    input wire hci_session_ready_i,
    input wire [31:0] hci_controller_epoch_i,hci_transport_generation_i,
    input wire pcm_tf_busy_i,
    output wire [127:0] held_notes_o,
    output wire [9:0] panic_epoch_o,
    output wire panic_muted_o,
    output wire [31:0] active_mask_o, scope_status_o, tf_scope_control_o,
    output wire [31:0] applied_events_o, control_options_o,
    output wire [5:0] active_voice_count_o,
    output wire [1:0] mode_o,
    output wire [15:0] master_volume_o,
    output wire [21:0] pitch_q20_o,
    output wire [31:0] pc_overflow_o,deadline_miss_o,midi_overflow_o,note_drop_o,
    output wire clip_o,
    output wire [15:0] synth_gain_o,pcm_gain_o,
    output wire [1:0] route_o,
    output wire [2:0] profile_o,effect_mask_o,
    output wire [5:0] effect_order_o,
    output wire [31:0] effect_state_o,
    output wire panel_event_valid_o,
    output wire [6:0] panel_command_o,
    // Atomic same-compute-clock TF packet; asynchronous file transport is external.
    input wire tf_active_i, tf_valid_i, tf_error_i,
    input wire signed [15:0] tf_left_i, tf_right_i,
    input wire [19:0] tf_sample_rate_i,
    input wire [31:0] tf_generation_i, expected_tf_generation_i,
    output wire tf_ready_o,
    input wire tf_last_i,tf_pause_i,
    input wire [31:0] tf_session_i,
    input wire tf_observation_valid_i,tf_observation_error_i,tf_observation_44k1_i,
    input wire tf_observation_gap_i,tf_observation_drop_i,
    input wire [31:0] tf_observation_epoch_i,tf_observation_sequence_i,tf_observation_source_drops_i,
    output wire tf_physical_eos_o,tf_physical_quiescent_o,tf_physical_failed_o,tf_physical_abort_o,
    // Existing owner-6 DDR channel; address units are 32-bit native words.
    output wire ddr_req_o, ddr_write_o,
    output wire [28:0] ddr_address_o,
    output wire [255:0] ddr_data_o,
    output wire [31:0] ddr_mask_o,
    input wire ddr_ready_i, ddr_response_i,
    input wire [255:0] ddr_read_data_i,
    // Selected-MCLK outputs and selected-MCLK pulse-valid consumer contracts.
    output wire mclk_o, bck_o, lrck_o, data_o, pdn_no, smute_o,
    input wire analysis_enable_i, analysis_ready_i, record_enable_i, record_ready_i,
    output wire analysis_valid_o, record_valid_o,
    output wire frame_valid_o, frame_error_o, frame_44k1_o,
    output wire [31:0] frame_epoch_o, frame_sequence_o, frame_pcm_o,
    output wire stream_change_o, sequence_gap_o, analysis_gap_o, record_fault_o,
    output wire [31:0] analysis_drop_count_o, record_drop_count_o,
    output wire [31:0] underrun_count_o, source_error_count_o,
    output wire [31:0] bridge_request_drop_count_o, bridge_return_discard_count_o,
    input wire common_reset_ni
);
    // The monotonic startup grant crosses as data. Only the common
    // assertion reaches async reset pins; every release bit uses local data.
    wire common_reset_n=SEPARATE_COMMON_RESET ? common_reset_ni:rst_ni;
    (* ASYNC_REG="TRUE",syn_preserve=1 *) reg [1:0] startup_control;
    always @(posedge clk_50m_i or negedge common_reset_n)
        if(!common_reset_n)startup_control<=0;else startup_control<={startup_control[0],rst_ni};
    (* ASYNC_REG="TRUE",syn_preserve=1 *) reg [1:0] startup_compute;
    always @(posedge compute_clk_i or negedge common_reset_n)
        if(!common_reset_n)startup_compute<=0;else startup_compute<={startup_compute[0],rst_ni};
    (* ASYNC_REG="TRUE",syn_preserve=1 *) reg [1:0] startup_memory;
    always @(posedge memory_clk_i or negedge common_reset_n)
        if(!common_reset_n)startup_memory<=0;else startup_memory<={startup_memory[0],rst_ni};
    (* ASYNC_REG="TRUE",syn_preserve=1 *) reg [2:0] control_release,compute_release,memory_release;
    always @(posedge clk_50m_i or negedge common_reset_n)
        if(!common_reset_n)control_release<=0;
        else if(SEPARATE_COMMON_RESET && !startup_control[1])control_release<=0;
        else control_release<={control_release[1:0],1'b1};
    always @(posedge compute_clk_i or negedge common_reset_n)
        if(!common_reset_n)compute_release<=0;
        else if(SEPARATE_COMMON_RESET && !startup_compute[1])compute_release<=0;
        else compute_release<={compute_release[1:0],1'b1};
    always @(posedge memory_clk_i or negedge common_reset_n)
        if(!common_reset_n)memory_release<=0;
        else if(SEPARATE_COMMON_RESET && !startup_memory[1])memory_release<=0;
        else memory_release<={memory_release[1:0],1'b1};
    wire control_reset_n=control_release[2],compute_reset_n=compute_release[2],memory_reset_n=memory_release[2];
    wire selected_clock,audio_reset_n,clock_ready,clock_fault,clock_applied,clock_failed;
    wire clock_active_valid,dac_mute,staged_rate,serial_quiet,serial_prefill,serial_running;
    wire [31:0] staged_epoch;
    wire service_quiet,service_fault,service_rate,service_ready,service_done,service_error;
    wire signed [31:0] service_left,service_right;
    wire bridge_quiet,bridge_busy,router_quiet,router_ready,router_done,router_error;
    wire [31:0] router_pcm;
    wire router_source_tf,router_frame_rate;
    wire [31:0] router_frame_epoch,router_frame_sequence;
    wire [31:0] router_unexpected,bridge_unexpected;
    wire router_tf_ready,tail_admit,direct_session_blocked;
    wire direct_tf_selected=TF_DIRECT_ENABLE ?
        (tf_active_i && tail_admit && !tf_pause_i && !direct_session_blocked):tf_active_i;
    wire direct_silence=TF_DIRECT_ENABLE && tf_active_i && !scope_status_o[8] && !direct_tf_selected;
    assign tf_ready_o=router_tf_ready && (!TF_DIRECT_ENABLE || direct_tf_selected);
    wire config_ready,config_accepted,config_applied;
    reg integration_fault;
    wire pcm_hard_fault,pcm_history_request,pcm_history_ready,pcm_history_done,pcm_serial_hold;
    wire [21:0] pcm_cancel_epoch;
    wire signed [31:0] input_left,input_right;
    wire compute_fault=service_fault || integration_fault || pcm_hard_fault;
    (* ASYNC_REG="TRUE",syn_preserve=1 *) reg [1:0] fault_sync,quiet_sync,prefill_sync,running_sync;
    reg fault_previous;
    // Register the combined compute-domain proof before synchronizing it;
    // an AND of independently changing outputs is not itself a CDC register.
    reg all_quiet;
    always @(posedge compute_clk_i or negedge compute_reset_n)
        if(!compute_reset_n)all_quiet<=0;else all_quiet<=bridge_quiet && router_quiet && service_quiet;
    always @(posedge clk_50m_i or negedge control_reset_n)begin
        if(!control_reset_n)begin
            fault_sync<=0;quiet_sync<=0;prefill_sync<=0;running_sync<=0;
            fault_previous<=0;policy_rejected_o<=0;
        end else begin
            fault_sync<={fault_sync[0],compute_fault};quiet_sync<={quiet_sync[0],all_quiet};
            prefill_sync<={prefill_sync[0],serial_prefill};running_sync<={running_sync[0],serial_running};
            fault_previous<=fault_sync[1];
            policy_rejected_o<=request_i && !switch_permit_i;
        end
    end
    assign dsp_fault_o=fault_sync[1];
    assign request_ready_o=clock_ready && switch_permit_i && !dsp_fault_o;
    assign fault_o=clock_fault || dsp_fault_o;
    assign failed_o=clock_failed || (dsp_fault_o && !fault_previous);
    assign active_valid_o=clock_active_valid && !dsp_fault_o;
    assign applied_o=clock_applied && !dsp_fault_o;
    workstation_audio_clock_domain #(
        .WINDOW_CYCLES(WINDOW_CYCLES),.STABLE_WINDOWS(STABLE_WINDOWS),.TOLERANCE_PPM(TOLERANCE_PPM),
        .LOSS_TIMEOUT_CYCLES(LOSS_TIMEOUT_CYCLES),.STOP_LOW_CYCLES(STOP_LOW_CYCLES),
        .COUNTER_BITS(COUNTER_BITS),.SWITCH_TIMEOUT_CYCLES(SWITCH_TIMEOUT_CYCLES),
        .RESERVE_ZERO_EPOCH(RESERVE_ZERO_EPOCH),.INITIAL_STREAM_EPOCH(INITIAL_STREAM_EPOCH),.SEPARATE_COMMON_RESET(SEPARATE_COMMON_RESET)
    ) clocks(
        .clk_50m_i,.rst_ni,.common_reset_ni(common_reset_n),.reference_48_i,.reference_44_i,
        .request_i(request_i && switch_permit_i && !dsp_fault_o),.request_44k1_i,.recover_i,
        .frame_quiescent_i(quiet_sync[1] && media_quiescent_i && !dsp_fault_o),
        .prefill_ready_i(prefill_sync[1] && context_ready_o && !dsp_fault_o),
        .output_running_i(running_sync[1] && context_ready_o && !dsp_fault_o),
        .selected_clock_o(selected_clock),.audio_reset_no(audio_reset_n),.request_ready_o(clock_ready),
        .busy_o,.fault_o(clock_fault),.accepted_o,.applied_o(clock_applied),.rejected_o,
        .failed_o(clock_failed),.reject_code_o,.fault_code_o,.clock_select_o,
        .quiesce_o,.dac_mute_o(dac_mute),.stream_flush_o,
        .active_44k1_o,.active_valid_o(clock_active_valid),.staged_44k1_o(staged_rate),
        .stream_epoch_o,.staged_epoch_o(staged_epoch),.source_qualified_o,.source_present_o(),
        .selected_qualified_o(),.selected_stopped_low_o(),.measured_48_o(),.measured_44_o(),.measured_selected_o());

    // One immutable rate/epoch mailbox. The ACK means ALL DSP/history ACKs,
    // never merely capture/acceptance. No naked multi-bit two-flop crossing.
    (* syn_preserve=1 *) reg [32:0] context_payload;
    reg context_toggle,context_sent,context_ack;
    (* ASYNC_REG="TRUE",syn_preserve=1 *) reg [1:0] ack_sync,context_sync;
    assign context_ready_o=context_sent && ack_sync[1]==context_toggle &&
        context_payload=={staged_rate,staged_epoch} && !dsp_fault_o;
    always @(posedge clk_50m_i or negedge control_reset_n)begin
        if(!control_reset_n)begin context_payload<=0;context_toggle<=0;context_sent<=0;ack_sync<=0;end
        else begin
            ack_sync<={ack_sync[0],context_ack};
            if((!context_sent || context_payload!={staged_rate,staged_epoch}) && ack_sync[1]==context_toggle)begin
                context_payload<={staged_rate,staged_epoch};context_toggle<=!context_toggle;context_sent<=1;
            end
        end
    end
    localparam [2:0] CFG_IDLE=0,CFG_SETTLE=1,CFG_DRAIN=2,CFG_ACCEPT=3,CFG_ACK=4;
    reg [2:0] config_state;
    // Register the ACCEPT predicate on the very same FSM transition. Its
    // value is always config_state==CFG_ACCEPT; no admission edge is added.
    // This keeps the state decode out of the high-fanout DSP request cone.
    (* syn_preserve=1 *) reg config_accept_pending;
    reg pending_rate,compute_rate,compute_context_valid;
    reg [31:0] pending_epoch,compute_epoch;
    // integration_fault is set only in CFG_ACK or an invalid state; neither
    // can return to CFG_ACCEPT. Keep actual service/PCM fault vetoes here
    // without feeding that unreachable integration-fault condition through
    // the service's acceptance/ready path and back into this state register.
    wire config_valid=config_accept_pending && !service_fault && !pcm_hard_fault;
    always @(posedge compute_clk_i or negedge compute_reset_n)begin
        if(!compute_reset_n)begin
            context_sync<=0;context_ack<=0;config_state<=CFG_IDLE;
            config_accept_pending<=0;
            pending_rate<=0;pending_epoch<=0;compute_rate<=0;compute_epoch<=0;
            compute_context_valid<=0;integration_fault<=0;
        end else begin
            context_sync<={context_sync[0],context_toggle};
            case(config_state)
                CFG_IDLE:if(context_sync[1]!=context_ack)config_state<=CFG_SETTLE;
                CFG_SETTLE:begin
                    {pending_rate,pending_epoch}<=context_payload;config_state<=CFG_DRAIN;
                end
                CFG_DRAIN:if(router_quiet && service_quiet && !bridge_busy)begin
                    config_state<=CFG_ACCEPT;config_accept_pending<=1;
                end
                CFG_ACCEPT:if(config_accepted)begin
                    config_state<=CFG_ACK;config_accept_pending<=0;
                end
                CFG_ACK:if(config_applied && !integration_fault)begin
                    if(service_rate!=pending_rate)integration_fault<=1;
                    else begin
                        compute_rate<=pending_rate;compute_epoch<=pending_epoch;compute_context_valid<=1;
                        context_ack<=context_sync[1];config_state<=CFG_IDLE;
                    end
                end
                default:integration_fault<=1;
            endcase
        end
    end

    // Stream ingress and source policy remain audio-owned. No new DSP or gain.
    generate if(ENABLE_AE350_PCM)begin: cpu_pcm
        wire session_live;
        wire [31:0] session_epoch,session_generation;
        workstation_ae350_pcm_session session(
            .reset_ni(SEPARATE_COMMON_RESET ? compute_reset_n:rst_ni),.clk_i(compute_clk_i),.source_ready_i(hci_session_ready_i),
            .source_epoch_i(hci_controller_epoch_i),.source_generation_i(hci_transport_generation_i),
            .live_o(session_live),.epoch_o(session_epoch),.generation_o(session_generation));
        reg switch_inhibit_50;
        (* ASYNC_REG="TRUE",syn_preserve=1 *) reg [1:0] switch_inhibit_compute;
        always @(posedge clk_50m_i or negedge control_reset_n)
            if(!control_reset_n)switch_inhibit_50<=1;else switch_inhibit_50<=busy_o || quiesce_o;
        always @(posedge compute_clk_i or posedge switch_inhibit_50 or negedge compute_reset_n)
            if(!compute_reset_n || switch_inhibit_50)switch_inhibit_compute<=3;
            else switch_inhibit_compute<={switch_inhibit_compute[0],1'b0};
        workstation_ae350_pcm_owner #(.SUSTAINED_VERIFIED(D_ONLY_ENABLE),.SNAPSHOT_ENABLE(PCM_SNAPSHOT_ENABLE)) owner(
            .clk_i(compute_clk_i),.reset_ni(compute_reset_n),.cpu_ready_i(pcm_cpu_ready_i),
            .command_valid_i(pcm_command_valid_i),.command_write_i(pcm_command_write_i),
            .command_address_i(pcm_command_address_i),.command_data_i(pcm_command_data_i),
            .command_strobes_i(pcm_command_strobes_i),.command_ready_o(pcm_command_ready_o),
            .response_data_o(pcm_response_data_o),.response_error_o(pcm_response_error_o),
            .session_live_i(session_live),.controller_epoch_i(session_epoch),.transport_generation_i(session_generation),
            .context_ready_i(compute_context_valid && config_state==CFG_IDLE && !compute_fault),
            .rate_44100_i(compute_rate),.physical_epoch_i(compute_epoch),.tf_busy_i(pcm_tf_busy_i),
            .switch_busy_i(switch_inhibit_compute[1]),.sample_take_i(render_request && service_ready),
            .legacy_left_i(pcm_left_i),.legacy_right_i(pcm_right_i),.pcm_left_o(input_left),.pcm_right_o(input_right),
            .history_clear_o(pcm_history_request),.history_ready_i(pcm_history_ready && !config_valid),.history_done_i(pcm_history_done),
            .serial_hold_o(pcm_serial_hold),.cancel_epoch_o(pcm_cancel_epoch),.selected_o(),.failed_o(),.hard_fault_o(pcm_hard_fault),.idle_o(pcm_owner_idle_o));
    end else begin: no_cpu_pcm
        assign input_left=pcm_left_i;assign input_right=pcm_right_i;
        assign pcm_command_ready_o=1'b1;assign pcm_response_data_o=0;assign pcm_response_error_o=1'b1;
        assign pcm_owner_idle_o=1'b1;
        assign pcm_history_request=1'b0;assign pcm_serial_hold=1'b0;assign pcm_cancel_epoch=0;assign pcm_hard_fault=1'b0;
    end endgenerate
    // The monotonic startup grant crosses as data. Only the common
    // assertion reaches async reset pins; every release bit uses local data.
    (* ASYNC_REG="TRUE",syn_preserve=1 *) reg [1:0] startup_serial;
    always @(posedge selected_clock or negedge common_reset_n)
        if(!common_reset_n)startup_serial<=0;else startup_serial<={startup_serial[0],rst_ni};
    (* ASYNC_REG="TRUE",syn_preserve=1 *) reg [2:0] serial_common_release;
    always @(posedge selected_clock or negedge common_reset_n)
        if(!common_reset_n)serial_common_release<=0;
        else if(SEPARATE_COMMON_RESET && !startup_serial[1])serial_common_release<=0;
        else serial_common_release<={serial_common_release[1:0],1'b1};
    wire serial_common_reset_n=serial_common_release[2];

    // A held source revoke drops pending serial payloads. Assertion is immediate;
    // release crosses two selected-clock flops and the serializer's frame guard.
    (* ASYNC_REG="TRUE",syn_preserve=1 *) reg [1:0] pcm_hold_serial;
    always @(posedge selected_clock or posedge pcm_serial_hold or negedge serial_common_reset_n)
        if(!serial_common_reset_n || pcm_serial_hold)pcm_hold_serial<=3;
        else pcm_hold_serial<={pcm_hold_serial[0],1'b0};

    // Local serializer reset is only asserted by the clock transaction/fault.
    // A new staged context MUST NOT cut the old frame during QUIESCE.
    // On each restart wait for the atomic config ACK, then eight real selected
    // edges. This also settles bridge global-release/quiesce synchronizers
    // BEFORE the serializer can emit its first request (no first-slot loss).
    wire serial_safe_n=audio_reset_n && !dsp_fault_o;
    reg [3:0] serial_guard;
    reg serial_reset_n,serial_rate;
    reg [31:0] serial_epoch;
    (* ASYNC_REG="TRUE",syn_preserve=1 *) reg [1:0] serial_quiesce,serial_resume,serial_context_ready;
    always @(posedge selected_clock or negedge serial_safe_n)begin
        if(!serial_safe_n)begin
            serial_guard<=0;serial_reset_n<=0;serial_quiesce<=3;serial_resume<=0;serial_context_ready<=0;
            serial_rate<=0;serial_epoch<=0;
        end
        else begin
            serial_quiesce<={serial_quiesce[0],quiesce_o};serial_resume<={serial_resume[0],!dac_mute};
            serial_context_ready<={serial_context_ready[0],context_ready_o};
            if(!serial_reset_n)begin
                if(serial_context_ready[1] && !serial_quiesce[1])begin
                    // Bundled payload has been immutable throughout config,
                    // its return ACK, two selected synchronizers and this guard.
                    if(serial_guard==0)begin serial_rate<=staged_rate;serial_epoch<=staged_epoch;end
                    if(serial_guard==7)serial_reset_n<=1;else serial_guard<=serial_guard+1'b1;
                end else serial_guard<=0;
            end
        end
    end
    wire serial_request,serial_request_rate,sample_valid,sample_ready,sample_rate,sample_error;
    wire [31:0] serial_request_epoch,serial_request_sequence,sample_epoch,sample_sequence,sample_pcm;
    wire bridge_request,bridge_rate;
    wire [31:0] bridge_epoch,bridge_sequence;
    workstation_pcm_frame_bridge bridge(
        .reset_ni(common_reset_n),.serial_clk_i(selected_clock),.compute_clk_i,
        .serial_reset_ni(serial_reset_n),.serial_quiet_i(serial_quiet),.quiesce_i(quiesce_o),
        .request_i(serial_request),.request_44k1_i(serial_request_rate),
        .request_epoch_i(serial_request_epoch),.request_sequence_i(serial_request_sequence),.request_ready_o(),
        .sample_valid_o(sample_valid),.sample_ready_i(sample_ready),.sample_44k1_o(sample_rate),.sample_error_o(sample_error),
        .sample_epoch_o(sample_epoch),.sample_sequence_o(sample_sequence),.sample_pcm_o(sample_pcm),
        .render_ready_i(router_ready && compute_context_valid && config_state==CFG_IDLE && !compute_fault),
        .render_done_i(router_done),.rendered_pcm_i(router_pcm),.rendered_error_i(router_error),
        .render_request_o(bridge_request),.render_44k1_o(bridge_rate),.render_epoch_o(bridge_epoch),
        .render_sequence_o(bridge_sequence),.render_busy_o(bridge_busy),.quiescent_o(bridge_quiet),
        .request_drop_count_o(bridge_request_drop_count_o),.return_discard_count_o(bridge_return_discard_count_o),
        .cancelled_request_count_o(),.cancelled_render_count_o(),.unexpected_render_count_o(bridge_unexpected));
    wire render_request,render_rate;
    workstation_final_pcm_router #(.CONTROLLED_SILENCE_ENABLE(TF_DIRECT_ENABLE)) final_pcm(
        .clk_i(compute_clk_i),.rst_ni(compute_reset_n),.request_i(bridge_request),.request_44k1_i(bridge_rate),
        .request_epoch_i(bridge_epoch),.request_sequence_i(bridge_sequence),.request_ready_o(router_ready),
        .active_44k1_i(compute_rate),.active_epoch_i(compute_epoch),.cancel_epoch_i({pcm_cancel_epoch,panic_epoch_o}),
        .scope_enable_i(scope_status_o[8]),.tf_active_i(direct_tf_selected),.master_volume_i(master_volume_o),
        .mute_i(output_mute_i || panic_muted_o),.tf_valid_i,.tf_error_i,.tf_left_i,.tf_right_i,
        .controlled_silence_i(direct_silence),
        .tf_sample_rate_i,.tf_generation_i,.expected_tf_generation_i,.tf_ready_o(router_tf_ready),
        .render_ready_i(service_ready),.render_done_i(service_done),.render_error_i(service_error),
        .render_left_i(service_left),.render_right_i(service_right),.render_request_o(render_request),.render_44k1_o(render_rate),
        .frame_valid_o(router_done),.frame_error_o(router_error),.frame_44k1_o(router_frame_rate),.frame_source_tf_o(router_source_tf),
        .frame_epoch_o(router_frame_epoch),.frame_sequence_o(router_frame_sequence),.frame_pcm_o(router_pcm),.frame_error_bits_o(),.frame_gain_o(),
        .quiescent_o(router_quiet),.rejected_request_count_o(),.tf_underrun_count_o(),.rate_mismatch_count_o(),
        .stale_source_count_o(),.cancelled_frame_count_o(),.unexpected_render_count_o(router_unexpected),.clipped_frame_count_o());
    wire dwr_valid,dwr_pop,drd_push,drd_ready,audio_heartbeat,memory_heartbeat,dma_fault;
    wire [64:0] dwr_data,drd_data;
    workstation_audio_render_service #(.RUNTIME_RATE_ENABLE(1),.RUNTIME_EFFECTS_ENABLE(1),
        .SYNTH_ENGINES_ENABLE(SYNTH_ENGINES_ENABLE),.D_ONLY_ENABLE(D_ONLY_ENABLE),
        .TF_CONTROL_ENABLE(TF_CONTROL_ENABLE)) service(
        .clk_i(compute_clk_i),.rst_ni(compute_reset_n),
        .config_valid_i(config_valid),.config_rate_44100_i(pending_rate),.history_clear_i(pcm_history_request),
        .config_ready_o(config_ready),.config_accepted_o(config_accepted),.config_applied_o(config_applied),.history_ready_o(pcm_history_ready),.history_done_o(pcm_history_done),
        .quiescent_o(service_quiet),.fault_o(service_fault),.applied_rate_44100_o(service_rate),
        .delay_peer_heartbeat_i(memory_heartbeat),.delay_dma_fault_i(dma_fault),.delay_heartbeat_o(audio_heartbeat),
        .render_request_i(render_request),.render_44k1_i(render_rate),.render_ready_o(service_ready),
        .render_done_o(service_done),.render_error_o(service_error),.render_left_o(service_left),.render_right_o(service_right),
        .render_busy_o(),.sample_ce_o(),.rejected_request_count_o(),.unsupported_rate_count_o(),
        .cancelled_response_count_o(),.drained_result_count_o(),.midi_byte_valid_i,.midi_byte_i,
        .pc_byte_valid_i,.pc_byte_i,.cpu_event_valid_i,.cpu_event_i,.cpu_event_ready_o,.pcm_left_i(input_left),.pcm_right_i(input_right),
        .held_notes_o,.applied_events_o,.pc_overflow_o,.control_options_o,.panic_epoch_o,.panic_muted_o,
        .active_mask_o,.active_voice_count_o,.mode_o,.pitch_q20_o,.deadline_miss_o,.midi_overflow_o,.note_drop_o,
        .clip_o,.synth_gain_o,.pcm_gain_o,.master_volume_o,.route_o,.profile_o,.effect_mask_o,.effect_order_o,.effect_state_o,
        .panel_event_valid_o,.panel_command_o,.scope_status_o,.tf_scope_control_o,.delivery_duplicate_count_o(),
        .delay_mem_clk_i(memory_clk_i),.delay_mem_rst_ni(memory_reset_n),.delay_dwr_valid_o(dwr_valid),.delay_dwr_data_o(dwr_data),
        .delay_dwr_pop_i(dwr_pop),.delay_drd_push_i(drd_push),.delay_drd_data_i(drd_data),.delay_drd_ready_o(drd_ready));
    workstation_runtime_delay_ddr_dma #(.TRANSACTION_TIMEOUT_CYCLES(DMA_TIMEOUT_CYCLES)) delay_dma(
        .clk_i(memory_clk_i),.rst_ni(memory_reset_n),.dwr_valid_i(dwr_valid),.dwr_data_i(dwr_data),.dwr_pop_o(dwr_pop),
        .drd_push_o(drd_push),.drd_data_o(drd_data),.drd_ready_i(drd_ready),
        .ddr_req_o,.ddr_write_o,.ddr_address_o,.ddr_data_o,.ddr_mask_o,.ddr_ready_i,.ddr_response_i,.ddr_read_data_i,
        .debug_status_o(),.flush_done_o(),.fault_o(dma_fault),.applied_rate_44100_o(),.applied_transaction_o(),
        .peer_heartbeat_i(audio_heartbeat),.heartbeat_o(memory_heartbeat));
    wire serializer_pdn,serializer_mute,physical_error,physical_rate;
    wire [31:0] physical_epoch,physical_sequence,physical_pcm;
    workstation_i2s_serializer #(.PDN_HOLD_FRAMES(PDN_HOLD_FRAMES),.STARTUP_MUTE_FRAMES(STARTUP_MUTE_FRAMES),
        .SAMPLE_ERROR_ENABLE(1),.SOURCE_HOLD_ENABLE(ENABLE_AE350_PCM)) serializer(
        .clk_i(selected_clock),.rst_ni(serial_reset_n),.rate_44k1_i(serial_rate),.epoch_i(serial_epoch),
        .quiesce_i(serial_quiesce[1]),.resume_i(serial_resume[1]),.source_hold_i(pcm_hold_serial[1]),.serial_quiescent_o(serial_quiet),
        .output_running_o(serial_running),.prefill_ready_o(serial_prefill),.request_o(serial_request),
        .request_sequence_o(serial_request_sequence),.request_44k1_o(serial_request_rate),.request_epoch_o(serial_request_epoch),
        .sample_valid_i(sample_valid),.sample_ready_o(sample_ready),.sample_44k1_i(sample_rate),.sample_error_i(sample_error),
        .sample_epoch_i(sample_epoch),.sample_sequence_i(sample_sequence),.sample_pcm_i(sample_pcm),
        .mclk_o,.bck_o,.lrck_o,.data_o,.pdn_no(serializer_pdn),.smute_o(serializer_mute),
        .frame_valid_o,.frame_error_o(physical_error),.frame_pcm_o(physical_pcm),.frame_sequence_o(physical_sequence),
        .frame_44k1_o(physical_rate),.frame_epoch_o(physical_epoch),.underrun_count_o,.source_error_count_o,.rejected_sample_count_o());
    assign pdn_no=serializer_pdn && !dsp_fault_o;
    assign smute_o=serializer_mute || dac_mute || dsp_fault_o;
    generate if(TF_DIRECT_ENABLE)begin:g_direct_tf
        // Reuse the existing coherent runtime lifetime. Local releases wait
        // for their own clock; sample scheduling and per-session fences do
        // not reset this two-clock mailbox.
        wire tail_compute_reset_n=TF_TAIL_LOCAL_RESET_ENABLE ? compute_reset_n:common_reset_n;
        reg [31:0] generation_q,epoch_q;
        reg [9:0] panic_q;
        reg [21:0] cancel_q;
        reg rate_q,blocked,tail_failed_q,drain_pending,quiet_published;
        reg [31:0] drain_epoch,drain_sequence;
        reg drain_rate;
        wire tail_failed,tail_quiet,tail_closed,tail_pending,tail_armed;
        wire generation_change=expected_tf_generation_i!=generation_q;
        wire local_abort=tf_active_i && !blocked &&
            (panic_epoch_o!=panic_q || pcm_cancel_epoch!=cancel_q || compute_epoch!=epoch_q ||
             compute_rate!=rate_q || compute_fault || !compute_context_valid);
        wire failure_event=tail_failed && !tail_failed_q;
        wire fence=generation_change || local_abort || failure_event;
        wire fire=tf_valid_i && tf_ready_o;
        wire arm_valid=compute_context_valid && config_state==CFG_IDLE && !compute_fault &&
            tf_active_i && tf_valid_i && !tf_pause_i && !blocked && !fence;
        wire transport_health_valid;
        wire [63:0] transport_health;
        reg [63:0] transport_health_q;
        reg [31:0] router_unexpected_q,bridge_unexpected_q;
        gw138k_stream_cdc #(.WIDTH(64)) transport_health_mailbox(
            .reset_n(common_reset_n),.source_clk(selected_clock),.destination_clk(compute_clk_i),
            .source_valid(frame_valid_o),.source_data({bridge_request_drop_count_o,bridge_return_discard_count_o}),
            .drop_count(),.destination_valid(transport_health_valid),.destination_data(transport_health));
        wire transport_fault=(transport_health_valid && transport_health!=transport_health_q) ||
            router_unexpected!=router_unexpected_q || bridge_unexpected!=bridge_unexpected_q;
        (* ASYNC_REG="TRUE",syn_preserve=1 *) reg [1:0] serial_quiet_compute;
        always @(posedge compute_clk_i or negedge tail_compute_reset_n)
            if(!tail_compute_reset_n)begin
                generation_q<=0;epoch_q<=0;panic_q<=0;cancel_q<=0;rate_q<=0;
                blocked<=0;tail_failed_q<=0;drain_pending<=0;drain_epoch<=0;drain_sequence<=0;drain_rate<=0;serial_quiet_compute<=0;quiet_published<=0;
                transport_health_q<=0;router_unexpected_q<=0;bridge_unexpected_q<=0;
            end else begin
                generation_q<=expected_tf_generation_i;epoch_q<=compute_epoch;rate_q<=compute_rate;
                panic_q<=panic_epoch_o;cancel_q<=pcm_cancel_epoch;tail_failed_q<=tail_failed;
                serial_quiet_compute<={serial_quiet_compute[0],serial_quiet};
                quiet_published<=compute_reset_n && tail_quiet && !drain_pending && !fire && !arm_valid && !fence;
                if(transport_health_valid)transport_health_q<=transport_health;
                router_unexpected_q<=router_unexpected;bridge_unexpected_q<=bridge_unexpected;
                if(generation_change)blocked<=0;
                if(local_abort || failure_event)blocked<=1;
                // Cancellation retires only after the actual last admitted
                // slot is observed, or the entire real serial path is quiet.
                if(tf_observation_valid_i && tf_observation_epoch_i==drain_epoch &&
                   tf_observation_sequence_i==drain_sequence && tf_observation_44k1_i==drain_rate)
                    drain_pending<=0;
                if(serial_quiet_compute[1] && bridge_quiet && router_quiet)drain_pending<=0;
                if(fire)begin
                    drain_pending<=1;drain_epoch<=bridge_epoch;drain_sequence<=bridge_sequence;drain_rate<=bridge_rate;
                end
            end
        assign direct_session_blocked=blocked;
        assign tf_physical_quiescent_o=quiet_published;
        assign tf_physical_abort_o=local_abort;
        assign tf_physical_failed_o=failure_event;
        workstation_tf_physical_tail_v1 #(.SEPARATE_DOMAIN_RESET(TF_TAIL_LOCAL_RESET_ENABLE)) tail(
            .rst_ni(common_reset_n),.compute_clk_i,.serial_clk_i(selected_clock),.fence_i(fence),
            .compute_reset_ni(compute_reset_n),.serial_reset_ni(serial_common_reset_n),
            .arm_valid_i(arm_valid),.arm_ready_o(),.arm_44k1_i(compute_rate),
            .arm_generation_i(tf_generation_i),.arm_session_i(tf_session_i),.arm_epoch_i(compute_epoch),
            .armed_o(tail_armed),.tail_pending_o(tail_pending),.tail_closed_o(tail_closed),.tf_admit_o(tail_admit),.quiescent_o(tail_quiet),
            .tf_fire_i(fire),.tf_last_i(tf_last_i),.tf_error_i(tf_error_i),.tf_44k1_i(tf_sample_rate_i==20'd44100),
            .tf_generation_i(tf_generation_i),.tf_session_i(tf_session_i),.render_epoch_i(bridge_epoch),.render_sequence_i(bridge_sequence),
            .router_valid_i(router_done),.router_error_i(router_error),.router_source_tf_i(router_source_tf),
            .router_44k1_i(router_frame_rate),.router_epoch_i(router_frame_epoch),.router_sequence_i(router_frame_sequence),
            .transport_fault_i(transport_fault),
            .observation_valid_i(tf_observation_valid_i),.observation_error_i(tf_observation_error_i),
            .observation_44k1_i(tf_observation_44k1_i),.observation_gap_i(tf_observation_gap_i),.observation_drop_event_i(tf_observation_drop_i),
            .observation_epoch_i(tf_observation_epoch_i),.observation_sequence_i(tf_observation_sequence_i),
            .physical_valid_i(frame_valid_o),.physical_error_i(physical_error),.physical_44k1_i(physical_rate),
            .physical_epoch_i(physical_epoch),.physical_sequence_i(physical_sequence),.observation_source_drops_i(tf_observation_source_drops_i),
            .physical_eos_o(tf_physical_eos_o),.failed_o(tail_failed),.tail_cancelled_o(),.failure_code_o(),
            .tail_epoch_o(),.tail_sequence_o(),.baseline_drops_o(),.tail_drops_o(),.mailbox_busy_o());
    end else begin:g_legacy_tf
        assign tail_admit=1'b1,direct_session_blocked=1'b0;
        assign tf_physical_eos_o=1'b0,tf_physical_quiescent_o=1'b1,tf_physical_failed_o=1'b0,tf_physical_abort_o=1'b0;
    end endgenerate
    workstation_pcm_frame_fanout taps(
        .clk_i(selected_clock),.rst_ni(SEPARATE_COMMON_RESET ? serial_common_reset_n:rst_ni),.frame_valid_i(frame_valid_o),.frame_error_i(physical_error),
        .frame_44k1_i(physical_rate),.frame_epoch_i(physical_epoch),.frame_sequence_i(physical_sequence),.frame_pcm_i(physical_pcm),
        .analysis_enable_i,.analysis_ready_i,.record_enable_i,.record_ready_i,.analysis_valid_o,.record_valid_o,
        .frame_error_o,.frame_44k1_o,.frame_epoch_o,.frame_sequence_o,.frame_pcm_o,
        .stream_change_o,.sequence_gap_o,.analysis_gap_o,.record_fault_o,.analysis_drop_count_o,.record_drop_count_o,
        .sequence_gap_count_o(),.stream_change_count_o(),.error_frame_count_o());
endmodule
