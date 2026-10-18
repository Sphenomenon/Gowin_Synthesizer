`timescale 1ns/1ps
// One complete MIDI message per BLE-MIDI characteristic value.
// All interfaces use ready/valid; bytes in value_*_data are low byte first.
// This codec does not implement a BLE controller, GATT server, or SysEx stream.
module ble_midi_codec (
    input wire clk,
    input wire reset,

    input wire tx_valid,
    output wire tx_ready,
    input wire [23:0] tx_message, // {status, data1, data2}
    input wire [1:0] tx_length,
    input wire [12:0] timestamp_ms,

    output reg value_tx_valid,
    input wire value_tx_ready,
    output reg [39:0] value_tx_data,
    output reg [2:0] value_tx_length,

    input wire value_rx_valid,
    output wire value_rx_ready,
    input wire [39:0] value_rx_data,
    input wire [2:0] value_rx_length,

    output reg rx_valid,
    input wire rx_ready,
    output reg [23:0] rx_message,
    output reg [1:0] rx_length,
    output reg [12:0] rx_timestamp,

    output reg [15:0] tx_errors,
    output reg [15:0] rx_errors
);

    // Zero denotes an unsupported status. Realtime bytes must be separate
    // events; interleaving them inside a channel/system-common message is not
    // part of this intentionally small, complete-message interface.
    function [1:0] message_length;
        input [7:0] status;
        begin
            case (status[7:4])
                4'h8, 4'h9, 4'ha, 4'hb, 4'he: message_length = 2'd3;
                4'hc, 4'hd: message_length = 2'd2;
                default: begin
                    case (status)
                        8'hf1, 8'hf3: message_length = 2'd2;
                        8'hf2: message_length = 2'd3;
                        8'hf6, 8'hf8, 8'hfa, 8'hfb, 8'hfc,
                        8'hfe, 8'hff: message_length = 2'd1;
                        default: message_length = 2'd0;
                    endcase
                end
            endcase
        end
    endfunction

    wire [1:0] tx_expected_length = message_length(tx_message[23:16]);
    wire [1:0] rx_expected_length = message_length(value_rx_data[23:16]);
    wire tx_well_formed = (tx_expected_length != 2'd0) &&
                         (tx_length == tx_expected_length) &&
                         ((tx_expected_length < 2'd2) || !tx_message[15]) &&
                         ((tx_expected_length < 2'd3) || !tx_message[7]);
    wire rx_well_formed = (value_rx_data[7:6] == 2'b10) &&
                         value_rx_data[15] &&
                         (rx_expected_length != 2'd0) &&
                         (value_rx_length == ({1'b0, rx_expected_length} + 3'd2)) &&
                         ((rx_expected_length < 2'd2) || !value_rx_data[31]) &&
                         ((rx_expected_length < 2'd3) || !value_rx_data[39]);

    // One elastic output slot per direction permits same-cycle replacement.
    // Invalid inputs are consumed only on valid && ready and generate no event.
    assign tx_ready = !value_tx_valid || value_tx_ready;
    assign value_rx_ready = !rx_valid || rx_ready;

    always @(posedge clk) begin
        if (reset) begin
            value_tx_valid <= 1'b0;
            value_tx_data <= 40'd0;
            value_tx_length <= 3'd0;
            rx_valid <= 1'b0;
            rx_message <= 24'd0;
            rx_length <= 2'd0;
            rx_timestamp <= 13'd0;
            tx_errors <= 16'd0;
            rx_errors <= 16'd0;
        end else begin
            if (tx_ready) begin
                value_tx_valid <= 1'b0;
                if (tx_valid) begin
                    if (tx_well_formed) begin
                        value_tx_valid <= 1'b1;
                        value_tx_length <= {1'b0, tx_length} + 3'd2;
                        value_tx_data <= {
                            (tx_length == 2'd3 ? tx_message[7:0] : 8'd0),
                            (tx_length >= 2'd2 ? tx_message[15:8] : 8'd0),
                            tx_message[23:16],
                            {1'b1, timestamp_ms[6:0]},
                            {2'b10, timestamp_ms[12:7]}
                        };
                    end else if (tx_errors != 16'hffff) begin
                        tx_errors <= tx_errors + 1'b1;
                    end
                end
            end

            if (value_rx_ready) begin
                rx_valid <= 1'b0;
                if (value_rx_valid) begin
                    if (rx_well_formed) begin
                        rx_valid <= 1'b1;
                        rx_message <= {
                            value_rx_data[23:16],
                            (rx_expected_length >= 2'd2 ? value_rx_data[31:24] : 8'd0),
                            (rx_expected_length == 2'd3 ? value_rx_data[39:32] : 8'd0)
                        };
                        rx_length <= rx_expected_length;
                        rx_timestamp <= {value_rx_data[5:0], value_rx_data[14:8]};
                    end else if (rx_errors != 16'hffff) begin
                        rx_errors <= rx_errors + 1'b1;
                    end
                end
            end
        end
    end
endmodule
