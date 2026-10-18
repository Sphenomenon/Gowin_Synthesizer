`timescale 1ns/1ps
`default_nettype none
// Local adapter. Vendor CDC/core RTL is copied without modifications.
module usb1_cdc_loopback (
    input  wire        clk_60mhz,
    input  wire        reset_n,
    inout  wire        usb_dp,
    inout  wire        usb_dm,
    output wire        attach_request,
    output wire        usb_reset_released,
    output wire        recv_valid,
    output wire        send_ready,
    output reg         received_seen,
    output reg         overflow_seen,
    output reg  [15:0] received_count,
    output reg  [15:0] echo_queued_count,
    output reg  [15:0] overflow_count
);
    wire [7:0] recv_data;

    // The on-chip send FIFO is 1024 bytes. OUT has no application ready
    // handshake: a host that writes indefinitely without reading can overflow.
    // Keep original byte values and make this limitation visible in status.
    usb_serial_top #(.DEBUG("FALSE")) u_cdc (
        .rstn(reset_n), .clk(clk_60mhz),
        .usb_dp_pull(attach_request), .usb_dp(usb_dp), .usb_dn(usb_dm),
        .usb_rstn(usb_reset_released),
        .recv_data(recv_data), .recv_valid(recv_valid),
        .send_data(recv_data), .send_valid(recv_valid), .send_ready(send_ready),
        .debug_en(), .debug_data(), .debug_uart_tx()
    );

    // usb_rstn is a bus-reset/SE0 indicator, NOT SET_CONFIGURATION status.
    always @(posedge clk_60mhz or negedge usb_reset_released) begin
        if (!usb_reset_released) begin
            received_seen <= 1'b0;
            overflow_seen <= 1'b0;
            received_count <= 16'd0;
            echo_queued_count <= 16'd0;
            overflow_count <= 16'd0;
        end else if (recv_valid) begin
            received_seen <= 1'b1;
            if (received_count != 16'hffff)
                received_count <= received_count + 1'b1;
            if (send_ready) begin
                if (echo_queued_count != 16'hffff)
                    echo_queued_count <= echo_queued_count + 1'b1;
            end else begin
                overflow_seen <= 1'b1;
                if (overflow_count != 16'hffff)
                    overflow_count <= overflow_count + 1'b1;
            end
        end
    end
endmodule
`default_nettype wire
