`timescale 1ns/1ps

// Request-driven synth/vector render service in the always-running compute domain.
// Source selection and final master-volume processing remain downstream.
// No output-clock divider, autonomous sample tick, or second parameter owner.
module workstation_audio_render_service #(
    parameter bit RUNTIME_RATE_ENABLE=0,
    parameter bit RUNTIME_EFFECTS_ENABLE=0,
    parameter bit SYNTH_ENGINES_ENABLE=1,
    parameter bit D_ONLY_ENABLE=0,
    parameter integer DELAY_BITS=14,
    parameter integer ECHO_SAMPLES=9600
) (
    input wire clk_i,rst_ni,
    input wire config_valid_i,config_rate_44100_i,history_clear_i,
    output wire config_ready_o,config_applied_o,history_ready_o,history_done_o,
    output wire quiescent_o,fault_o,applied_rate_44100_o,
    input wire delay_peer_heartbeat_i,delay_dma_fault_i,
    output wire delay_heartbeat_o,
    input wire render_request_i,render_44k1_i,
    output wire render_ready_o,
    output reg render_done_o,render_error_o,
    output reg signed [31:0] render_left_o,render_right_o,
    output wire render_busy_o,sample_ce_o,
    output reg [31:0] rejected_request_count_o,unsupported_rate_count_o,
    output reg [31:0] cancelled_response_count_o,drained_result_count_o,
    input wire midi_byte_valid_i,
    input wire [7:0] midi_byte_i,
    input wire pc_byte_valid_i,
    input wire [7:0] pc_byte_i,
    input wire cpu_event_valid_i,
    input wire [17:0] cpu_event_i,
    output wire cpu_event_ready_o,
    input wire signed [31:0] pcm_left_i,pcm_right_i,
    output wire [127:0] held_notes_o,
    output wire [31:0] applied_events_o,pc_overflow_o,control_options_o,
    output wire [9:0] panic_epoch_o,
    output wire panic_muted_o,
    output wire [31:0] active_mask_o,
    output wire [5:0] active_voice_count_o,
    output wire [1:0] mode_o,
    output wire [21:0] pitch_q20_o,
    output wire [31:0] deadline_miss_o,midi_overflow_o,note_drop_o,
    output wire clip_o,
    output wire [15:0] synth_gain_o,pcm_gain_o,master_volume_o,
    output wire [1:0] route_o,
    output wire [2:0] profile_o,effect_mask_o,
    output wire [5:0] effect_order_o,
    output wire [31:0] effect_state_o,
    output wire panel_event_valid_o,
    output wire [6:0] panel_command_o,
    output wire [31:0] scope_status_o,tf_scope_control_o,
    output wire [31:0] delivery_duplicate_count_o,
    input wire delay_mem_clk_i,delay_mem_rst_ni,
    output wire delay_dwr_valid_o,
    output wire [64:0] delay_dwr_data_o,
    input wire delay_dwr_pop_i,delay_drd_push_i,
    input wire [64:0] delay_drd_data_i,
    output wire delay_drd_ready_o
);
    reg active,response_sent;
    reg held_rate,external_busy,request_muted;
    wire core_rate_ready,core_rate_applied,core_rate_busy,core_fault,core_rate;
    wire core_history_ready,core_history_done;
    wire external_free=!active && !external_busy && !core_fault;
    // Raw request forwarding keeps valid independent of ready. The event
    // boundary reserves the commit edge before it evaluates engine ready.
    wire external_config=RUNTIME_EFFECTS_ENABLE && config_valid_i && external_free;
    wire external_history=RUNTIME_EFFECTS_ENABLE && history_clear_i && external_free && !config_valid_i;
    wire automatic_config=RUNTIME_EFFECTS_ENABLE &&
        ((accepted && render_44k1_i!=core_rate) ||
         (active && !response_sent && !cancelled && held_rate!=core_rate && !core_rate_busy));
    wire core_config=external_config || automatic_config;
    wire requested_rate=external_config ? config_rate_44100_i : accepted ? render_44k1_i : held_rate;
    reg [9:0] request_cancel_epoch;
    reg signed [31:0] held_pcm_left,held_pcm_right;
    wire core_idle,core_valid,delivery_valid;
    wire signed [31:0] core_left,core_right,delivery_left,delivery_right;
    wire accepted=render_request_i && render_ready_o;
    // Ready promises this one request slot. Register the sample immediately:
    // the existing workstation pending bit gives it priority over new events.
    assign render_ready_o=rst_ni && !active && (!RUNTIME_EFFECTS_ENABLE ||
        (!external_busy && !core_rate_busy && !core_fault && !config_valid_i && !history_clear_i));
    assign render_busy_o=active || (RUNTIME_EFFECTS_ENABLE && (external_busy || core_rate_busy));
    assign sample_ce_o=accepted && (RUNTIME_EFFECTS_ENABLE || !render_44k1_i);
    assign config_ready_o=RUNTIME_EFFECTS_ENABLE && external_free && core_rate_ready;
    assign history_ready_o=RUNTIME_EFFECTS_ENABLE && external_free && core_history_ready;
    assign config_applied_o=RUNTIME_EFFECTS_ENABLE && core_rate_applied;
    assign history_done_o=RUNTIME_EFFECTS_ENABLE && core_history_done;
    assign fault_o=RUNTIME_EFFECTS_ENABLE && core_fault;
    assign applied_rate_44100_o=RUNTIME_EFFECTS_ENABLE && core_rate;
    assign quiescent_o=rst_ni && !active && !external_busy && core_idle && !core_fault;
    // A new native request accepted in intentional PANIC mute is a good
    // deterministic zero. It keeps that identity even if NoteOn unmutes while
    // rendering; only a later cancellation epoch can cancel the transaction.
    wire cancelled=panic_epoch_o!=request_cancel_epoch ||
        (panic_muted_o && (!RUNTIME_EFFECTS_ENABLE || !request_muted));

    function automatic [31:0] increment(input [31:0] value);
        increment=&value ? value : value+1'b1;
    endfunction

    gw138k_event_workstation #(.SAMPLE_RATE_HZ(48000),.TIMING_OPTIMIZED(1),
        .EXTERNAL_MASTER_VOLUME(1),.REQUEST_DRIVEN_RENDER(1),
        .RUNTIME_RATE_ENABLE(RUNTIME_RATE_ENABLE),.RUNTIME_EFFECTS_ENABLE(RUNTIME_EFFECTS_ENABLE),
        .SYNTH_ENGINES_ENABLE(SYNTH_ENGINES_ENABLE),.D_ONLY_ENABLE(D_ONLY_ENABLE),
        .DELAY_BITS(DELAY_BITS),.ECHO_SAMPLES(ECHO_SAMPLES)) workstation(
        .clk_i,.rst_ni,.midi_byte_valid_i,.midi_byte_i,.pc_byte_valid_i,.pc_byte_i,
        .cpu_event_valid_i,.cpu_event_i,.cpu_event_ready_o,
        .sample_ce_i(sample_ce_o),
        .pcm_left_i(accepted ? pcm_left_i : held_pcm_left),
        .pcm_right_i(accepted ? pcm_right_i : held_pcm_right),
        .sample_valid_o(core_valid),.left_o(core_left),.right_o(core_right),
        .synth_valid_o(),.synth_o(),
        .held_notes_o,.applied_events_o,.pc_overflow_o,.control_options_o,
        .panic_epoch_o,.panic_muted_o,.render_idle_o(core_idle),
        .rate_commit_i(core_config),.rate_44100_i(requested_rate),
        .rate_ready_o(core_rate_ready),.applied_rate_44100_o(core_rate),
        .rate_applied_o(core_rate_applied),.rate_busy_o(core_rate_busy),.rate_fault_o(core_fault),
        .history_clear_i(external_history),.history_ready_o(core_history_ready),.history_done_o(core_history_done),
        .delay_peer_heartbeat_i,.delay_dma_fault_i,.delay_heartbeat_o,
        .active_mask_o,.active_voice_count_o,.mode_o,.pitch_q20_o,
        .deadline_miss_o,.midi_overflow_o,.note_drop_o,.clip_o,
        .synth_gain_o,.pcm_gain_o,.master_volume_o,.route_o,.profile_o,
        .effect_mask_o,.effect_order_o,.effect_state_o,.panel_event_valid_o,.panel_command_o,
        .scope_status_o,.tf_scope_control_o,
        .delay_mem_clk_i,.delay_mem_rst_ni,.delay_dwr_valid_o,.delay_dwr_data_o,
        .delay_dwr_pop_i,.delay_drd_push_i,.delay_drd_data_i,.delay_drd_ready_o);

    workstation_frame_delivery #(.REQUEST_EPOCH_SNAPSHOT(RUNTIME_EFFECTS_ENABLE)) delivery(
        .clk_i,.rst_ni,.sample_ce_i(sample_ce_o),
        // Native intentional silence still waits real core completion. This
        // also prevents returning a new-rate good frame before config ACK.
        .muted_i(RUNTIME_EFFECTS_ENABLE ? 1'b0 : panic_muted_o),
        .cancel_epoch_i(panic_epoch_o),.render_valid_i(core_valid),
        .left_i(core_left),.right_i(core_right),.reference_i(32'd0),.voices_i(active_mask_o),
        .valid_o(delivery_valid),.left_o(delivery_left),.right_o(delivery_right),
        .reference_o(),.voices_o(),.duplicate_frames_o(delivery_duplicate_count_o));

    always @(posedge clk_i or negedge rst_ni) begin
        if(!rst_ni) begin
            active<=0;response_sent<=0;request_cancel_epoch<=0;held_rate<=0;external_busy<=0;request_muted<=0;
            held_pcm_left<=0;held_pcm_right<=0;
            render_done_o<=0;render_error_o<=0;render_left_o<=0;render_right_o<=0;
            rejected_request_count_o<=0;unsupported_rate_count_o<=0;
            cancelled_response_count_o<=0;drained_result_count_o<=0;
        end else begin
            render_done_o<=0;
            if(RUNTIME_EFFECTS_ENABLE)begin
                if((external_config && core_rate_ready) || (external_history && core_history_ready))external_busy<=1;
                else if(core_history_done && !core_rate_busy)external_busy<=0;
            end
            if(render_request_i && !render_ready_o)
                rejected_request_count_o<=increment(rejected_request_count_o);
            if(accepted) begin
                active<=1;response_sent<=0;
                request_cancel_epoch<=panic_epoch_o;held_rate<=render_44k1_i;request_muted<=panic_muted_o;
                held_pcm_left<=pcm_left_i;held_pcm_right<=pcm_right_i;
                if(render_44k1_i && !RUNTIME_EFFECTS_ENABLE) begin
                    // Explicit unsupported response; never relabel 48-kHz DSP.
                    unsupported_rate_count_o<=increment(unsupported_rate_count_o);
                    render_done_o<=1;render_error_o<=1;render_left_o<=0;render_right_o<=0;
                    response_sent<=1;
                end
            end
            if((active || accepted) && (!response_sent || accepted) &&
               delivery_valid && !(accepted && render_44k1_i && !RUNTIME_EFFECTS_ENABLE) && !core_fault) begin
                render_done_o<=1;render_error_o<=cancelled;
                render_left_o<=RUNTIME_EFFECTS_ENABLE && request_muted ? 32'sd0 : delivery_left;
                render_right_o<=RUNTIME_EFFECTS_ENABLE && request_muted ? 32'sd0 : delivery_right;
                response_sent<=1;
                if(cancelled) cancelled_response_count_o<=increment(cancelled_response_count_o);
            end
            if(RUNTIME_EFFECTS_ENABLE && core_fault && active && !response_sent)begin
                render_done_o<=1;render_error_o<=1;render_left_o<=0;render_right_o<=0;response_sent<=1;
            end
            // Returning an explicit cancellation zero is not engine-idle.
            // Retain the transaction until every old render tail has drained.
            if(active && response_sent && core_idle) active<=0;
            if(active && response_sent && core_valid)
                drained_result_count_o<=increment(drained_result_count_o);
        end
    end
endmodule
