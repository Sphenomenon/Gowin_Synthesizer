// v1 business endpoint with a built-in-audio recording/download slot.
// Fragment payloads stream through CRC32; accepted requests fit in 36 bytes.
// Every byte of longer unsupported requests is still checked before rejection.
module ble_protocol_command #(parameter CLK_HZ=50000000, parameter AUDIO_FILE="audio/test_tone.mem",
    parameter EXTERNAL_PCM=0, parameter CAPACITY_FRAMES=48000,
    parameter CACHE_METADATA_RAM_STYLE="block_ram", parameter EXTERNAL_SEAL_PROTOCOL=0,
    parameter EXTERNAL_RAW_STORE=0,
    parameter SINGLE_BLE_RECORDING=0, parameter integer RAW_DRAIN_TIMEOUT_CYCLES=0) (
    input wire business_owner_reset_ni,business_command_valid_i,business_command_write_i,
    input wire [11:0] business_command_address_i,
    input wire [31:0] business_command_data_i,
    input wire [3:0] business_command_strobes_i,
    output wire business_command_ready_o,business_response_error_o,
    output wire [31:0] business_response_data_o,
    input wire clk, resetn, enable,
    input wire pcm_valid_i, source_ready_i, source_fault_i,
    input wire [31:0] pcm_pair_i,
    input wire [63:0] boot_id,
    input wire [8:0] att_value_limit,
    input wire boot_valid, response_subscribed, control_open,
    input wire recording_enable, transfer_subscribed,
    input wire [31:0] elapsed_ms,
    input wire fragment_write,
    input wire [4:0] fragment_addr,
    input wire [7:0] fragment_data,
    input wire fragment_start,
    input wire [4:0] fragment_length,
    output wire busy,
    output reg fragment_done,
    output reg [7:0] fragment_error,
    output reg response_valid,
    output reg [6:0] response_length,
    input wire [6:0] response_addr,
    output wire [7:0] response_data,
    input wire response_consume,
    output wire transfer_valid,
    output wire transfer_compact,
    output wire transfer_bulk,
    output wire transfer_direct,
    output wire response_is_data,
    output wire [12:0] transfer_length,
    input wire [12:0] transfer_addr,
    output wire [7:0] transfer_data,
    input wire transfer_consume,
    input wire summary_latch,
    output reg [159:0] summary,
    output reg session_active,
    output reg [31:0] accepted_count,
    output reg [31:0] crc_reject_count,
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
    localparam IDLE=0,CHECK=1,DUP=2,ORDER=3,COPY=4,VALIDATE=5,
        SESSION=6,LOOKUP=7,COMPARE_ADDR=8,COMPARE=9,DISPATCH=10,
        STORE_REQ=11,BUILD=12,CRC=13,REPLAY_ADDR=14,REPLAY=15,DONE=16,RECORD_WAIT=17,BUILD_FETCH=18,REPLAY_RECORD_WAIT=19,STORE_META=20,META_ADDR=21,META_READ=22,BUILD_DATA=23;
    reg [4:0] state;
    reg [7:0] frag[0:19], previous[0:19], header[0:35];
    (* syn_ramstyle="distributed_ram" *) reg [7:0] reply[0:83];
    reg [7:0] reply_opcode, reply_result;
    (* ram_style="block" *) reg [7:0] request_cache[0:2047];
    (* ram_style="block" *) reg [7:0] reply_cache[0:4095];
    reg [31:0] cache_valid;
    reg [4:0] cache_next, cache_slot, lookup_slot;
    reg [7:0] request_cache_data, reply_cache_data;
    reg [6:0] index;
    reg [4:0] frag_size, prev_size;
    reg previous_valid, assembling;
    reg [15:0] token;
    reg [7:0] next_fragment;
    reg [9:0] total;
    reg [31:0] last_fragment_ms, crc_work, high_water, snapshot_counter;
    reg [63:0] session_nonce;
    reg [7:0] reply_status;
    reg [15:0] reply_detail;
    reg accept_request;
    reg [31:0] snapshot_time, snapshot_number;
    wire [31:0] request_id={header[7],header[6],header[5],header[4]};
    wire [63:0] request_nonce={header[15],header[14],header[13],header[12],header[11],header[10],header[9],header[8]};
    wire [15:0] payload_length={header[3],header[2]};
    wire metadata_write=resetn && enable && state==CRC && index==3 && accept_request;
    wire [31:0] metadata_id,metadata_time;
    wire [5:0] metadata_request_length;
    wire [6:0] metadata_reply_length;
    wire metadata_hit=cache_valid[lookup_slot] && elapsed_ms-metadata_time<60000 &&
        metadata_id==request_id;
    generate if(CACHE_METADATA_RAM_STYLE=="block_ram")begin:g_block_metadata
        // SESSION loads slot0 before the first LOOKUP; each LOOKUP preloads
        // its successor. Thus all32 candidates retain one comparison/clock.
        // Writes occur only in CRC, so they cannot collide with these reads.
        wire read_enable=resetn && enable && (state==SESSION || state==LOOKUP);
        wire [4:0] read_slot=state==SESSION ? 5'd0 : lookup_slot+5'd1;
        wire [15:0] lengths;
        reg [6:0] matched_reply_length;
        workstation_sdp #(.DATA_WIDTH(32),.ADDR_WIDTH(5)) ids(
            .write_clk_i(clk),.write_enable_i(metadata_write),.write_addr_i(cache_slot),.write_data_i(request_id),
            .read_clk_i(clk),.read_enable_i(read_enable),.read_addr_i(read_slot),.read_data_o(metadata_id));
        workstation_sdp #(.DATA_WIDTH(32),.ADDR_WIDTH(5)) times(
            .write_clk_i(clk),.write_enable_i(metadata_write),.write_addr_i(cache_slot),.write_data_i(elapsed_ms),
            .read_clk_i(clk),.read_enable_i(read_enable),.read_addr_i(read_slot),.read_data_o(metadata_time));
        workstation_sdp #(.DATA_WIDTH(16),.ADDR_WIDTH(5)) sizes(
            .write_clk_i(clk),.write_enable_i(metadata_write),.write_addr_i(cache_slot),
            .write_data_i({3'd0,response_length,total[5:0]}),
            .read_clk_i(clk),.read_enable_i(read_enable),.read_addr_i(read_slot),.read_data_o(lengths));
        assign metadata_request_length=lengths[5:0];
        assign metadata_reply_length=matched_reply_length;
        always @(posedge clk)begin
            if(!resetn || !enable)matched_reply_length<=0;
            else if(state==LOOKUP && metadata_hit)matched_reply_length<=lengths[12:6];
        end
        // RAM has no reset. cache_valid is the common-reset/session fence;
        // no uninitialized or old slot is used without a new valid entry.
    end else begin:g_distributed_metadata
        (* syn_ramstyle="distributed_ram" *) reg [31:0] cache_id[0:31];
        (* syn_ramstyle="distributed_ram" *) reg [31:0] cache_time[0:31];
        reg [5:0] cache_req_length[0:31];
        reg [6:0] cache_reply_length[0:31];
        assign metadata_id=cache_id[lookup_slot],metadata_time=cache_time[lookup_slot];
        assign metadata_request_length=cache_req_length[lookup_slot];
        assign metadata_reply_length=cache_reply_length[cache_slot];
        always @(posedge clk)if(metadata_write)begin
            cache_id[cache_slot]<=request_id;cache_time[cache_slot]<=elapsed_ms;
            cache_req_length[cache_slot]<=total[5:0];cache_reply_length[cache_slot]<=response_length;
        end
    end endgenerate
    wire supported_business=header[0]==4 || (header[0]>=8'h20 && header[0]<=8'h23) ||
        (header[0]>=8'h30 && header[0]<=8'h42 && header[0]!=8'h3a); 
    wire [15:0] fragment_token={frag[2],frag[1]};
    reg [7:0] current_reply_byte;
    assign busy=state!=IDLE;
    assign response_data=reply[response_addr];
    assign response_is_data=(reply_opcode==8'h31 || reply_opcode==8'h35 || reply_opcode==8'h3e || reply_opcode==8'h3f || reply_opcode==8'h41 || reply_opcode==8'h42) && reply_result==0;
    wire reply_we=resetn && enable && (state==BUILD || state==CRC || state==REPLAY);
    wire [6:0] reply_write_addr=state==CRC ? response_length-4+index : index;
    wire [7:0] reply_write_data=state==CRC ? le32(~crc_work,index) : state==REPLAY ? reply_cache_data : current_reply_byte;
    // Write-through single-port RAM is supported by GW5A (NO_CHANGE is not).
    wire request_cache_we=resetn && enable && state==STORE_REQ;
    wire [10:0] request_cache_addr={cache_slot,index[5:0]};
    wire [31:0] recording_id, recorded_frames, capacity_frames;
    wire reply_cache_we=resetn && enable && accept_request && (state==BUILD || state==CRC || state==STORE_META);
    wire [11:0] reply_cache_addr=(state==STORE_META || state==META_ADDR || state==META_READ) ?
        {cache_slot,7'd124}+index : state==CRC ?
        {cache_slot,7'd0}+response_length-4+index : {cache_slot,index};
    wire [7:0] reply_cache_write_data=state==STORE_META ? le32(recording_id,index) : state==CRC ? le32(~crc_work,index) : current_reply_byte;
    always @(posedge clk) begin
        if(reply_we) begin
            reply[reply_write_addr]<=reply_write_data;
            if(reply_write_addr==0) reply_opcode<=reply_write_data;
            if(reply_write_addr==1) reply_result<=reply_write_data;
        end
        if(request_cache_we) begin
            request_cache[request_cache_addr]<=header[index];
            request_cache_data<=header[index];
        end else request_cache_data<=request_cache[request_cache_addr];
        if(reply_cache_we) begin
            reply_cache[reply_cache_addr]<=reply_cache_write_data;
            reply_cache_data<=reply_cache_write_data;
        end else reply_cache_data<=reply_cache[reply_cache_addr];
    end
    reg recording_start, recording_replay;
    wire engine_done;
    wire recording_done;
    wire [7:0] engine_status,engine_byte,record_state;
    wire [7:0] recording_result;
    wire [7:0] recording_byte;
    wire [6:0] engine_result_length;
    wire [6:0] recording_length;
    reg [31:0] replay_object_id;
    reg [7:0] snapshot_record_state;
    reg [31:0] snapshot_recording_id,snapshot_recorded_frames;
    wire [127:0] recording_payload={header[31],header[30],header[29],header[28],header[27],header[26],header[25],header[24],
        header[23],header[22],header[21],header[20],header[19],header[18],header[17],header[16]};
    reg cpu_offer,cpu_uncertain_fence;
    reg [31:0] business_session;
    reg business_session_q;
    wire cpu_admitted,cpu_rejected,cpu_request_ready;
    wire cpu_completion_valid;
    wire [7:0] cpu_completion_status,cpu_completion_reason,cpu_completion_phase;
    wire [6:0] cpu_completion_length;
    wire cpu_read_ready,cpu_data_valid;
    wire [7:0] cpu_data_byte;
    wire cpu_read_valid=state==BUILD_FETCH && !reply_status[7] && header[0]!=1 && header[0]!=2 && index>=16;
    wire [5:0] cpu_read_address=index-7'd16;
    wire cpu_consume=(state==RECORD_WAIT || state==REPLAY_RECORD_WAIT) && cpu_completion_valid;
    wire [31:0] cpu_key_ticket,cpu_key_owner,cpu_key_session;wire [63:0] cpu_key_boot;
    wire mb_ready,mb_error,data_ready,data_error,data_observer_fault;
    wire [31:0] mb_read,data_read;
    wire data_select=business_command_address_i[11:8]==1;
    assign business_command_ready_o=data_select ? data_ready:mb_ready;
    assign business_response_error_o=data_select ? data_error:mb_error;
    assign business_response_data_o=data_select ? data_read:mb_read;
    wire data_engine_start,data_engine_idle;
    wire [7:0] data_engine_opcode;
    wire [15:0] data_engine_length;
    wire [31:0] data_engine_request,data_engine_object,data_engine_transfer;
    wire [63:0] data_engine_nonce;
    wire [127:0] data_engine_payload;
    wire [383:0] data_engine_result;
    wire [31:0] data_crc_fact,data_reason_fact,data_first_ms,data_terminal_ms,data_block_crc,data_command_ms;
    wire [4:0] data_engine_flags;wire data_block_crc_valid,data_read_accepted;
    wire data_source_good,data_mutation_hold;
    assign recording_done=cpu_completion_valid;
    assign recording_result=cpu_completion_status;
    assign recording_byte=cpu_data_byte;
    assign recording_length=cpu_completion_length;
    always @(posedge clk or negedge resetn)begin
        if(!resetn)begin business_session<=0;business_session_q<=0;end
        else begin
            business_session_q<=session_active;
            if(session_active && !business_session_q && business_session!=32'hffffffff)
                business_session<=business_session+1'b1;
        end
    end
    workstation_business_mailbox cpu_mailbox(
        .clk_i(clk),.rst_ni(resetn),.owner_reset_ni(business_owner_reset_ni),
        .boot_valid_i(boot_valid && !data_observer_fault),.boot_id_i(boot_id),
        .control_open_i(enable && session_active),.session_generation_i(business_session),
        .fence_i(data_observer_fault || business_session==32'hffffffff),.cancel_i(1'b0),
        .request_offer_i(cpu_offer),.request_opcode_i(header[0]),.request_reserved_i(8'd0),
        .request_length_i(payload_length),.request_id_i(request_id),.request_nonce_i(request_nonce),
        .request_payload_i(recording_payload),.request_ready_o(cpu_request_ready),
        .request_admitted_o(cpu_admitted),.request_rejected_o(cpu_rejected),.request_reject_reason_o(),
        .command_valid_i(business_command_valid_i && !data_select),.command_write_i(business_command_write_i),
        .command_address_i(business_command_address_i),.command_data_i(business_command_data_i),
        .command_strobes_i(business_command_strobes_i),.command_ready_o(mb_ready),
        .response_error_o(mb_error),.response_data_o(mb_read),.completion_valid_o(cpu_completion_valid),
        .completion_consume_i(cpu_consume),.completion_ticket_o(cpu_key_ticket),.completion_owner_o(cpu_key_owner),
        .completion_session_o(cpu_key_session),.completion_boot_o(cpu_key_boot),.completion_phase_o(cpu_completion_phase),
        .completion_status_o(cpu_completion_status),.completion_reason_o(cpu_completion_reason),
        .completion_length_o(cpu_completion_length),.completion_operation_o(),
        .completion_read_valid_i(cpu_read_valid),.completion_read_ready_o(cpu_read_ready),
        .completion_read_address_i(cpu_read_address),.completion_data_valid_o(cpu_data_valid),
        .completion_data_o(cpu_data_byte));
    wire physical_recording_enable=recording_enable || SINGLE_BLE_RECORDING;
    workstation_ble_record_data_service #(.CAPACITY_FRAMES(CAPACITY_FRAMES)) cpu_data(
        .clk_i(clk),.rst_ni(resetn),.owner_reset_ni(business_owner_reset_ni),
        .command_valid_i(business_command_valid_i && data_select),.command_write_i(business_command_write_i),
        .command_address_i(business_command_address_i[7:0]),.command_data_i(business_command_data_i),
        .command_strobes_i(business_command_strobes_i),.command_ready_o(data_ready),
        .response_error_o(data_error),.response_data_o(data_read),
        .record_state_i(record_state),.object_id_i(recording_id),.frames_i(recorded_frames),
        .committed_i(raw_committed_frames_i),.crc_i(data_crc_fact),.stop_reason_i(data_reason_fact),
        .first_frame_ms_i(data_first_ms),.terminal_ms_i(data_terminal_ms),
        .source_good_i(data_source_good),.mutation_hold_i(data_mutation_hold),
        .transfer_valid_i(transfer_valid),
        .request_admitted_i(cpu_admitted),.request_replay_i(recording_replay),.request_object_i(replay_object_id),
        .request_ticket_i(cpu_key_ticket),.request_owner_i(cpu_key_owner),.request_session_i(cpu_key_session),.request_boot_i(cpu_key_boot),
        .enabled_i(physical_recording_enable),.subscribed_i(transfer_subscribed),.engine_idle_i(data_engine_idle),
        .att_value_limit_i(att_value_limit),.elapsed_ms_i(elapsed_ms),.engine_time_ms_i(data_command_ms),
        .engine_block_crc_i(data_block_crc),.engine_block_crc_valid_i(data_block_crc_valid),.engine_read_accepted_i(data_read_accepted),
        .engine_start_o(data_engine_start),.engine_opcode_o(data_engine_opcode),.engine_flags_o(data_engine_flags),
        .engine_length_o(data_engine_length),.engine_request_o(data_engine_request),
        .engine_object_o(data_engine_object),.engine_transfer_o(data_engine_transfer),
        .engine_nonce_o(data_engine_nonce),.engine_payload_o(data_engine_payload),
        .engine_done_i(engine_done),.engine_status_i(engine_status),
        .engine_length_i(engine_result_length),.engine_result_i(data_engine_result),
        .observer_fault_o(data_observer_fault));
    workstation_ble_record_data_engine #(.ALLOW_LOCAL_RECORDING(SINGLE_BLE_RECORDING),.EXTERNAL_SEAL_PROTOCOL(EXTERNAL_SEAL_PROTOCOL),.EXTERNAL_RAW_STORE(EXTERNAL_RAW_STORE),.RAW_DRAIN_TIMEOUT_CYCLES(RAW_DRAIN_TIMEOUT_CYCLES),.CLK_HZ(CLK_HZ),.AUDIO_FILE(AUDIO_FILE),.EXTERNAL_PCM(EXTERNAL_PCM),.CAPACITY_FRAMES(CAPACITY_FRAMES)) recording (
        .clk(clk),.resetn(resetn),.enable(physical_recording_enable),.connected(enable),
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
        .transfer_subscribed(transfer_subscribed),.boot_id(boot_id),.att_value_limit(att_value_limit),.elapsed_ms(elapsed_ms),
        .command_start(data_engine_start),.command_flags_i(data_engine_flags),
        .command_object_id_i(data_engine_object),.command_transfer_id_i(data_engine_transfer),
        .idle_o(data_engine_idle),.command_result_o(data_engine_result),
        .object_crc_o(data_crc_fact),.stop_reason_o(data_reason_fact),
        .block_crc_o(data_block_crc),.block_crc_valid_o(data_block_crc_valid),.read_accepted_o(data_read_accepted),.command_time_ms_o(data_command_ms),
        .first_frame_ms_o(data_first_ms),.terminal_ms_o(data_terminal_ms),
        .source_good_o(data_source_good),.mutation_hold_o(data_mutation_hold),
        .opcode(data_engine_opcode),
        .request_id(data_engine_request),
        .nonce(data_engine_nonce),
        .payload_length(data_engine_length),
        .payload(data_engine_payload),
        .command_done(engine_done),.command_status(engine_status),.command_length(engine_result_length),
        .command_addr(index-7'd16),.command_data(engine_byte),
        .record_state(record_state),.recording_id(recording_id),.recorded_frames(recorded_frames),.capacity_frames(capacity_frames),
        .transfer_valid(transfer_valid),.transfer_compact(transfer_compact),.transfer_bulk(transfer_bulk),.transfer_direct(transfer_direct),.transfer_length(transfer_length),.transfer_addr(transfer_addr),
        .transfer_data(transfer_data),.transfer_consume(transfer_consume));
    function [31:0] crc_byte;
        input [31:0] c0;
        input [7:0] data;
        reg [31:0] c;
        integer b;
        begin
            c=c0^data;
            for(b=0;b<8;b=b+1) c=(c>>1)^(c[0]?32'hedb88320:0);
            crc_byte=c;
        end
    endfunction
    function [7:0] le32;
        input [31:0] value;
        input [1:0] at;
        begin case(at) 0:le32=value[7:0];1:le32=value[15:8];
            2:le32=value[23:16];3:le32=value[31:24];endcase end
    endfunction
    function [7:0] logical_byte;
        input [6:0] at;
        integer n;
        begin
            logical_byte=0;
            if(at==0) logical_byte=header[0];
            else if(at==1) logical_byte=reply_status;
            else if(at==2) logical_byte=response_length-20;
            else if(at>=4 && at<16) logical_byte=header[at];
            else if(at>=16) begin
                n=at-16;
                if(reply_status[7]) begin
                    if(n==0) logical_byte=reply_detail[7:0];
                    if(n==1) logical_byte=reply_detail[15:8];
                    if(n==4) logical_byte=1; // config_revision
                end else if(header[0]==1) begin
                    if(n<8) logical_byte=boot_id >> (8*n);
                    else if(n==8) logical_byte=8'h68;
                    else if(n==12) logical_byte=1;
                    else if(n>=16 && n<20) logical_byte=le32(snapshot_time,n-16);
                end else if(header[0]==2) begin
                    if(n<4) logical_byte=le32(snapshot_number,n);
                    else if(n<8) logical_byte=le32(snapshot_time,n-4);
                    else if(n==8) logical_byte=4; // only recording group valid
                    else if(n==27) logical_byte=snapshot_record_state;
                    else if(n>=28 && n<32) logical_byte=le32(snapshot_recording_id,n-28);
                    else if(n>=32 && n<36) logical_byte=le32(snapshot_recorded_frames,n-32);
                    else if(n>=36 && n<40) logical_byte=le32(capacity_frames,n-36);
                    else if(n==44) logical_byte=8; // local test window open
                end else logical_byte=recording_byte;
            end
        end
    endfunction
    task finish_fragment;
        input [7:0] error;
        begin fragment_error<=error; fragment_done<=1; state<=IDLE; end
    endtask
    task error_reply;
        input [7:0] status;
        input [15:0] detail;
        begin
            reply_status<=status; reply_detail<=detail; accept_request<=0;
            response_length<=28; index<=0; crc_work<=32'hffffffff;
            state<=BUILD_FETCH;
        end
    endtask
    always @(posedge clk) begin
        fragment_done<=0; recording_start<=0;cpu_offer<=0;
        if(fragment_write && fragment_addr<20) frag[fragment_addr]<=fragment_data;
        if(!resetn || !enable) begin
            state<=IDLE; fragment_error<=0; response_valid<=0;
            response_length<=0; previous_valid<=0; assembling<=0;
            total<=0; token<=0; next_fragment<=0; last_fragment_ms<=0;
            session_active<=0; session_nonce<=0; high_water<=0;
            cache_valid<=0; cache_next<=0; cache_slot<=0; lookup_slot<=0;
            index<=0; frag_size<=0; prev_size<=0; crc_work<=32'hffffffff;
            reply_status<=0; reply_detail<=0; accept_request<=0;
            snapshot_counter<=0; snapshot_time<=0; snapshot_number<=0;
            recording_start<=0;recording_replay<=0;current_reply_byte<=0;cpu_offer<=0;cpu_uncertain_fence<=0;
            snapshot_record_state<=0;snapshot_recording_id<=0;snapshot_recorded_frames<=0;
            summary<=0; accepted_count<=0; crc_reject_count<=0;
        end else begin
            if(response_consume) response_valid<=0;
            if(assembling && elapsed_ms-last_fragment_ms>=2000) begin assembling<=0; previous_valid<=0; end
            if(summary_latch) begin
                snapshot_counter<=snapshot_counter+1;
                summary<={8'h08,8'hff,8'hff,record_state,recording_id,32'd1,elapsed_ms,snapshot_counter+1'b1};
            end
            case(state)
                IDLE: if(fragment_start) begin
                    frag_size<=fragment_length; index<=0; state<=CHECK;
                end
                CHECK: begin
                    if(frag_size<7 || frag_size>20 || frag[0]!=8'hb1 ||
                       frag[5]<1 || frag[5]>14 || frag_size!=6+frag[5] ||
                       (!frag[4][1] && frag[5]!=14) || frag[3]>36) begin
                        assembling<=0; previous_valid<=0; finish_fragment(8'h0d);
                    end else if(frag[4][7:2]!=0 || (frag[4][0]!=(frag[3]==0))) begin
                        assembling<=0; previous_valid<=0; finish_fragment(8'h80);
                    end else if(previous_valid && prev_size==frag_size &&
                                previous[1]==frag[1] && previous[2]==frag[2] && previous[3]==frag[3]) begin
                        index<=0; state<=DUP;
                    end else state<=ORDER;
                end
                DUP: begin
                    if(frag[index]!=previous[index]) begin
                        assembling<=0; previous_valid<=0; finish_fragment(8'h80);
                    end else if(index+1==frag_size) finish_fragment(0);
                    else index<=index+1'b1;
                end
                ORDER: begin
                    if(response_valid || transfer_valid) finish_fragment(8'h11);
                    else if(!response_subscribed || !boot_valid || !control_open) begin
                        assembling<=0; finish_fragment(8'h80);
                    end else if(!frag[4][0] && (!assembling || elapsed_ms-last_fragment_ms>=2000 ||
                                token!=fragment_token || next_fragment!=frag[3])) begin
                        assembling<=0; finish_fragment(8'h80);
                    end else if((frag[4][0] ? 0 : total)+frag[5]>512) begin
                        assembling<=0; finish_fragment(8'h0d);
                    end else begin
                        if(frag[4][0]) begin total<=0; crc_work<=32'hffffffff; end
                        token<=fragment_token; next_fragment<=frag[3]+1'b1;
                        assembling<=!frag[4][1]; last_fragment_ms<=elapsed_ms;
                        index<=0; state<=COPY;
                    end
                end
                COPY: begin
                    // Save exact preceding fragment, including its header.
                    if(index<frag_size) previous[index]<=frag[index];
                    if(index<frag[5]) begin
                        if(total<36) header[total]<=frag[6+index];
                        crc_work<=crc_byte(crc_work,frag[6+index]); total<=total+1'b1;
                    end
                    if(index+1==frag_size) begin
                        previous_valid<=1; prev_size<=frag_size;
                        if(frag[4][1]) state<=VALIDATE;
                        else finish_fragment(0);
                    end else index<=index+1'b1;
                end
                VALIDATE: begin
                    if(total<20 || payload_length>492 || total!=20+payload_length ||
                       crc_work!=32'hdebb20e3) begin
                        crc_reject_count<=crc_reject_count+1; finish_fragment(0);
                    end else if(request_id==0) finish_fragment(8'h80);
                    else state<=SESSION;
                end
                SESSION: begin
                    if(header[1]!=0) error_reply(8'h81,3);
                    else if(header[0]==1 && session_active && request_nonce!=session_nonce)
                        error_reply(8'h82,0);
                    else if(header[0]!=1 && (!session_active || request_nonce!=session_nonce))
                        error_reply(8'h85,0);
                    else if(request_id<=high_water) begin lookup_slot<=0; state<=LOOKUP; end
                    else state<=DISPATCH;
                end
                LOOKUP: begin
                    if(metadata_hit) begin
                        cache_slot<=lookup_slot; index<=0;
                        if(total!=metadata_request_length) error_reply(8'h86,0);
                        else state<=COMPARE_ADDR;
                    end else if(lookup_slot==31) error_reply(8'h87,0);
                    else lookup_slot<=lookup_slot+1'b1;
                end
                COMPARE_ADDR: state<=COMPARE;
                COMPARE: begin
                    if(header[index]!=request_cache_data) error_reply(8'h86,0);
                    else if(index+1==total) begin
                        response_length<=metadata_reply_length;
                        index<=0;
                        if(header[0]==8'h31 || header[0]==8'h35 || header[0]==8'h3e || header[0]==8'h3f || header[0]==8'h41 || header[0]==8'h42) state<=META_ADDR;
                        else state<=REPLAY_ADDR;
                    end else begin index<=index+1'b1; state<=COMPARE_ADDR; end
                end
                DISPATCH: begin
                    if(header[0]==1 && (payload_length!=4 || header[16]!=1 ||
                         header[17]!=0 || header[18]!=0 || header[19]!=0)) error_reply(8'h81,1);
                    else if(header[0]==1 && (request_nonce==0 || (!session_active && request_id!=1)))
                        error_reply(8'h81,2);
                    else if(header[0]==2 && payload_length!=0) error_reply(8'h81,1);
                                        else if(header[0]==1 && session_active) error_reply(8'h82,0);
                    else if(header[0]!=1 && header[0]!=2) begin
                        if(cpu_uncertain_fence && header[0]!=4 && header[0]!=8'h22)error_reply(8'h82,0);
                        else if(payload_length>16)error_reply(supported_business ? 8'h81:8'h80,0);
                        else begin cpu_offer<=1;recording_replay<=0;state<=RECORD_WAIT;end
                    end else begin
                        if(header[0]==1) begin session_active<=1; session_nonce<=request_nonce; end
                        else begin snapshot_counter<=snapshot_counter+1; snapshot_number<=snapshot_counter+1; end
                        snapshot_record_state<=record_state;snapshot_recording_id<=recording_id;snapshot_recorded_frames<=recorded_frames;
                        snapshot_time<=elapsed_ms; high_water<=request_id;
                        accepted_count<=accepted_count+1; accept_request<=1;
                        reply_status<=0; reply_detail<=0;
                        response_length<=header[0]==1 ? 40 : 84;
                        cache_slot<=cache_next; index<=0; state<=STORE_REQ;
                    end
                end
                RECORD_WAIT: begin
                    if(cpu_rejected)error_reply(8'h82,0);
                    else if(cpu_completion_valid)begin
                        if(cpu_completion_reason!=0)begin
                            if(cpu_completion_phase==5)cpu_uncertain_fence<=1;
                            error_reply(8'h82,0);
                        end else if(cpu_completion_status[7])error_reply(cpu_completion_status,0);
                        else begin
                            high_water<=request_id;accepted_count<=accepted_count+1;accept_request<=1;
                            reply_status<=cpu_completion_status;reply_detail<=0;response_length<=cpu_completion_length+20;
                            cache_slot<=cache_next;index<=0;state<=STORE_REQ;
                        end
                    end
                end
                REPLAY_RECORD_WAIT: if(recording_done) begin
                    if(cpu_completion_reason!=0)begin
                        if(cpu_completion_phase==5)cpu_uncertain_fence<=1;error_reply(8'h82,0);
                    end else if(recording_result[7]) error_reply(recording_result,0);
                    else begin index<=0;state<=REPLAY_ADDR;end
                end
                STORE_REQ: begin
                    if(index+1==total) begin index<=0; crc_work<=32'hffffffff; state<=BUILD_FETCH; end
                    else index<=index+1'b1;
                end
                BUILD_FETCH: begin
                    // The consumed result bank retains its bytes until the
                    // next COMPLETE. This parser cannot offer another command
                    // until this reply has been copied into its existing cache.
                    if(cpu_read_valid)begin
                        if(cpu_read_ready)state<=BUILD_DATA;
                    end else begin current_reply_byte<=logical_byte(index);state<=BUILD;end
                end
                BUILD_DATA: if(cpu_data_valid)begin current_reply_byte<=recording_byte;state<=BUILD;end
                BUILD: begin
                    crc_work<=crc_byte(crc_work,current_reply_byte);
                    if(index+5==response_length) begin index<=0; state<=CRC; end
                    else begin index<=index+1'b1;state<=BUILD_FETCH;end
                end
                CRC: begin
                    if(index==3) begin
                        if(accept_request) begin
                            cache_valid[cache_slot]<=1; cache_next<=cache_next+1'b1;
                        end
                        if(accept_request) begin index<=0;state<=STORE_META;end
                        else state<=DONE;
                    end else index<=index+1'b1;
                end
                STORE_META: if(index==3) state<=DONE;else index<=index+1'b1;
                META_ADDR: state<=META_READ;
                META_READ: begin
                    replay_object_id[8*index+:8]<=reply_cache_data;
                    if(index==3) begin cpu_offer<=1;recording_replay<=1;state<=REPLAY_RECORD_WAIT;end
                    else begin index<=index+1'b1;state<=META_ADDR;end
                end
                REPLAY_ADDR: state<=REPLAY;
                REPLAY: begin
                    if(index+1==response_length) state<=DONE;
                    else begin index<=index+1'b1; state<=REPLAY_ADDR; end
                end
                DONE: begin response_valid<=1; finish_fragment(0); end
                default: state<=IDLE;
            endcase
        end
    end
endmodule
