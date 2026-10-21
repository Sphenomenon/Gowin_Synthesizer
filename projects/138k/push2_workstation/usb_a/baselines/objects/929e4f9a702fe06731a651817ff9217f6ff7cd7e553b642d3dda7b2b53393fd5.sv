`timescale 1ns/1ps
`include "basic_pitch_ddr_map.svh"

// Receives BPN1 + 52239 little-endian words + CRC32 over UART. The bitstream
// contains no CNN parameter ROM. A full DDR readback CRC gates model_done_o.
module basic_pitch_uart_model_loader #(
    parameter integer WORDS = 52239,
    parameter integer CLK_HZ = 50_000_000,
    parameter integer BAUD = 115200
) (
    input  logic        clk_i,
    input  logic        rst_ni,
    input  logic        serial_i,
    output logic        done_o,
    output logic [3:0]  status_o,
    output logic [31:0] debug_expected_crc_o,
    output logic [31:0] debug_actual_crc_o,
    output logic [1:0] debug_error_stage_o,
    output logic        mem_req_o,
    output logic        mem_write_o,
    output logic [31:0] mem_byte_addr_o,
    output logic [15:0] mem_wdata_o,
    input  logic        mem_ready_i,
    input  logic        mem_rsp_valid_i,
    input  logic [15:0] mem_rdata_i
);
    localparam logic [3:0] MAGIC0=0, MAGIC1=1, MAGIC2=2, MAGIC3=3,
        DATA=4, WRITE=5, CRC0=6, CRC1=7, CRC2=8, CRC3=9,
        CHECK=10, VERIFY_REQ=11, VERIFY_WAIT=12, VERIFY_CHECK=13,
        DONE=14, ERROR=15;
    logic [3:0] state;
    logic [15:0] word_index;
    logic low_byte;
    logic [15:0] word_data;
    logic [31:0] rx_crc, expected_crc, verify_crc;
    wire [31:0] rx_data;
    wire rx_valid, rx_framing_error;

    function automatic [31:0] crc_byte(input [31:0] old_crc, input [7:0] value);
        logic [31:0] c;
        integer k;
        begin
            c = old_crc ^ value;
            for (k = 0; k < 8; k = k + 1)
                c = c[0] ? ((c >> 1) ^ 32'hedb88320) : (c >> 1);
            crc_byte = c;
        end
    endfunction

    basic_pitch_uart_rx #(.CLK_HZ(CLK_HZ), .BAUD(BAUD)) u_rx (
        .clk(clk_i), .rst_n(rst_ni), .serial_in(serial_i),
        .time_cycles(32'd0), .data(rx_data), .valid(rx_valid),
        .framing_error(rx_framing_error), .byte_start_time()
    );

    assign done_o = state == DONE;
    assign status_o = state;
    assign debug_expected_crc_o = expected_crc;
    assign debug_actual_crc_o = state==VERIFY_CHECK || state==DONE ||
                                (state==ERROR && debug_error_stage_o==2'd3) ?
                                ~verify_crc : ~rx_crc;
    assign mem_req_o = state == WRITE || state == VERIFY_REQ;
    assign mem_write_o = state == WRITE;
    assign mem_byte_addr_o = `BP_DDR_NN_MODEL_BYTE_BASE + ({16'd0, word_index} << 1);
    assign mem_wdata_o = word_data;

    always_ff @(posedge clk_i or negedge rst_ni) begin
        if (!rst_ni) begin
            state <= MAGIC0;
            word_index <= 0;
            low_byte <= 1'b1;
            word_data <= 0;
            rx_crc <= 32'hffff_ffff;
            expected_crc <= 0;
            verify_crc <= 32'hffff_ffff;
            debug_error_stage_o <= 0;
        end else begin
            if (rx_framing_error && state >= DATA && state <= CRC3) begin
                state <= ERROR;debug_error_stage_o<=2'd1;
            end
            else case (state)
                MAGIC0: if (rx_valid && rx_data[7:0] == "B") state <= MAGIC1;
                MAGIC1: if (rx_valid) state <= (rx_data[7:0] == "P") ? MAGIC2 : MAGIC0;
                MAGIC2: if (rx_valid) state <= (rx_data[7:0] == "N") ? MAGIC3 : MAGIC0;
                MAGIC3: if (rx_valid) state <= (rx_data[7:0] == "1") ? DATA : MAGIC0;
                DATA: if (rx_valid) begin
                    rx_crc <= crc_byte(rx_crc, rx_data[7:0]);
                    if (low_byte) begin
                        word_data[7:0] <= rx_data[7:0];
                        low_byte <= 1'b0;
                    end else begin
                        word_data[15:8] <= rx_data[7:0];
                        low_byte <= 1'b1;
                        state <= WRITE;
                    end
                end
                WRITE: if (mem_ready_i) begin
                    if (word_index == WORDS-1) state <= CRC0;
                    else begin word_index <= word_index + 1'b1; state <= DATA; end
                end
                CRC0: if (rx_valid) begin expected_crc[7:0] <= rx_data[7:0]; state <= CRC1; end
                CRC1: if (rx_valid) begin expected_crc[15:8] <= rx_data[7:0]; state <= CRC2; end
                CRC2: if (rx_valid) begin expected_crc[23:16] <= rx_data[7:0]; state <= CRC3; end
                CRC3: if (rx_valid) begin expected_crc[31:24] <= rx_data[7:0]; state <= CHECK; end
                CHECK: if ((~rx_crc) == expected_crc) begin
                    word_index <= 0;
                    verify_crc <= 32'hffff_ffff;
                    state <= VERIFY_REQ;
                end else begin state <= ERROR;debug_error_stage_o<=2'd2;end
                VERIFY_REQ: if (mem_ready_i) state <= VERIFY_WAIT;
                VERIFY_WAIT: if (mem_rsp_valid_i) begin
                    verify_crc <= crc_byte(crc_byte(verify_crc, mem_rdata_i[7:0]),
                                           mem_rdata_i[15:8]);
                    if (word_index == WORDS-1) state <= VERIFY_CHECK;
                    else begin word_index <= word_index + 1'b1; state <= VERIFY_REQ; end
                end
                VERIFY_CHECK: if((~verify_crc) == expected_crc) state<=DONE;
                    else begin state<=ERROR;debug_error_stage_o<=2'd3;end
                DONE, ERROR: begin end
                default: state <= ERROR;
            endcase
        end
    end
endmodule
