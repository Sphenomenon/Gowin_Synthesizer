`timescale 1ns/1ps
// Transport-neutral byte endpoint for the USB vendor bulk control interface.
// A transfer is accepted only when valid && ready. All ports use clk.
module screen_control_endpoint (
    input  wire              clk,
    input  wire              reset,
    input  wire              rx_valid,
    output wire              rx_ready,
    input  wire [7:0]        rx_data,
    output wire              tx_valid,
    input  wire              tx_ready,
    output wire [7:0]        tx_data,
    input  wire [31:0]       status_flags,
    input  wire [799:0]      touch_diagnostics,
    output reg  [3:0]        midi_channel,
    output reg signed [7:0]  transpose,
    output reg  [3:0]        screen_page,
    output reg  [15:0]       theme_rgb565,
    output reg  [15:0]       clear_rgb565,
    output reg               screen_update,
    output reg  [15:0]       protocol_errors,
    // Accepted writes, for a board application's unified local/host settings.
    output reg               config_write,
    output reg [7:0]         config_opcode,
    output reg [31:0]        config_value
);
    localparam [2:0] FIND_M = 3'd0, FIND_K = 3'd1, RECEIVE = 3'd2,
                     CHECK = 3'd3, BUILD_CRC = 3'd4, REPLY = 3'd5;
    reg [2:0] state;
    reg [3:0] rx_index;
    reg [3:0] tx_index;
    reg [3:0] crc_index;
    reg [127:0] request;
    reg [127:0] response;
    reg [15:0] request_crc;
    reg [15:0] response_crc;

    wire [7:0] opcode = request[31:24];
    wire [31:0] arg0 = request[79:48];
    wire [31:0] arg1 = request[111:80];
    reg [31:0] response_status;
    reg [31:0] response_result;

    function [15:0] crc16_byte;
        input [15:0] previous;
        input [7:0] value;
        reg [15:0] work;
        integer bit_number;
        begin
            work = previous ^ {value, 8'h00};
            for (bit_number = 0; bit_number < 8; bit_number = bit_number + 1)
                if (work[15]) work = (work << 1) ^ 16'h1021;
                else work = work << 1;
            crc16_byte = work;
        end
    endfunction

    // Error priority is CRC, version, opcode, then arguments. Invalid requests
    // never alter settings. Reply status is a uint32 in the arg0 field.
    always @* begin
        response_status = 32'd0;
        response_result = 32'd0;
        if (request[127:112] != request_crc)
            response_status = 32'd3;
        else if (request[23:16] != 8'h01)
            response_status = 32'd4;
        else begin
            case (opcode)
                8'h01: begin
                    if (arg0 != 0 || arg1 != 0) response_status = 32'd2;
                    else response_result = status_flags;
                end
                8'h02: begin
                    if (arg0 > 24 || arg1 != 0) response_status = 32'd2;
                    else response_result = touch_diagnostics[arg0[4:0]*32+:32];
                end
                8'h10, 8'h20: begin
                    if (arg0 > 32'd15 || arg1 != 0) response_status = 32'd2;
                    else response_result = arg0;
                end
                8'h11: begin
                    if ($signed(arg0) < -32'sd48 || $signed(arg0) > 32'sd48 || arg1 != 0)
                        response_status = 32'd2;
                    else response_result = arg0;
                end
                8'h21, 8'h22: begin
                    if (arg0 > 32'h0000ffff || arg1 != 0) response_status = 32'd2;
                    else response_result = arg0;
                end
                default: response_status = 32'd1;
            endcase
        end
    end

    assign rx_ready = (state == FIND_M || state == FIND_K || state == RECEIVE) && !reset;
    assign tx_valid = (state == REPLY) && !reset;
    assign tx_data = response[tx_index*8 +: 8];

    always @(posedge clk) begin
        if (reset) begin
            state <= FIND_M;
            rx_index <= 4'd0;
            tx_index <= 4'd0;
            crc_index <= 4'd0;
            request <= 128'd0;
            response <= 128'd0;
            request_crc <= 16'hffff;
            response_crc <= 16'hffff;
            midi_channel <= 4'd0;
            transpose <= 8'sd0;
            screen_page <= 4'd0;
            theme_rgb565 <= 16'h07ff;
            clear_rgb565 <= 16'h0000;
            screen_update <= 1'b0;
            protocol_errors <= 16'd0;
            config_write <= 1'b0;
            config_opcode <= 0;
            config_value <= 0;
        end else begin
            screen_update <= 1'b0;
            config_write <= 1'b0;
            case (state)
                FIND_M: if (rx_valid && rx_ready && rx_data == 8'h4d) begin
                    request[7:0] <= 8'h4d;
                    request_crc <= crc16_byte(16'hffff, 8'h4d);
                    state <= FIND_K;
                end
                FIND_K: if (rx_valid && rx_ready) begin
                    if (rx_data == 8'h4b) begin
                        request[15:8] <= 8'h4b;
                        request_crc <= crc16_byte(request_crc, 8'h4b);
                        rx_index <= 4'd2;
                        state <= RECEIVE;
                    end else if (rx_data != 8'h4d) begin
                        state <= FIND_M;
                    end
                    // A repeated M can be the start of a new MK signature.
                end
                RECEIVE: if (rx_valid && rx_ready) begin
                    request[rx_index*8 +: 8] <= rx_data;
                    if (rx_index < 4'd14)
                        request_crc <= crc16_byte(request_crc, rx_data);
                    if (rx_index == 4'd15)
                        state <= CHECK;
                    else rx_index <= rx_index + 1'b1;
                end
                CHECK: begin
                    // Little-endian byte storage; compute the outgoing CRC a
                    // byte per clock to keep the FPGA combinational path short.
                    response <= {16'h0000, response_result, response_status,
                                 request[47:32], (opcode | 8'h80), 8'h01, 8'h4b, 8'h4d};
                    response_crc <= 16'hffff;
                    crc_index <= 4'd0;
                    tx_index <= 4'd0;
                    state <= BUILD_CRC;
                    if (response_status != 0) begin
                        if (protocol_errors != 16'hffff)
                            protocol_errors <= protocol_errors + 1'b1;
                    end else begin
                        if (opcode != 8'h01 && opcode != 8'h02) begin
                            config_write <= 1'b1;
                            config_opcode <= opcode;
                            config_value <= arg0;
                        end
                        case (opcode)
                            8'h10: midi_channel <= arg0[3:0];
                            8'h11: transpose <= arg0[7:0];
                            8'h20: begin
                                screen_page <= arg0[3:0];
                                screen_update <= 1'b1;
                            end
                            8'h21: begin
                                theme_rgb565 <= arg0[15:0];
                                screen_update <= 1'b1;
                            end
                            8'h22: begin
                                clear_rgb565 <= arg0[15:0];
                                screen_update <= 1'b1;
                            end
                            default: begin end
                        endcase
                    end
                end
                BUILD_CRC: begin
                    response_crc <= crc16_byte(response_crc, response[crc_index*8 +: 8]);
                    if (crc_index == 4'd13) begin
                        response[127:112] <= crc16_byte(response_crc, response[crc_index*8 +: 8]);
                        state <= REPLY;
                    end else crc_index <= crc_index + 1'b1;
                end
                REPLY: if (tx_valid && tx_ready) begin
                    if (tx_index == 4'd15) state <= FIND_M;
                    else tx_index <= tx_index + 1'b1;
                end
                default: state <= FIND_M;
            endcase
        end
    end
endmodule
