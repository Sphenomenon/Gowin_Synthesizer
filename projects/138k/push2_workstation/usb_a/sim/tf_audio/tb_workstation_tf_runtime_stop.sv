`timescale 1ns/1ps
module tb_workstation_tf_runtime_stop #(parameter integer USE_COMMAND_BUFFER=0);
    tb_workstation_tf_runtime_service #(.USE_COMMAND_BUFFER(USE_COMMAND_BUFFER),.RUN_SCENARIOS(0),.EXTERNAL_STOP_PROTOCOL(1)) f();
    integer cases=0,done_count=0,failed_count=0,paused_high=0,paused_low=0,coalesced=0;
    integer mailbox_wait_checks=0,drain_wait_checks=0,stopped_checks=0,idempotent_checks=0;
    reg done_q=0,failed_q=0;
    always @(negedge f.source_clk)if(f.rst_n)begin
        if(f.stop_done)begin
            if(done_q || f.stop_failed || f.stop_pending || f.busy50 || !f.dut.stop_latched ||
               f.dut.state!=0 || !f.dut.source_quiet || !f.dut.path_clear_done || !f.dut.memory_open_sync[1] ||
               f.pending || f.dut.held_control[2] || f.dut.held_control[0] || f.tf_active || f.tf_busy)
                $fatal(1,"stop done preceded final mailbox/clear/gate proof");
            done_count=done_count+1;
        end
        if(f.stop_failed)begin
            if(failed_q || !f.stop_pending || f.stop_done || f.stop_failure==0)$fatal(1,"invalid stop failure pulse");
            failed_count=failed_count+1;
        end
        done_q=f.stop_done;failed_q=f.stop_failed;
    end
    task pulse_stop;
        begin
            f.checking=0;@(negedge f.source_clk);f.stop_request=1;#0.001;
            if(f.dut.stop_latched && f.dut.stop_begin)begin
                if(f.dut.stop_invalidate || f.dut.invalidate)$fatal(1,"idempotent stop created another fence");
                idempotent_checks=idempotent_checks+1;
            end
            @(negedge f.source_clk);f.stop_request=0;
        end
    endtask
    task await_pending_clear;
        integer n;
        begin
            n=0;
            while(f.stop_pending)begin @(negedge f.source_clk);n=n+1;if(n>2200)$fatal(1,"stop cleanup did not finish");end
            repeat(4)@(negedge f.source_clk);
        end
    endtask
    task await_done(input integer target);
        integer n;
        begin
            n=0;
            while(done_count<target)begin @(negedge f.source_clk);n=n+1;if(n>2200)$fatal(1,"stop done timeout state=%0d pending=%b failed=%b ctrl=%b",f.dut.state,f.stop_pending,f.stop_failed,f.pending);end
            await_pending_clear();
        end
    endtask
    task begin_track(input bit rate);
        begin
            @(negedge f.source_clk);f.mode=1;f.analysis_enable=0;f.runtime_rate=rate;f.runtime_epoch=f.runtime_epoch+1;
            f.begin_file(rate);f.await_frames(3);
        end
    endtask
    task assert_stays_stopped;
        integer restarts;
        reg [31:0] generation;
        begin
            restarts=f.path_restarts;generation=f.source_generation;
            repeat(60)begin
                @(negedge f.source_clk);
                if(f.tf_active || f.tf_valid || f.analysis_valid || f.busy50 || !f.dut.stop_latched ||
                   f.path_restarts!=restarts || f.source_generation!=generation || f.req)
                    $fatal(1,"stopped TF rearmed without explicit restart case=%0d active=%b valid=%b analysis=%b busy=%b latch=%b restarts=%0d/%0d generation=%0d/%0d req=%b",cases,f.tf_active,f.tf_valid,f.analysis_valid,f.busy50,f.dut.stop_latched,f.path_restarts,restarts,f.source_generation,generation,f.req);
                stopped_checks=stopped_checks+1;
            end
        end
    endtask
    task pause_memory_after_clear(input bit high);
        reg token;
        begin
            token=f.dut.path_clear_toggle;wait(f.dut.path_clear_toggle!=token);
            if(high)begin @(posedge f.memory_clk);#0.001;paused_high=paused_high+1;end
            else begin @(negedge f.memory_clk);paused_low=paused_low+1;end
            f.memory_run=0;
        end
    endtask
    integer before_done,before_failed,before_restarts;
    reg [31:0] before_generation;
    reg token;
    initial begin
        repeat(6)@(negedge f.source_clk);f.rst_n=1;repeat(30)@(negedge f.source_clk);
        // Active file stop, then track/run/analysis requests cannot rearm it.
        begin_track(0);pulse_stop();await_done(1);
        @(negedge f.source_clk);f.track=1;f.run=0;f.reader_restart=1;
        @(negedge f.source_clk);f.reader_restart=0;f.run=1;
        assert_stays_stopped();
        @(negedge f.source_clk);f.mode=0;f.analysis_enable=1;f.analysis_ready=1;
        f.await_quiet();assert_stays_stopped();cases=cases+1;
        // A new stop on an already clean stopped owner ACKs without clearing
        // or changing generation again. It is still a one-pulse transaction.
        before_restarts=f.path_restarts;before_generation=f.source_generation;
        pulse_stop();await_done(2);pulse_stop();await_done(3);
        if(f.path_restarts!=before_restarts || f.source_generation!=before_generation)$fatal(1,"idempotent stop restarted storage");
        cases=cases+1;
        // Explicit restart restores a whole new file. Simultaneous stop wins.
        begin_track(1);f.checking=0;
        @(negedge f.source_clk);f.restart=1;f.stop_request=1;
        @(negedge f.source_clk);f.restart=0;f.stop_request=0;
        await_done(4);assert_stays_stopped();cases=cases+1;
        // No clear may begin while an old accepted read has not returned.
        @(negedge f.source_clk);f.runtime_rate=0;f.runtime_epoch=f.runtime_epoch+1;f.track=0;f.hold_response=1;
        f.pulse_restart();wait(f.dut.memory_read_pending);before_restarts=f.path_restarts;
        pulse_stop();wait(f.dut.memory_gate);
        repeat(30)begin
            @(negedge f.source_clk);
            if(!f.stop_pending || f.stop_done || f.path_restarts!=before_restarts || f.dut.memory_quiet_50)
                $fatal(1,"stop bypassed accepted read drain");
            drain_wait_checks=drain_wait_checks+1;
        end
        f.hold_response=0;await_done(5);cases=cases+1;
        // Paused memory after the token cannot supply missing local ACKs.
        begin_track(0);
        fork begin pulse_stop();end begin pause_memory_after_clear(0);end join
        token=f.dut.path_clear_toggle;before_done=done_count;
        pulse_stop();pulse_stop();coalesced=coalesced+2;
        repeat(32)@(negedge f.source_clk);
        if(!f.stop_pending || f.stop_done || !f.busy50 || !f.dut.memory_gate || f.dut.path_clear_done ||
           f.dut.path_clear_toggle!=token || done_count!=before_done)$fatal(1,"paused memory invented stop ACK");
        f.memory_run=1;await_done(6);cases=cases+1;
        // Timeout fails once, retains cleanup pending, and never emits done
        // for that failed operation after real memory completion returns.
        begin_track(0);before_failed=failed_count;before_done=done_count;
        fork begin pulse_stop();end begin pause_memory_after_clear(1);end join
        repeat(1100)@(negedge f.source_clk);
        if(failed_count!=before_failed+1 || f.stop_failure!=8 || !f.stop_pending || !f.busy50 || !f.dut.memory_gate || done_count!=before_done)
            $fatal(1,"memory timeout invented stop completion");
        pulse_stop();coalesced=coalesced+1;f.memory_run=1;await_pending_clear();
        if(done_count!=before_done || failed_count!=before_failed+1)$fatal(1,"failed memory stop later emitted success");
        assert_stays_stopped();pulse_stop();await_done(7);cases=cases+1;
        // Stopped compute cannot drain generation/control mailboxes.
        begin_track(0);f.checking=0;@(negedge f.compute_clk);f.compute_run=0;
        before_failed=failed_count;before_done=done_count;pulse_stop();
        repeat(1100)@(negedge f.source_clk);
        if(failed_count!=before_failed+1 || f.stop_failure!=8 || !f.stop_pending || done_count!=before_done)
            $fatal(1,"compute timeout invented stop completion");
        f.compute_run=1;await_pending_clear();
        if(done_count!=before_done || failed_count!=before_failed+1)$fatal(1,"failed compute stop later emitted success");
        pulse_stop();await_done(8);cases=cases+1;
        // Stop compute only AFTER bridge/drain/clear, just before busy falls.
        // Source may reach IDLE but must wait for the final inactive mailbox.
        begin_track(0);
        fork
            begin pulse_stop();end
            begin
                wait(f.dut.state==4 && f.dut.path_clear_done && !f.dut.memory_gate);
                @(negedge f.compute_clk);f.compute_run=0;
            end
        join
        repeat(25)@(negedge f.source_clk);
        if(f.dut.state!=0 || f.busy50 || !f.pending || !f.stop_pending)$fatal(1,"final mailbox stall was not exercised");
        repeat(40)begin
            @(negedge f.source_clk);
            if(f.stop_done || !f.stop_pending || !f.pending)$fatal(1,"stop done bypassed final mailbox ACK");
            mailbox_wait_checks=mailbox_wait_checks+1;
        end
        f.compute_run=1;await_done(9);cases=cases+1;
        // The whole-transaction watchdog also covers an indefinitely missing
        // FINAL mailbox ACK, after ordinary clear/busy already completed.
        begin_track(0);before_done=done_count;before_failed=failed_count;
        fork
            begin pulse_stop();end
            begin
                wait(f.dut.state==4 && f.dut.path_clear_done && !f.dut.memory_gate);
                @(negedge f.compute_clk);f.compute_run=0;
            end
        join
        repeat(1100)@(negedge f.source_clk);
        if(f.dut.state!=0 || f.busy50 || !f.pending || !f.stop_pending || f.failed ||
           failed_count!=before_failed+1 || f.stop_failure!=8 || done_count!=before_done)
            $fatal(1,"final mailbox timeout invented stop completion");
        f.compute_run=1;await_pending_clear();
        if(done_count!=before_done || failed_count!=before_failed+1)$fatal(1,"failed final mailbox stop later emitted success");
        pulse_stop();await_done(10);cases=cases+1;
        // A simultaneous real transport failure fails the accepted stop once.
        begin_track(0);before_done=done_count;before_failed=failed_count;f.checking=0;
        @(negedge f.source_clk);f.transport_error=1;f.stop_request=1;
        @(negedge f.source_clk);f.stop_request=0;
        await_pending_clear();
        if(failed_count!=before_failed+1 || f.stop_failure!=7 || done_count!=before_done)$fatal(1,"transport failure became stop success");
        @(negedge f.source_clk);f.transport_error=0;
        assert_stays_stopped();begin_track(0);f.await_frames(64);cases=cases+1;
        // Re-request on the first source edge after completion, with no
        // extra quiet-settle delay. The existing fence/clear token must hold.
        begin_track(0);before_done=done_count;pulse_stop();wait(f.stop_done);
        before_generation=f.source_generation;before_restarts=f.path_restarts;
        token=f.dut.path_clear_toggle;pulse_stop();await_done(before_done+2);
        if(f.source_generation!=before_generation || f.path_restarts!=before_restarts ||
           f.dut.path_clear_toggle!=token)$fatal(1,"earliest idempotent stop changed the completed fence");
        cases=cases+1;
        if(cases!=11 || done_count!=12 || failed_count!=4 || coalesced!=3 || paused_high!=1 || paused_low!=1 ||
           mailbox_wait_checks!=40 || drain_wait_checks!=30 || stopped_checks<200 || idempotent_checks!=6)$fatal(1,"missing stop coverage");
        $display("PASS tf_runtime_stop: buffered=%0d cases=%0d done=%0d failed=%0d coalesced=%0d paused_high=%0d paused_low=%0d mailbox_wait=%0d drain_wait=%0d stopped_checks=%0d idempotent_checks=%0d delivered=%0d",USE_COMMAND_BUFFER,cases,done_count,failed_count,coalesced,paused_high,paused_low,mailbox_wait_checks,drain_wait_checks,stopped_checks,idempotent_checks,f.delivered);
        $finish;
    end
endmodule

module tb_workstation_tf_runtime_stop_disabled;
    tb_workstation_tf_runtime_service #(.RUN_SCENARIOS(0)) f();
    integer invalidates_before;
    initial begin
        repeat(6)@(negedge f.source_clk);f.rst_n=1;repeat(30)@(negedge f.source_clk);
        f.begin_file(0);f.await_frames(3);invalidates_before=f.invalidates;
        @(negedge f.source_clk);f.stop_request=1;
        repeat(12)@(negedge f.source_clk);f.stop_request=0;
        f.await_frames(64);
        if(f.stop_pending || f.stop_done || f.stop_failed || f.dut.stop_latched || f.invalidates!=invalidates_before || !f.tf_active)
            $fatal(1,"disabled stop protocol changed default policy");
        $display("PASS tf_runtime_stop_disabled: delivered=%0d",f.delivered);$finish;
    end
endmodule
