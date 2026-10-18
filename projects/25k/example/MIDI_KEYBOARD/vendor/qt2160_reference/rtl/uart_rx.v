`timescale 1ns / 1ps

// Single-ended, idle-high UART receiver: 8 data bits, no parity, one stop bit.
module uart_rx #(
    parameter integer CLK_HZ = 50_000_000,
    parameter integer BAUD = 115200
) (
    input wire clk,
    input wire rx,
    output reg [7:0] data = 0,
    output reg valid = 0,
    output wire busy
);
    localparam integer BIT_CYCLES = (CLK_HZ + BAUD / 2) / BAUD;
    localparam integer HALF_CYCLES = BIT_CYCLES / 2;
    localparam integer TIMER_WIDTH = (BIT_CYCLES > 1) ? $clog2(BIT_CYCLES) : 1;
    localparam [1:0] IDLE = 0, START = 1, DATA = 2, STOP = 3;

    (* ASYNC_REG = "TRUE" *) reg [1:0] rx_sync = 2'b11;
    reg [1:0] state = IDLE;
    reg [TIMER_WIDTH-1:0] timer = 0;
    reg [2:0] bit_index = 0;
    reg [7:0] shift_data = 0;
    assign busy = (state != IDLE);

    always @(posedge clk) begin
        rx_sync <= {rx_sync[0], rx};
        valid <= 1'b0;
        case (state)
            IDLE: if (!rx_sync[1]) begin
                timer <= HALF_CYCLES - 1;
                state <= START;
            end
            START: if (timer != 0) timer <= timer - 1'b1;
                else if (!rx_sync[1]) begin
                    timer <= BIT_CYCLES - 1;
                    bit_index <= 0;
                    state <= DATA;
                end else state <= IDLE; // Reject short low glitches.
            DATA: if (timer != 0) timer <= timer - 1'b1;
                else begin
                    shift_data[bit_index] <= rx_sync[1];
                    timer <= BIT_CYCLES - 1;
                    if (bit_index == 7) state <= STOP;
                    else bit_index <= bit_index + 1'b1;
                end
            STOP: if (timer != 0) timer <= timer - 1'b1;
                else begin
                    if (rx_sync[1]) begin
                        data <= shift_data;
                        valid <= 1'b1;
                    end
                    state <= IDLE; // Invalid stop bit: discard the byte.
                end
            default: state <= IDLE;
        endcase
    end
endmodule
