`timescale 1ns / 1ps

// A complete line is frozen until every byte has been accepted by the UART arbiter.
module qt2160_keypad_uart (
    input wire clk, input wire event_valid, output wire event_ready,
    input wire [3:0] key_index,
    input wire [15:0] key_signal, key_reference,
    output wire tx_valid, input wire tx_ready,
    output reg [7:0] tx_data, output wire tx_last
);
    reg active = 0, converting = 0;
    reg [5:0] index = 0;
    reg [4:0] number = 0;
    reg row = 0;
    reg [2:0] column = 0;
    reg [15:0] signal_value = 0, reference_value = 0, magnitude = 0;
    reg negative = 0;
    reg [4:0] convert_count = 0;
    reg [19:0] signal_bcd = 0, reference_bcd = 0, magnitude_bcd = 0;
    function [19:0] bcd_step;
        input [19:0] value;
        input next_bit;
        reg [19:0] adjusted;
        integer digit;
        begin
            adjusted = value;
            for (digit = 0; digit < 5; digit = digit + 1)
                if (value[digit*4 +: 4] >= 5) adjusted[digit*4 +: 4] = value[digit*4 +: 4] + 4'd3;
            bcd_step = {adjusted[18:0], next_bit};
        end
    endfunction
    assign event_ready = !active && !converting;
    assign tx_valid = active;
    assign tx_last = index == 51;
    always @(posedge clk) begin
        if (event_valid && event_ready) begin
            converting <= 1; convert_count <= 0;
            signal_bcd <= 0; reference_bcd <= 0; magnitude_bcd <= 0;
            index <= 0; number <= {1'b0,key_index} + 1;
            row <= key_index[3]; column <= key_index[2:0];
            signal_value <= key_signal; reference_value <= key_reference;
            negative <= key_reference < key_signal;
            magnitude <= key_reference < key_signal ? key_signal - key_reference : key_reference - key_signal;
        end else if (converting) begin
            signal_bcd <= bcd_step(signal_bcd, signal_value[15]);
            reference_bcd <= bcd_step(reference_bcd, reference_value[15]);
            magnitude_bcd <= bcd_step(magnitude_bcd, magnitude[15]);
            signal_value <= {signal_value[14:0],1'b0};
            reference_value <= {reference_value[14:0],1'b0};
            magnitude <= {magnitude[14:0],1'b0};
            if (convert_count == 15) begin converting <= 0; active <= 1; end
            else convert_count <= convert_count + 1;
        end else if (tx_valid && tx_ready) begin
            if (tx_last) active <= 0;
            else index <= index + 1;
        end
    end
    // KEY=01,Y=0,X=0,SIGNAL=01234,REF=01300,DELTA=+00066\r\n
    always @* begin
        case (index)
            0: tx_data = "K"; 1: tx_data = "E"; 2: tx_data = "Y"; 3: tx_data = "=";
            4: tx_data = 48 + number / 10; 5: tx_data = 48 + number % 10;
            6: tx_data = ","; 7: tx_data = "Y"; 8: tx_data = "="; 9: tx_data = 48 + row;
            10: tx_data = ","; 11: tx_data = "X"; 12: tx_data = "="; 13: tx_data = 48 + column;
            14: tx_data = ","; 15: tx_data = "S"; 16: tx_data = "I"; 17: tx_data = "G";
            18: tx_data = "N"; 19: tx_data = "A"; 20: tx_data = "L"; 21: tx_data = "=";
            22: tx_data = 48 + signal_bcd[19:16];
            23: tx_data = 48 + signal_bcd[15:12];
            24: tx_data = 48 + signal_bcd[11:8];
            25: tx_data = 48 + signal_bcd[7:4];
            26: tx_data = 48 + signal_bcd[3:0];
            27: tx_data = ","; 28: tx_data = "R"; 29: tx_data = "E"; 30: tx_data = "F"; 31: tx_data = "=";
            32: tx_data = 48 + reference_bcd[19:16];
            33: tx_data = 48 + reference_bcd[15:12];
            34: tx_data = 48 + reference_bcd[11:8];
            35: tx_data = 48 + reference_bcd[7:4];
            36: tx_data = 48 + reference_bcd[3:0];
            37: tx_data = ","; 38: tx_data = "D"; 39: tx_data = "E"; 40: tx_data = "L";
            41: tx_data = "T"; 42: tx_data = "A"; 43: tx_data = "=";
            44: tx_data = negative ? "-" : "+";
            45: tx_data = 48 + magnitude_bcd[19:16];
            46: tx_data = 48 + magnitude_bcd[15:12];
            47: tx_data = 48 + magnitude_bcd[11:8];
            48: tx_data = 48 + magnitude_bcd[7:4];
            49: tx_data = 48 + magnitude_bcd[3:0];
            50: tx_data = 8'h0d;
            default: tx_data = 8'h0a;
        endcase
    end
endmodule
