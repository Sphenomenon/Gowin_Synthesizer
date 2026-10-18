`timescale 1ns/1ps
`default_nettype none
// Passive line observer only. This module never drives USB D+ or D-.
// The line inputs are single-ended GPIO samples, not a USB-compliant PHY.
module usb1_passive_monitor #(
    parameter integer CLK_HZ = 50000000,
    parameter integer LONG_STATE_US = 3
) (
    input  wire        clk,
    input  wire        rst,
    input  wire        usb_dp,
    input  wire        usb_dm,
    output wire [1:0]  line_state, // {DP, DM}: 00 SE0, 10 FS J, 01 FS K, 11 SE1
    output reg  [31:0] transition_count,
    output reg         activity_seen,
    output wire        se0_long,
    output reg         se0_long_seen,
    output reg         se1_long_seen
);
    // Integer round-up. Supported parameters: CLK_HZ >= 1MHz,
    // LONG_STATE_US >= 1, and resulting threshold <= 2^32-1 clocks.
    localparam integer LONG_CYCLES = (CLK_HZ / 1000000) * LONG_STATE_US
        + (((CLK_HZ % 1000000) * LONG_STATE_US + 999999) / 1000000);

    (* ASYNC_REG = "TRUE" *) reg dp_meta;
    (* ASYNC_REG = "TRUE" *) reg dm_meta;
    (* ASYNC_REG = "TRUE" *) reg dp_sync;
    (* ASYNC_REG = "TRUE" *) reg dm_sync;
    reg [1:0] previous_state;
    reg [2:0] valid_pipe;
    reg [31:0] se0_cycles;
    reg [31:0] se1_cycles;

    assign line_state = {dp_sync, dm_sync};
    assign se0_long = (se0_cycles >= LONG_CYCLES);

    always @(posedge clk) begin
        if (rst) begin
            dp_meta <= 1'b0;
            dm_meta <= 1'b0;
            dp_sync <= 1'b0;
            dm_sync <= 1'b0;
            previous_state <= 2'b00;
            valid_pipe <= 3'b000;
            transition_count <= 32'd0;
            activity_seen <= 1'b0;
            se0_cycles <= 32'd0;
            se1_cycles <= 32'd0;
            se0_long_seen <= 1'b0;
            se1_long_seen <= 1'b0;
        end else begin
            dp_meta <= usb_dp;
            dm_meta <= usb_dm;
            dp_sync <= dp_meta;
            dm_sync <= dm_meta;
            previous_state <= line_state;
            valid_pipe <= {valid_pipe[1:0], 1'b1};

            // Ignore reset-release synchronization transitions.
            if (valid_pipe[2]) begin
                if (line_state != previous_state) begin
                    activity_seen <= 1'b1;
                    if (transition_count != 32'hffffffff)
                        transition_count <= transition_count + 1'b1;
                end

                if (line_state == 2'b00) begin
                    if (se0_cycles < LONG_CYCLES)
                        se0_cycles <= se0_cycles + 1'b1;
                    if (se0_cycles >= LONG_CYCLES - 1)
                        se0_long_seen <= 1'b1;
                end else begin
                    se0_cycles <= 32'd0;
                end

                if (line_state == 2'b11) begin
                    if (se1_cycles < LONG_CYCLES)
                        se1_cycles <= se1_cycles + 1'b1;
                    if (se1_cycles >= LONG_CYCLES - 1)
                        se1_long_seen <= 1'b1;
                end else begin
                    se1_cycles <= 32'd0;
                end
            end
        end
    end
endmodule
`default_nettype wire
