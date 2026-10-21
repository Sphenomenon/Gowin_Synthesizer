`timescale 1ns/1ps
module tb_workstation_ulpi_supervisor;
    reg clk_ref = 1'b0;
    always #10 clk_ref = ~clk_ref;
    reg clk_ulpi = 1'b0;
    reg clock_enabled = 1'b1;
    always begin
        #8.333;
        if (clock_enabled)
            clk_ulpi = !clk_ulpi;
    end
    reg reset_n = 1'b0;
    reg enable = 1'b0;
    wire link_reset_n;
    wire force_stp;
    wire running;
    wire clock_present;
    wire failed;
    wire [1:0] failure_code;
    integer checks = 0;
    integer scenarios = 0;
    integer release_edges = 0;
    integer hold_cycles = 0;

    workstation_ulpi_supervisor #(
        .HEARTBEAT_WIDTH(2), .EXIT_HOLD_REF_CYCLES(8), .QUALIFY_EDGES(3),
        .CLOCK_TIMEOUT_REF_CYCLES(40)
    ) dut (
        .clk_ref(clk_ref), .clk_ulpi(clk_ulpi), .reset_n(reset_n), .enable_i(enable),
        .link_reset_n_o(link_reset_n), .force_stp_o(force_stp), .running_o(running),
        .clock_present_o(clock_present), .failed_o(failed), .failure_code_o(failure_code)
    );

    task automatic check(input reg condition, input string message);
        begin
            checks = checks + 1;
            if (condition !== 1'b1)
                $fatal(1, "%s (running=%0d failed=%0d code=%0d)", message, running, failed, failure_code);
        end
    endtask

    task automatic begin_scenario(input reg start_clock);
        begin
            @(negedge clk_ref);
            reset_n = 1'b0;
            enable = 1'b0;
            clock_enabled = start_clock;
            repeat (4) @(negedge clk_ref);
            check(!link_reset_n && force_stp && !running && !failed, "asynchronous reset safety");
            reset_n = 1'b1;
            repeat (4) @(negedge clk_ref);
            check(!link_reset_n && force_stp && !running && !failed, "disabled safety");
            enable = 1'b1;
            scenarios = scenarios + 1;
        end
    endtask

    task automatic await_running;
        integer waited;
        begin
            waited = 0;
            while (!link_reset_n && !failed && waited < 100) begin
                @(negedge clk_ref);
                waited = waited + 1;
            end
            check(running && link_reset_n && !force_stp && clock_present && !failed, "qualified clock released");
            check(waited >= 8, "minimum STP recovery hold");
        end
    endtask

    task automatic await_failure(input reg [1:0] expected_code);
        integer waited;
        begin
            waited = 0;
            while (!failed && waited < 100) begin
                @(negedge clk_ref);
                waited = waited + 1;
            end
            check(failed && failure_code == expected_code, "clock failure bounded and located");
            check(!link_reset_n && force_stp && !running && !clock_present, "stopped clock reset without ULPI edges");
        end
    endtask

    always @(posedge clk_ulpi or negedge running) begin
        if (!running)
            release_edges = 0;
        else
            release_edges = release_edges + 1;
    end

    always @(posedge link_reset_n)
        check(release_edges >= 2, "reset deassertion synchronized to ULPI");

    always @(posedge clk_ref) begin
        if (!reset_n || !enable)
            hold_cycles <= 0;
        else if (!running)
            hold_cycles <= hold_cycles + 1;
        if (reset_n && running)
            check(hold_cycles >= 8, "startup hold cannot be skipped");
    end

    initial begin
        begin_scenario(1'b1);
        await_running();
        repeat (100) @(negedge clk_ref);
        check(running && !failed, "steady state clock does not false-trigger");
        @(negedge clk_ulpi);
        clock_enabled = 1'b0;
        await_failure(2);
        clock_enabled = 1'b1;
        repeat (100) @(negedge clk_ref);
        check(failed && !link_reset_n && force_stp, "clock return alone cannot restart failed link");
        enable = 1'b0;
        repeat (4) @(negedge clk_ref);
        check(!failed && failure_code == 0, "explicit disable clears failure");
        enable = 1'b1;
        await_running();
        @(posedge clk_ulpi);
        clock_enabled = 1'b0;
        await_failure(2);
        begin_scenario(1'b0);
        await_failure(1);
        begin_scenario(1'b0);
        repeat (12) @(negedge clk_ref);
        check(!running && force_stp && !failed, "absent clock is not qualified by elapsed time");
        clock_enabled = 1'b1;
        await_running();
        @(negedge clk_ulpi);
        clock_enabled = 1'b0;
        #3;
        reset_n = 1'b0;
        #1;
        check(!running && !link_reset_n && force_stp && !failed, "global reset works while clock stopped");
        begin_scenario(1'b1);
        await_running();
        @(negedge clk_ref);
        enable = 1'b0;
        @(negedge clk_ref);
        check(!link_reset_n && !running && force_stp && !failed, "disable terminates running link");
        $display("PASS workstation_ulpi_supervisor: %0d checks, %0d scenarios, missing/stopped clock, explicit recovery, asynchronous assertion/synchronous release", checks, scenarios);
        $finish;
    end

    initial begin
        #100000;
        $fatal(1, "global simulation timeout");
    end
endmodule
