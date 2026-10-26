// v1 business endpoint with a built-in-audio recording/download slot.
// Fragment payloads stream through CRC32; accepted requests fit in 36 bytes.
// Every byte of longer unsupported requests is still checked before rejection.
module ble_protocol_command #(parameter CLK_HZ=50000000, parameter AUDIO_FILE="audio/test_tone.mem",
    parameter EXTERNAL_PCM=0, parameter CAPACITY_FRAMES=48000) (
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
    output reg [31:0] crc_reject_count
);
    localparam IDLE=0,CHECK=1,DUP=2,ORDER=3,COPY=4,VALIDATE=5,
        SESSION=6,LOOKUP=7,COMPARE_ADDR=8,COMPARE=9,DISPATCH=10,
        STORE_REQ=11,BUILD=12,CRC=13,REPLAY_ADDR=14,REPLAY=15,DONE=16,RECORD_WAIT=17,BUILD_FETCH=18,REPLAY_RECORD_WAIT=19,STORE_META=20,META_ADDR=21,META_READ=22;
    reg [4:0] state;
    reg [7:0] frag[0:19], previous[0:19], header[0:35];
    reg [7:0] reply[0:127];
    (* ram_style="block" *) reg [7:0] request_cache[0:2047];
    (* ram_style="block" *) reg [7:0] reply_cache[0:4095];
    reg [31:0] cache_id[0:31], cache_time[0:31];
    reg [5:0] cache_req_length[0:31];
    reg [6:0] cache_reply_length[0:31];
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
    wire [15:0] fragment_token={frag[2],frag[1]};
    reg [7:0] current_reply_byte;
    assign busy=state!=IDLE;
    assign response_data=reply[response_addr];
    assign response_is_data=(reply[0]==8'h31 || reply[0]==8'h35 || reply[0]==8'h3e || reply[0]==8'h3f || reply[0]==8'h41 || reply[0]==8'h42) && reply[1]==0;
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
    wire recording_done;
    wire [7:0] recording_result, recording_byte, record_state;
    wire [6:0] recording_length;
    reg [31:0] replay_object_id;
    reg [7:0] snapshot_record_state;
    reg [31:0] snapshot_recording_id,snapshot_recorded_frames;
    wire [127:0] recording_payload={header[31],header[30],header[29],header[28],header[27],header[26],header[25],header[24],
        header[23],header[22],header[21],header[20],header[19],header[18],header[17],header[16]};
    ble_recording #(.CLK_HZ(CLK_HZ),.AUDIO_FILE(AUDIO_FILE),.EXTERNAL_PCM(EXTERNAL_PCM),.CAPACITY_FRAMES(CAPACITY_FRAMES)) recording (
        .clk(clk),.resetn(resetn),.enable(recording_enable),.connected(enable),
        .pcm_valid_i(pcm_valid_i),.pcm_pair_i(pcm_pair_i),.source_ready_i(source_ready_i),.source_fault_i(source_fault_i),
        .transfer_subscribed(transfer_subscribed),.boot_id(boot_id),.att_value_limit(att_value_limit),.elapsed_ms(elapsed_ms),
        .command_start(recording_start),.command_replay(recording_replay),
        .opcode(header[0]),.request_id(request_id),.nonce(request_nonce),
        .payload_length(payload_length),.payload(recording_payload),
        .replay_recording_id(replay_object_id),
        .command_done(recording_done),.command_status(recording_result),.command_length(recording_length),
        .command_addr(index-7'd16),.command_data(recording_byte),
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
        fragment_done<=0; recording_start<=0;
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
            recording_start<=0;recording_replay<=0;current_reply_byte<=0;
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
                    if(cache_valid[lookup_slot] && elapsed_ms-cache_time[lookup_slot]<60000 &&
                       cache_id[lookup_slot]==request_id) begin
                        cache_slot<=lookup_slot; index<=0;
                        if(total!=cache_req_length[lookup_slot]) error_reply(8'h86,0);
                        else state<=COMPARE_ADDR;
                    end else if(lookup_slot==31) error_reply(8'h87,0);
                    else lookup_slot<=lookup_slot+1'b1;
                end
                COMPARE_ADDR: state<=COMPARE;
                COMPARE: begin
                    if(header[index]!=request_cache_data) error_reply(8'h86,0);
                    else if(index+1==total) begin
                        response_length<=cache_reply_length[cache_slot];
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
                        recording_start<=1;recording_replay<=0;state<=RECORD_WAIT;
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
                RECORD_WAIT: if(recording_done) begin
                    if(recording_result[7]) error_reply(recording_result,0);
                    else begin
                        high_water<=request_id;accepted_count<=accepted_count+1;accept_request<=1;
                        reply_status<=recording_result;reply_detail<=0;response_length<=recording_length+20;
                        cache_slot<=cache_next;index<=0;state<=STORE_REQ;
                    end
                end
                REPLAY_RECORD_WAIT: if(recording_done) begin
                    if(recording_result[7]) error_reply(recording_result,0);
                    else begin index<=0;state<=REPLAY_ADDR;end
                end
                STORE_REQ: begin
                    if(index+1==total) begin index<=0; crc_work<=32'hffffffff; state<=BUILD_FETCH; end
                    else index<=index+1'b1;
                end
                BUILD_FETCH: begin current_reply_byte<=logical_byte(index);state<=BUILD;end
                BUILD: begin
                    reply[index]<=current_reply_byte;
                    crc_work<=crc_byte(crc_work,current_reply_byte);
                    if(index+5==response_length) begin index<=0; state<=CRC; end
                    else begin index<=index+1'b1;state<=BUILD_FETCH;end
                end
                CRC: begin
                    reply[response_length-4+index]<=le32(~crc_work,index);
                    if(index==3) begin
                        if(accept_request) begin
                            cache_valid[cache_slot]<=1; cache_id[cache_slot]<=request_id;
                            cache_time[cache_slot]<=elapsed_ms; cache_req_length[cache_slot]<=total;
                            cache_reply_length[cache_slot]<=response_length; cache_next<=cache_next+1'b1;
                        end
                        if(accept_request) begin index<=0;state<=STORE_META;end
                        else state<=DONE;
                    end else index<=index+1'b1;
                end
                STORE_META: if(index==3) state<=DONE;else index<=index+1'b1;
                META_ADDR: state<=META_READ;
                META_READ: begin
                    replay_object_id[8*index+:8]<=reply_cache_data;
                    if(index==3) begin recording_start<=1;recording_replay<=1;state<=REPLAY_RECORD_WAIT;end
                    else begin index<=index+1'b1;state<=META_ADDR;end
                end
                REPLAY_ADDR: state<=REPLAY;
                REPLAY: begin
                    reply[index]<=reply_cache_data;
                    if(index+1==response_length) state<=DONE;
                    else begin index<=index+1'b1; state<=REPLAY_ADDR; end
                end
                DONE: begin response_valid<=1; finish_fragment(0); end
                default: state<=IDLE;
            endcase
        end
    end
endmodule
