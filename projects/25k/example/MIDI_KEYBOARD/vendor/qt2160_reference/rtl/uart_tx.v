`timescale 1ns / 1ps

module uart_tx #(
    parameter integer CLK_HZ = 50_000_000,
    parameter integer BAUD = 115200
) (
    input wire clk,
    input wire send,
    input wire [7:0] data,
    output reg tx = 1,
    output reg busy = 0
);
    localparam integer BIT_CYCLES = (CLK_HZ + BAUD / 2) / BAUD;
    localparam integer TIMER_WIDTH = (BIT_CYCLES > 1) ? $clog2(BIT_CYCLES) : 1;
    reg [TIMER_WIDTH-1:0] timer = 0;
    reg [9:0] frame = 10'h3ff;
    reg [3:0] bit_index = 0;

    always @(posedge clk) begin
        if (!busy) begin
            tx <= 1'b1;
            if (send) begin
                frame <= {1'b1, data, 1'b0};
                tx <= 1'b0;
                busy <= 1'b1;
                bit_index <= 0;
                timer <= BIT_CYCLES - 1;
            end
        end else if (timer != 0) timer <= timer - 1'b1;
        else if (bit_index == 9) begin
            tx <= 1'b1;
            busy <= 1'b0;
        end else begin
            frame <= {1'b1, frame[9:1]};
            tx <= frame[1];
            bit_index <= bit_index + 1'b1;
            timer <= BIT_CYCLES - 1;
        end
    end
endmodule
