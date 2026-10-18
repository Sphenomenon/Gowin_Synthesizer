// Fixed, CRC-protected host packets -> two-word 32-bit command records.
// See docs/uart_protocol.md. One outstanding transaction (stop-and-wait).
module uart_control #(
    parameter integer CLK_HZ = 50000000,
    parameter integer BAUD = 115200
) (
    input wire clk, input wire rst_n,
    input wire uart_rx, output wire uart_tx,
    input wire [31:0] time_cycles,
    output wire [31:0] cmd_data, output wire cmd_valid, input wire cmd_ready,
    output wire cmd_first, output wire cmd_last,
    input wire [31:0] rsp_data, input wire rsp_valid, output wire rsp_ready,
    output reg [31:0] error_count,
    output reg trace_packet_valid,
    output reg [31:0] trace_packet_header, trace_packet_start, trace_packet_end,
    output reg trace_ack_ready,
    output reg [31:0] trace_ack_header, trace_ack_ready_time,
    output reg trace_ack_done,
    output reg [31:0] trace_ack_done_header, trace_ack_done_time
);
    localparam integer TIMEOUT_CLKS = ((CLK_HZ+BAUD/2)/BAUD)*30;
    wire [31:0] rx_data, rx_byte_start_time;
    wire rx_valid, rx_error;
    uart_rx #(.CLK_HZ(CLK_HZ),.BAUD(BAUD)) rx_adapter(
        .clk(clk),.rst_n(rst_n),.serial_in(uart_rx),
        .time_cycles(time_cycles),.byte_start_time(rx_byte_start_time),
        .data(rx_data),.valid(rx_valid),.framing_error(rx_error));
    function [15:0] crc_byte;
        input [15:0] crc; input [7:0] value;
        reg [15:0] c; integer b;
        begin
            c = crc ^ {value,8'b0};
            for (b=0;b<8;b=b+1) c = c[15] ? (c << 1)^16'h1021 : c << 1;
            crc_byte = c;
        end
    endfunction
    reg [2:0] parser;
    reg [2:0] byte_index;
    reg [31:0] timeout_count;
    reg [15:0] rx_crc;
    reg [7:0] received_crc_lo;
    reg [31:0] header_buffer, value_buffer, command_header, command_value;
    reg [1:0] emit_state;
    reg [31:0] packet_candidate_start;
    assign cmd_valid = emit_state != 0;
    assign cmd_first = emit_state == 1;
    assign cmd_last = emit_state == 2;
    assign cmd_data = emit_state == 1 ? command_header : command_value;
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            parser <= 0; byte_index <= 0; timeout_count <= 0; rx_crc <= 16'hffff;
            received_crc_lo <= 0; header_buffer <= 0; value_buffer <= 0;
            command_header <= 0; command_value <= 0; emit_state <= 0; error_count <= 0;
            packet_candidate_start <= 0; trace_packet_valid <= 0;
            trace_packet_header <= 0; trace_packet_start <= 0; trace_packet_end <= 0;
        end else begin
            trace_packet_valid <= 0;
            if (cmd_valid && cmd_ready) emit_state <= emit_state == 1 ? 2 : 0;
            if (parser != 0) timeout_count <= timeout_count+1'b1;
            else timeout_count <= 0;
            if (rx_error || (parser != 0 && timeout_count >= TIMEOUT_CLKS)) begin
                parser <= 0; timeout_count <= 0; error_count <= error_count+1'b1;
                packet_candidate_start <= 0;
            end else if (rx_valid) begin
                timeout_count <= 0;
                case (parser)
                    0: if (rx_data[7:0] == 8'ha5) begin
                        parser <= 1; packet_candidate_start <= rx_byte_start_time;
                    end
                    1: if (rx_data[7:0] == 8'h5a) begin
                           parser <= 2; byte_index <= 0; rx_crc <= 16'hffff;
                       end else if (rx_data[7:0] == 8'ha5) begin
                           // A5 A5 5A starts at the second A5, not the first.
                           packet_candidate_start <= rx_byte_start_time;
                       end else begin parser <= 0; packet_candidate_start <= 0; end
                    2: begin
                        rx_crc <= crc_byte(rx_crc,rx_data[7:0]);
                        case (byte_index)
                            0: header_buffer[31:24] <= rx_data[7:0];
                            1: header_buffer[23:16] <= rx_data[7:0];
                            2: header_buffer[15:8] <= rx_data[7:0];
                            3: header_buffer[7:0] <= rx_data[7:0];
                            4: value_buffer[7:0] <= rx_data[7:0];
                            5: value_buffer[15:8] <= rx_data[7:0];
                            6: value_buffer[23:16] <= rx_data[7:0];
                            7: value_buffer[31:24] <= rx_data[7:0];
                        endcase
                        if (byte_index == 7) parser <= 3;
                        else byte_index <= byte_index+1'b1;
                    end
                    3: begin received_crc_lo <= rx_data[7:0]; parser <= 4; end
                    4: begin
                        parser <= 0; packet_candidate_start <= 0;
                        if ({rx_data[7:0],received_crc_lo} == rx_crc && emit_state == 0) begin
                            command_header <= header_buffer; command_value <= value_buffer; emit_state <= 1;
                            trace_packet_valid <= 1; trace_packet_header <= header_buffer;
                            trace_packet_start <= packet_candidate_start; trace_packet_end <= time_cycles;
                        end else error_count <= error_count+1'b1;
                    end
                    default: parser <= 0;
                endcase
            end
        end
    end

    reg response_busy;
    reg [31:0] response;
    reg [15:0] response_crc;
    reg [2:0] response_index;
    reg [31:0] tx_data;
    wire tx_ready, tx_byte_done;
    reg final_byte_inflight;
    reg [31:0] final_byte_header;
    assign rsp_ready = !response_busy;
    always @* begin
        tx_data = 0;
        case (response_index)
            0: tx_data[7:0] = 8'ha5;
            1: tx_data[7:0] = 8'h5a;
            2: tx_data[7:0] = response[31:24];
            3: tx_data[7:0] = response[23:16];
            4: tx_data[7:0] = response[15:8];
            5: tx_data[7:0] = response[7:0];
            6: tx_data[7:0] = response_crc[7:0];
            7: tx_data[7:0] = response_crc[15:8];
        endcase
    end
    uart_tx #(.CLK_HZ(CLK_HZ),.BAUD(BAUD)) tx_adapter(
        .clk(clk),.rst_n(rst_n),.data(tx_data),.valid(response_busy),
        .ready(tx_ready),.serial_out(uart_tx),.byte_done(tx_byte_done));
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            response_busy <= 0; response <= 0; response_crc <= 0; response_index <= 0;
            final_byte_inflight <= 0; final_byte_header <= 0;
            trace_ack_ready <= 0; trace_ack_header <= 0; trace_ack_ready_time <= 0;
            trace_ack_done <= 0; trace_ack_done_header <= 0; trace_ack_done_time <= 0;
        end
        else begin
            trace_ack_ready <= 0; trace_ack_done <= 0;
            if (rsp_valid && rsp_ready) begin
                response <= rsp_data; response_index <= 0; response_busy <= 1;
                trace_ack_ready <= 1; trace_ack_header <= rsp_data; trace_ack_ready_time <= time_cycles;
                response_crc <= crc_byte(crc_byte(crc_byte(crc_byte(16'hffff,
                    rsp_data[31:24]),rsp_data[23:16]),rsp_data[15:8]),rsp_data[7:0]);
            end
            if (response_busy && tx_ready) begin
                if (response_index == 7) begin
                    response_busy <= 0;
                    final_byte_inflight <= 1; final_byte_header <= response;
                end
                else response_index <= response_index+1'b1;
            end
            // response can already contain the next ACK while the previous
            // CRC byte is still on the wire. Keep that final byte's own tag.
            if (tx_byte_done && final_byte_inflight) begin
                final_byte_inflight <= 0; trace_ack_done <= 1;
                trace_ack_done_header <= final_byte_header; trace_ack_done_time <= time_cycles;
            end
        end
    end
endmodule
