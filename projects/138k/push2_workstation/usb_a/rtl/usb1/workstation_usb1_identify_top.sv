`include "usb1_profile.vh"
`ifndef USB1_BUILD_ID
`define USB1_BUILD_ID 32'hC11028F1
`endif
module workstation_usb1_identify_top #(
    parameter [31:0] BUILD_ID = `USB1_BUILD_ID
)(
    input wire clk_50m,
    inout wire usb1_dp, usb1_dn,
    output wire debug_uart_tx
);
    wire clk_usb, reset_n;
    workstation_usb1_clock clock(.clk_50m(clk_50m), .clk_48m(clk_usb), .locked_o(), .reset_n_o(reset_n));
    wire service_valid, service_write, service_ready, service_error, session_valid;
    wire [7:0] service_address;
    wire [31:0] service_write_data, service_read_data;
    wire [3:0] service_mask;
    workstation_usb1_host host (
        .clk_usb(clk_usb), .reset_n(reset_n), .usb_dp(usb1_dp), .usb_dm(usb1_dn),
        .uart_rx_i(1'b1), .uart_tx_o(debug_uart_tx),
        .service_valid_o(service_valid), .service_write_o(service_write), .service_address_o(service_address),
        .service_write_data_o(service_write_data), .service_mask_o(service_mask),
        .service_ready_i(service_ready), .service_error_i(service_error), .service_read_data_i(service_read_data),
        .fault_o(), .fault_address_o(), .line_state_o(), .session_valid_o(session_valid)
    );
    workstation_usb1_diagnostics #(.BUILD_ID(BUILD_ID)) diagnostics (
        .clk_usb(clk_usb), .reset_n(reset_n), .session_valid_i(session_valid), .service_valid_i(service_valid), .service_write_i(service_write),
        .service_address_i(service_address), .service_write_data_i(service_write_data), .service_mask_i(service_mask),
        .service_ready_o(service_ready), .service_error_o(service_error), .service_read_data_o(service_read_data),
        .device_flags_o(), .identity_o(), .protocol_status_o(), .midi_count_o(),
        .midi_valid_o(), .midi_ready_i(1'b1), .midi_data_o()
    );
endmodule
