`timescale 1ns/1ps
`default_nettype none

// Single-clock complete-event FIFO. DEPTH may be any positive integer.
// reset/clear are synchronous active-high; neither permits a transfer.
// A full queue accepts a push when the oldest event is popped on that edge.
module midi_event_fifo #(
    parameter integer DEPTH = 16,
    parameter integer PANEL_EVENTS = 0
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
    localparam integer PAYLOAD_BITS = PANEL_EVENTS ? 32 : 39;
    reg [ADDR_WIDTH-1:0] read_index;
    reg [ADDR_WIDTH-1:0] write_index;
    reg [COUNT_WIDTH-1:0] count;
    wire pop = out_valid && out_ready;
    wire push = in_valid && in_ready;
    wire [38:0] head;
    wire [PAYLOAD_BITS-1:0] payload;

    generate if (PANEL_EVENTS) begin:panel_payload
        (* syn_ramstyle="block_ram" *) reg [31:0] memory [0:DEPTH-1];
        reg [14:0] code;
        reg [23:0] message;
        reg [1:0] length;
        reg [31:0] read_payload,bypass_payload;
        reg bypass_valid;
        wire [ADDR_WIDTH-1:0] next_index = read_index == DEPTH-1 ? 0 : read_index+1'b1;
        wire [ADDR_WIDTH-1:0] read_address = pop ? next_index : read_index;
        wire [31:0] stored = bypass_valid ? bypass_payload : read_payload;
        wire [3:0] channel = stored[18:15];
        always @* begin
            if (in_message[23:20] == 4'he) code = {1'b0,in_message[14:8],in_message[6:0]};
            else if (in_message[23:20] == 4'h9) code = {1'b1,3'd0,4'd0,in_message[14:8]};
            else if (in_message[23:20] == 4'h8) code = {1'b1,3'd1,4'd0,in_message[14:8]};
            else if (in_message[23:20] == 4'hc) code = {1'b1,3'd5,4'd0,in_message[14:8]};
            else code = {1'b1,in_message[15:8]==7 ? 3'd2 : in_message[15:8]==88 ? 3'd3 : 3'd4,4'd0,in_message[6:0]};
            length = 3;
            message = {4'he,channel,1'b0,stored[13:7],1'b0,stored[6:0]};
            if (stored[14]) case (stored[13:11])
                0: message = {4'h9,channel,1'b0,stored[6:0],8'd100};
                1: message = {4'h8,channel,1'b0,stored[6:0],8'd0};
                2: message = {4'hb,channel,8'd7,1'b0,stored[6:0]};
                3: message = {4'hb,channel,8'd88,1'b0,stored[6:0]};
                4: message = {4'hb,channel,8'd89,1'b0,stored[6:0]};
                5: begin message = {4'hc,channel,1'b0,stored[6:0],8'd0};length = 2;end
                default: message = 0;
            endcase
        end
        assign payload = {in_timestamp,in_message[19:16],code};
        assign head = out_valid ? {stored[31:19],length,message} : 39'd0;
        always @(posedge clk) begin
            if (push) memory[write_index] <= payload;
            read_payload <= memory[read_address];
            if (reset || clear) bypass_valid <= 0;
            else begin
                bypass_valid <= push && write_index == read_address;
                if (push && write_index == read_address) bypass_payload <= payload;
            end
        end
`ifndef SYNTHESIS
        always @(posedge clk) if (push) begin
            if (in_message[15] || in_message[7] || !in_message[23] ||
                in_length != (in_message[23:20]==4'hc ? 2 : 3))
                $fatal(1,"Invalid panel FIFO MIDI framing");
            case (in_message[23:20])
                4'h9: if (in_message[7:0]!=100) $fatal(1,"Panel FIFO Note On velocity changed");
                4'h8,4'hc: if (in_message[7:0]!=0) $fatal(1,"Panel FIFO Off/Program payload changed");
                4'he: begin end
                4'hb: if (in_message[15:8]!=7 && in_message[15:8]!=88 && in_message[15:8]!=89)
                    $fatal(1,"Panel FIFO received an unrepresented CC");
                default: $fatal(1,"Panel FIFO received an unrepresented message type");
            endcase
        end
`endif
    end else begin:generic_payload
        reg [38:0] memory [0:DEPTH-1];
        assign payload = {in_timestamp,in_length,in_message};
        assign head = out_valid ? memory[read_index] : 39'd0;
        always @(posedge clk) if (push) memory[write_index] <= payload;
    end endgenerate

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
