`timescale 1ns / 1ps

module uart_led_controller #(
    parameter integer CLK_HZ = 50_000_000,
    parameter integer BAUD = 115200,
    parameter integer STARTUP_CYCLES = CLK_HZ / 5,
    parameter integer IDLE_CYCLES = CLK_HZ / 50,
    parameter integer ENABLE_SLIDER_REPORT = 0,
    parameter integer ENABLE_KEY_REPORT = 0
) (
    input wire clk,
    input wire uart_rx_pin,
    output wire uart_tx_pin,
    output wire led1,
    output wire led2,
    input wire slider_report,
    input wire [7:0] slider_value,
    input wire slider_touch,
    input wire slider_valid,
    input wire key_tx_valid,
    input wire [7:0] key_tx_data,
    input wire key_tx_last,
    output wire key_tx_ready,
    output wire uart_byte_sent,
    output wire [63:0] uart_byte_result
);
    localparam integer STARTUP_WIDTH = (STARTUP_CYCLES > 1) ? $clog2(STARTUP_CYCLES) : 1;
    localparam integer IDLE_WIDTH = (IDLE_CYCLES > 1) ? $clog2(IDLE_CYCLES) : 1;
    reg [STARTUP_WIDTH-1:0] startup_count = 0;
    reg startup_done = 0;
    reg led1_enable = 0;
    reg led2_enable = 0;
    wire breath1, breath2;

    always @(posedge clk) begin
        if (!startup_done) begin
            if (startup_count == STARTUP_CYCLES - 1)
                startup_done <= 1'b1;
            else startup_count <= startup_count + 1'b1;
        end
    end
    led_breath_channel #(.CLK_HZ(CLK_HZ)) channel1 (
        .clk(clk), .enable(startup_done && led1_enable), .led(breath1));
    led_breath_channel #(.CLK_HZ(CLK_HZ)) channel2 (
        .clk(clk), .enable(startup_done && led2_enable), .led(breath2));
    assign led1 = !startup_done || breath1;
    assign led2 = !startup_done || breath2;

    wire [7:0] rx_data;
    wire rx_valid, rx_busy;
    uart_rx #(.CLK_HZ(CLK_HZ), .BAUD(BAUD)) receiver (
        .clk(clk), .rx(uart_rx_pin), .data(rx_data), .valid(rx_valid), .busy(rx_busy));

    // Maximum valid length is 11 bytes. Overlength input is rejected as one
    // complete command, rather than accepting a valid suffix after overflow.
    reg [87:0] command_buffer = 0;
    reg [3:0] command_length = 0;
    reg command_overflow = 0;
    reg [IDLE_WIDTH-1:0] idle_count = 0;
    reg unknown_event = 0;
    wire line_end = rx_valid && ((rx_data == 8'h0d) || (rx_data == 8'h0a));
    wire has_command = (command_length != 0) || command_overflow;
    wire idle_end = !rx_valid && !rx_busy && has_command && (idle_count == IDLE_CYCLES - 1);

    always @(posedge clk) begin
        unknown_event <= 1'b0;
        if (line_end || idle_end) begin
            // Ignore empty lines, including the LF half of a CRLF pair.
            if (has_command) begin
                if (!command_overflow && command_length == 11 && command_buffer == "LED1+BREATH")
                    led1_enable <= 1'b1;
                else if (!command_overflow && command_length == 9 && command_buffer == "LED1+STOP")
                    led1_enable <= 1'b0;
                else if (!command_overflow && command_length == 11 && command_buffer == "LED2+BREATH")
                    led2_enable <= 1'b1;
                else if (!command_overflow && command_length == 9 && command_buffer == "LED2+STOP")
                    led2_enable <= 1'b0;
                else unknown_event <= 1'b1;
            end
            command_buffer <= 0;
            command_length <= 0;
            command_overflow <= 1'b0;
            idle_count <= 0;
        end else if (rx_valid) begin
            idle_count <= 0;
            if (command_length < 11) begin
                command_buffer <= {command_buffer[79:0], rx_data};
                command_length <= command_length + 1'b1;
            end else command_overflow <= 1'b1;
        end else if (rx_busy || !has_command) idle_count <= 0;
        else idle_count <= idle_count + 1'b1;
    end

    // RX parsing remains active while an error reply is transmitted.
    // All replies are identical, so only their pending count needs queuing.
    reg [31:0] pending_replies = 0;
    reg reply_active = 0;
    reg [4:0] reply_index = 0;
    reg slider_pending = 0, slider_active = 0;
    reg [7:0] pending_value = 0, active_value = 0;
    reg pending_touch = 0, pending_valid = 0, active_touch = 0, active_valid = 0;
    reg [4:0] slider_index = 0;
    reg key_active = 0;
    wire key_waiting = ENABLE_KEY_REPORT && key_tx_valid;
    wire key_selected = key_active || (!reply_active && !slider_active && key_waiting);
    wire slider_begin = !key_active && !key_waiting && !reply_active && !slider_active && slider_pending;
    wire reply_begin = !key_active && !key_waiting && !reply_active && !slider_active && !slider_pending && (pending_replies != 0);
    wire tx_busy;
    assign key_tx_ready = ENABLE_KEY_REPORT && key_selected && !tx_busy;
    wire tx_send = (key_selected ? key_tx_valid : (reply_active || slider_active)) && !tx_busy;
    function [7:0] reply_byte;
        input [4:0] index;
        begin
            case (index)
                0: reply_byte = "u";
                1: reply_byte = "n";
                2: reply_byte = "k";
                3: reply_byte = "n";
                4: reply_byte = "o";
                5: reply_byte = "w";
                6: reply_byte = "n";
                7: reply_byte = " ";
                8: reply_byte = "c";
                9: reply_byte = "o";
                10: reply_byte = "m";
                11: reply_byte = "m";
                12: reply_byte = "a";
                13: reply_byte = "n";
                14: reply_byte = "d";
                15: reply_byte = 8'h0d;
                default: reply_byte = 8'h0a;
            endcase
        end
    endfunction
    function [7:0] slider_byte;
        input [4:0] index;
        begin
            case (index)
                0: slider_byte = "S";
                1: slider_byte = "L";
                2: slider_byte = "I";
                3: slider_byte = "D";
                4: slider_byte = "E";
                5: slider_byte = "R";
                6: slider_byte = "=";
                7: slider_byte = active_valid ? 8'd48 + active_value / 100 : "E";
                8: slider_byte = active_valid ? 8'd48 + (active_value / 10) % 10 : "R";
                9: slider_byte = active_valid ? 8'd48 + active_value % 10 : "R";
                10: slider_byte = ",";
                11: slider_byte = "T";
                12: slider_byte = "O";
                13: slider_byte = "U";
                14: slider_byte = "C";
                15: slider_byte = "H";
                16: slider_byte = "=";
                17: slider_byte = active_valid && active_touch ? "1" : "0";
                18: slider_byte = 8'h0d;
                default: slider_byte = 8'h0a;
            endcase
        end
    endfunction
    wire [7:0] tx_data = key_selected ? key_tx_data : (slider_active ? slider_byte(slider_index) : reply_byte(reply_index));
    reg [31:0] uart_clock_count = 0;
    assign uart_byte_sent = tx_send;
    assign uart_byte_result = {uart_clock_count, 16'b0, 5'b0, key_selected, slider_active, reply_active, tx_data};
    always @(posedge clk) begin
        uart_clock_count <= uart_clock_count + 1;
        if (key_tx_valid && key_tx_ready) key_active <= !key_tx_last;
        case ({unknown_event, reply_begin})
            2'b10: pending_replies <= pending_replies + 1'b1;
            2'b01: pending_replies <= pending_replies - 1'b1;
            default: ;
        endcase
        if (reply_begin) begin
            reply_active <= 1'b1;
            reply_index <= 0;
        end else if (tx_send && reply_active) begin
            if (reply_index == 16) reply_active <= 1'b0;
            else reply_index <= reply_index + 1'b1;
        end
        if (slider_begin) begin
            slider_pending <= 0; slider_active <= 1; slider_index <= 0;
            active_value <= pending_value; active_touch <= pending_touch; active_valid <= pending_valid;
        end else if (tx_send && slider_active) begin
            if (slider_index == 19) slider_active <= 0;
            else slider_index <= slider_index + 1;
        end
        // Freeze a complete line; never interleave it with an existing reply.
        if (ENABLE_SLIDER_REPORT && slider_report) begin
            slider_pending <= 1; pending_value <= slider_value;
            pending_touch <= slider_touch; pending_valid <= slider_valid;
        end
    end
    uart_tx #(.CLK_HZ(CLK_HZ), .BAUD(BAUD)) transmitter (
        .clk(clk), .send(tx_send), .data(tx_data), .tx(uart_tx_pin), .busy(tx_busy));
endmodule
