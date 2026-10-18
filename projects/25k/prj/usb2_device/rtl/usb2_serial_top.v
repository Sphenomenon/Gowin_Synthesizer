`timescale 1ns/1ps
`default_nettype none
// Separate image from the preserved ULPI probe. Same external ports/GAO bus.
module usb2_device_top #(
    // Reversible USB3300 DATA1 polarity candidate. Apply the same inversion
    // to TX and RX; DATA0 direction, DATA2 SE0, STP and ULPI init are unchanged.
    parameter [0:0] SERIAL_D1_INVERT = 1'b0,
    // D2A7's normal page 3 retains echo/drop counts. A separately identified
    // activity image enables raw serial-pad observations on page 3 instead.
    parameter [0:0] SERIAL_ACTIVITY_DIAG = 1'b0
) (
    input wire clk_50mhz,
    input wire clk_ulpi60,
    inout wire [7:0] ulpi_data,
    input wire ulpi_dir,
    input wire ulpi_nxt,
    output wire ulpi_stp,
    output wire led_ready,
    output wire led_done
);
    reg [12:0] powerup = 0;
    always @(posedge clk_50mhz)
        if (!powerup[12]) powerup <= powerup + 1'b1;
    (* ASYNC_REG = "TRUE" *) reg [2:0] reset_release = 0;
    always @(posedge clk_ulpi60)
        reset_release <= {reset_release[1:0], powerup[12]};
    wire reset_n = reset_release[2];
    wire init_done, init_error, id_ok;
    wire [7:0] stage, func_ctrl, if_ctrl, otg_ctrl;
    wire [7:0] phy_debug;
    wire [15:0] vendor_id, product_id;
    wire attach_request;
    wire [7:0] init_data_out;
    wire init_data_oe;
    usb2_serial_init u_init (
        .clk_ulpi60(clk_ulpi60), .reset_n(reset_n),
        .ulpi_data_i(ulpi_data), .ulpi_data_o(init_data_out), .ulpi_data_oe(init_data_oe),
        .ulpi_dir(ulpi_dir), .ulpi_nxt(ulpi_nxt),
        .ulpi_stp(ulpi_stp), .attach_request(attach_request),
        .init_done(init_done), .error(init_error), .stage(stage),
        .vendor_id(vendor_id), .product_id(product_id), .id_ok(id_ok),
        .func_ctrl(func_ctrl), .if_ctrl(if_ctrl), .otg_ctrl(otg_ctrl), .phy_debug(phy_debug)
    );
    wire usb_oe, dp_tx, dn_tx, dp_rx, dn_rx;
    wire usb_reset_released, received_seen, overflow_seen;
    wire [15:0] received_count, echo_queued_count, overflow_count;
    wire [7:0] recv_data;
    wire recv_valid, send_ready;
    // Serial mode direction is TX_ENABLE, not ULPI DIR. During the guarded
    // transition no FPGA serial pins drive. PHY interrupt/high bits stay Z.
    // One tri-state driver per physical pad. Separate data and OE muxes keep
    // raw DIR out of the data path while withdrawing ULPI drive immediately.
    wire serial_d1_rx = ulpi_data[1] ^ SERIAL_D1_INVERT;
    wire [7:0] serial_data_out = {5'b0, !(dp_tx || dn_tx),
                                 (dp_tx ^ SERIAL_D1_INVERT), usb_oe};
    wire [7:0] serial_data_oe = {5'b0, usb_oe, usb_oe, 1'b1};
    wire [7:0] pad_data_out = init_done ? serial_data_out : init_data_out;
    // init_data_oe is already withdrawn at mode entry, well before init_done.
    // These enables are mutually exclusive by the guarded handover FSM.
    wire [7:0] pad_data_oe = {8{init_data_oe}} | ({8{init_done}} & serial_data_oe);
    genvar pad;
    generate for (pad=0; pad<8; pad=pad+1) begin: pads
        assign ulpi_data[pad] = pad_data_oe[pad] ? pad_data_out[pad] : 1'bz;
    end endgenerate
    assign dp_rx = !init_done ? 1'b1 : usb_oe ? dp_tx : (!ulpi_data[2] && serial_d1_rx);
    assign dn_rx = !init_done ? 1'b0 : usb_oe ? dn_tx : (!ulpi_data[2] && !serial_d1_rx);
    usb2_cdc_loopback u_device (
        .clk_60mhz(clk_ulpi60), .reset_n(reset_n && !init_error),
        .dp_rx(dp_rx), .dn_rx(dn_rx), .usb_oe(usb_oe), .dp_tx(dp_tx), .dn_tx(dn_tx),
        .attach_request(attach_request), .usb_reset_released(usb_reset_released),
        .recv_data(recv_data), .recv_valid(recv_valid), .send_ready(send_ready),
        .received_seen(received_seen), .overflow_seen(overflow_seen),
        .received_count(received_count), .echo_queued_count(echo_queued_count),
        .overflow_count(overflow_count)
    );
    wire [3:0] flags = {init_done, usb_reset_released, received_seen,
                        init_error || overflow_seen};
    wire [7:0] line_flags = {attach_request, init_done, usb_oe, dp_rx, dn_rx,
                             ulpi_data[2:0]};
    wire [15:0] raw_transition_count;
    wire [7:0] activity_event_flags, raw_seen_mask;
    usb2_serial_activity u_activity (
        .clk_ulpi60(clk_ulpi60), .reset_n(reset_n), .init_done(init_done),
        .raw_data(ulpi_data[2:0]), .usb_oe(usb_oe),
        .usb_reset_released(usb_reset_released),
        .raw_transition_count(raw_transition_count),
        .event_flags(activity_event_flags), .raw_seen_mask(raw_seen_mask)
    );
    wire [31:0] page3_normal = {echo_queued_count, overflow_count};
    wire [31:0] page3_activity = {raw_transition_count, activity_event_flags,
                                 raw_seen_mask};
    wire [31:0] page3_payload = SERIAL_ACTIVITY_DIAG ? page3_activity : page3_normal;
    wire [127:0] live_snapshot = {
        vendor_id, product_id, func_ctrl, if_ctrl, otg_ctrl, line_flags,
        stage, phy_debug[3:0], flags, received_count, page3_payload
    };
    wire [63:0] status_raw;
    wire [3:0] result_flags;
    wire clock_alive;
    usb2_status_50mhz u_observer (
        .clk_50mhz(clk_50mhz), .clk_ulpi60(clk_ulpi60),
        .live_snapshot(live_snapshot), .status_50mhz(status_raw),
        .result_flags(result_flags), .clock_alive(clock_alive)
    );
    reg [63:0] status_50mhz /* synthesis syn_preserve=1 syn_keep=1 */;
    always @(posedge clk_50mhz) status_50mhz <= status_raw;
    assign led_ready = clock_alive && result_flags[3];
    assign led_done = result_flags[1];
endmodule
`default_nettype wire
