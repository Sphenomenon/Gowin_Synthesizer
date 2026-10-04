`timescale 1ns/1ps
module tb_scope_controls;
    reg clk=0;always #5 clk=~clk;
    reg rst_n=0,ce=0,start=0,stop=0;
    reg [9:0] speed=256;
    wire valid,running,done,error;
    reg ready=0;
    wire [17:0] event_data;
    wire [31:0] late,time_samples;
    integer accepted=0;
    scope_control_player #(.CUE_COUNT(4),.CUE_FILE("scope_test_cues.mem")) dut(
        .clk_i(clk),.rst_ni(rst_n),.sample_ce_i(ce),.start_i(start),.stop_i(stop),.speed_q8_i(speed),
        .event_valid_o(valid),.event_ready_i(ready),.event_o(event_data),.running_o(running),.done_o(done),
        .config_error_o(error),.late_events_o(late),.time_samples_o(time_samples));
    task automatic pulse_sample;
        begin ce=1;@(negedge clk);ce=0;repeat(8)@(negedge clk);end
    endtask
    task automatic take(input integer expected);
        begin
            if(!valid || event_data!=18'(expected))$fatal(1,"cue payload or early timestamp");
            ready=1;@(negedge clk);ready=0;repeat(3)@(negedge clk);accepted=accepted+1;
        end
    endtask
    initial begin
        repeat(4)@(negedge clk);rst_n=1;repeat(20)@(negedge clk);
        if(valid || running)$fatal(1,"cue must never autostart");
        start=1;@(negedge clk);start=0;repeat(3)@(negedge clk);
        take((2<<14)|(97<<7)|3);
        take((1<<14)|(69<<7)|127); // identical timestamp, preserve ordering
        pulse_sample();if(valid)$fatal(1,"early cue at sample 1");
        pulse_sample();if(valid)$fatal(1,"early cue at sample 2");
        pulse_sample();if(!valid)$fatal(1,"cue at exact sample 3");
        pulse_sample();pulse_sample(); // backpressure, event must remain stable
        take((0<<14)|(69<<7));
        if(late!=1)$fatal(1,"backpressure lateness must count");
        speed=512;pulse_sample(); // timestamp advances 5 -> 7 at 2x speed
        take((2<<14)|(95<<7)|127);
        if(!done || running || time_samples!=7)$fatal(1,"cue end/speed");
        start=1;@(negedge clk);start=0;repeat(3)@(negedge clk);
        stop=1;@(negedge clk);stop=0;
        if(running || valid)$fatal(1,"live stop");
        speed=0;start=1;@(negedge clk);start=0;
        if(!error || running)$fatal(1,"invalid speed must fail explicit");
        $display("PASS scope_controls live arm, absolute samples, equal timestamps, 2x speed, backpressure, stop, invalid speed");$finish;
    end
endmodule
