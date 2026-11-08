`timescale 1ns/1ps
`include "rtl/workstation/task3_paired_channels.vh"
// W business endpoint after validated electrical/framing/CDC transport. No
// incoming file/recording/phone credit is connected to a physical sample tick.
module workstation_task3_w_bus_endpoint #(
    parameter bit BLOCK_PCM=1'b0,
    parameter bit PHONE_WINDOW_BLOCK=1'b0,
    parameter bit PHONE_BATCH=1'b0,
    parameter integer MEDIA_CAP_TIMEOUT_CYCLES=5000000
) (
    input wire clk_i,reset_ni,link_ready_i,panic_i,
    input wire [31:0] local_boot_i,peer_boot_i,session_i,generation_i,
    input wire rx_valid_i,
    output reg rx_ready_o,
    input wire [3:0] rx_channel_i,
    input wire [255:0] rx_payload_i,
    input wire [5:0] rx_length_i,
    output reg tx_valid_o,
    input wire tx_ready_i,
    output reg [3:0] tx_channel_o,
    output reg [255:0] tx_payload_o,
    output reg [5:0] tx_length_o,
    output wire cnn_desc_valid_o,
    input wire cnn_desc_ready_i,
    output wire [199:0] cnn_desc_o,
    output wire cnn_frame_valid_o,
    input wire cnn_frame_ready_i,
    output wire [191:0] cnn_frame_o,
    output wire cnn_seal_valid_o,
    input wire cnn_seal_ready_i,
    output wire [191:0] cnn_seal_o,
    output wire cnn_cancel_valid_o,
    input wire cnn_cancel_ready_i,
    output wire [127:0] cnn_cancel_o,
    input wire cnn_score_valid_i,
    output wire cnn_score_ready_o,
    input wire [166:0] cnn_score_i,
    input wire cnn_terminal_valid_i,
    output wire cnn_terminal_ready_o,
    input wire [163:0] cnn_terminal_i,
    input wire backend_ready_i,
    input wire [3:0] model_status_i,
    // W physical engine is the only recording object authority.
    input wire record_object_idle_i,record_transport_fault_i,record_source_needed_i,
    output wire record_pcm_valid_o,record_source_allowed_o,
    output wire [31:0] record_pcm_o,record_sequence_o,
    output wire record_fault_o,
    output wire [3:0] record_failure_o,
    input wire hci_classic_ready_i,phone_owner_ready_i,
    input wire [31:0] hci_epoch_i,hci_generation_i,
    // Existing W PCM1 and clock APB command CDCs, lane0=PCM1/lane1=clock.
    input wire [1:0] command_valid_i,command_write_i,
    input wire [23:0] command_address_i,
    input wire [63:0] command_data_i,
    input wire [7:0] command_strobes_i,
    output wire [1:0] command_ready_o,response_error_o,
    output wire [63:0] response_data_o,
    output wire phone_fault_o,
    output reg [31:0] malformed_packets_o,stale_packets_o
);
    wire [95:0] common={peer_boot_i,session_i,generation_i};
    reg [127:0] observed_context;
    // Keep byte comparisons separate: one carry chain across the full key
    // put immediate session fencing on the W critical path. No extra state.
    wire [127:0] current_context={local_boot_i,common};
    (* syn_keep=1 *) wire [15:0] context_equal_bytes;
    genvar context_byte;
    generate for(context_byte=0;context_byte<16;context_byte=context_byte+1)begin:g_context_equal
        assign context_equal_bytes[context_byte]=
            observed_context[context_byte*8+:8]==current_context[context_byte*8+:8];
    end endgenerate
    wire context_current=&context_equal_bytes;
    wire live=reset_ni && link_ready_i && !panic_i && context_current &&
        local_boot_i!=0 && peer_boot_i!=0 && session_i!=0 && generation_i!=0;
    wire analysis_packet=rx_channel_i==`TASK3_PAIR_CH_ANALYSIS && rx_length_i==`TASK3_PAIR_ANALYSIS_BYTES && rx_payload_i[255:202]==0;
    wire analysis_desc=analysis_packet && rx_payload_i[201:200]==0;
    wire analysis_frame=analysis_packet && rx_payload_i[201:200]==1 && rx_payload_i[199:192]==0;
    wire analysis_seal=analysis_packet && rx_payload_i[201:200]==2 && rx_payload_i[199:192]==0;
    wire analysis_cancel=rx_channel_i==`TASK3_PAIR_CH_ANALYSIS_CANCEL && rx_length_i==`TASK3_PAIR_CANCEL_BYTES && rx_payload_i[255:128]==0;
    localparam [31:0] MEDIA_VERSION=PHONE_BATCH ? `TASK3_PAIR_PHONE_BATCH_VERSION:PHONE_WINDOW_BLOCK ? `TASK3_PAIR_PHONE_WINDOW_VERSION:`TASK3_PAIR_MEDIA_VERSION;
    localparam [31:0] MEDIA_FEATURES=PHONE_BATCH ? `TASK3_PAIR_PHONE_BATCH_FEATURES:PHONE_WINDOW_BLOCK ? `TASK3_PAIR_PHONE_WINDOW_FEATURES:`TASK3_PAIR_MEDIA_FEATURES;
    initial if(PHONE_WINDOW_BLOCK && !BLOCK_PCM)$fatal(1,"phone blocks require negotiated block media");
    initial if(PHONE_BATCH && !PHONE_WINDOW_BLOCK)$fatal(1,"phone batch requires phone window media");
    reg media_cap_ready,media_cap_fault,media_cap_pending;
    reg [31:0] media_cap_age,media_cap_send_age;
    wire media_current=!BLOCK_PCM || (media_cap_ready && !media_cap_fault);
    wire media_cap_packet=BLOCK_PCM && rx_channel_i==`TASK3_PAIR_CH_MEDIA_CAPS && rx_length_i==`TASK3_PAIR_MEDIA_CAPS_BYTES && rx_payload_i[255:224]==0;
    wire media_cap_matches=rx_payload_i[223:96]=={peer_boot_i,local_boot_i,session_i,generation_i} &&
        rx_payload_i[95:0]=={`TASK3_PAIR_MEDIA_MAGIC,MEDIA_VERSION,MEDIA_FEATURES};
    wire a_block_packet=BLOCK_PCM && rx_channel_i==`TASK3_PAIR_CH_ANALYSIS_BLOCK;
    wire r_block_packet=BLOCK_PCM && rx_channel_i==`TASK3_PAIR_CH_RECORD_BLOCK;
    reg a_desc_pending,a_seal_pending,a_cancel_pending,a_active,a_protocol_fault,a_wire_sealed;
    reg [199:0] a_descriptor;
    reg [191:0] a_seal;
    reg [127:0] a_context,a_retired_context,a_cancel;
    wire a_desc_peer=rx_payload_i[199:136]=={peer_boot_i,session_i} && rx_payload_i[135:104]!=0 && rx_payload_i[103:72]!=0;
    wire a_desc_fresh=rx_payload_i[199:136]!=a_retired_context[127:64] || rx_payload_i[103:72]>a_retired_context[31:0];
    wire a_desc_fire=BLOCK_PCM && live && media_current && rx_valid_i && rx_ready_o && analysis_desc;
    wire a_cancel_fire=BLOCK_PCM && rx_valid_i && rx_ready_o && analysis_cancel && rx_payload_i[127:0]==a_context;
    wire a_frame_valid,a_frame_ready,a_rx_empty,a_rx_fault,a_rx_active,a_credit_valid,a_credit_ready;
    wire [31:0] a_frame_index,a_frame_pcm,a_credit_token,a_credit_limit;
    wire r_frame_valid,r_frame_ready,r_rx_fault,r_rx_active,r_credit_valid,r_credit_ready;
    wire [31:0] r_frame_index,r_frame_pcm,r_credit_token,r_credit_limit;
    reg a_fault_pending,r_fault_pending;
    reg [31:0] a_fault_token,r_fault_token;
    reg [3:0] a_fault_reason,r_fault_reason;
    reg previous_a_fault,previous_r_fault,prefer_record_credit;
    wire a_after_seal=BLOCK_PCM && live && rx_valid_i && rx_ready_o && a_wire_sealed && (a_block_packet || analysis_seal);
    wire a_fault_event=BLOCK_PCM && a_active && (a_protocol_fault || media_cap_fault || a_rx_fault);
    assign cnn_desc_valid_o=BLOCK_PCM ? live && media_current && a_desc_pending && !a_cancel_fire && !a_protocol_fault : live && rx_valid_i && analysis_desc;
    assign cnn_desc_o=BLOCK_PCM?a_descriptor:rx_payload_i[199:0];
    assign cnn_frame_valid_o=BLOCK_PCM ? a_frame_valid && a_active && !a_cancel_fire && !a_protocol_fault : live && rx_valid_i && analysis_frame;
    assign cnn_frame_o=BLOCK_PCM?{a_context,a_frame_index,a_frame_pcm}:rx_payload_i[191:0];
    assign a_frame_ready=cnn_frame_ready_i && a_active && !a_cancel_fire && !a_protocol_fault;
    assign cnn_seal_valid_o=BLOCK_PCM ? live && media_current && a_active && a_seal_pending && a_rx_empty && !a_desc_pending && !a_cancel_fire && !a_protocol_fault && !a_after_seal : live && rx_valid_i && analysis_seal;
    assign cnn_seal_o=BLOCK_PCM?a_seal:rx_payload_i[191:0];
    assign cnn_cancel_valid_o=BLOCK_PCM ? reset_ni && a_cancel_pending : reset_ni && rx_valid_i && analysis_cancel;
    assign cnn_cancel_o=BLOCK_PCM?a_cancel:rx_payload_i[127:0];
    workstation_task3_pcm_block_rx analysis_blocks(
        .clk_i(clk_i),.reset_ni(reset_ni),.live_i(BLOCK_PCM && live && media_current),
        .start_i(cnn_desc_valid_o && cnn_desc_ready_i),.token_i(a_context[31:0]),.first_index_i(32'd0),
        .cancel_i(a_cancel_fire || a_protocol_fault || !a_active),
        .block_valid_i(live && rx_valid_i && rx_ready_o && a_block_packet && !a_wire_sealed),.block_payload_i(rx_payload_i),.block_length_i(rx_length_i),
        .frame_valid_o(a_frame_valid),.frame_ready_i(a_frame_ready),.frame_index_o(a_frame_index),.frame_pcm_o(a_frame_pcm),
        .credit_valid_o(a_credit_valid),.credit_ready_i(a_credit_ready),.credit_token_o(a_credit_token),.credit_limit_o(a_credit_limit),
        .empty_o(a_rx_empty),.active_o(a_rx_active),.fault_o(a_rx_fault),.accepted_blocks_o(),.delivered_frames_o());
    wire record_packet=rx_channel_i==`TASK3_PAIR_CH_RECORD && rx_length_i==`TASK3_PAIR_RECORD_BYTES && rx_payload_i[255:196]==0;
    // Record generation is independently allocated by M. Map it to a W-root
    // monotonic ingress generation, so either board can reboot independently.
    wire [95:0] record_wire_common=rx_payload_i[193:98];
    wire record_matches=record_wire_common[95:32]=={peer_boot_i,session_i} && record_wire_common[31:0]!=0;
    reg [95:0] record_active_common,record_retired_common;
    reg [31:0] record_local_counter,record_active_local,record_active_epoch,record_active_first;
    wire record_new_key=record_wire_common[95:32]!=record_retired_common[95:32] ||
        record_wire_common[31:0]>record_retired_common[31:0];
    wire [31:0] record_next_local=record_new_key && record_local_counter!=32'hffffffff ? record_local_counter+1'b1:32'd0;
    wire record_arm=record_packet && rx_payload_i[195:194]==`TASK3_PAIR_KIND_ARM && rx_payload_i[97:64]==0;
    wire record_frame=record_packet && rx_payload_i[195:194]==`TASK3_PAIR_KIND_DATA;
    wire record_cancel=record_packet && rx_payload_i[195:194]==`TASK3_PAIR_KIND_CANCEL && rx_payload_i[97:0]==0;
    reg record_ack_pending,record_wait_result;
    reg [95:0] record_ack_common;
    reg [1:0] record_ack_result;
    wire record_arm_ready,record_arm_accepted,record_arm_rejected,record_frame_ready;
    reg record_delivery_valid,record_protocol_fault,previous_record_fault;
    reg [97:0] record_delivery;
    wire arm_fire=live && media_current && rx_valid_i && rx_ready_o && record_arm && record_matches;
    wire record_frame_fire=!BLOCK_PCM && live && rx_valid_i && rx_ready_o && record_frame && record_matches && record_wire_common==record_active_common;
    wire record_cancel_fire=rx_valid_i && rx_ready_o && record_cancel && record_matches && record_wire_common==record_active_common;
    assign r_frame_ready=!record_delivery_valid && record_frame_ready && !record_cancel_fire && !record_protocol_fault;
    workstation_task3_pcm_block_rx record_blocks(
        .clk_i(clk_i),.reset_ni(reset_ni),.live_i(BLOCK_PCM && live && media_current),
        .start_i(record_arm_accepted),.token_i(record_active_common[31:0]),.first_index_i(record_active_first),
        .cancel_i(record_cancel_fire || record_fault_o || record_transport_fault_i || record_protocol_fault),
        .block_valid_i(live && rx_valid_i && rx_ready_o && r_block_packet),.block_payload_i(rx_payload_i),.block_length_i(rx_length_i),
        .frame_valid_o(r_frame_valid),.frame_ready_i(r_frame_ready),.frame_index_o(r_frame_index),.frame_pcm_o(r_frame_pcm),
        .credit_valid_o(r_credit_valid),.credit_ready_i(r_credit_ready),.credit_token_o(r_credit_token),.credit_limit_o(r_credit_limit),
        .empty_o(),.active_o(r_rx_active),.fault_o(r_rx_fault),.accepted_blocks_o(),.delivered_frames_o());
    workstation_task3_record_ingress recording_ingress(
        .clk_i(clk_i),.reset_ni(reset_ni),.link_ready_i(live),.panic_i(panic_i),
        .transport_fault_i(record_transport_fault_i || record_protocol_fault || (BLOCK_PCM && (r_rx_fault || media_cap_fault))),.object_idle_i(record_object_idle_i),
        .cancel_valid_i(record_cancel_fire),
        .cancel_session_i(session_i),.cancel_generation_i(record_active_local),
        .arm_valid_i(arm_fire),.arm_ready_o(record_arm_ready),.arm_session_i(rx_payload_i[161:130]),
        .arm_generation_i(record_next_local),.arm_physical_epoch_i(rx_payload_i[63:32]),.arm_first_sequence_i(rx_payload_i[31:0]),.arm_format_i(8'd1),
        .arm_accepted_o(record_arm_accepted),.arm_rejected_o(record_arm_rejected),
        .frame_valid_i(record_delivery_valid),.frame_ready_o(record_frame_ready),
        .frame_session_i(session_i),.frame_generation_i(record_active_local),.frame_physical_epoch_i(record_delivery[95:64]),
        .frame_sequence_i(record_delivery[63:32]),.frame_pcm_i(record_delivery[31:0]),
        .frame_44k1_i(record_delivery[97]),.frame_error_i(record_delivery[96]),
        .pcm_valid_o(record_pcm_valid_o),.source_allowed_o(record_source_allowed_o),.pcm_pair_o(record_pcm_o),.pcm_sequence_o(record_sequence_o),
        .physical_sequence_o(),.session_o(),.generation_o(),.physical_epoch_o(),.armed_o(),.fault_o(record_fault_o),
        .failure_code_o(record_failure_o),.queued_frames_o(),.accepted_frames_o(),.delivered_frames_o());
    wire mux_valid,mux_target,mux_write,mux_ready,mux_error;
    wire [11:0] mux_address;
    wire [31:0] mux_data,mux_response;
    wire [3:0] mux_strobes;
    workstation_task3_phone_command_mux command_mux(
        .clk_i(clk_i),.reset_ni(reset_ni),.valid_i(command_valid_i),.write_i(command_write_i),
        .address_i(command_address_i),.data_i(command_data_i),.strobes_i(command_strobes_i),
        .ready_o(command_ready_o),.response_error_o(response_error_o),.response_data_o(response_data_o),
        .valid_o(mux_valid),.target_o(mux_target),.write_o(mux_write),.address_o(mux_address),.data_o(mux_data),.strobes_o(mux_strobes),
        .ready_i(mux_ready),.response_error_i(mux_error),.response_data_i(mux_response));
    wire phone_arm_ready,phone_arm_tx,phone_cancel_tx,phone_request,phone_request_ready;
    wire phone_proxy_armed,phone_proxy_fault,phone_window_fault,phone_window_valid,phone_window_ready;
    wire [255:0] phone_window_payload;
    wire [5:0] phone_window_length;
    wire proxy_command_valid,proxy_command_target,proxy_command_write,proxy_command_ready,proxy_response_error;
    wire [11:0] proxy_command_address;
    wire [31:0] proxy_command_data,proxy_response_data;
    wire [3:0] proxy_command_strobes;
    wire phone_media_live=!PHONE_WINDOW_BLOCK || media_current;
    wire phone_batch_fault,phone_batch_busy,phone_batch_valid,phone_batch_ready,phone_window_busy,phone_window_flush;
    wire [255:0] phone_batch_payload;wire [5:0] phone_batch_length;
    assign phone_fault_o=phone_proxy_fault || phone_window_fault || phone_batch_fault;
    wire status_sent_current,phone_arm_tx_ready,phone_cancel_tx_ready;
    wire [31:0] phone_boot,phone_session,phone_generation,phone_sequence,phone_data;
    wire phone_target,phone_write,phone_response_ready;
    wire [11:0] phone_address;wire [3:0] phone_strobes;
    reg [95:0] attempted_common;
    wire phone_ack_packet=rx_channel_i==`TASK3_PAIR_CH_PHONE_ACK && rx_length_i==`TASK3_PAIR_PHONE_ACK_BYTES && rx_payload_i[255:163]==0;
    wire phone_ack_matches=rx_payload_i[160:65]=={phone_boot,phone_session,phone_generation};
    wire phone_arm_ack=phone_ack_packet && rx_payload_i[162:161]==`TASK3_PAIR_KIND_ARM && rx_payload_i[64:2]==0;
    wire phone_response=phone_ack_packet && rx_payload_i[162:161]==`TASK3_PAIR_KIND_DATA;
    wire phone_window_ack=PHONE_WINDOW_BLOCK && phone_ack_packet && rx_payload_i[162:161]==`TASK3_PAIR_KIND_WINDOW_ACK;
    wire phone_batch_reply=PHONE_BATCH && rx_channel_i==`TASK3_PAIR_CH_PHONE_ACK && rx_length_i==`TASK3_PAIR_PHONE_BATCH_REPLY_BYTES;
    wire window_local_valid,window_local_target,window_local_write,window_local_ready,window_local_error;
    wire [11:0] window_local_address;wire [31:0] window_local_data,window_local_response;wire [3:0] window_local_strobes;
    generate if(PHONE_BATCH)begin:g_phone_batch
        wire batch_ready,batch_error,legacy_valid,legacy_write;
        wire [31:0] batch_response,legacy_data;wire [11:0] legacy_address;wire [3:0] legacy_strobes;
        workstation_task3_phone_batch_w batch_w(
            .clk_i(clk_i),.reset_ni(reset_ni),.live_i(live && hci_classic_ready_i && phone_owner_ready_i && media_current && phone_proxy_armed && !phone_proxy_fault && !phone_window_fault),
            .capability_i(media_current),.token_i(generation_i),.local_boot_i(local_boot_i),.peer_boot_i(peer_boot_i),.session_i(session_i),.generation_i(generation_i),
            .local_valid_i(mux_valid && !mux_target),.local_write_i(mux_write),.local_address_i(mux_address),.local_data_i(mux_data),.local_strobes_i(mux_strobes),
            .local_ready_o(batch_ready),.local_response_error_o(batch_error),.local_response_data_o(batch_response),
            .legacy_valid_o(legacy_valid),.legacy_write_o(legacy_write),.legacy_address_o(legacy_address),.legacy_data_o(legacy_data),.legacy_strobes_o(legacy_strobes),
            .legacy_ready_i(window_local_ready && !mux_target),.legacy_response_error_i(window_local_error),.legacy_response_data_i(window_local_response),
            .request_valid_o(phone_batch_valid),.request_ready_i(phone_batch_ready),.request_payload_o(phone_batch_payload),.request_length_o(phone_batch_length),
            .response_valid_i(rx_valid_i && rx_ready_o && phone_batch_reply),.response_payload_i(rx_payload_i),.response_length_i(rx_length_i),
            .window_busy_i(phone_window_busy),.window_flush_o(phone_window_flush),.busy_o(phone_batch_busy),.fault_o(phone_batch_fault));
        assign window_local_valid=mux_target ? mux_valid:legacy_valid,window_local_target=mux_target;
        assign window_local_write=mux_target ? mux_write:legacy_write,window_local_address=mux_target ? mux_address:legacy_address;
        assign window_local_data=mux_target ? mux_data:legacy_data,window_local_strobes=mux_target ? mux_strobes:legacy_strobes;
        assign mux_ready=mux_target ? window_local_ready:batch_ready,mux_response=mux_target ? window_local_response:batch_response,mux_error=mux_target ? window_local_error:batch_error;
    end else begin:g_no_phone_batch
        assign window_local_valid=mux_valid,window_local_target=mux_target,window_local_write=mux_write,window_local_address=mux_address,window_local_data=mux_data,window_local_strobes=mux_strobes;
        assign mux_ready=window_local_ready,mux_response=window_local_response,mux_error=window_local_error;
        assign phone_batch_fault=0,phone_batch_busy=0,phone_batch_valid=0,phone_batch_payload=0,phone_batch_length=0,phone_window_flush=0;
    end endgenerate
    generate if(PHONE_WINDOW_BLOCK)begin:g_phone_window
        workstation_task3_phone_window_tx #(.EXTERNAL_FLUSH_ENABLE(PHONE_BATCH)) window_tx(
            .clk_i(clk_i),.reset_ni(reset_ni),.session_live_i(live && hci_classic_ready_i && phone_owner_ready_i && media_current),
            .armed_i(phone_proxy_armed && !phone_proxy_fault),.token_i(generation_i),
            .flush_i(phone_window_flush),
            .local_valid_i(window_local_valid),.local_target_i(window_local_target),.local_write_i(window_local_write),.local_address_i(window_local_address),
            .local_data_i(window_local_data),.local_strobes_i(window_local_strobes),.local_ready_o(window_local_ready),
            .local_response_data_o(window_local_response),.local_response_error_o(window_local_error),
            .proxy_valid_o(proxy_command_valid),.proxy_target_o(proxy_command_target),.proxy_write_o(proxy_command_write),
            .proxy_address_o(proxy_command_address),.proxy_data_o(proxy_command_data),.proxy_strobes_o(proxy_command_strobes),
            .proxy_ready_i(proxy_command_ready),.proxy_response_data_i(proxy_response_data),.proxy_response_error_i(proxy_response_error),
            .block_valid_o(phone_window_valid),.block_ready_i(phone_window_ready),.block_payload_o(phone_window_payload),.block_length_o(phone_window_length),
            .ack_valid_i(rx_valid_i && rx_ready_o && phone_window_ack && phone_ack_matches),
            .ack_first_sequence_i(rx_payload_i[64:33]),.ack_next_sequence_i(rx_payload_i[31:0]),.ack_error_i(rx_payload_i[32]),
            .busy_o(phone_window_busy),.fault_o(phone_window_fault));
    end else begin:g_legacy_phone_window
        assign proxy_command_valid=window_local_valid,proxy_command_target=window_local_target,proxy_command_write=window_local_write;
        assign proxy_command_address=window_local_address,proxy_command_data=window_local_data,proxy_command_strobes=window_local_strobes;
        assign window_local_ready=proxy_command_ready,window_local_response=proxy_response_data,window_local_error=proxy_response_error;
        assign phone_window_fault=0,phone_window_valid=0,phone_window_payload=0,phone_window_length=0,phone_window_busy=0;
    end endgenerate
    wire phone_arm_attempt=live && phone_media_live && hci_classic_ready_i && phone_owner_ready_i && status_sent_current &&
        phone_arm_ready && attempted_common!=common;
    workstation_task3_phone_command_proxy #(.CAPTURE_ARM(BLOCK_PCM)) phone_proxy(
        .clk_i(clk_i),.reset_ni(reset_ni),.link_ready_i(live && hci_classic_ready_i && phone_owner_ready_i && phone_media_live && !phone_window_fault && !phone_batch_fault),.panic_i(panic_i),
        .arm_valid_i(phone_arm_attempt),.arm_ready_o(phone_arm_ready),.arm_boot_i(peer_boot_i),.arm_session_i(session_i),.arm_generation_i(generation_i),
        .arm_accepted_o(),.arm_rejected_o(),.arm_tx_valid_o(phone_arm_tx),.arm_tx_ready_i(phone_arm_tx_ready),
        .arm_result_accepted_i(rx_valid_i && rx_ready_o && phone_arm_ack && phone_ack_matches && rx_payload_i[1]),
        .arm_result_rejected_i(rx_valid_i && rx_ready_o && phone_arm_ack && phone_ack_matches && rx_payload_i[0]),
        .boot_o(phone_boot),.session_o(phone_session),.generation_o(phone_generation),
        .cancel_tx_valid_o(phone_cancel_tx),.cancel_tx_ready_i(phone_cancel_tx_ready),
        .cancel_valid_i(1'b0),.cancel_session_i(32'd0),.cancel_generation_i(32'd0),
        .cpu_command_valid_i(proxy_command_valid),.cpu_command_target_i(proxy_command_target),.cpu_command_write_i(proxy_command_write),
        .cpu_command_address_i(proxy_command_address),.cpu_command_data_i(proxy_command_data),.cpu_command_strobes_i(proxy_command_strobes),
        .cpu_command_ready_o(proxy_command_ready),.cpu_response_data_o(proxy_response_data),.cpu_response_error_o(proxy_response_error),
        .request_valid_o(phone_request),.request_ready_i(phone_request_ready),.request_sequence_o(phone_sequence),
        .request_target_o(phone_target),.request_write_o(phone_write),.request_address_o(phone_address),.request_data_o(phone_data),.request_strobes_o(phone_strobes),
        .response_valid_i(rx_valid_i && phone_response && phone_ack_matches),.response_ready_o(phone_response_ready),
        .response_boot_i(rx_payload_i[160:129]),.response_session_i(rx_payload_i[128:97]),.response_generation_i(rx_payload_i[96:65]),
        .response_sequence_i(rx_payload_i[64:33]),.response_error_i(rx_payload_i[32]),.response_data_i(rx_payload_i[31:0]),
        .armed_o(phone_proxy_armed),.fault_o(phone_proxy_fault),.failure_code_o(),.completed_commands_o());
    always @*begin
        rx_ready_o=reset_ni;
        if(live)begin
            if(!BLOCK_PCM && analysis_desc)rx_ready_o=cnn_desc_ready_i;
            else if(!BLOCK_PCM && analysis_frame)rx_ready_o=cnn_frame_ready_i;
            else if(!BLOCK_PCM && analysis_seal)rx_ready_o=cnn_seal_ready_i;
            else if(!BLOCK_PCM && analysis_cancel)rx_ready_o=cnn_cancel_ready_i;
            // Even a busy/nonempty object gets an explicit real-arm rejection;
            // it must not hold the shared transport indefinitely.
            else if(record_matches && record_arm)rx_ready_o=!record_ack_pending && !record_wait_result;
            else if(!BLOCK_PCM && record_matches && record_wire_common==record_active_common && record_frame)rx_ready_o=record_fault_o || (!record_delivery_valid && record_frame_ready);
            else if(phone_ack_matches && phone_response)rx_ready_o=phone_response_ready;
        end
    end
    wire [197:0] status_now={local_boot_i,peer_boot_i,session_i,generation_i,hci_epoch_i,hci_generation_i,hci_classic_ready_i,backend_ready_i,model_status_i};
    reg [197:0] status_previous;
    reg [197:0] status_sent;
    reg have_sent_status;
    assign status_sent_current=have_sent_status && status_sent==status_now;
    reg status_pending;reg [18:0] status_age;
    reg demand_previous,demand_pending,demand_cancel;
    wire slot_free=!tx_valid_o && live;
    assign phone_cancel_tx_ready=slot_free && phone_cancel_tx;
    wire cap_take=BLOCK_PCM && slot_free && !phone_cancel_tx && media_cap_pending;
    wire a_fault_take=BLOCK_PCM && slot_free && !phone_cancel_tx && !cap_take && a_fault_pending;
    wire r_fault_take=BLOCK_PCM && slot_free && !phone_cancel_tx && !cap_take && !a_fault_pending && r_fault_pending;
    wire urgent_slot=slot_free && !phone_cancel_tx && !cap_take && !a_fault_take && !r_fault_take;
    wire take_record_ack=urgent_slot && record_ack_pending;
    wire take_demand=urgent_slot && !record_ack_pending && demand_pending && record_source_needed_i==demand_previous;
    wire normal_slot=urgent_slot && !record_ack_pending && !demand_pending;
    assign phone_arm_tx_ready=normal_slot && phone_arm_tx;
    reg [1:0] normal_turn;
    reg choose_phone,choose_credit,choose_result;
    wire phone_flow_pending=phone_request || phone_window_valid || phone_batch_valid;
    wire credit_pending=(a_credit_valid && !a_wire_sealed) || r_credit_valid;
    wire result_pending=cnn_terminal_valid_i || cnn_score_valid_i || status_pending;
    always_comb begin
        choose_phone=0;choose_credit=0;choose_result=0;
        if(!BLOCK_PCM)begin choose_phone=phone_request;choose_result=!phone_request;end
        else case(normal_turn)
            0:if(phone_flow_pending)choose_phone=1;else if(credit_pending)choose_credit=1;else if(result_pending)choose_result=1;
            1:if(credit_pending)choose_credit=1;else if(result_pending)choose_result=1;else if(phone_flow_pending)choose_phone=1;
            default:if(result_pending)choose_result=1;else if(phone_flow_pending)choose_phone=1;else if(credit_pending)choose_credit=1;
        endcase
    end
    wire fair_slot=normal_slot && !phone_arm_tx;
    assign phone_request_ready=fair_slot && choose_phone && phone_request;
    assign phone_batch_ready=fair_slot && choose_phone && !phone_request && phone_batch_valid;
    assign phone_window_ready=fair_slot && choose_phone && !phone_request && !phone_batch_valid && phone_window_valid;
    wire credit_slot=fair_slot && choose_credit;
    assign a_credit_ready=BLOCK_PCM && credit_slot && a_credit_valid && !a_wire_sealed && (!r_credit_valid || !prefer_record_credit);
    assign r_credit_ready=BLOCK_PCM && credit_slot && r_credit_valid && (!a_credit_valid || a_wire_sealed || prefer_record_credit);
    assign cnn_terminal_ready_o=fair_slot && choose_result;
    assign cnn_score_ready_o=cnn_terminal_ready_o && !cnn_terminal_valid_i;
    wire take_status=cnn_score_ready_o && !cnn_score_valid_i && status_pending;
    wire known_shape=analysis_desc || (!BLOCK_PCM && analysis_frame) || analysis_seal || analysis_cancel || record_arm || (!BLOCK_PCM && record_frame) || record_cancel || phone_arm_ack || phone_response || phone_window_ack || phone_batch_reply || a_block_packet || r_block_packet || media_cap_packet;
    wire stale=(record_packet && (!record_matches || (record_frame || record_cancel) && record_wire_common!=record_active_common)) ||
        (phone_ack_packet && !phone_ack_matches) || (media_cap_packet && !media_cap_matches);
    always @(posedge clk_i or negedge reset_ni)begin
        if(!reset_ni)begin
            tx_valid_o<=0;tx_channel_o<=0;tx_payload_o<=0;tx_length_o<=0;attempted_common<=0;observed_context<=0;
            media_cap_ready<=0;media_cap_fault<=0;media_cap_pending<=1;media_cap_age<=0;media_cap_send_age<=0;
            a_desc_pending<=0;a_seal_pending<=0;a_cancel_pending<=0;a_active<=0;a_protocol_fault<=0;a_wire_sealed<=0;
            a_descriptor<=0;a_seal<=0;a_context<=0;a_retired_context<=0;a_cancel<=0;
            a_fault_pending<=0;r_fault_pending<=0;a_fault_token<=0;r_fault_token<=0;a_fault_reason<=0;r_fault_reason<=0;
            previous_a_fault<=0;previous_r_fault<=0;prefer_record_credit<=0;normal_turn<=0;
            record_ack_pending<=0;record_wait_result<=0;record_ack_common<=0;record_ack_result<=0;
            record_active_common<=0;record_retired_common<=0;record_local_counter<=0;record_active_local<=0;record_active_epoch<=0;record_active_first<=0;
            record_delivery_valid<=0;record_delivery<=0;record_protocol_fault<=0;previous_record_fault<=0;
            status_previous<=0;status_sent<=0;have_sent_status<=0;status_pending<=1;status_age<=0;malformed_packets_o<=0;stale_packets_o<=0;
            demand_previous<=0;demand_pending<=0;demand_cancel<=0;
        end else begin
            record_delivery_valid<=0;record_protocol_fault<=0;
            if(!live)begin
                media_cap_ready<=0;media_cap_fault<=0;media_cap_pending<=1;media_cap_age<=0;media_cap_send_age<=0;
                a_desc_pending<=0;a_seal_pending<=0;a_cancel_pending<=0;a_active<=0;a_protocol_fault<=0;a_wire_sealed<=0;
                a_fault_pending<=0;r_fault_pending<=0;previous_a_fault<=0;previous_r_fault<=0;prefer_record_credit<=0;normal_turn<=0;
            end else if(BLOCK_PCM)begin
                if(media_cap_age<MEDIA_CAP_TIMEOUT_CYCLES)media_cap_age<=media_cap_age+1'b1;
                else begin media_cap_ready<=0;media_cap_fault<=1;end
                if(media_cap_send_age==499999)begin media_cap_pending<=1;media_cap_send_age<=0;end
                else media_cap_send_age<=media_cap_send_age+1'b1;
                if(rx_valid_i && rx_ready_o && rx_channel_i==`TASK3_PAIR_CH_MEDIA_CAPS)begin
                    if(media_cap_packet && media_cap_matches && !media_cap_fault)begin media_cap_ready<=1;media_cap_age<=0;end
                    else begin media_cap_ready<=0;media_cap_fault<=1;end
                end
                if(cap_take)media_cap_pending<=0;
                if((phone_request && phone_request_ready) || (phone_window_valid && phone_window_ready) || (phone_batch_valid && phone_batch_ready))normal_turn<=1;
                else if(a_credit_ready || r_credit_ready)normal_turn<=2;
                else if((cnn_terminal_valid_i && cnn_terminal_ready_o) || (cnn_score_valid_i && cnn_score_ready_o) || take_status)normal_turn<=0;
                if(a_credit_ready)prefer_record_credit<=1;
                if(r_credit_ready)prefer_record_credit<=0;
                if(a_fault_take)a_fault_pending<=0;
                if(r_fault_take)r_fault_pending<=0;
                if(cnn_desc_valid_o && cnn_desc_ready_i)a_desc_pending<=0;
                if(cnn_seal_valid_o && cnn_seal_ready_i)a_seal_pending<=0;
                if(cnn_cancel_valid_o && cnn_cancel_ready_i)a_cancel_pending<=0;
                if(cnn_terminal_valid_i && cnn_terminal_ready_o && cnn_terminal_i[163:36]==a_context)begin a_active<=0;a_seal_pending<=0;a_wire_sealed<=0;end
                if(a_desc_fire)begin
                    if(a_desc_peer && a_desc_fresh && !a_active && !a_cancel_pending)begin
                        a_descriptor<=rx_payload_i[199:0];a_context<=rx_payload_i[199:72];a_retired_context<=rx_payload_i[199:72];
                        a_desc_pending<=1;a_active<=1;a_seal_pending<=0;a_protocol_fault<=0;a_wire_sealed<=0;previous_a_fault<=0;
                    end else if(a_active) a_protocol_fault<=1;
                end
                if(rx_valid_i && rx_ready_o && analysis_seal && media_current)begin
                    if(a_active && !a_wire_sealed && rx_payload_i[191:64]==a_context)begin a_seal<=rx_payload_i[191:0];a_seal_pending<=1;a_wire_sealed<=1;end
                    else if(a_active)a_protocol_fault<=1;
                end
                if(rx_valid_i && rx_ready_o && analysis_frame && a_active)a_protocol_fault<=1;
                if(a_after_seal && a_active)a_protocol_fault<=1;
                previous_a_fault<=a_fault_event;
                previous_r_fault<=r_rx_fault || record_protocol_fault;
                if(a_fault_event && !previous_a_fault)begin
                    a_fault_pending<=1;a_fault_token<=a_context[31:0];a_fault_reason<=1;
                    a_cancel_pending<=1;a_cancel<=a_context;a_active<=0;a_desc_pending<=0;a_seal_pending<=0;a_wire_sealed<=0;
                end
                if((r_rx_fault || record_protocol_fault) && !previous_r_fault)begin
                    r_fault_pending<=1;r_fault_token<=record_active_common[31:0];r_fault_reason<=1;
                end
                if(a_cancel_fire)begin
                    a_active<=0;a_desc_pending<=0;a_seal_pending<=0;a_protocol_fault<=0;a_wire_sealed<=0;
                    a_cancel_pending<=1;a_cancel<=a_context;
                end
            end
            observed_context<={local_boot_i,common};
            previous_record_fault<=record_fault_o;
            if(phone_arm_attempt)attempted_common<=common;
            if(!live)begin
                tx_valid_o<=0;record_ack_pending<=0;record_wait_result<=0;have_sent_status<=0;status_pending<=1;
                demand_previous<=0;demand_pending<=0;
            end
            else if(tx_valid_o && tx_ready_i)begin
                tx_valid_o<=0;
                if(tx_channel_o==`TASK3_PAIR_CH_STATUS)begin status_sent<=tx_payload_o[197:0];have_sent_status<=1;end
            end
            if(rx_valid_i && rx_ready_o)begin
                if(!known_shape)begin
                    malformed_packets_o<=malformed_packets_o+1'b1;
                    if(rx_channel_i==`TASK3_PAIR_CH_RECORD || (BLOCK_PCM && rx_channel_i==`TASK3_PAIR_CH_RECORD_BLOCK))record_protocol_fault<=1;
                    if(BLOCK_PCM && rx_channel_i==`TASK3_PAIR_CH_ANALYSIS)a_protocol_fault<=1;
                end else if(stale)stale_packets_o<=stale_packets_o+1'b1;
            end
            if(live && record_source_needed_i!=demand_previous)begin
                demand_previous<=record_source_needed_i;demand_pending<=1;demand_cancel<=!record_source_needed_i;
            end
            if(arm_fire)begin
                record_wait_result<=1;record_ack_common<=record_wire_common;
                if(record_next_local!=0)begin
                    record_local_counter<=record_next_local;record_active_local<=record_next_local;
                    record_active_common<=record_wire_common;record_retired_common<=record_wire_common;
                    record_active_epoch<=rx_payload_i[63:32];record_active_first<=rx_payload_i[31:0];
                end
            end
            if(record_wait_result && (record_arm_accepted || record_arm_rejected))begin
                record_wait_result<=0;record_ack_pending<=1;record_ack_result<={record_arm_accepted,record_arm_rejected};
            end
            if(record_frame_fire && !record_fault_o)begin record_delivery_valid<=1;record_delivery<=rx_payload_i[97:0];end
            if(BLOCK_PCM && r_frame_valid && r_frame_ready && !record_fault_o)begin
                record_delivery_valid<=1;record_delivery<={2'b00,record_active_epoch,r_frame_index,r_frame_pcm};
            end
            if(live && record_fault_o && !previous_record_fault)begin
                record_ack_pending<=1;record_ack_common<=record_active_common;record_ack_result<=2'b01;
            end
            if(status_now!=status_previous || status_age==19'd499999)begin
                status_pending<=1;status_previous<=status_now;status_age<=0;
            end else status_age<=status_age+1'b1;
            if(slot_free)begin
                tx_payload_o<=0;
                if(phone_cancel_tx_ready)begin
                    tx_valid_o<=1;tx_channel_o<=`TASK3_PAIR_CH_PHONE;tx_length_o<=`TASK3_PAIR_PHONE_BYTES;
                    tx_payload_o[179:0]<={`TASK3_PAIR_KIND_CANCEL,phone_boot,phone_session,phone_generation,82'd0};
                end else if(cap_take)begin
                    tx_valid_o<=1;tx_channel_o<=`TASK3_PAIR_CH_MEDIA_CAPS;tx_length_o<=`TASK3_PAIR_MEDIA_CAPS_BYTES;
                    tx_payload_o[223:0]<={local_boot_i,peer_boot_i,session_i,generation_i,`TASK3_PAIR_MEDIA_MAGIC,MEDIA_VERSION,MEDIA_FEATURES};
                end else if(a_fault_take || r_fault_take)begin
                    tx_valid_o<=1;tx_channel_o<=`TASK3_PAIR_CH_MEDIA_FAULT;tx_length_o<=`TASK3_PAIR_MEDIA_FAULT_BYTES;
                    tx_payload_o[36:0]<=a_fault_take?{a_fault_reason,1'b0,a_fault_token}:{r_fault_reason,1'b1,r_fault_token};
                end else if(take_record_ack)begin
                    record_ack_pending<=0;tx_valid_o<=1;tx_channel_o<=`TASK3_PAIR_CH_RECORD_ACK;tx_length_o<=`TASK3_PAIR_RECORD_ACK_BYTES;
                    tx_payload_o[97:0]<={record_ack_common,record_ack_result};
                end else if(take_demand)begin
                    demand_pending<=0;tx_valid_o<=1;tx_channel_o<=`TASK3_PAIR_CH_RECORD_DEMAND;tx_length_o<=`TASK3_PAIR_RECORD_DEMAND_BYTES;
                    tx_payload_o[97:0]<={demand_cancel?`TASK3_PAIR_KIND_CANCEL:`TASK3_PAIR_KIND_ARM,common};
                end else if(phone_arm_tx_ready)begin
                    tx_valid_o<=1;tx_channel_o<=`TASK3_PAIR_CH_PHONE;tx_length_o<=`TASK3_PAIR_PHONE_BYTES;
                    tx_payload_o[179:0]<={`TASK3_PAIR_KIND_ARM,phone_boot,phone_session,phone_generation,82'd0};
                end else if(phone_request && phone_request_ready)begin
                    tx_valid_o<=1;tx_channel_o<=`TASK3_PAIR_CH_PHONE;tx_length_o<=`TASK3_PAIR_PHONE_BYTES;
                    tx_payload_o[179:0]<={`TASK3_PAIR_KIND_DATA,phone_boot,phone_session,phone_generation,phone_sequence,phone_target,phone_write,phone_address,phone_data,phone_strobes};
                end else if(phone_batch_valid && phone_batch_ready)begin
                    tx_valid_o<=1;tx_channel_o<=`TASK3_PAIR_CH_PHONE;tx_length_o<=phone_batch_length;tx_payload_o<=phone_batch_payload;
                end else if(phone_window_valid && phone_window_ready)begin
                    tx_valid_o<=1;tx_channel_o<=`TASK3_PAIR_CH_PHONE_WINDOW;tx_length_o<=phone_window_length;tx_payload_o<=phone_window_payload;
                end else if(a_credit_ready || r_credit_ready)begin
                    tx_valid_o<=1;tx_channel_o<=`TASK3_PAIR_CH_BLOCK_CREDIT;tx_length_o<=`TASK3_PAIR_CREDIT_BYTES;
                    tx_payload_o[64:0]<=a_credit_ready?{1'b0,a_credit_limit,a_credit_token}:{1'b1,r_credit_limit,r_credit_token};
                end else if(cnn_terminal_valid_i && cnn_terminal_ready_o)begin
                    tx_valid_o<=1;tx_channel_o<=`TASK3_PAIR_CH_RESULT;tx_length_o<=`TASK3_PAIR_RESULT_BYTES;
                    tx_payload_o[167:0]<={1'b1,3'd0,cnn_terminal_i};
                end else if(cnn_score_valid_i && cnn_score_ready_o)begin
                    tx_valid_o<=1;tx_channel_o<=`TASK3_PAIR_CH_RESULT;tx_length_o<=`TASK3_PAIR_RESULT_BYTES;
                    tx_payload_o[167:0]<={1'b0,cnn_score_i};
                end else if(take_status)begin
                    status_pending<=0;tx_valid_o<=1;tx_channel_o<=`TASK3_PAIR_CH_STATUS;tx_length_o<=`TASK3_PAIR_STATUS_BYTES;
                    tx_payload_o[197:0]<=status_now;
                end
            end
        end
    end
endmodule
