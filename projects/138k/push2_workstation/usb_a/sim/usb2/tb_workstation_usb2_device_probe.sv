`timescale 1ns/1ps
module tb_workstation_usb2_device_probe;
    reg clk = 0;
    always #10 clk = !clk;
    tri [7:0] data;
    workstation_usb2_device_probe_top #(.POWER_ON_CYCLES(8)) dut (
        .clk_50m(clk), .usb2_ulpi_clk(clk), .usb2_ulpi_data(data),
        .usb2_ulpi_dir(1'b0), .usb2_ulpi_nxt(1'b0), .usb2_ulpi_stp()
    );
    initial begin
        wait (!dut.reset);
        @(negedge clk);
        dut.u_device.midi_source_valid = 1;
        dut.u_device.bulk_source_valid = 1;
        repeat (4) @(negedge clk);
        if (dut.midi_rx_words != 0 || dut.bulk_rx_bytes != 0)
            $fatal(1, "counted data while stalled");
        dut.u_device.midi_sink_ready = 1;
        repeat (3) @(negedge clk);
        dut.u_device.midi_source_valid = 0;
        dut.u_device.bulk_sink_ready = 1;
        repeat (100) @(negedge clk);
        dut.u_device.bulk_source_valid = 0;
        repeat (2) @(negedge clk);
        if (dut.midi_rx_words != 3 || dut.midi_tx_words != 3 ||
            dut.bulk_rx_bytes != 100 || dut.bulk_tx_bytes != 100)
            $fatal(1, "accepted-data counters differ");
        if (dut.status_50mhz[127:0] != {32'd100, 32'd100, 16'd3, 16'd3, 32'h12345678})
            $fatal(1, "observer packing differs");
        if (dut.status_50mhz[159:128] == 0)
            $fatal(1, "independent reference counter stopped");
        $display("PASS workstation_usb2_device_probe: stall, MIDI echo, byte echo and observer counts");
        $finish;
    end
    initial begin #100000; $fatal(1, "probe timeout"); end
endmodule

module midi_usb2_link #(parameter integer ATTACH_DELAY_CYCLES = 0) (
    input wire clk_50mhz, reset, clk_ulpi60,
    inout wire [7:0] ulpi_data,
    input wire ulpi_dir, ulpi_nxt,
    output wire ulpi_stp,
    input wire midi_tx_valid,
    output wire midi_tx_ready,
    input wire [31:0] midi_tx_data,
    output wire midi_rx_valid,
    input wire midi_rx_ready,
    output wire [31:0] midi_rx_data,
    input wire control_tx_valid,
    output wire control_tx_ready,
    input wire [7:0] control_tx_data,
    output wire control_rx_valid,
    input wire control_rx_ready,
    output wire [7:0] control_rx_data,
    output wire online, control_reset, hs_active,
    output wire [31:0] debug_status, probe_history,
    output wire [191:0] probe_statistics
);
    reg midi_source_valid = 0, midi_sink_ready = 0;
    reg bulk_source_valid = 0, bulk_sink_ready = 0;
    assign ulpi_stp = reset;
    assign midi_tx_ready = midi_sink_ready;
    assign midi_rx_valid = midi_source_valid;
    assign midi_rx_data = 32'h00903c09;
    assign control_tx_ready = bulk_sink_ready;
    assign control_rx_valid = bulk_source_valid;
    assign control_rx_data = 8'ha5;
    assign online = !reset;
    assign control_reset = reset;
    assign hs_active = !reset;
    assign debug_status = 32'h12345678;
    assign probe_history = 32'h0002000d;
    assign probe_statistics = 192'd0;
    always @(posedge clk_50mhz) begin
        if (midi_tx_valid !== midi_source_valid || midi_rx_ready !== midi_sink_ready || midi_tx_data !== midi_rx_data)
            $fatal(1, "MIDI loopback wiring differs");
        if (control_tx_valid !== bulk_source_valid || control_rx_ready !== bulk_sink_ready || control_tx_data !== control_rx_data)
            $fatal(1, "byte loopback wiring differs");
    end
endmodule
