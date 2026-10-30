`timescale 1ns/1ps

module tb_workstation_runtime_memory_guard;
    localparam integer TIMEOUT=12;
    reg clk=0, memory_clk=0, memory_run=1;
    reg reset_n=1, backend_reset_n=1, backend_ready=1;
    wire started,fault,start_ready,mute,channel_open,clock_alive;
    wire [1:0] fault_code;
    wire default_started,default_fault,default_ready,default_mute,default_open,default_alive;
    wire [1:0] default_code;
    workstation_runtime_memory_guard #(.HEARTBEAT_TIMEOUT_CYCLES(TIMEOUT),.HEARTBEAT_BITS(4)) dut (
        .reset_ni(reset_n),.clk_50m_i(clk),.memory_clk_i(memory_clk),
        .backend_reset_ni(backend_reset_n),.backend_ready_i(backend_ready),
        .started_o(started),.fault_o(fault),.start_ready_o(start_ready),.mute_o(mute),
        .channel_open_o(channel_open),.clock_alive_o(clock_alive),.fault_code_o(fault_code));
    workstation_runtime_memory_guard production (
        .reset_ni(reset_n),.clk_50m_i(clk),.memory_clk_i(memory_clk),
        .backend_reset_ni(backend_reset_n),.backend_ready_i(backend_ready),
        .started_o(default_started),.fault_o(default_fault),.start_ready_o(default_ready),.mute_o(default_mute),
        .channel_open_o(default_open),.clock_alive_o(default_alive),.fault_code_o(default_code));
    always #10 clk=~clk;
    initial begin
        #2;
        forever begin #5; if (memory_run) memory_clk=~memory_clk; end
    end

    // Public integration model: requests, acceptance/ready and responses all
    // share the same gate. The backend retains a pre-loss read until told to
    // return it, just as a DDR queue can outlive a client-side fault.
    reg client_request=0,backend_request_ready=1,backend_response=0;
    wire backend_request=client_request && channel_open;
    wire client_ready=backend_request_ready && channel_open;
    wire client_response=backend_response && channel_open;
    wire runtime_reset_n=reset_n && started;
    integer accepted=0,delivered=0,wraps=0,checks=0,phases=0;
    integer high_stop_cycles=0,low_stop_cycles=0,default_stop_cycles=0;
    reg previously_started=0;
    task automatic check(input bit value,input string description);
        begin checks=checks+1; if (!value) $fatal(1,"memory guard: %s",description); end
    endtask
    always @(posedge memory_clk) begin
        if (backend_request && backend_request_ready) accepted=accepted+1;
        if (client_response) delivered=delivered+1;
        #1;
        if (dut.memory_reset_n && dut.memory_binary==0) wraps=wraps+1;
    end
    always @(posedge clk) begin
        #1;
        if (!reset_n) previously_started=0;
        else begin
            if (previously_started) check(started,"started must stay high until common reset");
            if (started && !previously_started)
                check(channel_open && dut.open_ack && !fault,"startup requires actual memory gate acknowledgement");
            previously_started=started;
            if (fault) check(!channel_open && mute && !start_ready,"sticky fault closes gate and mutes");
        end
    end
    task automatic cycles(input integer count);
        begin repeat(count) @(posedge clk); #2; end
    endtask
    task automatic common_reset;
        begin
            reset_n=0; backend_reset_n=0; backend_ready=0;
            client_request=0; backend_response=0; memory_run=1;
            #1; check(!started && !fault && !channel_open && mute,"common reset asserts without local edge");
            #36; reset_n=1; backend_reset_n=1;
            cycles(8);
            check(!started && !fault && !channel_open && mute,"reset waits for backend readiness");
        end
    endtask
    task automatic await_start;
        integer age;
        begin
            age=0;
            while (!start_ready && age<100) begin cycles(1); age=age+1; end
            check(start_ready && started && channel_open && !mute && !fault && clock_alive,"qualified startup completes");
            check(default_started && default_ready && default_open && !default_mute && !default_fault && default_alive && default_code==0,
                "default configuration also starts");
        end
    endtask
    task automatic start_backend;
        begin backend_ready=1; await_start(); end
    endtask
    task automatic stop_memory(input bit high_level);
        begin
            if (high_level) @(posedge memory_clk); else @(negedge memory_clk);
            #1; memory_run=0;
            check(memory_clk==high_level,"source stops at requested level");
        end
    endtask
    task automatic expect_permanent_fault(input [1:0] code);
        begin
            cycles(6);
            check(fault && fault_code==code && started && runtime_reset_n,"fault preserves runtime reset and startup state");
            check(!channel_open && !client_ready && !backend_request && !client_response && mute,"all modeled transaction directions close");
            backend_ready=1; backend_reset_n=1; memory_run=1;
            client_request=1; backend_response=1;
            cycles(50);
            check(fault && fault_code==code && !channel_open && !start_ready && mute,"backend recovery and new requests cannot rearm");
            check(started && runtime_reset_n,"recovery never resets notes or epoch through startup state");
            client_request=0; backend_response=0;
        end
    endtask

    integer saved_accepted,saved_delivered,elapsed;
    initial begin
        // All event controls are installed before the first explicit reset
        // edge; relying on declaration initialization is simulator dependent.
        #1;
        // Initial availability and clock absence can wait indefinitely without
        // poisoning the first legitimate startup.
        common_reset(); cycles(80);
        check(!started && !fault && !channel_open,"unready boot does not permanently fault after timeout");
        stop_memory(0); cycles(TIMEOUT+8);
        check(!clock_alive,"stale clock is not treated as fresh");
        backend_ready=1; cycles(TIMEOUT+8);
        check(!started && !fault && !channel_open && mute,"ready backend with stopped stale clock cannot start");
        memory_run=1; await_start(); phases=phases+1;

        cycles(500);
        check(!fault && start_ready && wraps>50,"registered Gray heartbeat crosses repeated counter wraps");
        phases=phases+1;

        // A read accepted before the failure may remain in a backend queue.
        saved_accepted=accepted; saved_delivered=delivered;
        @(negedge memory_clk); client_request=1;
        @(posedge memory_clk); #2; client_request=0;
        check(accepted==saved_accepted+1,"one read accepted before readiness loss");
        @(negedge clk); #3; backend_ready=0;
        #0.1; check(!channel_open && mute && !client_ready,"sub-cycle ready loss closes and mutes asynchronously");
        backend_response=1;
        #0.9; backend_ready=1;
        #0.1; check(!channel_open && mute && !client_response,"restored raw availability cannot reopen between reference edges");
        expect_permanent_fault(1);
        check(delivered==saved_delivered,"queued old response remains suppressed during and after loss");
        phases=phases+1;

        common_reset(); start_backend();
        @(negedge clk); #3; backend_reset_n=0;
        #0.1; check(!channel_open && mute,"sub-cycle backend reset closes without memory edge");
        #0.9; backend_reset_n=1;
        expect_permanent_fault(1); phases=phases+1;

        // A loss after the one-time grant but before startup acknowledgment is
        // also permanent: the memory gate must not receive a second grant.
        common_reset(); backend_ready=1;
        @(posedge dut.armed); #1;
        check(!started,"startup grant precedes started acknowledgement");
        backend_ready=0; #1; backend_ready=1; cycles(20);
        check(fault && fault_code==1 && !started && !channel_open && mute,"pre-ack grant loss cannot retry or start");
        phases=phases+1;

        common_reset(); start_backend(); stop_memory(1);
        elapsed=0;
        while (!fault && elapsed<TIMEOUT+6) begin cycles(1); elapsed=elapsed+1; end
        high_stop_cycles=elapsed;
        check(fault && fault_code==2 && elapsed<=TIMEOUT+5,"stopped-high clock faults within conservative bound");
        check(memory_clk && !channel_open,"stopped-high source needs no new edge to close gate");
        expect_permanent_fault(2); phases=phases+1;

        common_reset(); start_backend(); stop_memory(0);
        elapsed=0;
        while (!fault && elapsed<TIMEOUT+6) begin cycles(1); elapsed=elapsed+1; end
        low_stop_cycles=elapsed;
        check(fault && fault_code==2 && elapsed<=TIMEOUT+5,"stopped-low clock faults within conservative bound");
        check(!memory_clk && !channel_open,"stopped-low source needs no new edge to close gate");
        expect_permanent_fault(2); phases=phases+1;

        common_reset(); start_backend(); stop_memory(1);
        backend_reset_n=0; #0.1;
        check(!channel_open && mute,"backend loss closes while source clock is stopped");
        expect_permanent_fault(1); phases=phases+1;

        // Exercise the actual default 500-cycle timeout, independently of the
        // shortened DUT and its deliberately small wrapping source counter.
        common_reset(); start_backend(); stop_memory(0);
        elapsed=0;
        while (!default_fault && elapsed<506) begin cycles(1); elapsed=elapsed+1; end
        default_stop_cycles=elapsed;
        check(default_fault && default_code==2 && elapsed<=505,"default stopped-clock digital detection bound is 505 reference cycles");
        check(default_started && !default_open && default_mute && !default_ready,"default fault retains startup and asynchronously closes memory gate");
        memory_run=1; cycles(40);
        check(default_fault && !default_open,"default configuration also requires common reset after recovery");
        phases=phases+1;

        common_reset(); start_backend();
        check(!fault && fault_code==0 && runtime_reset_n,"only common reset permits fresh startup");
        phases=phases+1;
        $display("PASS runtime_memory_guard: phases=%0d checks=%0d wraps=%0d accepted=%0d delivered=%0d high_stop_cycles=%0d low_stop_cycles=%0d default_stop_cycles=%0d",
            phases,checks,wraps,accepted,delivered,high_stop_cycles,low_stop_cycles,default_stop_cycles);
        $finish;
    end
    initial begin #1000000; $fatal(1,"memory guard test timeout"); end
endmodule
