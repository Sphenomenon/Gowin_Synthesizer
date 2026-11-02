`timescale 1ns/1ps
// Executable logical pair composition, NOT a single-board production top.
// Actual SD/FAT/WAV is on M; actual model/CQT/CNN/native DDR client is on W.
// The link_* ports terminate a validated, ordered transaction transport. The
// shared clk here is a simulation/composition boundary, never an LCD/CDC claim.
module workstation_task3_tf_cnn_framework #(
    parameter bit CNN_USE_DDR_SIGNAL=1'b0,CNN_USE_DDR_CQT_COEFF=1'b0,
    parameter integer ANALYSIS_QUEUE_FRAMES=256,MAX_SCORE_NOTES=2048,LINK_QUEUE_DEPTH=4,
    parameter [31:0] ANALYSIS_WAIT_TIMEOUT=32'd4000000000
)(
    input wire clk_i,reset_ni,link_ready_i,transport_fault_i,cancel_i,panic_i,
    input wire [31:0] m_boot_i,session_i,
    input wire open_valid_i,
    output wire open_ready_o,
    input wire open_analysis_i,
    input wire [3:0] open_track_i,
    input wire [31:0] open_generation_i,open_task_id_i,clip_frames_i,
    output wire open_accepted_o,open_rejected_o,
    input wire [19:0] playback_rate_i,
    input wire playback_pause_i,playback_sample_request_i,
    output wire playback_pcm_valid_o,
    input wire playback_pcm_ready_i,
    output wire signed [15:0] playback_left_o,playback_right_o,
    output wire playback_last_o,
    output wire [31:0] playback_generation_o,
    output wire [19:0] playback_session_rate_o,
    output wire file_busy_o,file_consumed_o,file_failed_o,
    output wire [3:0] file_failure_o,
    output wire scan_done_o,
    output wire [4:0] track_count_o,
    input wire [7:0] name_address_i,
    output wire [7:0] name_data_o,
    output wire m_sd_cs_no,m_sd_sck_o,m_sd_mosi_o,
    input wire m_sd_miso_i,
    output wire push_score_valid_o,
    input wire push_score_ready_i,
    output wire [6:0] push_score_note_o,
    output wire analysis_done_o,analysis_failed_o,analysis_busy_o,
    output wire [31:0] analyzed_frames_o,completed_clips_o,score_notes_o,
    // One ordered lane: {kind[1:0],payload[199:0]}; 0 desc,1 PCM,2 seal.
    output wire m_analysis_tx_valid_o,
    input wire m_analysis_tx_ready_i,
    output wire [201:0] m_analysis_tx_o,
    input wire w_analysis_rx_valid_i,
    output wire w_analysis_rx_ready_o,
    input wire [201:0] w_analysis_rx_i,
    // Cancellation has a separate bounded control path, never audio credit.
    output wire m_cancel_tx_valid_o,
    input wire m_cancel_tx_ready_i,
    output wire [127:0] m_cancel_tx_o,
    input wire w_cancel_rx_valid_i,
    output wire w_cancel_rx_ready_o,
    input wire [127:0] w_cancel_rx_i,
    // One ordered result lane: {terminal,payload[166:0]}.
    output wire w_result_tx_valid_o,
    input wire w_result_tx_ready_i,
    output wire [167:0] w_result_tx_o,
    input wire m_result_rx_valid_i,
    output wire m_result_rx_ready_o,
    input wire [167:0] m_result_rx_i,
    // Bind these to W owner5 in workstation_media_memory, once, alongside
    // the unique owner8 raw store and real owner6 D-delay service.
    input wire w_memory_clk_i,w_memory_reset_ni,w_backend_ready_i,w_memory_transport_fault_i,
    output wire w_memory_valid_o,w_memory_write_o,
    output wire [28:0] w_memory_address_o,
    output wire [255:0] w_memory_data_o,
    output wire [31:0] w_memory_mask_o,
    input wire w_memory_slot_ready_i,w_memory_native_accept_i,w_memory_response_i,
    input wire [255:0] w_memory_read_data_i,
    input wire w_model_serial_i,w_model_flash_miso_i,
    output wire w_model_flash_cs_no,w_model_flash_clk_o,w_model_flash_mosi_o,
    output wire w_fatal_o,protocol_fault_o,
    output wire [3:0] w_model_status_o
);
    wire source_start,source_start_ready,pcm_valid,pcm_ready,pcm_last,route_cancel,route_analysis_selected;
    wire [31:0] pcm_pair;
    wire desc_valid,desc_ready,frame_valid,frame_ready,seal_valid,seal_ready;
    wire [199:0] desc;
    wire [191:0] frame,seal;
    wire arm_valid,arm_ready,arm_append,file_last,completion_valid,source_failed,collector_failed;
    wire [127:0] arm_identity;
    wire [163:0] completion;
    wire source_done;
    wire local_cancel=cancel_i || route_cancel || transport_fault_i;
    wire route_open_ready;
    assign open_ready_o=route_open_ready;
    workstation_task3_tf_route file_route(
        .clk_i(clk_i),.reset_ni(reset_ni),.cancel_i(cancel_i || (source_done && source_failed && route_analysis_selected)),.panic_i(panic_i),
        .open_valid_i(open_valid_i),.open_ready_o(route_open_ready),
        .open_analysis_i(open_analysis_i),.open_track_i(open_track_i),.open_generation_i(open_generation_i),
        .playback_rate_i(playback_rate_i),.open_accepted_o(open_accepted_o),.open_rejected_o(open_rejected_o),
        .analysis_start_valid_o(source_start),.analysis_start_ready_i(source_start_ready),
        .analysis_pcm_valid_o(pcm_valid),.analysis_pcm_ready_i(pcm_ready),.analysis_pcm_o(pcm_pair),
        .analysis_pcm_last_o(pcm_last),.analysis_cancel_o(route_cancel),
        .playback_pause_i(playback_pause_i),.playback_sample_request_i(playback_sample_request_i),
        .playback_pcm_valid_o(playback_pcm_valid_o),.playback_pcm_ready_i(playback_pcm_ready_i),
        .playback_left_o(playback_left_o),.playback_right_o(playback_right_o),.playback_last_o(playback_last_o),
        .playback_generation_o(playback_generation_o),.playback_session_rate_o(playback_session_rate_o),
        .busy_o(file_busy_o),.analysis_selected_o(route_analysis_selected),.file_consumed_o(file_consumed_o),
        .failed_o(file_failed_o),.failure_code_o(file_failure_o),.stop_completed_o(),.stop_failed_o(),
        .scan_done_o(scan_done_o),.track_count_o(track_count_o),.name_address_i(name_address_i),
        .name_data_o(name_data_o),.sd_cs_no(m_sd_cs_no),.sd_sck_o(m_sd_sck_o),.sd_mosi_o(m_sd_mosi_o),.sd_miso_i(m_sd_miso_i));
    workstation_task3_tf_analysis_source #(.QUEUE_FRAMES(ANALYSIS_QUEUE_FRAMES),
        .WAIT_TIMEOUT_CYCLES(ANALYSIS_WAIT_TIMEOUT)) source_m(
        .clk_i(clk_i),.reset_ni(reset_ni),.link_ready_i(link_ready_i),.transport_fault_i(transport_fault_i),
        .cancel_i(local_cancel),.panic_i(panic_i),.start_valid_i(source_start),.start_ready_o(source_start_ready),
        .start_boot_i(m_boot_i),.start_session_i(session_i),.start_task_id_i(open_task_id_i),
        .start_generation_i(open_generation_i),.clip_frames_i(clip_frames_i),
        .pcm_valid_i(pcm_valid),.pcm_ready_o(pcm_ready),.pcm_pair_i(pcm_pair),.pcm_last_i(pcm_last),
        .desc_valid_o(desc_valid),.desc_ready_i(desc_ready),.desc_o(desc),
        .frame_valid_o(frame_valid),.frame_ready_i(frame_ready),.frame_o(frame),
        .seal_valid_o(seal_valid),.seal_ready_i(seal_ready),.seal_o(seal),
        .cancel_valid_o(m_cancel_tx_valid_o),.cancel_ready_i(m_cancel_tx_ready_i),.cancel_o(m_cancel_tx_o),
        .arm_valid_o(arm_valid),.arm_ready_i(arm_ready),.arm_identity_o(arm_identity),.arm_append_o(arm_append),
        .chunk_file_last_o(file_last),.completion_valid_i(completion_valid),.completion_i(completion),
        .busy_o(analysis_busy_o),.done_o(source_done),.failed_o(source_failed),.failure_code_o(),
        .total_frames_o(analyzed_frames_o),.completed_clips_o(completed_clips_o));
    // A single ordered lane is deliberate: a seal may not pass its PCM, nor
    // may a terminal result pass an earlier note in independent queues.
    wire analysis_queue_ready;
    wire [201:0] analysis_offer=desc_valid?{2'd0,desc}:frame_valid?{2'd1,8'd0,frame}:{2'd2,8'd0,seal};
    workstation_task3_channel_mux #(.CHANNELS(1),.WIDTH(202),.DEPTH(LINK_QUEUE_DEPTH)) analysis_queue_m(
        .clk_i(clk_i),.reset_ni(reset_ni),.flush_i(local_cancel || source_failed),.link_ready_i(link_ready_i),
        .link_down_i(transport_fault_i),.panic_i(panic_i),
        .in_valid_i(desc_valid || frame_valid || seal_valid),.in_ready_o(analysis_queue_ready),.in_data_i(analysis_offer),
        .out_valid_o(m_analysis_tx_valid_o),.out_ready_i(m_analysis_tx_ready_i),.out_channel_o(),.out_data_o(m_analysis_tx_o),
        .full_o(),.overflow_o(),.overflow_count_o());
    assign desc_ready=analysis_queue_ready;
    assign frame_ready=analysis_queue_ready && !desc_valid;
    assign seal_ready=analysis_queue_ready && !desc_valid && !frame_valid;
    wire score_ready,terminal_ready;
    workstation_task3_score_commit_m #(.MAX_NOTES(MAX_SCORE_NOTES)) collector_m(
        .clk_i(clk_i),.reset_ni(reset_ni),.link_ready_i(link_ready_i),.cancel_i(local_cancel || source_failed),.panic_i(panic_i),
        .arm_valid_i(arm_valid),.arm_ready_o(arm_ready),.arm_identity_i(arm_identity),.arm_append_i(arm_append),
        .chunk_file_last_i(file_last),.score_valid_i(m_result_rx_valid_i && !m_result_rx_i[167]),
        .score_ready_o(score_ready),.score_i(m_result_rx_i[166:0]),
        .terminal_valid_i(m_result_rx_valid_i && m_result_rx_i[167]),.terminal_ready_o(terminal_ready),
        .terminal_i(m_result_rx_i[163:0]),.completion_valid_o(completion_valid),.completion_o(completion),
        .push_score_valid_o(push_score_valid_o),.push_score_ready_i(push_score_ready_i),
        .push_score_note_o(push_score_note_o),.analysis_done_o(analysis_done_o),.failed_o(collector_failed),
        .failure_code_o(),.note_count_o(score_notes_o));
    assign m_result_rx_ready_o=m_result_rx_i[167]?terminal_ready:score_ready;
    assign analysis_failed_o=source_failed || collector_failed;
    wire w_desc_ready,w_frame_ready,w_seal_ready,w_score_valid,w_terminal_valid,result_queue_ready;
    wire [166:0] w_score;
    wire [163:0] w_terminal;
    wire [1:0] rx_kind=w_analysis_rx_i[201:200];
    assign protocol_fault_o=w_analysis_rx_valid_i && rx_kind==3;
    assign w_analysis_rx_ready_o=rx_kind==0?w_desc_ready:rx_kind==1?w_frame_ready:
        rx_kind==2?w_seal_ready:1'b1;
    workstation_task3_cnn_stream_w #(.CNN_USE_DDR_SIGNAL(CNN_USE_DDR_SIGNAL),
        .CNN_USE_DDR_CQT_COEFF(CNN_USE_DDR_CQT_COEFF)) worker_w(
        .clk_i(clk_i),.reset_ni(reset_ni),.memory_clk_i(w_memory_clk_i),.memory_reset_ni(w_memory_reset_ni),
        .backend_ready_i(w_backend_ready_i),.link_ready_i(link_ready_i && !transport_fault_i && !protocol_fault_o),
        .transport_fault_i(w_memory_transport_fault_i),.panic_i(panic_i),.peer_boot_i(m_boot_i),.session_i(session_i),
        .desc_valid_i(w_analysis_rx_valid_i && rx_kind==0),.desc_ready_o(w_desc_ready),.desc_i(w_analysis_rx_i[199:0]),
        .frame_valid_i(w_analysis_rx_valid_i && rx_kind==1),.frame_ready_o(w_frame_ready),.frame_i(w_analysis_rx_i[191:0]),
        .seal_valid_i(w_analysis_rx_valid_i && rx_kind==2),.seal_ready_o(w_seal_ready),.seal_i(w_analysis_rx_i[191:0]),
        .cancel_valid_i(w_cancel_rx_valid_i),.cancel_ready_o(w_cancel_rx_ready_o),.cancel_i(w_cancel_rx_i),
        .score_valid_o(w_score_valid),.score_ready_i(result_queue_ready),.score_o(w_score),
        .terminal_valid_o(w_terminal_valid),.terminal_ready_i(result_queue_ready && !w_score_valid),.terminal_o(w_terminal),
        .fatal_o(w_fatal_o),.model_status_o(w_model_status_o),.model_serial_i(w_model_serial_i),
        .flash_miso_i(w_model_flash_miso_i),.flash_cs_n_o(w_model_flash_cs_no),
        .flash_clk_o(w_model_flash_clk_o),.flash_mosi_o(w_model_flash_mosi_o),
        .memory_valid_o(w_memory_valid_o),.memory_write_o(w_memory_write_o),.memory_address_o(w_memory_address_o),
        .memory_data_o(w_memory_data_o),.memory_mask_o(w_memory_mask_o),.memory_slot_ready_i(w_memory_slot_ready_i),
        .memory_native_accept_i(w_memory_native_accept_i),.memory_response_i(w_memory_response_i),
        .memory_read_data_i(w_memory_read_data_i),.rejected_descriptors_o(),.stale_transactions_o(),
        .accepted_frames_o(),.committed_frames_o(),.replayed_frames_o());
    wire [167:0] result_offer=w_score_valid?{1'b0,w_score}:{1'b1,3'd0,w_terminal};
    workstation_task3_channel_mux #(.CHANNELS(1),.WIDTH(168),.DEPTH(LINK_QUEUE_DEPTH)) result_queue_w(
        .clk_i(clk_i),.reset_ni(reset_ni),.flush_i(1'b0),.link_ready_i(link_ready_i),
        .link_down_i(transport_fault_i || protocol_fault_o),.panic_i(panic_i),
        .in_valid_i(w_score_valid || w_terminal_valid),.in_ready_o(result_queue_ready),.in_data_i(result_offer),
        .out_valid_o(w_result_tx_valid_o),.out_ready_i(w_result_tx_ready_i),.out_channel_o(),.out_data_o(w_result_tx_o),
        .full_o(),.overflow_o(),.overflow_count_o());
endmodule
