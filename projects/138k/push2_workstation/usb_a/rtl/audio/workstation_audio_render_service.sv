`timescale 1ns/1ps

// 48-kHz synth/vector render service in the always-running compute domain.
// Source selection and final master-volume processing remain downstream.
// No output-clock divider, autonomous sample tick, or second parameter owner.
module workstation_audio_render_service #(
    parameter bit RUNTIME_RATE_ENABLE=0,
    parameter integer DELAY_BITS=14,
    parameter integer ECHO_SAMPLES=9600
) (
    input wire clk_i,rst_ni,
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
    reg [9:0] request_cancel_epoch;
    reg signed [31:0] held_pcm_left,held_pcm_right;
    wire core_idle,core_valid,delivery_valid;
    wire signed [31:0] core_left,core_right,delivery_left,delivery_right;
    wire accepted=render_request_i && render_ready_o;
    // Ready promises this one request slot. Register the sample immediately:
    // the existing workstation pending bit gives it priority over new events.
    assign render_ready_o=rst_ni && !active;
    assign render_busy_o=active;
    assign sample_ce_o=accepted && !render_44k1_i;
    wire cancelled=panic_muted_o || panic_epoch_o!=request_cancel_epoch;

    function automatic [31:0] increment(input [31:0] value);
        increment=&value ? value : value+1'b1;
    endfunction

    gw138k_event_workstation #(.SAMPLE_RATE_HZ(48000),.TIMING_OPTIMIZED(1),
        .EXTERNAL_MASTER_VOLUME(1),.REQUEST_DRIVEN_RENDER(1),
        .RUNTIME_RATE_ENABLE(RUNTIME_RATE_ENABLE),
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
        .rate_commit_i(1'b0),.rate_44100_i(1'b0),
        .rate_ready_o(),.applied_rate_44100_o(),
        .active_mask_o,.active_voice_count_o,.mode_o,.pitch_q20_o,
        .deadline_miss_o,.midi_overflow_o,.note_drop_o,.clip_o,
        .synth_gain_o,.pcm_gain_o,.master_volume_o,.route_o,.profile_o,
        .effect_mask_o,.effect_order_o,.panel_event_valid_o,.panel_command_o,
        .scope_status_o,.tf_scope_control_o,
        .delay_mem_clk_i,.delay_mem_rst_ni,.delay_dwr_valid_o,.delay_dwr_data_o,
        .delay_dwr_pop_i,.delay_drd_push_i,.delay_drd_data_i,.delay_drd_ready_o);

    workstation_frame_delivery delivery(
        .clk_i,.rst_ni,.sample_ce_i(sample_ce_o),.muted_i(panic_muted_o),
        .cancel_epoch_i(panic_epoch_o),.render_valid_i(core_valid),
        .left_i(core_left),.right_i(core_right),.reference_i(32'd0),.voices_i(active_mask_o),
        .valid_o(delivery_valid),.left_o(delivery_left),.right_o(delivery_right),
        .reference_o(),.voices_o(),.duplicate_frames_o(delivery_duplicate_count_o));

    always @(posedge clk_i or negedge rst_ni) begin
        if(!rst_ni) begin
            active<=0;response_sent<=0;request_cancel_epoch<=0;
            held_pcm_left<=0;held_pcm_right<=0;
            render_done_o<=0;render_error_o<=0;render_left_o<=0;render_right_o<=0;
            rejected_request_count_o<=0;unsupported_rate_count_o<=0;
            cancelled_response_count_o<=0;drained_result_count_o<=0;
        end else begin
            render_done_o<=0;
            if(render_request_i && !render_ready_o)
                rejected_request_count_o<=increment(rejected_request_count_o);
            if(accepted) begin
                active<=1;response_sent<=0;
                request_cancel_epoch<=panic_epoch_o;
                held_pcm_left<=pcm_left_i;held_pcm_right<=pcm_right_i;
                if(render_44k1_i) begin
                    // Explicit unsupported response; never relabel 48-kHz DSP.
                    unsupported_rate_count_o<=increment(unsupported_rate_count_o);
                    render_done_o<=1;render_error_o<=1;render_left_o<=0;render_right_o<=0;
                    response_sent<=1;
                end
            end
            if((active || accepted) && (!response_sent || accepted) &&
               delivery_valid && !(accepted && render_44k1_i)) begin
                render_done_o<=1;render_error_o<=cancelled;
                render_left_o<=delivery_left;render_right_o<=delivery_right;
                response_sent<=1;
                if(cancelled) cancelled_response_count_o<=increment(cancelled_response_count_o);
            end
            // Returning an explicit cancellation zero is not engine-idle.
            // Retain the transaction until every old render tail has drained.
            if(active && response_sent && core_idle) active<=0;
            if(active && response_sent && core_valid)
                drained_result_count_o<=increment(drained_result_count_o);
        end
    end
endmodule
