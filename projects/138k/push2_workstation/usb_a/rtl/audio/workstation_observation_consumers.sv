`timescale 1ns/1ps

// Compute-domain consumers of PHYSICAL completed frames, after the atomic CDC.
// The legacy 96-bit recorder has no format/context/error metadata: this adapter
// admits 48 kHz only and makes any discontinuity a failed recording session.
module workstation_observation_consumers #(
    parameter integer RECORD_ADDRESS_BITS=8,
    parameter bit ENABLE_MEDIA_POLICY=0
) (
    input wire clk_i,rst_ni,
    input wire frame_valid_i,frame_44k1_i,frame_error_i,
    input wire stream_change_i,sequence_gap_i,observation_loss_i,media_switch_busy_i,
    input wire [31:0] frame_epoch_i,
    input wire signed [31:0] left_i,right_i,
    input wire record_enable_i,record_ready_i,
    output wire record_valid_o,
    output wire [95:0] record_packet_o,
    output reg record_failed_o,
    // 1=context change, 2=sequence gap, 3=physical error, 4=CDC loss,
    // 5=unsupported 44.1-kHz legacy recording, 6=record FIFO overflow,
    // 7=record launch races an already-started clock transaction.
    output reg [2:0] record_failure_code_o,
    output reg [31:0] record_drop_o,
    output wire fft_valid_o,
    output wire [7:0] fft_bin_o,
    output wire signed [23:0] fft_real_o,fft_imag_o,
    output wire [31:0] fft_frame_o,
    output wire fft_44k1_o,fft_context_valid_o,
    output wire [31:0] fft_epoch_o,
    output reg [31:0] fft_discard_count_o,
    input wire score_write_i,
    input wire [7:0] score_address_i,
    input wire [63:0] score_data_i,
    input wire [8:0] score_length_i,
    input wire score_start_i,score_stop_i,
    output wire score_running_o,score_done_o,
    output wire [31:0] led_mask_o,score_frame_o,
    output reg score_failed_o,
    input wire record_seal_i,
    output reg record_seal_done_o,record_seal_failed_o,
    output wire record_start_ready_o,
    output reg [31:0] record_object_id_o,record_object_rate_o,record_object_epoch_o,record_object_frames_o,
    output wire [5:0] record_object_status_o,
    output reg [2:0] record_object_failure_o,record_seal_status_o,
    output reg [31:0] record_seal_count_o,
    output reg score_cancelled_o
);
    reg have_context,current_rate,record_context_ready;
    reg [31:0] current_epoch;
    wire changed=frame_valid_i && have_context && stream_change_i;
    wire bad_frame=frame_valid_i && (frame_error_i || sequence_gap_i);
    wire context_break=changed || bad_frame || observation_loss_i;
    wire good_sample=frame_valid_i && !context_break;
    wire unsupported=record_enable_i &&
        ((frame_valid_i && frame_44k1_i) || (have_context && current_rate));
    wire [31:0] fifo_drop;
    wire fifo_valid,record_captured;
    reg previous_record_enable,object_valid,object_sealed,object_failed,seal_pending,seal_failure;
    wire new_record=ENABLE_MEDIA_POLICY && record_enable_i && !previous_record_enable;
    wire seal_request=ENABLE_MEDIA_POLICY && record_seal_i;
    reg recorder_reset_n,fft_reset_n;
    wire overflow=recorder_reset_n && fifo_drop!=0;
    wire record_abort=context_break || unsupported || overflow || media_switch_busy_i;
    wire fail_record=record_enable_i && !record_failed_o && record_abort;
    wire [2:0] failure_code=observation_loss_i ? 3'd4 :
        frame_valid_i && frame_error_i ? 3'd3 :
        frame_valid_i && sequence_gap_i ? 3'd2 : changed ? 3'd1 :
        unsupported ? 3'd5 : overflow ? 3'd6 : 3'd7;
    // A known-invalid queue is hidden immediately, before the local reset
    // flushes its contents on the next edge. POP can never turn it successful.
    assign record_valid_o=fifo_valid && recorder_reset_n && !record_failed_o &&
        !(record_enable_i && record_abort);
    assign record_start_ready_o=have_context && !current_rate && (!ENABLE_MEDIA_POLICY || record_context_ready) && !fifo_valid &&
        recorder_reset_n && !record_enable_i && !media_switch_busy_i && !context_break;
    assign record_object_status_o={record_start_ready_o,1'b0,fifo_valid,object_failed,object_sealed,object_valid};
    audio_capture_fifo #(.ADDRESS_BITS(RECORD_ADDRESS_BITS)) recorder(
        .clk_i,.rst_ni(recorder_reset_n),.enable_i(record_enable_i && !record_failed_o && !record_abort),
        .sample_valid_i(good_sample),
        .left_i,.right_i,.valid_o(fifo_valid),
        .ready_i(record_ready_i && record_valid_o),.packet_o(record_packet_o),.drop_count_o(fifo_drop),.captured_o(record_captured));
    wire raw_fft_valid;
    spectrum_fft256 spectrum(
        .clk_i,.rst_ni(fft_reset_n),.sample_valid_i(good_sample && fft_reset_n),
        .sample_i(left_i),.bin_valid_o(raw_fft_valid),.bin_o(fft_bin_o),
        .real_o(fft_real_o),.imag_o(fft_imag_o),.frame_o(fft_frame_o));
    assign fft_valid_o=raw_fft_valid && fft_reset_n && !context_break;
    assign fft_44k1_o=current_rate;
    assign fft_epoch_o=current_epoch;
    assign fft_context_valid_o=have_context && fft_reset_n && !context_break;
    // Cues remain resident across discontinuities. A broken physical timebase
    // stops playback and cannot assert successful completion on the same edge.
    wire raw_score_done;
    score_led_player score(
        .clk_i,.rst_ni,.sample_ce_i(good_sample),.write_i(score_write_i),
        .write_address_i(score_address_i),.write_data_i(score_data_i),
        .start_i(score_start_i && have_context && !context_break && !media_switch_busy_i &&
            (!ENABLE_MEDIA_POLICY || !score_stop_i)),
        .stop_i(score_stop_i || context_break || media_switch_busy_i),.length_i(score_length_i),
        .running_o(score_running_o),.done_o(raw_score_done),.leds_o(led_mask_o),.frame_o(score_frame_o));
    assign score_done_o=raw_score_done && !score_failed_o && !context_break && !media_switch_busy_i &&
        (!ENABLE_MEDIA_POLICY || !score_stop_i);
    always @(posedge clk_i or negedge rst_ni)begin
        if(!rst_ni)begin
            have_context<=0;current_rate<=0;current_epoch<=0;record_context_ready<=0;recorder_reset_n<=0;fft_reset_n<=0;
            record_failed_o<=0;record_failure_code_o<=0;record_drop_o<=0;
            score_failed_o<=0;fft_discard_count_o<=0;
            previous_record_enable<=0;object_valid<=0;object_sealed<=0;object_failed<=0;seal_pending<=0;seal_failure<=0;
            record_object_id_o<=0;record_object_rate_o<=0;record_object_epoch_o<=0;record_object_frames_o<=0;
            record_object_failure_o<=0;record_seal_status_o<=0;record_seal_count_o<=0;
            record_seal_done_o<=0;record_seal_failed_o<=0;score_cancelled_o<=0;
        end else begin
            if(media_switch_busy_i || context_break)record_context_ready<=0;
            else if(good_sample)record_context_ready<=1;
            record_seal_done_o<=0;record_seal_failed_o<=0;
            previous_record_enable<=record_enable_i;
            if(ENABLE_MEDIA_POLICY)begin
                if(new_record)begin
                    object_valid<=1;object_sealed<=0;object_failed<=0;
                    record_object_id_o<=record_object_id_o==32'hffffffff ? 32'd1 : record_object_id_o+1'b1;
                    // The legacy capture ABI is deliberately 48 kHz only.
                    record_object_rate_o<=32'd48000;record_object_epoch_o<=current_epoch;
                    record_object_frames_o<=record_captured ? 32'd1 : 32'd0;
                    record_object_failure_o<=0;
                end else if(record_captured && record_object_frames_o!=32'hffffffff)
                    record_object_frames_o<=record_object_frames_o+1'b1;
                if(fail_record)begin
                    object_failed<=1;object_sealed<=1;record_object_failure_o<=failure_code;
                end
                if(previous_record_enable && !record_enable_i && object_valid)object_sealed<=1;
                if(seal_request)begin
                    seal_pending<=1;record_seal_status_o<=3'b001;
                    seal_failure<=record_enable_i && (object_failed || record_failed_o || record_abort);
                end
                // The enable owner has really stopped. FIFO and snapshot
                // ownership are retained, including a final accepted packet.
                if(seal_pending && !record_enable_i)begin
                    seal_pending<=0;
                    if(object_valid)object_sealed<=1;
                    record_seal_done_o<=!seal_failure;
                    record_seal_failed_o<=seal_failure;
                    record_seal_status_o<={seal_failure,2'b10};
                    if(record_seal_count_o!=32'hffffffff)record_seal_count_o<=record_seal_count_o+1'b1;
                end
                // A planned rate-switch stop wins over start and final cue.
                // It is cancellation, never a successful cue completion.
                if(score_stop_i && (score_running_o || raw_score_done || score_start_i))score_cancelled_o<=1;
                else if(score_start_i && have_context && !context_break && !media_switch_busy_i)
                    score_cancelled_o<=0;
            end
            if(frame_valid_i)begin have_context<=1;current_rate<=frame_44k1_i;current_epoch<=frame_epoch_i;end
            fft_reset_n<=!context_break;
            // Normal REC_ENABLE=0 is STOP, not CLEAR. Existing firmware stops
            // first and then POP/RELEASEs captured packets. Only failure flushes.
            recorder_reset_n<=!(record_enable_i && (record_failed_o || record_abort));
            if(!record_enable_i)begin record_failed_o<=0;record_failure_code_o<=0;end
            else if(fail_record)begin
                record_failed_o<=1;record_failure_code_o<=failure_code;
                // A lower bound on known lost/rejected packets; the first
                // failure terminates the session, so later frames are ignored.
                if(record_drop_o!=32'hffff_ffff)record_drop_o<=record_drop_o+1'b1;
            end
            if(context_break && fft_discard_count_o!=32'hffff_ffff)
                fft_discard_count_o<=fft_discard_count_o+1'b1;
            if((context_break || media_switch_busy_i) && (score_running_o || score_start_i))score_failed_o<=1;
            else if(score_start_i && have_context && !context_break && !media_switch_busy_i)score_failed_o<=0;
        end
    end
endmodule
