module workstation_usb1_phy (
    input wire clk_usb, reset_n,
    inout wire usb_dp, usb_dm,
    input wire [7:0] tx_data_i,
    input wire tx_valid_i,
    output wire tx_ready_o,
    output wire [7:0] rx_data_o,
    output wire rx_valid_o, rx_active_o, rx_error_o,
    output wire [1:0] line_state_o,
    input wire [1:0] op_mode_i, xcvr_select_i,
    input wire term_select_i, dp_pulldown_i, dm_pulldown_i
);
    wire tx_dp, tx_dm, tx_disable;
    assign usb_dp = reset_n && !tx_disable ? tx_dp : 1'bz;
    assign usb_dm = reset_n && !tx_disable ? tx_dm : 1'bz;
    usb_fs_phy phy (
        .clk_i(clk_usb), .rstn_i(reset_n),
        .utmi_data_out_i(tx_data_i), .utmi_txvalid_i(tx_valid_i && reset_n),
        .utmi_op_mode_i(op_mode_i), .utmi_xcvrselect_i(xcvr_select_i),
        .utmi_termselect_i(term_select_i), .utmi_dppulldown_i(dp_pulldown_i),
        .utmi_dmpulldown_i(dm_pulldown_i),
        .usb_rx_rcv_i(usb_dp && !usb_dm), .usb_rx_dp_i(usb_dp), .usb_rx_dn_i(usb_dm),
        .usb_reset_assert_i(1'b0),
        .utmi_data_in_o(rx_data_o), .utmi_txready_o(tx_ready_o),
        .utmi_rxvalid_o(rx_valid_o), .utmi_rxactive_o(rx_active_o), .utmi_rxerror_o(rx_error_o),
        .utmi_linestate_o(line_state_o), .usb_tx_dp_o(tx_dp), .usb_tx_dn_o(tx_dm),
        .usb_tx_oen_o(tx_disable), .usb_reset_detect_o(), .usb_en_o()
    );
endmodule
