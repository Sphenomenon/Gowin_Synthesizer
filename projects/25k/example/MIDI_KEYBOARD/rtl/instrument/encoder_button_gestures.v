`timescale 1ns/1ps
// Classify a synchronous, already debounced encoder button. Short presses
// occur on release; long presses occur once after the configured hold time.
module encoder_button_gestures #(
    parameter integer CLK_HZ = 50000000,
    parameter integer LONG_PRESS_MS = 1000
) (
    input wire clk,
    input wire reset,
    input wire pressed,
    output reg short_press,
    output reg long_press
);
    function integer bits_for;
        input [63:0] value;
        reg [63:0] work;
        begin
            bits_for = 0;
            work = value;
            while (work != 0) begin
                bits_for = bits_for + 1;
                work = work >> 1;
            end
            if (bits_for == 0) bits_for = 1;
        end
    endfunction

    // Use a wide constant product: 50 MHz * 1000 ms exceeds 32 bits.
    // Round up so clocks not divisible by 1 kHz cannot trigger early.
    localparam [63:0] LONG_CYCLES =
        (CLK_HZ < 1 || LONG_PRESS_MS < 1) ? 64'd1 :
        ((CLK_HZ * 64'd1 * LONG_PRESS_MS) + 64'd999) / 64'd1000;
    localparam integer COUNT_BITS = bits_for(LONG_CYCLES - 64'd1);

    reg armed;
    reg active;
    reg long_sent;
    reg [COUNT_BITS-1:0] hold_count;

    always @(posedge clk) begin
        if (reset) begin
            armed <= 1'b0;
            active <= 1'b0;
            long_sent <= 1'b0;
            hold_count <= 0;
            short_press <= 1'b0;
            long_press <= 1'b0;
        end else begin
            short_press <= 1'b0;
            long_press <= 1'b0;
            if (!armed) begin
                // Ignore a button held through reset, including its release.
                // A fresh gesture starts only after a released sample.
                if (!pressed) armed <= 1'b1;
            end else if (!active) begin
                if (pressed) begin
                    active <= 1'b1;
                    long_sent <= 1'b0;
                    hold_count <= 0;
                end
            end else begin
                if (!long_sent) begin
                    // The first asserted sample is time zero. Emit after
                    // LONG_CYCLES complete clocks, even if released exactly
                    // at that boundary, so one gesture cannot be both kinds.
                    if (hold_count == LONG_CYCLES - 64'd1) begin
                        long_press <= 1'b1;
                        long_sent <= 1'b1;
                    end else if (!pressed) begin
                        short_press <= 1'b1;
                    end else begin
                        hold_count <= hold_count + 1'b1;
                    end
                end
                if (!pressed) begin
                    active <= 1'b0;
                    long_sent <= 1'b0;
                    hold_count <= 0;
                end
            end
        end
    end
endmodule
