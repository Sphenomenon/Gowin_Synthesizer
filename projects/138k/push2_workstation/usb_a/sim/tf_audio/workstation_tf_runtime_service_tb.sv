`timescale 1ns/1ps
// Standalone-runner SD/FAT endpoint model: real path, DMA, FIFOs and WAV remain.
module tf_sd_file_reader #(parameter [23:0] EXT="WAV",parameter integer SPI_CLK_DIV=100,SPI_CLK_DIV_FAST=12)(
    input wire rstn,clk,spi_miso,track_start,sector_allow,
    input wire [3:0] track_index,
    input wire [7:0] name_raddr,
    output wire spi_ssn,spi_sck,spi_mosi,
    output wire [1:0] card_type,filesystem_type,
    output wire [3:0] card_stat,debug_cardstate,
    output wire [2:0] filesystem_stat,
    output wire scan_done,sector_busy,playing,
    output reg eof,outen,
    output reg [7:0] outbyte,
    output wire [4:0] track_count,
    output wire [7:0] name_rdata,debug_cmdrsp,debug_rwrsp,
    output wire debug_spidone,debug_rvalid_session
);
    reg present=1;
    reg active,start_pending;
    integer index;
    reg [3:0] selected;
    reg [7:0] file0[0:299],file1[0:299],file2[0:299],file3[0:299];
    initial begin
        $readmemh("file0.hex",file0);$readmemh("file1.hex",file1);
        $readmemh("file2.hex",file2);$readmemh("file3.hex",file3);
    end
    assign spi_ssn=1;assign spi_sck=0;assign spi_mosi=0;
    assign card_type=2;assign filesystem_type=1;assign filesystem_stat=0;
    assign card_stat=8;assign debug_cardstate=8;assign scan_done=rstn && present;
    assign track_count=4;assign name_rdata=name_raddr;
    assign sector_busy=!present;assign playing=active;
    assign debug_cmdrsp=present ? 0:8'h80;assign debug_rwrsp=0;
    assign debug_spidone=0;assign debug_rvalid_session=present;
    always @(posedge clk or negedge rstn)begin
        if(!rstn)begin active<=0;start_pending<=0;index<=0;selected<=0;outen<=0;eof<=0;outbyte<=0;end
        else begin
            outen<=0;eof<=0;
            if(track_start && present)begin active<=0;start_pending<=1;index<=0;selected<=track_index;end
            else if(start_pending)begin active<=1;start_pending<=0;end
            else if(active && present && sector_allow)begin
                outen<=1;
                case(selected)
                    0:outbyte<=file0[index];1:outbyte<=file1[index];
                    2:outbyte<=file2[index];default:outbyte<=file3[index];
                endcase
                if(index==299)begin active<=0;eof<=1;end else index<=index+1;
            end
        end
    end
endmodule

module tb_workstation_tf_runtime_service #(parameter integer USE_COMMAND_BUFFER=0,RUN_SCENARIOS=1,EXTERNAL_STOP_PROTOCOL=0,
    OVERALL_TIMEOUT_NS=3000000);
    reg source_clk=0,compute_clk=0,memory_clk=0,source_run=1,compute_run=1,memory_run=1,rst_n=0;
    always begin #10;if(source_run)source_clk=~source_clk;end
    always begin #6.510416667;if(compute_run)compute_clk=~compute_clk;end
    always #5 if(memory_run)memory_clk=~memory_clk;
    reg mode=1,run=1,restart=0,cancel=0,reader_restart=0,transport_error=0;
    reg stop_request=0;
    wire stop_pending,stop_done,stop_failed;
    wire [3:0] stop_failure;
    reg [3:0] track=0;
    reg runtime_valid=1,runtime_rate=0,runtime_fault=0,runtime_busy=0;
    reg [31:0] runtime_epoch=32'd4;
    reg analysis_enable=0,analysis_hold=1,analysis_ready=0;
    wire analysis_valid,analysis_end;
    wire signed [15:0] analysis_left,analysis_right;
    wire [19:0] analysis_rate;
    wire req,write_req,ddr_ready,ddr_response;
    wire [28:0] address;
    wire [255:0] write_data,read_data;
    wire busy50,failed,cancelled,eof_seen,paused,pending,quiet50,tf_active,tf_busy,tf_valid,tf_error,quiet;
    wire [3:0] failure;
    wire signed [15:0] tf_left,tf_right;
    wire [19:0] tf_rate;
    wire [31:0] generation,expected,source_generation,accepted,failures,invalidates,stale,discarded;
    wire card_lost;
    wire playlist_ready;
    reg use_scope=0,scope_control_valid=0;
    reg [31:0] scope_control=0;
    wire scope_mode,scope_run,scope_restart,scope_analysis_cancel,scope_error,scope_explicit_restart,scope_file_cancel;
    wire [3:0] scope_track;
    wire legacy_scope_mode,legacy_scope_run,legacy_scope_restart,legacy_scope_cancel,legacy_scope_error;
    wire [3:0] legacy_scope_track;
    scope_tf_transport scope_transport(.clk_i(source_clk),.rst_ni(rst_n),
        .control_valid_i(scope_control_valid),.control_i(scope_control),.song_valid_i(1'b0),.song_track_i(4'd0),
        .playlist_ready_i(playlist_ready),.card_lost_i(card_lost),.track_count_i(5'd4),
        .mode_o(scope_mode),.run_o(scope_run),.track_o(scope_track),.restart_o(scope_restart),
        .cancel_analysis_o(scope_analysis_cancel),.error_o(scope_error),
        .explicit_restart_o(scope_explicit_restart),.file_cancel_o(scope_file_cancel));
    scope_tf_transport_legacy_reference scope_reference(.clk_i(source_clk),.rst_ni(rst_n),
        .control_valid_i(scope_control_valid),.control_i(scope_control),.song_valid_i(1'b0),.song_track_i(4'd0),
        .playlist_ready_i(playlist_ready),.card_lost_i(card_lost),.track_count_i(5'd4),
        .mode_o(legacy_scope_mode),.run_o(legacy_scope_run),.track_o(legacy_scope_track),.restart_o(legacy_scope_restart),
        .cancel_analysis_o(legacy_scope_cancel),.error_o(legacy_scope_error));
    integer scope_explicit_count=0,scope_file_cancel_count=0,scope_auto_count=0,scope_compares=0;
    always @(negedge source_clk)if(rst_n)begin
        if({scope_mode,scope_run,scope_track,scope_restart,scope_analysis_cancel,scope_error}!==
           {legacy_scope_mode,legacy_scope_run,legacy_scope_track,legacy_scope_restart,legacy_scope_cancel,legacy_scope_error})
            $fatal(1,"legacy scope outputs changed");
        scope_compares=scope_compares+1;
    end
    always @(posedge source_clk)if(rst_n)begin
        if(scope_explicit_restart)scope_explicit_count=scope_explicit_count+1;
        if(scope_file_cancel)scope_file_cancel_count=scope_file_cancel_count+1;
        if(scope_restart && !scope_explicit_restart)scope_auto_count=scope_auto_count+1;
    end
    reg tf_ready=0;
    workstation_tf_runtime_service #(.FIFO_ADDRESS_BITS(3),.QUIET_TIMEOUT_CYCLES(1000),.EXTERNAL_STOP_PROTOCOL(EXTERNAL_STOP_PROTOCOL),
        .HOTPLUG_TIMEOUT_CYCLES(28'd40),.HOTPLUG_STALL_TIMEOUT_CYCLES(28'd70)) dut(
        .rst_ni(rst_n),.clk_50m_i(source_clk),.compute_clk_i(compute_clk),.memory_clk_i(memory_clk),
        .memory_reset_ni(rst_n),.memory_ready_i(1'b1),.mode_i(use_scope ? scope_mode:mode),.run_i(use_scope ? scope_run:run),
        .restart_i(use_scope ? scope_explicit_restart:restart),.cancel_i(use_scope ? scope_file_cancel:cancel),
        .reader_restart_i(reader_restart),.transport_error_i(use_scope ? scope_error:transport_error),
        .track_index_i(use_scope ? scope_track:track),.runtime_valid_i(runtime_valid),.runtime_44k1_i(runtime_rate),
        .runtime_fault_i(runtime_fault),.runtime_busy_i(runtime_busy),.runtime_epoch_i(runtime_epoch),
        .analysis_enable_i(analysis_enable),.analysis_hold_i(analysis_hold),.analysis_pcm_ready_i(analysis_ready),
        .analysis_pcm_valid_o(analysis_valid),.analysis_pcm_end_o(analysis_end),
        .analysis_left_o(analysis_left),.analysis_right_o(analysis_right),.analysis_sample_rate_o(analysis_rate),
        .sd_miso_i(1'b1),.sd_cs_no(),.sd_sck_o(),.sd_mosi_o(),.track_count_o(),.playlist_ready_o(playlist_ready),
        .card_lost_o(card_lost),.hotplug_debug_o(),.playlist_name_address_i(8'd0),.playlist_name_data_o(),
        .format_ready_o(),.unsupported_o(),.ddr_error_o(),.file_size_o(),.file_sample_rate_o(),
        .ddr_valid_o(req),.ddr_write_o(write_req),.ddr_address_o(address),.ddr_data_o(write_data),
        .ddr_ready_i(ddr_ready),.ddr_response_i(ddr_response),.ddr_read_data_i(read_data),
        .busy_50_o(busy50),.failed_o(failed),.cancelled_o(cancelled),.eof_seen_o(eof_seen),
        .failure_code_o(failure),.paused_o(paused),.control_pending_o(pending),.media_quiescent_50_o(quiet50),
        .source_generation_o(source_generation),.source_accepted_count_o(accepted),
        .failure_count_o(failures),.invalidate_count_o(invalidates),
        .tf_active_o(tf_active),.tf_busy_o(tf_busy),.tf_valid_o(tf_valid),.tf_error_o(tf_error),
        .tf_left_o(tf_left),.tf_right_o(tf_right),.tf_sample_rate_o(tf_rate),.tf_generation_o(generation),
        .expected_generation_o(expected),.tf_ready_i(tf_ready),.media_quiescent_o(quiet),
        .stale_discard_count_o(stale),.quiesce_discard_count_o(discarded),
        .stop_request_i(stop_request),.stop_pending_o(stop_pending),.stop_done_o(stop_done),
        .stop_failed_o(stop_failed),.stop_failure_code_o(stop_failure));
    localparam [28:0] BASE=29'h0600000;
    reg [255:0] memory[0:127];
    wire downstream_req,downstream_write,downstream_ready;
    wire [28:0] downstream_address;
    wire [255:0] downstream_data;
    if(USE_COMMAND_BUFFER)begin: buffered
        tf_audio_ddr_command_buffer buffer(.clk(memory_clk),.rst_n(rst_n),.in_valid(req),.in_write(write_req),
            .in_address(address),.in_data(write_data),.in_ready(ddr_ready),
            .out_valid(downstream_req),.out_write(downstream_write),.out_address(downstream_address),
            .out_data(downstream_data),.out_ready(downstream_ready));
    end else begin: direct
        assign downstream_req=req,downstream_write=write_req,downstream_address=address,downstream_data=write_data;
        assign ddr_ready=downstream_ready;
    end
    reg response=0,read_pending=0;
    reg [255:0] response_data=0,pending_data;
    reg stall_reads=0,hold_response=0;
    integer response_delay=0,extra_response_delay=0,memory_cycle=0,ddr_writes=0,ddr_reads=0,read_drain_wait_cycles=0;
    integer queued_accepts=0,downstream_stalls=0;
    integer upstream_reads=0,responses_consumed=0,path_restarts=0;
    integer quiet_source_checks=0,quiet_source_changes=0,queued_drain_tests=0,adjacent_drain_tests=0,cancel_drain_tests=0;
    reg expected_memory_quiet,previous_memory_quiet=0;
    realtime last_memory_edge=0;
    assign downstream_ready=! (stall_reads && !downstream_write) &&
        memory_cycle%7!=0 && (!USE_COMMAND_BUFFER || memory_cycle%31<9);
    assign ddr_response=response;
    assign read_data=response_data;
    // The CDC source must be a flop, including the memory edge on which the
    // gate closes or the response clears pending. A combinational aggregate
    // fails these pre-edge-to-post-edge checks even if all PCM still matches.
    always @(posedge memory_clk)begin
        last_memory_edge=$realtime;
        expected_memory_quiet=dut.memory_gate && !dut.memory_read_pending;
        #0.001;
        if(rst_n)begin
            if(dut.memory_quiet!==expected_memory_quiet)$fatal(1,"quiet aggregate was not registered in memory domain");
            quiet_source_checks=quiet_source_checks+1;
            if(dut.memory_quiet!=previous_memory_quiet)quiet_source_changes=quiet_source_changes+1;
        end
        previous_memory_quiet=dut.memory_quiet;
    end
    always @(dut.memory_quiet)if(rst_n && $realtime!=last_memory_edge)
        $fatal(1,"quiet CDC source changed between memory edges");
    always @(posedge memory_clk)begin
        memory_cycle<=memory_cycle+1;response<=0;
        if(rst_n && req && ddr_ready && !write_req)upstream_reads=upstream_reads+1;
        if(rst_n && response)responses_consumed=responses_consumed+1;
        if(rst_n && dut.memory_gate && dut.memory_read_pending)read_drain_wait_cycles=read_drain_wait_cycles+1;
        if(rst_n && req && ddr_ready && !(downstream_req && downstream_ready))queued_accepts=queued_accepts+1;
        if(rst_n && downstream_req && !downstream_ready)downstream_stalls=downstream_stalls+1;
        if(downstream_req && downstream_ready)begin
            if(downstream_address<BASE || downstream_address>=BASE+1024 || downstream_address[2:0]!=0)$fatal(1,"DDR authority/alignment changed %h",downstream_address);
            if(downstream_write)begin memory[(downstream_address-BASE)>>3]<=downstream_data;ddr_writes<=ddr_writes+1;end
            else begin
                if(read_pending)$fatal(1,"multiple outstanding TF reads");
                pending_data<=memory[(downstream_address-BASE)>>3];response_delay<=3+memory_cycle%5+extra_response_delay;
                read_pending<=1;ddr_reads<=ddr_reads+1;
            end
        end
        if(read_pending)begin
            if(response_delay==0 && !hold_response)begin response<=1;response_data<=pending_data;read_pending<=0;end
            else if(response_delay!=0)response_delay<=response_delay-1;
        end
    end
    integer compute_cycle=0,delivered=0,pause_zeros=0,analysis_frames=0,session_index=0;
    integer expected_track=0,tests=0,stop_checks=0;
    reg checking=1;
    always @(negedge compute_clk)begin
        compute_cycle=compute_cycle+1;tf_ready=rst_n && compute_cycle%80==0;
    end
    always @(posedge compute_clk)if(rst_n)begin
        if(quiet && (tf_active || tf_busy || tf_valid))$fatal(1,"false compute media quiet");
        if(tf_active && tf_valid && tf_ready)begin
            if(generation!==expected || tf_error)$fatal(1,"invalid TF context/error");
            if(!dut.compute_control[1])begin
                if(tf_left!==0 || tf_right!==0)$fatal(1,"pause was not silent");
                pause_zeros=pause_zeros+1;
            end else begin
                if(checking && (session_index>=64 || tf_left!==16'(1000+expected_track*100+session_index) ||
                   tf_right!==16'(-2000-expected_track*100-session_index) ||
                   tf_rate!==(expected_track==1 ? 20'd44100:20'd48000)))
                    $fatal(1,"real PCM mismatch session=%0d index=%0d L=%0d R=%0d rate=%0d",expected_track,session_index,tf_left,tf_right,tf_rate);
                session_index=session_index+1;delivered=delivered+1;
            end
        end
    end
    always @(posedge source_clk)if(rst_n && analysis_valid)begin
        if(!analysis_ready || tf_active || mode || analysis_rate!=48000 ||
           analysis_left!==16'(1000+analysis_frames%64) || analysis_right!==16'(-2000-analysis_frames%64))
            $fatal(1,"analysis ownership/payload mismatch %0d",analysis_frames);
        analysis_frames=analysis_frames+1;
    end
    always @(posedge source_clk)if(rst_n && dut.path_restart)begin
        path_restarts=path_restarts+1;
        if(dut.memory_read_pending || !dut.memory_gate || !dut.memory_quiet || !dut.memory_quiet_50)
            $fatal(1,"path restarted before registered held DDR read drain proof");
    end
    task pulse_restart;
        begin @(negedge source_clk);restart=1;@(negedge source_clk);restart=0;end
    endtask
    task scope_command(input [15:0] epoch_value,input bit enabled,input [1:0] action_value);
        begin
            @(negedge source_clk);scope_control={epoch_value,2'd0,enabled,enabled,4'd0,action_value,6'd0};
            scope_control_valid=1;@(negedge source_clk);scope_control_valid=0;
        end
    endtask
    task await_quiet;
        integer count;
        begin
            count=0;
            while(!quiet50 || !quiet)begin
                @(negedge source_clk);count=count+1;
                if(count>2000)$fatal(1,"quiet timeout state=%0d busy=%b src=%b mem=%b ctrl=%h",dut.state,busy50,dut.source_quiet,dut.memory_quiet_50,dut.compute_control);
            end
        end
    endtask
    task await_active(input [3:0] new_track,input [31:0] target_generation);
        integer count;
        begin
            count=0;
            while(!tf_active || expected!=target_generation || dut.compute_control[35:4]!=target_generation)begin
                @(negedge source_clk);count=count+1;
                if(count>20000)$fatal(1,"start timeout track=%0d state=%0d failed=%b code=%0d format=%b path_rate=%0d pcm=%b path_restart=%b bytes=%0d reader=%b quiet=%b/%b dmaW=%0d dmaR=%0d capture=%b/%b eof=%b playback=%b bytecount=%0d fifo=%0d/%0d",new_track,dut.state,failed,failure,dut.format_ready_o,dut.file_sample_rate_o,dut.path_pcm_valid,dut.path_restart,dut.path.captured_bytes,dut.path.u_file_reader.active,dut.source_quiet,dut.memory_quiet_50,dut.path.g_runtime_dma.u_dma.write_total_bytes,dut.path.g_runtime_dma.u_dma.read_total_bytes,dut.path.capture_done_toggle,dut.path.g_runtime_dma.u_dma.capture_seen,dut.path.g_runtime_dma.u_dma.eof_finalized,dut.path.playback_active,dut.path.decoder_byte_count,dut.path.in_wr_count,dut.path.out_rd_count);
            end
            checking=1;
        end
    endtask
    task begin_file(input [3:0] new_track);
        reg [31:0] target_generation;
        begin
            checking=0;@(negedge source_clk);track=new_track;
            expected_track=new_track;session_index=0;pulse_restart();
            target_generation=source_generation;await_active(new_track,target_generation);
        end
    endtask
    task await_frames(input integer target);
        integer count;
        begin
            count=0;
            while(session_index<target)begin
                @(negedge compute_clk);count=count+1;
                if(count>100000)$fatal(1,"frame timeout target=%0d index=%0d state=%0d failure=%0d fmt=%b rate=%0d path_valid=%b",target,session_index,dut.state,failure,dut.format_ready_o,dut.file_sample_rate_o,dut.path_pcm_valid);
            end
        end
    endtask
    task fail_expected(input [3:0] code);
        integer count;
        begin
            checking=0;count=0;
            while(!failed)begin @(negedge source_clk);count=count+1;if(count>20000)$fatal(1,"failure timeout expected %0d state=%0d fmt=%b rate=%0d bytes=%0d dmaW=%0d dmaR=%0d inwait=%b rdvalid=%b empty=%b hold=%b reader=%b track=%0d",code,dut.state,dut.format_ready_o,dut.file_sample_rate_o,dut.path.captured_bytes,dut.path.g_runtime_dma.u_dma.write_total_bytes,dut.path.g_runtime_dma.u_dma.read_total_bytes,dut.path.g_runtime_dma.u_dma.in_read_wait,dut.path.in_rd_valid,dut.path.in_empty,dut.path.capture_switch_hold,dut.path.u_file_reader.active,track);end
            if(failure!==code)$fatal(1,"wrong failure expected=%0d got=%0d",code,failure);
            await_quiet();if(tf_active || busy50)$fatal(1,"failed file retained route");tests=tests+1;
        end
    endtask
    // With the real one-entry buffer, the service has accepted the read while
    // physical DDR has not. Both restart and cancel must wait through queue
    // residency, physical acceptance and the last old-file response.
    task queued_read_drain(input bit cancel_only);
        integer upstream_before,physical_before,response_before,restarts_before;
        begin
            checking=0;@(negedge source_clk);cancel=1;@(negedge source_clk);cancel=0;await_quiet();
            checking=0;hold_response=1;stall_reads=USE_COMMAND_BUFFER;
            upstream_before=upstream_reads;physical_before=ddr_reads;response_before=responses_consumed;
            @(negedge source_clk);runtime_rate=0;runtime_epoch=runtime_epoch+1;track=0;pulse_restart();
            wait(upstream_reads>upstream_before);#1;
            if(!dut.memory_read_pending)$fatal(1,"service did not retain accepted read");
            if(USE_COMMAND_BUFFER && (ddr_reads!=physical_before || read_pending || !downstream_req || downstream_write))
                $fatal(1,"directed read was not queued before physical DDR acceptance");
            restarts_before=path_restarts;
            fork
                begin
                    if(cancel_only)begin
                        @(negedge source_clk);cancel=1;@(negedge source_clk);cancel=0;
                    end else begin_file(1);
                end
                begin
                    wait(dut.memory_gate);
                    if(!cancel_only)begin runtime_rate=1;runtime_epoch=runtime_epoch+1;end
                    repeat(12)begin
                        @(negedge memory_clk);
                        if(!dut.memory_read_pending || dut.memory_quiet || dut.memory_quiet_50 || path_restarts!=restarts_before)
                            $fatal(1,"queued old read falsely acknowledged quiet");
                        if(USE_COMMAND_BUFFER && (ddr_reads!=physical_before || read_pending))
                            $fatal(1,"queued old read bypassed forced arbiter stall");
                    end
                    if(USE_COMMAND_BUFFER)queued_drain_tests=queued_drain_tests+1;
                    stall_reads=0;wait(read_pending);wait(response_delay==0);
                    repeat(6)begin
                        @(negedge memory_clk);
                        if(!dut.memory_read_pending || dut.memory_quiet || path_restarts!=restarts_before)
                            $fatal(1,"old response hold falsely completed drain");
                    end
                    hold_response=0;wait(responses_consumed>response_before);
                    wait(dut.memory_quiet);
                    if(dut.memory_read_pending)$fatal(1,"quiet preceded old response consumption");
                end
            join
            if(cancel_only)begin
                await_quiet();
                if(path_restarts!=restarts_before+1 || !cancelled || tf_active)
                    $fatal(1,"cancel did not clear once and remain stopped");
                cancel_drain_tests=cancel_drain_tests+1;
                @(negedge source_clk);runtime_rate=1;runtime_epoch=runtime_epoch+1;begin_file(1);
            end
            await_frames(64);tests=tests+1;
        end
    endtask
    // Emit the old response on the same memory edge that closes the gate.
    // The service consumes it on the adjacent edge, then registers quiet on
    // the following edge; a combinational or premature ACK fails explicitly.
    task adjacent_response_restart;
        integer response_before,restarts_before;
        begin
            checking=0;@(negedge source_clk);cancel=1;@(negedge source_clk);cancel=0;await_quiet();
            checking=0;hold_response=1;stall_reads=0;response_before=responses_consumed;
            @(negedge source_clk);runtime_rate=0;runtime_epoch=runtime_epoch+1;track=0;pulse_restart();
            wait(read_pending);wait(response_delay==0);restarts_before=path_restarts;
            fork
                begin begin_file(1);end
                begin
                    wait(dut.memory_gate_sync[0] && !dut.memory_gate);
                    @(negedge memory_clk);hold_response=0;
                    @(posedge memory_clk);#0.001;
                    if(!dut.memory_gate || !response || !dut.memory_read_pending || dut.memory_quiet)
                        $fatal(1,"response/gate adjacent boundary was not exercised");
                    runtime_rate=1;runtime_epoch=runtime_epoch+1;
                    @(posedge memory_clk);#0.001;
                    if(dut.memory_read_pending || dut.memory_quiet || responses_consumed!=response_before+1 || path_restarts!=restarts_before)
                        $fatal(1,"response edge acknowledged quiet before registered aggregate");
                    @(posedge memory_clk);#0.001;
                    if(!dut.memory_quiet || path_restarts!=restarts_before)
                        $fatal(1,"registered quiet did not follow drained response");
                    adjacent_drain_tests=adjacent_drain_tests+1;
                end
            join
            await_frames(64);tests=tests+1;
        end
    endtask
    integer accepted_before,frames_before;
    reg [31:0] generation_before;
    initial begin if(RUN_SCENARIOS)begin
        repeat(6)@(negedge source_clk);rst_n=1;repeat(30)@(negedge source_clk);
        begin_file(0);await_frames(10);
        @(negedge source_clk);run=0;wait(paused);repeat(5)@(negedge compute_clk);
        accepted_before=accepted;frames_before=session_index;generation_before=source_generation;
        repeat(500)@(negedge compute_clk);
        if(accepted!=accepted_before || session_index!=frames_before || source_generation!=generation_before || !busy50 || !tf_busy || quiet)
            $fatal(1,"pause lost decoder/FIFO position or permitted switch");
        @(negedge source_clk);run=1;await_frames(64);wait(eof_seen);
        if(!busy50 || !tf_active || quiet)$fatal(1,"EOF falsely claimed drained/complete");tests=tests+1;
        @(negedge source_clk);cancel=1;@(negedge source_clk);cancel=0;await_quiet();
        if(!cancelled)$fatal(1,"cancel was not reported");
        // Actual 44.1 header with active 48k must fail without rewriting rate.
        @(negedge source_clk);track=1;pulse_restart();fail_expected(1);
        @(negedge source_clk);reader_restart=1;@(negedge source_clk);reader_restart=0;
        repeat(100)@(negedge source_clk);if(!failed || tf_active || busy50)$fatal(1,"automatic reader retry rearmed failed TF");
        runtime_rate=1;runtime_epoch=5;begin_file(1);await_frames(64);tests=tests+1;
        // Epoch identity is opaque (including zero), not guessed +1 or remapped.
        begin_file(1);await_frames(8);@(negedge source_clk);runtime_epoch=0;fail_expected(6);
        begin_file(1);await_frames(64);tests=tests+1;
        @(negedge source_clk);cancel=1;@(negedge source_clk);cancel=0;await_quiet();
        @(negedge source_clk);track=2;pulse_restart();fail_expected(1);
        runtime_rate=0;runtime_epoch=9;@(negedge source_clk);track=3;pulse_restart();fail_expected(2);
        begin_file(0);await_frames(5);
        @(negedge source_clk);force dut.path.g_runtime_dma.u_dma.capacity_error=1'b1;
        fail_expected(3);release dut.path.g_runtime_dma.u_dma.capacity_error;
        begin_file(0);await_frames(5);@(negedge source_clk);dut.path.u_file_reader.present=0;
        fail_expected(4);dut.path.u_file_reader.present=1;
        repeat(100)@(negedge source_clk);if(!failed || tf_active)$fatal(1,"card return silently rearmed");
        begin_file(0);await_frames(5);@(negedge source_clk);runtime_valid=0;fail_expected(5);runtime_valid=1;
        begin_file(0);await_frames(5);@(negedge source_clk);transport_error=1;fail_expected(7);transport_error=0;
        // The old accepted read returns after a restart request. It must drain
        // before the same legacy DMA state machine can acquire the new file.
        extra_response_delay=80;checking=0;@(negedge source_clk);track=0;pulse_restart();wait(read_pending);
        runtime_rate=1;runtime_epoch=10;begin_file(1);extra_response_delay=0;
        await_frames(64);tests=tests+1;
        queued_read_drain(0);queued_read_drain(1);adjacent_response_restart();
        // A stopped compute clock cannot ACK cancellation. Timeout reports a
        // terminal failure but retains busy until the real quiet proof returns.
        begin_file(1);await_frames(3);checking=0;compute_run=0;
        @(negedge source_clk);cancel=1;@(negedge source_clk);cancel=0;
        repeat(1100)@(negedge source_clk);
        if(!failed || failure!=8 || !busy50 || quiet50)$fatal(1,"lost-compute quiet timeout falsely released media");
        compute_run=1;fail_expected(8);
        runtime_rate=0;runtime_epoch=11;
        // Last cancel must revoke the held route when source immediately stops.
        for(integer polarity=0;polarity<2;polarity=polarity+1)begin
            begin_file(0);await_frames(3);checking=0;
            @(negedge source_clk);cancel=1;@(posedge source_clk);#1;
            if(polarity==0)begin @(negedge source_clk);#1;end
            source_run=0;repeat(100)@(negedge compute_clk);
            if(source_clk!==1'(polarity) || tf_active || !dut.bridge_quiet || !tf_busy)
                $fatal(1,"last cancel lost with stopped source high=%0d",polarity);
            stop_checks=stop_checks+1;source_run=1;@(negedge source_clk);cancel=0;await_quiet();
        end
        // Analysis still consumes the same real path, exclusively and with its
        // original backpressure. It never enables physical TF or blocks synth.
        @(negedge source_clk);mode=0;track=0;analysis_enable=1;analysis_ready=0;reader_restart=1;
        @(negedge source_clk);reader_restart=0;await_quiet();
        wait(dut.format_ready_o);repeat(100)@(negedge source_clk);
        if(analysis_frames!=0 || tf_active || busy50)$fatal(1,"analysis hold/ownership changed");
        analysis_ready=1;wait(analysis_frames==64);tests=tests+1;
        @(negedge source_clk);reader_restart=1;@(negedge source_clk);reader_restart=0;
        wait(analysis_frames==128);tests=tests+1;
        // The real scope transport distinguishes entering TF from canceling
        // analysis, and distinguishes a user restart from card-return retry.
        checking=1;expected_track=0;session_index=0;
        @(negedge source_clk);analysis_enable=0;use_scope=1;
        scope_command(1,1,0);wait(tf_active);await_frames(64);
        if(scope_explicit_count!=1 || scope_file_cancel_count!=0)$fatal(1,"TF entry was canceled or lacked explicit provenance");
        session_index=0;scope_command(2,1,3);await_frames(64);
        if(scope_explicit_count!=2)$fatal(1,"user restart lacked provenance");
        dut.path.u_file_reader.present=0;fail_expected(4);dut.path.u_file_reader.present=1;
        repeat(200)@(negedge source_clk);
        if(scope_auto_count==0 || scope_explicit_count!=2 || !failed || tf_active || busy50)$fatal(1,"card return silently rearmed TF");
        checking=1;session_index=0;scope_command(3,1,3);await_frames(64);
        scope_command(4,0,0);await_quiet();
        if(scope_explicit_count!=3 || scope_file_cancel_count!=1)$fatal(1,"scope exit/rearm provenance mismatch");
        tests=tests+3;
        if(ddr_writes==0 || ddr_reads==0 || pause_zeros==0 || failures<7 || stop_checks!=2 || read_drain_wait_cycles==0)$fatal(1,"missing coverage");
        if(USE_COMMAND_BUFFER && (queued_accepts==0 || downstream_stalls==0 || queued_drain_tests!=2))$fatal(1,"buffer was not exercised");
        if(quiet_source_checks==0 || quiet_source_changes==0 || adjacent_drain_tests!=1 || cancel_drain_tests!=1)
            $fatal(1,"missing registered quiet/drain boundary coverage");
        $display("PASS tf_runtime_service: buffered=%0d cases=%0d delivered=%0d pause_zero_frames=%0d analysis_frames=%0d ddr_writes=%0d ddr_reads=%0d failures=%0d invalidates=%0d stopped_source=%0d stale=%0d discarded=%0d read_drain_wait_cycles=%0d queued_accepts=%0d downstream_stalls=%0d scope_compares=%0d scope_explicit=%0d scope_auto=%0d quiet_source_checks=%0d quiet_source_changes=%0d queued_drain_tests=%0d adjacent_drain_tests=%0d cancel_drain_tests=%0d",USE_COMMAND_BUFFER,tests,delivered,pause_zeros,analysis_frames,ddr_writes,ddr_reads,failures,invalidates,stop_checks,stale,discarded,read_drain_wait_cycles,queued_accepts,downstream_stalls,scope_compares,scope_explicit_count,scope_auto_count,quiet_source_checks,quiet_source_changes,queued_drain_tests,adjacent_drain_tests,cancel_drain_tests);
        $finish;
    end end
    initial begin #(OVERALL_TIMEOUT_NS);$fatal(1,"overall TF service timeout state=%0d index=%0d failed=%b code=%0d track=%0d",dut.state,session_index,failed,failure,track);end
endmodule
