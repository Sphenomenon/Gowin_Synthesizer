module workstation_usb2_host_controller #(
    parameter integer ATTACH_DEBOUNCE_US = 100000,
    parameter integer UPLOAD_TIMEOUT_CYCLES = 60000,
    parameter integer PACKET_TIMEOUT_CYCLES = 60000
)(
    input wire clk_ref,
    input wire clk_ulpi,
    input wire reset_n,
    input wire enable_i,
    input wire hs_enable_i,
    input wire reset_request_i,
    input wire [7:0] ulpi_data_i,
    input wire ulpi_dir_i,
    input wire ulpi_nxt_i,
    output wire [7:0] ulpi_data_o,
    output wire ulpi_data_oe_o,
    output wire ulpi_stp_o,
    input wire command_valid_i,
    output wire command_ready_o,
    input wire [7:0] command_pid_i,
    input wire [6:0] command_device_i,
    input wire [3:0] command_endpoint_i,
    input wire command_toggle_i,
    input wire [9:0] command_length_i,
    input wire [7:0] transmit_data_i,
    input wire transmit_valid_i,
    output wire transmit_ready_o,
    output wire result_valid_o,
    input wire result_ready_i,
    output wire [3:0] result_status_o,
    output wire [7:0] result_pid_o,
    output wire [9:0] result_length_o,
    output wire [7:0] receive_data_o,
    output wire receive_valid_o,
    input wire receive_ready_i,
    output wire receive_last_o,
    output wire transaction_reset_n_o,
    output wire connected_o,
    output wire high_speed_o,
    output wire sof_enable_o,
    output wire traffic_enable_o,
    output wire session_reset_o,
    output wire reset_active_o,
    output wire unsupported_low_speed_o,
    output wire failed_o,
    output wire mac_failed_o,
    output wire phy_failed_o,
    output wire phy_ready_o,
    output wire [4:0] port_state_o,
    output wire [3:0] port_failure_code_o,
    output wire [3:0] mac_state_o,
    output wire [31:0] sof_count_o,
    output wire [15:0] missed_sof_o,
    output wire [10:0] frame_number_o,
    output wire [2:0] microframe_o,
    output wire [15:0] vendor_id_o,
    output wire [15:0] product_id_o,
    output wire [7:0] function_o,
    output wire [3:0] init_failure_code_o,
    output wire [4:0] init_stage_o,
    output wire [1:0] clock_failure_code_o,
    output wire [31:0] received_bytes_o,
    output wire [31:0] transmitted_bytes_o
);
    wire phy_reset_n;
    wire phy_oe, phy_stp;
    wire mac_fatal;
    wire mac_idle;
    wire [7:0] mac_txdata, mac_rxdata;
    wire mac_txvalid, mac_txready, mac_rxvalid, mac_rxactive, mac_rxerror;
    wire mac_txend, mac_line_valid;
    wire [1:0] line_state;
    wire command_ready, transmit_ready, result_valid, receive_valid;
    wire phy_sof_enable, phy_traffic_enable;
    wire [15:0] unused_chirp_count, unused_rxcmd_count;
    wire [7:0] unused_last_response, unused_csr_retries, unused_init_retries, unused_init_data;
    wire [7:0] unused_init_function, unused_interface, unused_otg;
    wire [2:0] unused_init_error;
    wire [1:0] unused_vbus;
    wire unused_clock_running, unused_clock_present, unused_clock_failed, unused_init_failed;
    wire unused_id, unused_disconnect, unused_tx_abort, unused_link_fatal;
    (* async_reg = "true" *) reg [1:0] fatal_sync_q;
    reg fatal_latched_q;
    reg [1:0] fault_release_q;
    wire fault_enable_n = reset_n && enable_i;

    always @(posedge clk_ulpi or negedge fault_enable_n) begin
        if (!fault_enable_n) fault_release_q <= 0;
        else fault_release_q <= {fault_release_q[0], 1'b1};
    end

    always @(posedge clk_ref or negedge reset_n) begin
        if (!reset_n) begin fatal_sync_q <= 0; fatal_latched_q <= 0; end
        else if (!enable_i) begin fatal_sync_q <= 0; fatal_latched_q <= 0; end
        else begin
            fatal_sync_q <= {fatal_sync_q[0], mac_fatal};
            if (fatal_sync_q[1]) fatal_latched_q <= 1;
        end
    end

    assign mac_failed_o = mac_fatal || fatal_latched_q;
    assign failed_o = phy_failed_o || mac_failed_o;
    assign sof_enable_o = phy_sof_enable && !failed_o;
    assign traffic_enable_o = phy_traffic_enable && !failed_o;
    assign ulpi_data_oe_o = phy_oe && !mac_failed_o;
    assign ulpi_stp_o = phy_stp || mac_failed_o;
    assign transaction_reset_n_o = phy_reset_n && !failed_o;
    assign command_ready_o = command_ready && !failed_o;
    assign transmit_ready_o = transmit_ready && !failed_o;
    assign result_valid_o = result_valid && !failed_o;
    assign receive_valid_o = receive_valid && !failed_o;

    workstation_usb2_host_phy #(.ATTACH_DEBOUNCE_US(ATTACH_DEBOUNCE_US)) phy (
        .clk_ref(clk_ref), .clk_ulpi(clk_ulpi), .reset_n(reset_n), .enable_i(enable_i && !fatal_latched_q),
        .hs_enable_i(hs_enable_i), .reset_request_i(reset_request_i), .mac_idle_i(mac_idle),
        .ulpi_data_i(ulpi_data_i), .ulpi_dir_i(ulpi_dir_i), .ulpi_nxt_i(ulpi_nxt_i),
        .ulpi_data_o(ulpi_data_o), .ulpi_data_oe_o(phy_oe), .ulpi_stp_o(phy_stp),
        .mac_data_i(mac_txdata), .mac_txvalid_i(mac_txvalid), .mac_txready_o(mac_txready),
        .mac_data_o(mac_rxdata), .mac_rxvalid_o(mac_rxvalid), .mac_rxactive_o(mac_rxactive),
        .mac_rxerror_o(mac_rxerror), .mac_txend_o(mac_txend), .mac_line_valid_o(mac_line_valid),
        .mac_reset_n_o(phy_reset_n), .connected_o(connected_o), .high_speed_o(high_speed_o),
        .sof_enable_o(phy_sof_enable), .traffic_enable_o(phy_traffic_enable), .reset_active_o(reset_active_o),
        .session_reset_o(session_reset_o), .unsupported_low_speed_o(unsupported_low_speed_o),
        .failed_o(phy_failed_o), .port_state_o(port_state_o), .port_failure_code_o(port_failure_code_o),
        .chirp_count_o(unused_chirp_count), .port_last_function_o(function_o),
        .port_last_response_o(unused_last_response), .port_csr_retries_o(unused_csr_retries),
        .phy_ready_o(phy_ready_o), .clock_running_o(unused_clock_running),
        .clock_present_o(unused_clock_present), .clock_failed_o(unused_clock_failed),
        .clock_failure_code_o(clock_failure_code_o), .init_failed_o(unused_init_failed), .init_failure_code_o(init_failure_code_o),
        .init_stage_o(init_stage_o), .init_retry_count_o(unused_init_retries),
        .init_last_data_o(unused_init_data), .init_last_error_o(unused_init_error),
        .vendor_id_o(vendor_id_o), .product_id_o(product_id_o), .init_function_control_o(unused_init_function),
        .init_interface_control_o(unused_interface), .init_otg_control_o(unused_otg),
        .linestate_o(line_state), .vbus_state_o(unused_vbus), .id_state_o(unused_id),
        .host_disconnect_o(unused_disconnect), .tx_abort_o(unused_tx_abort), .link_fatal_o(unused_link_fatal),
        .received_bytes_o(received_bytes_o), .transmitted_bytes_o(transmitted_bytes_o), .rxcmd_count_o(unused_rxcmd_count)
    );

    workstation_usb2_host_mac #(
        .UPLOAD_TIMEOUT_CYCLES(UPLOAD_TIMEOUT_CYCLES), .PACKET_TIMEOUT_CYCLES(PACKET_TIMEOUT_CYCLES)
    ) mac (
        .clk_ulpi(clk_ulpi), .reset_n(phy_reset_n), .fault_reset_n(fault_release_q[1]), .high_speed_i(high_speed_o),
        .sof_enable_i(sof_enable_o), .traffic_enable_i(traffic_enable_o),
        .command_valid_i(command_valid_i && !failed_o), .command_ready_o(command_ready),
        .command_pid_i(command_pid_i), .command_device_i(command_device_i), .command_endpoint_i(command_endpoint_i),
        .command_toggle_i(command_toggle_i), .command_length_i(command_length_i),
        .transmit_data_i(transmit_data_i), .transmit_valid_i(transmit_valid_i && !failed_o),
        .transmit_ready_o(transmit_ready), .result_valid_o(result_valid), .result_ready_i(result_ready_i && !failed_o),
        .result_status_o(result_status_o), .result_pid_o(result_pid_o), .result_length_o(result_length_o),
        .receive_data_o(receive_data_o), .receive_valid_o(receive_valid),
        .receive_ready_i(receive_ready_i && !failed_o), .receive_last_o(receive_last_o),
        .utmi_data_o(mac_txdata), .utmi_txvalid_o(mac_txvalid), .utmi_txready_i(mac_txready),
        .tx_end_i(mac_txend), .utmi_data_i(mac_rxdata), .utmi_rxvalid_i(mac_rxvalid),
        .utmi_rxactive_i(mac_rxactive), .utmi_rxerror_i(mac_rxerror), .linestate_i(line_state),
        .line_valid_i(mac_line_valid), .idle_o(mac_idle), .fatal_o(mac_fatal), .sof_count_o(sof_count_o),
        .missed_sof_o(missed_sof_o), .frame_number_o(frame_number_o), .microframe_o(microframe_o), .state_o(mac_state_o)
    );
endmodule
