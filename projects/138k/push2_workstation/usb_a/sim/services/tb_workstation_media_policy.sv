`timescale 1ns/1ps
// Real held-word APB mailboxes, unique rate core, REC FIFO and score player.
// TF fixture provides explicit late completion/failure; its drain is tested by
// the TF owner's own regression, not inferred here from a falling busy bit.
module tb_workstation_media_policy;
    reg clk50=0,compute=0,pclk=0,board_n=0,cpu_n=0;
    always #10 clk50=~clk50;
    always #6.510416667 compute=~compute;
    real bus_phase;
    initial begin
        if(!$value$plusargs("BUS_PHASE=%f",bus_phase))bus_phase=3.7;
        #(bus_phase);forever #13.7 pclk=~pclk;
    end
    reg psel=0,penable=0,pwrite=0;
    reg [12:0] paddr=0;reg [31:0] pwdata=0;reg [3:0] pstrb=15;
    wire pready,pslverr;wire [31:0] prdata;
    wire [1:0] ready,error;wire [31:0] read_data[0:1];
    wire rec_reset,rec_valid_cmd,rec_ready_cmd,rec_write_cmd,rec_error_cmd;
    wire [11:0] rec_addr;wire [31:0] rec_data,rec_response;wire [3:0] rec_strobes;
    wire clock_reset,clock_valid_cmd,clock_ready_cmd,clock_write_cmd,clock_error_cmd;
    wire [11:0] clock_addr;wire [31:0] clock_data,clock_response;wire [3:0] clock_strobes;
    assign pready=ready[paddr[12]];assign pslverr=error[paddr[12]];assign prdata=read_data[paddr[12]];
    gw138k_apb_cdc rec_mailbox(.reset_n(cpu_n),.pclk,.audio_clk(compute),.psel(psel&&!paddr[12]),
        .penable,.pwrite,.paddr(paddr[11:0]),.pwdata,.pstrb,.pready(ready[0]),.pslverr(error[0]),.prdata(read_data[0]),
        .command_reset_n(rec_reset),.command_valid(rec_valid_cmd),.command_ready(rec_ready_cmd),
        .command_write(rec_write_cmd),.command_address(rec_addr),.command_data(rec_data),.command_strobes(rec_strobes),
        .response_data(rec_response),.response_error(rec_error_cmd));
    gw138k_apb_cdc clock_mailbox(.reset_n(cpu_n),.pclk,.audio_clk(clk50),.psel(psel&&paddr[12]),
        .penable,.pwrite,.paddr(paddr[11:0]),.pwdata,.pstrb,.pready(ready[1]),.pslverr(error[1]),.prdata(read_data[1]),
        .command_reset_n(clock_reset),.command_valid(clock_valid_cmd),.command_ready(clock_ready_cmd),
        .command_write(clock_write_cmd),.command_address(clock_addr),.command_data(clock_data),.command_strobes(clock_strobes),
        .response_data(clock_response),.response_error(clock_error_cmd));
    wire req,target,recover,core_ready,core_busy,core_fault,core_accepted,core_applied,core_rejected,core_failed;
    wire rate44,active_valid;wire [31:0] epoch;wire [2:0] reject_code;wire [3:0] fault_code;
    wire media_request,media_hold,media_ready,media_done,media_failed;wire [3:0] media_failure;
    reg platform_permit=1,tf_active=0,tf_busy=0,tf_done=0,tf_failed=0,tf_quiet=1;
    reg [1:0] qualified=3;
    reg [3:0] tf_code=8;
    reg tf_pending=0;
    wire tf_request,local_request,local_hold,local_done,local_failed;
    wire rec_enabled,rec_seal,seal_done,seal_failed,start_ready;
    wire rec_packet_valid,rec_packet_ready,rec_failed;wire [95:0] rec_packet;wire [2:0] rec_failure;
    wire [31:0] rec_drop,object_id,object_rate,object_epoch,object_frames,seal_count;
    wire [5:0] object_status;wire [2:0] object_failure,seal_status;
    wire score_write,score_start,score_stop,score_running,score_done,score_failed,score_cancelled;
    wire [7:0] score_addr;wire [63:0] score_data;wire [8:0] score_length;wire [31:0] leds,score_frame;
    reg frame_valid=0,frame_error=0,frame_change=0,frame_gap=0,loss=0;
    reg signed [31:0] left=0,right=0;
    reg media_busy_compute;
    (* ASYNC_REG="TRUE" *) reg [2:0] media_busy50;
    always @(posedge compute or negedge board_n)
        if(!board_n)media_busy_compute<=1;else media_busy_compute<=rec_enabled||score_running||tf_active||tf_busy;
    always @(posedge clk50 or posedge media_busy_compute or negedge board_n)
        if(!board_n)media_busy50<=7;else if(media_busy_compute)media_busy50<=7;else media_busy50<={media_busy50[1:0],1'b0};
    wire actual_permit=platform_permit&&!media_busy50[2];
    workstation_audio_clock_service #(.ENABLE_MEDIA_POLICY(1),.ACCEPT_TIMEOUT_CYCLES(16),
        .RESULT_TIMEOUT_CYCLES(192),.MEDIA_TIMEOUT_CYCLES(1000)) clock_service(
        .clk_i(clk50),.reset_ni(clock_reset),.command_valid_i(clock_valid_cmd),.command_write_i(clock_write_cmd),
        .command_address_i(clock_addr),.command_data_i(clock_data),.command_strobes_i(clock_strobes),
        .command_ready_o(clock_ready_cmd),.response_data_o(clock_response),.response_error_o(clock_error_cmd),
        .switch_permit_i(platform_permit),.core_request_ready_i(core_ready),.core_busy_i(core_busy),.core_fault_i(core_fault),
        .core_dsp_fault_i(1'b0),.core_accepted_i(core_accepted),.core_applied_i(core_applied),.core_rejected_i(core_rejected),
        .core_policy_rejected_i(1'b0),.core_failed_i(core_failed),.core_reject_code_i(reject_code),.core_fault_code_i(fault_code),
        .core_active_44k1_i(rate44),.core_active_valid_i(active_valid),.core_stream_epoch_i(epoch),.core_source_qualified_i(qualified),
        .request_o(req),.request_44k1_o(target),.recover_o(recover),.media_stop_request_o(media_request),.media_stop_hold_o(media_hold),
        .media_stop_ready_i(media_ready),.media_stop_done_i(media_done),.media_stop_failed_i(media_failed),.media_stop_failure_code_i(media_failure));
    workstation_sample_rate_switch #(.TIMEOUT_CYCLES(96)) core(
        .clk_i(clk50),.rst_ni(board_n),.request_i(req&&actual_permit),.request_44k1_i(target),.recover_i(recover),
        .source_qualified_i(qualified),.frame_quiescent_i(1'b1),.selected_clock_stopped_low_i(1'b1),
        .selected_clock_qualified_i(1'b1),.prefill_ready_i(1'b1),.output_running_i(1'b1),
        .request_ready_o(core_ready),.busy_o(core_busy),.fault_o(core_fault),.accepted_o(core_accepted),
        .applied_o(core_applied),.rejected_o(core_rejected),.failed_o(core_failed),.reject_code_o(reject_code),.fault_code_o(fault_code),
        .quiesce_o(),.dac_mute_o(),.stream_flush_o(),.audio_reset_no(),.clock_monitor_restart_o(),.clock_select_o(),
        .active_44k1_o(rate44),.active_valid_o(active_valid),.stream_epoch_o(epoch),.staged_44k1_o(),.staged_epoch_o());
    workstation_runtime_media_stop_bridge #(.ENABLE(1)) media(
        .reset_ni(board_n),.clk_50m_i(clk50),.compute_clk_i(compute),.owner_reset_ni(rec_reset),
        .request_i(media_request),.hold_i(media_hold),.local_request_o(local_request),.local_hold_o(local_hold),
        .local_done_i(local_done),.local_failed_i(local_failed),.tf_stop_request_o(tf_request),
        .tf_stop_pending_i(tf_pending),.tf_stop_done_i(tf_done),.tf_stop_failed_i(tf_failed),.tf_stop_failure_code_i(tf_code),
        .media_quiet_i(!media_busy50[2]&&tf_quiet),.ready_o(media_ready),.done_o(media_done),.failed_o(media_failed),.failure_code_o(media_failure));
    gw138k_controlled_services #(.ENABLE_MEDIA_POLICY(1)) services(
        .clk(compute),.reset_n(rec_reset),.command_valid(rec_valid_cmd),.command_write(rec_write_cmd),
        .command_address(rec_addr),.command_data(rec_data),.command_strobes(rec_strobes),.command_ready(rec_ready_cmd),
        .response_data(rec_response),.response_error(rec_error_cmd),.cpu_event_valid(),.cpu_event(),.cpu_event_ready(1'b1),
        .panel_event_valid(1'b0),.panel_command(7'd0),.panel_event_ready(),
        .control_state(32'd0),.control_pitch(32'd0),.control_options(32'd0),.applied_events(32'd0),.pc_health(32'd0),
        .held_notes(128'd0),.sample_valid(frame_valid),.active_mask(32'd0),.deadline_miss(32'd0),.midi_overflow(32'd0),
        .note_drop(32'd0),.underrun_count(32'd0),.midi_cdc_drop(32'd0),.observation_drop(32'd0),.record_drop(rec_drop),
        .record_enable(rec_enabled),.snap_status(),.snap_left(),.snap_right(),.snap_sequence(),
        .record_valid(rec_packet_valid),.record_packet(rec_packet),.record_ready(rec_packet_ready),
        .score_write,.score_start,.score_stop,.score_address(score_addr),.score_data,.score_length,
        .score_running,.score_done,.led_mask(leds),.score_frame,
        .media_stop_request_i(local_request),.media_stop_hold_i(local_hold),.record_storage_reset_ni(board_n),
        .record_seal_request_o(rec_seal),.record_seal_done_i(seal_done),.record_seal_failed_i(seal_failed),.record_start_ready_i(start_ready),
        .record_object_id_i(object_id),.record_object_rate_i(object_rate),.record_object_epoch_i(object_epoch),.record_object_frames_i(object_frames),
        .record_object_status_i(object_status),.record_object_failure_i(object_failure),.record_seal_status_i(seal_status),.record_seal_count_i(seal_count),
        .score_cancelled_i(score_cancelled),.score_failed_i(score_failed),.media_stop_done_o(local_done),.media_stop_failed_o(local_failed));
    workstation_observation_consumers #(.RECORD_ADDRESS_BITS(2),.ENABLE_MEDIA_POLICY(1)) consumers(
        .clk_i(compute),.rst_ni(board_n),.frame_valid_i(frame_valid),.frame_44k1_i(rate44),.frame_error_i(frame_error),
        .stream_change_i(frame_change),.sequence_gap_i(frame_gap),.observation_loss_i(loss),.media_switch_busy_i(core_busy),
        .frame_epoch_i(epoch),.left_i(left),.right_i(right),.record_enable_i(rec_enabled),.record_ready_i(rec_packet_ready),
        .record_valid_o(rec_packet_valid),.record_packet_o(rec_packet),.record_failed_o(rec_failed),.record_failure_code_o(rec_failure),
        .record_drop_o(rec_drop),.fft_valid_o(),.fft_bin_o(),.fft_real_o(),.fft_imag_o(),.fft_frame_o(),
        .fft_44k1_o(),.fft_context_valid_o(),.fft_epoch_o(),.fft_discard_count_o(),
        .score_write_i(score_write),.score_address_i(score_addr),.score_data_i(score_data),.score_length_i(score_length),
        .score_start_i(score_start),.score_stop_i(score_stop),.score_running_o(score_running),.score_done_o(score_done),
        .led_mask_o(leds),.score_frame_o(score_frame),.score_failed_o(score_failed),.record_seal_i(rec_seal),
        .record_seal_done_o(seal_done),.record_seal_failed_o(seal_failed),.record_start_ready_o(start_ready),
        .record_object_id_o(object_id),.record_object_rate_o(object_rate),.record_object_epoch_o(object_epoch),.record_object_frames_o(object_frames),
        .record_object_status_o(object_status),.record_object_failure_o(object_failure),.record_seal_status_o(seal_status),
        .record_seal_count_o(seal_count),.score_cancelled_o(score_cancelled));
    integer checks=0,requests=0,tf_requests=0,media_completions=0,media_failures=0,seal_completions=0;
    integer accepted_frames=0;reg previous_request=0;reg [31:0] v,old_id,old_epoch,snapshot_left;
    always @(posedge clk50)if(board_n)begin
        if(req)begin
            requests=requests+1;
            if(previous_request || !actual_permit || rec_enabled || score_running || tf_busy || tf_active)
                $fatal(1,"core pulse preceded actual media stop");
        end
        previous_request=req;
        if(tf_request)begin
            tf_requests=tf_requests+1;tf_pending=1;
            if(rec_enabled || score_running || !seal_status[1])$fatal(1,"TF stop preceded local seal/score completion");
        end
        if(media_done)media_completions=media_completions+1;
        if(media_failed)media_failures=media_failures+1;
    end
    always @(posedge compute)if(board_n)begin
        if(consumers.record_captured)accepted_frames=accepted_frames+1;
        if(seal_done || seal_failed)seal_completions=seal_completions+1;
    end
    task clocks(input integer n);begin repeat(n)@(negedge clk50);end endtask
    task sample(input integer x);begin
        @(negedge compute);frame_valid=1;left=32'(x);right=-32'(x);
        @(negedge compute);frame_valid=0;repeat(3)@(negedge compute);
    end endtask
    task bus(input bit wr,input [12:0] addr,input [31:0] data,input bit expected_error,output [31:0] value);
        integer n;
        begin
            @(negedge pclk);paddr=addr;pwdata=data;pwrite=wr;pstrb=15;psel=1;penable=0;
            @(negedge pclk);penable=1;n=0;@(posedge pclk);
            while(!pready)begin @(posedge pclk);n=n+1;if(n>500)$fatal(1,"bus timeout %h",addr);end
            if(pslverr!==expected_error)$fatal(1,"bus error addr=%h got=%b expected=%b",addr,pslverr,expected_error);
            value=prdata;
            @(negedge pclk);psel=0;penable=0;repeat(2)@(negedge pclk);
        end
    endtask
    task wr(input [12:0] addr,input [31:0] data,input bit err);begin bus(1,addr,data,err,v);end endtask
    task rd(input [12:0] addr,input [31:0] value);begin
        bus(0,addr,0,0,v);if(v!==value)$fatal(1,"read addr=%h got=%h expected=%h",addr,v,value);
    end endtask
    task wait_tf(input integer expected);begin
        for(integer i=0;i<300 && tf_requests!=expected;i=i+1)clocks(1);
        if(tf_requests!=expected)$fatal(1,"local stop never reached TF");
    end endtask
    task tf_complete;begin
        @(negedge clk50);tf_active=0;tf_busy=0;tf_quiet=1;clocks(8);tf_pending=0;tf_done=1;clocks(1);tf_done=0;clocks(24);
    end endtask
    task wait_result(input integer code);begin
        for(integer i=0;i<1200 && clock_service.phase!=0;i=i+1)clocks(1);
        if(clock_service.phase!=0)$fatal(1,"media command failed to terminate");
        rd(13'h101c,32'(code));
    end endtask
    task prepare_score(input integer time0);begin
        wr(13'h1120,1,1); // Clock page is read-only, cannot masquerade as score write.
        wr(13'h0120,1,0);wr(13'h0100,0,0);wr(13'h0104,32'(time0),0);
        wr(13'h0108,32'ha5,0);wr(13'h010c,1,0);wr(13'h0110,1,0);
    end endtask
    initial begin
        clocks(5);board_n=1;cpu_n=1;clocks(32);wait(core_ready);sample(0);
        rd(13'h1004,32'h00010017);rd(13'h0008,127);old_epoch=epoch;
        // Full queue plus a POP-owned snapshot. Accepted count must include
        // all captured packets, including the snapshot outside the FIFO.
        prepare_score(1000);wr(13'h0114,1,0);if(!score_running)$fatal(1,"score not running");
        wr(13'h0080,1,0);for(integer i=0;i<4;i=i+1)sample(100+i);
        wr(13'h0088,1,0);bus(0,13'h0090,0,0,snapshot_left);sample(104);
        if(object_frames!=5 || accepted_frames!=5)$fatal(1,"exact accepted packet count");
        tf_active=1;tf_busy=1;tf_quiet=0;clocks(3);
        wr(13'h1008,1,0);old_id=object_id;wait_tf(1);
        if(req || rec_enabled || !object_status[1] || score_running || !score_cancelled || score_done)
            $fatal(1,"planned media stop did not retain sealed/cancelled terminal states");
        rd(13'h009c,27);wr(13'h0080,1,1);wr(13'h0114,1,1);wr(13'h1008,0,1);
        // Busy becoming false and cancel acceptance are insufficient proof.
        tf_active=0;tf_busy=0;tf_quiet=1;clocks(30);
        if(requests!=0 || !media_hold)$fatal(1,"busy drop substituted for stop_done");
        tf_complete();wait_result(1);if(!rate44 || epoch!=old_epoch+1 || requests!=1)$fatal(1,"unique rate command missing");
        rd(13'h00a4,48000);rd(13'h00a8,old_epoch);rd(13'h00ac,5);rd(13'h00a0,old_id);rd(13'h0090,snapshot_left);
        rd(13'h0130,1);checks=checks+1;
        // The sealed object and POP snapshot survive a CPU-only reset, then
        // all remaining packets can be downloaded at the new system rate.
        cpu_n=0;clocks(6);cpu_n=1;clocks(20);rd(13'h0090,snapshot_left);rd(13'h00ac,5);rd(13'h00a4,48000);
        wr(13'h0080,1,1);wr(13'h0098,1,0);
        for(integer i=0;i<4;i=i+1)begin wr(13'h0088,1,0);wr(13'h0098,1,0);end
        if(rec_packet_valid)$fatal(1,"sealed FIFO download incomplete");
        wr(13'h0080,1,1);sample(0);wr(13'h0080,1,1);checks=checks+1;
        // Empty recording/media stop and reverse rate use exactly one core
        // request; no MIDI event/PANIC is synthesized by this service.
        wr(13'h1008,0,0);wait_tf(2);tf_complete();wait_result(1);sample(0);
        if(rate44 || requests!=2)$fatal(1,"empty stop failed");checks=checks+1;
        // A genuine empty recording is a sealed zero-frame object, not an
        // unsupported mixed-rate object or a silently discarded recording.
        wr(13'h0080,1,0);wr(13'h1008,1,0);wait_tf(3);tf_complete();wait_result(1);
        rd(13'h00ac,0);rd(13'h00a4,48000);
        if(!object_status[1] || object_status[2] || requests!=3)$fatal(1,"empty recording seal failed");
        wr(13'h1008,0,0);wait_tf(4);tf_complete();wait_result(1);sample(0);checks=checks+1;
        // CPU reset during a local transaction reissues seal after reset.
        // Resetting the observer cannot issue the abandoned rate request.
        wr(13'h0080,1,0);sample(222);tf_busy=1;tf_quiet=0;
        @(negedge pclk);paddr=13'h1008;pwdata=1;pwrite=1;psel=1;penable=0;
        @(negedge pclk);penable=1;
        wait(local_request);@(negedge compute);cpu_n=0;psel=0;penable=0;
        clocks(8);cpu_n=1;
        wait_tf(5);tf_complete();clocks(32);
        if(requests!=4 || media.local_hold_o || rec_enabled || !seal_status[1])$fatal(1,"CPU reset abandoned media fence");
        rd(13'h00ac,1);rd(13'h00a4,48000);checks=checks+1;
        // Preserve snapshot across CPU reset even with an in-flight APB POP.
        @(negedge pclk);paddr=13'h0088;pwdata=1;pwrite=1;psel=1;penable=0;
        @(negedge pclk);penable=1;
        wait(rec_packet_ready);@(posedge compute);#1;
        if(!services.record_snapshot_valid)$fatal(1,"in-flight POP did not transfer ownership");
        snapshot_left=services.record_snapshot[63:32];
        cpu_n=0;psel=0;penable=0;clocks(5);cpu_n=1;clocks(20);
        rd(13'h0090,snapshot_left);wr(13'h0098,1,0);
        // Overflow is an explicit failed object and a failed media transaction,
        // while TF still must actually finish its stop before that result.
        wr(13'h0080,1,0);for(integer i=0;i<5;i=i+1)sample(300+i);
        if(!rec_failed || object_failure!=6 || object_frames!=4)$fatal(1,"overflow metadata/count");
        wr(13'h1008,1,0);wait_tf(6);if(clock_service.phase==0)$fatal(1,"REC failure bypassed TF stop");
        tf_complete();wait_result(8);rd(13'h1068,9);
        if(requests!=4 || !object_status[2])$fatal(1,"failed REC caused a rate pulse");checks=checks+1;
        // TF failure and lost stop result are distinct queryable outcomes.
        wr(13'h1008,1,0);wait_tf(7);@(negedge clk50);tf_failed=1;clocks(1);tf_failed=0;
        wait_result(8);rd(13'h1068,8);if(requests!=4)$fatal(1,"failed TF caused rate pulse");
        clocks(12);if(!local_hold || media_ready)$fatal(1,"failed TF released before actual pending cleanup");
        wr(13'h1008,1,1);tf_pending=0;clocks(12);
        if(local_hold || !media_ready)$fatal(1,"completed failed TF cleanup did not rearm");checks=checks+1;
        wr(13'h1008,1,0);wait_tf(8);wait_result(9);
        if(requests!=4 || !local_hold)$fatal(1,"timed-out backend released its unfinished fence");
        wr(13'h1008,1,1);rd(13'h104c,14);
        tf_complete();clocks(12);if(local_hold)$fatal(1,"late real stop did not release fence");checks=checks+1;
        // Stop completion still cannot authorize a switch after the platform
        // permit or the target clock qualification has changed.
        wr(13'h1008,1,0);wait_tf(9);platform_permit=0;tf_complete();wait_result(10);
        if(requests!=4)$fatal(1,"post-stop platform gate escaped");platform_permit=1;checks=checks+1;
        wr(13'h1008,1,0);wait_tf(10);qualified=1;tf_complete();wait_result(10);
        if(requests!=4)$fatal(1,"post-stop target qualification escaped");qualified=3;checks=checks+1;
        // A same-rate no-op does not seal/cancel media again.
        old_id=32'(tf_requests);wr(13'h1008,0,0);wait_result(1);
        if(tf_requests!=integer'(old_id) || requests!=5)$fatal(1,"same-rate noop acquired media");checks=checks+1;
        $display("PASS media_policy: checks=%0d core_requests=%0d tf_stop_requests=%0d media_done=%0d media_failed=%0d seal_completions=%0d captured=%0d",checks,requests,tf_requests,media_completions,media_failures,seal_completions,accepted_frames);
        $finish;
    end
    initial begin #2000000;$fatal(1,"media policy watchdog");end
endmodule
