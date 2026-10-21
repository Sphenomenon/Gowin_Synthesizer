`timescale 1ns/1ps
module tb_workstation_usb2_application_25k #(
    parameter integer HIGH_SPEED = 1,
    parameter integer TRACE_LINK = 0
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
    wire [31:0] cpu_fault_address, sof_count, normal_packets;
    wire transaction_reset_n, phy_ready, failed, high_speed, traffic_enable;
    integer service_delay = 0;
    wire service_ready = service_delay >= 5;
    reg [31:0] connected = 0;
    integer midi_sent = 0, midi_received = 0, tiles = 0, tile_delay = 0;
    wire [7:0] note_number = 8'd36 + 8'(midi_sent >> 1);
    wire [31:0] midi_word = midi_sent[0] ? {8'd0, note_number, 8'h80, 8'h08} :
                                                    {8'd100, note_number, 8'h90, 8'h09};
    wire midi_ready, unexpected_midi_valid;
    wire [31:0] unexpected_midi_data;
    wire [7:0] device_txdata, device_rxdata, control_txdata, control_rxdata;
    wire device_txvalid, device_txready, device_rxvalid, device_rxactive, device_term;
    wire [1:0] device_xcvr, device_line;
    wire device_hs, device_configured, control_reset, control_txvalid, control_txready, control_rxvalid, control_rxready;
    wire [6:0] device_address;
    wire tile_valid, remote_enable;
    wire [8:0] tile_x, tile_width;
    wire [7:0] tile_y, tile_height;
    wire [15:0] protocol_errors;
    reg tile_done = 0;
    wire [31:0] expected_event = (midi_received[0] ? 32'd0 : 32'd16384) |
                                 ((32'd36 + 32'(midi_received >> 1)) << 7) |
                                 (midi_received[0] ? 32'd0 : 32'd100);
    reg [2:0] previous_device_state;
    reg previous_runtime;
    integer traced_results = 0;

    always @(posedge clk_ulpi) begin
        previous_device_state <= device.phy_state;
        previous_runtime <= transaction_reset_n;
        if (TRACE_LINK != 0) begin
            if (device.phy_state != previous_device_state || transaction_reset_n != previous_runtime)
                $display("LINK %0t device=%0d timer=%0d line=%b function=%x runtime=%b port=%0d", $time,
                         device.phy_state, device.phy.usb_rst_time_q, device_line, phy.function_o,
                         transaction_reset_n, host.usb.port_state);
            if (host.usb.result_valid && host.usb.result_ready && traced_results < 20) begin
                $display("RESULT %0t pid=%x status=%0d length=%0d device=%0d", $time,
                         host.usb.result_pid, host.usb.result_status, host.usb.result_length, device.phy_state);
                traced_results <= traced_results + 1;
            end
        end
    end

    workstation_usb2_soc #(.ATTACH_DEBOUNCE_US(100)) host (
        .clk_cpu(clk_cpu), .clk_ref(clk_ref), .clk_ulpi(clk_ulpi), .reset_n(reset_n), .uart_rx_i(1'b1), .uart_tx_o(),
        .ulpi_data_i(physical_data), .ulpi_dir_i(phy_dir), .ulpi_nxt_i(phy_nxt),
        .ulpi_data_o(host_data), .ulpi_data_oe_o(host_oe), .ulpi_stp_o(host_stp),
        .service_valid_o(service_valid), .service_write_o(service_write), .service_address_o(service_address),
        .service_write_data_o(service_data), .service_mask_o(service_mask),
        .service_ready_i(service_ready), .service_error_i(1'b0), .service_read_data_i(32'd0),
        .cpu_fault_o(cpu_fault), .cpu_fault_address_o(cpu_fault_address), .transaction_reset_n_o(transaction_reset_n),
        .phy_ready_o(phy_ready), .failed_o(failed), .high_speed_o(high_speed), .traffic_enable_o(traffic_enable), .sof_count_o(sof_count)
    );
    usb3300_host_model #(.HIGH_SPEED(HIGH_SPEED)) phy (
        .clk_ulpi(clk_ulpi), .reset_n(reset_n), .runtime_i(transaction_reset_n), .attached_i(1'b1), .stall_i(1'b0),
        .link_data_i(physical_data), .link_oe_i(host_oe), .link_stp_i(host_stp),
        .phy_data_o(phy_data), .phy_oe_o(phy_oe), .phy_dir_o(phy_dir), .phy_nxt_o(phy_nxt),
        .device_txdata_i(device_txdata), .device_txvalid_i(device_txvalid), .device_chirp_i(device.chirp),
        .device_xcvr_i(device_xcvr), .device_term_i(device_term), .device_txready_o(device_txready),
        .device_rxdata_o(device_rxdata), .device_rxvalid_o(device_rxvalid), .device_rxactive_o(device_rxactive),
        .device_line_o(device_line), .function_o(), .normal_packets_o(normal_packets)
    );
    midi_usb_device device (
        .clk(clk_ulpi), .reset(!reset_n), .enable(reset_n), .utmi_rxdata(device_rxdata),
        .utmi_rxvalid(device_rxvalid), .utmi_rxactive(device_rxactive), .utmi_rxerror(1'b0),
        .utmi_linestate(device_line), .utmi_txready(device_txready), .utmi_txdata(device_txdata),
        .utmi_txvalid(device_txvalid), .utmi_opmode(), .utmi_xcvr(device_xcvr), .utmi_termsel(device_term),
        .utmi_dppd(), .utmi_dmpd(), .midi_tx_valid(device_configured && midi_sent < 128),
        .midi_tx_ready(midi_ready), .midi_tx_data(midi_word), .midi_rx_valid(unexpected_midi_valid),
        .midi_rx_ready(1'b1), .midi_rx_data(unexpected_midi_data), .control_tx_valid(control_txvalid),
        .control_tx_ready(control_txready), .control_tx_data(control_txdata), .control_rx_valid(control_rxvalid),
        .control_rx_ready(control_rxready), .control_rx_data(control_rxdata), .configured(device_configured),
        .session_reset(), .midi_session_reset(), .control_session_reset(control_reset), .hs_active(device_hs),
        .phy_state(), .device_address(device_address)
    );
    panel_display_endpoint #(.CLK_HZ(60000000)) panel (
        .clk(clk_ulpi), .reset(!reset_n), .link_reset(control_reset), .rx_valid(control_rxvalid),
        .rx_ready(control_rxready), .rx_data(control_rxdata), .tx_valid(control_txvalid),
        .tx_ready(control_txready), .tx_data(control_txdata), .settings_toggle(1'b0),
        .remote_enable(remote_enable), .manual_settings(), .redraw_required(), .protocol_errors(protocol_errors),
        .tile_valid(tile_valid), .tile_ready(tile_delay == 0), .tile_x(tile_x), .tile_y(tile_y),
        .tile_width(tile_width), .tile_height(tile_height), .tile_read_addr(8'd0), .tile_read_data(), .tile_done(tile_done)
    );
    always @(posedge clk_ulpi) begin
        if (host_oe && phy_oe) $fatal(1, "application ULPI contention");
        if (!reset_n || !device_configured) midi_sent <= 0;
        else if (midi_sent < 128 && midi_ready) midi_sent <= midi_sent + 1;
        tile_done <= tile_delay == 1;
        if (tile_delay > 0) tile_delay <= tile_delay - 1;
        if (tile_valid && tile_delay == 0) begin
            if (tile_x != 9'(tiles * 62) || tile_y != 0 || tile_width != 62 || tile_height != 4)
                $fatal(1, "production PL tile coordinates or dimensions");
            tiles <= tiles + 1; tile_delay <= 20;
        end
        if (unexpected_midi_valid) $fatal(1, "PL leaked to MIDI OUT");
    end
    always @(posedge clk_cpu) begin
        if (!reset_n || !service_valid) service_delay <= 0;
        else if (!service_ready) service_delay <= service_delay + 1;
        if (service_valid && service_ready && service_write) begin
            if (service_mask != 15) $fatal(1, "application service write mask");
            if (service_address == 0) begin connected <= service_data; $display("Application mode %0d HS=%0d at %0t", service_data, HIGH_SPEED, $time); end
            if (service_address == 8'h54) begin
                if (midi_received >= 128 || service_data != expected_event || connected != 7)
                    $fatal(1, "production MIDI event %0d got %08x expected %08x", midi_received, service_data, expected_event);
                midi_received <= midi_received + 1;
            end
        end
        if (connected == 7 && midi_received == 128 && tiles >= 2) begin
            if (cpu_fault != 0 || failed || !phy_ready || !traffic_enable || high_speed != (HIGH_SPEED != 0) ||
                device_hs != (HIGH_SPEED != 0) || !device_configured || device_address != 1 || !remote_enable ||
                protocol_errors != 0 || normal_packets < 100 || sof_count < 20)
                $fatal(1, "application acceptance fault=%x address=%08x", cpu_fault, cpu_fault_address);
            $display("PASS workstation_usb2_application_25k: HS=%0d production main/USB core/native backend/128 MIDI events/PL CAPS and two acknowledged tiles", HIGH_SPEED);
            $finish;
        end
    end
    initial begin #1; reset_n = 0; repeat (10) @(negedge clk_cpu); reset_n = 1; end
    initial begin #2000000000; $fatal(1, "application timeout pc=%08x mode=%0d midi=%0d tiles=%0d fault=%x addr=%08x device_addr=%0d config=%b hs=%b phy=%0d", host.instruction_address, connected, midi_received, tiles, cpu_fault, cpu_fault_address, device_address, device_configured, device_hs, device.phy_state); end
endmodule
