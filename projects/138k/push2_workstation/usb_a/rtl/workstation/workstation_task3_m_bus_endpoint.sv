`timescale 1ns/1ps
`include "rtl/workstation/task3_paired_channels.vh"
// M endpoint AFTER an ordered, measured transport. All ports use clk_i.
// Physical-frame observations have no ready signal; congestion fails only
// the recording branch. Offline TF may pause its single native decoder.
module workstation_task3_m_bus_endpoint #(
    parameter integer RECORD_DEMAND_TIMEOUT_CYCLES=50000000
) (
    input wire clk_i,reset_ni,link_ready_i,panic_i,
    input wire [31:0] local_boot_i,peer_boot_i,session_i,generation_i,
    input wire rx_valid_i,output reg rx_ready_o,
    input wire [3:0] rx_channel_i,input wire [255:0] rx_payload_i,input wire [5:0] rx_length_i,
    output reg tx_valid_o,input wire tx_ready_i,
    output reg [3:0] tx_channel_o,output reg [255:0] tx_payload_o,output reg [5:0] tx_length_o,
    input wire analysis_start_i,output wire analysis_ready_o,
    input wire analysis_cancel_i,analysis_pcm_valid_i,analysis_pcm_last_i,
    output wire analysis_pcm_ready_o,input wire [31:0] analysis_pcm_i,
    output wire analysis_failed_o,analysis_busy_o,analysis_done_o,
    output wire push_score_valid_o,input wire push_score_ready_i,output wire [6:0] push_score_note_o,
    input wire record_arm_i,record_cancel_i,
    input wire frame_valid_i,frame_44k1_i,frame_error_i,
    input wire [31:0] frame_epoch_i,frame_sequence_i,frame_pcm_i,
    output wire record_armed_o,record_fault_o,
    input wire phone_owner_idle_i,
    output wire phone_owner_live_o,phone_command_valid_o,
    input wire phone_command_ready_i,
    output wire phone_command_target_o,phone_command_write_o,
    output wire [11:0] phone_command_address_o,
    output wire [31:0] phone_command_data_o,output wire [3:0] phone_command_strobes_o,
    input wire [31:0] phone_response_data_i,input wire phone_response_error_i,
    output reg hci_ready_o,output wire [31:0] hci_epoch_o,hci_generation_o,
    output wire [3:0] model_status_o,
    output reg [31:0] malformed_packets_o,stale_packets_o
);
    wire live=reset_ni && link_ready_i && !panic_i && local_boot_i!=0 && peer_boot_i!=0 && session_i!=0 && generation_i!=0;
    wire [95:0] common={local_boot_i,session_i,generation_i};
    reg [127:0] configured_identity;
    reg [31:0] next_job;
    wire new_identity=configured_identity!={local_boot_i,peer_boot_i,session_i,generation_i};
    // A FAT32 file contains at most 2^30 stereo16 frames, hence <65536
    // native 96000-frame clips. Reserve that entire interval for each job.
    wire job_space=next_job!=0 && next_job<=32'hfffe0000;
    wire source_ready,source_done,source_failed,collector_failed;
    wire desc_valid,desc_ready,frame_valid,frame_ready,seal_valid,seal_ready,cancel_valid,cancel_ready;
    wire [199:0] desc;wire [191:0] frame,seal;wire [127:0] cancel;
    wire arm_valid,arm_ready,arm_append,file_last,completion_valid;
    wire [127:0] arm_identity;wire [163:0] completion;
    assign analysis_ready_o=live && !new_identity && job_space && source_ready;
    wire start_fire=analysis_start_i && analysis_ready_o;
    workstation_task3_tf_analysis_source source_m(
        .clk_i(clk_i),.reset_ni(reset_ni),.link_ready_i(live && !new_identity),.transport_fault_i(1'b0),
        .cancel_i(analysis_cancel_i),.panic_i(panic_i),.start_valid_i(start_fire),.start_ready_o(source_ready),
        .start_boot_i(local_boot_i),.start_session_i(session_i),.start_task_id_i(next_job),.start_generation_i(next_job),.clip_frames_i(32'd96000),
        .pcm_valid_i(analysis_pcm_valid_i),.pcm_ready_o(analysis_pcm_ready_o),.pcm_pair_i(analysis_pcm_i),.pcm_last_i(analysis_pcm_last_i),
        .desc_valid_o(desc_valid),.desc_ready_i(desc_ready),.desc_o(desc),.frame_valid_o(frame_valid),.frame_ready_i(frame_ready),.frame_o(frame),
        .seal_valid_o(seal_valid),.seal_ready_i(seal_ready),.seal_o(seal),.cancel_valid_o(cancel_valid),.cancel_ready_i(cancel_ready),.cancel_o(cancel),
        .arm_valid_o(arm_valid),.arm_ready_i(arm_ready),.arm_identity_o(arm_identity),.arm_append_o(arm_append),.chunk_file_last_o(file_last),
        .completion_valid_i(completion_valid),.completion_i(completion),.busy_o(analysis_busy_o),.done_o(source_done),.failed_o(source_failed),
        .failure_code_o(),.total_frames_o(),.completed_clips_o());
    wire result_packet=rx_channel_i==`TASK3_PAIR_CH_RESULT && rx_length_i==`TASK3_PAIR_RESULT_BYTES && rx_payload_i[255:168]==0 &&
        (!rx_payload_i[167] || rx_payload_i[166:164]==0);
    wire score_ready,terminal_ready;
    workstation_task3_score_commit_m collector_m(
        .clk_i(clk_i),.reset_ni(reset_ni),.link_ready_i(live && !new_identity),.cancel_i(analysis_cancel_i || source_failed),.panic_i(panic_i),
        .arm_valid_i(arm_valid),.arm_ready_o(arm_ready),.arm_identity_i(arm_identity),.arm_append_i(arm_append),.chunk_file_last_i(file_last),
        .score_valid_i(live && rx_valid_i && result_packet && !rx_payload_i[167]),.score_ready_o(score_ready),.score_i(rx_payload_i[166:0]),
        .terminal_valid_i(live && rx_valid_i && result_packet && rx_payload_i[167]),.terminal_ready_o(terminal_ready),.terminal_i(rx_payload_i[163:0]),
        .completion_valid_o(completion_valid),.completion_o(completion),.push_score_valid_o(push_score_valid_o),.push_score_ready_i(push_score_ready_i),
        .push_score_note_o(push_score_note_o),.analysis_done_o(analysis_done_o),.failed_o(collector_failed),.failure_code_o(),.note_count_o());
    assign analysis_failed_o=source_failed || collector_failed;
    wire record_ack=rx_channel_i==`TASK3_PAIR_CH_RECORD_ACK && rx_length_i==`TASK3_PAIR_RECORD_ACK_BYTES && rx_payload_i[255:98]==0;
    wire record_ack_matches;
    reg frame_seen;reg [31:0] last_epoch,last_sequence;reg last_bad;
    wire record_arm_ready,record_arm_tx,record_frame_tx,record_cancel_tx;
    wire record_arm_tx_ready,record_frame_tx_ready,record_cancel_tx_ready,phone_response_ready;
    reg record_demand_pending;
    reg [31:0] record_demand_age,next_record_generation;
    wire demand_packet=rx_channel_i==`TASK3_PAIR_CH_RECORD_DEMAND && rx_length_i==`TASK3_PAIR_RECORD_DEMAND_BYTES && rx_payload_i[255:98]==0;
    wire demand_matches=rx_payload_i[95:0]==common;
    wire demand_start=demand_packet && rx_payload_i[97:96]==`TASK3_PAIR_KIND_ARM;
    wire demand_cancel=demand_packet && rx_payload_i[97:96]==`TASK3_PAIR_KIND_CANCEL;
    wire demand_cancel_fire=rx_valid_i && rx_ready_o && demand_cancel && demand_matches;
    wire demand_restart_fire=rx_valid_i && rx_ready_o && demand_start && demand_matches && record_armed_o;
    wire record_frame_usable=frame_seen && (frame_valid_i?frame_epoch_i:last_epoch)!=0 &&
        !(frame_valid_i?(frame_44k1_i || frame_error_i):last_bad);
    wire record_arm_fire=live && !new_identity && (record_arm_i || record_demand_pending) &&
        !demand_cancel_fire && record_arm_ready && record_frame_usable && next_record_generation!=0;
    wire [31:0] record_boot,record_session,record_generation,record_epoch,record_first;
    assign record_ack_matches=rx_payload_i[97:2]=={record_boot,record_session,record_generation};
    wire [31:0] record_tx_epoch,record_tx_sequence,record_tx_pcm;
    wire record_tx_rate,record_tx_error;
    workstation_task3_final_tap_export recording(
        .clk_i(clk_i),.reset_ni(reset_ni),.link_ready_i(live && !new_identity),.panic_i(panic_i),
        .arm_valid_i(record_arm_fire),.arm_ready_o(record_arm_ready),
        .arm_boot_i(local_boot_i),.arm_session_i(session_i),.arm_generation_i(next_record_generation),
        .arm_physical_epoch_i(frame_valid_i?frame_epoch_i:last_epoch),.arm_first_sequence_i((frame_valid_i?frame_sequence_i:last_sequence)+1'b1),.arm_accepted_o(),.arm_rejected_o(),
        .arm_tx_valid_o(record_arm_tx),.arm_tx_ready_i(record_arm_tx_ready),
        .arm_result_accepted_i(rx_valid_i && rx_ready_o && record_ack && record_ack_matches && rx_payload_i[1]),
        .arm_result_rejected_i(rx_valid_i && rx_ready_o && record_ack && record_ack_matches && rx_payload_i[0]),
        .boot_o(record_boot),.session_o(record_session),.generation_o(record_generation),.physical_epoch_o(record_epoch),.first_sequence_o(record_first),
        .cancel_valid_i(record_cancel_i || demand_cancel_fire || demand_restart_fire),.cancel_session_i(record_session),.cancel_generation_i(record_generation),
        .frame_valid_i(frame_valid_i),.frame_44k1_i(frame_44k1_i),.frame_error_i(frame_error_i),
        .frame_epoch_i(frame_epoch_i),.frame_sequence_i(frame_sequence_i),.frame_pcm_i(frame_pcm_i),
        .frame_tx_valid_o(record_frame_tx),.frame_tx_ready_i(record_frame_tx_ready),.frame_tx_epoch_o(record_tx_epoch),
        .frame_tx_sequence_o(record_tx_sequence),.frame_tx_pcm_o(record_tx_pcm),.frame_tx_44k1_o(record_tx_rate),.frame_tx_error_o(record_tx_error),
        .cancel_tx_valid_o(record_cancel_tx),.cancel_tx_ready_i(record_cancel_tx_ready),.armed_o(record_armed_o),.fault_o(record_fault_o),
        .failure_code_o(),.queued_frames_o(),.captured_frames_o(),.exported_frames_o());
    wire phone_packet=rx_channel_i==`TASK3_PAIR_CH_PHONE && rx_length_i==`TASK3_PAIR_PHONE_BYTES && rx_payload_i[255:180]==0;
    // Proxy deliberately addresses the M boot, not a radio-local boot.
    wire phone_matches=rx_payload_i[177:82]==common;
    wire phone_arm=phone_packet && rx_payload_i[179:178]==`TASK3_PAIR_KIND_ARM && rx_payload_i[81:0]==0;
    wire phone_request=phone_packet && rx_payload_i[179:178]==`TASK3_PAIR_KIND_DATA;
    wire phone_cancel=phone_packet && rx_payload_i[179:178]==`TASK3_PAIR_KIND_CANCEL && rx_payload_i[81:0]==0;
    wire phone_arm_ready,phone_arm_accepted,phone_arm_rejected,phone_request_ready,phone_response_valid;
    wire [31:0] response_boot,response_session,response_generation,response_sequence,response_data;
    wire response_error;
    reg phone_ack_pending;reg [1:0] phone_ack_result;
    workstation_task3_phone_command_ingress phone(
        .clk_i(clk_i),.reset_ni(reset_ni),.link_ready_i(live && !new_identity && hci_ready_o),.panic_i(panic_i),.owner_idle_i(phone_owner_idle_i),
        .arm_valid_i(live && rx_valid_i && rx_ready_o && phone_arm && phone_matches),.arm_ready_o(phone_arm_ready),
        .arm_boot_i(rx_payload_i[177:146]),.arm_session_i(rx_payload_i[145:114]),.arm_generation_i(rx_payload_i[113:82]),
        .arm_accepted_o(phone_arm_accepted),.arm_rejected_o(phone_arm_rejected),
        .cancel_valid_i(rx_valid_i && phone_cancel && phone_matches),.cancel_session_i(rx_payload_i[145:114]),.cancel_generation_i(rx_payload_i[113:82]),
        .request_valid_i(live && rx_valid_i && phone_request && phone_matches),.request_ready_o(phone_request_ready),
        .request_boot_i(rx_payload_i[177:146]),.request_session_i(rx_payload_i[145:114]),.request_generation_i(rx_payload_i[113:82]),.request_sequence_i(rx_payload_i[81:50]),
        .request_target_i(rx_payload_i[49]),.request_write_i(rx_payload_i[48]),.request_address_i(rx_payload_i[47:36]),.request_data_i(rx_payload_i[35:4]),.request_strobes_i(rx_payload_i[3:0]),
        .response_valid_o(phone_response_valid),.response_ready_i(phone_response_ready),
        .response_boot_o(response_boot),.response_session_o(response_session),.response_generation_o(response_generation),.response_sequence_o(response_sequence),
        .response_data_o(response_data),.response_error_o(response_error),.owner_live_o(phone_owner_live_o),
        .command_valid_o(phone_command_valid_o),.command_ready_i(phone_command_ready_i),.command_target_o(phone_command_target_o),
        .command_write_o(phone_command_write_o),.command_address_o(phone_command_address_o),.command_data_o(phone_command_data_o),.command_strobes_o(phone_command_strobes_o),
        .command_response_data_i(phone_response_data_i),.command_response_error_i(phone_response_error_i),.armed_o(),.fault_o(),.failure_code_o(),.accepted_commands_o(),.applied_commands_o());
    wire status_packet=rx_channel_i==`TASK3_PAIR_CH_STATUS && rx_length_i==`TASK3_PAIR_STATUS_BYTES && rx_payload_i[255:198]==0;
    wire status_matches=rx_payload_i[197:70]=={peer_boot_i,local_boot_i,session_i,generation_i};
    reg [69:0] remote_status;reg [23:0] status_age;
    wire status_current=live && !new_identity && status_age<24'd5000000;
    assign model_status_o=status_current && remote_status[4]?remote_status[3:0]:4'd0;
    assign hci_epoch_o=remote_status[69:38];
    assign hci_generation_o=remote_status[37:6];
    always @*begin
        rx_ready_o=reset_ni;
        if(live)begin
            if(result_packet)rx_ready_o=rx_payload_i[167]?terminal_ready:score_ready;
            else if(phone_matches && phone_arm)rx_ready_o=!phone_ack_pending;
            else if(phone_matches && phone_request)rx_ready_o=phone_request_ready;
        end
    end
    wire slot_free=live && !tx_valid_o;
    assign record_cancel_tx_ready=slot_free && record_cancel_tx;
    wire cancel_take=slot_free && !record_cancel_tx && cancel_valid;
    assign cancel_ready=cancel_take;
    wire phone_ack_take=slot_free && !record_cancel_tx && !cancel_valid && phone_ack_pending;
    assign phone_response_ready=slot_free && !record_cancel_tx && !cancel_valid && !phone_ack_pending;
    assign record_arm_tx_ready=phone_response_ready && !phone_response_valid && record_arm_tx;
    assign record_frame_tx_ready=phone_response_ready && !phone_response_valid && !record_arm_tx && record_frame_tx;
    wire analysis_slot=phone_response_ready && !phone_response_valid && !record_arm_tx && !record_frame_tx;
    assign desc_ready=analysis_slot;
    assign frame_ready=analysis_slot && !desc_valid;
    assign seal_ready=analysis_slot && !desc_valid && !frame_valid;
    wire known=result_packet || record_ack || phone_arm || phone_request || phone_cancel || status_packet || demand_start || demand_cancel;
    wire stale=(record_ack && !record_ack_matches) || (phone_packet && !phone_matches) || (status_packet && !status_matches) || (demand_packet && !demand_matches);
    always @(posedge clk_i or negedge reset_ni)begin
        if(!reset_ni)begin
            configured_identity<=0;next_job<=32'h00010000;
            frame_seen<=0;last_epoch<=0;last_sequence<=0;last_bad<=1;
            record_demand_pending<=0;record_demand_age<=0;next_record_generation<=1;
            tx_valid_o<=0;tx_channel_o<=0;tx_payload_o<=0;tx_length_o<=0;
            phone_ack_pending<=0;phone_ack_result<=0;remote_status<=0;status_age<=24'hffffff;hci_ready_o<=0;
            malformed_packets_o<=0;stale_packets_o<=0;
        end else begin
            hci_ready_o<=status_current && remote_status[5];
            if(new_identity)begin
                configured_identity<={local_boot_i,peer_boot_i,session_i,generation_i};remote_status<=0;status_age<=24'hffffff;
            end else if(start_fire)next_job<=next_job+32'h00010000;
            if(status_age!=24'hffffff)status_age<=status_age+1'b1;
            if(frame_valid_i)begin frame_seen<=1;last_epoch<=frame_epoch_i;last_sequence<=frame_sequence_i;last_bad<=frame_44k1_i || frame_error_i;end
            if(record_demand_pending)begin
                if(record_demand_age==RECORD_DEMAND_TIMEOUT_CYCLES-1)record_demand_pending<=0;
                else record_demand_age<=record_demand_age+1'b1;
            end
            if(record_arm_fire)begin
                record_demand_pending<=0;record_demand_age<=0;
                next_record_generation<=next_record_generation+1'b1;
            end
            if(!live || new_identity || demand_cancel_fire || record_cancel_i)record_demand_pending<=0;
            if(!live || new_identity)begin tx_valid_o<=0;phone_ack_pending<=0;end
            else if(tx_valid_o && tx_ready_i)tx_valid_o<=0;
            if(phone_arm_accepted || phone_arm_rejected)begin phone_ack_pending<=1;phone_ack_result<={phone_arm_accepted,phone_arm_rejected};end
            if(rx_valid_i && rx_ready_o)begin
                if(!known)malformed_packets_o<=malformed_packets_o+1'b1;
                else if(stale)stale_packets_o<=stale_packets_o+1'b1;
                if(live && !new_identity && !record_cancel_i && demand_start && demand_matches && !record_demand_pending && !record_arm_fire)begin
                    record_demand_pending<=1;record_demand_age<=0;
                end
                if(live && status_packet && status_matches)begin
                    remote_status<=rx_payload_i[69:0];status_age<=0;
                    // One complete source cycle revokes ready before an HCI
                    // identity change, as required by the existing PCM CDC.
                    if(rx_payload_i[69:6]!=remote_status[69:6] || !rx_payload_i[5])hci_ready_o<=0;
                end
            end
            if(slot_free)begin
                tx_payload_o<=0;
                if(record_cancel_tx_ready)begin
                    tx_valid_o<=1;tx_channel_o<=`TASK3_PAIR_CH_RECORD;tx_length_o<=`TASK3_PAIR_RECORD_BYTES;
                    tx_payload_o[195:0]<={`TASK3_PAIR_KIND_CANCEL,record_boot,record_session,record_generation,98'd0};
                end else if(cancel_take)begin tx_valid_o<=1;tx_channel_o<=`TASK3_PAIR_CH_ANALYSIS_CANCEL;tx_length_o<=`TASK3_PAIR_CANCEL_BYTES;tx_payload_o[127:0]<=cancel;end
                else if(phone_ack_take)begin
                    phone_ack_pending<=0;tx_valid_o<=1;tx_channel_o<=`TASK3_PAIR_CH_PHONE_ACK;tx_length_o<=`TASK3_PAIR_PHONE_ACK_BYTES;
                    tx_payload_o[162:0]<={`TASK3_PAIR_KIND_ARM,common,63'd0,phone_ack_result};
                end else if(phone_response_valid && phone_response_ready)begin
                    tx_valid_o<=1;tx_channel_o<=`TASK3_PAIR_CH_PHONE_ACK;tx_length_o<=`TASK3_PAIR_PHONE_ACK_BYTES;
                    tx_payload_o[162:0]<={`TASK3_PAIR_KIND_DATA,response_boot,response_session,response_generation,response_sequence,response_error,response_data};
                end else if(record_arm_tx_ready)begin
                    tx_valid_o<=1;tx_channel_o<=`TASK3_PAIR_CH_RECORD;tx_length_o<=`TASK3_PAIR_RECORD_BYTES;
                    tx_payload_o[195:0]<={`TASK3_PAIR_KIND_ARM,record_boot,record_session,record_generation,34'd0,record_epoch,record_first};
                end else if(record_frame_tx_ready)begin
                    tx_valid_o<=1;tx_channel_o<=`TASK3_PAIR_CH_RECORD;tx_length_o<=`TASK3_PAIR_RECORD_BYTES;
                    tx_payload_o[195:0]<={`TASK3_PAIR_KIND_DATA,record_boot,record_session,record_generation,record_tx_rate,record_tx_error,record_tx_epoch,record_tx_sequence,record_tx_pcm};
                end else if(analysis_slot && (desc_valid || frame_valid || seal_valid))begin
                    tx_valid_o<=1;tx_channel_o<=`TASK3_PAIR_CH_ANALYSIS;tx_length_o<=`TASK3_PAIR_ANALYSIS_BYTES;
                    tx_payload_o[201:0]<=desc_valid?{2'd0,desc}:frame_valid?{2'd1,8'd0,frame}:{2'd2,8'd0,seal};
                end
            end
        end
    end
endmodule
