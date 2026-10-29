`timescale 1ns/1ps

module tb_workstation_audio_clock_domain;
    reg clk=0,rst_n=0,reference48=0,reference44=0,run48=1,run44=1;
    realtime phase48=3.7,phase44=17.2,half44=29.525699;
    integer ignored;
    always #10 clk=~clk;
    initial begin
        ignored=$value$plusargs("PHASE48=%f",phase48);
        #(phase48);
        forever begin #40.690104; if(run48)reference48=~reference48; end
    end
    initial begin
        ignored=$value$plusargs("PHASE44=%f",phase44);
        #(phase44);
        forever begin #(half44); if(run44)reference44=~reference44; end
    end
    reg request=0,request44=0,recover=0,idle=0,prefill=1,output_running=1;
    wire selected_clk,audio_reset_n,ready,busy,fault,accepted,applied,rejected,failed;
    wire [2:0] reject_code;
    wire [3:0] fault_code,selection;
    wire quiesce,mute,flush,active44,active_valid,staged44,selected_good,selected_low;
    wire [31:0] epoch,staged_epoch;
    wire [1:0] raw_good,raw_present;
    wire [11:0] edges48,edges44,edges_selected;
    workstation_audio_clock_domain #(
        .WINDOW_CYCLES(500),.STABLE_WINDOWS(3),.LOSS_TIMEOUT_CYCLES(25),
        .STOP_LOW_CYCLES(8),.COUNTER_BITS(12),.SWITCH_TIMEOUT_CYCLES(4000)
    ) dut (
        .clk_50m_i(clk),.rst_ni(rst_n),.reference_48_i(reference48),.reference_44_i(reference44),
        .request_i(request),.request_44k1_i(request44),.recover_i(recover),
        .frame_quiescent_i(idle),.prefill_ready_i(prefill && audio_reset_n),
        .output_running_i(output_running && audio_reset_n),
        .selected_clock_o(selected_clk),.audio_reset_no(audio_reset_n),
        .request_ready_o(ready),.busy_o(busy),.fault_o(fault),.accepted_o(accepted),.applied_o(applied),
        .rejected_o(rejected),.failed_o(failed),.reject_code_o(reject_code),.fault_code_o(fault_code),
        .clock_select_o(selection),.quiesce_o(quiesce),.dac_mute_o(mute),.stream_flush_o(flush),
        .active_44k1_o(active44),.active_valid_o(active_valid),.staged_44k1_o(staged44),
        .stream_epoch_o(epoch),.staged_epoch_o(staged_epoch),
        .source_qualified_o(raw_good),.source_present_o(raw_present),
        .selected_qualified_o(selected_good),.selected_stopped_low_o(selected_low),
        .measured_48_o(edges48),.measured_44_o(edges44),.measured_selected_o(edges_selected)
    );
    integer selected_edges_since_reset=0,failures=0,applies=0;
    always @(posedge selected_clk or negedge dut.audio_safe_n)
        if (!dut.audio_safe_n) selected_edges_since_reset=0;
        else selected_edges_since_reset=selected_edges_since_reset+1;
    always @(posedge audio_reset_n) begin
        #0.001;
        if (selected_edges_since_reset<3) $fatal(1,"local reset release lacked three selected edges");
    end
    always @(negedge clk) begin
        if (rst_n) begin
            if (failed) failures=failures+1;
            if (applied) applies=applies+1;
            if (fault && (!mute || audio_reset_n || selection!=0 || !flush)) $fatal(1,"unsafe fault isolation");
            if (selection!=0 && selection!=1 && selection!=2) $fatal(1,"DCS select not onehot-or-zero");
            if (selected_low && selected_clk!==1'b0) $fatal(1,"stopped-low proof while output high");
        end
    end
    realtime last_clock_edge=0;
    reg check_pulses=1;
    always @(selected_clk) begin
        if (rst_n && check_pulses && last_clock_edge>0 && $realtime-last_clock_edge<29.3)
            $fatal(1,"truncated normal DCS clock pulse %0.3f",$realtime-last_clock_edge);
        last_clock_edge=$realtime;
    end
    task tick; begin @(posedge clk); #1; end endtask
    task ticks(input integer count); begin repeat(count)tick(); end endtask
    task wait_ready;
        integer n;
        begin
            n=0;
            while (!ready && !fault && n<15000) begin tick(); n=n+1; end
            if (!ready || fault) $fatal(1,"ready missing fault=%0d state=%0d",fault_code,dut.transaction.state);
        end
    endtask
    task wait_raw(input [1:0] expected);
        integer n;
        begin
            n=0;
            while (raw_good!=expected && n<6000) begin tick(); n=n+1; end
            if (raw_good!=expected) $fatal(1,"raw qualification expected=%b got=%b",expected,raw_good);
        end
    endtask
    task wait_fault(input integer code);
        integer n;
        begin
            n=0;
            while(!fault && n<15000) begin tick(); n=n+1; end
            if(!fault || fault_code!=code) $fatal(1,"fault expected=%0d actual=%0d",code,fault_code);
        end
    endtask
    task pulse_request(input bit rate44);
        begin @(negedge clk); request44=rate44; request=1; tick(); request=0; end
    endtask
    task recover_ready;
        begin
            prefill=1; output_running=1;
            @(negedge clk); recover=1; tick(); recover=0; wait_ready();
        end
    endtask
    task switch_ready(input bit rate44,input integer next_epoch);
        integer n;
        begin
            idle=0; prefill=0; output_running=0;
            pulse_request(rate44);
            if(!accepted || !quiesce || selection!=(rate44 ? 1 : 2)) $fatal(1,"switch acceptance/old source");
            ticks(10); idle=1; tick(); idle=0;
            n=0;
            while(!audio_reset_n && !fault && n<6000)begin tick();n=n+1;end
            if(!audio_reset_n || fault || !mute || !selected_good || epoch!=next_epoch-1)
                $fatal(1,"selected monitor/reset/prefill");
            if(n<1400) $fatal(1,"old selected qualification reused");
            prefill=1; tick(); ticks(5);
            if(ready || applied || epoch!=next_epoch-1) $fatal(1,"actual output acknowledgement bypassed");
            output_running=1; tick();
            if(!ready || !applied || epoch!=next_epoch || active44!=rate44 || !audio_reset_n)
                $fatal(1,"atomic applied output");
            ticks(3);
        end
    endtask
    integer n;
    initial begin
        ticks(5);rst_n=1;
        ticks(1000);
        if(raw_good!=0 || active_valid || audio_reset_n) $fatal(1,"qualified before three windows");
        wait_ready();wait_raw(2'b11);
        if(epoch!=0 || active44 || !audio_reset_n) $fatal(1,"startup state epoch=%0d active44=%b reset=%b state=%0d",epoch,active44,audio_reset_n,dut.transaction.state);
        // Multiple 12-bit source-counter wraps must not affect unsigned deltas.
        repeat(36)begin
            ticks(500);
            if(raw_good!=3 || !ready || edges48<120 || edges48>126 || edges44<166 || edges44>173)
                $fatal(1,"frequency window/counter wrap");
        end
        switch_ready(1,1);
        switch_ready(0,2);
        // Oscillating at the wrong rate stays present but loses qualification.
        check_pulses=0;half44=26.0;wait_raw(2'b01);
        if(raw_present!=3 || !ready) $fatal(1,"wrong frequency presence/isolation");
        pulse_request(1);
        if(!rejected || reject_code!=2 || accepted || epoch!=2) $fatal(1,"wrong-rate target accepted");
        half44=29.525699;wait_raw(2'b11);check_pulses=1;last_clock_edge=0;
        // Reject consecutive requests without replacing staged target/epoch.
        idle=0;prefill=0;output_running=0;pulse_request(1);pulse_request(0);
        if(!rejected || reject_code!=1 || !staged44 || staged_epoch!=3) $fatal(1,"busy request replacement");
        // Stop active old clock high only after acceptance, then finish ack.
        check_pulses=0;wait(reference48===1'b1);run48=0;
        idle=1;tick();idle=0;ticks(40);
        if(raw_good[0] || audio_reset_n || selected_low || selected_clk!==1'b1)
            $fatal(1,"stopped-high monitor/reset isolation");
        wait_fault(2);
        if(epoch!=2) $fatal(1,"stopped-high changed epoch");
        // Recovery cannot start until last committed raw reference requalifies.
        @(negedge clk);recover=1;tick();recover=0;ticks(20);
        if(!fault || selection!=0) $fatal(1,"unqualified recovery started");
        run48=1;wait_raw(2'b11);recover_ready();
        if(epoch!=3 || active44) $fatal(1,"stopped-high recovery");
        // New selected target disappears during its fresh qualification window.
        idle=0;prefill=0;output_running=0;pulse_request(1);
        idle=1;tick();idle=0;
        n=0;while(selection!=2 && n<200)begin tick();n=n+1;end
        if(selection!=2)$fatal(1,"target was never selected");
        wait(selected_clk===1'b1 && reference44===1'b1);run44=0;
        wait_fault(4);
        if(epoch!=3 || audio_reset_n || selected_low) $fatal(1,"lost target isolation");
        // Even healthy last-committed source cannot bypass a stuck target gate.
        @(negedge clk);recover=1;tick();recover=0;wait_fault(2);
        run44=1;wait_raw(2'b11);recover_ready();
        if(epoch!=4 || active44) $fatal(1,"target-loss recovery");
        check_pulses=1;last_clock_edge=0;
        switch_ready(1,5);
        // Current source loss in RUN asserts local reset without a source edge.
        check_pulses=0;wait(reference44===1'b1);run44=0;
        n=0;while(!fault && n<40)begin tick();n=n+1;end
        if(!fault || fault_code!=6 || audio_reset_n || !rst_n || epoch!=5)
            $fatal(1,"running clock loss did not isolate within monitor bound");
        run44=1;wait_raw(2'b11);recover_ready();
        if(epoch!=6 || !active44) $fatal(1,"running-loss recovery");
        ticks(5);
        $display("PASS audio clock domain: phase48=%0.3f phase44=%0.3f, measured Gray windows/wrap, wrong rate, stable qualification, stop-low proof, official DCS bidirectional switching, busy, stopped-high/target/running loss and recovery, reset release; applies=%0d faults=%0d",phase48,phase44,applies,failures);
        $finish;
    end
    initial begin #5000000;$fatal(1,"domain watchdog");end
endmodule
