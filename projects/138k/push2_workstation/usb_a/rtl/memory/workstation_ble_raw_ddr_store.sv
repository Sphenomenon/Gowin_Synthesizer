`timescale 1ns/1ps
`default_nettype none
// Unselected raw storage only. BLE owns objects, tasks, CRC and protocol.
module workstation_ble_raw_ddr_store #(
    parameter [28:0] BASE_APP=29'h0000000,
    parameter integer CAPACITY_FRAMES=16384,
    parameter integer FIFO_ADDRESS_BITS=8,
    parameter integer COMMAND_TIMEOUT_CYCLES=10000,
    parameter integer READ_TIMEOUT_CYCLES=10000,
    parameter bit CAPTURE_COMMAND=0
) (
    input wire clk_i,memory_clk_i,rst_ni,
    input wire start_valid_i,
    output wire start_ready_o,
    output reg start_done_o,
    input wire clear_valid_i,
    output wire clear_ready_o,
    output reg clear_done_o,
    input wire capture_valid_i,
    input wire [31:0] capture_index_i,capture_pcm_i,
    output wire capture_ready_o,
    input wire close_valid_i,
    output wire close_ready_o,
    output wire drained_o,fault_o,
    output reg object_fault_o,channel_fault_o,
    output reg [3:0] failure_code_o,
    output reg [31:0] accepted_frames_o,committed_frames_o,
    input wire fetch_valid_i,
    output wire fetch_ready_o,
    input wire [31:0] fetch_offset_i,
    input wire [13:0] fetch_length_i,
    output reg fetch_done_o,fetch_fault_o,
    output reg cache_valid_o,
    input wire [31:0] sample_addr_i,
    output wire [31:0] sample_word_o,
    // memory_clk_i: local slot readiness is not native acceptance.
    output wire slot_valid_o,
    input wire slot_ready_i,native_accept_i,
    output reg ddr_write_o,
    output reg [28:0] ddr_address_o,
    output reg [255:0] ddr_data_o,
    output reg [31:0] ddr_mask_o,
    input wire read_response_i,
    input wire [255:0] read_data_i,
    input wire transport_fault_i,
    output wire native_protocol_fault_o
);
    localparam integer PTR_BITS=FIFO_ADDRESS_BITS+1;
    localparam [1:0] CMD_START=0,CMD_CLEAR=1,CMD_FETCH=2;
    localparam [3:0] F_OVERFLOW=1,F_INDEX=2,F_CAPACITY=3,F_DESCRIPTOR=4,
        F_COMMAND_TIMEOUT=5,F_READ_TIMEOUT=6,F_TRANSPORT=7,F_PROTOCOL=8,
        F_GENERATION=9,F_CANCELLED=10;
    initial begin
        if(CAPACITY_FRAMES<1 || CAPACITY_FRAMES>32'h10000000 || FIFO_ADDRESS_BITS<2 ||
           FIFO_ADDRESS_BITS>8 || COMMAND_TIMEOUT_CYCLES<4 || READ_TIMEOUT_CYCLES<4 ||
           BASE_APP[2:0]!=0 || {3'd0,BASE_APP}+32'(CAPACITY_FRAMES)>32'h10000000)
            $fatal(1,"invalid raw BLE DDR store geometry/budget");
    end
    (* ASYNC_REG="TRUE" *) reg [1:0] control_release,memory_release;
    always @(posedge clk_i or negedge rst_ni)
        if(!rst_ni)control_release<=0;else control_release<={control_release[0],1'b1};
    always @(posedge memory_clk_i or negedge rst_ni)
        if(!rst_ni)memory_release<=0;else memory_release<={memory_release[0],1'b1};
    wire control_reset_n=control_release[1],memory_reset_n=memory_release[1];
    (* ASYNC_REG="TRUE" *) reg memory_up_meta,memory_up_sync;

    // One immutable command descriptor and immutable completion. Payloads are
    // held from publication until the next request can legitimately replace it.
    reg command_req,command_ack;
    (* ASYNC_REG="TRUE" *) reg command_ack_meta,command_ack_sync;
    (* ASYNC_REG="TRUE" *) reg command_req_meta,command_req_sync;
    reg command_ack_seen;
    reg [1:0] command_kind;
    reg [31:0] command_generation,command_offset;
    reg [13:0] command_length;
    reg [PTR_BITS-1:0] command_event_target;
    reg [31:0] completion_generation,completion_committed;
    reg [1:0] completion_kind;
    reg [3:0] completion_code;
    wire command_busy=command_req!=command_ack_sync;
    wire command_return=command_ack_sync!=command_ack_seen;
    reg cancel_toggle,cancel_seen;
    (* ASYNC_REG="TRUE" *) reg cancel_meta,cancel_sync;
    wire cancel_now=cancel_sync!=cancel_seen;

    // Independent memory-to-control status snapshot: no multi-bit bitwise CDC.
    reg status_req,status_ack;
    reg [69:0] status_payload;
    (* ASYNC_REG="TRUE" *) reg status_req_meta,status_req_sync;
    (* ASYNC_REG="TRUE" *) reg status_ack_meta,status_ack_sync;
    wire [31:0] status_generation=status_payload[69:38];
    wire [31:0] status_committed=status_payload[37:6];
    wire status_drained=status_payload[5],status_channel_fault=status_payload[4];
    wire [3:0] status_failure=status_payload[3:0];

    // At most one read response is published. Ack follows all eight cache
    // writes, or a deliberate discard after a fence. The source stays stable.
    reg return_req,return_ack;
    reg [255:0] return_data;
    reg [31:0] return_generation;
    reg [10:0] return_word;
    (* ASYNC_REG="TRUE" *) reg return_req_meta,return_req_sync;
    (* ASYNC_REG="TRUE" *) reg return_ack_meta,return_ack_sync;
    reg return_pending,unpack_active;
    reg [255:0] unpack_data;
    reg [31:0] unpack_generation;
    reg [10:0] unpack_word;
    reg [2:0] unpack_index;

    reg [31:0] generation;
    reg raw_empty,capture_active,closed,memory_drained;
    reg clear_pending,clear_sent,auto_close_pending,fetch_active;
    reg start_seen,clear_seen,close_seen,fetch_seen;
    reg [PTR_BITS-1:0] fifo_produced,clear_event_target;
    wire fifo_write_ready,fifo_read_valid,fifo_read_ready;
    wire [64:0] fifo_read_data;
    wire start_fire=start_valid_i && start_ready_o;
    wire clear_fire=clear_valid_i && clear_ready_o;
    wire close_fire=close_valid_i && close_ready_o;
    wire fetch_fire=fetch_valid_i && fetch_ready_o;
    wire capture_attempt=capture_active && capture_valid_i && !clear_valid_i && !close_valid_i &&
        !clear_pending && !object_fault_o && !channel_fault_o;
    wire capture_bad=capture_attempt && (!fifo_write_ready || capture_index_i!=accepted_frames_o ||
                                        accepted_frames_o>=CAPACITY_FRAMES);
    wire capture_fire=capture_attempt && !capture_bad;
    wire auto_close_fire=auto_close_pending && fifo_write_ready && !clear_pending && !clear_fire;
    wire fifo_write_valid=capture_fire || close_fire || auto_close_fire;
    wire fifo_marker=close_fire || auto_close_fire;
    wire [64:0] fifo_write_data={fifo_marker,
        fifo_marker ? accepted_frames_o : capture_index_i,fifo_marker ? 32'd0 : capture_pcm_i};
    music_async_fifo #(.WIDTH(65),.ADDRESS_BITS(FIFO_ADDRESS_BITS),.RAM_STYLE("block_ram")) capture_fifo(
        .write_clk_i(clk_i),.write_rst_ni(control_reset_n),.write_valid_i(fifo_write_valid),
        .write_ready_o(fifo_write_ready),.write_data_i(fifo_write_data),
        .read_clk_i(memory_clk_i),.read_rst_ni(memory_reset_n),.read_valid_o(fifo_read_valid),
        .read_ready_i(fifo_read_ready),.read_data_o(fifo_read_data));

    assign fault_o=object_fault_o || channel_fault_o;
    assign start_ready_o=control_reset_n && memory_up_sync && raw_empty && !command_busy &&
        !clear_pending && !start_seen && !clear_valid_i && !fault_o && generation!=32'hffffffff;
    assign clear_ready_o=control_reset_n && memory_up_sync && !clear_pending && !clear_seen &&
        !channel_fault_o && generation!=32'hffffffff;
    assign capture_ready_o=control_reset_n && capture_active && !fault_o && !clear_pending &&
        !clear_valid_i && !close_valid_i && fifo_write_ready && accepted_frames_o<CAPACITY_FRAMES;
    assign close_ready_o=control_reset_n && capture_active && !close_seen && !clear_valid_i &&
        !clear_pending && !fault_o && fifo_write_ready;
    assign drained_o=control_reset_n && closed && memory_drained && !clear_pending &&
        !command_busy && !fetch_active && !auto_close_pending && !channel_fault_o;
    assign fetch_ready_o=control_reset_n && !fetch_seen && !clear_valid_i && !fault_o &&
        !raw_empty && drained_o;
    wire [32:0] fetch_end={1'b0,fetch_offset_i}+{19'd0,fetch_length_i};
    wire fetch_descriptor_bad=fetch_length_i==0 || fetch_length_i>8112 || fetch_end[32] ||
        {2'd0,fetch_end}>{1'b0,committed_frames_o,2'b0};

    reg [31:0] cache_first_frame,cache_end_frame,cache_aligned_frame;
    wire [31:0] cache_relative=sample_addr_i-cache_aligned_frame;
    wire cache_read_allowed=cache_valid_o && !clear_valid_i && !fault_o &&
        sample_addr_i>=cache_first_frame && sample_addr_i<cache_end_frame && cache_relative<2048;
    wire cache_write=unpack_active && unpack_generation==generation && fetch_active &&
        !clear_pending && !clear_fire && !fault_o;
    wire [10:0] cache_write_word=unpack_word+{8'd0,unpack_index};
    wire [31:0] cache_write_data=unpack_data[unpack_index*32+:32];
    wire [15:0] cache_low[0:1],cache_high[0:1];
    reg cache_bank_q,cache_read_valid_q;
    genvar bank;
    generate for(bank=0;bank<2;bank=bank+1)begin:g_cache
        workstation_sdp #(.DATA_WIDTH(16),.ADDR_WIDTH(10)) low_half(
            .write_clk_i(clk_i),.write_enable_i(cache_write && cache_write_word[10]==bank),
            .write_addr_i(cache_write_word[9:0]),.write_data_i(cache_write_data[15:0]),
            .read_clk_i(clk_i),.read_enable_i(1'b1),.read_addr_i(cache_relative[9:0]),.read_data_o(cache_low[bank]));
        workstation_sdp #(.DATA_WIDTH(16),.ADDR_WIDTH(10)) high_half(
            .write_clk_i(clk_i),.write_enable_i(cache_write && cache_write_word[10]==bank),
            .write_addr_i(cache_write_word[9:0]),.write_data_i(cache_write_data[31:16]),
            .read_clk_i(clk_i),.read_enable_i(1'b1),.read_addr_i(cache_relative[9:0]),.read_data_o(cache_high[bank]));
    end endgenerate
    assign sample_word_o=cache_read_valid_q && cache_valid_o && !clear_valid_i && !fault_o ?
        {cache_high[cache_bank_q],cache_low[cache_bank_q]} : 32'd0;

    always @(posedge clk_i or negedge control_reset_n)begin
        if(!control_reset_n)begin
            memory_up_meta<=0;memory_up_sync<=0;command_ack_meta<=0;command_ack_sync<=0;command_ack_seen<=0;
            status_req_meta<=0;status_req_sync<=0;status_ack<=0;
            return_req_meta<=0;return_req_sync<=0;return_ack<=0;
            command_req<=0;command_kind<=0;command_generation<=0;command_offset<=0;command_length<=0;command_event_target<=0;
            cancel_toggle<=0;generation<=0;raw_empty<=1;capture_active<=0;closed<=1;memory_drained<=0;
            clear_pending<=0;clear_sent<=0;auto_close_pending<=0;fetch_active<=0;
            start_seen<=0;clear_seen<=0;close_seen<=0;fetch_seen<=0;fifo_produced<=0;clear_event_target<=0;
            object_fault_o<=0;channel_fault_o<=0;failure_code_o<=0;accepted_frames_o<=0;committed_frames_o<=0;
            start_done_o<=0;clear_done_o<=0;fetch_done_o<=0;fetch_fault_o<=0;cache_valid_o<=0;
            unpack_active<=0;unpack_data<=0;unpack_generation<=0;unpack_word<=0;unpack_index<=0;
            cache_first_frame<=0;cache_end_frame<=0;cache_aligned_frame<=0;cache_bank_q<=0;cache_read_valid_q<=0;
        end else begin
            memory_up_meta<=memory_reset_n;memory_up_sync<=memory_up_meta;
            command_ack_meta<=command_ack;command_ack_sync<=command_ack_meta;
            status_req_meta<=status_req;status_req_sync<=status_req_meta;
            return_req_meta<=return_req;return_req_sync<=return_req_meta;
            start_done_o<=0;clear_done_o<=0;fetch_done_o<=0;fetch_fault_o<=0;
            cache_bank_q<=cache_relative[10];cache_read_valid_q<=cache_read_allowed;
            if(!start_valid_i)start_seen<=0;
            if(!clear_valid_i)clear_seen<=0;
            if(!close_valid_i)close_seen<=0;
            if(!fetch_valid_i)fetch_seen<=0;
            if(fifo_write_valid)fifo_produced<=fifo_produced+1'b1;
            if(capture_fire)accepted_frames_o<=accepted_frames_o+1'b1;
            if(close_fire)begin close_seen<=1;capture_active<=0;closed<=1;memory_drained<=0;end
            if(auto_close_fire)auto_close_pending<=0;
            if(capture_bad)begin
                object_fault_o<=1;capture_active<=0;closed<=1;auto_close_pending<=1;memory_drained<=0;cache_valid_o<=0;
                failure_code_o<=!fifo_write_ready ? F_OVERFLOW : accepted_frames_o>=CAPACITY_FRAMES ? F_CAPACITY : F_INDEX;
            end
            if(status_req_sync!=status_ack)begin
                status_ack<=status_req_sync;
                if(status_generation==generation && !clear_pending)begin
                    committed_frames_o<=status_committed;memory_drained<=status_drained;
                end
                if(status_channel_fault)begin
                    channel_fault_o<=1;failure_code_o<=status_failure;capture_active<=0;cache_valid_o<=0;
                end
            end
            if(return_req_sync!=return_ack && !unpack_active)begin
                if(return_generation==generation && fetch_active && !clear_pending && !fault_o)begin
                    unpack_active<=1;unpack_data<=return_data;unpack_generation<=return_generation;
                    unpack_word<=return_word;unpack_index<=0;
                end else return_ack<=return_req_sync;
            end
            if(unpack_active)begin
                if(unpack_index==7)begin unpack_active<=0;return_ack<=return_req_sync;end
                else unpack_index<=unpack_index+1'b1;
            end
            if(command_return)begin
                command_ack_seen<=command_ack_sync;
                if(completion_kind==CMD_FETCH)begin
                    fetch_active<=0;
                    if(completion_code==0 && completion_generation==generation && !clear_pending && !clear_fire &&
                       !fault_o && !(status_req_sync!=status_ack && status_channel_fault))begin
                        cache_valid_o<=1;fetch_done_o<=1;
                    end else begin cache_valid_o<=0;fetch_fault_o<=1;end
                end
                if(completion_generation==generation)begin
                    committed_frames_o<=completion_committed;
                    if(completion_kind==CMD_START && completion_code==0)start_done_o<=1;
                    if(completion_kind==CMD_CLEAR && completion_code==0)begin
                        clear_done_o<=1;clear_pending<=0;clear_sent<=0;raw_empty<=1;closed<=1;memory_drained<=1;
                        object_fault_o<=0;failure_code_o<=0;accepted_frames_o<=0;committed_frames_o<=0;
                    end
                    if(completion_code!=0 && completion_code!=F_CANCELLED)begin
                        channel_fault_o<=1;failure_code_o<=completion_code;cache_valid_o<=0;capture_active<=0;
                    end
                end
            end
            if(clear_pending && !clear_sent && !command_busy && !command_return)begin
                command_kind<=CMD_CLEAR;command_generation<=generation;command_event_target<=clear_event_target;
                command_offset<=0;command_length<=0;command_req<=~command_req;clear_sent<=1;
            end
            if(start_fire)begin
                start_seen<=1;generation<=generation+1'b1;command_kind<=CMD_START;command_generation<=generation+1'b1;
                command_event_target<=fifo_produced;command_offset<=0;command_length<=0;command_req<=~command_req;
                raw_empty<=0;capture_active<=1;closed<=0;memory_drained<=0;cache_valid_o<=0;
                accepted_frames_o<=0;committed_frames_o<=0;
            end
            if(fetch_fire)begin
                fetch_seen<=1;cache_valid_o<=0;
                if(fetch_descriptor_bad)begin fetch_fault_o<=1;object_fault_o<=1;failure_code_o<=F_DESCRIPTOR;end
                else begin
                    command_kind<=CMD_FETCH;command_generation<=generation;command_offset<=fetch_offset_i;
                    command_length<=fetch_length_i;command_req<=~command_req;fetch_active<=1;
                    cache_aligned_frame<=fetch_offset_i>>2 & 32'hfffffff8;
                    cache_first_frame<=fetch_offset_i>>2;cache_end_frame<=32'((fetch_end+33'd3)>>2);
                end
            end
            if(clear_fire)begin
                clear_seen<=1;generation<=generation+1'b1;clear_pending<=1;clear_sent<=0;clear_event_target<=fifo_produced;
                cancel_toggle<=~cancel_toggle;capture_active<=0;closed<=1;raw_empty<=0;memory_drained<=0;
                cache_valid_o<=0;auto_close_pending<=0;
            end
            if(((start_valid_i && !start_seen) || (clear_valid_i && !clear_seen)) &&
               generation==32'hffffffff)begin
                channel_fault_o<=1;failure_code_o<=F_GENERATION;cache_valid_o<=0;capture_active<=0;
            end
        end
    end

    reg [31:0] memory_generation,memory_next_index,memory_committed;
    reg [PTR_BITS-1:0] fifo_consumed,memory_clear_target;
    reg memory_active,memory_closed,memory_empty,memory_clear_pending,memory_command_active;
    reg memory_channel_fault;
    reg [3:0] memory_failure;
    reg [255:0] pack_data;
    reg pack_word_valid;
    reg [2:0] pack_word_index;
    reg [31:0] pack_word_data;
    wire [255:0] packed_payload;
    reg [3:0] pack_frames,published_frames;
    reg [28:0] write_address;
    reg published_valid,read_outstanding;
    reg [31:0] published_generation,read_generation;
    reg [10:0] published_word,read_word;
    reg [31:0] command_wait,read_wait;
    reg memory_fetch_active,memory_fetch_cancel;
    reg [8:0] fetch_beats_total,fetch_beats_issued;
    reg [28:0] fetch_address;
    wire native_ready,bridge_fault,unused_submitted;
    workstation_recording_ddr_native_bridge native_bridge(
        .clk_i(memory_clk_i),.rst_ni(memory_reset_n),.published_valid_i(published_valid),
        .slot_ready_i(slot_ready_i),.native_accept_i(native_accept_i),.transport_fault_i(transport_fault_i),
        .slot_valid_o(slot_valid_o),.native_ready_o(native_ready),.transport_fault_o(bridge_fault),
        .submitted_o(unused_submitted),.protocol_fault_o(native_protocol_fault_o));
    wire native_commit=published_valid && native_ready;
    wire native_read_commit=native_commit && !ddr_write_o;
    wire command_expired=published_valid && !native_ready && command_wait>=COMMAND_TIMEOUT_CYCLES-1;
    wire read_expired=read_outstanding && !read_response_i && read_wait>=READ_TIMEOUT_CYCLES-1;
    wire response_bad=read_response_i && !read_outstanding && !native_read_commit;
    wire [31:0] response_generation=read_outstanding ? read_generation : published_generation;
    wire [10:0] response_word=read_outstanding ? read_word : published_word;
    wire memory_fault_now=bridge_fault || command_expired || read_expired || response_bad;
    wire memory_quiescent=!published_valid && !read_outstanding && !return_pending && !pack_word_valid;
    wire memory_drained_now=memory_closed && !memory_active && !memory_clear_pending &&
        !memory_fetch_active && !fifo_read_valid && pack_frames==0 && memory_quiescent && !memory_channel_fault;
    wire [69:0] status_current={memory_generation,memory_committed,memory_drained_now,memory_channel_fault,memory_failure};
    // Capture the complete held tuple before any memory-domain arithmetic.
    // The source cannot replace it before ACK. The extra local cycle removes
    // the cross-clock descriptor-to-business critical path without changing
    // command ordering, cancellation, quarantine or native acceptance.
    wire memory_command_request=command_req_sync!=command_ack && !memory_command_active;
    wire [1:0] memory_command_kind;
    wire [31:0] memory_command_generation,memory_command_offset;
    wire [13:0] memory_command_length;
    wire [PTR_BITS-1:0] memory_command_event_target;
    wire memory_command_start;
    generate if(CAPTURE_COMMAND)begin:g_command_capture
        reg valid;
        (* syn_preserve=1 *) reg [79+PTR_BITS:0] payload;
        wire capture=memory_command_request && !valid;
        always @(posedge memory_clk_i or negedge memory_reset_n)begin
            if(!memory_reset_n)begin valid<=0;payload<=0;end
            else begin
                if(capture)begin
                    payload<={command_kind,command_generation,command_offset,command_length,command_event_target};
                    valid<=1;
                end
                if(memory_command_start)valid<=0;
            end
        end
        assign {memory_command_kind,memory_command_generation,memory_command_offset,
                memory_command_length,memory_command_event_target}=payload;
        assign memory_command_start=memory_command_request && valid;
    end else begin:g_direct_command
        assign {memory_command_kind,memory_command_generation,memory_command_offset,
                memory_command_length,memory_command_event_target}=
               {command_kind,command_generation,command_offset,command_length,command_event_target};
        assign memory_command_start=memory_command_request;
    end endgenerate
    wire start_context_bad=!memory_empty || !memory_closed || memory_active || memory_clear_pending ||
        memory_fetch_active || pack_frames!=0 || !memory_quiescent ||
        fifo_consumed!=memory_command_event_target || memory_command_generation!=memory_generation+1'b1 ||
        memory_generation==32'hffffffff;
    // Only a quiescent START uses this cofactor. The original expression is
    // retained for false/unknown quiescent, preserving procedural X behavior.
    reg start_fault_now,start_initialize;
    always @* begin
        start_fault_now=memory_fault_now;
        if(memory_quiescent)start_fault_now=transport_fault_i || native_protocol_fault_o ||
            unused_submitted || native_accept_i || read_response_i;
        start_initialize=0;
        // An occupied memory slot makes start_context_bad known true. Keep
        // its false and unknown cases explicit so binary mapping need not
        // share the complete command/read fault cone into wide START state.
        case(memory_quiescent)
            1'b0:begin end
            1'b1:begin
                if(memory_command_start)begin
                    if(memory_channel_fault || transport_fault_i || native_protocol_fault_o ||
                       unused_submitted || native_accept_i || read_response_i)begin end
                    else if(memory_command_kind==CMD_START)begin
                        if(start_context_bad)begin end
                        else start_initialize=1;
                    end
                end
            end
            default:begin
                if(memory_command_start)begin
                    if(memory_channel_fault || start_fault_now)begin end
                    else if(memory_command_kind==CMD_START)begin
                        if(start_context_bad)begin end
                        else start_initialize=1;
                    end
                end
            end
        endcase
    end
    // Cache-only proposal: the CLEAR completion assignments remain in their
    // original sequential position. Only a known quiescent slot uses the exact
    // immediate fault cofactor; unknown quiescence retains the complete guard.
    reg clear_initialize;
    always @* begin
        clear_initialize=0;
        case(memory_quiescent)
            1'b0:begin end
            1'b1:begin
                if(memory_clear_pending && fifo_consumed==memory_clear_target &&
                   !fifo_read_valid && !memory_channel_fault &&
                   !(transport_fault_i || native_protocol_fault_o ||
                     unused_submitted || native_accept_i || read_response_i))
                    clear_initialize=1;
            end
            default:begin
                if(memory_clear_pending && fifo_consumed==memory_clear_target &&
                   !fifo_read_valid && memory_quiescent && !memory_channel_fault && !memory_fault_now)
                    clear_initialize=1;
            end
        endcase
    end
    wire clear_fifo_pop=memory_clear_pending && fifo_consumed!=memory_clear_target;
    wire normal_fifo_pop=memory_active && pack_frames<8;
    assign fifo_read_ready=memory_reset_n && !memory_channel_fault && !memory_fault_now &&
        !memory_command_start && (clear_fifo_pop || (!memory_clear_pending && normal_fifo_pop));
    wire fifo_pop=fifo_read_valid && fifo_read_ready;
    wire [32:0] memory_fetch_end={1'b0,memory_command_offset}+{19'd0,memory_command_length};
    wire [8:0] memory_fetch_beats=9'(({10'd0,memory_command_offset[4:0]}+{1'b0,memory_command_length}+15'd31)>>5);
    wire publish_pack=pack_frames==8 || (memory_closed && pack_frames!=0 && !fifo_read_valid);

    // A known bridge fault publishes the transport code directly. Keep the
    // immediate fault, first-fault sticky guard and exact X/Z ternary semantics.
    // This write retains its last priority after every protocol failure.
    reg global_failure_write;
    reg [3:0] global_failure_value;
    always @* begin
        global_failure_write=0;global_failure_value=F_PROTOCOL;
        case(bridge_fault)
            1'b1:begin
                if(!memory_channel_fault)begin
                    global_failure_write=1;global_failure_value=F_TRANSPORT;
                end
            end
            1'b0:begin
                if(command_expired || read_expired || response_bad)begin
                    if(!memory_channel_fault)begin
                        global_failure_write=1;
                        global_failure_value=command_expired ? F_COMMAND_TIMEOUT :
                            read_expired ? F_READ_TIMEOUT : F_PROTOCOL;
                    end
                end
            end
            default:begin
                if(memory_fault_now)begin
                    if(!memory_channel_fault)begin
                        global_failure_write=1;
                        global_failure_value=bridge_fault ? F_TRANSPORT :
                            command_expired ? F_COMMAND_TIMEOUT : read_expired ? F_READ_TIMEOUT : F_PROTOCOL;
                    end
                end
            end
        endcase
    end
    // Retire one previously admitted FIFO word through a fixed lane enable.
    // Native fault/acceptance feedback terminates at the one-bit valid strobe;
    // it never controls a256-bit variable-part-select or whole-pack clear.
    // Old words remain private until their lane is overwritten. Publishing
    // explicitly zeros inactive lanes, preserving every DDR command field.
    always @(posedge memory_clk_i or negedge memory_reset_n)begin
        if(!memory_reset_n)begin pack_word_index<=0;pack_word_data<=0;end
        else begin
            pack_word_index<=pack_frames[2:0];pack_word_data<=fifo_read_data[31:0];
        end
    end
    generate for(genvar lane=0;lane<8;lane=lane+1)begin:g_pack_lane
        always @(posedge memory_clk_i or negedge memory_reset_n)
            if(!memory_reset_n)pack_data[lane*32+:32]<=0;
            else if(pack_word_valid && pack_word_index==3'(lane))
                pack_data[lane*32+:32]<=pack_word_data;
        assign packed_payload[lane*32+:32]=pack_frames>4'(lane) ? pack_data[lane*32+:32] : 32'd0;
    end endgenerate

    // Private failure-code writes keep the original edge and first-fault rule.
    // A known immediate fault suppresses every protocol write, so it reaches
    // the final write enable directly. Its zero cofactor has no fault feedback;
    // unknown fault values retain the exact original procedural projection.
    wire failure_fifo_without_fault=fifo_read_valid && memory_reset_n && !memory_channel_fault &&
        !memory_command_start && (clear_fifo_pop || (!memory_clear_pending && normal_fifo_pop));
    reg memory_failure_protocol_write /* synthesis syn_keep=1 */;
    always @* begin
        memory_failure_protocol_write=0;
        if(failure_fifo_without_fault)begin
            if(!memory_clear_pending)begin
                if(fifo_read_data[63:32]!=memory_next_index ||
                   (!fifo_read_data[64] && memory_next_index>=CAPACITY_FRAMES))begin
                    memory_failure_protocol_write=1;
                end
            end
        end
        if(memory_command_start)begin
            if(memory_channel_fault)begin end
            else case(memory_command_kind)
                CMD_START:begin if(start_context_bad)memory_failure_protocol_write=1;end
                CMD_CLEAR:begin
                    if(memory_command_generation!=memory_generation+1'b1 || memory_generation==32'hffffffff)
                        memory_failure_protocol_write=1;
                end
                CMD_FETCH:begin end
                default:memory_failure_protocol_write=1;
            endcase
        end
    end
    always @(posedge memory_clk_i or negedge memory_reset_n)begin
        if(!memory_reset_n)memory_failure<=0;
        else case(memory_fault_now)
            1'b1:begin
                if(!memory_channel_fault)memory_failure<=global_failure_value;
            end
            1'b0:begin
                if(memory_failure_protocol_write)memory_failure<=F_PROTOCOL;
            end
            default:begin
                if(fifo_pop)begin
                    if(!memory_clear_pending)begin
                        if(fifo_read_data[63:32]!=memory_next_index ||
                           (!fifo_read_data[64] && memory_next_index>=CAPACITY_FRAMES))begin
                            memory_failure<=F_PROTOCOL;
                        end
                    end
                end
                if(memory_command_start)begin
                    if(memory_channel_fault || memory_fault_now)begin end
                    else case(memory_command_kind)
                        CMD_START:begin if(start_context_bad)memory_failure<=F_PROTOCOL;end
                        CMD_CLEAR:begin
                            if(memory_command_generation!=memory_generation+1'b1 || memory_generation==32'hffffffff)
                                memory_failure<=F_PROTOCOL;
                        end
                        CMD_FETCH:begin end
                        default:memory_failure<=F_PROTOCOL;
                    endcase
                end
                if(global_failure_write)memory_failure<=global_failure_value;
            end
        endcase
    end

    always @(posedge memory_clk_i or negedge memory_reset_n)begin
        if(!memory_reset_n)begin
            command_req_meta<=0;command_req_sync<=0;command_ack<=0;cancel_meta<=0;cancel_sync<=0;cancel_seen<=0;
            status_req<=0;status_payload<=0;status_ack_meta<=0;status_ack_sync<=0;
            return_req<=0;return_data<=0;return_generation<=0;return_word<=0;return_pending<=0;
            return_ack_meta<=0;return_ack_sync<=0;
            completion_generation<=0;completion_committed<=0;completion_kind<=0;completion_code<=0;
            memory_generation<=0;memory_next_index<=0;memory_committed<=0;fifo_consumed<=0;memory_clear_target<=0;
            memory_active<=0;memory_closed<=1;memory_empty<=1;memory_clear_pending<=0;memory_command_active<=0;
            memory_channel_fault<=0;pack_frames<=0;published_frames<=0;
            pack_word_valid<=0;
            write_address<=BASE_APP;published_valid<=0;read_outstanding<=0;published_generation<=0;read_generation<=0;
            published_word<=0;read_word<=0;command_wait<=0;read_wait<=0;
            memory_fetch_active<=0;memory_fetch_cancel<=0;fetch_beats_total<=0;fetch_beats_issued<=0;fetch_address<=0;
            ddr_write_o<=0;ddr_address_o<=0;ddr_data_o<=0;ddr_mask_o<=0;
        end else begin
            command_req_meta<=command_req;command_req_sync<=command_req_meta;
            cancel_meta<=cancel_toggle;cancel_sync<=cancel_meta;
            status_ack_meta<=status_ack;status_ack_sync<=status_ack_meta;
            return_ack_meta<=return_ack;return_ack_sync<=return_ack_meta;
            pack_word_valid<=0;
            // Payload is private while this local slot is empty. Preload it
            // without broadcasting native-accept/fault feedback to its wide
            // enables; only published_valid below commits the complete tuple.
            // A published command keeps every field stable until real native
            // acceptance, including through cancel, timeout or quarantine.
            if(!published_valid)begin
                ddr_write_o<=publish_pack;ddr_address_o<=publish_pack ? write_address:fetch_address;
                ddr_data_o<=publish_pack ? packed_payload:256'd0;
                ddr_mask_o<=publish_pack ? 32'hffffffff<<(pack_frames*4):32'd0;
                published_frames<=publish_pack ? pack_frames:4'd0;
                published_generation<=memory_generation;
                published_word<={fetch_beats_issued[7:0],3'b000};
            end
            if(status_req==status_ack_sync && status_payload!=status_current)begin
                status_payload<=status_current;status_req<=~status_req;
            end
            if(cancel_now)begin cancel_seen<=cancel_sync;memory_fetch_cancel<=1;end
            if(published_valid && !native_ready)begin
                if(command_wait!=32'hffffffff)command_wait<=command_wait+1'b1;
            end else command_wait<=0;
            if(read_outstanding && !read_response_i)begin
                if(read_wait!=32'hffffffff)read_wait<=read_wait+1'b1;
            end else read_wait<=0;

            // Retirement happens even after quarantine. Quarantine itself is
            // sticky; a late return cannot make the channel reusable.
            if(native_commit)begin
                published_valid<=0;
                if(ddr_write_o)begin
                    memory_committed<=memory_committed+{28'd0,published_frames};
                    write_address<=write_address+29'd8;
                end else begin
                    read_outstanding<=1;read_generation<=published_generation;read_word<=published_word;
                end
            end
            // The return payload is private until the original narrow request
            // publication below. Preload only while no acknowledged consumer
            // owns the mailbox; pending freezes every payload field until ACK.
            if(!return_pending)begin
                return_data<=read_data_i;return_generation<=response_generation;return_word<=response_word;
            end
            if(read_response_i && (read_outstanding || native_read_commit))begin
                read_outstanding<=0;
                if(memory_fetch_active && !memory_fetch_cancel && !cancel_now &&
                   !memory_channel_fault && !memory_fault_now && response_generation==memory_generation)begin
                    return_req<=~return_req;return_pending<=1;
                end
            end
            if(return_pending && return_ack_sync==return_req)return_pending<=0;

            if(fifo_pop)begin
                fifo_consumed<=fifo_consumed+1'b1;
                if(!memory_clear_pending)begin
                    if(fifo_read_data[63:32]!=memory_next_index ||
                       (!fifo_read_data[64] && memory_next_index>=CAPACITY_FRAMES))begin
                        memory_channel_fault<=1;
                    end else if(fifo_read_data[64])begin
                        memory_active<=0;memory_closed<=1;
                    end else begin
                        pack_word_valid<=1;
                        pack_frames<=pack_frames+1'b1;memory_next_index<=memory_next_index+1'b1;
                    end
                end
            end
            if(!published_valid && !pack_word_valid && !memory_channel_fault && !memory_fault_now &&
               !memory_command_start && !memory_clear_pending)begin
                if(publish_pack)begin
                    published_valid<=1;
                    pack_frames<=0;
                end else if(memory_fetch_active && !memory_fetch_cancel && !cancel_now &&
                    !read_outstanding && !return_pending && fetch_beats_issued<fetch_beats_total)begin
                    published_valid<=1;
                    fetch_address<=fetch_address+29'd8;fetch_beats_issued<=fetch_beats_issued+1'b1;
                end
            end

            if(memory_command_start)begin
                if(memory_channel_fault || memory_fault_now)begin
                    completion_generation<=memory_command_generation;completion_committed<=memory_committed;
                    completion_kind<=memory_command_kind;completion_code<=memory_failure==0 ? F_TRANSPORT : memory_failure;
                    command_ack<=command_req_sync;
                end else case(memory_command_kind)
                    CMD_START:begin
                        // New-epoch frames may reach the FIFO synchronizer at
                        // the same time as START. Prove the old epoch retired
                        // using its immutable event target, not FIFO visibility.
                        if(start_context_bad)begin
                            memory_channel_fault<=1;completion_code<=F_PROTOCOL;
                        end else begin
                            memory_active<=1;memory_closed<=0;memory_empty<=0;completion_code<=0;
                        end
                        completion_generation<=memory_command_generation;completion_committed<=0;completion_kind<=CMD_START;
                        command_ack<=command_req_sync;
                    end
                    CMD_CLEAR:begin
                        if(memory_command_generation!=memory_generation+1'b1 || memory_generation==32'hffffffff)begin
                            memory_channel_fault<=1;
                            completion_generation<=memory_command_generation;completion_committed<=memory_committed;
                            completion_kind<=CMD_CLEAR;completion_code<=F_PROTOCOL;command_ack<=command_req_sync;
                        end else begin
                            memory_generation<=memory_command_generation;memory_command_active<=1;memory_clear_pending<=1;
                            memory_clear_target<=memory_command_event_target;memory_active<=0;memory_closed<=1;memory_empty<=0;
                            pack_frames<=0;
                        end
                    end
                    CMD_FETCH:begin
                        if(memory_command_generation!=memory_generation || !memory_drained_now || memory_empty ||
                           memory_command_length==0 || memory_command_length>8112 || memory_fetch_end[32] ||
                           {2'd0,memory_fetch_end}>{1'b0,memory_committed,2'b0})begin
                            completion_generation<=memory_command_generation;completion_committed<=memory_committed;
                            completion_kind<=CMD_FETCH;completion_code<=F_DESCRIPTOR;command_ack<=command_req_sync;
                        end else begin
                            memory_fetch_active<=1;memory_fetch_cancel<=cancel_now;memory_command_active<=1;
                            fetch_beats_total<=memory_fetch_beats;fetch_beats_issued<=0;
                            fetch_address<=BASE_APP+{2'd0,memory_command_offset[28:5],3'b000};
                        end
                    end
                    default:begin
                        memory_channel_fault<=1;
                        completion_generation<=memory_command_generation;completion_committed<=memory_committed;
                        completion_kind<=memory_command_kind;completion_code<=F_PROTOCOL;command_ack<=command_req_sync;
                    end
                endcase
            end
            // Preserve the original START assignment priority, before CLEAR
            // completion. No request, acknowledgement or fault state moves.
            if(start_initialize)begin
                memory_generation<=memory_command_generation;memory_next_index<=0;
                memory_committed<=0;write_address<=BASE_APP;
            end
            if(clear_initialize)begin
                memory_clear_pending<=0;memory_command_active<=0;memory_empty<=1;memory_closed<=1;
                memory_next_index<=0;memory_committed<=0;memory_fetch_cancel<=0;
                completion_generation<=memory_generation;completion_committed<=0;
                completion_kind<=CMD_CLEAR;completion_code<=0;command_ack<=command_req_sync;
            end
            if(memory_fetch_active && memory_quiescent &&
               (memory_fetch_cancel || cancel_now || memory_channel_fault ||
                fetch_beats_issued==fetch_beats_total))begin
                memory_fetch_active<=0;memory_command_active<=0;
                completion_generation<=memory_generation;completion_committed<=memory_committed;completion_kind<=CMD_FETCH;
                completion_code<=memory_channel_fault ? memory_failure :
                    (memory_fetch_cancel || cancel_now) ? F_CANCELLED : 4'd0;
                command_ack<=command_req_sync;
            end
            if(memory_fault_now)begin
                memory_channel_fault<=1;memory_fetch_cancel<=1;
            end
        end
    end
endmodule
`default_nettype wire
