`timescale 1ns/1ps
module tb_encoder_input;
    reg clk = 0;
    always #5 clk = !clk;
    reg reset = 1;
    reg a = 1, b = 1, key_n = 1;
    wire signed [15:0] position;
    wire [15:0] press_count, invalid_count;
    wire [1:0] ab_state;
    wire key_pressed, step_pulse, press_pulse;
    wire signed [1:0] direction;
    integer checks = 0;
    integer i;
    integer step_events = 0, press_events = 0;
    reg previous_step = 0, previous_press = 0;

    encoder_input #(.CLK_HZ(100000000), .AB_FILTER_CYCLES(4),
        .KEY_FILTER_CYCLES(6)) dut (
        .clk(clk), .reset(reset), .a(a), .b(b), .key_n(key_n),
        .position(position), .press_count(press_count),
        .invalid_count(invalid_count), .ab_state(ab_state),
        .key_pressed(key_pressed), .direction(direction),
        .step_pulse(step_pulse), .press_pulse(press_pulse)
    );

    // Boundary configuration checks that one-cycle filters still seed safely.
    reg fast_reset = 1;
    reg [1:0] fast_ab = 2'b11;
    reg fast_key_n = 1;
    wire signed [15:0] fast_position;
    wire [15:0] fast_press_count, fast_invalid_count;
    wire [1:0] fast_ab_state;
    wire fast_key_pressed, fast_step_pulse, fast_press_pulse;
    wire signed [1:0] fast_direction;
    encoder_input #(.AB_FILTER_CYCLES(1), .KEY_FILTER_CYCLES(1)) fast (
        .clk(clk), .reset(fast_reset), .a(fast_ab[1]), .b(fast_ab[0]),
        .key_n(fast_key_n), .position(fast_position),
        .press_count(fast_press_count), .invalid_count(fast_invalid_count),
        .ab_state(fast_ab_state), .key_pressed(fast_key_pressed),
        .direction(fast_direction), .step_pulse(fast_step_pulse),
        .press_pulse(fast_press_pulse)
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
        input [511:0] message;
        begin
            checks = checks + 1;
            if (condition !== 1'b1) begin
                $display("FAIL: %0s (time %0t)", message, $time);
                $fatal(1);
            end
        end
    endtask

    task drive_ab;
        input [1:0] value;
        begin
            @(negedge clk);
            {a, b} = value;
            tick(9);
            check(ab_state === value, "AB pair reaches the requested stable state");
        end
    endtask

    task start_at;
        input [1:0] value;
        input held_key;
        begin
            @(negedge clk);
            reset = 1;
            {a, b} = value;
            key_n = !held_key;
            tick(3);
            @(negedge clk);
            reset = 0;
            tick(12);
            check(ab_state === value, "startup seeds actual AB state");
            check(position === 16'sd0, "startup creates no phantom rotation");
            check(invalid_count === 0, "startup creates no invalid transition");
            check(direction === 0, "startup direction is neutral");
        end
    endtask

    task positive_detent;
        begin
            if (ab_state == 2'b11) begin
                drive_ab(2'b01);
                drive_ab(2'b00);
            end else begin
                drive_ab(2'b10);
                drive_ab(2'b11);
            end
        end
    endtask

    task negative_detent;
        begin
            if (ab_state == 2'b11) begin
                drive_ab(2'b10);
                drive_ab(2'b00);
            end else begin
                drive_ab(2'b01);
                drive_ab(2'b11);
            end
        end
    endtask

    task drive_key;
        input value;
        begin
            @(negedge clk);
            key_n = value;
            tick(12);
        end
    endtask

    always @(negedge clk) begin
        if (reset) begin
            previous_step = 0;
            previous_press = 0;
            step_events = 0;
            press_events = 0;
        end else begin
            if (step_pulse && previous_step) $fatal(1, "step pulse longer than one clock");
            if (press_pulse && previous_press) $fatal(1, "press pulse longer than one clock");
            if (step_pulse && direction == 0) $fatal(1, "step pulse has no direction");
            if (step_pulse) step_events = step_events + 1;
            if (press_pulse) press_events = press_events + 1;
            previous_step = step_pulse;
            previous_press = press_pulse;
        end
    end

    initial begin
        // Every possible contact state at power-on; intermediate states must
        // reach an anchor before any full two-transition detent can be counted.
        for (i = 0; i < 4; i = i + 1) begin
            start_at(i[1:0], 0);
            if (i == 1) drive_ab(2'b00);
            if (i == 2) drive_ab(2'b11);
            check(position === 0, "first incomplete detent is discarded");
            positive_detent;
            check(position === 16'sd1, "two transitions produce one positive detent");
            check(step_events == 1, "positive detent emits exactly one step pulse");
            check(direction === 2'sd1, "positive direction is latched");
            negative_detent;
            check(position === 0, "two reverse transitions undo one detent");
            check(step_events == 2, "negative detent emits exactly one step pulse");
            check(direction === -2'sd1, "negative direction is latched");
        end

        start_at(2'b11, 0);
        for (i = 0; i < 15; i = i + 1) begin
            positive_detent;
            positive_detent;
        end
        check(position === 16'sd30, "15 quadrature pulses equal 30 mechanical detents");
        check(step_events == 30, "revolution emits exactly 30 step pulses");
        for (i = 0; i < 30; i = i + 1) negative_detent;
        check(position === 0, "one reverse revolution returns to zero");

        // Contact chatter that survives filtering must cancel algebraically.
        for (i = 0; i < 4; i = i + 1) begin
            drive_ab(2'b01);
            drive_ab(2'b11);
        end
        check(position === 0, "stable contact chatter creates no detent");
        drive_ab(2'b01);
        check(position === 0, "single transition has no detent yet");
        drive_ab(2'b11);
        negative_detent;
        check(position === -16'sd1, "partial forward motion cancels before reversal");
        check(invalid_count === 0, "legal chatter and reversal are not invalid");

        start_at(2'b11, 0);
        drive_ab(2'b00);
        check(invalid_count === 1 && position === 0, "two-bit jump is rejected");
        positive_detent;
        check(position === 16'sd1, "legal decoding recovers after illegal jump");
        drive_ab(2'b01);
        drive_ab(2'b10);
        check(invalid_count === 2 && position === 16'sd1, "illegal jump discards partial phase");
        drive_ab(2'b11);
        check(position === 16'sd1, "recovery anchor creates no phantom detent");
        positive_detent;
        check(position === 16'sd2, "full detent counts after intermediate recovery");

        start_at(2'b11, 0);
        @(negedge clk); {a, b} = 2'b01;
        tick(1);
        @(negedge clk); {a, b} = 2'b11;
        tick(10);
        check(ab_state === 2'b11 && position === 0 && invalid_count === 0,
            "AB pulses shorter than filter are ignored");
        @(negedge clk); {a, b} = 2'b01;
        tick(2);
        @(negedge clk); {a, b} = 2'b00;
        tick(2);
        @(negedge clk); {a, b} = 2'b11;
        tick(10);
        check(ab_state === 2'b11 && position === 0 && invalid_count === 0,
            "rapid coherent AB changes cannot synthesize a phase step");

        // Low-active button: sub-filter bounce, hold, release bounce, re-press.
        @(negedge clk); key_n = 0;
        tick(2);
        @(negedge clk); key_n = 1;
        tick(12);
        check(!key_pressed && press_count === 0, "short key bounce is ignored");
        check(press_events == 0, "short key bounce emits no press pulse");
        drive_key(0);
        check(key_pressed && press_count === 1, "debounced press increments once");
        tick(50);
        check(key_pressed && press_count === 1 && !press_pulse, "holding key does not repeat");
        @(negedge clk); key_n = 1;
        tick(2);
        @(negedge clk); key_n = 0;
        tick(12);
        check(key_pressed && press_count === 1, "short release bounce keeps button pressed");
        drive_key(1);
        check(!key_pressed && press_count === 1, "release does not increment press count");
        drive_key(0);
        check(key_pressed && press_count === 2, "second press increments exactly once");
        check(press_events == 2, "button emits one pulse for each accepted press");
        start_at(2'b10, 1);
        check(key_pressed && press_count === 1, "key held at startup becomes pressed once");
        tick(30);
        check(press_count === 1, "held startup key never repeats");

        // Deposit near limits to exercise actual next-state arithmetic cheaply.
        // No force remains active while the DUT updates its registers.
        start_at(2'b11, 0);
        @(negedge clk); dut.position = 16'sd32766;
        positive_detent;
        positive_detent;
        check(position === 16'sd32767, "positive position saturates at +32767");
        negative_detent;
        check(position === 16'sd32766, "reverse motion leaves positive saturation");
        @(negedge clk); dut.position = -16'sd32766;
        negative_detent;
        negative_detent;
        check(position === -16'sd32767, "negative position saturates at -32767");
        positive_detent;
        check(position === -16'sd32766, "forward motion leaves negative saturation");
        @(negedge clk); dut.invalid_count = 16'hfffe;
        drive_ab(~ab_state);
        drive_ab(~ab_state);
        check(invalid_count === 16'hffff, "invalid counter saturates");
        @(negedge clk); dut.press_count = 16'hfffe;
        drive_key(0);
        drive_key(1);
        drive_key(0);
        check(press_count === 16'hffff, "press counter saturates");

        start_at(2'b01, 0);
        check(position === 0 && press_count === 0 && invalid_count === 0,
            "synchronous reset clears all accumulated counters");
        check(!key_pressed && !step_pulse && !press_pulse,
            "reset leaves released key and idle pulses");

        @(negedge clk); fast_ab = 2'b00; fast_key_n = 0; fast_reset = 0;
        tick(6);
        check(fast_ab_state === 2'b00 && fast_position === 0 && fast_invalid_count === 0,
            "one-cycle filter seeds AB without false transition");
        check(fast_key_pressed && fast_press_count === 1,
            "one-cycle filter accepts held startup button");
        @(negedge clk); fast_ab = 2'b10;
        tick(5);
        @(negedge clk); fast_ab = 2'b11;
        tick(5);
        check(fast_position === 16'sd1 && fast_direction === 2'sd1,
            "one-cycle filter decodes two-transition detent");

        $display("PASS: tb_encoder_input (%0d checks, startup/chatter/reversal/illegal/filter/key/reset/saturation)", checks);
        $finish;
    end

    initial begin
        #1000000;
        $fatal(1, "testbench timeout");
    end
endmodule
