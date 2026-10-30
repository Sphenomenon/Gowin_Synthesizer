`timescale 1ns/1ps

// Opt-in CPU/UART/USB composition for the native dual-clock runtime.
// No accepted top/profile selects this module. runtime.service is the ONLY
// event/session/parameter owner; preset_n resets CPU services only.
module workstation_runtime_controlled #(
    parameter integer WINDOW_CYCLES=50000,STABLE_WINDOWS=4,TOLERANCE_PPM=2000,
    parameter integer LOSS_TIMEOUT_CYCLES=500,STOP_LOW_CYCLES=16,COUNTER_BITS=32,
    parameter integer SWITCH_TIMEOUT_CYCLES=2000000,
    parameter integer PDN_HOLD_FRAMES=4,STARTUP_MUTE_FRAMES=1028,
    parameter integer DMA_TIMEOUT_CYCLES=1048576,RECORD_ADDRESS_BITS=8,
    parameter bit RESERVE_ZERO_EPOCH=0,
    parameter [31:0] INITIAL_STREAM_EPOCH=RESERVE_ZERO_EPOCH ? 32'd1 : 32'd0,
    parameter bit ENABLE_MEDIA_POLICY=0
) (
    input wire rst_ni,clk_50m_i,compute_clk_i,memory_clk_i,
    input wire reference_48_i,reference_44_i,midi_rx_i,pc_uart_rx_i,
    input wire usb_event_valid,usb_lifecycle,usb_cancel,
    input wire [17:0] usb_event_data,
    output wire usb_event_ready,
    input wire pclk,preset_n,psel,penable,pwrite,
    input wire [11:0] paddr,
    input wire [31:0] pwdata,
    input wire [3:0] pstrb,
    output wire pready,pslverr,
    output wire [31:0] prdata,
    output wire [447:0] performance_words_o,
    // All external switch controls remain in the continuous 50-MHz domain.
    input wire request_i,request_44k1_i,switch_permit_i,recover_i,media_quiescent_i,
    output wire request_ready_o,busy_o,fault_o,accepted_o,applied_o,rejected_o,failed_o,
    output wire policy_rejected_o,
    output wire [2:0] reject_code_o,
    output wire [3:0] fault_code_o,clock_select_o,
    // Diagnostic busy reasons: bit0 caller permit, bit1 REC, bit2 score, bit3 TF.
    output wire [3:0] switch_block_reason_o,
    output wire active_44k1_o,active_valid_o,
    output wire [31:0] stream_epoch_o,
    output wire [1:0] source_qualified_o,
    output wire quiesce_o,stream_flush_o,dsp_fault_o,context_ready_o,
    input wire signed [31:0] pcm_left_i,pcm_right_i,
    input wire output_mute_i,
    // Atomic compute-domain TF packet. tf_busy also includes file-side work.
    input wire tf_active_i,tf_busy_i,tf_valid_i,tf_error_i,
    input wire signed [15:0] tf_left_i,tf_right_i,
    input wire [19:0] tf_sample_rate_i,
    input wire [31:0] tf_generation_i,expected_tf_generation_i,
    output wire tf_ready_o,
    // Direct owner-6 channel from runtime.delay_dma; no second delay DMA.
    output wire ddr_req_o,ddr_write_o,
    output wire [28:0] ddr_address_o,
    output wire [255:0] ddr_data_o,
    output wire [31:0] ddr_mask_o,
    input wire ddr_ready_i,ddr_response_i,
    input wire [255:0] ddr_read_data_i,
    output wire mclk_o,bck_o,lrck_o,data_o,pdn_no,smute_o,
    // Selected-MCLK physical frame context, before observation CDC.
    output wire frame_valid_o,frame_error_o,frame_44k1_o,
    output wire [31:0] frame_epoch_o,frame_sequence_o,frame_pcm_o,
    // Continuous compute-domain state and physical-frame observations.
    output wire [127:0] held_notes_o,
    output wire [31:0] control_state_o,control_pitch_o,control_options_o,applied_events_o,pc_health_o,
    output wire [15:0] master_volume_o,
    output wire [31:0] active_mask_o,scope_status_o,tf_scope_control_o,
    output wire [31:0] deadline_miss_o,midi_overflow_o,note_drop_o,
    output wire [31:0] underrun_count_o,midi_cdc_drop_o,observation_drop_o,record_drop_o,
    output wire uart_error_o,sample_valid_o,
    output wire signed [31:0] audio_left_o,audio_right_o,
    output wire record_enabled_o,record_failed_o,
    output wire [2:0] record_failure_code_o,
    output wire score_running_o,score_done_o,score_failed_o,
    output wire [31:0] led_mask_o,score_frame_o,
    output wire fft_valid_o,
    output wire [7:0] fft_bin_o,
    output wire signed [23:0] fft_real_o,fft_imag_o,
    output wire [31:0] fft_frame_o,fft_discard_count_o,
    output wire fft_44k1_o,fft_context_valid_o,
    output wire [31:0] fft_epoch_o,
    // Atomic tuple in 50 MHz; reference/voices/health/effects sampled at
    // observation. All fields, including effects, are valid only with valid.
    output wire display_valid_o,
    output wire [31:0] display_pcm_o,display_reference_o,display_voices_o,display_status_o,
    output wire display_44k1_o,display_error_o,
    output wire [31:0] display_epoch_o,display_sequence_o,
    output wire [2:0] effect_mask_o,
    output wire [5:0] effect_order_o,
    // Display-only, 50MHz sticky fault. Only rst_ni clears observation loss;
    // preset, rate switch and serializer resets never rearm this path.
    output wire display_observation_fault_o,
    input wire media_stop_request_i,media_stop_hold_i,
    output wire media_stop_ready_o,media_stop_done_o,media_stop_failed_o,
    output wire [3:0] media_stop_failure_code_o,
    output wire tf_stop_request_o,
    input wire tf_stop_pending_i,tf_stop_done_i,tf_stop_failed_i,
    input wire [3:0] tf_stop_failure_code_i
);
    (* ASYNC_REG="TRUE",syn_preserve=1 *) reg [2:0] reset_50_pipe,reset_compute_pipe;
    always @(posedge clk_50m_i or negedge rst_ni)
        if(!rst_ni)reset_50_pipe<=0;else reset_50_pipe<={reset_50_pipe[1:0],1'b1};
    always @(posedge compute_clk_i or negedge rst_ni)
        if(!rst_ni)reset_compute_pipe<=0;else reset_compute_pipe<={reset_compute_pipe[1:0],1'b1};
    wire reset_50_n=reset_50_pipe[2],reset_compute_n=reset_compute_pipe[2];
    wire midi_valid_50,midi_valid_compute,pc_valid_50,pc_valid_compute,pc_frame_error;
    wire [7:0] midi_byte_50,midi_byte_compute,pc_byte_50,pc_byte_compute;
    wire [31:0] pc_drop,pc_overflow,midi_drop_compute;
    uart_rx #(.CLOCK_HZ(50000000),.BAUD(31250)) midi_uart(
        .clk_i(clk_50m_i),.rst_ni(reset_50_n),.rx_i(midi_rx_i),
        .valid_o(midi_valid_50),.data_o(midi_byte_50),.framing_error_o(uart_error_o));
    uart_rx #(.CLOCK_HZ(50000000),.BAUD(115200)) pc_uart(
        .clk_i(clk_50m_i),.rst_ni(reset_50_n),.rx_i(pc_uart_rx_i),
        .valid_o(pc_valid_50),.data_o(pc_byte_50),.framing_error_o(pc_frame_error));
    gw138k_stream_cdc #(.WIDTH(8)) midi_bytes(
        .reset_n(rst_ni),.source_clk(clk_50m_i),.destination_clk(compute_clk_i),
        .source_valid(midi_valid_50),.source_data(midi_byte_50),.drop_count(midi_cdc_drop_o),
        .destination_valid(midi_valid_compute),.destination_data(midi_byte_compute));
    gw138k_stream_cdc #(.WIDTH(8)) pc_bytes(
        .reset_n(rst_ni),.source_clk(clk_50m_i),.destination_clk(compute_clk_i),
        .source_valid(pc_valid_50),.source_data(pc_byte_50),.drop_count(pc_drop),
        .destination_valid(pc_valid_compute),.destination_data(pc_byte_compute));
    gw138k_counter_cdc midi_drops(
        .reset_n(rst_ni),.source_clk(clk_50m_i),.destination_clk(compute_clk_i),
        .source_count(midi_cdc_drop_o),.destination_count(midi_drop_compute));
    reg pc_framing_sticky;
    // A binary drop counter can change several bits on a carry. Register its
    // diagnostic reduction before crossing; do not synchronize a LUT decode.
    (* syn_preserve=1 *) reg pc_drop_seen_50;
    always @(posedge clk_50m_i or negedge reset_50_n)
        if(!reset_50_n)pc_framing_sticky<=0;else if(pc_frame_error)pc_framing_sticky<=1;
    always @(posedge clk_50m_i or negedge reset_50_n)
        if(!reset_50_n)pc_drop_seen_50<=0;else pc_drop_seen_50<=pc_drop!=0;
    (* ASYNC_REG="TRUE" *) reg [1:0] pc_health_meta,pc_health_sync;
    always @(posedge compute_clk_i or negedge reset_compute_n)
        if(!reset_compute_n)begin pc_health_meta<=0;pc_health_sync<=0;end
        else begin pc_health_meta<={pc_drop_seen_50,pc_framing_sticky};pc_health_sync<=pc_health_meta;end
    assign pc_health_o={29'd0,pc_overflow!=0,pc_health_sync};

    wire command_reset_n,command_valid,command_ready,command_write,response_error;
    wire [11:0] command_address;
    wire [31:0] command_data,response_data;
    wire [3:0] command_strobes;
    // Pinned APB CDC captures held payload then gives service predecode a cycle.
    gw138k_apb_cdc control_cdc(
        .reset_n(rst_ni && preset_n),.pclk,.audio_clk(compute_clk_i),
        .psel,.penable,.pwrite,.paddr,.pwdata,.pstrb,.pready,.pslverr,.prdata,
        .command_reset_n,.command_valid,.command_ready,.command_write,.command_address,
        .command_data,.command_strobes,.response_data,.response_error);
    wire cpu_event_valid,cpu_event_ready,merged_valid,merged_ready;
    wire [17:0] cpu_event,merged_data;
    wire panel_event_valid,panel_event_ready;
    wire [6:0] panel_command;
    wire record_valid,record_ready,score_write,score_start,score_stop;
    wire [95:0] record_packet;
    wire [7:0] score_address;
    wire [63:0] score_data;
    wire [8:0] score_length;
    wire [31:0] snap_status,snap_left,snap_right,snap_sequence,underrun_compute;
    wire local_stop_request,local_stop_hold,local_stop_done,local_stop_failed;
    wire record_seal_request,record_seal_done,record_seal_failed,record_start_ready,score_cancelled;
    wire [31:0] record_object_id,record_object_rate,record_object_epoch,record_object_frames,record_seal_count;
    wire [5:0] record_object_status;
    wire [2:0] record_object_failure,record_seal_status;
    // Original 448-bit performance layout is byte-for-byte unchanged.
    assign performance_words_o={32'h43545231,snap_sequence,snap_right,snap_left,snap_status,
        control_pitch_o,control_options_o,held_notes_o,pc_health_o,control_state_o,applied_events_o};
    gw138k_controlled_services #(.ENABLE_MEDIA_POLICY(ENABLE_MEDIA_POLICY)) services(
        .clk(compute_clk_i),.reset_n(command_reset_n),.command_valid,.command_write,.command_address,
        .command_data,.command_strobes,.command_ready,.response_data,.response_error,
        .cpu_event_valid,.cpu_event,.cpu_event_ready,.panel_event_valid,.panel_command,.panel_event_ready,
        .control_state(control_state_o),.control_pitch(control_pitch_o),.control_options(control_options_o),
        .applied_events(applied_events_o),.pc_health(pc_health_o),.held_notes(held_notes_o),
        .sample_valid(sample_valid_o),.active_mask(active_mask_o),.deadline_miss(deadline_miss_o),
        .midi_overflow(midi_overflow_o),.note_drop(note_drop_o),.underrun_count(underrun_compute),
        .midi_cdc_drop(midi_drop_compute),.observation_drop(observation_drop_o),.record_drop(record_drop_o),
        .record_enable(record_enabled_o),.snap_status,.snap_left,.snap_right,.snap_sequence,
        .record_valid,.record_packet,.record_ready,.score_write,.score_start,.score_stop,.score_address,.score_data,
        .score_length,.score_running(score_running_o),.score_done(score_done_o),.led_mask(led_mask_o),.score_frame(score_frame_o),
        .media_stop_request_i(local_stop_request),.media_stop_hold_i(local_stop_hold),
        .record_storage_reset_ni(reset_compute_n),.record_seal_request_o(record_seal_request),
        .record_seal_done_i(record_seal_done),.record_seal_failed_i(record_seal_failed),.record_start_ready_i(record_start_ready),
        .record_object_id_i(record_object_id),.record_object_rate_i(record_object_rate),.record_object_epoch_i(record_object_epoch),
        .record_object_frames_i(record_object_frames),.record_object_status_i(record_object_status),
        .record_object_failure_i(record_object_failure),.record_seal_status_i(record_seal_status),.record_seal_count_i(record_seal_count),
        .score_cancelled_i(score_cancelled),.score_failed_i(score_failed_o),
        .media_stop_done_o(local_stop_done),.media_stop_failed_o(local_stop_failed));
    gw138k_usb_lifecycle_merge #(.EXPLICIT_LIFECYCLE(1)) events(
        .clk(compute_clk_i),.reset_n(reset_compute_n),.g1_valid(usb_event_valid),
        .g1_lifecycle(usb_lifecycle),.g1_cancel(usb_cancel),.g1_data(usb_event_data),.g1_ready(usb_event_ready),
        .pc_valid(cpu_event_valid),.pc_data(cpu_event),.pc_ready(cpu_event_ready),
        .cpu_valid(1'b0),.cpu_data(18'd0),.cpu_ready(),.event_valid(merged_valid),
        .event_ready(merged_ready),.event_data(merged_data));

    // Register the combined proof before crossing. Assertion inhibits without
    // waiting for a 50-MHz edge; release requires three destination edges.
    reg media_busy_compute;
    // Independent diagnostic reasons, sampled together in their source
    // domain. They never authorize a switch; media_busy_compute does that.
    (* syn_preserve=1 *) reg [2:0] reasons_compute;
    (* ASYNC_REG="TRUE",syn_preserve=1 *) reg [2:0] media_busy_50;
    (* ASYNC_REG="TRUE" *) reg [2:0] reasons_meta,reasons_sync;
    always @(posedge compute_clk_i or negedge reset_compute_n)
        if(!reset_compute_n)media_busy_compute<=1;
        else media_busy_compute<=record_enabled_o || score_running_o || tf_active_i || tf_busy_i;
    always @(posedge compute_clk_i or negedge reset_compute_n)
        if(!reset_compute_n)reasons_compute<=0;
        else reasons_compute<={tf_active_i || tf_busy_i,score_running_o,record_enabled_o};
    always @(posedge clk_50m_i or posedge media_busy_compute or negedge rst_ni)
        if(!rst_ni)media_busy_50<=3'b111;
        else if(media_busy_compute)media_busy_50<=3'b111;
        else media_busy_50<={media_busy_50[1:0],1'b0};
    always @(posedge clk_50m_i or negedge reset_50_n)
        if(!reset_50_n)begin reasons_meta<=0;reasons_sync<=0;end
        else begin reasons_meta<=reasons_compute;reasons_sync<=reasons_meta;end
    assign switch_block_reason_o={reasons_sync,!switch_permit_i};
    wire qualified_permit=switch_permit_i && !media_busy_50[2];
    workstation_runtime_media_stop_bridge #(.ENABLE(ENABLE_MEDIA_POLICY)) media_stop(
        .reset_ni(rst_ni),.clk_50m_i,.compute_clk_i,.owner_reset_ni(command_reset_n),
        .request_i(media_stop_request_i),.hold_i(media_stop_hold_i),
        .local_request_o(local_stop_request),.local_hold_o(local_stop_hold),
        .local_done_i(local_stop_done),.local_failed_i(local_stop_failed),
        .tf_stop_request_o,.tf_stop_pending_i,.tf_stop_done_i,.tf_stop_failed_i,.tf_stop_failure_code_i,
        .media_quiet_i(!media_busy_50[2] && media_quiescent_i),
        .ready_o(media_stop_ready_o),.done_o(media_stop_done_o),.failed_o(media_stop_failed_o),.failure_code_o(media_stop_failure_code_o));
    wire [5:0] voices,effect_order_compute;
    wire [1:0] mode,route;
    wire [2:0] profile,effect_mask_compute;
    wire [9:0] panic_epoch;
    wire [21:0] pitch;
    wire [31:0] source_errors;
    assign control_state_o={master_volume_o,voices,profile,route,mode,effect_mask_compute};
    assign control_pitch_o={panic_epoch,pitch};
    workstation_runtime_audio #(
        .WINDOW_CYCLES(WINDOW_CYCLES),.STABLE_WINDOWS(STABLE_WINDOWS),.TOLERANCE_PPM(TOLERANCE_PPM),
        .LOSS_TIMEOUT_CYCLES(LOSS_TIMEOUT_CYCLES),.STOP_LOW_CYCLES(STOP_LOW_CYCLES),.COUNTER_BITS(COUNTER_BITS),
        .SWITCH_TIMEOUT_CYCLES(SWITCH_TIMEOUT_CYCLES),.PDN_HOLD_FRAMES(PDN_HOLD_FRAMES),
        .STARTUP_MUTE_FRAMES(STARTUP_MUTE_FRAMES),.DMA_TIMEOUT_CYCLES(DMA_TIMEOUT_CYCLES),
        .RESERVE_ZERO_EPOCH(RESERVE_ZERO_EPOCH),.INITIAL_STREAM_EPOCH(INITIAL_STREAM_EPOCH)
    ) runtime(
        .rst_ni,.clk_50m_i,.compute_clk_i,.memory_clk_i,.reference_48_i,.reference_44_i,
        .request_i,.request_44k1_i,.switch_permit_i(qualified_permit),.recover_i,.media_quiescent_i,
        .request_ready_o,.busy_o,.fault_o,.accepted_o,.applied_o,.rejected_o,.failed_o,.policy_rejected_o,
        .reject_code_o,.fault_code_o,.clock_select_o,.active_44k1_o,.active_valid_o,.stream_epoch_o,
        .source_qualified_o,.quiesce_o,.stream_flush_o,.dsp_fault_o,.context_ready_o,
        .midi_byte_valid_i(midi_valid_compute),.midi_byte_i(midi_byte_compute),
        .pc_byte_valid_i(pc_valid_compute),.pc_byte_i(pc_byte_compute),
        .cpu_event_valid_i(merged_valid),.cpu_event_i(merged_data),.cpu_event_ready_o(merged_ready),
        .pcm_left_i,.pcm_right_i,.output_mute_i,.held_notes_o,.panic_epoch_o(panic_epoch),.panic_muted_o(),
        .active_mask_o,.scope_status_o,.tf_scope_control_o,.applied_events_o,.control_options_o,
        .active_voice_count_o(voices),.mode_o(mode),.master_volume_o,.pitch_q20_o(pitch),
        .pc_overflow_o(pc_overflow),.deadline_miss_o,.midi_overflow_o,.note_drop_o,.clip_o(),
        .synth_gain_o(),.pcm_gain_o(),.route_o(route),.profile_o(profile),
        .effect_mask_o(effect_mask_compute),.effect_order_o(effect_order_compute),
        .panel_event_valid_o(panel_event_valid),.panel_command_o(panel_command),
        .tf_active_i,.tf_valid_i,.tf_error_i,.tf_left_i,.tf_right_i,.tf_sample_rate_i,
        .tf_generation_i,.expected_tf_generation_i,.tf_ready_o,
        .ddr_req_o,.ddr_write_o,.ddr_address_o,.ddr_data_o,.ddr_mask_o,.ddr_ready_i,.ddr_response_i,.ddr_read_data_i,
        .mclk_o,.bck_o,.lrck_o,.data_o,.pdn_no,.smute_o,
        .analysis_enable_i(1'b0),.analysis_ready_i(1'b1),.record_enable_i(1'b0),.record_ready_i(1'b1),
        .analysis_valid_o(),.record_valid_o(),.frame_valid_o,.frame_error_o,.frame_44k1_o,
        .frame_epoch_o,.frame_sequence_o,.frame_pcm_o,.stream_change_o(),.sequence_gap_o(),
        .analysis_gap_o(),.record_fault_o(),.analysis_drop_count_o(),.record_drop_count_o(),
        .underrun_count_o,.source_error_count_o(source_errors),
        .bridge_request_drop_count_o(),.bridge_return_discard_count_o());

    wire observed_valid,observed_rate,observed_error,observed_change,observed_gap,observation_loss;
    wire [31:0] observed_epoch,observed_sequence,observed_pcm,observation_source_drop;
    workstation_pcm_observation_bridge observation(
        .reset_ni(rst_ni),.source_clk_i(mclk_o),.destination_clk_i(compute_clk_i),
        .frame_valid_i(frame_valid_o),.frame_44k1_i(frame_44k1_o),.frame_error_i(frame_error_o),
        .frame_epoch_i(frame_epoch_o),.frame_sequence_i(frame_sequence_o),.frame_pcm_i(frame_pcm_o),
        .source_drop_count_o(observation_source_drop),.destination_drop_count_o(observation_drop_o),
        .destination_drop_event_o(observation_loss),.destination_loss_seen_o(),
        .frame_valid_o(observed_valid),.frame_ready_i(1'b1),.frame_44k1_o(observed_rate),.frame_error_o(observed_error),
        .frame_epoch_o(observed_epoch),.frame_sequence_o(observed_sequence),.frame_pcm_o(observed_pcm),
        .left_q31_o(audio_left_o),.right_q31_o(audio_right_o),
        .stream_change_o(observed_change),.sequence_gap_o(observed_gap));
    assign sample_valid_o=observed_valid;
    // Both public levels decode the clock owner's multibit state. Capture
    // their union on 50 MHz. Assertion from this source flop must inhibit
    // immediately: another two compute capture edges can let an in-flight
    // frame-zero score finish before its failure is latched. Release alone
    // waits for two compute edges. The public clock-owner levels are unchanged.
    (* syn_preserve=1 *) reg switch_busy_50;
    always @(posedge clk_50m_i or negedge reset_50_n)
        if(!reset_50_n)switch_busy_50<=1;
        else switch_busy_50<=busy_o || quiesce_o;
    (* ASYNC_REG="TRUE",syn_preserve=1 *) reg [1:0] switch_busy_compute;
    always @(posedge compute_clk_i or posedge switch_busy_50 or negedge reset_compute_n)
        if(!reset_compute_n)switch_busy_compute<=2'b11;
        else if(switch_busy_50)switch_busy_compute<=2'b11;
        else switch_busy_compute<={switch_busy_compute[0],1'b0};
    // Serializer counters reset per stream; a jump N->0 is NOT a unit-step
    // Gray counter. Sample the complete epoch-tagged health tuple instead.
    // APB/display see the last completed-frame snapshot, never a torn count.
    wire health_valid;
    wire [31:0] health_epoch,source_errors_compute,health_drop;
    gw138k_stream_cdc #(.WIDTH(96)) health_snapshot(
        .reset_n(rst_ni),.source_clk(mclk_o),.destination_clk(compute_clk_i),
        .source_valid(frame_valid_o),.source_data({frame_epoch_o,underrun_count_o,source_errors}),
        .drop_count(health_drop),.destination_valid(health_valid),
        .destination_data({health_epoch,underrun_compute,source_errors_compute}));
    workstation_observation_consumers #(.RECORD_ADDRESS_BITS(RECORD_ADDRESS_BITS),.ENABLE_MEDIA_POLICY(ENABLE_MEDIA_POLICY)) consumers(
        .clk_i(compute_clk_i),.rst_ni(reset_compute_n),.frame_valid_i(observed_valid),
        .frame_44k1_i(observed_rate),.frame_error_i(observed_error),.stream_change_i(observed_change),
        .sequence_gap_i(observed_gap),
        .observation_loss_i(observation_loss || observation_drop_o==32'hffff_ffff),
        .media_switch_busy_i(switch_busy_compute[1]),.frame_epoch_i(observed_epoch),
        .left_i(audio_left_o),.right_i(audio_right_o),
        .record_enable_i(record_enabled_o),.record_ready_i(record_ready),.record_valid_o(record_valid),
        .record_packet_o(record_packet),.record_failed_o,.record_failure_code_o,.record_drop_o,
        .fft_valid_o,.fft_bin_o,.fft_real_o,.fft_imag_o,.fft_frame_o,.fft_discard_count_o,
        .fft_44k1_o,.fft_context_valid_o,.fft_epoch_o,
        .score_write_i(score_write),.score_address_i(score_address),.score_data_i(score_data),
        .score_length_i(score_length),.score_start_i(score_start),.score_stop_i(score_stop),
        .score_running_o,.score_done_o,.led_mask_o,.score_frame_o,.score_failed_o,
        .record_seal_i(record_seal_request),.record_seal_done_o(record_seal_done),.record_seal_failed_o(record_seal_failed),
        .record_start_ready_o(record_start_ready),.record_object_id_o(record_object_id),.record_object_rate_o(record_object_rate),
        .record_object_epoch_o(record_object_epoch),.record_object_frames_o(record_object_frames),
        .record_object_status_o(record_object_status),.record_object_failure_o(record_object_failure),
        .record_seal_status_o(record_seal_status),.record_seal_count_o(record_seal_count),.score_cancelled_o(score_cancelled));
    reg [23:0] revision;
    always @(posedge compute_clk_i or negedge reset_compute_n)
        if(!reset_compute_n)revision<=0;
        else if(midi_valid_compute || pc_valid_compute || (merged_valid && merged_ready))revision<=revision+1'b1;
    wire [31:0] display_drop;
    wire [31:0] core_faults=deadline_miss_o+midi_overflow_o+note_drop_o;
    gw138k_stream_cdc #(.WIDTH(203)) display(
        .reset_n(rst_ni),.source_clk(compute_clk_i),.destination_clk(clk_50m_i),
        .source_valid(observed_valid),
        .source_data({observed_rate,observed_epoch,observed_sequence,observed_error,
            observed_pcm,revision,8'd0,active_mask_o,underrun_compute[15:0],core_faults[15:0],
            effect_mask_compute,effect_order_compute}),
        .drop_count(display_drop),.destination_valid(display_valid_o),
        .destination_data({display_44k1_o,display_epoch_o,display_sequence_o,display_error_o,
            display_pcm_o,display_reference_o,display_voices_o,display_status_o,effect_mask_o,effect_order_o}));
    workstation_display_observation_health display_observation_health(
        .reset_ni(rst_ni),.compute_clk_i(compute_clk_i),.clk_50m_i(clk_50m_i),
        .physical_observation_drop_i(observation_drop_o),.display_mailbox_drop_i(display_drop),
        .fault_50_o(display_observation_fault_o));
endmodule

// The physical count has ALREADY crossed from selected MCLK into compute and
// may jump by several drops. Never Gray-encode that decoded count a second time.
// Each source becomes one sticky bit, independently synchronized to 50MHz.
module workstation_display_observation_health (
    input wire reset_ni,compute_clk_i,clk_50m_i,
    input wire [31:0] physical_observation_drop_i,display_mailbox_drop_i,
    output reg fault_50_o
);
    wire [1:0] nonzero={display_mailbox_drop_i!=0,physical_observation_drop_i!=0};
    reg [1:0] source_sticky;
    always @(posedge compute_clk_i or negedge reset_ni)
        if(!reset_ni)source_sticky<=0;else source_sticky<=source_sticky | nonzero;
    // On the edge of the first drop, the producer counter changes after this
    // observer's sampling edge. If compute stops right there, current nonzero
    // still raises the held level without needing another compute edge. Once
    // source_sticky is set, later counter wrap cannot lower that level.
    wire [1:0] loss_level=source_sticky | nonzero;
    (* ASYNC_REG="TRUE",syn_preserve=1 *) reg [1:0] loss_meta,loss_sync;
    always @(posedge clk_50m_i or negedge reset_ni)begin
        if(!reset_ni)begin loss_meta<=0;loss_sync<=0;fault_50_o<=0;end
        else begin
            loss_meta<=loss_level;loss_sync<=loss_meta;
            if(|loss_sync)fault_50_o<=1;
        end
    end
endmodule

// Readiness/CDC composition only. REC_ENABLE and cue stop remain owned by the
// compute services, TF stop/drain remains owned by the TF service. A request is
// a four-phase held transaction, never an asynchronous one-cycle pulse crossing.
module workstation_runtime_media_stop_bridge #(parameter bit ENABLE=0) (
    input wire reset_ni,clk_50m_i,compute_clk_i,owner_reset_ni,
    input wire request_i,hold_i,
    output reg local_request_o,
    output wire local_hold_o,
    input wire local_done_i,local_failed_i,
    output reg tf_stop_request_o,
    input wire tf_stop_pending_i,tf_stop_done_i,tf_stop_failed_i,
    input wire [3:0] tf_stop_failure_code_i,
    input wire media_quiet_i,
    output wire ready_o,
    output reg done_o,failed_o,
    output reg [3:0] failure_code_o
);
    localparam [1:0] IDLE=0,LOCAL=1,TF=2,QUIET=3;
    reg [1:0] state;
    reg hold_50,request_toggle,acknowledge_seen,local_failure;
    (* ASYNC_REG="TRUE",syn_preserve=1 *) reg [1:0] request_compute,hold_compute;
    (* ASYNC_REG="TRUE",syn_preserve=1 *) reg [2:0] acknowledge_50;
    (* ASYNC_REG="TRUE" *) reg [1:0] failed_50;
    reg request_seen,compute_pending,compute_sent,acknowledge_toggle,compute_failure;
    assign local_hold_o=ENABLE && hold_compute[1];
    assign ready_o=ENABLE && state==IDLE && !hold_50 && !tf_stop_pending_i;
    // Assertion fences new starts immediately. Release waits for two compute
    // edges and is allowed only after the actual backend transaction ends.
    always @(posedge compute_clk_i or posedge hold_50 or negedge reset_ni)
        if(!reset_ni)hold_compute<=0;
        else if(hold_50)hold_compute<=2'b11;
        else hold_compute<={hold_compute[0],1'b0};
    always @(posedge compute_clk_i or negedge reset_ni)begin
        if(!reset_ni)begin
            request_compute<=0;request_seen<=0;compute_pending<=0;compute_sent<=0;
            acknowledge_toggle<=0;compute_failure<=0;local_request_o<=0;
        end else begin
            request_compute<={request_compute[0],request_toggle};local_request_o<=0;
            if(ENABLE && request_compute[1]!=request_seen)begin
                request_seen<=request_compute[1];compute_pending<=1;compute_sent<=0;
            end
            if(compute_pending)begin
                // A CPU-only reset cannot abandon a request or clear storage.
                // Reissue to the service after reset; the seal is idempotent.
                if(!owner_reset_ni)compute_sent<=0;
                else if(!compute_sent)begin local_request_o<=1;compute_sent<=1;end
                else if(local_done_i || local_failed_i)begin
                    compute_pending<=0;compute_failure<=local_failed_i;
                    acknowledge_toggle<=!acknowledge_toggle;
                end
            end
        end
    end
    // Failure payload is held until the next transaction. The acknowledge
    // gets an extra destination settle edge after its two-flop synchronizer;
    // parallel per-bit sampling alone would not correlate the result.
    always @(posedge clk_50m_i or negedge reset_ni)begin
        if(!reset_ni)begin
            acknowledge_50<=0;failed_50<=0;
        end else begin
            acknowledge_50<={acknowledge_50[1:0],acknowledge_toggle};
            failed_50<={failed_50[0],compute_failure};
        end
    end
    always @(posedge clk_50m_i or negedge reset_ni)begin
        if(!reset_ni)begin
            state<=IDLE;hold_50<=0;request_toggle<=0;acknowledge_seen<=0;local_failure<=0;
            tf_stop_request_o<=0;done_o<=0;failed_o<=0;failure_code_o<=0;
        end else begin
            tf_stop_request_o<=0;done_o<=0;failed_o<=0;
            if(state==IDLE && !hold_i && (!ENABLE || !tf_stop_pending_i))hold_50<=0;
            if(ENABLE)case(state)
                IDLE:if(request_i && ready_o)begin
                    hold_50<=1;request_toggle<=!request_toggle;state<=LOCAL;local_failure<=0;failure_code_o<=0;
                end
                LOCAL:if(acknowledge_50[2]!=acknowledge_seen)begin
                    acknowledge_seen<=acknowledge_50[2];local_failure<=failed_50[1];
                    // Even a failed recording is actually stopped before TF.
                    tf_stop_request_o<=1;state<=TF;
                end
                TF:if(tf_stop_failed_i)begin
                    failure_code_o<=tf_stop_failure_code_i;failed_o<=1;state<=IDLE;
                end else if(tf_stop_done_i)state<=QUIET;
                QUIET:if(media_quiet_i)begin
                    if(local_failure)begin failure_code_o<=4'd9;failed_o<=1;end
                    else done_o<=1;
                    state<=IDLE;
                end
                default:state<=IDLE;
            endcase
        end
    end
endmodule
