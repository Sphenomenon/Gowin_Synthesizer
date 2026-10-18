`timescale 1ns/1ps
// EC11E15244B2: 30 detents / 15 pulses per revolution.
// A detent occurs at 00 or 11, so two valid transitions make one count.
// Positive sequence: 11 -> 01 -> 00 -> 10 -> 11. Physical CW depends on wiring.
module encoder_input #(
    parameter integer CLK_HZ = 50000000,
    // At 50 MHz these defaults are 20 us for A/B and 1 ms for the key.
    // They are short enough for responsive hand turning while still
    // rejecting ordinary contact bounce; applications can override them.
    parameter integer AB_FILTER_CYCLES = 1000,
    parameter integer KEY_FILTER_CYCLES = 50000
) (
    input wire clk,
    input wire reset,
    input wire a,
    input wire b,
    input wire key_n,
    output reg signed [15:0] position,
    output reg [15:0] press_count,
    output reg [15:0] invalid_count,
    output reg [1:0] ab_state,
    output reg key_pressed,
    output reg signed [1:0] direction,
    output reg step_pulse,
    output reg press_pulse
);
    function integer bits_for;
        input integer value;
        integer work;
        begin
            bits_for = 0;
            work = value;
            while (work > 0) begin
                bits_for = bits_for + 1;
                work = work >> 1;
            end
            if (bits_for == 0) bits_for = 1;
        end
    endfunction

    localparam integer AB_CYCLES = (AB_FILTER_CYCLES < 1) ? 1 : AB_FILTER_CYCLES;
    localparam integer KEY_CYCLES = (KEY_FILTER_CYCLES < 1) ? 1 : KEY_FILTER_CYCLES;
    localparam integer AB_BITS = bits_for(AB_CYCLES);
    localparam integer KEY_BITS = bits_for(KEY_CYCLES);

    (* syn_preserve = 1, async_reg = "true" *) reg [1:0] ab_meta, ab_sync;
    (* syn_preserve = 1, async_reg = "true" *) reg key_meta, key_sync;
    reg [1:0] sync_ready;
    reg [1:0] ab_candidate;
    reg key_candidate;
    reg [AB_BITS-1:0] ab_filter_count;
    reg [KEY_BITS-1:0] key_filter_count;
    reg ab_seeded;
    reg detent_seeded;
    reg signed [2:0] phase;

    // Filter the A/B pair together. Independent pin filters can manufacture
    // phase relationships that never existed at the encoder contacts.
    wire ab_accept = sync_ready[1] &&
        ((AB_CYCLES == 1) || ((ab_sync == ab_candidate) &&
          (ab_filter_count == AB_CYCLES - 1)));
    wire key_accept = sync_ready[1] &&
        ((KEY_CYCLES == 1) || ((key_sync == key_candidate) &&
          (key_filter_count == KEY_CYCLES - 1)));
    wire at_detent = (ab_sync == 2'b00) || (ab_sync == 2'b11);
    wire positive_transition = ({ab_state, ab_sync} == 4'b1101) ||
        ({ab_state, ab_sync} == 4'b0100) ||
        ({ab_state, ab_sync} == 4'b0010) ||
        ({ab_state, ab_sync} == 4'b1011);
    wire negative_transition = ({ab_state, ab_sync} == 4'b1110) ||
        ({ab_state, ab_sync} == 4'b1000) ||
        ({ab_state, ab_sync} == 4'b0001) ||
        ({ab_state, ab_sync} == 4'b0111);
    wire signed [3:0] next_phase = $signed(phase) +
        (positive_transition ? 4'sd1 : -4'sd1);

    always @(posedge clk) begin
        if (reset) begin
            ab_meta <= 2'b11;
            ab_sync <= 2'b11;
            key_meta <= 1'b1;
            key_sync <= 1'b1;
            sync_ready <= 2'b00;
            ab_candidate <= 2'b11;
            key_candidate <= 1'b1;
            ab_filter_count <= 0;
            key_filter_count <= 0;
            ab_seeded <= 1'b0;
            detent_seeded <= 1'b0;
            phase <= 0;
            position <= 0;
            press_count <= 0;
            invalid_count <= 0;
            ab_state <= 2'b11;
            key_pressed <= 1'b0;
            direction <= 0;
            step_pulse <= 1'b0;
            press_pulse <= 1'b0;
        end else begin
            ab_meta <= {a, b};
            ab_sync <= ab_meta;
            key_meta <= key_n;
            key_sync <= key_meta;
            sync_ready <= {sync_ready[0], 1'b1};
            step_pulse <= 1'b0;
            press_pulse <= 1'b0;

            if (sync_ready[1]) begin
                if (ab_sync != ab_candidate) begin
                    ab_candidate <= ab_sync;
                    ab_filter_count <= 1;
                end else if (ab_filter_count < AB_CYCLES) begin
                    ab_filter_count <= ab_filter_count + 1'b1;
                end
                if (key_sync != key_candidate) begin
                    key_candidate <= key_sync;
                    key_filter_count <= 1;
                end else if (key_filter_count < KEY_CYCLES) begin
                    key_filter_count <= key_filter_count + 1'b1;
                end
            end

            if (ab_accept && (!ab_seeded || ab_sync != ab_state)) begin
                ab_state <= ab_sync;
                if (!ab_seeded) begin
                    // Establish the actual power-on state without a phantom
                    // transition. Starting between detents waits for an anchor.
                    ab_seeded <= 1'b1;
                    detent_seeded <= at_detent;
                    phase <= 0;
                end else if (!positive_transition && !negative_transition) begin
                    if (invalid_count != 16'hffff)
                        invalid_count <= invalid_count + 1'b1;
                    phase <= 0;
                    detent_seeded <= at_detent;
                end else if (!detent_seeded) begin
                    phase <= 0;
                    detent_seeded <= at_detent;
                end else if (at_detent) begin
                    // Chatter returning to the same detent sums to zero.
                    // A reversal cancels the unfinished part of a step.
                    phase <= 0;
                    if (next_phase == 4'sd2) begin
                        if (position < 16'sd32767)
                            position <= position + 16'sd1;
                        direction <= 2'sd1;
                        step_pulse <= 1'b1;
                    end else if (next_phase == -4'sd2) begin
                        if (position > -16'sd32767)
                            position <= position - 16'sd1;
                        direction <= -2'sd1;
                        step_pulse <= 1'b1;
                    end
                end else begin
                    phase <= next_phase;
                end
            end

            if (key_accept && key_pressed != !key_sync) begin
                key_pressed <= !key_sync;
                if (!key_sync) begin
                    if (press_count != 16'hffff)
                        press_count <= press_count + 1'b1;
                    press_pulse <= 1'b1;
                end
            end
        end
    end
endmodule
