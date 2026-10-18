`timescale 1ns/1ps
`default_nettype none

// MIDI 1.0 messages <-> one USB-MIDI 1.0 event packet, cable number 0.
// tx_message/rx_message = {status, data1, data2}; length counts MIDI bytes.
// packet_data[7:0] is the FIRST byte on USB: {cable, CIN}.
// A beat transfers only at valid && ready. Each direction has an independent
// one-entry output register; its valid/data remain stable under backpressure.
// reset is synchronous, active high. It discards pending packets and counters.
module usb_midi_codec (
    input wire clk,
    input wire reset,

    input wire tx_valid,
    output wire tx_ready,
    input wire [23:0] tx_message,
    input wire [1:0] tx_length,
    output reg packet_tx_valid,
    input wire packet_tx_ready,
    output reg [31:0] packet_tx_data,

    input wire packet_rx_valid,
    output wire packet_rx_ready,
    input wire [31:0] packet_rx_data,
    output reg rx_valid,
    input wire rx_ready,
    output reg [23:0] rx_message,
    output reg [1:0] rx_length,

    output reg [15:0] tx_errors,
    output reg [15:0] rx_errors
);
    // Returns {MIDI byte count, USB-MIDI Code Index Number}; 0 = unsupported.
    // SysEx, running status, undefined F4/F5/F9/FD, and standalone F7 are not
    // supported by this fixed-message transport interface.
    function [5:0] message_kind;
        input [7:0] status;
        begin
            case (status[7:4])
                4'h8: message_kind = {2'd3, 4'h8};
                4'h9: message_kind = {2'd3, 4'h9};
                4'ha: message_kind = {2'd3, 4'ha};
                4'hb: message_kind = {2'd3, 4'hb};
                4'hc: message_kind = {2'd2, 4'hc};
                4'hd: message_kind = {2'd2, 4'hd};
                4'he: message_kind = {2'd3, 4'he};
                default: begin
                    case (status)
                        8'hf1, 8'hf3: message_kind = {2'd2, 4'h2};
                        8'hf2: message_kind = {2'd3, 4'h3};
                        8'hf6: message_kind = {2'd1, 4'h5};
                        8'hf8, 8'hfa, 8'hfb, 8'hfc, 8'hfe, 8'hff:
                            message_kind = {2'd1, 4'hf};
                        default: message_kind = 6'd0;
                    endcase
                end
            endcase
        end
    endfunction

    wire [5:0] tx_kind = message_kind(tx_message[23:16]);
    wire [1:0] tx_expected_length = tx_kind[5:4];
    wire tx_message_ok = (tx_kind != 0) &&
        (tx_length == tx_expected_length) &&
        ((tx_expected_length < 2) || !tx_message[15]) &&
        ((tx_expected_length < 3) || !tx_message[7]);

    wire [5:0] rx_kind = message_kind(packet_rx_data[15:8]);
    wire [1:0] rx_expected_length = rx_kind[5:4];
    wire rx_packet_ok = (rx_kind != 0) &&
        (packet_rx_data[7:4] == 0) &&
        (packet_rx_data[3:0] == rx_kind[3:0]) &&
        ((rx_expected_length < 2) || !packet_rx_data[23]) &&
        ((rx_expected_length < 3) || !packet_rx_data[31]) &&
        ((rx_expected_length >= 2) || (packet_rx_data[23:16] == 0)) &&
        ((rx_expected_length >= 3) || (packet_rx_data[31:24] == 0));

    // Malformed input is consumed once on handshake and counted, producing no
    // output. The same output-slot backpressure applies to valid/invalid input.
    assign tx_ready = !reset && (!packet_tx_valid || packet_tx_ready);
    assign packet_rx_ready = !reset && (!rx_valid || rx_ready);

    always @(posedge clk) begin
        if (reset) begin
            packet_tx_valid <= 1'b0;
            packet_tx_data <= 32'd0;
            tx_errors <= 16'd0;
        end else if (tx_ready) begin
            packet_tx_valid <= tx_valid && tx_message_ok;
            if (tx_valid) begin
                if (tx_message_ok) begin
                    packet_tx_data <= {
                        (tx_expected_length == 3) ? tx_message[7:0] : 8'd0,
                        (tx_expected_length >= 2) ? tx_message[15:8] : 8'd0,
                        tx_message[23:16], 4'd0, tx_kind[3:0]
                    };
                end else if (tx_errors != 16'hffff) begin
                    tx_errors <= tx_errors + 1'b1;
                end
            end
        end
    end

    always @(posedge clk) begin
        if (reset) begin
            rx_valid <= 1'b0;
            rx_message <= 24'd0;
            rx_length <= 2'd0;
            rx_errors <= 16'd0;
        end else if (packet_rx_ready) begin
            rx_valid <= packet_rx_valid && rx_packet_ok;
            if (packet_rx_valid) begin
                if (rx_packet_ok) begin
                    rx_message <= {
                        packet_rx_data[15:8], packet_rx_data[23:16],
                        packet_rx_data[31:24]
                    };
                    rx_length <= rx_expected_length;
                end else if (rx_errors != 16'hffff) begin
                    rx_errors <= rx_errors + 1'b1;
                end
            end
        end
    end
endmodule

`default_nettype wire
