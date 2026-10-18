// Application-facing driver. This is NOT a USB PHY or enumerator.
// All ports are synchronous to clk (nominally 60 MHz). See docs/INTERFACE.md.
// Configuration metadata must come from checked, parsed USB descriptors.
module push2_driver_core #(
    parameter integer RETRY_DELAY_CYCLES=7500,
    parameter integer WATCHDOG_CYCLES=6000000,
    parameter integer MAX_ERRORS=3
) (
    input wire clk, input wire rst,
    input wire usb_configured, input wire usb_high_speed,
    input wire [15:0] usb_vid, input wire [15:0] usb_pid,
    input wire [6:0] usb_address,
    input wire [7:0] usb_display_out, input wire [10:0] usb_display_mps,
    input wire [7:0] usb_midi_out, input wire [10:0] usb_midi_mps,
    output wire session_ready,
    input wire cmd_valid, output wire cmd_ready,
    input wire [1:0] cmd_kind, input wire [6:0] cmd_index,
    input wire [7:0] cmd_value, input wire [3:0] cmd_cable,
    input wire frame_start, output wire frame_ready, output wire frame_done,
    input wire pixel_valid, output wire pixel_ready,
    input wire [15:0] pixel_bgr565,
    output wire [9:0] pixel_x, output wire [7:0] pixel_y,
    input wire usb_rx_valid, output wire usb_rx_ready, input wire [31:0] usb_rx_event,
    output wire event_valid, input wire event_ready,
    output wire [3:0] event_kind, output wire [3:0] event_channel,
    output wire [3:0] event_cable,
    output wire [6:0] event_data1, output wire [6:0] event_data2,
    output wire [13:0] event_pitch,
    output wire out_req_valid, input wire out_req_ready,
    output wire [6:0] out_device_address, output wire [3:0] out_endpoint,
    output wire out_data1, output wire [9:0] out_length,
    output wire out_valid, input wire out_ready, output wire [7:0] out_data,
    output wire out_last, input wire out_done, input wire [2:0] out_response,
    output wire busy, output wire fault, output wire [3:0] fault_code,
    output wire [31:0] packets_acked, output wire [31:0] nak_count,
    output wire [31:0] retry_count, output wire [31:0] frames_acked,
    output wire [31:0] pixels_accepted, output wire [31:0] commands_acked,
    output wire [31:0] commands_rejected,
    output wire [31:0] events_received, output wire [31:0] packets_ignored
);
    wire profile_ok=usb_configured && usb_high_speed && usb_address!=0 &&
                    usb_vid==16'h2982 && usb_pid==16'h1967 &&
                    usb_display_out==8'h01 && usb_display_mps==11'd512 &&
                    usb_midi_out==8'h02 && usb_midi_mps==11'd512;
    reg [6:0] address_q;
    always @(posedge clk) begin
        if (rst) address_q<=0;
        else address_q<=usb_address;
    end
    wire session_reset=rst || !profile_ok || address_q!=usb_address;
    assign session_ready=!session_reset && !fault;
    wire midi_valid, midi_ack, display_valid, display_ack;
    wire [9:0] midi_length, display_length;
    wire [7:0] midi_data, display_data;
    wire [8:0] packet_index;
    wire cmd_ready_i, frame_ready_i, frame_done_i, pixel_ready_i, display_busy;
    wire rx_ready_i, event_valid_i, req_valid_i, tx_valid_i, scheduler_busy;
    assign cmd_ready=cmd_ready_i && session_ready;
    assign frame_ready=frame_ready_i && session_ready;
    assign frame_done=frame_done_i && session_ready;
    assign pixel_ready=pixel_ready_i && session_ready;
    assign usb_rx_ready=rx_ready_i && session_ready;
    assign event_valid=event_valid_i && session_ready;
    assign out_req_valid=req_valid_i && session_ready;
    assign out_valid=tx_valid_i && session_ready;
    assign busy=(scheduler_busy || display_busy || midi_valid) && !session_reset;
    push2_led_tx led (
        .clk(clk),.rst(session_reset),.cmd_valid(cmd_valid && session_ready),
        .cmd_ready(cmd_ready_i),.cmd_kind(cmd_kind),.cmd_index(cmd_index),
        .cmd_value(cmd_value),.cmd_cable(cmd_cable),
        .packet_valid(midi_valid),.packet_length(midi_length),
        .packet_index(packet_index),.packet_data(midi_data),.packet_acked(midi_ack),
        .commands_acked(commands_acked),.commands_rejected(commands_rejected)
    );
    push2_display_tx display (
        .clk(clk),.rst(session_reset),.frame_start(frame_start && session_ready),
        .frame_ready(frame_ready_i),.busy(display_busy),.frame_done(frame_done_i),
        .pixel_valid(pixel_valid && session_ready),.pixel_ready(pixel_ready_i),
        .pixel_bgr565(pixel_bgr565),.pixel_x(pixel_x),.pixel_y(pixel_y),
        .packet_valid(display_valid),.packet_length(display_length),
        .packet_index(packet_index),.packet_data(display_data),.packet_acked(display_ack),
        .frames_acked(frames_acked),.pixels_accepted(pixels_accepted)
    );
    push2_midi_rx midi_rx (
        .clk(clk),.rst(session_reset),.usb_valid(usb_rx_valid && session_ready),
        .usb_ready(rx_ready_i),.usb_event(usb_rx_event),
        .event_valid(event_valid_i),.event_ready(event_ready && session_ready),
        .event_kind(event_kind),.event_channel(event_channel),.event_cable(event_cable),
        .event_data1(event_data1),.event_data2(event_data2),.event_pitch(event_pitch),
        .events_received(events_received),.packets_ignored(packets_ignored)
    );
    push2_out_scheduler #(
        .RETRY_DELAY_CYCLES(RETRY_DELAY_CYCLES),.WATCHDOG_CYCLES(WATCHDOG_CYCLES),
        .MAX_ERRORS(MAX_ERRORS)
    ) scheduler (
        .clk(clk),.rst(session_reset),.device_address(usb_address),
        .midi_valid(midi_valid),.midi_length(midi_length),.midi_data(midi_data),.midi_acked(midi_ack),
        .display_valid(display_valid),.display_length(display_length),
        .display_data(display_data),.display_acked(display_ack),.packet_index(packet_index),
        .out_req_valid(req_valid_i),.out_req_ready(out_req_ready && session_ready),
        .out_device_address(out_device_address),.out_endpoint(out_endpoint),
        .out_data1(out_data1),.out_length(out_length),
        .out_valid(tx_valid_i),.out_ready(out_ready && session_ready),
        .out_data(out_data),.out_last(out_last),
        .out_done(out_done && session_ready),.out_response(out_response),
        .busy(scheduler_busy),.fault(fault),.fault_code(fault_code),
        .packets_acked(packets_acked),.nak_count(nak_count),.retry_count(retry_count)
    );
endmodule
