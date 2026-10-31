`timescale 1ns/1ps
module tb_workstation_media_hold_fence;
    reg control_clk=0,compute_clk=0,reset_n=1,owner_n=1;
    always #10 control_clk=~control_clk;
    reg request=0,hold=0,local_done=0,local_failed=0;
    reg tf_pending=0,tf_done=0,tf_failed=0,quiet=0;
    reg [3:0] tf_code=7;
    wire local_request,local_hold,tf_request,ready,done,failed;
    wire [3:0] failure;
`ifdef MEDIA_HOLD_MAPPED
    workstation_media_hold_probe dut(
`else
    workstation_runtime_media_stop_bridge #(.ENABLE(1)) dut(
.control_reset_ni(1'b1),.compute_reset_ni(1'b1),`endif
        .reset_ni(reset_n),.clk_50m_i(control_clk),.compute_clk_i(compute_clk),.owner_reset_ni(owner_n),
        .request_i(request),.hold_i(hold),.local_request_o(local_request),.local_hold_o(local_hold),
        .local_done_i(local_done),.local_failed_i(local_failed),.tf_stop_request_o(tf_request),
        .tf_stop_pending_i(tf_pending),.tf_stop_done_i(tf_done),.tf_stop_failed_i(tf_failed),
        .tf_stop_failure_code_i(tf_code),.media_quiet_i(quiet),.ready_o(ready),.done_o(done),.failed_o(failed),.failure_code_o(failure));
    wire off_local_hold,off_ready,off_done,off_failed,off_local_request,off_tf_request;
    workstation_runtime_media_stop_bridge #(.ENABLE(0)) off(
        .control_reset_ni(1'b1),.compute_reset_ni(1'b1),.reset_ni(reset_n),.clk_50m_i(control_clk),.compute_clk_i(compute_clk),.owner_reset_ni(owner_n),
        .request_i(request),.hold_i(hold),.local_request_o(off_local_request),.local_hold_o(off_local_hold),
        .local_done_i(local_done),.local_failed_i(local_failed),.tf_stop_request_o(off_tf_request),
        .tf_stop_pending_i(tf_pending),.tf_stop_done_i(tf_done),.tf_stop_failed_i(tf_failed),
        .tf_stop_failure_code_i(tf_code),.media_quiet_i(quiet),.ready_o(off_ready),.done_o(off_done),.failed_o(off_failed),.failure_code_o());
    // Actual sole REC_ENABLE owner checks a START on the second release edge.
    // This small test supplies recorder completion; the full runtime/TF/BLE
    // regression separately checks the actual FIFO, CRC and TF terminal owners.
    reg command_valid=0;wire response_error,record_enable;
    gw138k_controlled_services #(.ENABLE_MEDIA_POLICY(1)) service(
        .clk(compute_clk),.reset_n(reset_n&&owner_n),.command_valid,.command_write(1'b1),
        .command_address(12'h080),.command_data(32'd1),.command_strobes(4'hf),
        .command_ready(),.response_data(),.response_error,.cpu_event_valid(),.cpu_event(),.cpu_event_ready(1'b1),
        .panel_event_valid(1'b0),.panel_command(7'd0),.panel_event_ready(),
        .control_state(32'd0),.control_pitch(32'd0),.control_options(32'd0),.applied_events(32'd0),.pc_health(32'd0),
        .held_notes(128'd0),.sample_valid(1'b0),.active_mask(32'd0),.deadline_miss(32'd0),.midi_overflow(32'd0),
        .note_drop(32'd0),.underrun_count(32'd0),.midi_cdc_drop(32'd0),.observation_drop(32'd0),.record_drop(32'd0),
        .record_enable,.snap_status(),.snap_left(),.snap_right(),.snap_sequence(),.record_valid(1'b0),
        .record_packet(96'd0),.record_ready(),.score_write(),.score_start(),.score_stop(),.score_address(),.score_data(),
        .score_length(),.score_running(1'b0),.score_done(1'b0),.led_mask(32'd0),.score_frame(32'd0),
        .media_stop_request_i(local_request),.media_stop_hold_i(local_hold),.record_storage_reset_ni(reset_n),
        .record_seal_request_o(),.record_seal_done_i(1'b1),.record_seal_failed_i(1'b0),.record_start_ready_i(1'b1),
        .record_object_id_i(32'd0),.record_object_rate_i(32'd48000),.record_object_epoch_i(32'd1),.record_object_frames_i(32'd0),
        .record_object_status_i(6'd0),.record_object_failure_i(3'd0),.record_seal_status_i(3'd0),.record_seal_count_i(32'd0),
        .score_cancelled_i(1'b1),.score_failed_i(1'b0),.media_stop_done_o(),.media_stop_failed_o());
    integer cases=0,local_requests=0,tf_requests=0,done_count=0,failed_count=0,compute_edges=0;
    always @(negedge compute_clk)if(reset_n&&local_request)local_requests=local_requests+1;
    always @(negedge control_clk)if(reset_n)begin
        if(tf_request)tf_requests=tf_requests+1;
        if(done)done_count=done_count+1;
        if(failed)failed_count=failed_count+1;
        if(off_local_hold||off_ready||off_done||off_failed||off_local_request||off_tf_request)$fatal(1,"default-off bridge emitted an event");
    end
    task clocks(input integer n);begin repeat(n)@(negedge control_clk);#0.1;end endtask
    task edge_compute;begin #3.1;compute_clk=1;compute_edges=compute_edges+1;#0.2;compute_clk=0;#0.2;end endtask
    task release_check;begin
        clocks(3);if(local_hold!==1)$fatal(1,"hold released without a compute edge");
        edge_compute();if(local_hold!==1)$fatal(1,"hold release used fewer than two compute edges");
        edge_compute();if(local_hold!==0)$fatal(1,"hold did not release on second compute edge");
    end endtask
    task reset_case;begin
        #1.3;reset_n=0;owner_n=1;request=0;hold=0;local_done=0;local_failed=0;
        tf_pending=0;tf_done=0;tf_failed=0;quiet=0;command_valid=0;
        #0.2;if(local_hold!==1)$fatal(1,"common reset did not asynchronously assert conservative hold");
        clocks(2);#1.1;reset_n=1;release_check();
    end endtask
    task begin_stop;begin
        @(negedge control_clk);hold=1;request=1;
        @(negedge control_clk);request=0;#0.2;
        if(local_hold!==1)$fatal(1,"asynchronous media hold waited for a stopped compute clock");
    end endtask
    task acknowledge_local(input bit bad);begin
        local_failed=bad;local_done=!bad;edge_compute();local_failed=0;local_done=0;
        wait(tf_request);@(negedge control_clk);#0.2;tf_pending=1;
    end endtask
    integer old_local,old_done,old_failed;
    initial begin
        #0.1;reset_n=0;#0.6;if(local_hold!==1)$fatal(1,"common reset did not asynchronously assert conservative hold");
        #1.1;reset_n=1;release_check();cases=cases+1;
        // CPU-only reset is not a reason to alter the idle hold fence.
        #1.2;owner_n=0;#0.2;if(local_hold!==0)$fatal(1,"CPU-only reset changed idle hold");
        clocks(3);owner_n=1;cases=cases+1;
        // Services sample the old hold on the second release edge: no new
        // recording may start on either of those two edges.
        #1.3;reset_n=0;clocks(2);#1.1;reset_n=1;
        edge_compute();command_valid=1;
        if(!response_error)$fatal(1,"actual REC START was not fenced on first release edge");
        edge_compute();command_valid=0;
        if(record_enable)$fatal(1,"actual REC START crossed common-reset hold fence");
        edge_compute();command_valid=1;
        if(response_error)$fatal(1,"actual REC START remained blocked after release");
        edge_compute();command_valid=0;
        if(!record_enable)$fatal(1,"actual REC owner did not start after release");cases=cases+1;
        reset_case();old_local=local_requests;begin_stop();clocks(8);
        if(local_requests!=old_local||tf_request||done||failed||ready)$fatal(1,"stopped compute manufactured a backend event");cases=cases+1;
        owner_n=0;repeat(7)edge_compute();
        if(local_requests!=old_local||local_hold!==1)$fatal(1,"CPU reset abandoned or delivered held transaction");
        owner_n=1;repeat(2)edge_compute();
        if(local_requests!=old_local+1)$fatal(1,"held local request was not delivered after CPU reset");
        owner_n=0;repeat(2)edge_compute();owner_n=1;repeat(2)edge_compute();
        if(local_requests!=old_local+2||local_hold!==1)$fatal(1,"CPU reset failed to reissue same local transaction");cases=cases+1;
        old_done=done_count;hold=0;acknowledge_local(0);clocks(6);
        if(local_hold!==1||ready||done_count!=old_done)$fatal(1,"hold released before true TF terminal");
        tf_pending=0;tf_done=1;clocks(1);tf_done=0;clocks(4);
        if(local_hold!==1||done_count!=old_done)$fatal(1,"hold released before physical quiet");
        quiet=1;wait(done);clocks(2);
        if(done_count!=old_done+1)$fatal(1,"normal stop terminal count");release_check();cases=cases+1;
        reset_case();begin_stop();repeat(6)edge_compute();hold=0;acknowledge_local(1);
        old_failed=failed_count;tf_failed=1;clocks(1);tf_failed=0;clocks(3);
        if(failed_count!=old_failed+1||failure!=7||ready||local_hold!==1)$fatal(1,"TF failure escaped pending drain fence");
        owner_n=0;clocks(5);owner_n=1;
        if(failed_count!=old_failed+1||local_hold!==1)$fatal(1,"CPU reset revoked failed backend hold");
        tf_pending=0;clocks(3);release_check();cases=cases+1;
        // A board reset overlapping active hold never opens the compute gate,
        // including a fresh request immediately after common reset release.
        begin_stop();#1.3;reset_n=0;#0.2;if(local_hold!==1)$fatal(1,"overlapping reset opened active hold");
        request=0;hold=0;clocks(2);#1.1;reset_n=1;begin_stop();
        repeat(2)edge_compute();if(local_hold!==1)$fatal(1,"new stop crossed common-reset release fence");
        reset_case();cases=cases+1;
        if(cases!=8)$fatal(1,"hold fence coverage missing");
        $display("PASS media_hold_fence: cases=%0d compute_edges=%0d local_requests=%0d tf_requests=%0d done=%0d failed=%0d",cases,compute_edges,local_requests,tf_requests,done_count,failed_count);$finish;
    end
    initial begin #1000000;$fatal(1,"hold fence watchdog");end
endmodule
