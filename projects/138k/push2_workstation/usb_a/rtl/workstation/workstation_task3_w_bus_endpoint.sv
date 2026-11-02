`timescale 1ns/1ps
`include "rtl/workstation/task3_paired_channels.vh"
// W business endpoint after validated electrical/framing/CDC transport. No
// incoming file/recording/phone credit is connected to a physical sample tick.
module workstation_task3_w_bus_endpoint (
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
    wire context_current=observed_context=={local_boot_i,common};
    wire live=reset_ni && link_ready_i && !panic_i && context_current &&
        local_boot_i!=0 && peer_boot_i!=0 && session_i!=0 && generation_i!=0;
    wire analysis_packet=rx_channel_i==`TASK3_PAIR_CH_ANALYSIS && rx_length_i==`TASK3_PAIR_ANALYSIS_BYTES && rx_payload_i[255:202]==0;
    wire analysis_desc=analysis_packet && rx_payload_i[201:200]==0;
    wire analysis_frame=analysis_packet && rx_payload_i[201:200]==1 && rx_payload_i[199:192]==0;
    wire analysis_seal=analysis_packet && rx_payload_i[201:200]==2 && rx_payload_i[199:192]==0;
    wire analysis_cancel=rx_channel_i==`TASK3_PAIR_CH_ANALYSIS_CANCEL && rx_length_i==`TASK3_PAIR_CANCEL_BYTES && rx_payload_i[255:128]==0;
    assign cnn_desc_valid_o=live && rx_valid_i && analysis_desc;
    assign cnn_desc_o=rx_payload_i[199:0];
    assign cnn_frame_valid_o=live && rx_valid_i && analysis_frame;
    assign cnn_frame_o=rx_payload_i[191:0];
    assign cnn_seal_valid_o=live && rx_valid_i && analysis_seal;
    assign cnn_seal_o=rx_payload_i[191:0];
    assign cnn_cancel_valid_o=reset_ni && rx_valid_i && analysis_cancel;
    assign cnn_cancel_o=rx_payload_i[127:0];
    wire record_packet=rx_channel_i==`TASK3_PAIR_CH_RECORD && rx_length_i==`TASK3_PAIR_RECORD_BYTES && rx_payload_i[255:196]==0;
    // Record generation is independently allocated by M. Map it to a W-root
    // monotonic ingress generation, so either board can reboot independently.
    wire [95:0] record_wire_common=rx_payload_i[193:98];
    wire record_matches=record_wire_common[95:32]=={peer_boot_i,session_i} && record_wire_common[31:0]!=0;
    reg [95:0] record_active_common,record_retired_common;
    reg [31:0] record_local_counter,record_active_local;
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
    wire arm_fire=live && rx_valid_i && rx_ready_o && record_arm && record_matches;
    wire record_frame_fire=live && rx_valid_i && rx_ready_o && record_frame && record_matches && record_wire_common==record_active_common;
    workstation_task3_record_ingress recording_ingress(
        .clk_i(clk_i),.reset_ni(reset_ni),.link_ready_i(live),.panic_i(panic_i),
        .transport_fault_i(record_transport_fault_i || record_protocol_fault),.object_idle_i(record_object_idle_i),
        .cancel_valid_i(rx_valid_i && record_cancel && record_matches && record_wire_common==record_active_common),
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
    wire status_sent_current,phone_arm_tx_ready,phone_cancel_tx_ready;
    wire [31:0] phone_boot,phone_session,phone_generation,phone_sequence,phone_data;
    wire phone_target,phone_write,phone_response_ready;
    wire [11:0] phone_address;wire [3:0] phone_strobes;
    reg [95:0] attempted_common;
    wire phone_ack_packet=rx_channel_i==`TASK3_PAIR_CH_PHONE_ACK && rx_length_i==`TASK3_PAIR_PHONE_ACK_BYTES && rx_payload_i[255:163]==0;
    wire phone_ack_matches=rx_payload_i[160:65]=={phone_boot,phone_session,phone_generation};
    wire phone_arm_ack=phone_ack_packet && rx_payload_i[162:161]==`TASK3_PAIR_KIND_ARM && rx_payload_i[64:2]==0;
    wire phone_response=phone_ack_packet && rx_payload_i[162:161]==`TASK3_PAIR_KIND_DATA;
    wire phone_arm_attempt=live && hci_classic_ready_i && phone_owner_ready_i && status_sent_current &&
        phone_arm_ready && attempted_common!=common;
    workstation_task3_phone_command_proxy phone_proxy(
        .clk_i(clk_i),.reset_ni(reset_ni),.link_ready_i(live && hci_classic_ready_i && phone_owner_ready_i),.panic_i(panic_i),
        .arm_valid_i(phone_arm_attempt),.arm_ready_o(phone_arm_ready),.arm_boot_i(peer_boot_i),.arm_session_i(session_i),.arm_generation_i(generation_i),
        .arm_accepted_o(),.arm_rejected_o(),.arm_tx_valid_o(phone_arm_tx),.arm_tx_ready_i(phone_arm_tx_ready),
        .arm_result_accepted_i(rx_valid_i && rx_ready_o && phone_arm_ack && phone_ack_matches && rx_payload_i[1]),
        .arm_result_rejected_i(rx_valid_i && rx_ready_o && phone_arm_ack && phone_ack_matches && rx_payload_i[0]),
        .boot_o(phone_boot),.session_o(phone_session),.generation_o(phone_generation),
        .cancel_tx_valid_o(phone_cancel_tx),.cancel_tx_ready_i(phone_cancel_tx_ready),
        .cancel_valid_i(1'b0),.cancel_session_i(32'd0),.cancel_generation_i(32'd0),
        .cpu_command_valid_i(mux_valid),.cpu_command_target_i(mux_target),.cpu_command_write_i(mux_write),
        .cpu_command_address_i(mux_address),.cpu_command_data_i(mux_data),.cpu_command_strobes_i(mux_strobes),
        .cpu_command_ready_o(mux_ready),.cpu_response_data_o(mux_response),.cpu_response_error_o(mux_error),
        .request_valid_o(phone_request),.request_ready_i(phone_request_ready),.request_sequence_o(phone_sequence),
        .request_target_o(phone_target),.request_write_o(phone_write),.request_address_o(phone_address),.request_data_o(phone_data),.request_strobes_o(phone_strobes),
        .response_valid_i(rx_valid_i && phone_response && phone_ack_matches),.response_ready_o(phone_response_ready),
        .response_boot_i(rx_payload_i[160:129]),.response_session_i(rx_payload_i[128:97]),.response_generation_i(rx_payload_i[96:65]),
        .response_sequence_i(rx_payload_i[64:33]),.response_error_i(rx_payload_i[32]),.response_data_i(rx_payload_i[31:0]),
        .armed_o(),.fault_o(phone_fault_o),.failure_code_o(),.completed_commands_o());
    always @*begin
        rx_ready_o=reset_ni;
        if(live)begin
            if(analysis_desc)rx_ready_o=cnn_desc_ready_i;
            else if(analysis_frame)rx_ready_o=cnn_frame_ready_i;
            else if(analysis_seal)rx_ready_o=cnn_seal_ready_i;
            else if(analysis_cancel)rx_ready_o=cnn_cancel_ready_i;
            // Even a busy/nonempty object gets an explicit real-arm rejection;
            // it must not hold the shared transport indefinitely.
            else if(record_matches && record_arm)rx_ready_o=!record_ack_pending && !record_wait_result;
            else if(record_matches && record_wire_common==record_active_common && record_frame)rx_ready_o=record_fault_o || (!record_delivery_valid && record_frame_ready);
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
    wire take_record_ack=slot_free && !phone_cancel_tx && record_ack_pending;
    wire take_demand=slot_free && !phone_cancel_tx && !record_ack_pending && demand_pending && record_source_needed_i==demand_previous;
    assign phone_arm_tx_ready=slot_free && !phone_cancel_tx && !record_ack_pending && !demand_pending && phone_arm_tx;
    assign phone_request_ready=slot_free && !phone_cancel_tx && !record_ack_pending && !demand_pending && !phone_arm_tx && phone_request;
    assign cnn_terminal_ready_o=slot_free && !phone_cancel_tx && !record_ack_pending && !demand_pending && !phone_arm_tx && !phone_request;
    assign cnn_score_ready_o=cnn_terminal_ready_o && !cnn_terminal_valid_i;
    wire take_status=cnn_score_ready_o && !cnn_score_valid_i && status_pending;
    wire known_shape=analysis_desc || analysis_frame || analysis_seal || analysis_cancel || record_arm || record_frame || record_cancel || phone_arm_ack || phone_response;
    wire stale=(record_packet && (!record_matches || (record_frame || record_cancel) && record_wire_common!=record_active_common)) ||
        (phone_ack_packet && !phone_ack_matches);
    always @(posedge clk_i or negedge reset_ni)begin
        if(!reset_ni)begin
            tx_valid_o<=0;tx_channel_o<=0;tx_payload_o<=0;tx_length_o<=0;attempted_common<=0;observed_context<=0;
            record_ack_pending<=0;record_wait_result<=0;record_ack_common<=0;record_ack_result<=0;
            record_active_common<=0;record_retired_common<=0;record_local_counter<=0;record_active_local<=0;
            record_delivery_valid<=0;record_delivery<=0;record_protocol_fault<=0;previous_record_fault<=0;
            status_previous<=0;status_sent<=0;have_sent_status<=0;status_pending<=1;status_age<=0;malformed_packets_o<=0;stale_packets_o<=0;
            demand_previous<=0;demand_pending<=0;demand_cancel<=0;
        end else begin
            record_delivery_valid<=0;record_protocol_fault<=0;
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
                    if(rx_channel_i==`TASK3_PAIR_CH_RECORD)record_protocol_fault<=1;
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
                end
            end
            if(record_wait_result && (record_arm_accepted || record_arm_rejected))begin
                record_wait_result<=0;record_ack_pending<=1;record_ack_result<={record_arm_accepted,record_arm_rejected};
            end
            if(record_frame_fire && !record_fault_o)begin record_delivery_valid<=1;record_delivery<=rx_payload_i[97:0];end
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
