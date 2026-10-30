`timescale 1ns/1ps
`default_nettype none
// Opt-in TF owner. The maintained reader/DDR/decoder stay intact. Only the
// physical-playback policy and its atomic transport are composed here.
module workstation_tf_runtime_service #(
    parameter integer AUDIO_KIND=2,
    parameter [23:0] FILE_EXT="WAV",
    parameter integer FIFO_ADDRESS_BITS=4,
    parameter integer QUIET_TIMEOUT_CYCLES=2000000,
    parameter [27:0] HOTPLUG_TIMEOUT_CYCLES=28'd200000000,
    parameter [27:0] HOTPLUG_STALL_TIMEOUT_CYCLES=28'd250000000,
    parameter integer EXTERNAL_STOP_PROTOCOL=0
) (
    input wire rst_ni,clk_50m_i,compute_clk_i,memory_clk_i,memory_reset_ni,memory_ready_i,
    // restart_i is an explicit user TF restart, never a card-return retry.
    // reader_restart_i retains the existing analysis-only reader request.
    input wire mode_i,run_i,restart_i,cancel_i,reader_restart_i,transport_error_i,
    input wire [3:0] track_index_i,
    input wire runtime_valid_i,runtime_44k1_i,runtime_fault_i,runtime_busy_i,
    input wire [31:0] runtime_epoch_i,
    input wire analysis_enable_i,analysis_hold_i,analysis_pcm_ready_i,
    output wire analysis_pcm_valid_o,analysis_pcm_end_o,
    output wire signed [15:0] analysis_left_o,analysis_right_o,
    output wire [19:0] analysis_sample_rate_o,
    input wire sd_miso_i,
    output wire sd_cs_no,sd_sck_o,sd_mosi_o,
    output wire [4:0] track_count_o,
    output wire playlist_ready_o,card_lost_o,
    output wire [10:0] hotplug_debug_o,
    input wire [7:0] playlist_name_address_i,
    output wire [7:0] playlist_name_data_o,
    output wire format_ready_o,unsupported_o,ddr_error_o,
    output wire [31:0] file_size_o,
    output wire [19:0] file_sample_rate_o,
    output wire ddr_valid_o,ddr_write_o,
    output wire [28:0] ddr_address_o,
    output wire [255:0] ddr_data_o,
    input wire ddr_ready_i,ddr_response_i,
    input wire [255:0] ddr_read_data_i,
    // Source-domain policy/status. Busy includes pause, EOF and cancel drain.
    output reg busy_50_o,failed_o,cancelled_o,eof_seen_o,
    output reg [3:0] failure_code_o,
    output wire paused_o,control_pending_o,media_quiescent_50_o,
    output wire [31:0] source_generation_o,source_accepted_count_o,
    output reg [31:0] failure_count_o,invalidate_count_o,
    // All ports below are continuous compute domain, never naked 50-MHz bits.
    output wire tf_active_o,tf_busy_o,tf_valid_o,tf_error_o,
    output wire signed [15:0] tf_left_o,tf_right_o,
    output wire [19:0] tf_sample_rate_o,
    output wire [31:0] tf_generation_o,expected_generation_o,
    input wire tf_ready_i,
    output wire media_quiescent_o,
    output wire [31:0] stale_discard_count_o,quiesce_discard_count_o,
    // Optional 50-MHz stop transaction; explicitly enabled by the new owner.
    input wire stop_request_i,
    output reg stop_pending_o,stop_done_o,stop_failed_o,
    output reg [3:0] stop_failure_code_o
);
    localparam [2:0] IDLE=0,QUIESCE=1,WAIT_FORMAT=2,PLAY=3,RESTART_SETTLE=4;
    localparam [3:0] RATE=1,FORMAT=2,DDR=3,CARD=4,CONTEXT=5,EPOCH=6,
        TRANSPORT=7,QUIET_TIMEOUT=8;
    reg [2:0] state;
    reg restart_playback;
    reg [3:0] path_track;
    reg path_clear_toggle,pending_clear;
    wire path_clear_done;
    (* ASYNC_REG="TRUE",syn_preserve=1 *) reg [1:0] memory_open_sync;
    reg restart_q,cancel_q,reader_restart_q,mode_q,run_q,card_lost_q,transport_error_q;
    reg [3:0] track_q;
    reg pending_start,pending_reader_restart,path_restart;
    reg launched_rate;
    reg [31:0] launched_epoch;
    reg [31:0] quiet_wait;
    wire track_change=track_index_i!=track_q;
    wire explicit_restart=restart_i && !restart_q;
    wire cancel_event=(cancel_i && !cancel_q) || (mode_q && !mode_i);
    wire reader_restart=reader_restart_i && !reader_restart_q;
    reg stop_request_q,stop_latched,stop_transaction_failed;
    reg [31:0] stop_wait;
    wire stop_begin=(EXTERNAL_STOP_PROTOCOL!=0) && stop_request_i && !stop_request_q && !stop_pending_o;
    // Stop wins simultaneous restart, and requests during pending coalesce.
    wire resume_restart=explicit_restart && !stop_pending_o && !stop_begin;
    wire auto_track_change=track_change && !stop_latched && !stop_begin;
    wire allowed_reader_restart=reader_restart && !stop_latched && !stop_begin;
    wire allowed_cancel=cancel_event && !stop_latched;
    wire stop_cleanup_complete;
    // A latched stop admits no new media; only an explicit resume clears it.
    // Repeated stop requests therefore reuse that fence. Completion itself
    // depends on source_quiet and must never feed back into invalidate.
    wire stop_invalidate=stop_begin && !stop_latched;
    wire physical=(state==RESTART_SETTLE && restart_playback) || state==WAIT_FORMAT || state==PLAY;
    wire memory_quiet_50,memory_gate;
    (* ASYNC_REG="TRUE",syn_preserve=1 *) reg [1:0] memory_ready_sync;
    wire bad_context=!runtime_valid_i || runtime_fault_i || runtime_busy_i;
    reg [3:0] error_now;
    always @* begin
        error_now=0;
        if(physical)begin
            if(card_lost_o)error_now=CARD;
            else if((state!=RESTART_SETTLE && ddr_error_o) || !memory_ready_sync[1])error_now=DDR;
            else if(state!=RESTART_SETTLE && unsupported_o)error_now=FORMAT;
            else if(transport_error_i)error_now=TRANSPORT;
            else if(bad_context)error_now=CONTEXT;
            else if(runtime_epoch_i!=launched_epoch || runtime_44k1_i!=launched_rate)error_now=EPOCH;
            else if(state!=RESTART_SETTLE && format_ready_o && file_sample_rate_o!=(launched_rate ? 20'd44100:20'd48000))error_now=RATE;
        end
    end
    // Every termination is visible to the generation bridge on THIS edge.
    // A registered invalidate pulse would be lost if source clock stopped now.
    wire new_failure=error_now!=0;
    wire invalidate=resume_restart || auto_track_change || allowed_cancel || new_failure || (!mode_i && allowed_reader_restart) || stop_invalidate ||
        (!stop_latched && ((card_lost_o && !card_lost_q) || (transport_error_i && !transport_error_q)));
    wire bridge_source_ready,source_quiet,generation_pending;
    wire source_quiesce=state==IDLE || state==QUIESCE || state==RESTART_SETTLE || invalidate;
    wire playback_accept=state==PLAY && mode_i && run_i && !invalidate && !stop_latched;
    wire path_pcm_valid,path_pcm_ready,path_pcm_end;
    wire signed [15:0] path_left,path_right;
    wire analysis_accept=state==IDLE && !invalidate && !stop_latched && !mode_i && analysis_enable_i &&
        (!analysis_hold_i || analysis_pcm_ready_i);
    assign path_pcm_ready=playback_accept ? bridge_source_ready : analysis_accept;
    assign analysis_pcm_valid_o=!mode_i && analysis_enable_i && path_pcm_valid && path_pcm_ready;
    assign analysis_pcm_end_o=state==IDLE && !stop_latched && !mode_i && path_pcm_end;
    assign analysis_left_o=path_left;
    assign analysis_right_o=path_right;
    assign analysis_sample_rate_o=file_sample_rate_o;
    function automatic [31:0] increment(input [31:0] value);
        increment=&value ? value:value+1'b1;
    endfunction
    initial if(QUIET_TIMEOUT_CYCLES<8)$fatal(1,"TF quiet timeout too short");
    always @(posedge clk_50m_i or negedge rst_ni)begin
        if(!rst_ni)begin
            state<=IDLE;restart_playback<=0;memory_ready_sync<=0;
            path_track<=0;path_clear_toggle<=0;pending_clear<=0;
            memory_open_sync<=0;
            restart_q<=0;cancel_q<=0;reader_restart_q<=0;mode_q<=0;run_q<=0;
            track_q<=0;card_lost_q<=0;transport_error_q<=0;pending_start<=0;
            pending_reader_restart<=0;path_restart<=0;launched_rate<=0;launched_epoch<=0;
            quiet_wait<=0;busy_50_o<=0;failed_o<=0;cancelled_o<=0;eof_seen_o<=0;
            failure_code_o<=0;failure_count_o<=0;invalidate_count_o<=0;
        end else begin
            memory_ready_sync<={memory_ready_sync[0],memory_ready_i && memory_reset_ni};
            memory_open_sync<={memory_open_sync[0],!memory_gate};
            restart_q<=restart_i;cancel_q<=cancel_i;reader_restart_q<=reader_restart_i;
            mode_q<=mode_i;run_q<=run_i;track_q<=track_index_i;
            card_lost_q<=card_lost_o;transport_error_q<=transport_error_i;path_restart<=0;
            if(invalidate)invalidate_count_o<=increment(invalidate_count_o);
            if(physical && path_pcm_end)eof_seen_o<=1;
            if((state==QUIESCE || state==RESTART_SETTLE) && !(source_quiet && memory_quiet_50 && path_clear_done))begin
                if(quiet_wait<QUIET_TIMEOUT_CYCLES)quiet_wait<=quiet_wait+1'b1;
                if(quiet_wait==QUIET_TIMEOUT_CYCLES-1)begin
                    failed_o<=1;failure_code_o<=QUIET_TIMEOUT;pending_start<=0;
                    restart_playback<=0;
                    failure_count_o<=increment(failure_count_o);
                end
            end else quiet_wait<=0;
            if(state==QUIESCE && source_quiet && memory_quiet_50 && path_clear_done)begin
                if(pending_start && mode_i)begin
                    if(bad_context)begin
                        pending_start<=0;state<=RESTART_SETTLE;failed_o<=1;restart_playback<=0;
                        path_restart<=1;path_clear_toggle<=~path_clear_toggle;pending_clear<=0;
                        failure_code_o<=CONTEXT;failure_count_o<=increment(failure_count_o);
                    end else begin
                        path_restart<=1;path_track<=track_index_i;path_clear_toggle<=~path_clear_toggle;pending_clear<=0;
                        pending_start<=0;pending_reader_restart<=0;
                        launched_rate<=runtime_44k1_i;launched_epoch<=runtime_epoch_i;
                        state<=RESTART_SETTLE;restart_playback<=1;
                    end
                end else if(pending_reader_restart && !mode_i)begin
                    path_restart<=1;path_track<=track_index_i;path_clear_toggle<=~path_clear_toggle;pending_clear<=0;
                    pending_reader_restart<=0;restart_playback<=0;state<=RESTART_SETTLE;
                end else if(pending_clear)begin
                    path_restart<=1;path_clear_toggle<=~path_clear_toggle;pending_clear<=0;
                    restart_playback<=0;state<=RESTART_SETTLE;
                end else begin
                    state<=IDLE;busy_50_o<=0;
                    pending_reader_restart<=0;
                end
            end
            if(state==RESTART_SETTLE)begin
                if(path_clear_done && memory_open_sync[1])begin
                    if(restart_playback)state<=WAIT_FORMAT;
                    else begin state<=IDLE;busy_50_o<=0;end
                end
            end
            if(state==WAIT_FORMAT && format_ready_o && !new_failure)state<=PLAY;
            if(invalidate)begin
                state<=QUIESCE;busy_50_o<=1;quiet_wait<=0;
                pending_clear<=1;
                pending_start<=mode_i && (resume_restart || auto_track_change) && !allowed_cancel && !stop_begin;
                pending_reader_restart<=!mode_i && (allowed_reader_restart || auto_track_change) && !stop_begin;
                if(resume_restart || auto_track_change)begin
                    failed_o<=0;cancelled_o<=0;failure_code_o<=0;eof_seen_o<=0;
                end
                if(allowed_cancel)begin pending_start<=0;cancelled_o<=physical || busy_50_o;end
                if(new_failure)begin
                    pending_start<=0;failed_o<=1;failure_code_o<=error_now;
                    failure_count_o<=increment(failure_count_o);
                end
            end
        end
    end
    // This completion is entirely source-domain evidence. The mailbox equality
    // includes ACK of the final inactive/busy=0 payload, not only busy falling.
    assign stop_cleanup_complete=state==IDLE && !busy_50_o && source_quiet && path_clear_done &&
        memory_open_sync[1] && !control_pending_o;
    always @(posedge clk_50m_i or negedge rst_ni)begin
        if(!rst_ni)begin
            stop_request_q<=0;stop_latched<=0;stop_transaction_failed<=0;stop_wait<=0;
            stop_pending_o<=0;stop_done_o<=0;stop_failed_o<=0;stop_failure_code_o<=0;
        end else begin
            stop_request_q<=(EXTERNAL_STOP_PROTOCOL!=0) && stop_request_i;
            stop_done_o<=0;stop_failed_o<=0;
            if(resume_restart)stop_latched<=0;
            if(stop_begin)begin
                stop_latched<=1;stop_pending_o<=1;stop_wait<=0;
                stop_transaction_failed<=new_failure;stop_failure_code_o<=new_failure ? error_now:4'd0;
                if(new_failure)stop_failed_o<=1;
            end else if(stop_pending_o)begin
                if(new_failure && !stop_transaction_failed)begin
                    stop_transaction_failed<=1;stop_failed_o<=1;stop_failure_code_o<=error_now;
                end
                if(stop_cleanup_complete)begin
                    stop_pending_o<=0;
                    if(!stop_transaction_failed && !new_failure)stop_done_o<=1;
                end else begin
                    if(stop_wait<QUIET_TIMEOUT_CYCLES)stop_wait<=stop_wait+1'b1;
                    if(stop_wait==QUIET_TIMEOUT_CYCLES-1 && !stop_transaction_failed && !new_failure)begin
                        stop_transaction_failed<=1;stop_failed_o<=1;stop_failure_code_o<=QUIET_TIMEOUT;
                    end
                end
            end
        end
    end
    wire [2:0] path_command;
    wire path_write,path_end,path_ddr_valid;
    tf_audio_ddr_path #(.FILE_EXT(FILE_EXT),.AUDIO_KIND(AUDIO_KIND),.CAPTURE_ON_ANALYSIS(1),
        .HOTPLUG_TIMEOUT_CYCLES(HOTPLUG_TIMEOUT_CYCLES),
        .HOTPLUG_STALL_TIMEOUT_CYCLES(HOTPLUG_STALL_TIMEOUT_CYCLES),.NATIVE_RESTART_HOLD(1),.NATIVE_RUNTIME_PROTOCOL(1)) path(
        .clk_50m(clk_50m_i),.reset_n(rst_ni),.restart(path_restart),.track_index(path_track),
        .capture_enable_i(!stop_latched && !stop_begin && ((state==IDLE && !mode_i && analysis_enable_i) ||
            ((state==WAIT_FORMAT || state==PLAY) && mode_i && run_i && !new_failure))),
        .memory_clk(memory_clk_i),.memory_reset_n(memory_reset_ni),.memory_ready(memory_ready_i),
        .sample_tick(1'b0),.sd_miso(sd_miso_i),.sd_cs_n(sd_cs_no),.sd_sck(sd_sck_o),.sd_mosi(sd_mosi_o),
        .card_type(),.card_stat(),.filesystem_type(),.filesystem_stat(),.scan_done(),
        .card_lost(card_lost_o),.hotplug_debug(hotplug_debug_o),.card_ready(),.playing(),.eof(),
        .track_count(track_count_o),.playlist_ready(playlist_ready_o),
        .playlist_name_addr(playlist_name_address_i),.playlist_name_data(playlist_name_data_o),
        .format_ready(format_ready_o),.unsupported(unsupported_o),.audio_ddr_error(ddr_error_o),
        .audio_bank0_valid(),.audio_bank1_valid(),.audio_file_size(file_size_o),.sample_rate_hz(file_sample_rate_o),
        .stereo(),.bits_per_sample(),.pcm_valid(path_pcm_valid),.pcm_end(path_pcm_end),
        .pcm_ready(path_pcm_ready),.pcm_left(path_left),.pcm_right(path_right),
        .frame_count(),.resync_count(),.skipped_frames(),.stuck_frames(),.pcm_fifo_parity_errors(),
        .debug_cmdrsp(),.debug_rwrsp(),.debug_cardstate(),.debug_spidone(),.debug_rvalid_session(),
        .app_cmd(path_command),.app_en(path_ddr_valid),.app_addr(ddr_address_o),.app_wdata(ddr_data_o),
        .app_rdy(ddr_ready_i && !memory_gate),.app_wren(path_write),.app_wend(path_end),.app_wrdy(ddr_ready_i && !memory_gate),
        .app_rvalid(ddr_response_i),.app_rdata(ddr_read_data_i),.native_memory_hold_i(memory_gate),
        .native_source_hold_i(state==QUIESCE || state==RESTART_SETTLE || invalidate || stop_latched || (state==IDLE && mode_i)),
        .runtime_clear_toggle_i(path_clear_toggle),.runtime_clear_done_o(path_clear_done));
    // A file restart must not reinterpret an old accepted DDR response as the
    // new file's first beat. Stop acceptance, drain the one outstanding read,
    // return a quiet ACK, then pulse the unchanged path's restart.
    reg memory_stop;
    always @(posedge clk_50m_i or negedge rst_ni)
        if(!rst_ni)memory_stop<=0;
        else if(invalidate)memory_stop<=1;
        else if(state==RESTART_SETTLE && path_clear_done)memory_stop<=0;
        else if(state==QUIESCE && source_quiet && memory_quiet_50 && path_clear_done && !pending_clear &&
            !(pending_start && mode_i) && !(pending_reader_restart && !mode_i))memory_stop<=0;
    (* ASYNC_REG="TRUE",syn_preserve=1 *) reg [1:0] memory_gate_sync;
    always @(posedge memory_clk_i or negedge rst_ni)
        if(!rst_ni)memory_gate_sync<=0;else memory_gate_sync<={memory_gate_sync[0],memory_stop};
    assign memory_gate=memory_gate_sync[1];
    reg memory_read_pending;
    always @(posedge memory_clk_i or negedge memory_reset_ni)
        if(!memory_reset_ni)memory_read_pending<=0;
        else begin
            if(ddr_valid_o && ddr_ready_i && !ddr_write_o)memory_read_pending<=1;
            if(ddr_response_i)memory_read_pending<=0;
        end
    // Register the aggregate before crossing it: synchronizing a combinational
    // AND of independently changing memory flops can capture a transient ACK.
    // The extra memory edge is conservative: acceptance closes before this
    // ACK, and the last ordered response clears pending one edge before it.
    reg memory_quiet;
    always @(posedge memory_clk_i or negedge rst_ni)
        if(!rst_ni)memory_quiet<=0;
        else memory_quiet<=memory_gate && !memory_read_pending;
    (* ASYNC_REG="TRUE",syn_preserve=1 *) reg [1:0] memory_quiet_sync;
    always @(posedge clk_50m_i or negedge rst_ni)
        if(!rst_ni)memory_quiet_sync<=0;else memory_quiet_sync<={memory_quiet_sync[0],memory_quiet};
    assign memory_quiet_50=memory_quiet_sync[1];
    assign ddr_valid_o=path_ddr_valid && !memory_gate;
    assign ddr_write_o=ddr_valid_o && path_write && path_end && path_command==0;
    wire bridge_valid,bridge_error,bridge_ready,bridge_quiet,expected_valid;
    wire [19:0] bridge_rate;
    wire signed [15:0] bridge_left,bridge_right;
    wire [31:0] bridge_generation;
    workstation_tf_frame_bridge #(.FIFO_ADDRESS_BITS(FIFO_ADDRESS_BITS)) frames(
        .rst_ni,.source_clk_i(clk_50m_i),.compute_clk_i,.invalidate_i(invalidate),.source_quiesce_i(source_quiesce),
        .source_valid_i(path_pcm_valid && playback_accept),.source_error_i(1'b0),
        .source_sample_rate_i(file_sample_rate_o),.source_left_i(path_left),.source_right_i(path_right),
        .source_ready_o(bridge_source_ready),.source_generation_o,.source_generation_pending_o(generation_pending),
        .source_quiescent_o(source_quiet),.source_accepted_count_o,.source_unsupported_count_o(),.source_error_count_o(),
        .tf_valid_o(bridge_valid),.tf_ready_i(bridge_ready),.tf_error_o(bridge_error),.tf_sample_rate_o(bridge_rate),
        .tf_left_o(bridge_left),.tf_right_o(bridge_right),.tf_generation_o(bridge_generation),
        .expected_generation_o,.expected_generation_valid_o(expected_valid),.generation_change_o(),
        .media_quiescent_o(bridge_quiet),.stale_discard_count_o,.quiesce_discard_count_o);
    // Held request/ACK snapshot: a slow destination may coalesce states, but
    // source never overwrites an unacknowledged payload. Generation fencing
    // independently revokes old active control even if source stops on cancel.
    localparam CTRL_BITS=36;
    wire [CTRL_BITS-1:0] desired_control={source_generation_o,launched_rate,
        state==PLAY && mode_i,run_q,busy_50_o};
    reg [CTRL_BITS-1:0] held_control,compute_control;
    reg control_request,control_ack,control_capture;
    (* ASYNC_REG="TRUE",syn_preserve=1 *) reg [1:0] request_sync,ack_sync;
    always @(posedge clk_50m_i or negedge rst_ni)begin
        if(!rst_ni)begin held_control<=0;control_request<=0;ack_sync<=0;end
        else begin
            ack_sync<={ack_sync[0],control_ack};
            if(ack_sync[1]==control_request && held_control!=desired_control)begin
                held_control<=desired_control;control_request<=~control_request;
            end
        end
    end
    always @(posedge compute_clk_i or negedge rst_ni)begin
        if(!rst_ni)begin request_sync<=0;control_ack<=0;control_capture<=0;compute_control<=0;end
        else begin
            request_sync<={request_sync[0],control_request};
            control_capture<=request_sync[1]!=control_ack;
            if(control_capture)begin compute_control<=held_control;control_ack<=request_sync[1];control_capture<=0;end
        end
    end
    assign control_pending_o=ack_sync[1]!=control_request || held_control!=desired_control;
    assign paused_o=state==PLAY && !run_q && !control_pending_o;
    wire control_active=compute_control[2] && compute_control[35:4]==expected_generation_o && expected_valid;
    assign tf_active_o=control_active;
    // Pause supplies explicit silence while retaining every FIFO/decoder pair.
    assign tf_valid_o=control_active && (!compute_control[1] || bridge_valid);
    assign tf_error_o=compute_control[1] && bridge_error;
    assign tf_sample_rate_o=compute_control[1] ? bridge_rate:(compute_control[3] ? 20'd44100:20'd48000);
    assign tf_left_o=compute_control[1] ? bridge_left:16'sd0;
    assign tf_right_o=compute_control[1] ? bridge_right:16'sd0;
    assign tf_generation_o=compute_control[1] ? bridge_generation:expected_generation_o;
    assign bridge_ready=tf_ready_i && control_active && compute_control[1];
    (* ASYNC_REG="TRUE",syn_preserve=1 *) reg [2:0] busy_release;
    always @(posedge compute_clk_i or negedge rst_ni or posedge busy_50_o)
        if(!rst_ni || busy_50_o)busy_release<=3'b111;
        else busy_release<={busy_release[1:0],1'b0};
    assign tf_busy_o=busy_release[2] || compute_control[0];
    assign media_quiescent_50_o=source_quiet && !busy_50_o;
    assign media_quiescent_o=bridge_quiet && !control_active && !tf_busy_o;
endmodule
`default_nettype wire
