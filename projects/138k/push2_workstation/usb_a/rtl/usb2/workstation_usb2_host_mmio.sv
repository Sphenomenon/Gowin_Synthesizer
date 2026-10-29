module workstation_usb2_host_mmio #(
    parameter integer ATTACH_DEBOUNCE_US = 100000,
    parameter integer TRANSACTION_TIMEOUT_CYCLES = 120000,
    parameter integer PORT_OBSERVER = 0
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
    (* async_reg = "true", syn_preserve=1 *) reg [1:0] reference_release_q;
    wire reference_reset_n = reference_release_q[1];
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
    (* async_reg = "true", syn_preserve=1 *) reg [1:0] status_release_q;
    (* async_reg = "true", syn_preserve = 1, syn_keep = 1 *) reg [4:0] failure_meta_q, failure_sync_q;
    wire status_reset_n = status_release_q[1];
    (* syn_preserve = 1 *) reg [18:0] state_history_q;
    (* syn_preserve = 1 *) reg [15:0] failure_history_q, attempts_q;
    (* syn_preserve = 1 *) reg [3:0] last_failure_q;
    (* syn_preserve = 1 *) reg [4:0] last_failure_state_q;
    (* syn_preserve = 1 *) reg [7:0] last_failure_function_q;
    (* syn_preserve = 1 *) reg [31:0] received_peak_q, transmitted_peak_q, sof_peak_q;
    (* syn_preserve = 1 *) reg [15:0] recovery_count_q, active_count_q, recovery_aborts_q, command_count_q;
    (* syn_preserve = 1 *) reg [31:0] recovery_exit_ticks_q, recovery_exit_sofs_q, last_command_q;
    (* syn_preserve = 1 *) reg [4:0] recovery_exit_state_q;
    (* syn_preserve = 1 *) reg [7:0] recovery_exit_flags_q, recovery_exit_rxcmd_q, recovery_exit_function_q;
    (* syn_preserve = 1 *) reg [15:0] last_sof_token_q;
    (* syn_preserve = 1 *) reg [23:0] last_result_q;
    generate if (PORT_OBSERVER != 0) begin : port_observer
        reg [4:0] previous_state_q;
        reg previous_ready_q;
        reg previous_dir_q;
        reg [7:0] last_rxcmd_q, previous_flags_q, previous_function_q, sof_low_q;
        reg [31:0] recovery_ticks_q, previous_sofs_q;
        reg [1:0] sof_bytes_q;
        always @(posedge clk_ulpi or negedge status_reset_n) begin
            if (!status_reset_n) begin
                state_history_q <= 0;
                failure_history_q <= 0;
                attempts_q <= 0;
                last_failure_q <= 0;
                last_failure_state_q <= 0;
                last_failure_function_q <= 0;
                received_peak_q <= 0;
                transmitted_peak_q <= 0;
                sof_peak_q <= 0;
                previous_state_q <= 0;
                previous_ready_q <= 0;
                recovery_count_q <= 0;
                active_count_q <= 0;
                recovery_aborts_q <= 0;
                command_count_q <= 0;
                recovery_exit_ticks_q <= 0;
                recovery_exit_sofs_q <= 0;
                recovery_exit_state_q <= 0;
                recovery_exit_flags_q <= 0;
                recovery_exit_rxcmd_q <= 0;
                recovery_exit_function_q <= 0;
                last_command_q <= 0;
                last_result_q <= 0;
                last_sof_token_q <= 0;
                previous_dir_q <= 0;
                last_rxcmd_q <= 0;
                previous_flags_q <= 0;
                previous_function_q <= 0;
                previous_sofs_q <= 0;
                recovery_ticks_q <= 0;
                sof_low_q <= 0;
                sof_bytes_q <= 0;
            end else begin
                previous_state_q <= port_state;
                previous_ready_q <= phy_ready_o;
                previous_dir_q <= ulpi_dir_i;
                previous_flags_q <= {phy_ready_o, connected, high_speed_o, failure_sync_q[1],
                                     failure_sync_q[0], failure_sync_q[2], reset_active, sof_enable};
                previous_function_q <= unused_function;
                previous_sofs_q <= sof_count_o;
                if (port_state == 15) begin
                    if (recovery_ticks_q != 32'hffffffff)
                        recovery_ticks_q <= recovery_ticks_q + 1'b1;
                    if (previous_state_q != 15 && recovery_count_q != 16'hffff)
                        recovery_count_q <= recovery_count_q + 1'b1;
                end else begin
                    recovery_ticks_q <= 0;
                    if (previous_state_q == 15) begin
                        recovery_exit_ticks_q <= recovery_ticks_q;
                        recovery_exit_sofs_q <= previous_sofs_q;
                        recovery_exit_state_q <= port_state;
                        recovery_exit_flags_q <= previous_flags_q;
                        recovery_exit_rxcmd_q <= last_rxcmd_q;
                        recovery_exit_function_q <= previous_function_q;
                        if (port_state != 16 && recovery_aborts_q != 16'hffff)
                            recovery_aborts_q <= recovery_aborts_q + 1'b1;
                    end
                end
                if (port_state == 16 && previous_state_q != 16 && active_count_q != 16'hffff)
                    active_count_q <= active_count_q + 1'b1;
                if ((port_state == 15 || port_state == 16) && ulpi_dir_i && previous_dir_q && !ulpi_nxt_i)
                    last_rxcmd_q <= ulpi_data_i;
                if (ulpi_dir_i || ulpi_stp_o || port_state != 15)
                    sof_bytes_q <= 0;
                else if (ulpi_data_oe_o && ulpi_nxt_i) begin
                    if (sof_bytes_q == 2) begin
                        sof_low_q <= ulpi_data_o;
                        sof_bytes_q <= 1;
                    end else if (sof_bytes_q == 1) begin
                        last_sof_token_q <= {ulpi_data_o, sof_low_q};
                        sof_bytes_q <= 0;
                    end else if (ulpi_data_o == 8'h45)
                        sof_bytes_q <= 2;
                end
                if (command_valid && command_ready) begin
                    if (command_count_q != 16'hffff) command_count_q <= command_count_q + 1'b1;
                    last_command_q <= {2'd0, command_pid, command_device, command_endpoint, command_toggle, command_length};
                end
                if (result_valid && result_ready)
                    last_result_q <= {2'd0, result_status, result_pid, result_length};
                if (port_state <= 18)
                    state_history_q <= state_history_q | (19'b1 << port_state);
                if (phy_ready_o && !previous_ready_q && attempts_q != 16'hffff)
                    attempts_q <= attempts_q + 1'b1;
                if (port_failure != 0) begin
                    failure_history_q <= failure_history_q | (16'b1 << port_failure);
                    last_failure_q <= port_failure;
                    if (previous_state_q != 18)
                        last_failure_state_q <= previous_state_q;
                    last_failure_function_q <= unused_function;
                end
                if (unused_received > received_peak_q) received_peak_q <= unused_received;
                if (unused_transmitted > transmitted_peak_q) transmitted_peak_q <= unused_transmitted;
                if (sof_count_o > sof_peak_q) sof_peak_q <= sof_count_o;
            end
        end
    end else begin : no_port_observer
        assign {state_history_q, failure_history_q, attempts_q, last_failure_q, last_failure_state_q,
                last_failure_function_q, received_peak_q, transmitted_peak_q, sof_peak_q,
                recovery_count_q, active_count_q, recovery_aborts_q, command_count_q,
                recovery_exit_ticks_q, recovery_exit_sofs_q, recovery_exit_state_q,
                recovery_exit_flags_q, recovery_exit_rxcmd_q, recovery_exit_function_q,
                last_command_q, last_result_q, last_sof_token_q} = '0;
    end endgenerate
    always @(posedge clk_ulpi or negedge reset_n)
        if (!reset_n) status_release_q <= 0;
        else status_release_q <= {status_release_q[0], 1'b1};
    always @(posedge clk_ulpi or negedge status_reset_n)
        if (!status_reset_n) begin failure_meta_q <= 0; failure_sync_q <= 0; end
        else begin
            failure_meta_q <= {clock_failure, phy_failed, failed_o, mac_failed};
            failure_sync_q <= failure_meta_q;
        end
    wire [15:0] status = {7'd0, unsupported_low_speed, reset_active, sof_enable,
                          failure_sync_q[2:1], traffic_enable_o, high_speed_o, connected, phy_ready_o};
    wire [31:0] diagnostic = {7'd0, failure_sync_q[4:3], init_stage, init_failure, mac_state, port_failure, port_state, failure_sync_q[0]};

    always @(posedge clk_ref or negedge reset_n)
        if (!reset_n) reference_release_q <= 0;
        else reference_release_q <= {reference_release_q[0], 1'b1};

    always @(posedge clk_ref or negedge reference_reset_n)
        if (!reference_reset_n) begin enable_ref_q <= 0; reference_fault_q <= 0; end
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
        .clk_ref(clk_ref), .clk_ulpi(clk_ulpi), .reset_n(reference_reset_n), .enable_i(enable_ref_q[1]),
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
