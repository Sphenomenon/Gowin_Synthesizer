`timescale 1ns/1ps
`default_nettype none
// CDC echo adapter. Pad/PHY mode selection and TX loopback belong to the top.
module usb2_cdc_loopback (
    input  wire        clk_60mhz,
    input  wire        reset_n,
    input  wire        dp_rx,
    input  wire        dn_rx,
    output wire        usb_oe,
    output wire        dp_tx,
    output wire        dn_tx,
    output wire        attach_request,
    output wire        usb_reset_released,
    output wire [7:0]  recv_data,
    output wire        recv_valid,
    output wire        send_ready,
    output reg         received_seen,
    output reg         overflow_seen,
    output reg  [15:0] received_count,
    output reg  [15:0] echo_queued_count,
    output reg  [15:0] overflow_count
);
    usb_serial_top #(.DEBUG("FALSE")) u_cdc (
        .rstn(reset_n), .clk(clk_60mhz),
        .usb_dp_pull(attach_request), .usb_oe(usb_oe),
        .dp_tx(dp_tx), .dn_tx(dn_tx), .dp_rx(dp_rx), .dn_rx(dn_rx),
        .usb_rstn(usb_reset_released),
        .recv_data(recv_data), .recv_valid(recv_valid),
        .send_data(recv_data), .send_valid(recv_valid), .send_ready(send_ready),
        .debug_en(), .debug_data(), .debug_uart_tx()
    );

    // No application backpressure exists on OUT. The unchanged 1024-byte
    // vendor send FIFO can fill if the host never reads; expose exact drops.
    always @(posedge clk_60mhz or negedge usb_reset_released) begin
        if (!usb_reset_released) begin
            received_seen <= 0;
            overflow_seen <= 0;
            received_count <= 0;
            echo_queued_count <= 0;
            overflow_count <= 0;
        end else if (recv_valid) begin
            received_seen <= 1;
            if (received_count != 16'hffff)
                received_count <= received_count + 1'b1;
            if (send_ready) begin
                if (echo_queued_count != 16'hffff)
                    echo_queued_count <= echo_queued_count + 1'b1;
            end else begin
                overflow_seen <= 1;
                if (overflow_count != 16'hffff)
                    overflow_count <= overflow_count + 1'b1;
            end
        end
    end
endmodule
`default_nettype wire
