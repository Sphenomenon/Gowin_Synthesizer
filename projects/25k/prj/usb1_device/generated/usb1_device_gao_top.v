`timescale 1ns/1ps
`default_nettype none
module usb1_device_top (
    input  wire clk_50mhz, // E2, 50 MHz oscillator
    inout  wire usb1_dp,   // L6, USB1 D+
    inout  wire usb1_dm,   // K6, USB1 D-
    output wire led_ready, // E8, active high heartbeat after PLL/reset release
    output wire led_done   // D7, active high when an actual CDC OUT byte arrived
);
    wire clk_60mhz;
    wire pll_locked;
    wire reset_60mhz_n;
    usb1_clock_60m u_clock (
        .clk_50mhz(clk_50mhz), .clk_usb60(clk_60mhz),
        .pll_locked(pll_locked), .reset_60mhz_n(reset_60mhz_n)
    );

    // Board has no pin connected to the top of a 1.5k D+ resistor.
    // This is an INTERNAL request only. Never drive D+ high as a substitute
    // for that resistor; the vendor inouts drive only while sending a packet.
    (* syn_keep = 1 *) wire usb_attach_request;
    wire usb_reset_released;
    wire recv_valid, send_ready, received_seen, overflow_seen;
    wire [15:0] received_count, echo_queued_count, overflow_count;
    usb1_cdc_loopback u_device (
        .clk_60mhz(clk_60mhz), .reset_n(reset_60mhz_n),
        .usb_dp(usb1_dp), .usb_dm(usb1_dm),
        .attach_request(usb_attach_request),
        .usb_reset_released(usb_reset_released),
        .recv_valid(recv_valid), .send_ready(send_ready),
        .received_seen(received_seen), .overflow_seen(overflow_seen),
        .received_count(received_count), .echo_queued_count(echo_queued_count),
        .overflow_count(overflow_count)
    );

    reg [25:0] heartbeat = 26'd0;
    (* ASYNC_REG = "TRUE" *) reg [1:0] usb_line_meta = 2'b00;
    (* ASYNC_REG = "TRUE" *) reg [1:0] usb_line_sync = 2'b00;
    always @(posedge clk_60mhz or negedge reset_60mhz_n) begin
        if (!reset_60mhz_n) begin
            heartbeat <= 26'd0;
            usb_line_meta <= 2'b00;
            usb_line_sync <= 2'b00;
        end else begin
            heartbeat <= heartbeat + 1'b1;
            usb_line_meta <= {usb1_dp, usb1_dm};
            usb_line_sync <= usb_line_meta;
        end
    end
    assign led_ready = pll_locked && reset_60mhz_n && heartbeat[25];
    assign led_done = received_seen;

    // 63:48 RX bytes, 47:32 accepted into echo FIFO, 31:16 dropped bytes;
    // 15 LOCK, 14 clock-domain reset_n, 13 USB bus-reset released,
    // 12 attach intent (unconnected), 11:10 {D+,D-}, 9 overflow sticky,
    // 8 RX pulse, 7 echo FIFO ready, 6 received sticky, 5 heartbeat, 4:0 zero.
    (* syn_keep = 1 *) wire [63:0] status = {
        received_count, echo_queued_count, overflow_count,
        pll_locked, reset_60mhz_n, usb_reset_released, usb_attach_request,
        usb_line_sync, overflow_seen, recv_valid, send_ready,
        received_seen, heartbeat[25], 5'b00000
    };

    // Added only to the optional generated GAO copy. The normal top is intact.
    wire [63:0] status_50mhz_raw;
    reg [63:0] status_50mhz /* synthesis syn_preserve=1 syn_keep=1 */;
    always @(posedge clk_50mhz) status_50mhz <= status_50mhz_raw;
    usb1_status_50mhz u_status_observer (
        .clk_50mhz(clk_50mhz), .usb_dp(usb1_dp), .usb_dm(usb1_dm),
        .stable_flags_async({status[15:12], status[9], status[6], status[5]}),
        .status_50mhz(status_50mhz_raw)
    );
endmodule
`default_nettype wire
