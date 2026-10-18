`timescale 1ns / 1ps

// Sixteen GRB pixels, MSB first. A complete input snapshot is held per frame.
// Fractional bit timing gives exactly 800 kbit/s average at a 50 MHz clock.
module midi_ws2812 #(
    parameter integer CLK_HZ = 50_000_000,
    parameter integer RESET_CYCLES = (CLK_HZ / 1_000_000) * 300,
    parameter integer T0H_CYCLES = (CLK_HZ / 1_000_000) * 350 / 1000,
    parameter integer T1H_CYCLES = (CLK_HZ / 1_000_000) * 850 / 1000
) (
    input wire clk, input wire reset, input wire [15:0] key_bitmap,
    input wire [7:0] brightness, output reg data_out = 0
);
    localparam integer BASE_CYCLES = CLK_HZ / 800_000;
    localparam integer REM_CYCLES = CLK_HZ % 800_000;
    reg sending = 0;
    reg [31:0] timer = 0, fraction = 0, bit_cycles = BASE_CYCLES;
    reg [15:0] frame_keys = 0;
    reg [7:0] frame_brightness = 0;
    reg [3:0] pixel = 0;
    reg [4:0] bit_index = 23;
    // Physical DIN chain: ABCD HGFE IJKL PONM. Input bits remain A..P,
    // shared with MIDI, the LCD and the separate PCA9685 LED bank.
    function [3:0] key_at_pixel;
        input [3:0] chain_index;
        begin
            case (chain_index)
                0: key_at_pixel = 0;
                1: key_at_pixel = 1;
                2: key_at_pixel = 2;
                3: key_at_pixel = 3;
                4: key_at_pixel = 7;
                5: key_at_pixel = 6;
                6: key_at_pixel = 5;
                7: key_at_pixel = 4;
                8: key_at_pixel = 8;
                9: key_at_pixel = 9;
                10: key_at_pixel = 10;
                11: key_at_pixel = 11;
                12: key_at_pixel = 15;
                13: key_at_pixel = 14;
                14: key_at_pixel = 13;
                15: key_at_pixel = 12;
            endcase
        end
    endfunction
    wire [3:0] logical_key = key_at_pixel(pixel);
    wire [23:0] pixel_color;
    reg [7:0] red, green, blue;
    wire bit_value = pixel_color[bit_index];
    always @* begin
        red = 0; green = 0; blue = 0;
        if (frame_keys[logical_key]) begin
            case (logical_key[2:0])
                0: red = frame_brightness;
                1: begin red = frame_brightness; green = frame_brightness >> 1; end
                2: begin red = frame_brightness; green = frame_brightness; end
                3: green = frame_brightness;
                4: begin green = frame_brightness; blue = frame_brightness; end
                5: blue = frame_brightness;
                6: begin red = frame_brightness >> 1; blue = frame_brightness; end
                7: begin red = frame_brightness; blue = frame_brightness; end
            endcase
        end
    end
    assign pixel_color = {green,red,blue};
    always @(posedge clk) begin
        if (reset) begin
            data_out <= 0; sending <= 0; timer <= 0; fraction <= 0;
            bit_cycles <= BASE_CYCLES; frame_keys <= 0; frame_brightness <= 0;
            pixel <= 0; bit_index <= 23;
        end else if (!sending) begin
            data_out <= 0;
            if (timer >= RESET_CYCLES - 1) begin
                timer <= 0; fraction <= REM_CYCLES; bit_cycles <= BASE_CYCLES;
                frame_keys <= key_bitmap; frame_brightness <= brightness;
                pixel <= 0; bit_index <= 23; sending <= 1; data_out <= 1;
            end else timer <= timer + 1;
        end else begin
            if (timer == (bit_value ? T1H_CYCLES : T0H_CYCLES) - 1) data_out <= 0;
            if (timer >= bit_cycles - 1) begin
                timer <= 0;
                if (fraction + REM_CYCLES >= 800_000) begin
                    fraction <= fraction + REM_CYCLES - 800_000; bit_cycles <= BASE_CYCLES + 1;
                end else begin fraction <= fraction + REM_CYCLES; bit_cycles <= BASE_CYCLES; end
                if (bit_index == 0) begin
                    bit_index <= 23;
                    if (pixel == 15) begin sending <= 0; data_out <= 0; end
                    else begin pixel <= pixel + 1; data_out <= 1; end
                end else begin bit_index <= bit_index - 1; data_out <= 1; end
            end else timer <= timer + 1;
        end
    end
endmodule
