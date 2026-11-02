// Selected only by the explicit native shared-HCI source policy.
`include "native_bluetooth/patch_path.vh"

module workstation_bluetooth #(
    parameter CLK_HZ=50000000,
    parameter CAPACITY_FRAMES=16384,
    parameter DISABLE_MS=200,
    parameter STARTUP_MS=2000,
    parameter EXTERNAL_SEAL_PROTOCOL=0,
    parameter EXTERNAL_RAW_STORE=0,
    parameter SINGLE_BLE_RECORDING=0,
    parameter SESSION_ONLY_PAIRING=0,
    parameter integer RAW_DRAIN_TIMEOUT_CYCLES=0
) (
    input wire business_owner_reset_ni,business_command_valid_i,business_command_write_i,
    input wire [11:0] business_command_address_i,
    input wire [31:0] business_command_data_i,
    input wire [3:0] business_command_strobes_i,
    output wire business_command_ready_o,business_response_error_o,
    output wire [31:0] business_response_data_o,
    output wire [31:0] hci_epoch_o,hci_classic_generation_o,
    output wire hci_classic_active_o,hci_classic_fenced_o,hci_classic_ready_o,
    input wire clk_i, rst_ni, module_uart_tx_i,
    input wire pcm_valid_i, source_allowed_i,
    input wire [31:0] pcm_pair_i, pcm_sequence_i,
    output wire module_uart_rx_o, module_bt_dis_no, module_wl_dis_no, outputs_active_o,
    output wire initialized_o, connected_o, subscribed_o, failed_o,
    output wire [767:0] status_o,
    input wire seal_hold_i, seal_request_i,
    output wire seal_ready_o, seal_pending_o, seal_done_o, seal_failed_o,
    output wire [3:0] seal_failure_code_o,
`ifdef WORKSTATION_TASK3_W_PAIRED
    output wire record_object_idle_o,record_source_needed_o,
`endif
    output wire [7:0] seal_record_state_o,
    output wire [31:0] seal_recording_id_o, seal_frames_o, seal_crc_o,
    // clk / clk_i raw storage only; object/task/CRC/wire ownership stays here.
    output wire raw_start_valid_o,
    input wire raw_start_ready_i,raw_start_done_i,
    output wire raw_clear_valid_o,
    input wire raw_clear_ready_i,raw_clear_done_i,
    output wire raw_capture_valid_o,
    output wire [31:0] raw_capture_index_o,raw_capture_pcm_o,
    input wire raw_capture_ready_i,
    output wire raw_close_valid_o,
    input wire raw_close_ready_i,raw_drained_i,raw_fault_i,
    input wire raw_object_fault_i,raw_channel_fault_i,
    input wire [3:0] raw_failure_code_i,
    input wire [31:0] raw_accepted_frames_i,raw_committed_frames_i,
    output wire raw_fetch_valid_o,
    input wire raw_fetch_ready_i,
    output wire [31:0] raw_fetch_offset_o,
    output wire [13:0] raw_fetch_length_o,
    input wire raw_fetch_done_i,raw_fetch_fault_i,raw_cache_valid_i,
    output wire [31:0] raw_sample_addr_o,
    input wire [31:0] raw_sample_word_i
);
    wire reset_n;
    reset_release_sync u_reset (.clk(clk_i),.arstn(rst_ni),.resetn(reset_n));
`ifndef WORKSTATION_HCI_AUDIO_ONLY
    reg sample_seen;
    reg [31:0] sample_age, previous_sequence;
    wire source_fault = pcm_valid_i && sample_seen && pcm_sequence_i != previous_sequence+1'b1;
    always @(posedge clk_i or negedge reset_n) begin
        if(!reset_n) begin
            sample_seen<=0;sample_age<=CLK_HZ/250;previous_sequence<=0;
        end else begin
            if(pcm_valid_i) begin sample_seen<=1;sample_age<=0;previous_sequence<=pcm_sequence_i;end
            else if(sample_age<CLK_HZ/250) sample_age<=sample_age+1'b1;
        end
    end
