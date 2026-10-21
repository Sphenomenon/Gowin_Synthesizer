`timescale 1ns/1ps
module tb_workstation_usb2_25k_negotiation #(
    parameter integer DEVICE_HIGH_SPEED = 1
);
    reg clk_ulpi = 1'b0;
    always #8.333 clk_ulpi = ~clk_ulpi;
    reg clk_ref = 1'b0;
    always #10 clk_ref = ~clk_ref;
    reg reset_n = 1'b0;
    wire [7:0] host_data;
    wire host_oe;
    wire host_stp;
    wire [7:0] phy_data;
    wire phy_oe;
    wire phy_dir;
    wire phy_nxt;
    tri [7:0] physical_data;
    assign physical_data = host_oe ? host_data : 8'hzz;
    assign physical_data = phy_oe ? phy_data : 8'hzz;
    wire [7:0] function_value;
    wire host_chirp_valid;
    wire [7:0] host_chirp_data;
    wire [7:0] device_txdata;
    wire device_txvalid;
    wire [1:0] device_opmode;
    wire [1:0] device_xcvr;
    wire device_term;
    wire device_hs;
    wire device_chirping;
    wire [2:0] device_state;
    wire high_speed;
    wire sof_enable;
    wire traffic_enable;
    wire reset_active;
    wire mac_reset_n;
    wire failed;
    wire [3:0] port_failure;
    wire [4:0] port_state;
    wire [15:0] chirp_count;
    wire [7:0] last_function;
    wire phy_ready;
    wire [15:0] vendor_id;
    wire [15:0] product_id;
    wire link_fatal;
    wire [31:0] received_bytes;
    wire [31:0] transmitted_bytes;
    wire device_raw_k = device_txvalid && device_opmode == 2 && device_txdata == 0;
    integer cycle_count = 0;
    integer reset_start_cycle = -1;
    integer chirp_end_cycle = -1;
    integer sof_start_cycle = -1;
    integer raw_bytes = 0;
    integer segment_bytes = 0;
    integer segments = 0;
    integer checks = 0;
    reg last_j = 1'b0;
    reg raw_active_q = 1'b0;
    reg [7:0] function_q = 8'h41;
    reg [12:0] activity_q = 0;
    wire [1:0] bus_line = host_chirp_valid ? (host_chirp_data == 0 ? 2'b10 : 2'b01) :
                          device_raw_k ? 2'b10 :
                          ((function_value == 8'h45 || function_value == 8'h41) && device_term && device_xcvr == 1) ? 2'b01 :
                          (sof_enable && activity_q < 4) ? 2'b01 : 2'b00;

    workstation_usb2_host_phy #(.ATTACH_DEBOUNCE_US(100)) host (
        .clk_ref(clk_ref), .clk_ulpi(clk_ulpi), .reset_n(reset_n), .enable_i(1'b1),
        .hs_enable_i(1'b1), .reset_request_i(1'b0), .mac_idle_i(1'b1),
        .ulpi_data_i(physical_data), .ulpi_dir_i(phy_dir), .ulpi_nxt_i(phy_nxt),
        .ulpi_data_o(host_data), .ulpi_data_oe_o(host_oe), .ulpi_stp_o(host_stp),
        .mac_data_i(8'h00), .mac_txvalid_i(1'b0), .mac_txready_o(),
        .mac_data_o(), .mac_rxvalid_o(), .mac_rxactive_o(), .mac_rxerror_o(), .mac_reset_n_o(mac_reset_n),
        .connected_o(), .high_speed_o(high_speed), .sof_enable_o(sof_enable), .traffic_enable_o(traffic_enable),
        .reset_active_o(reset_active), .session_reset_o(), .unsupported_low_speed_o(),
        .failed_o(failed), .port_state_o(port_state), .port_failure_code_o(port_failure),
        .chirp_count_o(chirp_count), .port_last_function_o(last_function), .port_last_response_o(), .port_csr_retries_o(),
        .phy_ready_o(phy_ready), .clock_running_o(), .clock_present_o(), .clock_failed_o(), .clock_failure_code_o(),
        .init_failed_o(), .init_failure_code_o(), .init_stage_o(), .init_retry_count_o(), .init_last_data_o(), .init_last_error_o(),
        .vendor_id_o(vendor_id), .product_id_o(product_id), .init_function_control_o(), .init_interface_control_o(),
        .init_otg_control_o(), .linestate_o(), .vbus_state_o(), .id_state_o(), .host_disconnect_o(), .tx_abort_o(),
        .link_fatal_o(link_fatal), .received_bytes_o(received_bytes), .transmitted_bytes_o(transmitted_bytes), .rxcmd_count_o()
    );
    usb3300_register_model #(.HOST_PORT_MODEL(1)) phy (
        .clk_ulpi(clk_ulpi), .reset_n(reset_n), .fault_i(4'd0), .link_data_i(physical_data),
        .link_data_oe_i(host_oe), .link_stp_i(host_stp), .phy_data_o(phy_data), .phy_data_oe_o(phy_oe),
        .phy_dir_o(phy_dir), .phy_nxt_o(phy_nxt), .completed_o(), .scratch_o(),
        .device_line_i(bus_line), .function_o(function_value), .host_chirp_valid_o(host_chirp_valid), .host_chirp_data_o(host_chirp_data)
    );
    usb_cdc_core #(.USB_SPEED_HS(DEVICE_HIGH_SPEED != 0 ? "True" : "False")) device_core (
        .clk_i(clk_ulpi), .rst_i(!reset_n), .enable_i(1'b1),
        .utmi_data_in_i(8'h00), .utmi_txready_i(1'b1), .utmi_rxvalid_i(1'b0),
        .utmi_rxactive_i(1'b0), .utmi_rxerror_i(1'b0), .utmi_linestate_i(bus_line),
        .inport_valid_i(1'b0), .inport_data_i(8'h00), .outport_accept_i(1'b1),
        .utmi_data_out_o(device_txdata), .utmi_txvalid_o(device_txvalid), .utmi_op_mode_o(device_opmode),
        .utmi_xcvrselect_o(device_xcvr), .utmi_termselect_o(device_term), .utmi_dppulldown_o(), .utmi_dmpulldown_o(),
        .inport_accept_o(), .outport_valid_o(), .outport_data_o(), .hs_active_o(device_hs), .configured_o(),
        .usb_reset_o(), .chirp_active_o(device_chirping), .hs_state_o(device_state), .device_address_o()
    );

    task automatic check(input reg condition, input string message);
        begin
            checks = checks + 1;
            if (condition !== 1'b1)
                $fatal(1, "%s: deviceHS=%0d hostState=%0d failure=%0d phyFC=%02x deviceState=%0d cycle=%0d",
                       message, DEVICE_HIGH_SPEED, port_state, port_failure, function_value, device_state, cycle_count);
        end
    endtask

    always @(posedge clk_ulpi) begin
        cycle_count = cycle_count + 1;
        if (!reset_n)
            activity_q <= 0;
        else if (sof_enable) begin
            if (activity_q == 7499)
                activity_q <= 0;
            else
                activity_q <= activity_q + 1'b1;
        end else
            activity_q <= 0;
        if (reset_n) begin
            if (failed || link_fatal)
                check(1'b0, "real composition may not fail or timeout during legal reset/chirp");
            if (host_oe && phy_oe)
                check(1'b0, "ULPI physical contention");
            if (function_value == 8'h50 && function_q != 8'h50)
                reset_start_cycle = cycle_count;
            function_q = function_value;
            if (host_chirp_valid) begin
                if (segment_bytes == 0) begin
                    check(host_chirp_data == 0, "first raw chirp is K");
                    last_j = 1'b0;
                end else if (last_j != (host_chirp_data == 8'hff)) begin
                    check(segment_bytes == 3000, "physical raw K/J duration exactly 50 us at 60 MHz");
                    segment_bytes = 0;
                    segments = segments + 1;
                    last_j = !last_j;
                end
                segment_bytes = segment_bytes + 1;
                raw_bytes = raw_bytes + 1;
                raw_active_q = 1'b1;
            end else if (raw_active_q) begin
                check(segment_bytes == 3000 && last_j && segments >= 5, "physical train ends with complete KJ KJ KJ or longer");
                raw_active_q = 1'b0;
                chirp_end_cycle = cycle_count;
            end
        end
    end

    always @(posedge sof_enable) begin
        if (reset_n && sof_start_cycle < 0) begin
            sof_start_cycle = cycle_count;
            check(cycle_count - reset_start_cycle >= 3000000, "real root reset is at least 50 ms");
            if (DEVICE_HIGH_SPEED != 0)
                check(cycle_count - chirp_end_cycle >= 6000 && cycle_count - chirp_end_cycle <= 30000,
                      "physical chirp ends 100-500 us before reset release");
        end
    end

    initial begin
        repeat (10) @(negedge clk_ref);
        reset_n = 1'b1;
        wait (traffic_enable || failed);
        @(negedge clk_ulpi);
        check(traffic_enable && phy_ready && !failed && mac_reset_n, "actual host composition hands off after recovery");
        check(cycle_count - sof_start_cycle >= 600000, "normal transactions wait 10 ms after real reset");
        check(vendor_id == 16'h0424 && product_id == 16'h0004 && received_bytes == 0, "physical CSR identity is not fake USB traffic");
        check(high_speed == (DEVICE_HIGH_SPEED != 0) && device_hs == (DEVICE_HIGH_SPEED != 0),
              "both actual Host and existing 25K device core agree on speed");
        check(function_value == (DEVICE_HIGH_SPEED != 0 ? 8'h40 : 8'h45) && last_function == function_value,
              "verified PHY configuration agrees with negotiated speed");
        if (DEVICE_HIGH_SPEED != 0) begin
            check(raw_bytes > 60000 && transmitted_bytes == raw_bytes && chirp_count == segments + 1,
                  "long NOPID train exceeds ordinary 1 ms watchdog without weakening packet timeout");
            check(!device_chirping, "25K completed its device chirp rather than remaining in a diagnostic phase");
        end else
            check(raw_bytes == 0 && transmitted_bytes == 0 && chirp_count == 0, "FS-only device produces no host chirps");
        $display("PASS workstation_usb2_25k_negotiation: deviceHS=%0d, %0d checks, %0d cycles, %0d physical raw bytes, %0d chirps, default 60MHz/50ms reset/10ms recovery", DEVICE_HIGH_SPEED, checks, cycle_count, raw_bytes, chirp_count);
        $finish;
    end

    initial begin
        #80000000;
        $fatal(1, "real-time negotiation timeout: hostState=%0d deviceState=%0d", port_state, device_state);
    end
endmodule
