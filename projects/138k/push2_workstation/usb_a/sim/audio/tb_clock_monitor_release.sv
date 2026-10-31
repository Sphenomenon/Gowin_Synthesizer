`timescale 1ns/1ps
module clock_monitor_release_case #(parameter bit SEPARATE=0)(output reg done=0);
    reg clk=0,source_clk=0,common_n=0,startup_n=0,restart=0,rate44=0,run_source=1;
    real half_period=40.690104167;
    integer checks=0,release_checks=0,wraps=0;
    realtime last_falling=0;
    always #10 clk=!clk;
    always begin #(half_period);if(run_source)source_clk=!source_clk;end
    wire qualified,present,stopped,valid,good;
    wire reference_qualified,reference_present,reference_stopped,reference_valid,reference_good;
    wire [11:0] edges,reference_edges;
    wire reset_n=SEPARATE ? startup_n:common_n;
    workstation_audio_clock_monitor #(.WINDOW_CYCLES(256),.COUNTER_BITS(12),
        .STABLE_WINDOWS(2),.LOSS_TIMEOUT_CYCLES(100),.SEPARATE_COMMON_RESET(SEPARATE)) dut(
        .clk_i(clk),.rst_ni(reset_n),.common_reset_ni(common_n),.source_clk_i(source_clk),
        .restart_i(restart),.expect_44k1_i(rate44),.qualified_o(qualified),.clock_present_o(present),
        .stopped_low_o(stopped),.window_valid_o(valid),.window_good_o(good),.window_edges_o(edges));
    reference_workstation_audio_clock_monitor #(.WINDOW_CYCLES(256),.COUNTER_BITS(12),
        .STABLE_WINDOWS(2),.LOSS_TIMEOUT_CYCLES(100),.SEPARATE_COMMON_RESET(SEPARATE)) old(
        .clk_i(clk),.rst_ni(reset_n),.common_reset_ni(common_n),.source_clk_i(source_clk),
        .restart_i(restart),.expect_44k1_i(rate44),.qualified_o(reference_qualified),.clock_present_o(reference_present),
        .stopped_low_o(reference_stopped),.window_valid_o(reference_valid),.window_good_o(reference_good),
        .window_edges_o(reference_edges));
    always @(negedge source_clk)last_falling=$realtime;
    always @(posedge dut.source_reset_n)begin
        #0.001;
        if(source_clk!==0 || $realtime-last_falling>0.01)
            $fatal(1,"release did not use the opposite source edge separate=%0d",SEPARATE);
        release_checks=release_checks+1;
    end
    always @(posedge source_clk)begin
        #0.001;
        if(reset_n && dut.source_reset_n && old.source_reset_n)begin
            if(dut.source_binary!==old.source_binary || dut.source_gray!==old.source_gray)
                $fatal(1,"first counting edge or modulo counter changed separate=%0d",SEPARATE);
            if(dut.source_binary==0)wraps=wraps+1;
        end
    end
    always @(posedge clk)begin
        #1;
        if({qualified,present,stopped,valid,good,edges}!==
           {reference_qualified,reference_present,reference_stopped,reference_valid,reference_good,reference_edges})
            $fatal(1,"public monitor behavior changed separate=%0d checks=%0d",SEPARATE,checks);
        checks=checks+1;
    end
    task cycles(input integer n);begin repeat(n)@(negedge clk);end endtask
    task reset_while_stopped(input bit high);begin
        wait(source_clk==high);run_source=0;cycles(7);
        common_n=0;startup_n=0;#0.001;
        if(dut.source_reset_n || dut.source_binary || dut.source_gray)
            $fatal(1,"common reset assertion waited for stopped source");
        cycles(7);common_n=1;startup_n=1;cycles(7);
        if(dut.source_reset_n || qualified || present)
            $fatal(1,"stopped source released or qualified without a genuine edge");
        run_source=1;cycles(2000);
    end endtask
    initial begin
        cycles(5);common_n=1;cycles(5);startup_n=1;cycles(100000);
        reset_while_stopped(1);reset_while_stopped(0);
        // Startup reset is independent of common assertion in the native path.
        startup_n=0;cycles(50);startup_n=1;cycles(100000);
        restart=1;cycles(1);restart=0;cycles(1000);
        rate44=1;half_period=29.5256991685;cycles(100000);
        // Wrong frequency and a running-clock loss still revoke qualification.
        half_period=50.0;cycles(1000);run_source=0;cycles(150);
        run_source=1;half_period=29.5256991685;cycles(2000);
        if(checks<300000 || release_checks<3 || wraps<10)
            $fatal(1,"release coverage incomplete checks=%0d releases=%0d wraps=%0d",checks,release_checks,wraps);
        $display("PASS clock_monitor_release: separate=%0d checks=%0d releases=%0d wraps=%0d",SEPARATE,checks,release_checks,wraps);
        done=1;
    end
endmodule
module tb_clock_monitor_release;
    wire a,b;
    clock_monitor_release_case #(.SEPARATE(0)) legacy(a);
    clock_monitor_release_case #(.SEPARATE(1)) native(b);
    initial begin wait(a && b);$finish;end
    initial begin #10000000;$fatal(1,"release watchdog");end
endmodule
