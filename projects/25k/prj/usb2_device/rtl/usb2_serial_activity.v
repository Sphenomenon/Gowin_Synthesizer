`timescale 1ns/1ps
`default_nettype none
// Sticky evidence sampled in the PHY's 60 MHz clock domain. These are pad
// observations, not decoded USB packets; TX and RX may both change DATA[2:0].
module usb2_serial_activity (
    input wire clk_ulpi60,
    input wire reset_n,
    input wire init_done,
    input wire [2:0] raw_data,
    input wire usb_oe,
    input wire usb_reset_released,
    output reg [15:0] raw_transition_count,
    output wire [7:0] event_flags,
    output reg [7:0] raw_seen_mask
);
    reg [2:0] previous_raw;
    reg previous_valid;
    reg tx_seen, reset_asserted_seen, reset_released_seen;
    assign event_flags = {5'b0, tx_seen, reset_asserted_seen, reset_released_seen};
    always @(posedge clk_ulpi60) begin
        if (!reset_n) begin
            raw_transition_count <= 0;
            raw_seen_mask <= 0;
            previous_raw <= 0;
            previous_valid <= 0;
            tx_seen <= 0;
            reset_asserted_seen <= 0;
            reset_released_seen <= 0;
        end else if (init_done) begin
            raw_seen_mask[raw_data] <= 1'b1;
            if (previous_valid && raw_data != previous_raw &&
                    raw_transition_count != 16'hffff)
                raw_transition_count <= raw_transition_count + 1'b1;
            previous_raw <= raw_data;
            previous_valid <= 1;
            if (usb_oe) tx_seen <= 1;
            if (usb_reset_released) reset_released_seen <= 1;
            else reset_asserted_seen <= 1;
        end else begin
            // Initialization transitions and gaps cannot create artificial
            // counts or reset events. Previously collected evidence persists.
            previous_valid <= 0;
        end
    end
endmodule
`default_nettype wire
