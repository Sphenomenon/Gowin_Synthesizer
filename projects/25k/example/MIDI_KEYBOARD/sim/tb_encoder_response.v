`timescale 1ns/1ps
// Exercise production defaults at the real 50 MHz board clock. Physical input
// durations are intentional: overriding/deriving the DUT's filter parameters
// here would conceal a regression back to the previous slower defaults.
module tb_encoder_response;
    reg clk = 0;
    always #10 clk = !clk;
    reg reset = 1;
    reg [1:0] ab = 2'b11;
    reg key_n = 1;
    wire signed [15:0] position;
    wire [15:0] press_count, invalid_count;
    wire [1:0] ab_state;
    wire key_pressed, step_pulse, press_pulse;
    wire signed [1:0] direction;
    integer checks = 0, i;
    integer step_events = 0, press_events = 0;
    reg previous_step = 0, previous_press = 0;

    encoder_input dut (
        .clk(clk), .reset(reset), .a(ab[1]), .b(ab[0]), .key_n(key_n),
        .position(position), .press_count(press_count),
        .invalid_count(invalid_count), .ab_state(ab_state),
        .key_pressed(key_pressed), .direction(direction),
        .step_pulse(step_pulse), .press_pulse(press_pulse)
    );

    task check;
        input condition;
        input [639:0] message;
        begin
            checks = checks + 1;
            if (condition !== 1'b1) begin
                $display("FAIL: %0s (time %0t)", message, $time);
                $fatal(1);
            end
        end
    endtask

    task start_at;
        input [1:0] state;
        input held_key;
        begin
            @(negedge clk); #3;
            reset = 1;
            ab = state;
            key_n = !held_key;
            #100;
            reset = 0;
            #30000;
            check(ab_state === state && position === 0 && invalid_count === 0,
                "asynchronous startup seeds all contact states within 30 us without rotation");
            check(step_events == 0 && direction === 0,
                "startup creates no step pulse or direction");
            check(!key_pressed && press_count === 0,
                "startup button is not accepted before its 1 ms filter");
            #1070000;
            check(key_pressed === held_key && press_count === (held_key ? 16'd1 : 16'd0),
                "startup-held button is accepted within 1.1 ms exactly once");
            check(press_events == (held_key ? 1 : 0),
                "startup-held button emits exactly one press event");
        end
    endtask

    task set_ab_async;
        input [1:0] state;
        begin
            @(negedge clk); #3;
            ab = state;
        end
    endtask

    task set_key_async;
        input value;
        begin
            @(negedge clk); #3;
            key_n = value;
        end
    endtask

    always @(negedge clk) begin
        if (reset) begin
            step_events = 0;
            press_events = 0;
            previous_step = 0;
            previous_press = 0;
        end else begin
            if (step_pulse && previous_step) $fatal(1, "step pulse is not one clock");
            if (press_pulse && previous_press) $fatal(1, "press pulse is not one clock");
            if (step_pulse) step_events = step_events + 1;
            if (press_pulse) press_events = press_events + 1;
            previous_step = step_pulse;
            previous_press = press_pulse;
        end
    end

    initial begin
        for (i = 0; i < 4; i = i + 1) start_at(i[1:0], i[0]);
        start_at(2'b11, 0);

        // A nearly 20 us pulse must still be rejected, including synchronizer
        // latency. A slower default would pass rejection but fail acceptance.
        set_ab_async(2'b01);
        #19500;
        check(ab_state === 2'b11, "AB is unchanged before 20 us");
        ab = 2'b11;
        #21000;
        check(ab_state === 2'b11 && position === 0 && step_events == 0 && invalid_count === 0,
            "19.5 us contact pulse produces no accepted transition");

        set_ab_async(2'b01);
        #19500;
        check(ab_state === 2'b11, "20 us filter does not accept a new phase prematurely");
        #1000;
        check(ab_state === 2'b01 && position === 0,
            "stable phase is accepted by 20.5 us, before the old 100 us window");
        set_ab_async(2'b00);
        #20500;
        check(ab_state === 2'b00 && position === 0 && step_events == 0 && direction === 0,
            "one 20.5 us detent is buffered for half-speed output");
        set_ab_async(2'b10);
        #20500;
        set_ab_async(2'b11);
        #20500;
        check(position === -16'sd1 && step_events == 1 && direction === -2'sd1,
            "four 20.5 us phases emit one step in the reversed direction");
        set_ab_async(2'b10);
        #20500;
        set_ab_async(2'b00);
        #20500;
        check(position === -16'sd1 && step_events == 1,
            "first reverse detent emits no application step");
        set_ab_async(2'b01);
        #20500;
        set_ab_async(2'b11);
        #20500;
        check(position === 0 && step_events == 2 && direction === 2'sd1,
            "two short reverse detents undo one output step exactly once");

        // Button pulses straddling the actual 1 ms default. This also proves
        // that a short intentional press works without waiting the old 5 ms.
        set_key_async(0);
        #900000;
        check(!key_pressed && press_count === 0, "900 us press is below button filter");
        key_n = 1;
        #1100000;
        check(!key_pressed && press_count === 0 && press_events == 0,
            "short key chatter is rejected after return to released");
        set_key_async(0);
        #990000;
        check(!key_pressed && press_count === 0, "button is unchanged just before 1 ms");
        #110000;
        check(key_pressed && press_count === 1 && press_events == 1,
            "1.1 ms press is accepted exactly once, before the old 5 ms window");
        #5000000;
        check(key_pressed && press_count === 1 && press_events == 1 && !press_pulse,
            "held button emits no repeated counts or pulses");
        set_key_async(1);
        #900000;
        key_n = 0;
        #1100000;
        check(key_pressed && press_count === 1 && press_events == 1,
            "sub-1 ms release chatter does not create a new press");
        set_key_async(1);
        #1100000;
        check(!key_pressed && press_count === 1, "stable release is accepted within 1.1 ms");
        set_key_async(0);
        #1100000;
        check(key_pressed && press_count === 2 && press_events == 2,
            "second short press is independent and accepted exactly once");
        check(position === 0 && step_events == 2 && invalid_count === 0,
            "key activity leaves encoder position and phase validity unchanged");

        $display("PASS: tb_encoder_response (%0d checks, real 50 MHz defaults: reversed/half speed, AB 20 us / KEY 1 ms)", checks);
        $finish;
    end

    initial begin
        #30000000;
        $fatal(1, "testbench timeout");
    end
endmodule
