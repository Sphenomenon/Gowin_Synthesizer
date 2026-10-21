module workstation_usb2_host_phy #(
    parameter integer ATTACH_DEBOUNCE_US = 100000
)(
    input wire clk_ref,
    input wire clk_ulpi,
    input wire reset_n,
    input wire enable_i,
    input wire hs_enable_i,
    input wire reset_request_i,
    input wire mac_idle_i,
    input wire [7:0] ulpi_data_i,
    input wire ulpi_dir_i,
    input wire ulpi_nxt_i,
    output wire [7:0] ulpi_data_o,
    output wire ulpi_data_oe_o,
    output wire ulpi_stp_o,
    input wire [7:0] mac_data_i,
    input wire mac_txvalid_i,
    output wire mac_txready_o,
    output wire [7:0] mac_data_o,
    output wire mac_rxvalid_o,
    output wire mac_rxactive_o,
    output wire mac_rxerror_o,
    output wire mac_txend_o,
    output wire mac_line_valid_o,
    output wire mac_reset_n_o,
    output wire connected_o,
    output wire high_speed_o,
    output wire sof_enable_o,
    output wire traffic_enable_o,
    output wire reset_active_o,
    output wire session_reset_o,
    output wire unsupported_low_speed_o,
    output wire failed_o,
    output wire [4:0] port_state_o,
    output wire [3:0] port_failure_code_o,
    output wire [15:0] chirp_count_o,
    output wire [7:0] port_last_function_o,
    output wire [7:0] port_last_response_o,
    output wire [7:0] port_csr_retries_o,
    output wire phy_ready_o,
    output wire clock_running_o,
    output wire clock_present_o,
    output wire clock_failed_o,
    output wire [1:0] clock_failure_code_o,
    output wire init_failed_o,
    output wire [3:0] init_failure_code_o,
    output wire [4:0] init_stage_o,
    output wire [7:0] init_retry_count_o,
    output wire [7:0] init_last_data_o,
    output wire [2:0] init_last_error_o,
    output wire [15:0] vendor_id_o,
    output wire [15:0] product_id_o,
    output wire [7:0] init_function_control_o,
    output wire [7:0] init_interface_control_o,
    output wire [7:0] init_otg_control_o,
    output wire [1:0] linestate_o,
    output wire [1:0] vbus_state_o,
    output wire id_state_o,
    output wire host_disconnect_o,
    output wire tx_abort_o,
    output wire link_fatal_o,
    output wire [31:0] received_bytes_o,
    output wire [31:0] transmitted_bytes_o,
    output wire [15:0] rxcmd_count_o
);
    wire link_reset_n;
    wire link_oe;
    wire link_stp;
    wire port_failed;
    wire owns_tx;
    wire csr_valid;
    wire csr_ready;
    wire csr_write;
    wire [5:0] csr_address;
    wire [7:0] csr_data;
    wire response_valid;
    wire response_ready;
    wire [7:0] response_data;
    wire [2:0] response_error;
    wire [7:0] chirp_data;
    wire chirp_valid;
    wire link_txready;
    wire link_rxvalid;
    wire link_rxactive;
    wire link_rxerror;
    wire rxcmd_valid;

    assign ulpi_data_oe_o = link_oe && !port_failed;
    assign ulpi_stp_o = link_stp || port_failed;
    assign failed_o = port_failed || clock_failed_o || init_failed_o || link_fatal_o;
    assign mac_reset_n_o = link_reset_n && phy_ready_o && !owns_tx && !failed_o;
    assign mac_txready_o = mac_reset_n_o && link_txready;
    assign mac_rxvalid_o = mac_reset_n_o && link_rxvalid;
    assign mac_rxactive_o = mac_reset_n_o && link_rxactive;
    assign mac_rxerror_o = mac_reset_n_o && link_rxerror;
    assign mac_txend_o = mac_reset_n_o && link_stp;
    assign mac_line_valid_o = mac_reset_n_o && rxcmd_valid;

    workstation_usb2_host_port #(.ATTACH_DEBOUNCE_US(ATTACH_DEBOUNCE_US)) port_control (
        .clk_ulpi(clk_ulpi), .reset_n(link_reset_n), .phy_ready_i(phy_ready_o), .phy_fatal_i(link_fatal_o),
        .hs_enable_i(hs_enable_i), .reset_request_i(reset_request_i), .mac_idle_i(mac_idle_i),
        .linestate_i(linestate_o), .rxcmd_valid_i(rxcmd_valid),
        .host_disconnect_i(host_disconnect_o), .tx_abort_i(tx_abort_o),
        .csr_valid_o(csr_valid), .csr_ready_i(csr_ready), .csr_write_o(csr_write),
        .csr_address_o(csr_address), .csr_data_o(csr_data), .csr_response_valid_i(response_valid),
        .csr_response_ready_o(response_ready), .csr_response_data_i(response_data), .csr_response_error_i(response_error),
        .chirp_data_o(chirp_data), .chirp_valid_o(chirp_valid), .chirp_ready_i(link_txready && owns_tx),
        .connected_o(connected_o), .high_speed_o(high_speed_o), .sof_enable_o(sof_enable_o),
        .traffic_enable_o(traffic_enable_o), .reset_active_o(reset_active_o), .owns_tx_o(owns_tx),
        .session_reset_o(session_reset_o), .unsupported_low_speed_o(unsupported_low_speed_o),
        .failed_o(port_failed), .failure_code_o(port_failure_code_o), .state_o(port_state_o),
        .last_function_o(port_last_function_o), .last_response_o(port_last_response_o),
        .csr_retries_o(port_csr_retries_o), .chirp_count_o(chirp_count_o)
    );

    workstation_usb3300_host_link physical_link (
        .clk_ref(clk_ref), .clk_ulpi(clk_ulpi), .reset_n(reset_n), .enable_i(enable_i),
        .ulpi_data_i(ulpi_data_i), .ulpi_dir_i(ulpi_dir_i), .ulpi_nxt_i(ulpi_nxt_i),
        .ulpi_data_o(ulpi_data_o), .ulpi_data_oe_o(link_oe), .ulpi_stp_o(link_stp),
        .link_reset_n_o(link_reset_n), .ready_o(phy_ready_o), .clock_running_o(clock_running_o),
        .clock_present_o(clock_present_o), .clock_failed_o(clock_failed_o), .clock_failure_code_o(clock_failure_code_o),
        .init_failed_o(init_failed_o), .init_failure_code_o(init_failure_code_o), .init_stage_o(init_stage_o),
        .init_retry_count_o(init_retry_count_o), .init_last_data_o(init_last_data_o), .init_last_error_o(init_last_error_o),
        .vendor_id_o(vendor_id_o), .product_id_o(product_id_o), .function_control_o(init_function_control_o),
        .interface_control_o(init_interface_control_o), .otg_control_o(init_otg_control_o),
        .csr_valid_i(csr_valid), .csr_ready_o(csr_ready), .csr_write_i(csr_write),
        .csr_address_i(csr_address), .csr_data_i(csr_data), .csr_response_valid_o(response_valid),
        .csr_response_ready_i(response_ready), .csr_response_data_o(response_data), .csr_response_error_o(response_error),
        .utmi_data_i(owns_tx ? chirp_data : mac_data_i), .utmi_txvalid_i(owns_tx ? chirp_valid : mac_txvalid_i),
        .utmi_tx_nopid_i(owns_tx), .utmi_txready_o(link_txready), .utmi_data_o(mac_data_o),
        .utmi_rxvalid_o(link_rxvalid), .utmi_rxactive_o(link_rxactive), .utmi_rxerror_o(link_rxerror),
        .utmi_linestate_o(linestate_o), .vbus_state_o(vbus_state_o), .id_state_o(id_state_o),
        .host_disconnect_o(host_disconnect_o), .tx_abort_o(tx_abort_o), .link_fatal_o(link_fatal_o),
        .received_bytes_o(received_bytes_o), .transmitted_bytes_o(transmitted_bytes_o),
        .rxcmd_count_o(rxcmd_count_o), .rxcmd_valid_o(rxcmd_valid)
    );
endmodule