`else
    wire sample_seen=1'b0,source_fault=1'b0;
    wire [31:0] sample_age=32'd0;
`endif
    wire core_active;
    workstation_hci_native_core #(
        .CLK_HZ(CLK_HZ),.EXTERNAL_PCM(1),.EXTERNAL_SEAL_PROTOCOL(EXTERNAL_SEAL_PROTOCOL),.EXTERNAL_RAW_STORE(EXTERNAL_RAW_STORE),.SINGLE_BLE_RECORDING(SINGLE_BLE_RECORDING),.RAW_DRAIN_TIMEOUT_CYCLES(RAW_DRAIN_TIMEOUT_CYCLES),.CAPACITY_FRAMES(CAPACITY_FRAMES),.DEVICE_NAME("GW138K-MAIN"),
        .SESSION_ONLY_PAIRING(SESSION_ONLY_PAIRING),.CACHE_METADATA_RAM_STYLE("distributed_ram"),
        .DISABLE_MS(DISABLE_MS),.STARTUP_MS(STARTUP_MS),.SESSION_MS(0),
        .PATCH_FILE(`WORKSTATION_BLE_PATCH_FILE)
    ) u_core (
        .hci_epoch_o(hci_epoch_o),.hci_classic_generation_o(hci_classic_generation_o),
        .hci_classic_ready_o(hci_classic_ready_o),.hci_classic_active_o(hci_classic_active_o),.hci_classic_fenced_o(hci_classic_fenced_o),
        .business_owner_reset_ni(business_owner_reset_ni),
        .business_command_valid_i(business_command_valid_i),
        .business_command_write_i(business_command_write_i),
        .business_command_address_i(business_command_address_i),
        .business_command_data_i(business_command_data_i),
        .business_command_strobes_i(business_command_strobes_i),
        .business_command_ready_o(business_command_ready_o),
        .business_response_error_o(business_response_error_o),
        .business_response_data_o(business_response_data_o),

        .clk(clk_i),.resetn(reset_n),.enable(reset_n),.uart_rx(module_uart_tx_i),
        .seal_hold_i(seal_hold_i),.seal_request_i(seal_request_i),
        .seal_ready_o(seal_ready_o),.seal_pending_o(seal_pending_o),.seal_done_o(seal_done_o),.seal_failed_o(seal_failed_o),
`ifdef WORKSTATION_TASK3_W_PAIRED
        .record_object_idle_o(record_object_idle_o),.record_source_needed_o(record_source_needed_o),
`endif
        .seal_failure_code_o(seal_failure_code_o),.seal_record_state_o(seal_record_state_o),
        .seal_recording_id_o(seal_recording_id_o),.seal_frames_o(seal_frames_o),.seal_crc_o(seal_crc_o),
        .raw_start_valid_o(raw_start_valid_o),
        .raw_start_ready_i(raw_start_ready_i),
        .raw_start_done_i(raw_start_done_i),
        .raw_clear_valid_o(raw_clear_valid_o),
        .raw_clear_ready_i(raw_clear_ready_i),
        .raw_clear_done_i(raw_clear_done_i),
        .raw_capture_valid_o(raw_capture_valid_o),
        .raw_capture_index_o(raw_capture_index_o),
        .raw_capture_pcm_o(raw_capture_pcm_o),
        .raw_capture_ready_i(raw_capture_ready_i),
        .raw_close_valid_o(raw_close_valid_o),
        .raw_close_ready_i(raw_close_ready_i),
        .raw_drained_i(raw_drained_i),
        .raw_fault_i(raw_fault_i),
        .raw_object_fault_i(raw_object_fault_i),
        .raw_channel_fault_i(raw_channel_fault_i),
        .raw_failure_code_i(raw_failure_code_i),
        .raw_accepted_frames_i(raw_accepted_frames_i),
        .raw_committed_frames_i(raw_committed_frames_i),
        .raw_fetch_valid_o(raw_fetch_valid_o),
        .raw_fetch_ready_i(raw_fetch_ready_i),
        .raw_fetch_offset_o(raw_fetch_offset_o),
        .raw_fetch_length_o(raw_fetch_length_o),
        .raw_fetch_done_i(raw_fetch_done_i),
        .raw_fetch_fault_i(raw_fetch_fault_i),
        .raw_cache_valid_i(raw_cache_valid_i),
        .raw_sample_addr_o(raw_sample_addr_o),
        .raw_sample_word_i(raw_sample_word_i),
        .pcm_valid_i(pcm_valid_i),.pcm_pair_i({pcm_pair_i[15:0],pcm_pair_i[31:16]}),
        .source_ready_i(source_allowed_i && sample_seen && sample_age<CLK_HZ/250),
        .source_fault_i(source_fault),.uart_tx(module_uart_rx_o),.bt_enable(module_bt_dis_no),
        .outputs_active(core_active),.initialized(initialized_o),.connected(connected_o),
        .subscribed(subscribed_o),.failed(failed_o),.debug(status_o)
    );
    assign outputs_active_o = rst_ni && reset_n && core_active;
    assign module_wl_dis_no = 1'b0;
endmodule
