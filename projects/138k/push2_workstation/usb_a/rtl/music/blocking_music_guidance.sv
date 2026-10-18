`timescale 1ns/1ps
// Product-level blocking practice pipeline in the DDR clock domain. A toggle
// starts from PCM frame zero; after each matching physical note-on it scans
// only far enough to publish the next stable target and then blocks again.
module blocking_music_guidance(
    input  logic clk_i,rst_ni,
    input  logic payload_complete_i,
    input  logic [31:0] total_frames_i,
    input  logic toggle_i,
    input  logic played_note_valid_i,
    input  logic [6:0] played_note_i,
    input  logic upload_valid_i,
    output logic upload_ready_o,
    input  logic [20:0] upload_beat_index_i,
    input  logic [255:0] upload_data_i,
    input  logic [31:0] upload_keep_i,
    output logic music_req_o,music_write_o,
    output logic [28:0] music_address_o,
    output logic [255:0] music_data_o,
    output logic [31:0] music_mask_o,
    input  logic music_ready_i,music_response_i,
    input  logic [255:0] music_read_data_i,
    output logic running_o,waiting_o,scanning_o,end_of_song_o,
    output logic [6:0] current_note_o,
    output logic [31:0] current_frame_o,
    output logic [15:0] current_confidence_o,
    output logic [63:0] guide_mask_o,
    output logic [31:0] accepted_count_o,wrong_count_o,windows_scanned_o
);
    logic reset_cursor,start_trainer,stop_trainer,start_pending;
    logic request_next,target_valid,target_ready,window_request,detector_start,detector_sample_ready;
    logic detector_sample_valid,detector_result_valid,detector_result_ready,detector_silence,detector_busy;
    logic viterbi_result_valid,viterbi_result_ready,viterbi_silence,viterbi_busy;
    logic [31:0] window_frame,detector_frame,target_frame,engine_frame,windows_loaded,viterbi_frame;
    logic [6:0] detector_note,target_note,viterbi_note;
    logic [15:0] detector_confidence,target_confidence,viterbi_confidence;
    logic signed [15:0] detector_sample;
    logic correct_pulse,wrong_pulse,engine_busy;

    always_ff @(posedge clk_i or negedge rst_ni)begin
        if(!rst_ni)begin
            reset_cursor<=0;start_trainer<=0;stop_trainer<=0;start_pending<=0;
        end else begin
            reset_cursor<=0;start_trainer<=0;stop_trainer<=0;
            if(!payload_complete_i && running_o)stop_trainer<=1;
            if(toggle_i)begin
                if(running_o)stop_trainer<=1;
                else if(payload_complete_i)begin reset_cursor<=1;start_pending<=1;end
            end
            if(start_pending)begin start_pending<=0;start_trainer<=1;end
            if(end_of_song_o && running_o)stop_trainer<=1;
        end
    end

    blocking_note_trainer u_trainer(.clk_i,.rst_ni,.start_i(start_trainer),.stop_i(stop_trainer),
        .target_valid_i(target_valid),.target_ready_o(target_ready),.target_note_i(target_note),
        .target_frame_i(target_frame),.target_confidence_i(target_confidence),
        .played_note_valid_i,.played_note_i,.running_o,.waiting_o,.correct_pulse_o(correct_pulse),
        .wrong_pulse_o(wrong_pulse),.request_next_o(request_next),.current_note_o,
        .current_frame_o,.current_confidence_o,.guide_mask_o,.accepted_count_o,.wrong_count_o);

    blocking_note_search u_search(.clk_i,.rst_ni,.reset_cursor_i(reset_cursor),
        .request_next_i(request_next),.total_frames_i,.window_request_o(window_request),
        .window_frame_o(window_frame),.detector_valid_i(viterbi_result_valid),
        .detector_ready_o(viterbi_result_ready),.detector_note_i(viterbi_note),
        .detector_frame_i(viterbi_frame),.detector_confidence_i(viterbi_confidence),
        .detector_silence_i(viterbi_silence),.target_valid_o(target_valid),
        .target_ready_i(target_ready),.target_note_o(target_note),.target_frame_o(target_frame),
        .target_confidence_o(target_confidence),.scanning_o,.end_of_song_o,.windows_scanned_o);

    music_ddr_engine u_engine(.clk_i,.rst_ni,.upload_valid_i,.upload_ready_o,
        .upload_beat_index_i,.upload_data_i,.upload_keep_i,.window_request_i(window_request),
        .window_frame_i(window_frame),.detector_start_o(detector_start),.detector_frame_o(engine_frame),
        .detector_sample_ready_i(detector_sample_ready),.detector_sample_valid_o(detector_sample_valid),
        .detector_sample_o(detector_sample),.music_req_o,.music_write_o,.music_address_o,
        .music_data_o,.music_mask_o,.music_ready_i,.music_response_i,.music_read_data_i,
        .busy_o(engine_busy),.windows_loaded_o(windows_loaded));

    blocking_pcm_note_detector u_detector(.clk_i,.rst_ni,.start_window_i(detector_start),
        .source_frame_i(engine_frame),.sample_ready_o(detector_sample_ready),
        .sample_valid_i(detector_sample_valid),.sample_i(detector_sample),
        .result_valid_o(detector_result_valid),.result_ready_i(detector_result_ready),
        .result_note_o(detector_note),.result_frame_o(detector_frame),
        .result_confidence_o(detector_confidence),.silence_o(detector_silence),.busy_o(detector_busy));

    // Basic Pitch + Python Viterbi remain the workstation teacher.  This
    // bounded RTL column is the 138K streaming approximation: one detector
    // observation enters per PCM window, only current path costs are kept,
    // and no note sequence is written to DDR.
    blocking_note_viterbi u_viterbi(.clk_i,.rst_ni,
        .input_valid_i(detector_result_valid),.input_ready_o(detector_result_ready),
        .input_note_i(detector_note),.input_frame_i(detector_frame),
        .input_confidence_i(detector_confidence),.input_silence_i(detector_silence),
        .result_valid_o(viterbi_result_valid),.result_ready_i(viterbi_result_ready),
        .result_note_o(viterbi_note),.result_frame_o(viterbi_frame),
        .result_confidence_o(viterbi_confidence),.result_silence_o(viterbi_silence),
        .busy_o(viterbi_busy));
endmodule
