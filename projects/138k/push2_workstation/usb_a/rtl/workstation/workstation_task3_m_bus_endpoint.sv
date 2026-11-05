`timescale 1ns/1ps
`include "rtl/workstation/task3_paired_channels.vh"
// M endpoint AFTER an ordered, measured transport. All ports use clk_i.
// Physical-frame observations have no ready signal; congestion fails only
// the recording branch. Offline TF may pause its single native decoder.
module workstation_task3_m_bus_endpoint #(
    parameter integer RECORD_DEMAND_TIMEOUT_CYCLES=50000000,
    parameter bit BLOCK_PCM=1'b0,
    parameter bit PHONE_WINDOW_BLOCK=1'b0,
    parameter bit PHONE_BATCH=1'b0,
    parameter bit SYNC_READ_STORAGE=1'b0,
    parameter integer IDENTITY_COMPARE_GROUP_BITS=128,
    parameter integer MEDIA_CAP_TIMEOUT_CYCLES=5000000
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
    // TASK3 identity comparison begin. Group only this combinational guard;
    // keep every identity bit and same-cycle revocation, without new state.
    wire new_identity;
    wire [127:0] current_identity={local_boot_i,peer_boot_i,session_i,generation_i};
    generate if(IDENTITY_COMPARE_GROUP_BITS==128)begin:g_identity_direct
        assign new_identity=configured_identity!=current_identity;
    end else begin:g_identity_grouped
        localparam integer GROUPS=128/IDENTITY_COMPARE_GROUP_BITS;
        (* syn_keep=1 *) wire [GROUPS-1:0] changed;
        for(genvar bit_group=0;bit_group<GROUPS;bit_group=bit_group+1)begin:g_word
            assign changed[bit_group]=
                configured_identity[bit_group*IDENTITY_COMPARE_GROUP_BITS+:IDENTITY_COMPARE_GROUP_BITS]!=
                current_identity[bit_group*IDENTITY_COMPARE_GROUP_BITS+:IDENTITY_COMPARE_GROUP_BITS];
        end
        assign new_identity=|changed;
    end endgenerate
    initial if(IDENTITY_COMPARE_GROUP_BITS!=128 && IDENTITY_COMPARE_GROUP_BITS!=8)
        $fatal(1,"identity comparison requires the reviewed128-bit direct or8-bit grouped policy");
    // TASK3 identity comparison end.
    // A FAT32 file contains at most 2^30 stereo16 frames, hence <65536
    // native 96000-frame clips. Reserve that entire interval for each job.
    wire job_space=next_job!=0 && next_job<=32'hfffe0000;
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
    wire credit_packet=BLOCK_PCM && rx_channel_i==`TASK3_PAIR_CH_BLOCK_CREDIT && rx_length_i==`TASK3_PAIR_CREDIT_BYTES && rx_payload_i[255:65]==0;
    wire a_block_fault,r_block_fault;
    wire media_fault_packet=BLOCK_PCM && rx_channel_i==`TASK3_PAIR_CH_MEDIA_FAULT && rx_length_i==`TASK3_PAIR_MEDIA_FAULT_BYTES && rx_payload_i[255:37]==0 && rx_payload_i[36:33]!=0;
    wire remote_analysis_fault,remote_record_fault;
    wire source_ready,source_done,source_failed,collector_failed;
    wire desc_valid,desc_ready,frame_valid,frame_ready,seal_valid,seal_ready,cancel_valid,cancel_ready;
    wire [199:0] desc;wire [191:0] frame,seal;wire [127:0] cancel;
    wire arm_valid,arm_ready,arm_append,file_last,completion_valid;
    wire [127:0] arm_identity;wire [163:0] completion;
    assign analysis_ready_o=live && !new_identity && media_current && job_space && source_ready;
    wire start_fire=analysis_start_i && analysis_ready_o;
    workstation_task3_tf_analysis_source source_m(
        .clk_i(clk_i),.reset_ni(reset_ni),.link_ready_i(live && !new_identity),.transport_fault_i(BLOCK_PCM && (a_block_fault || remote_analysis_fault || media_cap_fault)),
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
    workstation_task3_score_commit_m #(.SYNC_READ_STORAGE(SYNC_READ_STORAGE),
        .PIPELINED_TERMINAL(SYNC_READ_STORAGE)) collector_m(
        .clk_i(clk_i),.reset_ni(reset_ni),.link_ready_i(live && !new_identity),.cancel_i(analysis_cancel_i || source_failed),.panic_i(panic_i),
        .arm_valid_i(arm_valid),.arm_ready_o(arm_ready),.arm_identity_i(arm_identity),.arm_append_i(arm_append),.chunk_file_last_i(file_last),
        .score_valid_i(live && rx_valid_i && result_packet && !rx_payload_i[167]),.score_ready_o(score_ready),.score_i(rx_payload_i[166:0]),
        .terminal_valid_i(live && rx_valid_i && result_packet && rx_payload_i[167]),.terminal_ready_o(terminal_ready),.terminal_i(rx_payload_i[163:0]),
        .completion_valid_o(completion_valid),.completion_o(completion),.push_score_valid_o(push_score_valid_o),.push_score_ready_i(push_score_ready_i),
        .push_score_note_o(push_score_note_o),.analysis_done_o(analysis_done_o),.failed_o(collector_failed),.failure_code_o(),.note_count_o());
    assign analysis_failed_o=source_failed || collector_failed || (BLOCK_PCM && media_cap_fault);
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
    wire record_arm_fire=live && !new_identity && media_current && (record_arm_i || record_demand_pending) &&
        !demand_cancel_fire && record_arm_ready && record_frame_usable && next_record_generation!=0;
    wire [31:0] record_boot,record_session,record_generation,record_epoch,record_first;
    assign remote_analysis_fault=rx_valid_i && rx_ready_o && media_fault_packet && !rx_payload_i[32] && rx_payload_i[31:0]==desc[103:72];
    assign remote_record_fault=rx_valid_i && rx_ready_o && media_fault_packet && rx_payload_i[32] && rx_payload_i[31:0]==record_generation;
    assign record_ack_matches=rx_payload_i[97:2]=={record_boot,record_session,record_generation};
    wire [31:0] record_tx_epoch,record_tx_sequence,record_tx_pcm;
    wire record_tx_rate,record_tx_error,record_local_fault;
    assign record_fault_o=record_local_fault || (BLOCK_PCM && media_cap_fault);
    workstation_task3_final_tap_export #(.SYNC_READ_STORAGE(SYNC_READ_STORAGE)) recording(
        .clk_i(clk_i),.reset_ni(reset_ni),.link_ready_i(live && !new_identity),.panic_i(panic_i),
        .arm_valid_i(record_arm_fire),.arm_ready_o(record_arm_ready),
        .arm_boot_i(local_boot_i),.arm_session_i(session_i),.arm_generation_i(next_record_generation),
        .arm_physical_epoch_i(frame_valid_i?frame_epoch_i:last_epoch),.arm_first_sequence_i((frame_valid_i?frame_sequence_i:last_sequence)+1'b1),.arm_accepted_o(),.arm_rejected_o(),
        .arm_tx_valid_o(record_arm_tx),.arm_tx_ready_i(record_arm_tx_ready),
        .arm_result_accepted_i(rx_valid_i && rx_ready_o && record_ack && record_ack_matches && rx_payload_i[1]),
        .arm_result_rejected_i(rx_valid_i && rx_ready_o && record_ack && record_ack_matches && rx_payload_i[0]),
        .boot_o(record_boot),.session_o(record_session),.generation_o(record_generation),.physical_epoch_o(record_epoch),.first_sequence_o(record_first),
        .cancel_valid_i(record_cancel_i || demand_cancel_fire || demand_restart_fire || (BLOCK_PCM && (r_block_fault || remote_record_fault || media_cap_fault))),.cancel_session_i(record_session),.cancel_generation_i(record_generation),
        .frame_valid_i(frame_valid_i),.frame_44k1_i(frame_44k1_i),.frame_error_i(frame_error_i),
        .frame_epoch_i(frame_epoch_i),.frame_sequence_i(frame_sequence_i),.frame_pcm_i(frame_pcm_i),
        .frame_tx_valid_o(record_frame_tx),.frame_tx_ready_i(record_frame_tx_ready),.frame_tx_epoch_o(record_tx_epoch),
        .frame_tx_sequence_o(record_tx_sequence),.frame_tx_pcm_o(record_tx_pcm),.frame_tx_44k1_o(record_tx_rate),.frame_tx_error_o(record_tx_error),
        .cancel_tx_valid_o(record_cancel_tx),.cancel_tx_ready_i(record_cancel_tx_ready),.armed_o(record_armed_o),.fault_o(record_local_fault),
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
    wire phone_ingress_live,phone_normal_valid,phone_normal_ready,phone_normal_target,phone_normal_write;
    wire [11:0] phone_normal_address;
    wire [31:0] phone_normal_data;
    wire [3:0] phone_normal_strobes;
    wire phone_window_valid,phone_window_busy,phone_window_fault,phone_window_rx_fault,phone_window_ack;
    reg phone_window_protocol_fault;
    wire phone_window_ack_ready,phone_window_ack_error;
    wire [11:0] phone_window_address;
    wire [31:0] phone_window_data,phone_window_first,phone_window_next;
    wire phone_window_packet=PHONE_WINDOW_BLOCK && rx_channel_i==`TASK3_PAIR_CH_PHONE_WINDOW;
    wire phone_batch_packet=PHONE_BATCH && rx_channel_i==`TASK3_PAIR_CH_PHONE && rx_length_i==`TASK3_PAIR_PHONE_BATCH_REQUEST_BYTES;
    wire phone_batch_command_valid,phone_batch_command_write,phone_batch_busy,phone_batch_fault;
    wire [11:0] phone_batch_address;wire [31:0] phone_batch_data;wire [3:0] phone_batch_strobes;
    wire phone_batch_reply_valid,phone_batch_reply_ready,phone_batch_packet_ready;
    wire [255:0] phone_batch_reply;wire [5:0] phone_batch_reply_length;
    // W's barrier forbids overlap. M independently rejects it rather than
    // allowing a new block to steal an already held PCM/clock transaction.
    wire phone_window_eligible=phone_request_ready && !phone_ack_pending && !phone_batch_busy && !phone_batch_fault;
    wire phone_batch_eligible=phone_request_ready && !phone_ack_pending && !phone_window_busy && !phone_batch_busy && !phone_batch_fault;
    wire phone_window_overlap=PHONE_WINDOW_BLOCK && live && rx_valid_i && rx_ready_o &&
        ((phone_window_packet && phone_ingress_live && !phone_window_eligible) ||
         (phone_request && phone_matches && (phone_window_busy || phone_batch_busy)) ||
         (phone_batch_packet && phone_ingress_live && !phone_batch_eligible));
    assign phone_window_fault=phone_window_rx_fault || phone_window_protocol_fault;
    always @(posedge clk_i or negedge reset_ni)
        if(!reset_ni)phone_window_protocol_fault<=0;
        else if(!live || new_identity)phone_window_protocol_fault<=0;
        else if(phone_window_overlap)phone_window_protocol_fault<=1;
    wire phone_media_live=!PHONE_WINDOW_BLOCK || media_current;
    assign phone_owner_live_o=phone_ingress_live && !phone_window_fault && !phone_batch_fault;
    assign phone_command_valid_o=!phone_batch_fault && (phone_batch_busy ? phone_batch_command_valid:phone_window_busy ? phone_window_valid:phone_normal_valid);
    assign phone_command_target_o=phone_batch_busy || phone_window_busy ? 1'b0:phone_normal_target;
    assign phone_command_write_o=phone_batch_busy ? phone_batch_command_write:phone_window_busy ? 1'b1:phone_normal_write;
    assign phone_command_address_o=phone_batch_busy ? phone_batch_address:phone_window_busy ? phone_window_address:phone_normal_address;
    assign phone_command_data_o=phone_batch_busy ? phone_batch_data:phone_window_busy ? phone_window_data:phone_normal_data;
    assign phone_command_strobes_o=phone_batch_busy ? phone_batch_strobes:phone_window_busy ? 4'hf:phone_normal_strobes;
    assign phone_normal_ready=phone_command_ready_i && !phone_window_busy && !phone_batch_busy && !phone_batch_fault;
    generate if(PHONE_BATCH)begin:g_phone_batch
        workstation_task3_phone_batch_m batch_m(
            .clk_i(clk_i),.reset_ni(reset_ni),.live_i(live && !new_identity && hci_ready_o && media_current && phone_ingress_live),
            .cancel_i(panic_i || phone_window_protocol_fault),.token_i(generation_i),
            .packet_valid_i(rx_valid_i && rx_ready_o && phone_batch_packet && phone_batch_eligible),.packet_ready_o(phone_batch_packet_ready),
            .packet_payload_i(rx_payload_i),.packet_length_i(rx_length_i),
            .reply_valid_o(phone_batch_reply_valid),.reply_ready_i(phone_batch_reply_ready),.reply_payload_o(phone_batch_reply),.reply_length_o(phone_batch_reply_length),
            .command_valid_o(phone_batch_command_valid),.command_write_o(phone_batch_command_write),.command_address_o(phone_batch_address),
            .command_data_o(phone_batch_data),.command_strobes_o(phone_batch_strobes),
            .command_ready_i(phone_command_ready_i && !phone_window_busy),.command_response_data_i(phone_response_data_i),.command_response_error_i(phone_response_error_i),
            .busy_o(phone_batch_busy),.fault_o(phone_batch_fault));
    end else begin:g_no_phone_batch
        assign phone_batch_command_valid=0,phone_batch_command_write=0,phone_batch_address=0,phone_batch_data=0,phone_batch_strobes=0;
        assign phone_batch_busy=0,phone_batch_fault=0,phone_batch_reply_valid=0,phone_batch_reply=0,phone_batch_reply_length=0,phone_batch_packet_ready=0;
    end endgenerate
    generate if(PHONE_WINDOW_BLOCK)begin:g_phone_window
        workstation_task3_phone_window_rx window_rx(
            .clk_i(clk_i),.reset_ni(reset_ni),.session_live_i(live && !new_identity && hci_ready_o && media_current),
            .armed_i(phone_ingress_live && !phone_window_protocol_fault),.token_i(generation_i),
            .block_valid_i(rx_valid_i && rx_ready_o && phone_window_packet && (!phone_ingress_live || phone_window_eligible)),.block_payload_i(rx_payload_i),.block_length_i(rx_length_i),
            .command_valid_o(phone_window_valid),.command_ready_i(phone_command_ready_i && !phone_batch_busy),
            .command_address_o(phone_window_address),.command_data_o(phone_window_data),.command_response_error_i(phone_response_error_i),
            .ack_valid_o(phone_window_ack),.ack_ready_i(phone_window_ack_ready),
            .ack_first_sequence_o(phone_window_first),.ack_next_sequence_o(phone_window_next),.ack_error_o(phone_window_ack_error),
            .busy_o(phone_window_busy),.fault_o(phone_window_rx_fault));
    end else begin:g_legacy_phone_window
        assign phone_window_valid=0,phone_window_busy=0,phone_window_rx_fault=0,phone_window_ack=0;
        assign phone_window_address=0,phone_window_data=0,phone_window_first=0,phone_window_next=0,phone_window_ack_error=0;
    end endgenerate
    workstation_task3_phone_command_ingress phone(
        .clk_i(clk_i),.reset_ni(reset_ni),.link_ready_i(live && !new_identity && hci_ready_o && phone_media_live && !phone_window_fault),.panic_i(panic_i),.owner_idle_i(phone_owner_idle_i),
        .arm_valid_i(live && rx_valid_i && rx_ready_o && phone_arm && phone_matches),.arm_ready_o(phone_arm_ready),
        .arm_boot_i(rx_payload_i[177:146]),.arm_session_i(rx_payload_i[145:114]),.arm_generation_i(rx_payload_i[113:82]),
        .arm_accepted_o(phone_arm_accepted),.arm_rejected_o(phone_arm_rejected),
        .cancel_valid_i(rx_valid_i && phone_cancel && phone_matches),.cancel_session_i(rx_payload_i[145:114]),.cancel_generation_i(rx_payload_i[113:82]),
        .request_valid_i(live && rx_valid_i && phone_request && phone_matches && !phone_window_busy && !phone_batch_busy && !phone_batch_fault),.request_ready_o(phone_request_ready),
        .request_boot_i(rx_payload_i[177:146]),.request_session_i(rx_payload_i[145:114]),.request_generation_i(rx_payload_i[113:82]),.request_sequence_i(rx_payload_i[81:50]),
        .request_target_i(rx_payload_i[49]),.request_write_i(rx_payload_i[48]),.request_address_i(rx_payload_i[47:36]),.request_data_i(rx_payload_i[35:4]),.request_strobes_i(rx_payload_i[3:0]),
        .response_valid_o(phone_response_valid),.response_ready_i(phone_response_ready),
        .response_boot_o(response_boot),.response_session_o(response_session),.response_generation_o(response_generation),.response_sequence_o(response_sequence),
        .response_data_o(response_data),.response_error_o(response_error),.owner_live_o(phone_ingress_live),
        .command_valid_o(phone_normal_valid),.command_ready_i(phone_normal_ready),.command_target_o(phone_normal_target),
        .command_write_o(phone_normal_write),.command_address_o(phone_normal_address),.command_data_o(phone_normal_data),.command_strobes_o(phone_normal_strobes),
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
            // The batch lease captures the full pair token one edge after
            // phone ARM. Wait for that edge without consuming its first packet;
            // real owner overlap still takes the fault path above.
            else if(phone_batch_packet && phone_ingress_live && phone_batch_eligible)rx_ready_o=phone_batch_packet_ready;
            else if(phone_matches && phone_arm)rx_ready_o=!phone_ack_pending;
            else if(phone_matches && phone_request)rx_ready_o=phone_request_ready;
        end
    end
    wire a_frame_ready,r_frame_ready,a_block_valid,r_block_valid,a_block_ready,r_block_ready,a_empty;
    wire [255:0] a_block_payload,r_block_payload;
    wire [5:0] a_block_length,r_block_length;
    workstation_task3_pcm_block_tx analysis_blocks(
        .clk_i(clk_i),.reset_ni(reset_ni),.live_i(BLOCK_PCM && live && !new_identity && media_current),
        .start_i(desc_valid && desc_ready),.token_i(desc[103:72]),.first_index_i(32'd0),
        .cancel_i(analysis_cancel_i || source_failed || collector_failed || cancel_valid),.flush_i(seal_valid),
        .frame_valid_i(frame_valid),.frame_ready_o(a_frame_ready),.frame_index_i(frame[63:32]),.frame_pcm_i(frame[31:0]),
        .credit_valid_i(rx_valid_i && rx_ready_o && credit_packet && !rx_payload_i[64]),.credit_token_i(rx_payload_i[31:0]),.credit_limit_i(rx_payload_i[63:32]),
        .block_valid_o(a_block_valid),.block_ready_i(a_block_ready),.block_payload_o(a_block_payload),.block_length_o(a_block_length),
        .empty_o(a_empty),.active_o(),.fault_o(a_block_fault),.sent_blocks_o());
    workstation_task3_pcm_block_tx record_blocks(
        .clk_i(clk_i),.reset_ni(reset_ni),.live_i(BLOCK_PCM && live && !new_identity && media_current),
        .start_i(record_arm_tx && record_arm_tx_ready),.token_i(record_generation),.first_index_i(record_first),
        .cancel_i(record_cancel_tx || !record_armed_o),.flush_i(1'b0),
        .frame_valid_i(record_frame_tx),.frame_ready_o(r_frame_ready),.frame_index_i(record_tx_sequence),.frame_pcm_i(record_tx_pcm),
        .credit_valid_i(rx_valid_i && rx_ready_o && credit_packet && rx_payload_i[64]),.credit_token_i(rx_payload_i[31:0]),.credit_limit_i(rx_payload_i[63:32]),
        .block_valid_o(r_block_valid),.block_ready_i(r_block_ready),.block_payload_o(r_block_payload),.block_length_o(r_block_length),
        .empty_o(),.active_o(),.fault_o(r_block_fault),.sent_blocks_o());
    wire slot_free=live && !tx_valid_o;
    assign record_cancel_tx_ready=slot_free && record_cancel_tx;
    wire cancel_take=slot_free && !record_cancel_tx && cancel_valid;
    assign cancel_ready=cancel_take;
    wire cap_take=BLOCK_PCM && slot_free && !record_cancel_tx && !cancel_valid && media_cap_pending;
    wire phone_ack_take=slot_free && !record_cancel_tx && !cancel_valid && !cap_take && phone_ack_pending;
    assign phone_response_ready=slot_free && !record_cancel_tx && !cancel_valid && !cap_take && !phone_ack_pending;
    assign phone_window_ack_ready=phone_response_ready && !phone_response_valid && phone_window_ack;
    assign phone_batch_reply_ready=phone_response_ready && !phone_response_valid && !phone_window_ack && phone_batch_reply_valid;
    assign record_arm_tx_ready=phone_response_ready && !phone_response_valid && !phone_window_ack && !phone_batch_reply_valid && record_arm_tx;
    wire control_slot=phone_response_ready && !phone_response_valid && !phone_window_ack && !phone_batch_reply_valid && !record_arm_tx;
    assign record_frame_tx_ready=BLOCK_PCM ? r_frame_ready : control_slot && record_frame_tx;
    wire analysis_slot=control_slot && (BLOCK_PCM || !record_frame_tx);
    assign desc_ready=analysis_slot && media_current;
    assign frame_ready=BLOCK_PCM ? a_frame_ready : analysis_slot && !desc_valid;
    assign seal_ready=analysis_slot && !desc_valid && (BLOCK_PCM ? a_empty : !frame_valid);
    reg prefer_analysis;
    wire media_slot=BLOCK_PCM && control_slot && !desc_valid && !(seal_valid && a_empty);
    assign a_block_ready=media_slot && a_block_valid && (!r_block_valid || prefer_analysis);
    assign r_block_ready=media_slot && r_block_valid && (!a_block_valid || !prefer_analysis);
    wire known=result_packet || record_ack || phone_arm || phone_request || phone_cancel || status_packet || demand_start || demand_cancel || media_cap_packet || credit_packet || media_fault_packet || phone_window_packet || phone_batch_packet;
    wire stale=(record_ack && !record_ack_matches) || (phone_packet && !phone_matches) || (status_packet && !status_matches) || (demand_packet && !demand_matches) || (media_cap_packet && !media_cap_matches);
    always @(posedge clk_i or negedge reset_ni)begin
        if(!reset_ni)begin
            configured_identity<=0;next_job<=32'h00010000;prefer_analysis<=0;
            media_cap_ready<=0;media_cap_fault<=0;media_cap_pending<=1;media_cap_age<=0;media_cap_send_age<=0;
            frame_seen<=0;last_epoch<=0;last_sequence<=0;last_bad<=1;
            record_demand_pending<=0;record_demand_age<=0;next_record_generation<=1;
            tx_valid_o<=0;tx_channel_o<=0;tx_payload_o<=0;tx_length_o<=0;
            phone_ack_pending<=0;phone_ack_result<=0;remote_status<=0;status_age<=24'hffffff;hci_ready_o<=0;
            malformed_packets_o<=0;stale_packets_o<=0;
        end else begin
            hci_ready_o<=status_current && remote_status[5];
            if(!live || new_identity)begin
                media_cap_ready<=0;media_cap_fault<=0;media_cap_pending<=1;media_cap_age<=0;media_cap_send_age<=0;prefer_analysis<=0;
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
                if(r_block_ready)prefer_analysis<=1;
                if(a_block_ready)prefer_analysis<=0;
            end
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
                else if(cap_take)begin
                    tx_valid_o<=1;tx_channel_o<=`TASK3_PAIR_CH_MEDIA_CAPS;tx_length_o<=`TASK3_PAIR_MEDIA_CAPS_BYTES;
                    tx_payload_o[223:0]<={local_boot_i,peer_boot_i,session_i,generation_i,`TASK3_PAIR_MEDIA_MAGIC,MEDIA_VERSION,MEDIA_FEATURES};
                end else if(phone_ack_take)begin
                    phone_ack_pending<=0;tx_valid_o<=1;tx_channel_o<=`TASK3_PAIR_CH_PHONE_ACK;tx_length_o<=`TASK3_PAIR_PHONE_ACK_BYTES;
                    tx_payload_o[162:0]<={`TASK3_PAIR_KIND_ARM,common,63'd0,phone_ack_result};
                end else if(phone_response_valid && phone_response_ready)begin
                    tx_valid_o<=1;tx_channel_o<=`TASK3_PAIR_CH_PHONE_ACK;tx_length_o<=`TASK3_PAIR_PHONE_ACK_BYTES;
                    tx_payload_o[162:0]<={`TASK3_PAIR_KIND_DATA,response_boot,response_session,response_generation,response_sequence,response_error,response_data};
                end else if(phone_window_ack && phone_window_ack_ready)begin
                    tx_valid_o<=1;tx_channel_o<=`TASK3_PAIR_CH_PHONE_ACK;tx_length_o<=`TASK3_PAIR_PHONE_ACK_BYTES;
                    tx_payload_o[162:0]<={`TASK3_PAIR_KIND_WINDOW_ACK,common,phone_window_first,phone_window_ack_error,phone_window_next};
                end else if(phone_batch_reply_valid && phone_batch_reply_ready)begin
                    tx_valid_o<=1;tx_channel_o<=`TASK3_PAIR_CH_PHONE_ACK;tx_length_o<=phone_batch_reply_length;tx_payload_o<=phone_batch_reply;
                end else if(record_arm_tx_ready)begin
                    tx_valid_o<=1;tx_channel_o<=`TASK3_PAIR_CH_RECORD;tx_length_o<=`TASK3_PAIR_RECORD_BYTES;
                    tx_payload_o[195:0]<={`TASK3_PAIR_KIND_ARM,record_boot,record_session,record_generation,34'd0,record_epoch,record_first};
                end else if(!BLOCK_PCM && record_frame_tx_ready)begin
                    tx_valid_o<=1;tx_channel_o<=`TASK3_PAIR_CH_RECORD;tx_length_o<=`TASK3_PAIR_RECORD_BYTES;
                    tx_payload_o[195:0]<={`TASK3_PAIR_KIND_DATA,record_boot,record_session,record_generation,record_tx_rate,record_tx_error,record_tx_epoch,record_tx_sequence,record_tx_pcm};
                end else if(a_block_ready || r_block_ready)begin
                    tx_valid_o<=1;tx_channel_o<=a_block_ready?`TASK3_PAIR_CH_ANALYSIS_BLOCK:`TASK3_PAIR_CH_RECORD_BLOCK;
                    tx_length_o<=a_block_ready?a_block_length:r_block_length;tx_payload_o<=a_block_ready?a_block_payload:r_block_payload;
                end else if(analysis_slot && (desc_valid || (!BLOCK_PCM && frame_valid) || (seal_valid && (!BLOCK_PCM || a_empty))))begin
                    tx_valid_o<=1;tx_channel_o<=`TASK3_PAIR_CH_ANALYSIS;tx_length_o<=`TASK3_PAIR_ANALYSIS_BYTES;
                    tx_payload_o[201:0]<=desc_valid?{2'd0,desc}:(!BLOCK_PCM && frame_valid)?{2'd1,8'd0,frame}:{2'd2,8'd0,seal};
                end
            end
        end
    end
endmodule
