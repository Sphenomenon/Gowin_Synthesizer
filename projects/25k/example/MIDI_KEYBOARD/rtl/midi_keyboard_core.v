`timescale 1ns/1ps
`default_nettype none

// Application framework, all ports synchronous to clk. This is not a board
// top: ULPI/USB endpoints, H5/GATT, LCD drawing and key scanning are adapters.
module midi_keyboard_core #(
    parameter integer CLOCK_HZ = 50000000,
    parameter integer FIFO_DEPTH = 16
) (
    input wire clk,
    input wire reset,
    // Assert only after USB configuration / BLE connection + CCCD subscription.
    input wire usb_online,
    input wire ble_online,
    // Abort a partial vendor request on a new USB control session. Also restores
    // channel/transpose/screen settings to defaults, without releasing keys.
    input wire control_reset,

    input wire key_valid,
    output wire key_ready,
    input wire key_down,
    input wire [6:0] key_note,
    input wire [6:0] key_velocity,

    // One USB-MIDI 1.0 four-byte event per beat, low byte first on the wire.
    output wire usb_packet_tx_valid,
    input wire usb_packet_tx_ready,
    output wire [31:0] usb_packet_tx_data,
    input wire usb_packet_rx_valid,
    output wire usb_packet_rx_ready,
    input wire [31:0] usb_packet_rx_data,
    // Inbound host messages are exposed to the application, never auto-echoed.
    output wire usb_midi_rx_valid,
    input wire usb_midi_rx_ready,
    output wire [23:0] usb_midi_rx_message,
    output wire [1:0] usb_midi_rx_length,

    // One complete BLE-MIDI characteristic value per beat, low byte first.
    output wire ble_value_tx_valid,
    input wire ble_value_tx_ready,
    output wire [39:0] ble_value_tx_data,
    output wire [2:0] ble_value_tx_length,
    input wire ble_value_rx_valid,
    output wire ble_value_rx_ready,
    input wire [39:0] ble_value_rx_data,
    input wire [2:0] ble_value_rx_length,
    output wire ble_midi_rx_valid,
    input wire ble_midi_rx_ready,
    output wire [23:0] ble_midi_rx_message,
    output wire [1:0] ble_midi_rx_length,
    output wire [12:0] ble_midi_rx_timestamp,

    // Independent USB vendor endpoint byte stream for device/screen controls.
    input wire control_rx_valid,
    output wire control_rx_ready,
    input wire [7:0] control_rx_data,
    output wire control_tx_valid,
    input wire control_tx_ready,
    output wire [7:0] control_tx_data,

    output wire [3:0] midi_channel,
    output wire signed [7:0] transpose,
    output wire [3:0] screen_page,
    output wire [15:0] theme_rgb565,
    output wire [15:0] clear_rgb565,
    output wire screen_update,
    output reg [12:0] timestamp_ms,
    output wire [7:0] active_notes,
    output wire [31:0] status_flags,
    output wire usb_queue_full,
    output wire ble_queue_full,
    output wire [15:0] ignored_key_events,
    output wire [15:0] unrouted_events,
    output wire [15:0] control_errors,
    output wire [15:0] usb_tx_errors,
    output wire [15:0] usb_rx_errors,
    output wire [15:0] ble_tx_errors,
    output wire [15:0] ble_rx_errors
);
    // CLOCK_HZ must be a positive integer multiple of 1000, >= 1000.
    localparam integer CYCLES_PER_MS = CLOCK_HZ / 1000;
    localparam integer TICK_WIDTH = (CYCLES_PER_MS > 1) ? $clog2(CYCLES_PER_MS) : 1;
    reg [TICK_WIDTH-1:0] tick_count;
    always @(posedge clk) begin
        if (reset) begin
            tick_count <= 0;
            timestamp_ms <= 13'd0;
        end else if (tick_count == CYCLES_PER_MS - 1) begin
            tick_count <= 0;
            timestamp_ms <= timestamp_ms + 1'b1;
        end else tick_count <= tick_count + 1'b1;
    end

    wire mapped_valid, mapped_ready;
    wire [23:0] mapped_message;
    wire [1:0] mapped_length;
    wire [12:0] mapped_timestamp;
    // Sidecar for the mapper's single output slot. Capture targets when the
    // key is accepted, and permanently invalidate a target if its session
    // ends while this event is blocked. Reconnection cannot add it back.
    reg [1:0] mapped_targets;
    wire [1:0] online_targets = {ble_online, usb_online};
    always @(posedge clk) begin
        if (reset) mapped_targets <= 2'b00;
        else if (key_valid && key_ready) mapped_targets <= online_targets;
        else mapped_targets <= mapped_targets & online_targets;
    end
    keyboard_event_mapper key_mapper (
        .clk(clk), .reset(reset),
        .key_valid(key_valid), .key_ready(key_ready), .key_down(key_down),
        .key_note(key_note), .key_velocity(key_velocity),
        .midi_channel(midi_channel), .transpose(transpose), .timestamp_ms(timestamp_ms),
        .event_valid(mapped_valid), .event_ready(mapped_ready),
        .event_message(mapped_message), .event_length(mapped_length),
        .event_timestamp(mapped_timestamp), .active_notes(active_notes),
        .ignored_events(ignored_key_events)
    );

    wire usb_event_valid, usb_event_ready, ble_event_valid, ble_event_ready;
    wire [23:0] usb_event_message, ble_event_message;
    wire [1:0] usb_event_length, ble_event_length;
    wire [12:0] usb_event_timestamp, ble_event_timestamp;
    midi_event_router #(.FIFO_DEPTH(FIFO_DEPTH)) router (
        .clk(clk), .reset(reset),
        .in_valid(mapped_valid), .in_ready(mapped_ready),
        .in_message(mapped_message), .in_length(mapped_length), .in_timestamp(mapped_timestamp),
        .in_targets(mapped_targets & online_targets),
        .usb_online(usb_online), .ble_online(ble_online),
        .usb_valid(usb_event_valid), .usb_ready(usb_event_ready),
        .usb_message(usb_event_message), .usb_length(usb_event_length),
        .usb_timestamp(usb_event_timestamp),
        .ble_valid(ble_event_valid), .ble_ready(ble_event_ready),
        .ble_message(ble_event_message), .ble_length(ble_event_length),
        .ble_timestamp(ble_event_timestamp),
        .usb_full(usb_queue_full), .ble_full(ble_queue_full),
        .unrouted_events(unrouted_events)
    );

    // A link going offline discards both the router queue and the codec slot.
    // No stale NoteOn or received host event survives a new link session.
    wire usb_codec_reset = reset || !usb_online;
    wire ble_codec_reset = reset || !ble_online;
    wire usb_tx_valid_internal, usb_rx_ready_internal, usb_rx_valid_internal;
    assign usb_packet_tx_valid = usb_tx_valid_internal && !usb_codec_reset;
    assign usb_packet_rx_ready = usb_rx_ready_internal && !usb_codec_reset;
    assign usb_midi_rx_valid = usb_rx_valid_internal && !usb_codec_reset;
    usb_midi_codec usb_codec (
        .clk(clk), .reset(usb_codec_reset),
        .tx_valid(usb_event_valid), .tx_ready(usb_event_ready),
        .tx_message(usb_event_message), .tx_length(usb_event_length),
        .packet_tx_valid(usb_tx_valid_internal), .packet_tx_ready(usb_packet_tx_ready),
        .packet_tx_data(usb_packet_tx_data),
        .packet_rx_valid(usb_packet_rx_valid && !usb_codec_reset),
        .packet_rx_ready(usb_rx_ready_internal), .packet_rx_data(usb_packet_rx_data),
        .rx_valid(usb_rx_valid_internal), .rx_ready(usb_midi_rx_ready),
        .rx_message(usb_midi_rx_message), .rx_length(usb_midi_rx_length),
        .tx_errors(usb_tx_errors), .rx_errors(usb_rx_errors)
    );

    wire ble_tx_valid_internal, ble_rx_ready_internal, ble_rx_valid_internal;
    assign ble_value_tx_valid = ble_tx_valid_internal && !ble_codec_reset;
    assign ble_value_rx_ready = ble_rx_ready_internal && !ble_codec_reset;
    assign ble_midi_rx_valid = ble_rx_valid_internal && !ble_codec_reset;
    ble_midi_codec ble_codec (
        .clk(clk), .reset(ble_codec_reset),
        .tx_valid(ble_event_valid), .tx_ready(ble_event_ready),
        .tx_message(ble_event_message), .tx_length(ble_event_length),
        .timestamp_ms(ble_event_timestamp),
        .value_tx_valid(ble_tx_valid_internal), .value_tx_ready(ble_value_tx_ready),
        .value_tx_data(ble_value_tx_data), .value_tx_length(ble_value_tx_length),
        .value_rx_valid(ble_value_rx_valid && !ble_codec_reset),
        .value_rx_ready(ble_rx_ready_internal), .value_rx_data(ble_value_rx_data),
        .value_rx_length(ble_value_rx_length),
        .rx_valid(ble_rx_valid_internal), .rx_ready(ble_midi_rx_ready),
        .rx_message(ble_midi_rx_message), .rx_length(ble_midi_rx_length),
        .rx_timestamp(ble_midi_rx_timestamp),
        .tx_errors(ble_tx_errors), .rx_errors(ble_rx_errors)
    );

    assign status_flags = {20'd0,
        (ble_tx_errors != 0), (usb_tx_errors != 0),
        (ble_rx_errors != 0), (usb_rx_errors != 0),
        (control_errors != 0), (unrouted_events != 0),
        (ignored_key_events != 0), (active_notes != 0),
        ble_queue_full, usb_queue_full, ble_online, usb_online};
    screen_control_endpoint control_endpoint (
        .touch_diagnostics(800'd0),
        .clk(clk), .reset(reset || control_reset),
        .rx_valid(control_rx_valid), .rx_ready(control_rx_ready), .rx_data(control_rx_data),
        .tx_valid(control_tx_valid), .tx_ready(control_tx_ready), .tx_data(control_tx_data),
        .status_flags(status_flags), .midi_channel(midi_channel), .transpose(transpose),
        .screen_page(screen_page), .theme_rgb565(theme_rgb565), .clear_rgb565(clear_rgb565),
        .screen_update(screen_update), .protocol_errors(control_errors)
    );
endmodule

`default_nettype wire
