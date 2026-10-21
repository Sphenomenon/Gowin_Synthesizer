`timescale 1ns/1ps
// Reserve one return-FIFO slot before accepting a DDR read. Only this client
// writes that FIFO, and the original DDR16 port permits one outstanding read.
// The registered credit removes the FIFO-full comparator from DDR arbitration.
module basic_pitch_ddr_read_credit (
    input wire clk_i, rst_ni,
    input wire fifo_ready_i,
    input wire read_accept_i,
    input wire response_valid_i,
    output reg credit_o
);
    reg reserved;
    always @(posedge clk_i or negedge rst_ni) begin
        if (!rst_ni) begin
            credit_o <= 1'b0;
            reserved <= 1'b0;
        end else if (read_accept_i) begin
            credit_o <= 1'b0;
            reserved <= 1'b1;
        end else if (reserved) begin
            credit_o <= 1'b0;
            if (response_valid_i && fifo_ready_i) reserved <= 1'b0;
        end else begin
            // One empty cycle after the response commit observes the updated
            // FIFO write pointer before granting another reservation.
            credit_o <= fifo_ready_i && !response_valid_i;
        end
    end
endmodule
