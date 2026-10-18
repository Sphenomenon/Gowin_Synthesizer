`timescale 1ns / 1ps

module tb_midi_slider_filter;
    reg clk = 0;
    always #5 clk = ~clk;
    reg reset = 1;
    reg sample_valid = 0;
    reg raw_touch = 0;
    reg [7:0] raw_position = 0;
    wire valid, touched;
    wire [7:0] position;
    integer sample_count = 0;
    integer value;

    midi_slider_filter dut (
        .clk(clk), .reset(reset), .sample_valid(sample_valid),
        .raw_touch(raw_touch), .raw_position(raw_position),
        .valid(valid), .touched(touched), .position(position)
    );

    task expect_output;
        input expected_valid;
        input expected_touch;
        input [7:0] expected_position;
        begin
            if (valid !== expected_valid || touched !== expected_touch ||
                position !== expected_position)
                $fatal(1, "Sample %0d input %0d/%0d: got valid/touch/position %0d/%0d/%0d expected %0d/%0d/%0d",
                       sample_count, raw_touch, raw_position,
                       valid, touched, position,
                       expected_valid, expected_touch, expected_position);
        end
    endtask

    // Expectations below describe gestures and their visible output; no DUT
    // state or internal candidate is read by the testbench.
    task sample;
        input new_touch;
        input [7:0] new_position;
        input expected_touch;
        input [7:0] expected_position;
        begin
            @(negedge clk);
            sample_valid = 1;
            raw_touch = new_touch;
            raw_position = new_position;
            @(posedge clk); #1;
            sample_count = sample_count + 1;
            expect_output(1, expected_touch, expected_position);
            @(negedge clk); sample_valid = 0;
            @(posedge clk); #1;
            expect_output(0, expected_touch, expected_position);
        end
    endtask

    task reset_filter;
        begin
            @(negedge clk);
            reset = 1;
            sample_valid = 0;
            @(posedge clk); #1;
            expect_output(0, 0, 0);
            @(negedge clk); reset = 0;
        end
    endtask

    initial begin
        reset_filter;

        // A finger landing is reported without an extra software delay.
        sample(1, 100, 1, 100);
        sample(1, 101, 1, 100);
        sample(1,  99, 1, 100);
        sample(1, 102, 1, 100);
        sample(1,  98, 1, 100);
        sample(1, 103, 1, 103); // Deadband is strictly less than three.
        sample(1, 100, 1, 100);
        sample(1, 132, 1, 132); // A 32-step movement is immediate.
        sample(1, 100, 1, 100);
        sample(1, 133, 1, 100); // A 33-step movement needs confirmation.
        sample(1, 130, 1, 130); // Confirmation may be three below candidate.
        sample(1,  97, 1, 130);
        sample(1, 100, 1, 100); // Confirmation may be three above candidate.

        // A single full-range spike must not move the accepted position.
        sample(0,   0, 0, 100);
        sample(1,   0, 1,   0);
        sample(1, 255, 1,   0);
        sample(1,   1, 1,   0);
        sample(1, 255, 1,   0);
        sample(1, 255, 1, 255);
        sample(1,   0, 1, 255);
        sample(1, 254, 1, 255);
        sample(1,   0, 1, 255);
        sample(1,   0, 1,   0);

        // Inconsistent distant samples replace the candidate. Four apart
        // fails confirmation; a following sample three apart succeeds.
        sample(1, 100, 1,   0);
        sample(1, 200, 1,   0);
        sample(1, 104, 1,   0);
        sample(1, 108, 1,   0);
        sample(1, 111, 1, 111);

        // Normal motion cancels a pending jump; returning near the old jump
        // cannot use its stale confirmation.
        sample(1, 230, 1, 111);
        sample(1, 120, 1, 120);
        sample(1, 232, 1, 120);
        sample(1, 230, 1, 230);
        sample(1,  30, 1, 230);
        sample(1, 231, 1, 230); // Deadband also cancels a candidate.
        sample(1,  32, 1, 230);
        sample(1,  30, 1,  30);

        // Missing samples cannot change state, even with changing raw inputs.
        @(negedge clk);
        sample_valid = 0; raw_touch = 0; raw_position = 255;
        repeat (5) begin
            @(posedge clk); #1;
            expect_output(0, 1, 30);
        end
        sample(1, 200, 1, 30);
        @(negedge clk);
        sample_valid = 0; raw_touch = 0; raw_position = 0;
        repeat (5) begin
            @(posedge clk); #1;
            expect_output(0, 1, 30);
        end
        sample(1, 202, 1, 202); // Confirmation counts samples, not clocks.

        // Release is immediate, retains the accepted position, and cancels
        // any unconfirmed jump before the next touch starts.
        sample(1, 10, 1, 202);
        sample(0, 10, 0, 202);
        sample(1, 11, 1, 11);
        sample(1, 240, 1, 11);
        reset_filter;
        sample(1, 240, 1, 240);

        // Slow movement accumulates naturally across the deadband, with
        // neither a stall nor an overshoot at either end of the strip.
        sample(0, 0, 0, 240);
        sample(1, 0, 1, 0);
        for (value = 1; value <= 255; value = value + 1)
            sample(1, value, 1, (value / 3) * 3);
        for (value = 254; value >= 0; value = value - 1)
            sample(1, value, 1, 255 - ((255 - value) / 3) * 3);

        // Every absolute touch location, including both endpoints, is exact.
        for (value = 0; value < 256; value = value + 1) begin
            sample(0, 255 - value, 0, value == 0 ? 0 : value - 1);
            sample(1, value, 1, value);
            sample(1, value, 1, value);
        end

        // Back-to-back valid samples each publish one result.
        @(negedge clk); sample_valid = 1; raw_touch = 1; raw_position = 223;
        @(posedge clk); #1; expect_output(1, 1, 223);
        @(negedge clk); raw_position = 191;
        @(posedge clk); #1; expect_output(1, 1, 191);
        @(negedge clk); sample_valid = 0;
        @(posedge clk); #1; expect_output(0, 1, 191);

        $display("PASS slider filter: jitter, boundary motion, spike confirmation, release/reset, ramps and all 256 touch positions");
        $finish;
    end
endmodule
