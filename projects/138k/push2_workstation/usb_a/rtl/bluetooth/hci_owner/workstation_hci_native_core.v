// Native shared HCI composition; opt-in, original CPU core retained.
// Business test adaptation; vendor remains frozen.
module workstation_hci_native_core #(
    parameter [87:0] DEVICE_NAME="GW25K-PROTO",
    parameter EXTERNAL_PCM=0, parameter CAPACITY_FRAMES=48000,
    parameter CACHE_METADATA_RAM_STYLE="block_ram",
    parameter CLK_HZ=50000000,
    parameter AUDIO_FILE="audio/test_tone.mem",
    parameter BAUD=115200,
    parameter FAST_BAUD=921600,
    parameter DISABLE_MS=200,
    parameter STARTUP_MS=2000,
    parameter SESSION_MS=0,
    parameter PATCH_BYTES=30147,
    parameter PATCH_FILE="rtl8723ds_patch.mem",
    parameter NOTIFY_MS=500,
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
    input wire clk, resetn, enable, uart_rx,
    input wire pcm_valid_i, source_ready_i, source_fault_i,
    input wire [31:0] pcm_pair_i,
    output wire uart_tx, bt_enable, outputs_active,
    output wire initialized, connected, subscribed,
    output reg failed,
    output wire [767:0] debug,
    input wire seal_hold_i, seal_request_i,
    output wire seal_ready_o, seal_pending_o, seal_done_o, seal_failed_o,
    output wire [3:0] seal_failure_code_o,
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
    localparam MS_TICKS=CLK_HZ/1000;
    reg [31:0] ms_div, uptime_ms;
    reg [7:0] core_error;
    wire init_failed,hci_fault;
    wire fast_mode, baud_idle;
    wire link_up, tx_ready, tx_done, tx_error, rx_valid;
    wire sub_resetn = resetn && enable;
    wire start_ready = enable && uptime_ms >= DISABLE_MS+STARTUP_MS;
    wire session_ended = (SESSION_MS != 0) && uptime_ms >= SESSION_MS;
    assign outputs_active = enable && !failed && !session_ended;
    assign bt_enable = uptime_ms >= DISABLE_MS && outputs_active;
    always @(posedge clk) begin
        if(!resetn || !enable) begin ms_div<=0; uptime_ms<=0; failed<=0; core_error<=0; end
        else begin
            // Saturate so a long-lived session cannot repeat startup after wrap.
            if(ms_div==MS_TICKS-1) begin ms_div<=0; if(!session_ended && uptime_ms != 32'hffffffff) uptime_ms<=uptime_ms+1; end
            else ms_div<=ms_div+1;
            if(init_failed || hci_fault) failed<=1;
            if(!link_up && uptime_ms >= DISABLE_MS+STARTUP_MS+5000 && !initialized) begin
                failed<=1; core_error<=8;
            end
            if(tx_error && initialized) begin failed<=1; core_error<=9; end
        end
    end
    wire [3:0] rx_type;
    wire [8:0] rx_length, rx_addr, tx_addr;
    wire [7:0] rx_data, tx_data, h5_state;
    wire [31:0] rx_frames,tx_frames,retries,uart_errors,protocol_errors;
    wire init_tx_start,init_rx_consume;
    wire [3:0] init_tx_type;
    wire [8:0] init_tx_length, init_rx_addr;
    wire [7:0] init_tx_data,init_state,init_error,last_status,rom_version;
    wire [15:0] last_opcode;
    wire [31:0] command_count,patch_fragments;
    wire [2:0] hci_valid_mask;
    wire [7:0] acl_packet_count;
    wire [47:0] bd_addr;
    wire [63:0] boot_id;
    wire app_tx_start,app_rx_consume;
    wire [3:0] app_tx_type;
    wire [8:0] app_tx_length,app_rx_addr;
    wire [7:0] app_tx_data,app_state;
    wire [11:0] handle;
    wire [31:0] notification_count,acl_rx_count,att_request_count,completed_packets,app_errors,app_elapsed;
    wire bridge_tx_start,bridge_rx_consume;
    wire [3:0] bridge_tx_type,app_rx_type;
    wire [8:0] bridge_tx_length,bridge_rx_addr,app_payload_addr,app_rx_length;
    wire [7:0] bridge_tx_data,app_rx_data;
    wire app_tx_ready,app_tx_done,app_tx_error,app_rx_valid;
    wire owner_tx_start,owner_rx_consume;
    wire [3:0] owner_tx_type;
    wire [8:0] owner_tx_length;
    wire hci_handoff,host_flow_ready;
    wire init_tx_ready,init_tx_done,init_tx_error,init_rx_valid;
    wire [3:0] init_rx_type;
    wire [8:0] init_rx_length,init_tx_addr;
    wire [7:0] init_rx_data;
    wire bridge_tx_ready,bridge_tx_done,bridge_tx_error,bridge_rx_valid;
    wire [3:0] bridge_rx_type;
    wire [8:0] bridge_rx_length,bridge_tx_addr;
    wire [7:0] bridge_rx_data;
    wire [15:0] ble_acl_limit;
    wire hci_select=business_command_address_i[11:8]==2;
    wire hci_bus_ready,hci_bus_error,business_app_ready,business_app_error;
    wire [31:0] hci_bus_data,business_app_data;
    assign business_command_ready_o=hci_select ? hci_bus_ready : business_app_ready;
    assign business_response_error_o=hci_select ? hci_bus_error : business_app_error;
    assign business_response_data_o=hci_select ? hci_bus_data : business_app_data;
    workstation_hci_ble_bridge #(.CLK_HZ(CLK_HZ)) acl_bridge (
        .clk(clk),.resetn(sub_resetn),.enable(initialized && outputs_active),
        .connected(connected),.connection_handle(handle),.acl_data_limit_i(ble_acl_limit),
        .app_tx_start(app_tx_start),.app_tx_type(app_tx_type),.app_tx_length(app_tx_length),
        .app_tx_addr(app_payload_addr),.app_tx_data(app_tx_data),.app_tx_ready(app_tx_ready),
        .app_tx_done(app_tx_done),.app_tx_error(app_tx_error),
        .app_rx_valid(app_rx_valid),.app_rx_type(app_rx_type),.app_rx_length(app_rx_length),
        .app_rx_addr(app_rx_addr),.app_rx_data(app_rx_data),.app_rx_consume(app_rx_consume),
        .h5_tx_start(bridge_tx_start),.h5_tx_type(bridge_tx_type),.h5_tx_length(bridge_tx_length),
        .h5_tx_addr(bridge_tx_addr),.h5_tx_data(bridge_tx_data),.h5_tx_ready(bridge_tx_ready),
        .h5_tx_done(bridge_tx_done),.h5_tx_error(bridge_tx_error),
        .h5_rx_valid(bridge_rx_valid),.h5_rx_type(bridge_rx_type),.h5_rx_length(bridge_rx_length),
        .h5_rx_addr(bridge_rx_addr),.h5_rx_data(bridge_rx_data),.h5_rx_consume(bridge_rx_consume)
    );
    workstation_hci_native_transport #(.CLK_HZ(CLK_HZ),.SESSION_ONLY_PAIRING(SESSION_ONLY_PAIRING)) owner (
        .clk_i(clk),.reset_ni(sub_resetn),.enable_i(start_ready && outputs_active),.observer_reset_ni(business_owner_reset_ni),
        .link_up_i(link_up),.physical_fault_i(init_failed),.boot_id_i(boot_id),
        .initializer_handoff_i(hci_handoff),.initialized_i(initialized),.host_flow_ready_o(host_flow_ready),
        .controller_epoch_o(hci_epoch_o),.classic_generation_o(hci_classic_generation_o),
        .classic_active_o(hci_classic_active_o),.classic_ready_o(hci_classic_ready_o),.classic_fenced_o(hci_classic_fenced_o),
        .fault_o(hci_fault),.ble_acl_limit_o(ble_acl_limit),
        .init_tx_start_i(init_tx_start),.init_tx_type_i(init_tx_type),.init_tx_length_i(init_tx_length),
        .init_tx_address_o(init_tx_addr),.init_tx_data_i(init_tx_data),.init_tx_ready_o(init_tx_ready),
        .init_tx_done_o(init_tx_done),.init_tx_error_o(init_tx_error),
        .init_rx_valid_o(init_rx_valid),.init_rx_type_o(init_rx_type),.init_rx_length_o(init_rx_length),
        .init_rx_address_i(init_rx_addr),.init_rx_data_o(init_rx_data),.init_rx_consume_i(init_rx_consume),
        .ble_tx_start_i(bridge_tx_start),.ble_tx_type_i(bridge_tx_type),.ble_tx_length_i(bridge_tx_length),
        .ble_tx_address_o(bridge_tx_addr),.ble_tx_data_i(bridge_tx_data),.ble_tx_ready_o(bridge_tx_ready),
        .ble_tx_done_o(bridge_tx_done),.ble_tx_error_o(bridge_tx_error),
        .ble_rx_valid_o(bridge_rx_valid),.ble_rx_type_o(bridge_rx_type),.ble_rx_length_o(bridge_rx_length),
        .ble_rx_address_i(bridge_rx_addr),.ble_rx_data_o(bridge_rx_data),.ble_rx_consume_i(bridge_rx_consume),
        .h5_tx_start_o(owner_tx_start),.h5_tx_type_o(owner_tx_type),.h5_tx_length_o(owner_tx_length),
        .h5_tx_address_i(tx_addr),.h5_tx_data_o(tx_data),.h5_tx_ready_i(tx_ready),.h5_tx_done_i(tx_done),
        .h5_tx_error_i(tx_error),.h5_rx_valid_i(rx_valid),.h5_rx_type_i(rx_type),.h5_rx_length_i(rx_length),
        .h5_rx_address_o(rx_addr),.h5_rx_data_i(rx_data),.h5_rx_consume_o(owner_rx_consume),
        .command_valid_i(business_command_valid_i && hci_select),.command_write_i(business_command_write_i),
        .command_address_i(business_command_address_i),.command_data_i(business_command_data_i),
        .command_strobes_i(business_command_strobes_i),.command_ready_o(hci_bus_ready),
        .response_error_o(hci_bus_error),.response_data_o(hci_bus_data)
    );
    bt_h5_transport #(.CLK_HZ(CLK_HZ),.BAUD(BAUD),.FAST_BAUD(FAST_BAUD)) transport (
        .clk(clk),.resetn(sub_resetn),.enable(start_ready),.uart_rx(uart_rx),.uart_tx(uart_tx),
        .fast_mode(fast_mode),.baud_idle(baud_idle),
        .tx_start(owner_tx_start && outputs_active),.tx_type(owner_tx_type),.tx_length(owner_tx_length),
        .tx_payload_addr(tx_addr),.tx_payload_data(tx_data),.tx_ready(tx_ready),
        .tx_done(tx_done),.tx_error(tx_error),.rx_valid(rx_valid),.rx_type(rx_type),
        .rx_length(rx_length),.rx_payload_addr(rx_addr),.rx_payload_data(rx_data),
        .rx_consume(owner_rx_consume),.link_up(link_up),
        .debug_state(h5_state),.rx_frames(rx_frames),.tx_frames(tx_frames),.retries(retries),
        .uart_errors(uart_errors),.protocol_errors(protocol_errors)
    );
    workstation_hci_initializer #(.CLK_HZ(CLK_HZ),.PATCH_BYTES(PATCH_BYTES),.PATCH_FILE(PATCH_FILE),
        .BAUD(BAUD),.FAST_BAUD(FAST_BAUD),.DEVICE_NAME(DEVICE_NAME)) initializer (
        .clk(clk),.resetn(sub_resetn),.enable(start_ready),.link_up(link_up),
        .fast_mode(fast_mode),.baud_idle(baud_idle),.host_flow_ready_i(host_flow_ready),.host_handoff_o(hci_handoff),
        .tx_start(init_tx_start),.tx_type(init_tx_type),.tx_length(init_tx_length),
        .tx_ready(init_tx_ready),.tx_done(init_tx_done),.tx_error(init_tx_error),
        .tx_payload_addr(init_tx_addr),.tx_payload_data(init_tx_data),.rx_valid(init_rx_valid),
        .rx_type(init_rx_type),.rx_length(init_rx_length),.rx_payload_addr(init_rx_addr),
        .rx_payload_data(init_rx_data),.rx_consume(init_rx_consume),.initialized(initialized),
        .failed(init_failed),.debug_state(init_state),.error_code(init_error),
        .last_opcode(last_opcode),.last_status(last_status),.rom_version(rom_version),
        .command_count(command_count),.patch_fragments(patch_fragments),
        .hci_valid_mask(hci_valid_mask),.bd_addr(bd_addr),.boot_id(boot_id),.acl_packet_count(acl_packet_count)
    );
    bt_gatt #(.SHARED_HCI_OWNER(1),.EXTERNAL_SEAL_PROTOCOL(EXTERNAL_SEAL_PROTOCOL),.EXTERNAL_RAW_STORE(EXTERNAL_RAW_STORE),.SINGLE_BLE_RECORDING(SINGLE_BLE_RECORDING),.RAW_DRAIN_TIMEOUT_CYCLES(RAW_DRAIN_TIMEOUT_CYCLES),.CLK_HZ(CLK_HZ),.AUDIO_FILE(AUDIO_FILE),.NOTIFY_MS(NOTIFY_MS),.EXTERNAL_PCM(EXTERNAL_PCM),.CAPACITY_FRAMES(CAPACITY_FRAMES),.DEVICE_NAME(DEVICE_NAME),.CACHE_METADATA_RAM_STYLE(CACHE_METADATA_RAM_STYLE)) application (
        .business_owner_reset_ni(business_owner_reset_ni),
        .business_command_valid_i(business_command_valid_i && !hci_select),
        .business_command_write_i(business_command_write_i),
        .business_command_address_i(business_command_address_i),
        .business_command_data_i(business_command_data_i),
        .business_command_strobes_i(business_command_strobes_i),
        .business_command_ready_o(business_app_ready),
        .business_response_error_o(business_app_error),
        .business_response_data_o(business_app_data),

        .clk(clk),.resetn(sub_resetn),.enable(enable && initialized && outputs_active),
        .seal_hold_i(seal_hold_i),.seal_request_i(seal_request_i),
        .seal_ready_o(seal_ready_o),.seal_pending_o(seal_pending_o),.seal_done_o(seal_done_o),.seal_failed_o(seal_failed_o),
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
        .pcm_valid_i(pcm_valid_i),.pcm_pair_i(pcm_pair_i),.source_ready_i(source_ready_i),.source_fault_i(source_fault_i),
        .boot_id(boot_id),.acl_packet_count(acl_packet_count),
        .rx_valid(app_rx_valid),.rx_type(app_rx_type),.rx_length(app_rx_length),
        .rx_payload_addr(app_rx_addr),.rx_payload_data(app_rx_data),.rx_consume(app_rx_consume),
        .tx_start(app_tx_start),.tx_type(app_tx_type),.tx_length(app_tx_length),
        .tx_ready(app_tx_ready),.tx_done(app_tx_done),.tx_error(app_tx_error),
        .tx_payload_addr(app_payload_addr),.tx_payload_data(app_tx_data),.connected(connected),
        .subscribed(subscribed),.connection_handle(handle),.notification_count(notification_count),
        .acl_rx_count(acl_rx_count),.att_request_count(att_request_count),.completed_packets(completed_packets),
        .debug_state(app_state),.error_count(app_errors),.elapsed_ms(app_elapsed)
    );
    assign debug[0*32+:32]=32'h42545647;
    assign debug[1*32+:32]=32'd1;
    assign debug[2*32+:32]={20'd0,hci_valid_mask,2'd0,session_ended,failed,subscribed,connected,initialized,link_up,outputs_active};
    assign debug[3*32+:32]=uptime_ms;
    assign debug[4*32+:32]={8'd0,app_state,init_state,h5_state};
    assign debug[5*32+:32]={core_error != 0 ? core_error : init_error,last_status,last_opcode};
    assign debug[6*32+:32]=command_count;
    assign debug[7*32+:32]=patch_fragments;
    assign debug[8*32+:32]=rx_frames;
    assign debug[9*32+:32]=tx_frames;
    assign debug[10*32+:32]=retries;
    assign debug[11*32+:32]=uart_errors;
    assign debug[12*32+:32]=protocol_errors;
    assign debug[13*32+:32]=notification_count;
    assign debug[14*32+:32]=acl_rx_count;
    assign debug[15*32+:32]=att_request_count;
    assign debug[16*32+:32]=completed_packets;
    assign debug[17*32+:32]=app_errors;
    assign debug[18*32+:32]=bd_addr[31:0];
    assign debug[19*32+:32]={16'd0,bd_addr[47:32]};
    assign debug[20*32+:32]={12'd0,handle,rom_version};
    assign debug[21*32+:32]=app_elapsed;
    assign debug[22*32+:32]=CLK_HZ;
    assign debug[23*32+:32]=fast_mode ? FAST_BAUD : BAUD;
endmodule
