`timescale 1ns/1ps
// Explicit task3 direct-file owner. One native SPI/FAT/WAV owner, no DDR API.
// Committed rate/epoch and command generation are frozen session snapshots.
module workstation_tf_direct_runtime_service #(
    parameter integer SPI_CLK_DIV=100,SPI_CLK_DIV_FAST=12,
    parameter integer VERIFY_DATA_CRC=0,
    parameter integer FAT_SECTOR_CACHE=0,
    parameter integer TOKEN_WAIT_CLOCKS=8320000,WATCHDOG_CLOCKS=250000000,
    parameter integer BYTE_DEPTH=4096,PCM_DEPTH=4096,PREFILL_FRAMES=3072,
    parameter integer FIFO_ADDRESS_BITS=4,QUIET_TIMEOUT_CYCLES=25000000,
    parameter bit SEPARATE_COMMON_RESET=0,
    parameter bit LOCAL_COMPUTE_RESET_ENABLE=0,
    parameter bit LOCAL_NATIVE_HEAD_ENABLE=0,
    parameter bit REMOTE_ANALYSIS_ENABLE=0
)(
    input wire rst_ni,common_reset_ni,clk_50m_i,compute_clk_i,
    input wire mode_i,run_i,restart_i,cancel_i,transport_error_i,
    input wire [3:0] track_index_i,
    input wire runtime_valid_i,runtime_44k1_i,runtime_fault_i,runtime_busy_i,
    input wire [31:0] runtime_epoch_i,
    input wire sd_miso_i,
    output wire sd_cs_no,sd_sck_o,sd_mosi_o,
    output wire [4:0] track_count_o,
    output wire playlist_ready_o,card_lost_o,
    input wire [7:0] playlist_name_address_i,
    output wire [7:0] playlist_name_data_o,
    output wire format_ready_o,unsupported_o,
    output wire [19:0] file_sample_rate_o,
    output wire busy_50_o,failed_o,eof_seen_o,
    output wire [3:0] failure_code_o,
    output wire media_quiescent_50_o,
    output wire tf_active_o,tf_busy_o,tf_valid_o,tf_error_o,tf_last_o,tf_pause_o,
    output wire signed [15:0] tf_left_o,tf_right_o,
    output wire [19:0] tf_sample_rate_o,
    output wire [31:0] tf_generation_o,tf_session_o,expected_generation_o,
    input wire tf_ready_i,
    output wire media_quiescent_o,
    // Optional dedicated offline analysis pass through THIS file owner.
    // Defaults retain the existing playback/physical-EOS contract.
    input wire analysis_request_i,analysis_cancel_i,analysis_start_ready_i,
    output wire analysis_start_valid_o,
    output wire [31:0] analysis_session_o,
    output wire analysis_pcm_valid_o,analysis_pcm_last_o,
    input wire analysis_pcm_ready_i,
    output wire [31:0] analysis_pcm_o,
    output wire analysis_cancel_o,
    // The unique runtime router/serializer/observation path supplies these.
    input wire physical_eos_i,physical_quiescent_i,physical_failed_i,physical_abort_i,
    input wire stop_request_i,
    output reg stop_pending_o,stop_done_o,stop_failed_o,
    output reg [3:0] stop_failure_code_o
);
    localparam [2:0] IDLE=0,DRAIN=1,LAUNCH=2,PREFILL=3,PLAY=4,ENDED=5;
    localparam [3:0] CONTEXT=1,EPOCH=2,FILE=3,INGRESS=4,TRANSPORT=5,
        PHYSICAL=6,QUIET_TIMEOUT=7,EMPTY=8;
    wire common_n=SEPARATE_COMMON_RESET ? common_reset_ni:rst_ni;
    (* ASYNC_REG="TRUE",syn_preserve=1 *) reg [1:0] startup_source,startup_compute;
    (* ASYNC_REG="TRUE",syn_preserve=1 *) reg [2:0] source_release,compute_release;
    always @(posedge clk_50m_i or negedge common_n)
        if(!common_n)begin startup_source<=0;source_release<=0;end
        else begin
            startup_source<={startup_source[0],rst_ni};
            if(SEPARATE_COMMON_RESET && !startup_source[1])source_release<=0;
            else source_release<={source_release[1:0],1'b1};
        end
    always @(posedge compute_clk_i or negedge common_n)
        if(!common_n)begin startup_compute<=0;compute_release<=0;end
        else begin
            startup_compute<={startup_compute[0],rst_ni};
            if(SEPARATE_COMMON_RESET && !startup_compute[1])compute_release<=0;
            else compute_release<={compute_release[1:0],1'b1};
        end
    wire source_n=source_release[2],compute_n=compute_release[2];
    // One common lifetime; functional release follows its own compute clock.
    // Session cancellation never resets an outstanding receipt or snapshot.
    wire compute_functional_n=LOCAL_COMPUTE_RESET_ENABLE ? compute_n:common_n;
    reg [2:0] state;
    reg restart_q,cancel_q,mode_q,stop_q,transport_q,analysis_q,analysis_cancel_q;
    reg [3:0] track_q,pending_track;
    reg pending_start,pending_rate,session_rate,session_applied,native_quiet;
    reg pending_analysis,session_analysis;
    reg failed,eof_seen;
    reg [3:0] failure;
    reg [31:0] session,pending_epoch,session_epoch,quiet_wait;
    localparam integer STATUS_WIDTH=68;
    reg [STATUS_WIDTH-1:0] held_status,compute_status;
    wire native_ready,native_applied,native_stop_done,native_stop_failed,native_pending;
    wire native_valid,native_last,native_active,native_prefill,native_empty,native_file_error,native_ingress_error;
    wire [3:0] native_file_code,native_ingress_code;
    wire [19:0] native_rate;
    wire [31:0] native_session;
    wire signed [15:0] native_left,native_right;
    wire bridge_ready,source_quiet,generation_pending,bridge_quiet,expected_valid;
    wire [31:0] source_generation;
    wire analysis_live=REMOTE_ANALYSIS_ENABLE && session_analysis;
    wire bad_context=!analysis_live && (!runtime_valid_i || runtime_fault_i || runtime_busy_i);
    wire resume_event=restart_i && !restart_q;
    wire cancel_event=(cancel_i && !cancel_q) || (mode_q && !mode_i && !analysis_live) ||
        (analysis_live && analysis_cancel_i && !analysis_cancel_q);
    wire stop_event=stop_request_i && !stop_q && !stop_pending_o;
    wire analysis_event=REMOTE_ANALYSIS_ENABLE && analysis_request_i && !analysis_q;
    wire new_command=((mode_i && (resume_event || track_index_i!=track_q)) || analysis_event) &&
        !cancel_event && !stop_event && !stop_pending_o;
    wire live=state==PREFILL || state==PLAY || state==ENDED;

    // Reliable event receipt: immutable session/kind bundle until source ACK.
    // The next session cannot start until the physical quiet proof returns.
    reg receipt_request,receipt_ack,receipt_seen;
    reg [33:0] receipt_payload;
    reg [31:0] queued_receipt_session;
    reg abort_queued,eos_queued;
    (* ASYNC_REG="TRUE",syn_preserve=1 *) reg [1:0] receipt_request_sync,receipt_ack_sync,physical_quiet_sync;
    reg receipt_capture;
    // Capture the held compute payload at one explicit clk50 boundary. All
    // file/ingress/cancellation policy consumes only this local register on
    // the following edge, so no remote payload reaches a business CE or WRE.
    (* syn_preserve=1 *) reg [33:0] receipt_local;
    reg receipt_dispatch;
    wire receipt_free=receipt_request==receipt_ack_sync[1];
    always @(posedge compute_clk_i or negedge compute_functional_n)
        if(!compute_functional_n)begin receipt_request<=0;receipt_payload<=0;queued_receipt_session<=0;receipt_ack_sync<=0;abort_queued<=0;eos_queued<=0;end
        else begin
            receipt_ack_sync<={receipt_ack_sync[0],receipt_ack};
            if(physical_abort_i || physical_failed_i)begin
                abort_queued<=1;eos_queued<=0;queued_receipt_session<=compute_status[35:4];
            end else if(physical_eos_i && !abort_queued)begin eos_queued<=1;queued_receipt_session<=compute_status[35:4];end
            if(compute_n && receipt_free)begin
                if(abort_queued || physical_abort_i || physical_failed_i)begin
                    receipt_payload<={(physical_abort_i || physical_failed_i) ? compute_status[35:4]:queued_receipt_session,2'd2};receipt_request<=!receipt_request;abort_queued<=0;eos_queued<=0;
                end else if(eos_queued || physical_eos_i)begin
                    receipt_payload<={physical_eos_i ? compute_status[35:4]:queued_receipt_session,2'd1};receipt_request<=!receipt_request;eos_queued<=0;
                end
            end
        end
    wire receipt_event=receipt_capture && receipt_request_sync[1]!=receipt_seen;
    (* syn_keep=1 *) wire [3:0] receipt_session_equal;
    for(genvar receipt_byte=0;receipt_byte<4;receipt_byte=receipt_byte+1)begin:g_receipt_session_equal
        assign receipt_session_equal[receipt_byte]=~(|(receipt_local[2+receipt_byte*8+:8]^session[receipt_byte*8+:8]));
    end
    wire receipt_current=&receipt_session_equal;
    wire physical_failure_event=receipt_dispatch && receipt_current && receipt_local[1:0]==2;
    wire physical_end_event=receipt_dispatch && receipt_current && receipt_local[1:0]==1;
    always @(posedge clk_50m_i or negedge common_n)
        if(!common_n)begin receipt_request_sync<=0;receipt_capture<=0;receipt_seen<=0;receipt_ack<=0;physical_quiet_sync<=0;receipt_local<=0;receipt_dispatch<=0;end
        else begin
            receipt_request_sync<={receipt_request_sync[0],receipt_request};
            receipt_capture<=receipt_request_sync[1]!=receipt_seen;
            physical_quiet_sync<={physical_quiet_sync[0],physical_quiescent_i};
            receipt_dispatch<=0;
            if(receipt_event)begin
                receipt_local<=receipt_payload;receipt_dispatch<=1;
                receipt_seen<=receipt_request_sync[1];receipt_ack<=receipt_request_sync[1];receipt_capture<=0;
            end
        end
    reg [3:0] failure_now;
    always @* begin
        failure_now=0;
        if(live || state==LAUNCH)begin
            if(native_file_error)failure_now=FILE;
            else if(session_applied && native_ingress_error)failure_now=INGRESS;
            else if(transport_error_i)failure_now=TRANSPORT;
            else if(bad_context)failure_now=CONTEXT;
            else if(session_applied && !analysis_live && (runtime_epoch_i!=session_epoch || runtime_44k1_i!=session_rate))failure_now=EPOCH;
            else if(!analysis_live && physical_failure_event)failure_now=PHYSICAL;
            else if(session_applied && native_empty)failure_now=EMPTY;
            else if(analysis_live && state==LAUNCH && quiet_wait==QUIET_TIMEOUT_CYCLES-1)failure_now=QUIET_TIMEOUT;
        end
    end
    // Cancellation needs the existence of a fault, independently of the
    // diagnostic code priority. Avoid code selection followed by decoding on
    // the same-cycle source/analysis stop path. The default preserves RTL
    // procedural unknown-guard semantics; no cycle or public status changes.
    wire [7:0] fault_conditions={native_file_error,
        session_applied && native_ingress_error,transport_error_i,bad_context,
        session_applied && !analysis_live && (runtime_epoch_i!=session_epoch || runtime_44k1_i!=session_rate),
        !analysis_live && physical_failure_event,session_applied && native_empty,
        analysis_live && state==LAUNCH && quiet_wait==QUIET_TIMEOUT_CYCLES-1};
    reg failure_present;
    always @* begin
        failure_present=0;
        case(^fault_conditions)
            1'b0,1'b1:if(live || state==LAUNCH)failure_present=|fault_conditions;
            default:failure_present=failure_now!=0;
        endcase
    end
    wire new_failure=failure_present && !failed;
    wire invalidate=source_n && (new_command || cancel_event || stop_event || new_failure);
    wire native_stop=state==DRAIN;
    wire source_quiesce=state==IDLE || state==DRAIN || state==LAUNCH || invalidate;
    // One bounded native PCM head breaks downstream cancellation/backpressure
    // from the ingress RAM enable. Cancellation still suppresses publication
    // on its original edge; any speculative native pop is locally discarded.
    reg head_valid,head_last;
    reg [31:0] head_pcm,head_session;
    reg [19:0] head_rate;
    wire head_ready=!head_valid && state==PLAY;
    wire head_pop=head_valid && !source_quiesce &&
        (analysis_live ? analysis_pcm_ready_i:bridge_ready);
    always @(posedge clk_50m_i or negedge source_n)
        if(!source_n)begin
            head_valid<=0;head_last<=0;head_pcm<=0;head_session<=0;head_rate<=0;
        end else if(source_quiesce)head_valid<=0;
        else begin
            if(head_pop)head_valid<=0;
            if(native_valid && head_ready)begin
                head_valid<=1;head_last<=native_last;head_pcm<={native_right,native_left};
                head_session<=native_session;head_rate<=native_rate;
            end
        end
    wire dequeued_valid=LOCAL_NATIVE_HEAD_ENABLE ? head_valid:native_valid;
    wire dequeued_last=LOCAL_NATIVE_HEAD_ENABLE ? head_last:native_last;
    wire [31:0] dequeued_pcm=LOCAL_NATIVE_HEAD_ENABLE ? head_pcm:{native_right,native_left};
    wire [31:0] dequeued_session=LOCAL_NATIVE_HEAD_ENABLE ? head_session:native_session;
    wire [19:0] dequeued_rate=LOCAL_NATIVE_HEAD_ENABLE ? head_rate:native_rate;
    (* syn_preserve=1 *) reg source_quiesce_level;
    always @(posedge clk_50m_i or negedge common_n)
        if(!common_n)source_quiesce_level<=1'b1;
        else source_quiesce_level<=!source_n || source_quiesce;
    wire native_request=state==LAUNCH && !bad_context && !cancel_event && !stop_event &&
        (!pending_analysis || analysis_start_ready_i);
    assign analysis_start_valid_o=REMOTE_ANALYSIS_ENABLE && native_request && native_ready && pending_analysis;
    assign analysis_session_o=session;
    assign analysis_pcm_valid_o=analysis_live && dequeued_valid && !source_quiesce && !invalidate;
    assign analysis_pcm_last_o=dequeued_last;
    assign analysis_pcm_o=dequeued_pcm;
    assign analysis_cancel_o=analysis_live && invalidate;
    workstation_tf_direct_native_v1 #(.SPI_CLK_DIV(SPI_CLK_DIV),.SPI_CLK_DIV_FAST(SPI_CLK_DIV_FAST),
        .TOKEN_WAIT_CLOCKS(TOKEN_WAIT_CLOCKS),.WATCHDOG_CLOCKS(WATCHDOG_CLOCKS),
        .VERIFY_DATA_CRC(VERIFY_DATA_CRC),.FAT_SECTOR_CACHE(FAT_SECTOR_CACHE),
        .BYTE_DEPTH(BYTE_DEPTH),.PCM_DEPTH(PCM_DEPTH),.PREFILL_FRAMES(PREFILL_FRAMES)) native(
        .clk_i(clk_50m_i),.rst_ni(source_n),.spi_ssn_o(sd_cs_no),.spi_sck_o(sd_sck_o),.spi_mosi_o(sd_mosi_o),.spi_miso_i(sd_miso_i),
        .request_valid_i(native_request),.request_ready_o(native_ready),.track_index_i(pending_track),.generation_i(session),
        .expected_rate_i(pending_rate ? 20'd44100:20'd48000),.stop_i(native_stop),.pause_i(!analysis_live && !run_i),
        // Physical deadlines belong to the unique actual downstream router.
        .sample_request_i(1'b0),.request_applied_o(native_applied),.request_pending_o(native_pending),
        .stop_completed_o(native_stop_done),.stop_failed_o(native_stop_failed),
        .pcm_valid_o(native_valid),.pcm_ready_i(LOCAL_NATIVE_HEAD_ENABLE ? head_ready:
            ((analysis_live?analysis_pcm_ready_i:bridge_ready) && !source_quiesce)),
        .pcm_left_o(native_left),.pcm_right_o(native_right),.pcm_last_o(native_last),
        .generation_o(native_session),.session_rate_o(native_rate),.active_o(native_active),.prefill_ready_o(native_prefill),.empty_o(native_empty),
        .ingress_failed_o(native_ingress_error),.ingress_failure_code_o(native_ingress_code),
        .file_error_o(native_file_error),.file_error_code_o(native_file_code),
        .scan_done_o(playlist_ready_o),.track_count_o(track_count_o),
        .name_raddr_i(playlist_name_address_i),.name_rdata_o(playlist_name_data_o));
    workstation_tf_frame_bridge_v2 #(.FIFO_ADDRESS_BITS(FIFO_ADDRESS_BITS),
        .LOCAL_COMPUTE_RESET_ENABLE(LOCAL_COMPUTE_RESET_ENABLE)) frames(
        .rst_ni(common_n),.source_clk_i(clk_50m_i),.compute_clk_i,
        .invalidate_i(invalidate),.source_quiesce_i(source_quiesce_level),
        .source_valid_i(dequeued_valid && !source_quiesce && !analysis_live),.source_error_i(1'b0),.source_last_i(dequeued_last),
        .source_session_generation_i(dequeued_session),.source_sample_rate_i(dequeued_rate),
        .source_left_i(dequeued_pcm[15:0]),.source_right_i(dequeued_pcm[31:16]),.source_ready_o(bridge_ready),
        .source_generation_o(source_generation),.source_generation_pending_o(generation_pending),.source_quiescent_o(source_quiet),
        .tf_valid_o(tf_valid_o),.tf_ready_i(tf_ready_i),.tf_error_o(tf_error_o),.tf_last_o(tf_last_o),.tf_session_generation_o(tf_session_o),
        .tf_sample_rate_o(tf_sample_rate_o),.tf_left_o(tf_left_o),.tf_right_o(tf_right_o),.tf_generation_o(tf_generation_o),
        .expected_generation_o(expected_generation_o),.expected_generation_valid_o(expected_valid),.media_quiescent_o(bridge_quiet));
    // Immutable status mailbox. Gray generation separately revokes admission
    // even if this source clock stops before its inactive status can arrive.
    wire [STATUS_WIDTH-1:0] desired_status={source_generation,session,mode_i && live && !analysis_live,run_i,
        state!=IDLE && !analysis_live,failed && !analysis_live};
    reg status_request,status_ack,status_capture;
    (* ASYNC_REG="TRUE",syn_preserve=1 *) reg [1:0] status_request_sync,status_ack_sync;
    always @(posedge clk_50m_i or negedge common_n)
        if(!common_n)begin held_status<=0;status_request<=0;status_ack_sync<=0;end
        else begin
            status_ack_sync<={status_ack_sync[0],status_ack};
            if(source_n && status_ack_sync[1]==status_request && held_status!=desired_status)begin
                held_status<=desired_status;status_request<=!status_request;
            end
        end
    always @(posedge compute_clk_i or negedge compute_functional_n)
        if(!compute_functional_n)begin status_request_sync<=0;status_ack<=0;status_capture<=0;compute_status<=0;end
        else begin
            status_request_sync<={status_request_sync[0],status_request};
            status_capture<=status_request_sync[1]!=status_ack;
            if(compute_n && status_capture)begin compute_status<=held_status;status_ack<=status_request_sync[1];status_capture<=0;end
        end
    wire status_current=expected_valid && compute_status[67:36]==expected_generation_o;
    wire control_pending=status_ack_sync[1]!=status_request || held_status!=desired_status;
    assign tf_active_o=compute_n && status_current && compute_status[3];
    assign tf_pause_o=!status_current || !compute_status[2];
    assign tf_busy_o=compute_n && (!status_current || compute_status[1]);
    assign media_quiescent_o=compute_n && bridge_quiet && physical_quiescent_i && !tf_active_o && !tf_busy_o;
    assign busy_50_o=state!=IDLE;
    assign failed_o=failed;
    assign failure_code_o=failure;
    assign eof_seen_o=eof_seen;
    assign card_lost_o=native_file_error;
    assign format_ready_o=native_prefill && !native_ingress_error && !native_file_error;
    assign unsupported_o=native_ingress_error;
    assign file_sample_rate_o=native_rate;
    assign media_quiescent_50_o=state==IDLE && source_quiet && physical_quiet_sync[1] && !control_pending;
    always @(posedge clk_50m_i or negedge source_n)
        if(!source_n)begin
            state<=IDLE;restart_q<=0;cancel_q<=0;mode_q<=0;stop_q<=0;transport_q<=0;track_q<=0;analysis_q<=0;analysis_cancel_q<=0;
            pending_track<=0;pending_start<=0;pending_rate<=0;pending_epoch<=0;
            session<=0;session_rate<=0;session_epoch<=0;session_applied<=0;native_quiet<=0;
            pending_analysis<=0;session_analysis<=0;
            failed<=0;failure<=0;eof_seen<=0;quiet_wait<=0;
            stop_pending_o<=0;stop_done_o<=0;stop_failed_o<=0;stop_failure_code_o<=0;
        end else begin
            restart_q<=restart_i;cancel_q<=cancel_i;mode_q<=mode_i;stop_q<=stop_request_i;
            analysis_q<=REMOTE_ANALYSIS_ENABLE && analysis_request_i;
            analysis_cancel_q<=REMOTE_ANALYSIS_ENABLE && analysis_cancel_i;
            transport_q<=transport_error_i;track_q<=track_index_i;
            stop_done_o<=0;stop_failed_o<=0;
            if(native_applied)begin session_applied<=1;session_rate<=pending_rate;session_epoch<=pending_epoch;end
            if(physical_end_event && live && !analysis_live)begin eof_seen<=1;state<=ENDED;end
            if(analysis_live && state==PLAY && dequeued_valid && analysis_pcm_ready_i && dequeued_last && !source_quiesce)begin
                // File EOF releases the shared native reader. Recognition
                // may continue on W without retaining M's media-stop grant.
                eof_seen<=1;state<=DRAIN;quiet_wait<=0;native_quiet<=0;pending_start<=0;
            end
            if(state==LAUNCH && native_request && native_ready)begin state<=PREFILL;session_applied<=0;end
            if(analysis_live && state==LAUNCH && quiet_wait<QUIET_TIMEOUT_CYCLES)quiet_wait<=quiet_wait+1'b1;
            if(state==PREFILL && native_active)state<=PLAY;
            if(state==DRAIN)begin
                if(native_stop_done)native_quiet<=1;
                if(quiet_wait<QUIET_TIMEOUT_CYCLES)quiet_wait<=quiet_wait+1'b1;
                if(native_stop_failed || native_file_error)begin
                    failed<=1;failure<=FILE;pending_start<=0;native_quiet<=0;
                    if(stop_pending_o)begin stop_pending_o<=0;stop_failed_o<=1;stop_failure_code_o<=FILE;end
                    // A failed drain is not quiet/success. Keep its source
                    // fence held until coordinated whole-owner reset.
                end else if((native_quiet || native_stop_done) && source_quiet &&
                            physical_quiet_sync[1] && !control_pending)begin
                    quiet_wait<=0;
                    if(stop_pending_o)begin stop_pending_o<=0;stop_done_o<=1;end
                    if(pending_start && (mode_i || pending_analysis) && !bad_context)begin state<=LAUNCH;pending_start<=0;end
                    else begin state<=IDLE;pending_start<=0;end
                end else if(quiet_wait==QUIET_TIMEOUT_CYCLES-1)begin
                    failed<=1;failure<=QUIET_TIMEOUT;pending_start<=0;
                    if(stop_pending_o)begin stop_pending_o<=0;stop_failed_o<=1;stop_failure_code_o<=QUIET_TIMEOUT;end
                end
            end
            if(invalidate)begin
                state<=DRAIN;quiet_wait<=0;
                if(state!=DRAIN)native_quiet<=0;
                session_applied<=0;
                if(new_command)begin
                    session<=session+1'b1;pending_track<=track_index_i;
                    pending_analysis<=analysis_event;session_analysis<=analysis_event;
                    pending_rate<=analysis_event?1'b0:runtime_44k1_i;pending_epoch<=runtime_epoch_i;pending_start<=1;
                    failed<=0;failure<=0;eof_seen<=0;
                end else pending_start<=0;
                if(new_failure)begin failed<=1;failure<=failure_now;pending_start<=0;end
                if(stop_event)begin
                    pending_start<=0;stop_pending_o<=1;stop_failure_code_o<=0;
                    if(new_failure)begin stop_pending_o<=0;stop_failed_o<=1;stop_failure_code_o<=failure_now;end
                end
            end
        end
endmodule
