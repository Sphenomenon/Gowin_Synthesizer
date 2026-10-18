`timescale 1ns/1ps
`default_nettype none

// Atomically broadcasts one event to every selected, currently online link.
// in_targets[0] selects USB, bit 1 selects BLE; online is independently used
// for link availability and queue clearing. A source holds its complete beat,
// including targets, until in_valid && in_ready. Only selected online queues
// participate in backpressure. No such queue receives a beat unless all such
// queues can accept it on that edge. An empty target/online intersection is
// consumed and counted as unrouted.
// All controls are synchronous to clk. An offline link flushes its queue and
// gates valid immediately; reconnecting never replays old queued events.
// This block does not generate MIDI panic. After a disconnect, the host must
// first issue panic/all-notes-off and/or re-press keys to restore note state.
module midi_event_router #(
    parameter integer FIFO_DEPTH = 16
) (
    input wire clk,
    input wire reset,
    input wire in_valid,
    output wire in_ready,
    input wire [23:0] in_message,
    input wire [1:0] in_length,
    input wire [12:0] in_timestamp,
    input wire [1:0] in_targets,
    input wire usb_online,
    input wire ble_online,
    output wire usb_valid,
    input wire usb_ready,
    output wire [23:0] usb_message,
    output wire [1:0] usb_length,
    output wire [12:0] usb_timestamp,
    output wire ble_valid,
    input wire ble_ready,
    output wire [23:0] ble_message,
    output wire [1:0] ble_length,
    output wire [12:0] ble_timestamp,
    output wire usb_full,
    output wire ble_full,
    output reg [15:0] unrouted_events
);
    wire usb_enqueue_ready, ble_enqueue_ready;
    wire usb_queue_valid, ble_queue_valid;
    wire usb_target = in_targets[0] && usb_online;
    wire ble_target = in_targets[1] && ble_online;
    wire accept_event = in_valid && in_ready;
    assign in_ready = !reset &&
        (!usb_target || usb_enqueue_ready) &&
        (!ble_target || ble_enqueue_ready);
    assign usb_valid = usb_online && usb_queue_valid;
    assign ble_valid = ble_online && ble_queue_valid;

    midi_event_fifo #(.DEPTH(FIFO_DEPTH)) usb_queue (
        .clk(clk), .reset(reset), .clear(!usb_online),
        .in_valid(accept_event && usb_target), .in_ready(usb_enqueue_ready),
        .in_message(in_message), .in_length(in_length), .in_timestamp(in_timestamp),
        .out_valid(usb_queue_valid), .out_ready(usb_ready && usb_online),
        .out_message(usb_message), .out_length(usb_length), .out_timestamp(usb_timestamp),
        .full(usb_full)
    );
    midi_event_fifo #(.DEPTH(FIFO_DEPTH)) ble_queue (
        .clk(clk), .reset(reset), .clear(!ble_online),
        .in_valid(accept_event && ble_target), .in_ready(ble_enqueue_ready),
        .in_message(in_message), .in_length(in_length), .in_timestamp(in_timestamp),
        .out_valid(ble_queue_valid), .out_ready(ble_ready && ble_online),
        .out_message(ble_message), .out_length(ble_length), .out_timestamp(ble_timestamp),
        .full(ble_full)
    );

    always @(posedge clk) begin
        if (reset) unrouted_events <= 16'd0;
        else if (accept_event && !usb_target && !ble_target &&
                 unrouted_events != 16'hffff)
            unrouted_events <= unrouted_events + 1'b1;
    end
endmodule

`default_nettype wire
