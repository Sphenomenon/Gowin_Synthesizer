// 138K physical recording/data engine. IDs are supplied by the sole C owner.
// Capture, CRC, seal/drain, fetch, codec and wire bytes only; C owns policy.
module workstation_ble_record_data_engine #(
    parameter CLK_HZ=50000000,
    parameter AUDIO_FILE="audio/test_tone.mem",
    parameter CAPACITY_FRAMES=48000,
    parameter EXTERNAL_PCM=0,
    parameter EXTERNAL_SEAL_PROTOCOL=0,
    parameter integer SEAL_TIMEOUT_CYCLES=64,
    parameter EXTERNAL_RAW_STORE=0,
    parameter ALLOW_LOCAL_RECORDING=0,
    parameter DUAL_RATE_RECORDING=0,
    parameter integer RAW_DRAIN_TIMEOUT_CYCLES=0
)(
    input wire clk, resetn, enable, connected, transfer_subscribed,
    input wire pcm_valid_i, source_ready_i, source_fault_i,
    input wire [31:0] pcm_pair_i,
    // Opt-in physical source fact, on clk. Never a requested clock setting.
    input wire [7:0] source_format_i,
    output reg [7:0] object_format_o,
    output wire [31:0] object_rate_o,
    input wire [63:0] boot_id,
    input wire [8:0] att_value_limit,
    input wire [31:0] elapsed_ms,
    input wire command_start,
    input wire [4:0] command_flags_i,
    input wire [31:0] command_object_id_i,command_transfer_id_i,
    output wire idle_o,
    output wire [383:0] command_result_o,
    output wire [31:0] object_crc_o,stop_reason_o,
    output reg [31:0] command_time_ms_o,
    output reg block_crc_valid_o,read_accepted_o,
    output wire [31:0] block_crc_o,
    output reg [31:0] first_frame_ms_o,terminal_ms_o,
    output wire source_good_o,mutation_hold_o,
    input wire [7:0] opcode,
    input wire [31:0] request_id,
    input wire [63:0] nonce,
    input wire [15:0] payload_length,
    input wire [127:0] payload,
    output reg command_done,
    output reg [7:0] command_status,
    output reg [6:0] command_length,
    input wire [6:0] command_addr,
    output wire [7:0] command_data,
    output reg [7:0] record_state,
    output reg [31:0] recording_id, recorded_frames,
    output wire [31:0] capacity_frames,
    output reg transfer_valid,
    output reg transfer_compact,
    output reg transfer_bulk,
    output reg transfer_direct,
    output reg [12:0] transfer_length,
    input wire [12:0] transfer_addr,
    output reg [7:0] transfer_data,
    input wire transfer_consume,
    // Local clock policy only; no new BLE opcode or recording format.
    input wire seal_hold_i, seal_request_i,
    output wire seal_ready_o,
    output reg seal_pending_o, seal_done_o, seal_failed_o,
    output reg [3:0] seal_failure_code_o,
    output reg [7:0] seal_record_state_o,
    output reg [31:0] seal_recording_id_o, seal_frames_o, seal_crc_o,
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
    localparam [31:0] CAPACITY=CAPACITY_FRAMES;
    localparam C_IDLE=0,C_OPERATION=1,C_BLOCK_PREP=2,C_BLOCK_CRC=3,
        C_DATA_PREP=4,C_DATA_BUILD=5,C_DATA_CRC=6,C_CODEC_START=7,C_CODEC_WAIT=8,
        C_RAW_START=9,C_RAW_CLEAR=10,C_RAW_FETCH_REQ=11,C_RAW_FETCH_WAIT=12;
    reg [3:0] state;
    reg raw_closing,raw_cache_owned,raw_clear_sent;
    wire raw_seal_admission;
    reg [383:0] result_payload;
    assign command_data=result_payload>>(8*command_addr);
    assign command_result_o=result_payload,idle_o=state==C_IDLE;
    assign capacity_frames=CAPACITY_FRAMES;
    reg [31:0] limit_frames, object_crc, recording_crc;
    reg [15:0] stop_reason;
    reg [31:0] sample_phase;
    assign object_rate_o=DUAL_RATE_RECORDING && object_format_o==2 ? 32'd44100:32'd48000;
    wire sample_tick=sample_phase+object_rate_o>=CLK_HZ;
    wire requested_format_valid=payload[31:0]==1 || (DUAL_RATE_RECORDING && payload[31:0]==2);
    wire source_format_matches=!DUAL_RATE_RECORDING || source_format_i==object_format_o;
    wire start_source_good=source_ready_i && !source_fault_i &&
        (!DUAL_RATE_RECORDING || source_format_i==payload[7:0]);
    reg [2:0] capture_state;
    reg [31:0] capture_word;
    reg stop_pending;
    reg seal_request_q,seal_failed_seen,seal_initial_error,seal_requires_source;
    reg [31:0] seal_wait;
    assign seal_ready_o=EXTERNAL_SEAL_PROTOCOL && !seal_pending_o && !seal_request_q &&
        (!EXTERNAL_RAW_STORE || raw_seal_admission);
    wire seal_begin=seal_request_i && seal_ready_o;
    wire external_mutation_hold=EXTERNAL_SEAL_PROTOCOL && (seal_hold_i || seal_request_i || seal_pending_o);
    wire external_capture_hold=(EXTERNAL_SEAL_PROTOCOL && (seal_request_i || seal_pending_o)) ||
        (EXTERNAL_RAW_STORE && (raw_closing || raw_clear_sent || raw_fault_i));
    wire recording_active=record_state==1 || record_state==2 || record_state==3;
    // Trusted CPU descriptor only. Bit4 retains its existing Rice meaning for
    // READ; no external opcode, wire flag, or second capture owner is added.
    wire local_record_command=ALLOW_LOCAL_RECORDING && command_flags_i==5'b10000 &&
        (opcode==8'h20 || opcode==8'h21 || opcode==8'h23);
    wire command_link_ready=connected || local_record_command;
    wire seal_commit=EXTERNAL_SEAL_PROTOCOL && seal_pending_o &&
        recording_active && capture_state==0 && recording_id==seal_recording_id_o;
    wire seal_source_lost=seal_requires_source && (!enable || (EXTERNAL_PCM && (!source_ready_i || source_fault_i || !source_format_matches)));
    wire seal_current_error=seal_source_lost || recording_id!=seal_recording_id_o || record_state==5;
    reg [31:0] data_request, data_transfer, data_recording, data_offset, data_crc;
    reg [63:0] data_nonce;
    reg [12:0] data_length, data_wire_length, index;
    reg data_lossless,data_second;
    reg [7:0] data_codec;
    reg [31:0] crc_work;
    wire [31:0] object_bytes=recorded_frames<<2;
    wire [31:0] read_offset=payload[63:32];
    wire [15:0] read_length=payload[79:64];
    wire [31:0] data_absolute=data_offset+index-44;
    wire [12:0] codec_sample_addr,codec_write_addr,codec_length;
    wire [7:0] codec_write_data;
    wire codec_write_valid,codec_done,codec_rice,codec_second;
    wire codec_active=state==C_CODEC_START || state==C_CODEC_WAIT;
    wire [31:0] codec_absolute=data_offset+{19'd0,codec_sample_addr};
    wire [31:0] sample_address=codec_active ? codec_absolute>>2 :(state==C_DATA_PREP || state==C_DATA_BUILD) ? data_absolute>>2 :
        (state==C_BLOCK_PREP || state==C_BLOCK_CRC) ? (data_offset+index)>>2 : recorded_frames;
    reg [31:0] raw_wait;
    wire raw_waiting=raw_closing || state==C_RAW_START || state==C_RAW_CLEAR ||
        state==C_RAW_FETCH_REQ || state==C_RAW_FETCH_WAIT;
    wire raw_expired=EXTERNAL_RAW_STORE && raw_waiting && raw_wait>=RAW_DRAIN_TIMEOUT_CYCLES-1;
    wire raw_processing=state==C_BLOCK_PREP || state==C_BLOCK_CRC || state==C_CODEC_START ||
        state==C_CODEC_WAIT || state==C_DATA_PREP || state==C_DATA_BUILD || state==C_DATA_CRC;
    wire raw_cache_live=raw_cache_owned && raw_cache_valid_i && !raw_fault_i;
    assign raw_seal_admission=!raw_clear_sent && !raw_closing && state!=C_RAW_START && state!=C_RAW_CLEAR &&
        !raw_channel_fault_i && (recording_active || (record_state==0 ? raw_start_ready_i : raw_drained_i));
    assign raw_start_valid_o=EXTERNAL_RAW_STORE && state==C_RAW_START && command_link_ready && enable && !external_mutation_hold && start_source_good;
    assign raw_clear_valid_o=EXTERNAL_RAW_STORE && state==C_RAW_CLEAR && !raw_clear_sent;
    assign raw_capture_valid_o=EXTERNAL_RAW_STORE && resetn && enable && source_ready_i && !source_fault_i && source_format_matches && pcm_valid_i &&
        capture_state==0 && !stop_pending && !external_capture_hold && recording_active;
    assign raw_capture_index_o=recorded_frames,raw_capture_pcm_o=pcm_pair_i;
    assign raw_close_valid_o=EXTERNAL_RAW_STORE && raw_closing && !raw_fault_i;
    assign raw_fetch_valid_o=EXTERNAL_RAW_STORE && state==C_RAW_FETCH_REQ && connected && enable;
    assign raw_fetch_offset_o=data_offset,raw_fetch_length_o={1'b0,data_length};
    assign raw_sample_addr_o=sample_address;
    // One native word per stereo PCM16 frame. The physical 1-GiB address
    // space also bounds object_bytes and every frame/byte counter below.
    initial if(CAPACITY_FRAMES<1 || CAPACITY_FRAMES>32'h10000000)
        $fatal(1,"recording capacity exceeds native DDR or PCM byte count");
    initial if(EXTERNAL_RAW_STORE && (!EXTERNAL_PCM || !EXTERNAL_SEAL_PROTOCOL || RAW_DRAIN_TIMEOUT_CYCLES<64))
        $fatal(1,"raw DDR requires external PCM, bounded capacity and explicit drain timeout");
    assign object_crc_o=object_crc,stop_reason_o={16'd0,stop_reason};
    assign block_crc_o=data_crc;
    assign source_good_o=source_ready_i && !source_fault_i && (!DUAL_RATE_RECORDING ||
        ((source_format_i==1 || source_format_i==2) && (!recording_active || source_format_matches)));
    assign mutation_hold_o=external_mutation_hold;
    reg [31:0] rom_word;
    generate if(EXTERNAL_RAW_STORE) begin: raw_storage
        // sample_word already has the original one-clock synchronous latency.
        always @* rom_word=raw_cache_live ? raw_sample_word_i:32'd0;
    end else if(EXTERNAL_PCM) begin: live_capture
        localparam ADDRESS_BITS=$clog2(CAPACITY_FRAMES);
        (* ram_style="block" *) reg [31:0] pcm_memory[0:CAPACITY_FRAMES-1];
        wire capture_write=resetn && enable && source_ready_i && !source_fault_i && source_format_matches && pcm_valid_i &&
            capture_state==0 && !stop_pending && !external_capture_hold && recording_active;
        always @(posedge clk) begin
            if(capture_write) pcm_memory[recorded_frames[ADDRESS_BITS-1:0]]<=pcm_pair_i;
            rom_word<=pcm_memory[sample_address[ADDRESS_BITS-1:0]];
        end
    end else begin: builtin_capture
        (* ram_style="block" *) reg [31:0] pcm_rom[0:1023];
        initial $readmemh(AUDIO_FILE,pcm_rom);
        always @(posedge clk) rom_word<=pcm_rom[sample_address[9:0]];
    end endgenerate
    ble_rice_encoder encoder(.clk(clk),.resetn(resetn),.enable(enable && connected && codec_active),
        .start(state==C_CODEC_START),.allow_second(data_second),.pcm_length(data_length),.sample_addr(codec_sample_addr),
        .sample_data(codec_sample_addr[1] ? rom_word[31:16] : rom_word[15:0]),
        .write_valid(codec_write_valid),.write_addr(codec_write_addr),.write_data(codec_write_data),
        .done(codec_done),.use_rice(codec_rice),.use_second(codec_second),.encoded_length(codec_length));
    // Four explicit 2 KiB banks: the installed Gowin mapper truncates a
    // single inferred 8 KiB byte RAM to seven address bits on this device.
    (* ram_style="block" *) reg [7:0] transfer_bank0[0:2047];
    (* ram_style="block" *) reg [7:0] transfer_bank1[0:2047];
    (* ram_style="block" *) reg [7:0] transfer_bank2[0:2047];
    (* ram_style="block" *) reg [7:0] transfer_bank3[0:2047];
    reg [7:0] bank_data0,bank_data1,bank_data2,bank_data3;
    reg [1:0] read_bank;
    wire buffer_we=resetn && enable && (state==C_DATA_BUILD || state==C_DATA_CRC || (codec_active && codec_write_valid));
    wire [12:0] buffer_write_addr=codec_active ? codec_write_addr+13'd44 : index;
    wire [12:0] buffer_read_addr=(data_codec!=0 && (state==C_DATA_PREP || state==C_DATA_BUILD)) ? index : transfer_addr;
    wire [7:0] frame_byte=rom_word>>(8*((state==C_BLOCK_PREP || state==C_BLOCK_CRC) ?
        (data_offset+index)&3 : data_absolute[1:0]));
    wire [7:0] data_byte=transfer_message_byte(index,data_codec!=0 ? transfer_data : frame_byte);
    wire [7:0] buffer_write_data=codec_active ? codec_write_data : state==C_DATA_CRC ? le32(~crc_work,index-transfer_length+4) : data_byte;
    always @(posedge clk) begin
        if(buffer_we) begin
            case(buffer_write_addr[12:11])
                0:transfer_bank0[buffer_write_addr[10:0]]<=buffer_write_data;
                1:transfer_bank1[buffer_write_addr[10:0]]<=buffer_write_data;
                2:transfer_bank2[buffer_write_addr[10:0]]<=buffer_write_data;
                3:transfer_bank3[buffer_write_addr[10:0]]<=buffer_write_data;
            endcase
        end
        bank_data0<=transfer_bank0[buffer_read_addr[10:0]];
        bank_data1<=transfer_bank1[buffer_read_addr[10:0]];
        bank_data2<=transfer_bank2[buffer_read_addr[10:0]];
        bank_data3<=transfer_bank3[buffer_read_addr[10:0]];
        read_bank<=buffer_read_addr[12:11];
    end
    always @* case(read_bank)
        0:transfer_data=bank_data0;
        1:transfer_data=bank_data1;
        2:transfer_data=bank_data2;
        3:transfer_data=bank_data3;
    endcase
    function [7:0] le32;
        input [31:0] v;
        input [1:0] n;
        begin le32=v>>(8*n); end
    endfunction
    function [31:0] crc_byte;
        input [31:0] previous;
        input [7:0] byte_value;
        reg [31:0] c;
        integer n;
        begin
            c=previous^byte_value;
            for(n=0;n<8;n=n+1) c=(c>>1)^(c[0]?32'hedb88320:0);
            crc_byte=c;
        end
    endfunction
    function [7:0] transfer_message_byte;
        input [12:0] at;
        input [7:0] audio_byte;
        begin
            transfer_message_byte=0;
            if(at==0) transfer_message_byte=8'hd0;
            else if(at==2) transfer_message_byte=(data_wire_length+28)&255;
            else if(at==3) transfer_message_byte=(data_wire_length+28)>>8;
            else if(at>=4 && at<8) transfer_message_byte=le32(data_request,at-4);
            else if(at>=8 && at<16) transfer_message_byte=data_nonce>>(8*(at-8));
            else if(at>=16 && at<20) transfer_message_byte=le32(data_transfer,at-16);
            else if(at>=20 && at<28) transfer_message_byte=boot_id>>(8*(at-20));
            else if(at>=28 && at<32) transfer_message_byte=le32(data_recording,at-28);
            else if(at>=32 && at<36) transfer_message_byte=le32(data_offset,at-32);
            else if(at==36) transfer_message_byte=data_length[7:0];
            else if(at==37) transfer_message_byte={3'd0,data_length[12:8]};
            else if(at==38) transfer_message_byte=data_codec;
            else if(at>=40 && at<44) transfer_message_byte=le32(data_crc,at-40);
            else if(at>=44) transfer_message_byte=audio_byte;
        end
    endfunction
    task reject;
        input [7:0] status;
        begin command_status<=status; command_length<=8; result_payload<=384'd1<<32;
            command_done<=1; state<=C_IDLE; end
    endtask
    task success;
        input [6:0] length;
        begin command_status<=0; command_length<=length; command_done<=1; state<=C_IDLE; end
    endtask
    // Physical event timestamps are facts, not task identities. Observe the
    // registered transition one edge later, retaining its original ms value.
    reg [7:0] previous_record_state;
    reg [31:0] previous_elapsed_ms;
    always @(posedge clk or negedge resetn)begin
        if(!resetn)begin previous_record_state<=0;previous_elapsed_ms<=0;first_frame_ms_o<=0;terminal_ms_o<=0;end
        else begin
            previous_record_state<=record_state;previous_elapsed_ms<=elapsed_ms;
            if(record_state==1 && previous_record_state==0)begin first_frame_ms_o<=0;terminal_ms_o<=0;end
            if(previous_record_state==1 && recorded_frames!=0 && record_state!=1)
                first_frame_ms_o<=previous_elapsed_ms;
            if((record_state==4 || record_state==5) && record_state!=previous_record_state)
                terminal_ms_o<=previous_elapsed_ms;
        end
    end
    initial if(SEAL_TIMEOUT_CYCLES<8)$fatal(1,"BLE seal timeout too short");
    // The local transaction survives the business endpoint's enable dropping.
    // EMPTY/READY need no live BLE/audio source; active-object loss is failure.
    // Snapshot identity belongs to this request and cannot follow a new slot.
    always @(posedge clk)begin
        seal_done_o<=0;seal_failed_o<=0;
        if(!resetn)begin
            seal_request_q<=0;seal_failed_seen<=0;seal_initial_error<=0;seal_requires_source<=0;seal_wait<=0;seal_pending_o<=0;
            seal_failure_code_o<=0;seal_record_state_o<=0;seal_recording_id_o<=0;seal_frames_o<=0;seal_crc_o<=0;
        end else begin
            seal_request_q<=EXTERNAL_SEAL_PROTOCOL && seal_request_i;
            if(seal_begin)begin
                seal_pending_o<=1;seal_failed_seen<=0;seal_wait<=0;seal_failure_code_o<=0;
                seal_initial_error<=record_state==5;
                seal_requires_source<=recording_active;
                seal_record_state_o<=record_state;seal_recording_id_o<=recording_id;
                seal_frames_o<=recorded_frames;seal_crc_o<=record_state==4 ? object_crc:32'd0;
            end else if(seal_pending_o)begin
                if(!seal_failed_seen && seal_current_error)begin
                    seal_failed_seen<=1;seal_failed_o<=1;
                    seal_failure_code_o<=seal_source_lost && !enable ? 4'd2:recording_id!=seal_recording_id_o ? 4'd3:seal_initial_error ? 4'd1:4'd4;
                end
                if(!recording_active && capture_state==0 && (!EXTERNAL_RAW_STORE || raw_drained_i))begin
                    seal_pending_o<=0;
                    if(recording_id==seal_recording_id_o)begin
                        seal_record_state_o<=record_state;seal_frames_o<=recorded_frames;
                        seal_crc_o<=record_state==4 ? object_crc:32'd0;
                    end
                    if(!seal_failed_seen && !seal_current_error && (record_state==0 || record_state==4))seal_done_o<=1;
                end else begin
                    if(seal_wait<(EXTERNAL_RAW_STORE ? RAW_DRAIN_TIMEOUT_CYCLES:SEAL_TIMEOUT_CYCLES))seal_wait<=seal_wait+1'b1;
                    if(seal_wait==(EXTERNAL_RAW_STORE ? RAW_DRAIN_TIMEOUT_CYCLES:SEAL_TIMEOUT_CYCLES)-1 && !seal_failed_seen)begin
                        seal_failed_seen<=1;seal_failed_o<=1;seal_failure_code_o<=4'd8;
                    end
                end
            end
        end
    end
    always @(posedge clk) begin
        command_done<=0;
        if(!resetn || (!enable && !EXTERNAL_SEAL_PROTOCOL)) begin
            state<=C_IDLE; result_payload<=0; command_status<=0; command_length<=0;
            raw_closing<=0;raw_cache_owned<=0;raw_clear_sent<=0;raw_wait<=0;
            record_state<=0; recording_id<=0; recorded_frames<=0;
            object_format_o<=1;
            limit_frames<=0; object_crc<=0; recording_crc<=32'hffffffff;
            stop_reason<=0; sample_phase<=0; capture_state<=0; capture_word<=0; stop_pending<=0;
            transfer_compact<=0;transfer_bulk<=0;transfer_direct<=0;
            command_time_ms_o<=0;block_crc_valid_o<=0;read_accepted_o<=0;
            transfer_valid<=0; transfer_length<=0; data_request<=0; data_transfer<=0;
            data_recording<=0; data_nonce<=0; data_offset<=0; data_length<=0;data_wire_length<=0;data_lossless<=0;data_second<=0;data_codec<=0;
            data_crc<=0; crc_work<=0; index<=0;
        end else begin
            if(sample_tick) sample_phase<=sample_phase+object_rate_o-CLK_HZ;
            else sample_phase<=sample_phase+object_rate_o;
            if(transfer_consume) transfer_valid<=0;
            if(command_start)begin block_crc_valid_o<=0;read_accepted_o<=0;end
            if(!command_link_ready || !enable) begin
                transfer_valid<=0;
                transfer_compact<=0;transfer_bulk<=0;transfer_direct<=0;
                if(state!=C_IDLE && (!EXTERNAL_RAW_STORE || state!=C_RAW_CLEAR))reject(8'h83);
                else if(command_start)reject(8'h83);
            end
            // Only this recorder advances the committed prefix and its CRC.
            // The command processor may inspect it; transfers require READY.
            case(capture_state)
                0: if((record_state==1 || record_state==2 || record_state==3) && (!EXTERNAL_RAW_STORE || !raw_closing)) begin
                    if(stop_pending && recorded_frames!=0) begin
                        if(EXTERNAL_RAW_STORE)begin raw_closing<=1;record_state<=3;object_crc<=~recording_crc;end
                        else begin
                            record_state<=4; object_crc<=~recording_crc;
                            stop_pending<=0;
                        end
                    end else if(!external_capture_hold && (EXTERNAL_PCM ? pcm_valid_i && source_ready_i && !source_fault_i && source_format_matches : sample_tick)) begin
                        if(EXTERNAL_PCM) begin
                            if(!EXTERNAL_RAW_STORE || raw_capture_ready_i)begin capture_word<=pcm_pair_i;capture_state<=2;end
                        end
                        else capture_state<=1;
                    end
                end
                1: begin capture_word<=rom_word; capture_state<=2; end
                2,3,4: begin recording_crc<=crc_byte(recording_crc,capture_word[7:0]);
                    capture_word<=capture_word>>8;capture_state<=capture_state+1'b1;end
                5: begin
                    recording_crc<=crc_byte(recording_crc,capture_word[7:0]);
                    recorded_frames<=recorded_frames+1'b1; capture_state<=0;
                    if(record_state==1) begin
                        record_state<=2;
                    end
                    if(stop_pending || recorded_frames+1'b1==limit_frames) begin
                        object_crc<=~crc_byte(recording_crc,capture_word[7:0]);
                        if(EXTERNAL_RAW_STORE)begin raw_closing<=1;record_state<=3;if(!stop_pending)stop_reason<=2;end
                        else begin
                            record_state<=4;
                            if(!stop_pending)stop_reason<=2;
                            stop_pending<=0;
                        end
                    end
                end
            endcase
            if(recording_active && ((EXTERNAL_SEAL_PROTOCOL && !enable) || (EXTERNAL_PCM &&
                (!source_ready_i || source_fault_i || !source_format_matches || (!external_capture_hold && pcm_valid_i && capture_state!=0))))) begin
                record_state<=5;stop_reason<=!enable || !source_ready_i ? 6 : 3;capture_state<=0;
                if(EXTERNAL_RAW_STORE)raw_closing<=1;
                stop_pending<=0;
            end
            // Finish the accepted stereo word and all four CRC bytes first.
            // An unstarted zero-frame object keeps its ID and empty CRC, but
            // its START task fails because no first frame ever became real.
            if(seal_commit && enable && !(EXTERNAL_PCM && (!source_ready_i || source_fault_i || !source_format_matches)) &&
               (!EXTERNAL_RAW_STORE || !raw_closing))begin
                object_crc<=~recording_crc;stop_reason<=1;
                if(EXTERNAL_RAW_STORE)begin raw_closing<=1;record_state<=3;end
                else begin record_state<=4;stop_pending<=0;end
            end
            if(command_link_ready && enable) case(state)
                C_IDLE: if(command_link_ready && command_start) begin
                    command_status<=0; result_payload<=0;command_time_ms_o<=elapsed_ms;
                    block_crc_valid_o<=0;
                    case(opcode)

                        8'h20: begin
                            if(payload_length!=8 || !requested_format_valid) reject(8'h81);
                            else if(external_mutation_hold) reject(8'h82);
                            else if(EXTERNAL_PCM && !start_source_good) reject(8'h83);
                            else if(record_state!=0) reject(8'h83);
                            else if(payload[63:32]>CAPACITY_FRAMES) reject(8'h89);
                            else if(command_object_id_i==0) reject(8'h82);
                            else begin
                                if(EXTERNAL_RAW_STORE)begin
                                    if(!raw_start_ready_i || raw_clear_sent || raw_closing)reject(8'h82);
                                    else state<=C_RAW_START;
                                end else begin
                                recording_id<=command_object_id_i;
                                object_format_o<=DUAL_RATE_RECORDING ? payload[7:0]:8'd1;
                                recorded_frames<=0; recording_crc<=32'hffffffff; object_crc<=0;
                                limit_frames<=payload[63:32]==0 ? CAPACITY_FRAMES : payload[63:32];
                                record_state<=1; stop_reason<=0; stop_pending<=0; capture_state<=0;
                                command_status<=0;command_length<=0;command_done<=1;
                                end
                            end
                        end
                        8'h21: begin
                            if(payload_length!=12) reject(8'h81);
                            else if(payload[63:0]!=boot_id || recording_id==0 || payload[95:64]!=recording_id) reject(8'h88);
                            else if(external_mutation_hold) reject(8'h82);
                            else if(record_state!=2) reject(8'h83);
                            else begin
                                record_state<=3; stop_pending<=1; stop_reason<=1;
                                command_status<=0;command_length<=0;command_done<=1;
                            end
                        end

                        8'h23: begin
                            if(payload_length!=12) reject(8'h81);
                            else if(payload[63:0]!=boot_id || recording_id==0 || payload[95:64]!=recording_id) reject(8'h88);
                            else if(external_mutation_hold) reject(8'h82);
                            else if(record_state!=4 && record_state!=5) reject(8'h83);
                            else begin
                                if(EXTERNAL_RAW_STORE)begin
                                    if(raw_channel_fault_i || raw_clear_sent || raw_closing)reject(8'h82);
                                    else begin raw_cache_owned<=0;state<=C_RAW_CLEAR;end
                                end else begin
                                result_payload<={352'd0,recording_id}; success(4);
                                record_state<=0; recording_id<=0; recorded_frames<=0;
                                object_format_o<=1;
                                object_crc<=0; stop_reason<=0;
                                end
                            end
                        end
                        // Already validated by the sole C transfer owner. The
                        // physical checks bound memory and borrowed identity.
                        8'h31: begin
                            if(payload_length!=12 || payload[95:80]!=0 || command_flags_i[4] && !command_flags_i[3])reject(8'h81);
                            else if(record_state!=4 || recording_id==0 || command_object_id_i!=recording_id)reject(8'h88);
                            else if(command_transfer_id_i==0 || payload[31:0]!=command_transfer_id_i)reject(8'h8d);
                            else if(read_length==0 || read_length>8112 || read_length[1:0]!=0 || read_offset[1:0]!=0 ||
                                    read_offset>=object_bytes || read_length>object_bytes-read_offset)reject(8'h89);
                            else begin
                                read_accepted_o<=1;
                                data_request<=request_id;data_nonce<=nonce;data_transfer<=command_transfer_id_i;
                                data_recording<=command_object_id_i;data_offset<=read_offset;data_length<=read_length;
                                data_lossless<=command_flags_i[3];data_second<=command_flags_i[4];data_codec<=0;
                                transfer_compact<=command_flags_i[0];transfer_bulk<=command_flags_i[1];transfer_direct<=command_flags_i[2];
                                crc_work<=32'hffffffff;index<=0;state<=EXTERNAL_RAW_STORE ? C_RAW_FETCH_REQ:C_BLOCK_PREP;
                            end
                        end
                        default: reject(8'h80);
                    endcase
                end
                C_RAW_START: begin
                    if(external_mutation_hold || raw_fault_i)reject(8'h82);
                    else if(!start_source_good)reject(8'h83);
                    else if(raw_start_valid_o && raw_start_ready_i)begin
                                recording_id<=command_object_id_i;
                                object_format_o<=DUAL_RATE_RECORDING ? payload[7:0]:8'd1;
                                recorded_frames<=0; recording_crc<=32'hffffffff; object_crc<=0;
                                limit_frames<=payload[63:32]==0 ? CAPACITY_FRAMES : payload[63:32];
                                record_state<=1; stop_reason<=0; stop_pending<=0; capture_state<=0;
                                command_status<=0;command_length<=0;command_done<=1;
                        state<=C_IDLE;
                    end
                end
                C_RAW_CLEAR: begin end // Actual clear survives link/observer loss below.
                C_RAW_FETCH_REQ: if(raw_fetch_valid_o && raw_fetch_ready_i)begin
                    raw_cache_owned<=0;state<=C_RAW_FETCH_WAIT;
                end
                C_RAW_FETCH_WAIT: begin
                    if(raw_fetch_fault_i || raw_fault_i)reject(8'h83);
                    else if(raw_fetch_done_i && raw_cache_valid_i)begin raw_cache_owned<=1;state<=C_BLOCK_PREP;end
                end

                C_BLOCK_PREP: state<=C_BLOCK_CRC;
                C_BLOCK_CRC: begin
                    crc_work<=crc_byte(crc_work,frame_byte);
                    if(index+1'b1==data_length) begin
                        data_crc<=~crc_byte(crc_work,frame_byte);index<=0;state<=data_lossless ? C_CODEC_START : C_DATA_PREP;
                        data_wire_length<=data_length;transfer_length<=data_length+48;crc_work<=32'hffffffff;
                        block_crc_valid_o<=1;
                    end else begin index<=index+1'b1;state<=C_BLOCK_PREP;end
                end
                C_CODEC_START: state<=C_CODEC_WAIT;
                C_CODEC_WAIT: if(codec_done) begin
                    data_codec<=codec_rice ? (codec_second ? 8'd11 : 8'd10) : 8'd0;
                    data_wire_length<=codec_length;transfer_length<=codec_length+13'd48;
                    index<=0;crc_work<=32'hffffffff;state<=C_DATA_PREP;
                end
                C_DATA_PREP: state<=C_DATA_BUILD;
                C_DATA_BUILD: begin
                    crc_work<=crc_byte(crc_work,data_byte);
                    if(index+5==transfer_length) begin index<=index+1'b1;state<=C_DATA_CRC;end
                    else begin index<=index+1'b1;state<=C_DATA_PREP;end
                end
                C_DATA_CRC: begin
                    if(index+1'b1==transfer_length) begin
                        transfer_valid<=1;
                        result_payload<={288'd0,16'd0,3'd0,data_length,data_offset,data_transfer};
                        success(12);
                    end else index<=index+1'b1;
                end
                default: state<=C_IDLE;
            endcase
            else begin if(!EXTERNAL_RAW_STORE || state!=C_RAW_CLEAR)state<=C_IDLE;transfer_valid<=0;end
            // Physical storage lifetime and borrowed capture identity only.
            // Operation tasks, transfer policy and IDs are owned by C.
            if(EXTERNAL_RAW_STORE)begin
                if(raw_waiting)begin if(raw_wait<RAW_DRAIN_TIMEOUT_CYCLES)raw_wait<=raw_wait+1'b1;end
                else raw_wait<=0;
                if(raw_clear_valid_o && raw_clear_ready_i)raw_clear_sent<=1;
                if(raw_clear_sent && raw_clear_done_i)begin
                    raw_clear_sent<=0;
                    if(state==C_RAW_CLEAR)begin
                                result_payload<={352'd0,recording_id}; success(4);
                                record_state<=0; recording_id<=0; recorded_frames<=0;
                                object_format_o<=1;
                                object_crc<=0; stop_reason<=0;
                    end
                end
                if(raw_closing && raw_drained_i)begin
                    raw_closing<=0;
                    if(record_state!=5 && enable && source_ready_i && !source_fault_i && source_format_matches && !raw_fault_i && !raw_expired &&
                       raw_accepted_frames_i==recorded_frames && raw_committed_frames_i==recorded_frames)begin
                        record_state<=4;
                        stop_pending<=0;
                    end else if(record_state!=0)begin record_state<=5;stop_reason<=!enable || !source_ready_i ? 6:3;end
                end
                if(!connected || !enable || transfer_consume || state==C_RAW_FETCH_REQ || state==C_RAW_CLEAR ||
                   raw_fault_i || raw_fetch_fault_i)raw_cache_owned<=0;
                if((raw_fault_i && record_state!=0) || (raw_capture_valid_o && !raw_capture_ready_i) ||
                   (raw_expired && raw_waiting) ||
                   (seal_pending_o && seal_wait>=RAW_DRAIN_TIMEOUT_CYCLES-1 && !seal_failed_seen) ||
                   (raw_closing && raw_drained_i &&
                    (raw_accepted_frames_i!=recorded_frames || raw_committed_frames_i!=recorded_frames)))begin
                    if(record_state!=0)record_state<=5;
                    capture_state<=0;stop_reason<=3;raw_cache_owned<=0;transfer_valid<=0;
                    if(recording_active)raw_closing<=1;
                    if(state==C_RAW_START || state==C_RAW_CLEAR || state==C_RAW_FETCH_REQ ||
                       state==C_RAW_FETCH_WAIT || raw_processing)reject(8'h83);
                end else if(raw_processing && !raw_cache_live)begin
                    raw_cache_owned<=0;transfer_valid<=0;reject(8'h83);
                end
            end
        end
    end
endmodule

// Stereo PCM16 modular delta, bounded Rice k9. Count first, so RAW fallback
// cannot overflow the shared transfer RAM. Predictors reset at every block.
module ble_rice_encoder(
    input wire clk, resetn, enable, start, allow_second,
    input wire [12:0] pcm_length,
    output reg [12:0] sample_addr,
    input wire [15:0] sample_data,
    output reg write_valid,
    output reg [12:0] write_addr,
    output reg [7:0] write_data,
    output reg done, use_rice, use_second,
    output reg [12:0] encoded_length
);
    localparam IDLE=0,REQ=1,WAIT_ROM=2,VALUE=3,DECIDE=4,BITS=5,FINISH=6;
    reg [2:0] phase;
    reg encoding;
    reg [15:0] left_previous,right_previous,left_delta,right_delta;
    wire [15:0] delta=sample_data-(sample_addr[1] ? right_previous : left_previous);
    wire [15:0] zigzag={delta[14:0],1'b0}^{16{delta[15]}};
    wire [15:0] delta_second=delta-(sample_addr[1] ? right_delta : left_delta);
    wire [15:0] zigzag_second={delta_second[14:0],1'b0}^{16{delta_second[15]}};
    wire [15:0] encoded_zigzag=use_second ? zigzag_second : zigzag;
    wire [10:0] quotient=use_second ? zigzag_second[15:5] : {4'd0,zigzag[15:9]};
    wire escaped=quotient>=15;
    wire [6:0] quotient_first=zigzag[15:9];
    wire [10:0] quotient_second=zigzag_second[15:5];
    reg [16:0] bit_cost,second_bit_cost;
    wire [16:0] byte_cost=(bit_cost+17'd7)>>3;
    wire [16:0] second_byte_cost=(second_bit_cost+17'd7)>>3;
    wire choose_second=allow_second && second_byte_cost<byte_cost;
    wire [16:0] chosen_byte_cost=choose_second ? second_byte_cost : byte_cost;
    reg [3:0] unary_left;
    reg delimiter;
    reg [15:0] remainder;
    reg [4:0] remainder_left;
    reg [7:0] packed_byte;
    reg [2:0] packed_bits;
    reg [12:0] output_count;
    wire next_bit=unary_left!=0 ? 1'b1 : delimiter ? 1'b0 : remainder[15];
    wire last_bit=unary_left==0 && !delimiter && remainder_left==1;
    wire last_sample=sample_addr+13'd2==pcm_length;
    always @(posedge clk) begin
        write_valid<=0;done<=0;
        if(!resetn || !enable) begin
            phase<=IDLE;sample_addr<=0;encoding<=0;use_rice<=0;use_second<=0;encoded_length<=0;
            left_previous<=0;right_previous<=0;left_delta<=0;right_delta<=0;bit_cost<=0;second_bit_cost<=0;output_count<=0;
            unary_left<=0;delimiter<=0;remainder<=0;remainder_left<=0;
            packed_byte<=0;packed_bits<=0;write_addr<=0;write_data<=0;
        end else case(phase)
            IDLE: if(start) begin
                sample_addr<=0;encoding<=0;use_rice<=0;bit_cost<=0;second_bit_cost<=0;use_second<=0;
                left_previous<=0;right_previous<=0;left_delta<=0;right_delta<=0;phase<=REQ;
            end
            REQ: phase<=WAIT_ROM;
            WAIT_ROM: phase<=VALUE;
            VALUE: begin
                if(sample_addr[1])begin right_previous<=sample_data;right_delta<=delta;end
                else begin left_previous<=sample_data;left_delta<=delta;end
                if(!encoding) begin
                    bit_cost<=bit_cost+(quotient_first>=15 ? 17'd31 : {13'd0,quotient_first[3:0]}+17'd10);
                    second_bit_cost<=second_bit_cost+(quotient_second>=15 ? 17'd31 : {13'd0,quotient_second[3:0]}+17'd6);
                    if(last_sample)phase<=DECIDE;
                    else begin sample_addr<=sample_addr+13'd2;phase<=REQ;end
                end else begin
                    unary_left<=escaped ? 4'd15 : quotient[3:0];delimiter<=!escaped;
                    remainder<=escaped ? encoded_zigzag : use_second ? {zigzag_second[4:0],11'd0} : {zigzag[8:0],7'd0};
                    remainder_left<=escaped ? 5'd16 : use_second ? 5'd5 : 5'd9;phase<=BITS;
                end
            end
            DECIDE: begin
                if(chosen_byte_cost>=pcm_length) begin encoded_length<=pcm_length;use_rice<=0;phase<=FINISH;end
                else begin
                    use_rice<=1;use_second<=choose_second;encoded_length<=chosen_byte_cost[12:0];encoding<=1;
                    sample_addr<=0;left_previous<=0;right_previous<=0;left_delta<=0;right_delta<=0;
                    packed_byte<=0;packed_bits<=0;output_count<=0;phase<=REQ;
                end
            end
            BITS: begin
                packed_byte<={packed_byte[6:0],next_bit};packed_bits<=packed_bits+1'b1;
                if(unary_left!=0)unary_left<=unary_left-1'b1;
                else if(delimiter)delimiter<=0;
                else begin remainder<=remainder<<1;remainder_left<=remainder_left-1'b1;end
                if(packed_bits==7 || (last_bit && last_sample)) begin
                    write_valid<=1;write_addr<=output_count;output_count<=output_count+1'b1;
                    write_data<={packed_byte[6:0],next_bit}<<(7-packed_bits);
                    packed_byte<=0;packed_bits<=0;
                end
                if(last_bit) begin
                    if(last_sample)phase<=FINISH;
                    else begin sample_addr<=sample_addr+13'd2;phase<=REQ;end
                end
            end
            FINISH: begin done<=1;phase<=IDLE;end
            default: phase<=IDLE;
        endcase
    end
endmodule
