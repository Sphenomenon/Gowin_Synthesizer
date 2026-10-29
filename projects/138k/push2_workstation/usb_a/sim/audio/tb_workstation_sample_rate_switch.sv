`timescale 1ns/1ps

module tb_workstation_sample_rate_switch;
    reg clk=0, rst_n=0, clk48=0, clk44=0, run48=1, run44=1;
    always #10 clk=~clk;
    always #40.690104 if (run48) clk48=~clk48;
    always #29.525699 if (run44) clk44=~clk44;
    reg request=0, request44=0, recover=0, idle=0, prefill=0, output_running=1;
    reg [1:0] qualified=2'b11;
    wire ready,busy,fault,accepted,applied,rejected,failed;
    wire [2:0] rejection;
    wire [3:0] failure,select;
    wire quiesce,mute,audio_reset_n,flush,restart,active44,active_valid,staged44;
    wire [31:0] epoch,staged_epoch;
    wire selected_clk;
    reg [1:0] selected_sync=0;
    reg previous=0;
    integer age=0,edges=0;
    wire stopped_low=age>=12 && !selected_sync[1];
    wire selected_qualified=edges>=8 && age<12;
    // Monitor stays in the always-on domain, including when DCS is stopped.
    always @(posedge clk) begin
        selected_sync <= {selected_sync[0],selected_clk};
        previous <= selected_sync[1];
        if (!rst_n || restart) begin age<=0; edges<=0; end
        else if (selected_sync[1]!=previous) begin
            age<=0; if (edges<16) edges<=edges+1;
        end else if (age<32) age<=age+1;
    end
    // Official GW5A library, not a combinational-mux test double.
    DCS #(.DCS_MODE("FALLING")) dcs (
        .CLKIN0(clk48),.CLKIN1(clk44),.CLKIN2(1'b0),.CLKIN3(1'b0),
        .CLKSEL(select),.SELFORCE(1'b0),.CLKOUT(selected_clk)
    );
    workstation_sample_rate_switch #(.TIMEOUT_CYCLES(96)) dut (
        .clk_i(clk),.rst_ni(rst_n),.request_i(request),.request_44k1_i(request44),.recover_i(recover),
        .source_qualified_i(qualified),.frame_quiescent_i(idle),
        .selected_clock_stopped_low_i(stopped_low),.selected_clock_qualified_i(selected_qualified),
        .prefill_ready_i(prefill),.output_running_i(output_running),.request_ready_o(ready),.busy_o(busy),.fault_o(fault),
        .accepted_o(accepted),.applied_o(applied),.rejected_o(rejected),.failed_o(failed),
        .reject_code_o(rejection),.fault_code_o(failure),.quiesce_o(quiesce),.dac_mute_o(mute),
        .audio_reset_no(audio_reset_n),.stream_flush_o(flush),.clock_monitor_restart_o(restart),
        .clock_select_o(select),.active_44k1_o(active44),.active_valid_o(active_valid),
        .stream_epoch_o(epoch),.staged_44k1_o(staged44),.staged_epoch_o(staged_epoch)
    );
    integer accepts=0,applies=0,rejects=0,failures=0,cycles=0;
    always @(negedge clk) begin
        if (rst_n) begin
            cycles=cycles+1;
            if (accepted) accepts=accepts+1;
            if (applied) applies=applies+1;
            if (rejected) rejects=rejects+1;
            if (failed) failures=failures+1;
            if (!(select==0 || select==1 || select==2)) $fatal(1,"not onehot-or-zero");
            if (fault && (!mute || audio_reset_n || !flush || select!=0)) $fatal(1,"unsafe fault outputs");
            if (!active_valid && ready) $fatal(1,"ready without active stream");
        end
    end
    realtime last_edge=0;
    reg check_pulses=1;
    always @(selected_clk) begin
        if (rst_n && check_pulses && last_edge!=0 && $realtime-last_edge<29.4)
            $fatal(1,"DCS truncated pulse: %0.3f ns",$realtime-last_edge);
        last_edge=$realtime;
    end
    task tick; begin @(posedge clk); #1; end endtask
    task ticks(input integer n); begin repeat(n) tick(); end endtask
    task pulse_request(input bit rate44);
        begin @(negedge clk); request44=rate44; request=1; tick(); request=0; end
    endtask
    task wait_run;
        integer n;
        begin
            n=0;
            while (!ready && !fault && n<400) begin tick(); n=n+1; end
            if (!ready || fault) $fatal(1,"RUN missing state=%0d fault=%0d",dut.state,failure);
        end
    endtask
    task wait_fault(input integer code);
        integer n;
        begin
            n=0;
            while (!fault && n<400) begin tick(); n=n+1; end
            if (!fault || failure!=code) $fatal(1,"fault expected=%0d actual=%0d state=%0d",code,failure,dut.state);
        end
    endtask
    task recover_run;
        begin @(negedge clk); recover=1; tick(); recover=0; prefill=1; wait_run(); end
    endtask
    task complete_switch(input bit rate44,input integer expected_epoch);
        integer n;
        begin
            prefill=0; idle=0; output_running=0;
            pulse_request(rate44);
            if (!accepted || !quiesce || mute || !audio_reset_n) $fatal(1,"boundary quiesce handshake");
            ticks(4);
            if (epoch!=expected_epoch-1 || active44==rate44 || !active_valid) $fatal(1,"premature commit");
            idle=1; tick(); idle=0;
            n=0;
            while (!audio_reset_n && !fault && n<400) begin tick(); n=n+1; end
            if (fault || !mute || !busy || staged44!=rate44 || staged_epoch!=expected_epoch)
                $fatal(1,"prefill staging");
            ticks(4);
            if (epoch!=expected_epoch-1 || !mute) $fatal(1,"commit before prefill");
            prefill=1; tick();
            if (ready || applied || mute || epoch!=expected_epoch-1) $fatal(1,"apply before actual output");
            ticks(3); output_running=1; tick();
            if (!ready || !applied || active44!=rate44 || epoch!=expected_epoch || mute)
                $fatal(1,"atomic apply");
            ticks(2);
        end
    endtask
    initial begin
        ticks(4); rst_n=1;
        if (!mute || audio_reset_n || !flush) $fatal(1,"startup isolation");
        prefill=1; wait_run();
        if (epoch!=0 || active44 || !active_valid || applied) $fatal(1,"boot identity");
        complete_switch(1,1);
        complete_switch(0,2);
        // Idempotent request: reports apply without resetting or adding epoch.
        pulse_request(0);
        if (!accepted || !applied || epoch!=2 || busy || quiesce) $fatal(1,"same-mode no-op");
        ticks(2);
        qualified[1]=0;
        pulse_request(1);
        if (!rejected || rejection!=2 || accepted || epoch!=2 || !ready) $fatal(1,"missing-target refusal");
        qualified[1]=1;
        // Busy strobes cannot replace the selected target or pending epoch.
        idle=0; prefill=0; pulse_request(1);
        pulse_request(0);
        if (!rejected || rejection!=1 || !staged44 || staged_epoch!=3) $fatal(1,"busy replaced pending request");
        pulse_request(1);
        if (!rejected || rejection!=1) $fatal(1,"second busy strobe");
        idle=1; tick(); idle=0;
        while (!audio_reset_n && !fault) tick();
        qualified[1]=0;
        wait_fault(4);
        if (epoch!=2 || active44 || active_valid) $fatal(1,"failed target committed");
        pulse_request(1);
        if (!rejected || rejection!=3 || accepted) $fatal(1,"fault request accepted");
        qualified[1]=1; recover_run();
        if (epoch!=3 || active44) $fatal(1,"recovery identity");
        // A stopped-high active source cannot release a glitchless DCS gate.
        check_pulses=0; idle=0; prefill=0; pulse_request(1);
        wait(clk48===1'b1); run48=0;
        idle=1; tick(); idle=0;
        wait_fault(2);
        if (selected_clk!==1'b1 || epoch!=3) $fatal(1,"did not exercise stopped-high DCS");
        // A retry cannot invent the missing old-source edge.
        @(negedge clk); recover=1; tick(); recover=0;
        wait_fault(2);
        run48=1; ticks(16); recover_run();
        if (epoch!=4 || active44) $fatal(1,"old-source recovery");
        check_pulses=1; last_edge=0;
        // Complete-frame acknowledgement is bounded; no implicit global reset.
        idle=0; pulse_request(1); wait_fault(1);
        if (epoch!=4 || !rst_n) $fatal(1,"quiesce failure identity");
        recover_run();
        // Bounded prefill failure retains the last committed identity.
        prefill=0; pulse_request(1); idle=1; tick(); idle=0;
        wait_fault(5);
        if (epoch!=5 || active44) $fatal(1,"prefill failure committed");
        recover_run();
        // A stale source qualification cannot bypass a fresh output monitor.
        wait(clk44===1'b0); run44=0;
        prefill=0; pulse_request(1); idle=1; tick(); idle=0;
        wait_fault(3);
        if (epoch!=6 || active44) $fatal(1,"unqualified output committed");
        run44=1; recover_run();
        // Output acknowledgement has its own bound after prefill/unmute.
        output_running=0; prefill=1;
        pulse_request(1); idle=1; tick(); idle=0;
        wait_fault(7);
        if (epoch!=7 || active44) $fatal(1,"resume timeout committed");
        output_running=1; recover_run();
        // Running clock qualification loss asserts local isolation immediately.
        qualified[0]=0; tick(); wait_fault(6);
        if (!rst_n || epoch!=8) $fatal(1,"running failure/global reset");
        qualified[0]=1; recover_run();
        if (epoch!=9 || active44) $fatal(1,"final recovery");
        idle=0; pulse_request(1);
        qualified[0]=0; tick();
        if (!fault || failure!=6 || !mute || audio_reset_n)
            $fatal(1,"current clock loss waited for quiesce timeout");
        qualified[0]=1; recover_run();
        if (epoch!=10) $fatal(1,"quiesce-loss recovery");
        // An unselected target loss keeps the healthy old frame intact.
        idle=0; pulse_request(1); qualified[1]=0; ticks(3);
        if (fault || mute || !audio_reset_n || select!=1)
            $fatal(1,"target loss truncated healthy current frame");
        idle=1; tick(); idle=0; wait_fault(4);
        if (epoch!=10) $fatal(1,"quiesce target loss committed");
        qualified[1]=1; recover_run();
        if (epoch!=11) $fatal(1,"quiesce target recovery");
        ticks(2);
        // Startup never advertises a valid stream without a qualified source.
        rst_n=0; qualified=0; ticks(4); rst_n=1;
        wait_fault(3);
        if (epoch!=0 || active_valid || !mute || audio_reset_n) $fatal(1,"unqualified startup");
        qualified=2'b11; recover_run();
        if (epoch!=1 || active44) $fatal(1,"startup recovery");
        ticks(2);
        $display("PASS sample-rate switch: official GW5A DCS, bidirectional switch, atomic epoch/output acknowledgement, busy/missing target, stopped-high timeout, recovery, quiesce/qualification/prefill/resume/running/startup faults; cycles=%0d accepts=%0d applies=%0d rejects=%0d faults=%0d",cycles,accepts,applies,rejects,failures);
        $finish;
    end
    initial begin #1000000; $fatal(1,"test watchdog"); end
endmodule
