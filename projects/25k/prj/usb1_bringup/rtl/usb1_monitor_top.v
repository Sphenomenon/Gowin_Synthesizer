`timescale 1ns/1ps
`default_nettype none
// Standalone passive observer. The seven debug outputs go to U5 PWM1..7.
// Do not load this standalone image with another board driving those pins.
module usb1_monitor_top (
    input  wire clk,
    input  wire usb_dp,
    input  wire usb_dm,
    output wire [6:0] debug
);
    reg [7:0] power_on = 8'd0;
    reg [25:0] heartbeat = 26'd0;
    wire rst = !(&power_on);
    wire [1:0] state;
    wire [31:0] transition_count;
    wire activity_seen;
    wire se0_long;
    wire se0_long_seen;
    wire se1_long_seen;

    always @(posedge clk) begin
        if (!(&power_on)) power_on <= power_on + 1'b1;
        if (rst) heartbeat <= 26'd0;
        else heartbeat <= heartbeat + 1'b1;
    end

    usb1_passive_monitor monitor (
        .clk(clk), .rst(rst), .usb_dp(usb_dp), .usb_dm(usb_dm),
        .line_state(state), .transition_count(transition_count),
        .activity_seen(activity_seen), .se0_long(se0_long),
        .se0_long_seen(se0_long_seen), .se1_long_seen(se1_long_seen)
    );
    assign debug = {heartbeat[25], se1_long_seen, se0_long_seen,
                    se0_long, activity_seen, state};
endmodule
`default_nettype wire
