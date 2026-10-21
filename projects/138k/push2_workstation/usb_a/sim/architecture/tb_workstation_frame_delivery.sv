`timescale 1ns/1ps

module tb_workstation_frame_delivery;
    logic clk = 0, reset_n = 0, sample_ce = 0, render_valid = 0;
    logic muted = 0;
    always #5 clk = ~clk;
    logic [9:0] cancel_epoch = 0;
    logic signed [31:0] left = 0, right = 0;
    logic [31:0] reference_value = 0, voices = 0;
    wire valid;
    wire signed [31:0] delivered_left, delivered_right;
    wire [31:0] delivered_reference, delivered_voices, duplicates;
    logic model_offered = 0;
    logic model_cancelled = 0;
    logic [9:0] model_epoch = 0;
    integer model_duplicates = 0, cycles = 0;
    integer seed = 32'h51ce0221;

    workstation_frame_delivery dut(
        .clk_i(clk), .rst_ni(reset_n), .sample_ce_i(sample_ce), .muted_i(muted),
        .cancel_epoch_i(cancel_epoch), .render_valid_i(render_valid),
        .left_i(left), .right_i(right), .reference_i(reference_value), .voices_i(voices),
        .valid_o(valid), .left_o(delivered_left), .right_o(delivered_right),
        .reference_o(delivered_reference), .voices_o(delivered_voices),
        .duplicate_frames_o(duplicates));

    task automatic step(input logic tick_value, input logic [9:0] epoch_value,
                        input logic valid_value, input integer payload);
        logic available, cancelled, expected_valid;
        @(negedge clk);
        sample_ce = tick_value;
        cancel_epoch = epoch_value;
        render_valid = valid_value;
        left = payload;
        right = -payload;
        reference_value = payload ^ 32'ha5a5a5a5;
        voices = payload ^ 32'h5a5a5a5a;
        #1;
        available = !model_offered || tick_value;
        cancelled = epoch_value != model_epoch;
        expected_valid = available && ((valid_value && (!model_cancelled || tick_value)) || cancelled || (muted && tick_value));
        if (valid !== expected_valid) $fatal(1, "delivery valid mismatch");
        if (valid && {delivered_left, delivered_right, delivered_reference, delivered_voices} !==
            (cancelled || muted ? 128'd0 : {left, right, reference_value, voices}))
            $fatal(1, "delivery payload or cancelled metadata mismatch");
        if (valid_value && !available && !model_cancelled && !cancelled && !muted) model_duplicates++;
        if (tick_value) begin
            model_offered = 0;
            model_cancelled = 0;
        end
        if (expected_valid) model_offered = 1;
        if (cancelled || (muted && tick_value)) model_cancelled = 1;
        model_epoch = epoch_value;
        @(posedge clk); #1;
        if (duplicates !== model_duplicates) $fatal(1, "delivery fault was hidden");
        cycles++;
    endtask

    initial begin
        repeat (3) @(negedge clk);
        reset_n = 1;
        step(1, 0, 0, 0);
        step(0, 0, 1, 12345);
        step(0, 0, 1, 23456);
        step(0, 1, 0, 0);
        step(1, 1, 0, 0);
        step(0, 2, 0, 67890);
        step(0, 3, 0, 0);
        step(0, 3, 1, 98765);
        step(1, 3, 0, 0);
        repeat (4) step(0, 3, 0, 0);
        step(1, 1023, 1, 23456);
        step(1, 0, 1, 34567);
        muted = 1;
        repeat (4) begin
            step(1, 0, 0, 0);
            step(0, 0, 1, 45678);
        end
        muted = 0;
        for (integer index = 0; index < 4096; index++) begin
            step(index % 32 == 0, cancel_epoch + 10'(($random(seed) & 7) == 0),
                 ($random(seed) & 3) == 0, $random(seed));
        end
        $display("PASS workstation_frame_delivery: cycles=%0d duplicate_faults=%0d; passthrough, cancel-zero, at-most-once, missing render and epoch wrap", cycles, duplicates);
        $finish;
    end
endmodule
