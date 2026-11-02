`timescale 1ns/1ps
`include "rtl/ddr_address_map.vh"
// Native, unselected W-media boundary. HCI/GATT still owns the one recording
// object; this module owns only its raw DDR store and the real CNN task. The
// board shell must bind HCI raw_* and a validated transport to these ports.
// No LCD pins, M peripherals, second recorder or graphics are inferred here.
module workstation_task3_w_media #(
    parameter integer BIST_BURSTS=`PRJ1_DDR_BIST_BEATS,
    parameter bit CNN_USE_DDR_SIGNAL=1'b1,
    parameter bit CNN_USE_DDR_CQT_COEFF=1'b1,
    parameter integer CNN_IO_TIMEOUT_CYCLES=50000000,
    parameter [31:0] CNN_TASK_TIMEOUT_CYCLES=32'd3600000000,
    parameter integer RAW_COMMAND_TIMEOUT_CYCLES=10000,
    parameter integer RAW_READ_TIMEOUT_CYCLES=10000
) (
    input wire clk_i,reset_ni,memory_clk_i,memory_reset_ni,
    input wire memory_calibrated_i,memory_pll_locked_i,
    output wire client_reset_no,client_ready_o,control_ready_o,
    output wire [7:0] memory_flags_o,
    output wire [8:0] slot_accept_o,core_accept_o,native_accept_o,
    output wire transport_fault_o,
    // Native owner6 belongs to the maintained D delay service, not CNN/record.
    input wire delay_valid_i,delay_write_i,
    input wire [28:0] delay_address_i,
    input wire [255:0] delay_data_i,
    output wire delay_ready_o,delay_response_o,
    output wire [255:0] response_data_o,
    // Existing HCI single-owner engine/service raw storage contract (clk_i).
    input wire raw_start_valid_i,raw_clear_valid_i,
    output wire raw_start_ready_o,raw_start_done_o,raw_clear_ready_o,raw_clear_done_o,
    input wire raw_capture_valid_i,
    input wire [31:0] raw_capture_index_i,raw_capture_pcm_i,
    output wire raw_capture_ready_o,
    input wire raw_close_valid_i,
    output wire raw_close_ready_o,raw_drained_o,raw_fault_o,
    output wire raw_object_fault_o,raw_channel_fault_o,
    output wire [3:0] raw_failure_code_o,
    output wire [31:0] raw_accepted_frames_o,raw_committed_frames_o,
    input wire raw_fetch_valid_i,
    output wire raw_fetch_ready_o,
    input wire [31:0] raw_fetch_offset_i,
    input wire [13:0] raw_fetch_length_i,
    output wire raw_fetch_done_o,raw_fetch_fault_o,raw_cache_valid_o,
    input wire [31:0] raw_sample_addr_i,
    output wire [31:0] raw_sample_word_o,
    output wire raw_native_protocol_fault_o,
    // Offline bounded CNN job. Its credits must not gate realtime PCM.
    input wire cnn_start_valid_i,
    output wire cnn_start_ready_o,
    input wire [31:0] cnn_start_task_id_i,cnn_start_generation_i,cnn_start_frames_i,cnn_start_crc_i,
    input wire [7:0] cnn_start_format_i,
    output wire cnn_start_accepted_o,cnn_start_rejected_o,
    output wire [3:0] cnn_rejection_code_o,
    input wire cnn_frame_valid_i,
    output wire cnn_frame_ready_o,
    input wire [31:0] cnn_frame_task_id_i,cnn_frame_generation_i,cnn_frame_index_i,cnn_frame_pcm_i,
    input wire cnn_ingress_fault_i,cnn_cancel_valid_i,
    input wire [31:0] cnn_cancel_task_id_i,cnn_cancel_generation_i,
    output wire cnn_seal_valid_o,
    output wire [31:0] cnn_seal_crc_o,cnn_accepted_frames_o,cnn_committed_frames_o,cnn_replayed_frames_o,
    output wire cnn_score_valid_o,
    input wire cnn_score_ready_i,
    output wire [6:0] cnn_score_note_o,
    output wire [31:0] cnn_score_index_o,cnn_task_id_o,cnn_generation_o,
    output wire cnn_terminal_valid_o,
    input wire cnn_terminal_ready_i,
    output wire [3:0] cnn_terminal_code_o,
    output wire cnn_first_result_valid_o,
    output wire [6:0] cnn_first_result_note_o,
    output wire [15:0] cnn_first_result_frame_o,
    output wire cnn_fatal_o,
    output wire [3:0] cnn_model_status_o,
    input wire model_serial_i,model_flash_miso_i,
    output wire model_flash_cs_no,model_flash_clk_o,model_flash_mosi_o,
    output wire [2:0] app_cmd_o,
    output wire app_en_o,app_wren_o,app_wend_o,
    output wire [28:0] app_address_o,
    output wire [255:0] app_data_o,
    output wire [31:0] app_mask_o,
    input wire app_ready_i,app_write_ready_i,app_response_i,
    input wire [255:0] app_response_data_i
);
    localparam integer RECORD_CAPACITY_FRAMES=`PRJ1_DDR_TASK3_W_RECORDING_CAPACITY_FRAMES;
    localparam [28:0] RECORD_BASE=`PRJ1_DDR_TASK3_W_RECORDING_APP_BASE;
    ddr_address_map_guard address_policy();
    initial begin
        if(RECORD_CAPACITY_FRAMES!=2880000 ||
           `PRJ1_DDR_TASK3_W_RECORDING_BYTES!=11520000 ||
           RECORD_BASE[2:0]!=0)
            $fatal(1,"task3 W recording source policy changed");
    end
    // Both domains and all native queues reset together on controller loss.
    // A fault without common reset stays quarantined inside the clients.
    wire service_reset_n=reset_ni && client_reset_no;
    (* ASYNC_REG="TRUE",syn_preserve=1 *) reg [1:0] ready_control;
    always @(posedge clk_i or negedge service_reset_n)
        if(!service_reset_n)ready_control<=0;
        else ready_control<={ready_control[0],client_ready_o};
    assign control_ready_o=ready_control[1];
    wire music_valid,music_write,music_ready,music_response;
    wire [28:0] music_address;
    wire [255:0] music_data;
    wire [31:0] music_mask;
    wire recording_valid,recording_write,recording_ready,recording_response;
    wire [28:0] recording_address;
    wire [255:0] recording_data;
    wire [31:0] recording_mask;
    workstation_media_memory #(.BIST_BURSTS(BIST_BURSTS)) memory(
        .reset_ni(reset_ni),.clk_50m_i(clk_i),.memory_clk_i(memory_clk_i),.memory_reset_ni(memory_reset_ni),
        .memory_calibrated_i(memory_calibrated_i),.memory_pll_locked_i(memory_pll_locked_i),
        .client_reset_no(client_reset_no),.client_ready_o(client_ready_o),
        .music_valid_i(music_valid),.music_write_i(music_write),.music_address_i(music_address),
        .music_data_i(music_data),.music_mask_i(music_mask),.music_ready_o(music_ready),.music_response_o(music_response),
        .delay_valid_i(delay_valid_i),.delay_write_i(delay_write_i),.delay_address_i(delay_address_i),
        .delay_data_i(delay_data_i),.delay_ready_o(delay_ready_o),.delay_response_o(delay_response_o),
        .recording_valid_i(recording_valid),.recording_write_i(recording_write),.recording_address_i(recording_address),
        .recording_data_i(recording_data),.recording_mask_i(recording_mask),
        .recording_ready_o(recording_ready),.recording_response_o(recording_response),
        .app_cmd_o(app_cmd_o),.app_en_o(app_en_o),.app_wren_o(app_wren_o),.app_wend_o(app_wend_o),
        .app_address_o(app_address_o),.app_data_o(app_data_o),.app_mask_o(app_mask_o),
        .app_ready_i(app_ready_i),.app_write_ready_i(app_write_ready_i),.app_response_i(app_response_i),
        .app_response_data_i(app_response_data_i),.response_data_o(response_data_o),.memory_flags_o(memory_flags_o),
        .slot_accept_o(slot_accept_o),.core_accept_o(core_accept_o),.native_accept_o(native_accept_o),
        .transport_fault_o(transport_fault_o));
    wire start_ready,clear_ready,capture_ready,close_ready,fetch_ready;
    assign raw_start_ready_o=control_ready_o && start_ready;
    assign raw_clear_ready_o=control_ready_o && clear_ready;
    assign raw_capture_ready_o=control_ready_o && capture_ready;
    assign raw_close_ready_o=control_ready_o && close_ready;
    assign raw_fetch_ready_o=control_ready_o && fetch_ready;
    workstation_ble_raw_ddr_store #(
        .BASE_APP(`PRJ1_DDR_TASK3_W_RECORDING_APP_BASE),.CAPACITY_FRAMES(RECORD_CAPACITY_FRAMES),
        .COMMAND_TIMEOUT_CYCLES(RAW_COMMAND_TIMEOUT_CYCLES),.READ_TIMEOUT_CYCLES(RAW_READ_TIMEOUT_CYCLES)) raw_store(
        .clk_i(clk_i),.memory_clk_i(memory_clk_i),.rst_ni(service_reset_n),
        .start_valid_i(raw_start_valid_i && control_ready_o),.start_ready_o(start_ready),.start_done_o(raw_start_done_o),
        .clear_valid_i(raw_clear_valid_i && control_ready_o),.clear_ready_o(clear_ready),.clear_done_o(raw_clear_done_o),
        .capture_valid_i(raw_capture_valid_i && control_ready_o),.capture_index_i(raw_capture_index_i),
        .capture_pcm_i(raw_capture_pcm_i),.capture_ready_o(capture_ready),
        .close_valid_i(raw_close_valid_i && control_ready_o),.close_ready_o(close_ready),
        .drained_o(raw_drained_o),.fault_o(raw_fault_o),.object_fault_o(raw_object_fault_o),
        .channel_fault_o(raw_channel_fault_o),.failure_code_o(raw_failure_code_o),
        .accepted_frames_o(raw_accepted_frames_o),.committed_frames_o(raw_committed_frames_o),
        .fetch_valid_i(raw_fetch_valid_i && control_ready_o),.fetch_ready_o(fetch_ready),
        .fetch_offset_i(raw_fetch_offset_i),.fetch_length_i(raw_fetch_length_i),
        .fetch_done_o(raw_fetch_done_o),.fetch_fault_o(raw_fetch_fault_o),.cache_valid_o(raw_cache_valid_o),
        .sample_addr_i(raw_sample_addr_i),.sample_word_o(raw_sample_word_o),
        .slot_valid_o(recording_valid),.slot_ready_i(recording_ready),.native_accept_i(native_accept_o[8]),
        .ddr_write_o(recording_write),.ddr_address_o(recording_address),.ddr_data_o(recording_data),.ddr_mask_o(recording_mask),
        .read_response_i(recording_response),.read_data_i(response_data_o),.transport_fault_i(transport_fault_o),
        .native_protocol_fault_o(raw_native_protocol_fault_o));
    workstation_cnn_task_service #(.IO_TIMEOUT_CYCLES(CNN_IO_TIMEOUT_CYCLES),
        .CNN_USE_DDR_SIGNAL(CNN_USE_DDR_SIGNAL),.CNN_USE_DDR_CQT_COEFF(CNN_USE_DDR_CQT_COEFF),
        .TASK_TIMEOUT_CYCLES(CNN_TASK_TIMEOUT_CYCLES)) cnn_task(
        .clk_i(clk_i),.reset_ni(service_reset_n),.memory_clk_i(memory_clk_i),.memory_reset_ni(client_reset_no),
        .backend_ready_i(client_ready_o),.transport_fault_i(transport_fault_o),
        .start_valid_i(cnn_start_valid_i),.start_ready_o(cnn_start_ready_o),
        .start_task_id_i(cnn_start_task_id_i),.start_generation_i(cnn_start_generation_i),
        .start_frames_i(cnn_start_frames_i),.start_crc_i(cnn_start_crc_i),.start_format_i(cnn_start_format_i),
        .start_accepted_o(cnn_start_accepted_o),.start_rejected_o(cnn_start_rejected_o),.rejection_code_o(cnn_rejection_code_o),
        .frame_valid_i(cnn_frame_valid_i),.frame_ready_o(cnn_frame_ready_o),
        .frame_task_id_i(cnn_frame_task_id_i),.frame_generation_i(cnn_frame_generation_i),
        .frame_index_i(cnn_frame_index_i),.frame_pcm_i(cnn_frame_pcm_i),.ingress_fault_i(cnn_ingress_fault_i),
        .cancel_valid_i(cnn_cancel_valid_i),.cancel_task_id_i(cnn_cancel_task_id_i),.cancel_generation_i(cnn_cancel_generation_i),
        .seal_valid_o(cnn_seal_valid_o),.seal_crc_o(cnn_seal_crc_o),.accepted_frames_o(cnn_accepted_frames_o),
        .committed_frames_o(cnn_committed_frames_o),.replayed_frames_o(cnn_replayed_frames_o),
        .score_valid_o(cnn_score_valid_o),.score_ready_i(cnn_score_ready_i),.score_note_o(cnn_score_note_o),
        .score_index_o(cnn_score_index_o),.task_id_o(cnn_task_id_o),.generation_o(cnn_generation_o),
        .terminal_valid_o(cnn_terminal_valid_o),.terminal_ready_i(cnn_terminal_ready_i),.terminal_code_o(cnn_terminal_code_o),
        .first_result_valid_o(cnn_first_result_valid_o),.first_result_note_o(cnn_first_result_note_o),
        .first_result_frame_o(cnn_first_result_frame_o),.fatal_o(cnn_fatal_o),.model_status_o(cnn_model_status_o),
        .model_serial_i(model_serial_i),.flash_miso_i(model_flash_miso_i),.flash_cs_n_o(model_flash_cs_no),
        .flash_clk_o(model_flash_clk_o),.flash_mosi_o(model_flash_mosi_o),
        .memory_valid_o(music_valid),.memory_write_o(music_write),.memory_address_o(music_address),
        .memory_data_o(music_data),.memory_mask_o(music_mask),.memory_slot_ready_i(music_ready),
        .memory_native_accept_i(native_accept_o[5]),.memory_response_i(music_response),.memory_read_data_i(response_data_o));
endmodule
