`timescale 1ns/1ps
module tb_workstation_usb2_soc_25k #(
    parameter integer HIGH_SPEED = 1
);
    reg clk_cpu = 0, clk_ref = 0, clk_ulpi = 0, reset_n = 1;
    always #10.417 clk_cpu = !clk_cpu;
    always #10 clk_ref = !clk_ref;
    always #8.333 clk_ulpi = !clk_ulpi;
    wire [7:0] host_data, phy_data;
    wire host_oe, host_stp, phy_oe, phy_dir, phy_nxt;
    tri [7:0] physical_data;
    assign physical_data = host_oe ? host_data : 8'hzz;
    assign physical_data = phy_oe ? phy_data : 8'hzz;
    wire service_valid, service_write;
    wire [7:0] service_address;
    wire [31:0] service_data;
    wire [3:0] service_mask, cpu_fault;
    wire [31:0] cpu_fault_address, sof_count;
    wire transaction_reset_n, phy_ready, failed, high_speed, traffic_enable;
    integer service_delay = 0;
    wire service_ready = service_delay >= 5;
    reg stall_phy = 0;
    wire [31:0] normal_packets;
    wire [7:0] device_txdata, device_rxdata, device_out_data;
    wire device_txvalid, device_txready, device_rxvalid, device_rxactive;
    wire device_chirp, device_term, device_hs, device_configured, device_in_accept, device_out_valid;
    wire [1:0] device_xcvr, device_line;
    wire [6:0] device_address;
    reg [7:0] loopback [0:2047];
    integer write_index = 0, read_index = 0, fifo_count = 0;
    wire loopback_valid = fifo_count != 0;
    workstation_usb2_soc #(.ATTACH_DEBOUNCE_US(100)) host (
        .clk_cpu(clk_cpu), .clk_ref(clk_ref), .clk_ulpi(clk_ulpi), .reset_n(reset_n), .uart_rx_i(1'b1), .uart_tx_o(),
        .ulpi_data_i(physical_data), .ulpi_dir_i(phy_dir), .ulpi_nxt_i(phy_nxt),
        .ulpi_data_o(host_data), .ulpi_data_oe_o(host_oe), .ulpi_stp_o(host_stp),
        .service_valid_o(service_valid), .service_write_o(service_write), .service_address_o(service_address),
        .service_write_data_o(service_data), .service_mask_o(service_mask),
        .service_ready_i(service_ready), .service_error_i(1'b0), .service_read_data_i(HIGH_SPEED != 0 ? 32'd1 : 32'd0),
        .cpu_fault_o(cpu_fault), .cpu_fault_address_o(cpu_fault_address), .transaction_reset_n_o(transaction_reset_n),
        .phy_ready_o(phy_ready), .failed_o(failed), .high_speed_o(high_speed), .traffic_enable_o(traffic_enable), .sof_count_o(sof_count)
    );
    usb3300_host_model #(.HIGH_SPEED(HIGH_SPEED)) phy (
        .clk_ulpi(clk_ulpi), .reset_n(reset_n), .runtime_i(transaction_reset_n), .attached_i(1'b1),
        .stall_i(stall_phy), .link_data_i(physical_data), .link_oe_i(host_oe), .link_stp_i(host_stp),
        .phy_data_o(phy_data), .phy_oe_o(phy_oe), .phy_dir_o(phy_dir), .phy_nxt_o(phy_nxt),
        .device_txdata_i(device_txdata), .device_txvalid_i(device_txvalid), .device_chirp_i(device_chirp),
        .device_xcvr_i(device_xcvr), .device_term_i(device_term), .device_txready_o(device_txready),
        .device_rxdata_o(device_rxdata), .device_rxvalid_o(device_rxvalid), .device_rxactive_o(device_rxactive),
        .device_line_o(device_line), .function_o(), .normal_packets_o(normal_packets)
    );
    usb_cdc_core #(.USB_SPEED_HS(HIGH_SPEED != 0 ? "True" : "False")) device (
        .clk_i(clk_ulpi), .rst_i(!reset_n), .enable_i(reset_n),
        .utmi_data_in_i(device_rxdata), .utmi_txready_i(device_txready), .utmi_rxvalid_i(device_rxvalid),
        .utmi_rxactive_i(device_rxactive), .utmi_rxerror_i(1'b0), .utmi_linestate_i(device_line),
        .inport_valid_i(loopback_valid), .inport_data_i(loopback[read_index]), .outport_accept_i(fifo_count < 1536),
        .utmi_data_out_o(device_txdata), .utmi_txvalid_o(device_txvalid), .utmi_op_mode_o(), .utmi_xcvrselect_o(device_xcvr),
        .utmi_termselect_o(device_term), .utmi_dppulldown_o(), .utmi_dmpulldown_o(), .inport_accept_o(device_in_accept),
        .outport_valid_o(device_out_valid), .outport_data_o(device_out_data), .hs_active_o(device_hs),
        .configured_o(device_configured), .usb_reset_o(), .chirp_active_o(device_chirp), .hs_state_o(), .device_address_o(device_address)
    );
    always @(posedge clk_ulpi) begin
        if (host_oe && phy_oe) $fatal(1, "native CPU ULPI bus contention");
        if (!reset_n) begin write_index <= 0; read_index <= 0; fifo_count <= 0; end
        else begin
            if (device_out_valid) begin loopback[write_index] <= device_out_data; write_index <= (write_index + 1) % 2048; end
            if (loopback_valid && device_in_accept) read_index <= (read_index + 1) % 2048;
            case ({device_out_valid, loopback_valid && device_in_accept})
                2'b10: fifo_count <= fifo_count + 1;
                2'b01: fifo_count <= fifo_count - 1;
                default: begin end
            endcase
        end
    end
    always @(posedge clk_cpu) begin
        if (!reset_n || !service_valid) service_delay <= 0;
        else if (!service_ready) service_delay <= service_delay + 1;
        if (service_valid && service_ready && service_write) begin
            if (service_mask != 15) $fatal(1, "native CPU service mask");
            if (service_address == 8'hf4) stall_phy <= service_data[0];
            if (service_address == 8'hf8) $display("CPU stage %08x HS=%0d time=%0t", service_data, HIGH_SPEED, $time);
            if (service_address == 8'hfc) begin
                if (service_data != (32'h600d0000 | (HIGH_SPEED != 0 ? 512 : 64)))
                    $fatal(1, "firmware failure %08x pc=%08x fault=%x addr=%08x", service_data, host.instruction_address, cpu_fault, cpu_fault_address);
                if (cpu_fault != 0 || failed || !phy_ready || !traffic_enable || high_speed != (HIGH_SPEED != 0) ||
                    device_hs != (HIGH_SPEED != 0) || device_address != 0 || device_configured || fifo_count != 0 ||
                    normal_packets < (HIGH_SPEED != 0 ? 100 : 50) || sof_count < (HIGH_SPEED != 0 ? 80 : 10))
                    $fatal(1, "CPU completed without full device/host acceptance");
                $display("PASS workstation_usb2_soc_25k: HS=%0d actual RV32I/ROM/driver/USB2 enumeration/%0d-byte loopback/reset/fault recovery", HIGH_SPEED, HIGH_SPEED != 0 ? 512 : 64);
                $finish;
            end
        end
    end
    initial begin #1; reset_n = 0; repeat (10) @(negedge clk_cpu); reset_n = 1; end
    initial begin #600000000; $fatal(1, "CPU firmware timeout pc=%08x stage=%0d fault=%x", host.instruction_address, host.bus.state_q, cpu_fault); end
endmodule
