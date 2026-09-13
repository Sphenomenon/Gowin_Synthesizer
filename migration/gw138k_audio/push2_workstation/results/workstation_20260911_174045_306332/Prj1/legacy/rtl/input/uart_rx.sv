`timescale 1ns/1ps
module uart_rx #(
    parameter integer CLOCK_HZ = 100000000,
    parameter integer BAUD = 31250
) (
    input logic clk_i, rst_ni, rx_i,
    output logic valid_o,
    output logic [7:0] data_o,
    output logic framing_error_o
);
  localparam integer BIT_CYCLES = CLOCK_HZ / BAUD;
  (* ASYNC_REG = "TRUE" *) logic [1:0] rx_sync;
  logic [15:0] timer;
  logic [3:0] bit_index;
  logic [7:0] shift;
  logic [1:0] state;
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      rx_sync <= 2'b11; timer <= 0; bit_index <= 0; shift <= 0;
      state <= 0; valid_o <= 0; data_o <= 0; framing_error_o <= 0;
    end else begin
      rx_sync <= {rx_sync[0], rx_i};
      valid_o <= 0; framing_error_o <= 0;
      case (state)
        0: if (!rx_sync[1]) begin timer <= (BIT_CYCLES/2)-1; state <= 1; end
        1: if (timer != 0) timer <= timer-1;
           else if (rx_sync[1]) state <= 0;
           else begin timer <= BIT_CYCLES-1; bit_index <= 0; state <= 2; end
        2: if (timer != 0) timer <= timer-1;
           else begin
             shift[bit_index] <= rx_sync[1]; timer <= BIT_CYCLES-1;
             if (bit_index == 7) state <= 3; else bit_index <= bit_index+1;
           end
        3: if (timer != 0) timer <= timer-1;
           else begin
             valid_o <= rx_sync[1]; framing_error_o <= !rx_sync[1];
             data_o <= shift; state <= 0;
           end
      endcase
    end
  end
endmodule
