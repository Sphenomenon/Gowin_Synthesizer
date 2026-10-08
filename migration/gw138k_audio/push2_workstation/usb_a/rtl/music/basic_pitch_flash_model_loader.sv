`timescale 1ns/1ps
`include "basic_pitch_ddr_map.svh"
`include "basic_pitch_flash_map.svh"

// Read-only SPI mode-0 boot client, 0x03 + 24-bit address. No weight ROM and
// no erase/program commands. Keep CS asserted and SCK low at byte boundaries
// during DDR backpressure. DONE requires both Flash payload CRC and a complete
// DDR readback CRC. Status 4/5/A/B/C/D/E/F follows the existing UART convention.
module basic_pitch_flash_model_loader #(
    parameter integer WORDS = `BP_FLASH_MODEL_WORDS,
    parameter logic [23:0] FLASH_BYTE_BASE = `BP_FLASH_MODEL_BYTE_BASE,
    parameter integer CLK_DIV = 4,
    parameter integer STARTUP_CYCLES = 32
) (
    input wire clk_i, rst_ni, boot_ready_i,
    input wire flash_miso_i,
    output wire flash_cs_n_o, flash_clk_o, flash_mosi_o,
    output wire done_o,
    output wire [3:0] status_o,
    output wire [31:0] debug_expected_crc_o, debug_actual_crc_o,
    output logic [1:0] debug_error_stage_o,
    output wire mem_req_o, mem_write_o,
    output wire [31:0] mem_byte_addr_o,
    output wire [15:0] mem_wdata_o,
    input wire mem_ready_i, mem_rsp_valid_i,
    input wire [15:0] mem_rdata_i
);
    localparam integer HEADER_BYTES = `BP_FLASH_MODEL_HEADER_BYTES;
    localparam integer PAYLOAD_BYTES = WORDS * 2;
    localparam integer DIV_BITS = CLK_DIV <= 1 ? 1 : $clog2(CLK_DIV);
    localparam integer START_BITS = STARTUP_CYCLES <= 1 ? 1 : $clog2(STARTUP_CYCLES);
    localparam logic [3:0] WAIT_BOOT=0, COMMAND=1, HEADER=2, HEADER_CHECK=3,
        DATA=4, WRITE=5, CHECK=10, VERIFY_REQ=11, VERIFY_WAIT=12,
        VERIFY_CHECK=13, DONE=14, ERROR=15;
    logic [3:0] state;
    logic [DIV_BITS-1:0] divider;
    logic [START_BITS-1:0] startup;
    logic spi_clk, spi_cs_n;
    logic [2:0] bit_index;
    logic [1:0] command_index;
    logic [7:0] tx_byte, rx_byte;
    logic [4:0] header_index;
    logic [255:0] header;
    logic [15:0] word_index, word_data;
    logic low_byte;
    logic [31:0] payload_crc, verify_crc;
    wire [31:0] expected_crc = header[127:96];
    wire reading = state == HEADER || state == DATA;
    wire verify_phase = state == VERIFY_REQ || state == VERIFY_WAIT ||
                        state == VERIFY_CHECK || state == DONE ||
                        (state == ERROR && debug_error_stage_o == 3);

    function automatic [31:0] crc_byte(input [31:0] prior, input [7:0] value);
        reg [31:0] c;
        integer k;
        begin
            c = prior ^ {24'd0,value};
            for (k=0; k<8; k=k+1)
                c = c[0] ? (c >> 1) ^ 32'hedb88320 : c >> 1;
            crc_byte = c;
        end
    endfunction

    assign flash_cs_n_o = spi_cs_n;
    assign flash_clk_o = spi_clk;
    assign flash_mosi_o = state == COMMAND ? tx_byte[bit_index] : 1'b0;
    assign done_o = state == DONE;
    assign status_o = state;
    assign debug_expected_crc_o = expected_crc;
    assign debug_actual_crc_o = verify_phase ? ~verify_crc : ~payload_crc;
    assign mem_req_o = state == WRITE || state == VERIFY_REQ;
    assign mem_write_o = state == WRITE;
    assign mem_byte_addr_o = `BP_DDR_NN_MODEL_BYTE_BASE + ({16'd0,word_index} << 1);
    assign mem_wdata_o = word_data;

    // Fail at elaboration/simulation for unsupported configurations.
    initial begin
        if (WORDS < 1 || WORDS > 65536 || WORDS*2 > `BP_DDR_REGION_BYTES)
            $fatal(1,"Flash model word count outside DDR/index budget");
        if (CLK_DIV < 1 || STARTUP_CYCLES < 1)
            $fatal(1,"Flash clock divider/startup must be positive");
        if ({8'd0,FLASH_BYTE_BASE}+HEADER_BYTES+PAYLOAD_BYTES > `BP_FLASH_CAPACITY_BYTES)
            $fatal(1,"Flash model exceeds 24-bit Flash partition");
    end

    always @(posedge clk_i or negedge rst_ni) begin
        if (!rst_ni) begin
            state <= WAIT_BOOT; divider <= 0; startup <= 0;
            spi_clk <= 0; spi_cs_n <= 1; bit_index <= 7; command_index <= 0;
            tx_byte <= 8'h03; rx_byte <= 0; header_index <= 0; header <= 0;
            word_index <= 0; word_data <= 0; low_byte <= 1;
            payload_crc <= 32'hffff_ffff; verify_crc <= 32'hffff_ffff;
            debug_error_stage_o <= 0;
        end else begin
            case (state)
                WAIT_BOOT: begin
                    if (!boot_ready_i) startup <= 0;
                    else if (startup == STARTUP_CYCLES-1) begin state <= COMMAND; spi_cs_n <= 0; end
                    else startup <= startup + 1'b1;
                end
                HEADER_CHECK: begin
                    // BPF1; version 1; 32-byte header; exact ABI/length;
                    // reserved fields must be zero, so unknown flags fail.
                    if (header[31:0] != 32'h31465042 || header[47:32] != 1 ||
                        header[63:48] != HEADER_BYTES || header[95:64] != PAYLOAD_BYTES ||
                        header[159:128] != WORDS || header[255:160] != 0) begin
                        state <= ERROR; spi_cs_n <= 1; debug_error_stage_o <= 1;
                    end else state <= DATA;
                end
                COMMAND, HEADER, DATA: begin
                    if (divider == CLK_DIV-1) begin
                        divider <= 0;
                        if (!spi_clk) begin
                            spi_clk <= 1;
                            if (reading) rx_byte[bit_index] <= flash_miso_i;
                        end else begin
                            spi_clk <= 0;
                            if (bit_index != 0) bit_index <= bit_index - 1'b1;
                            else begin
                                bit_index <= 7;
                                if (state == COMMAND) begin
                                    command_index <= command_index + 1'b1;
                                    case (command_index)
                                        0: tx_byte <= FLASH_BYTE_BASE[23:16];
                                        1: tx_byte <= FLASH_BYTE_BASE[15:8];
                                        2: tx_byte <= FLASH_BYTE_BASE[7:0];
                                        3: state <= HEADER;
                                    endcase
                                end else if (state == HEADER) begin
                                    header[header_index*8 +: 8] <= rx_byte;
                                    if (header_index == HEADER_BYTES-1) state <= HEADER_CHECK;
                                    else header_index <= header_index + 1'b1;
                                end else begin
                                    payload_crc <= crc_byte(payload_crc,rx_byte);
                                    low_byte <= !low_byte;
                                    if (low_byte) word_data[7:0] <= rx_byte;
                                    else begin word_data[15:8] <= rx_byte; state <= WRITE; end
                                end
                            end
                        end
                    end else divider <= divider + 1'b1;
                end
                WRITE: if (mem_ready_i) begin
                    if (word_index == WORDS-1) begin state <= CHECK; spi_cs_n <= 1; end
                    else begin word_index <= word_index + 1'b1; state <= DATA; end
                end
                CHECK: begin
                    if (~payload_crc == expected_crc) begin
                        word_index <= 0; state <= VERIFY_REQ;
                    end else begin state <= ERROR; debug_error_stage_o <= 2; end
                end
                VERIFY_REQ: if (mem_ready_i) begin
                    // Also support a zero-latency response in endpoint tests.
                    if (mem_rsp_valid_i) begin
                        verify_crc <= crc_byte(crc_byte(verify_crc,mem_rdata_i[7:0]),mem_rdata_i[15:8]);
                        if (word_index == WORDS-1) state <= VERIFY_CHECK;
                        else word_index <= word_index + 1'b1;
                    end else state <= VERIFY_WAIT;
                end
                VERIFY_WAIT: if (mem_rsp_valid_i) begin
                    verify_crc <= crc_byte(crc_byte(verify_crc,mem_rdata_i[7:0]),mem_rdata_i[15:8]);
                    if (word_index == WORDS-1) state <= VERIFY_CHECK;
                    else begin word_index <= word_index + 1'b1; state <= VERIFY_REQ; end
                end
                VERIFY_CHECK: begin
                    if (~verify_crc == expected_crc) state <= DONE;
                    else begin state <= ERROR; debug_error_stage_o <= 3; end
                end
                default: begin end
            endcase
        end
    end
endmodule
