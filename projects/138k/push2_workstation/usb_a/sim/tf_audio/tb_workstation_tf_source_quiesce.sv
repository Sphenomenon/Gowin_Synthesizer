`timescale 1ns/1ps
// Real service/path/DMA/FIFOs/decoder/bridge, with the maintained SD and DDR
// fixtures. Digital publisher/last-edge checks do not model metastability.
module tb_workstation_tf_source_quiesce #(
    parameter integer USE_COMMAND_BUFFER=0, CHECK_REGISTER_POLICY=1
);
    tb_workstation_tf_runtime_service #(.USE_COMMAND_BUFFER(USE_COMMAND_BUFFER),
        .RUN_SCENARIOS(0),.EXTERNAL_STOP_PROTOCOL(1),.OVERALL_TIMEOUT_NS(20000000)) f();
    integer cases=0,glitches=0,edge_checks=0,stopped_high=0,stopped_low=0;
    integer admission_checks=0,barrier_checks=0,release_delay_checks=0,quiet_ack_checks=0;
    integer failure_checks=0,stop_done_count=0,stop_failed_count=0;
    realtime last_source_edge=0;
    reg expected_quiesce,leaving_settle;
    reg [31:0] target_generation;
    reg checking_barrier=0;
    always @(posedge f.source_clk)begin
        last_source_edge=$realtime;
        expected_quiesce=f.dut.state==0 || f.dut.state==1 || f.dut.state==4 || f.dut.invalidate;
        leaving_settle=f.dut.state==4 && f.dut.path_clear_done && f.dut.memory_open_sync[1] && f.dut.restart_playback;
        #0.001;
        if(f.rst_n && CHECK_REGISTER_POLICY)begin
            if(f.dut.source_quiesce!==expected_quiesce)
                $fatal(1,"quiesce publisher did not sample source policy");
            if(leaving_settle)begin
                if(f.dut.state!=2 || !f.dut.source_quiesce || f.dut.bridge_source_ready)
                    $fatal(1,"quiesce release lost its conservative source edge");
                release_delay_checks=release_delay_checks+1;
            end
            edge_checks=edge_checks+1;
        end
    end
    always @(f.dut.source_quiesce)if(f.rst_n && $realtime!=last_source_edge)
        $fatal(1,"quiesce publisher changed between source edges");
    always @(f.dut.frames.source_quiesce_i)if(f.rst_n && $realtime!=last_source_edge)
        $fatal(1,"bridge quiesce input changed between source edges");
    always @(posedge f.compute_clk)if(f.rst_n && checking_barrier && f.expected==target_generation)begin
        if(f.tf_valid && f.tf_active && f.generation!=target_generation)
            $fatal(1,"old PCM escaped the observed generation barrier");
        barrier_checks=barrier_checks+1;
    end
    always @(negedge f.source_clk)if(f.rst_n)begin
        if(f.stop_done)begin
            if(f.stop_pending || f.pending || f.busy50 || !f.dut.stop_cleanup_complete ||
               !f.dut.source_quiet || !f.dut.path_clear_done || !f.dut.memory_open_sync[1])
                $fatal(1,"stop done bypassed actual quiet/control ACK");
            stop_done_count=stop_done_count+1;
        end
        if(f.stop_failed)stop_failed_count=stop_failed_count+1;
    end
    task start_rate(input bit rate);
        begin
            @(negedge f.source_clk);
            f.mode=1;f.run=1;f.runtime_rate=rate;f.runtime_epoch=f.runtime_epoch+1;
            f.cancel=0;f.restart=0;f.stop_request=0;f.transport_error=0;
            f.runtime_valid=1;f.runtime_fault=0;f.runtime_busy=0;
            f.begin_file(rate);f.await_frames(3);
            if(f.dut.source_quiesce || f.dut.frames.source_quiesce_i)
                $fatal(1,"active file retained quiesce");
        end
    endtask
    task cleanup;
        integer n;
        begin
            checking_barrier=0;f.checking=0;
            f.mode=0;f.cancel=0;f.restart=0;f.stop_request=0;f.transport_error=0;
            f.runtime_valid=1;f.runtime_fault=0;f.runtime_busy=0;f.source_run=1;
            f.await_quiet();n=0;
            while(f.stop_pending)begin
                @(negedge f.source_clk);n=n+1;
                if(n>2200)$fatal(1,"pending stop did not receive actual cleanup ACK");
            end
            if(!f.dut.source_quiet || f.dut.generation_pending || !f.dut.path_clear_done ||
               f.dut.memory_read_pending || f.tf_active || f.tf_valid || f.busy50)
                $fatal(1,"cleanup bypassed real transport/storage ACK");
            quiet_ack_checks=quiet_ack_checks+1;
        end
    endtask
    task between_edges_glitch(input bit rate);
        reg [31:0] epoch_before,generation_before,invalidates_before;
        begin
            start_rate(rate);f.checking=0;
            @(negedge f.source_clk);
            epoch_before=f.runtime_epoch;generation_before=f.source_generation;invalidates_before=f.invalidates;
            #2;f.runtime_epoch=epoch_before^32'h1;#2;
            if(f.dut.source_quiesce || f.dut.frames.source_quiesce_i)
                $fatal(1,"subcycle epoch decode published asynchronous quiesce");
            f.runtime_epoch=epoch_before;#2;
            @(posedge f.source_clk);#0.002;
            if(f.source_generation!=generation_before || f.invalidates!=invalidates_before || f.failed)
                $fatal(1,"non-event decode glitch changed source transaction");
            glitches=glitches+1;cleanup();
        end
    endtask
    // Each event occurs while real PCM could be accepted at the upcoming
    // source edge. There are no later source rising edges until recovery.
    task last_edge(input bit rate,input integer kind,input bit high);
        reg [31:0] before_generation,before_invalidates,before_accepted,epoch_before;
        reg rate_before;
        integer n,expected_failure,before_done,before_failed;
        begin
            start_rate(rate);f.checking=0;n=0;
            @(negedge f.source_clk);
            while(!(f.dut.path_pcm_valid && f.dut.bridge_source_ready))begin
                @(negedge f.source_clk);n=n+1;
                if(n>10000)$fatal(1,"no real PCM admission opportunity");
            end
            before_generation=f.source_generation;before_invalidates=f.invalidates;before_accepted=f.accepted;
            epoch_before=f.runtime_epoch;rate_before=f.runtime_rate;
            before_done=stop_done_count;before_failed=stop_failed_count;expected_failure=0;
            case(kind)
                0:f.cancel=1;
                1:begin f.runtime_epoch=f.runtime_epoch+1;expected_failure=6;end
                2:begin f.runtime_rate=!f.runtime_rate;expected_failure=6;end
                3:f.track=rate ? 0:1;
                4:f.stop_request=1;
                5:begin f.transport_error=1;expected_failure=7;end
                6:begin f.runtime_valid=0;expected_failure=5;end
                7:begin f.cancel=1;f.restart=1;f.stop_request=1;f.transport_error=1;expected_failure=7;end
            endcase
            #0.001;
            if(!f.dut.invalidate || f.dut.playback_accept || f.dut.path_pcm_ready || !f.dut.path.native_source_hold_i)
                $fatal(1,"same-edge source admission or native input hold missing");
            admission_checks=admission_checks+1;
            @(posedge f.source_clk);#0.002;
            target_generation=before_generation+1'b1;
            if(f.source_generation!==target_generation || f.invalidates!==before_invalidates+1'b1)
                $fatal(1,"same-edge generation barrier was delayed or duplicated");
            if(!f.dut.source_quiesce || !f.dut.frames.source_quiesce_i || f.accepted!=before_accepted)
                $fatal(1,"last source edge failed to retain quiesce or admitted stale PCM");
            if(expected_failure!=0)begin
                if(!f.failed || f.failure!=expected_failure)$fatal(1,"same-edge failure identity changed");
                failure_checks=failure_checks+1;
            end
            if(kind==7 && (!f.stop_pending || !f.stop_failed || f.stop_failure!=7 || f.dut.pending_start))
                $fatal(1,"simultaneous stop/failure/restart priority changed");
            if(!high)begin @(negedge f.source_clk);#0.001;end
            f.source_run=0;checking_barrier=1;
            repeat(100)@(negedge f.compute_clk);
            if(f.source_clk!==high || !f.dut.source_quiesce || !f.dut.frames.source_quiesce_i ||
               f.source_generation!==target_generation || f.expected!==target_generation ||
               f.tf_active || f.tf_valid || !f.dut.bridge_quiet || !f.tf_busy || !f.busy50 ||
               f.dut.source_quiet || f.quiet50 || f.stop_done || f.accepted!=before_accepted)
                $fatal(1,"stopped source lost cancellation or invented returned quiet ACK kind=%0d high=%0d",kind,high);
            if(high)stopped_high=stopped_high+1;else stopped_low=stopped_low+1;
            f.runtime_epoch=epoch_before;f.runtime_rate=rate_before;
            cleanup();
            if(kind==4 && stop_done_count!=before_done+1)$fatal(1,"successful stop completion count changed");
            if(kind==7 && (stop_done_count!=before_done || stop_failed_count!=before_failed+1))
                $fatal(1,"failed stop later invented success or duplicate failure");
            // Explicit restart must recover a full valid file after old data
            // and control cleanup, rather than merely reopening an empty route.
            start_rate(rate);f.await_frames(64);cleanup();cases=cases+1;
            $display("TRACE source quiesce rate:%0d kind:%0d high:%0d cases:%0d",rate,kind,high,cases);
        end
    endtask
    initial begin
        // Exercise an actual asynchronous assertion before any source edge;
        // a declaration-time zero alone is not an event in every simulator.
        #1;f.rst_n=1;#1;f.rst_n=0;#0.001;
        if(f.dut.source_quiesce!==1 || f.dut.frames.source_quiesce_i!==1)
            $fatal(1,"asserted reset quiesce missing");
        repeat(6)@(negedge f.source_clk);f.rst_n=1;repeat(30)@(negedge f.source_clk);
        for(integer rate=0;rate<2;rate=rate+1)begin
            between_edges_glitch(1'(rate));
            for(integer kind=0;kind<8;kind=kind+1)
                for(integer high=0;high<2;high=high+1)last_edge(1'(rate),kind,1'(high));
        end
        if(cases!=32 || glitches!=2 || stopped_high!=16 || stopped_low!=16 ||
           admission_checks!=32 || failure_checks!=20 || release_delay_checks<64 ||
           quiet_ack_checks!=66 || barrier_checks==0 || edge_checks==0)
            $fatal(1,"source-quiesce coverage incomplete");
        $display("PASS tf_source_quiesce: cases=%0d rates=2 glitches=%0d stopped_high=%0d stopped_low=%0d admission=%0d failures=%0d release_delay=%0d real_quiet_ack=%0d barrier_checks=%0d edges=%0d pcm=%0d buffer=%0d",
            cases,glitches,stopped_high,stopped_low,admission_checks,failure_checks,release_delay_checks,
            quiet_ack_checks,barrier_checks,edge_checks,f.delivered,USE_COMMAND_BUFFER);
        $finish;
    end
    initial begin #20000000;$fatal(1,"source quiesce bounded regression timed out");end
endmodule
