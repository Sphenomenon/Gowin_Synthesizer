`timescale 1ns/1ps
`default_nettype none

// Single-clock complete-event FIFO. DEPTH may be any positive integer.
// reset/clear are synchronous active-high; neither permits a transfer.
// A full queue accepts a push when the oldest event is popped on that edge.
module midi_event_fifo #(
    parameter integer DEPTH = 16
) (
    input wire clk,
    input wire reset,
    input wire clear,
    input wire in_valid,
    output wire in_ready,
    input wire [23:0] in_message,
    input wire [1:0] in_length,
    input wire [12:0] in_timestamp,
    output wire out_valid,
    input wire out_ready,
    output wire [23:0] out_message,
    output wire [1:0] out_length,
    output wire [12:0] out_timestamp,
    output wire full
);
    function integer bit_width;
        input integer value;
        integer remaining;
        begin
            remaining = value - 1;
            bit_width = 0;
            while (remaining > 0) begin
                bit_width = bit_width + 1;
                remaining = remaining >> 1;
            end
            if (bit_width == 0) bit_width = 1;
        end
    endfunction

    localparam integer ADDR_WIDTH = bit_width(DEPTH);
    localparam integer COUNT_WIDTH = bit_width(DEPTH + 1);
    reg [38:0] memory [0:DEPTH-1];
    reg [ADDR_WIDTH-1:0] read_index;
    reg [ADDR_WIDTH-1:0] write_index;
    reg [COUNT_WIDTH-1:0] count;
    wire pop = out_valid && out_ready;
    wire push = in_valid && in_ready;
    wire [38:0] head = out_valid ? memory[read_index] : 39'd0;

    assign full = !reset && !clear && (count == DEPTH);
    assign out_valid = !reset && !clear && (count != 0);
    assign in_ready = !reset && !clear && ((count < DEPTH) || pop);
    assign out_message = head[23:0];
    assign out_length = head[25:24];
    assign out_timestamp = head[38:26];

    always @(posedge clk) begin
        if (reset || clear) begin
            read_index <= 0;
            write_index <= 0;
            count <= 0;
        end else begin
            if (push) begin
                memory[write_index] <= {in_timestamp, in_length, in_message};
                if (write_index == DEPTH - 1) write_index <= 0;
                else write_index <= write_index + 1'b1;
            end
            if (pop) begin
                if (read_index == DEPTH - 1) read_index <= 0;
                else read_index <= read_index + 1'b1;
            end
            case ({push, pop})
                2'b10: count <= count + 1'b1;
                2'b01: count <= count - 1'b1;
                default: count <= count;
            endcase
        end
    end
endmodule

`default_nettype wire
