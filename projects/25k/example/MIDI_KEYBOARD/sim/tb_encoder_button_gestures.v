`timescale 1ns/1ps
module tb_encoder_button_gestures;
    reg clk = 0;
    always #5 clk = !clk;
    reg reset = 1, pressed = 0;
    wire short_press, long_press;
    integer checks = 0;
    integer short_events = 0, long_events = 0;
    reg previous_short = 0, previous_long = 0;

    // 20 complete clocks from the initial asserted sample to long_press.
    encoder_button_gestures #(.CLK_HZ(10000), .LONG_PRESS_MS(2)) dut (
        .clk(clk), .reset(reset), .pressed(pressed),
        .short_press(short_press), .long_press(long_press)
    );

    reg edge_reset = 1, edge_pressed = 0;
    wire edge_short, edge_long;
    // 1001 Hz * 3 ms = 3.003 cycles, which must round up to four.
    encoder_button_gestures #(.CLK_HZ(1001), .LONG_PRESS_MS(3)) rounded (
        .clk(clk), .reset(edge_reset), .pressed(edge_pressed),
        .short_press(edge_short), .long_press(edge_long)
    );

    reg single_reset = 1, single_pressed = 0;
    wire single_short, single_long;
    encoder_button_gestures #(.CLK_HZ(1000), .LONG_PRESS_MS(1)) single (
        .clk(clk), .reset(single_reset), .pressed(single_pressed),
        .short_press(single_short), .long_press(single_long)
    );

    reg default_reset = 1, default_pressed = 0;
    wire default_short, default_long;
    encoder_button_gestures default_timing (
        .clk(clk), .reset(default_reset), .pressed(default_pressed),
        .short_press(default_short), .long_press(default_long)
    );

    task tick;
        input integer cycles;
        begin
            repeat (cycles) @(posedge clk);
            #1;
        end
    endtask

    task check;
        input condition;
        input [767:0] message;
        begin
            checks = checks + 1;
            if (condition !== 1'b1) begin
                $display("FAIL: %0s (time %0t)", message, $time);
                $fatal(1);
            end
        end
    endtask

    task drive;
        input value;
        begin
            @(negedge clk);
            pressed = value;
            tick(1);
        end
    endtask

    always @(negedge clk) begin
        if (reset) begin
            previous_short = 0;
            previous_long = 0;
        end else begin
            if (short_press && long_press)
                $fatal(1, "one gesture emitted short and long together");
            if (short_press && previous_short)
                $fatal(1, "short pulse lasted more than one clock");
            if (long_press && previous_long)
                $fatal(1, "long pulse lasted more than one clock");
            if (short_press) short_events = short_events + 1;
            if (long_press) long_events = long_events + 1;
            previous_short = short_press;
            previous_long = long_press;
        end
    end

    initial begin
        tick(3);
        check(!short_press && !long_press, "reset leaves both outputs inactive");
        @(negedge clk);
        reset = 0;
        edge_reset = 0;
        single_reset = 0;
        default_reset = 0;
        tick(2);
        check(!short_press && !long_press, "idle release does not emit a gesture");

        drive(1);
        check(!short_press && !long_press, "press starts timing without emitting short");
        tick(5);
        drive(0);
        check(short_press && !long_press, "release before threshold emits short");
        tick(1);
        check(!short_press && !long_press, "short pulse clears on next clock");
        check(short_events == 1 && long_events == 0, "short gesture emits once");

        drive(1);
        tick(18);
        drive(0);
        check(short_press && !long_press, "release one clock before threshold is short");
        tick(1);
        drive(1);
        tick(19);
        check(!short_press && !long_press, "held button does not trigger before full threshold");
        tick(1);
        check(long_press && !short_press, "held button triggers exactly at threshold");
        tick(47);
        check(!short_press && !long_press, "long hold never repeats");
        drive(0);
        check(!short_press && !long_press, "release after long does not emit short");
        tick(1);
        check(short_events == 2 && long_events == 1, "hold and release produce one long gesture");

        drive(1);
        tick(19);
        drive(0);
        check(long_press && !short_press, "release exactly at threshold is long");
        tick(1);
        drive(1);
        drive(0);
        check(short_press && !long_press, "fresh short press works immediately after long release");
        tick(1);

        // Reset in the middle of a gesture; its eventual release is ignored.
        drive(1);
        tick(6);
        @(negedge clk); reset = 1;
        tick(2);
        check(!short_press && !long_press, "reset cancels an in-progress gesture");
        @(negedge clk); reset = 0;
        tick(30);
        check(!short_press && !long_press, "button held through reset produces no long");
        drive(0);
        check(!short_press && !long_press, "release after reset produces no phantom short");
        drive(1);
        drive(0);
        check(short_press && !long_press, "released state rearms gestures after reset");
        tick(1);

        @(negedge clk); edge_pressed = 1;
        tick(1);
        tick(3);
        check(!edge_long && !edge_short, "fractional-clock threshold does not round down");
        tick(1);
        check(edge_long && !edge_short, "fractional-clock threshold rounds up to four clocks");
        tick(8);
        @(negedge clk); edge_pressed = 0;
        tick(1);
        check(!edge_long && !edge_short, "rounded threshold still suppresses long release short");

        @(negedge clk); single_pressed = 1;
        tick(1);
        check(!single_long && !single_short, "one-cycle threshold waits a complete clock");
        @(negedge clk); single_pressed = 0;
        tick(1);
        check(single_long && !single_short, "one-cycle boundary release emits long");
        tick(1);
        check(!single_long && !single_short, "one-cycle long pulse clears");

        // Exercise the actual default counter width and 64-bit constant
        // arithmetic without spending 50 million simulation clocks waiting.
        check(default_timing.LONG_CYCLES == 64'd50000000,
            "default 50 MHz/1000 ms constant has no 32-bit overflow");
        check(default_timing.COUNT_BITS == 26, "default counter covers all 50 million clocks");
        @(negedge clk); default_pressed = 1;
        tick(1);
        @(negedge clk); default_timing.hold_count = 26'd49999998;
        tick(1);
        check(!default_long, "default counter does not trigger one clock early");
        tick(1);
        check(default_long && !default_short, "default counter triggers at 50 million clocks");
        tick(3);
        @(negedge clk); default_pressed = 0;
        tick(1);
        check(!default_long && !default_short, "default long gesture does not repeat on release");

        $display("PASS: tb_encoder_button_gestures (%0d checks, short/long/boundary/reset/rounding/default timing)", checks);
        $finish;
    end

    initial begin
        #100000;
        $fatal(1, "testbench timeout");
    end
endmodule
