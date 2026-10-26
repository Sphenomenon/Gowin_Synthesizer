module workstation_usb3300_host_link #(
    parameter integer HEARTBEAT_WIDTH = 5,
    parameter integer EXIT_HOLD_REF_CYCLES = 500,
    parameter integer QUALIFY_EDGES = 8,
    parameter integer CLOCK_TIMEOUT_REF_CYCLES = 5000,
    parameter integer STARTUP_CYCLES = 600,
    parameter integer TRANSACTION_TIMEOUT_CYCLES = 60000,
    parameter integer NOPID_TIMEOUT_CYCLES = 3600000,
    parameter integer STAGE_TIMEOUT_CYCLES = 120000
)(
    input wire clk_ref,
    input wire clk_ulpi,
    input wire reset_n,
    input wire enable_i,
    input wire [7:0] ulpi_data_i,
    input wire ulpi_dir_i,
    input wire ulpi_nxt_i,
    output wire [7:0] ulpi_data_o,
    output wire ulpi_data_oe_o,
    output wire ulpi_stp_o,
    output wire link_reset_n_o,
    output wire ready_o,
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
    output wire [7:0] function_control_o,
    output wire [7:0] interface_control_o,
    output wire [7:0] otg_control_o,
    input wire csr_valid_i,
    output wire csr_ready_o,
    input wire csr_write_i,
    input wire [5:0] csr_address_i,
    input wire [7:0] csr_data_i,
    output wire csr_response_valid_o,
    input wire csr_response_ready_i,
    output wire [7:0] csr_response_data_o,
    output wire [2:0] csr_response_error_o,
    input wire [7:0] utmi_data_i,
    input wire utmi_txvalid_i,
    input wire utmi_tx_nopid_i,
    output wire utmi_txready_o,
    output wire [7:0] utmi_data_o,
    output wire utmi_rxvalid_o,
    output wire utmi_rxactive_o,
    output wire utmi_rxerror_o,
    output wire utmi_txend_o,
    output wire [1:0] utmi_linestate_o,
    output wire [1:0] vbus_state_o,
    output wire id_state_o,
    output wire host_disconnect_o,
    output wire tx_abort_o,
    output wire link_fatal_o,
    output wire [31:0] received_bytes_o,
    output wire [31:0] transmitted_bytes_o,
    output wire [15:0] rxcmd_count_o,
    output wire rxcmd_valid_o
);
    wire force_stp;
    wire link_oe;
    wire link_stp;
    wire init_ready;
    wire init_valid;
    wire init_write;
    wire [5:0] init_address;
    wire [7:0] init_data;
    wire init_response_ready;
    wire link_csr_ready;
    wire link_response_valid;
    wire [7:0] link_response_data;
    wire [2:0] link_response_error;
    wire link_txready;
    wire link_rxvalid;
    wire link_rxactive;
    wire link_rxerror;
    wire safe_stop = !link_reset_n_o || init_failed_o || link_fatal_o;

    assign ready_o = init_ready && !safe_stop;
    assign ulpi_data_oe_o = link_oe && !safe_stop && !force_stp;
    assign ulpi_stp_o = link_stp || safe_stop || force_stp;
    assign csr_ready_o = ready_o && link_csr_ready;
    assign csr_response_valid_o = ready_o && link_response_valid;
    assign csr_response_data_o = link_response_data;
    assign csr_response_error_o = link_response_error;
    assign utmi_txready_o = ready_o && link_txready;
    assign utmi_rxvalid_o = ready_o && link_rxvalid;
    assign utmi_rxactive_o = ready_o && link_rxactive;
    assign utmi_rxerror_o = ready_o && link_rxerror;
    assign utmi_txend_o = ready_o && link_stp;

    workstation_ulpi_supervisor #(
        .HEARTBEAT_WIDTH(HEARTBEAT_WIDTH), .EXIT_HOLD_REF_CYCLES(EXIT_HOLD_REF_CYCLES),
        .QUALIFY_EDGES(QUALIFY_EDGES), .CLOCK_TIMEOUT_REF_CYCLES(CLOCK_TIMEOUT_REF_CYCLES)
    ) supervisor (
        .clk_ref(clk_ref), .clk_ulpi(clk_ulpi), .reset_n(reset_n), .enable_i(enable_i),
        .link_reset_n_o(link_reset_n_o), .force_stp_o(force_stp), .running_o(clock_running_o),
        .clock_present_o(clock_present_o), .failed_o(clock_failed_o), .failure_code_o(clock_failure_code_o)
    );

    workstation_usb3300_host_init #(
        .STARTUP_CYCLES(STARTUP_CYCLES), .STAGE_TIMEOUT_CYCLES(STAGE_TIMEOUT_CYCLES)
    ) initialize_host (
        .clk_ulpi(clk_ulpi), .reset_n(link_reset_n_o), .link_fatal_i(link_fatal_o),
        .csr_valid_o(init_valid), .csr_ready_i(link_csr_ready), .csr_write_o(init_write),
        .csr_address_o(init_address), .csr_data_o(init_data),
        .csr_response_valid_i(link_response_valid && !init_ready),
        .csr_response_ready_o(init_response_ready), .csr_response_data_i(link_response_data),
        .csr_response_error_i(link_response_error), .ready_o(init_ready), .failed_o(init_failed_o),
        .failure_code_o(init_failure_code_o), .stage_o(init_stage_o), .retry_count_o(init_retry_count_o),
        .last_data_o(init_last_data_o), .last_error_o(init_last_error_o),
        .vendor_id_o(vendor_id_o), .product_id_o(product_id_o), .function_control_o(function_control_o),
        .interface_control_o(interface_control_o), .otg_control_o(otg_control_o)
    );

    workstation_ulpi_link #(
        .TRANSACTION_TIMEOUT_CYCLES(TRANSACTION_TIMEOUT_CYCLES), .NOPID_TIMEOUT_CYCLES(NOPID_TIMEOUT_CYCLES)
    ) link (
        .clk_ulpi(clk_ulpi), .reset_n(link_reset_n_o), .ulpi_data_i(ulpi_data_i),
        .ulpi_dir_i(ulpi_dir_i), .ulpi_nxt_i(ulpi_nxt_i), .ulpi_data_o(ulpi_data_o),
        .ulpi_data_oe_o(link_oe), .ulpi_stp_o(link_stp),
        .csr_valid_i(init_ready ? (csr_valid_i && ready_o) : init_valid), .csr_ready_o(link_csr_ready),
        .csr_write_i(init_ready ? csr_write_i : init_write),
        .csr_address_i(init_ready ? csr_address_i : init_address),
        .csr_data_i(init_ready ? csr_data_i : init_data),
        .csr_response_valid_o(link_response_valid),
        .csr_response_ready_i(init_ready ? (csr_response_ready_i && ready_o) : init_response_ready),
        .csr_response_data_o(link_response_data), .csr_response_error_o(link_response_error),
        .utmi_data_i(utmi_data_i), .utmi_txvalid_i(utmi_txvalid_i && ready_o),
        .utmi_tx_nopid_i(utmi_tx_nopid_i), .utmi_txready_o(link_txready), .utmi_data_o(utmi_data_o),
        .utmi_rxvalid_o(link_rxvalid), .utmi_rxactive_o(link_rxactive), .utmi_rxerror_o(link_rxerror),
        .utmi_linestate_o(utmi_linestate_o), .vbus_state_o(vbus_state_o), .id_state_o(id_state_o),
        .host_disconnect_o(host_disconnect_o), .tx_abort_o(tx_abort_o), .fatal_error_o(link_fatal_o),
        .received_bytes_o(received_bytes_o), .transmitted_bytes_o(transmitted_bytes_o),
        .rxcmd_count_o(rxcmd_count_o), .rxcmd_valid_o(rxcmd_valid_o)
    );
endmodule
