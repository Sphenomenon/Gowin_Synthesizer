`timescale 1ns/1ps
`default_nettype none
module workstation_usb2_device_probe_top #(
    parameter integer POWER_ON_CYCLES = 50000,
    parameter integer DEVICE_ATTACH_DELAY_CYCLES = 12500000
)(
    input wire clk_50m,
    input wire usb2_ulpi_clk,
    inout wire [7:0] usb2_ulpi_data,
    input wire usb2_ulpi_dir,
    input wire usb2_ulpi_nxt,
    output wire usb2_ulpi_stp
);
    reg [31:0] power_on_count = 0;
    wire reset = power_on_count < POWER_ON_CYCLES;
    always @(posedge clk_50m)
        if (reset) power_on_count <= power_on_count + 1'b1;

    wire midi_valid, midi_ready, bulk_valid, bulk_ready;
    wire [31:0] midi_data, usb_status;
    wire [31:0] probe_history;
    wire [191:0] probe_statistics;
    wire [7:0] bulk_data;
    wire online, control_reset, high_speed;
    midi_usb2_link #(.ATTACH_DELAY_CYCLES(DEVICE_ATTACH_DELAY_CYCLES)) u_device (
        .clk_50mhz(clk_50m), .reset(reset), .clk_ulpi60(usb2_ulpi_clk),
        .ulpi_data(usb2_ulpi_data), .ulpi_dir(usb2_ulpi_dir),
        .ulpi_nxt(usb2_ulpi_nxt), .ulpi_stp(usb2_ulpi_stp),
        .midi_tx_valid(midi_valid), .midi_tx_ready(midi_ready), .midi_tx_data(midi_data),
        .midi_rx_valid(midi_valid), .midi_rx_ready(midi_ready), .midi_rx_data(midi_data),
        .control_tx_valid(bulk_valid), .control_tx_ready(bulk_ready), .control_tx_data(bulk_data),
        .control_rx_valid(bulk_valid), .control_rx_ready(bulk_ready), .control_rx_data(bulk_data),
        .online(online), .control_reset(control_reset), .hs_active(high_speed),
        .debug_status(usb_status), .probe_history(probe_history), .probe_statistics(probe_statistics)
    );

    wire [223:0] native_status = {probe_statistics, probe_history};
    wire [223:0] observed_status;
    genvar monitor_index;
    generate for (monitor_index = 0; monitor_index < 7; monitor_index = monitor_index + 1) begin : observations
        midi_usb2_debug native_monitor (
            .clk_50mhz(clk_50m), .clk_ulpi60(usb2_ulpi_clk),
            .source_status(native_status[monitor_index * 32 +: 32]), .local_snapshot(32'd0),
            .local_flags({online, high_speed, !control_reset}),
            .status_50mhz(observed_status[monitor_index * 32 +: 32])
        );
    end endgenerate

    reg [15:0] midi_rx_words = 0, midi_tx_words = 0;
    reg [31:0] bulk_rx_bytes = 0, bulk_tx_bytes = 0;
    always @(posedge clk_50m) begin
        if (reset) begin
            midi_rx_words <= 0;
            midi_tx_words <= 0;
            bulk_rx_bytes <= 0;
            bulk_tx_bytes <= 0;
        end else begin
            if (midi_valid && midi_ready) begin
                midi_rx_words <= midi_rx_words + 1'b1;
                midi_tx_words <= midi_tx_words + 1'b1;
            end
            if (bulk_valid && bulk_ready) begin
                bulk_rx_bytes <= bulk_rx_bytes + 1'b1;
                bulk_tx_bytes <= bulk_tx_bytes + 1'b1;
            end
        end
    end
    reg [31:0] reference_cycles = 0;
    reg [383:0] status_50mhz /* synthesis syn_preserve=1 syn_keep=1 */;
    always @(posedge clk_50m) begin
        reference_cycles <= reference_cycles + 1'b1;
        status_50mhz <= {observed_status, reference_cycles, bulk_tx_bytes, bulk_rx_bytes, midi_tx_words, midi_rx_words, usb_status};
    end
endmodule
`default_nettype wire
