module workstation_usb2_host_mmio #(
    parameter integer ATTACH_DEBOUNCE_US = 100000,
    parameter integer TRANSACTION_TIMEOUT_CYCLES = 120000
)(
    input wire clk_cpu,
    input wire clk_ref,
    input wire clk_ulpi,
    input wire reset_n,
    input wire reg_cs_i,
    input wire reg_wr_i,
    input wire [7:0] reg_addr_i,
    input wire [31:0] reg_wdata_i,
    input wire [3:0] reg_be_i,
    output wire reg_ack_o,
    output wire reg_error_o,
    output wire [31:0] reg_rdata_o,
    output wire irq_o,
    input wire [7:0] ulpi_data_i,
    input wire ulpi_dir_i,
    input wire ulpi_nxt_i,
    output wire [7:0] ulpi_data_o,
    output wire ulpi_data_oe_o,
    output wire ulpi_stp_o,
    output wire transaction_reset_n_o,
    output wire phy_ready_o,
    output wire failed_o,
    output wire high_speed_o,
    output wire traffic_enable_o,
    output wire [31:0] sof_count_o
);
    wire enable_cpu, hs_enable, reset_request;
    (* async_reg = "true" *) reg [1:0] enable_ref_q;
    reg [2:0] reference_fault_q;
    wire command_valid, command_ready, command_toggle, transmit_valid, transmit_ready;
    wire result_valid, result_ready, receive_valid, receive_ready, receive_last;
    wire [7:0] command_pid, transmit_data, result_pid, receive_data;
    wire [6:0] command_device;
    wire [3:0] command_endpoint, result_status, port_failure, mac_state, init_failure;
    wire [9:0] command_length, result_length;
    wire connected, sof_enable, reset_active, unsupported_low_speed, mac_failed, phy_failed;
    wire [4:0] port_state, init_stage;
    wire [1:0] clock_failure;
    wire [15:0] unused_missed_sof, unused_vendor, unused_product;
    wire [10:0] unused_frame;
    wire [2:0] unused_microframe;
    wire [7:0] unused_function;
    wire [31:0] unused_received, unused_transmitted;
    wire unused_session_reset;
    wire [15:0] status = {7'd0, unsupported_low_speed, reset_active, sof_enable,
                          phy_failed, failed_o, traffic_enable_o, high_speed_o, connected, phy_ready_o};
    wire [31:0] diagnostic = {7'd0, clock_failure, init_stage, init_failure, mac_state, port_failure, port_state, mac_failed};

    always @(posedge clk_ref or negedge reset_n)
        if (!reset_n) begin enable_ref_q <= 0; reference_fault_q <= 0; end
        else begin
            enable_ref_q <= {enable_ref_q[0], enable_cpu};
            reference_fault_q <= {clock_failure == 2'd3, clock_failure == 2'd2, clock_failure == 2'd1};
        end

    workstation_usb2_cpu_bridge #(.TRANSACTION_TIMEOUT_CYCLES(TRANSACTION_TIMEOUT_CYCLES)) bridge (
        .clk_cpu(clk_cpu), .clk_ulpi(clk_ulpi), .reset_n(reset_n), .session_reset_n_i(transaction_reset_n_o),
        .reg_cs_i(reg_cs_i), .reg_wr_i(reg_wr_i), .reg_addr_i(reg_addr_i), .reg_wdata_i(reg_wdata_i), .reg_be_i(reg_be_i),
        .reg_ack_o(reg_ack_o), .reg_error_o(reg_error_o), .reg_rdata_o(reg_rdata_o), .irq_o(irq_o),
        .enable_o(enable_cpu), .hs_enable_o(hs_enable), .reset_request_o(reset_request),
        .status_i(status), .diagnostic_i(diagnostic), .sof_count_i(sof_count_o), .reference_fault_i(reference_fault_q),
        .command_valid_o(command_valid), .command_ready_i(command_ready), .command_pid_o(command_pid),
        .command_device_o(command_device), .command_endpoint_o(command_endpoint), .command_toggle_o(command_toggle),
        .command_length_o(command_length), .transmit_data_o(transmit_data), .transmit_valid_o(transmit_valid),
        .transmit_ready_i(transmit_ready), .result_valid_i(result_valid), .result_ready_o(result_ready),
        .result_status_i(result_status), .result_pid_i(result_pid), .result_length_i(result_length),
        .receive_data_i(receive_data), .receive_valid_i(receive_valid), .receive_ready_o(receive_ready), .receive_last_i(receive_last)
    );
    workstation_usb2_host_controller #(.ATTACH_DEBOUNCE_US(ATTACH_DEBOUNCE_US)) controller (
        .clk_ref(clk_ref), .clk_ulpi(clk_ulpi), .reset_n(reset_n), .enable_i(enable_ref_q[1]),
        .hs_enable_i(hs_enable), .reset_request_i(reset_request),
        .ulpi_data_i(ulpi_data_i), .ulpi_dir_i(ulpi_dir_i), .ulpi_nxt_i(ulpi_nxt_i),
        .ulpi_data_o(ulpi_data_o), .ulpi_data_oe_o(ulpi_data_oe_o), .ulpi_stp_o(ulpi_stp_o),
        .command_valid_i(command_valid), .command_ready_o(command_ready), .command_pid_i(command_pid),
        .command_device_i(command_device), .command_endpoint_i(command_endpoint), .command_toggle_i(command_toggle),
        .command_length_i(command_length), .transmit_data_i(transmit_data), .transmit_valid_i(transmit_valid),
        .transmit_ready_o(transmit_ready), .result_valid_o(result_valid), .result_ready_i(result_ready),
        .result_status_o(result_status), .result_pid_o(result_pid), .result_length_o(result_length),
        .receive_data_o(receive_data), .receive_valid_o(receive_valid), .receive_ready_i(receive_ready), .receive_last_o(receive_last),
        .transaction_reset_n_o(transaction_reset_n_o), .connected_o(connected), .high_speed_o(high_speed_o),
        .sof_enable_o(sof_enable), .traffic_enable_o(traffic_enable_o), .session_reset_o(unused_session_reset),
        .reset_active_o(reset_active), .unsupported_low_speed_o(unsupported_low_speed), .failed_o(failed_o),
        .mac_failed_o(mac_failed), .phy_failed_o(phy_failed), .phy_ready_o(phy_ready_o),
        .port_state_o(port_state), .port_failure_code_o(port_failure), .mac_state_o(mac_state),
        .sof_count_o(sof_count_o), .missed_sof_o(unused_missed_sof), .frame_number_o(unused_frame), .microframe_o(unused_microframe),
        .vendor_id_o(unused_vendor), .product_id_o(unused_product), .function_o(unused_function),
        .init_failure_code_o(init_failure), .init_stage_o(init_stage), .clock_failure_code_o(clock_failure),
        .received_bytes_o(unused_received), .transmitted_bytes_o(unused_transmitted)
    );
endmodule
