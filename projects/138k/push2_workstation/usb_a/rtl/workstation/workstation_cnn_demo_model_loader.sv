`timescale 1ns/1ps
`include "basic_pitch_ddr_map.svh"

// CNN-DEMO only. The accepted model E travels in the configuration image as
// synchronous BSRAM ROM. Keep the historical loader's DDR/status contract:
// status E is released only after every DDR word passes a readback CRC.
// The existing ordered request FIFO waits for DDR calibration/BIST; it never
// holds up the independent audio sample clock. Song restart does not reset us.
module workstation_cnn_demo_model_loader #(
    parameter integer WORDS = 52239,
    parameter [31:0] EXPECTED_CRC = 32'hAF01A61B,
    parameter integer WAIT_CYCLES = 250_000_000
) (
    input wire clk_i, rst_ni, serial_i,
    output wire done_o,
    output wire [3:0] status_o,
    output wire [31:0] debug_expected_crc_o, debug_actual_crc_o,
    output reg [1:0] debug_error_stage_o,
    output wire mem_req_o, mem_write_o,
    output wire [31:0] mem_byte_addr_o,
    output wire [15:0] mem_wdata_o,
    input wire mem_ready_i, mem_rsp_valid_i,
    input wire [15:0] mem_rdata_i
);
    localparam [3:0] READ=0, LATCH=1, WRITE=5, CRC_LOW=6, CRC_HIGH=7,
        VERIFY_REQ=11, VERIFY_WAIT=12, VERIFY_CHECK=13, DONE=14, ERROR=15;
    localparam integer WAIT_BITS = $clog2(WAIT_CYCLES+1);
    reg [3:0] state;
    reg [15:0] word_index, rom_data, verify_word;
    reg [31:0] verify_crc;
    reg [WAIT_BITS-1:0] wait_count;
    (* syn_romstyle="block_rom", rom_style="block" *)
    reg [15:0] model_rom [0:WORDS-1];
    initial $readmemh("rtl/music/weights/cnn_ddr_blob.mem", model_rom);
    // Separate unreset synchronous read preserves BSRAM ROM inference.
    always @(posedge clk_i) rom_data <= model_rom[word_index];

    function automatic [31:0] crc_byte(input [31:0] old_crc, input [7:0] value);
        reg [31:0] c;
        integer k;
        begin
            c = old_crc ^ value;
            for (k=0; k<8; k=k+1)
                c = c[0] ? ((c >> 1) ^ 32'hedb88320) : (c >> 1);
            crc_byte = c;
        end
    endfunction
    assign done_o = state == DONE;
    assign status_o = state;
    assign debug_expected_crc_o = EXPECTED_CRC;
    assign debug_actual_crc_o = ~verify_crc;
    assign mem_req_o = state == WRITE || state == VERIFY_REQ;
    assign mem_write_o = state == WRITE;
    assign mem_byte_addr_o = `BP_DDR_NN_MODEL_BYTE_BASE + ({16'd0,word_index} << 1);
    assign mem_wdata_o = rom_data;

    always @(posedge clk_i or negedge rst_ni) begin
        if (!rst_ni) begin
            state <= READ;
            word_index <= 0;
            verify_word <= 0;
            verify_crc <= 32'hffffffff;
            wait_count <= 0;
            debug_error_stage_o <= 0;
        end else if ((state==WRITE || state==VERIFY_REQ || state==VERIFY_WAIT) &&
                     wait_count == WAIT_CYCLES-1) begin
            state <= ERROR;
            debug_error_stage_o <= 1;
        end else begin
            if ((state==WRITE || state==VERIFY_REQ) && !mem_ready_i ||
                state==VERIFY_WAIT && !mem_rsp_valid_i) wait_count <= wait_count+1'b1;
            else wait_count <= 0;
            case (state)
                READ: state <= LATCH;
                LATCH: state <= WRITE;
                WRITE: if (mem_ready_i) begin
                    if (word_index == WORDS-1) begin
                        word_index <= 0;
                        state <= VERIFY_REQ;
                    end else begin
                        word_index <= word_index+1'b1;
                        state <= READ;
                    end
                end
                VERIFY_REQ: if (mem_ready_i) state <= VERIFY_WAIT;
                VERIFY_WAIT: if (mem_rsp_valid_i) begin
                    verify_word <= mem_rdata_i;
                    state <= CRC_LOW;
                end
                CRC_LOW: begin
                    verify_crc <= crc_byte(verify_crc,verify_word[7:0]);
                    state <= CRC_HIGH;
                end
                CRC_HIGH: begin
                    verify_crc <= crc_byte(verify_crc,verify_word[15:8]);
                    if (word_index == WORDS-1) state <= VERIFY_CHECK;
                    else begin word_index <= word_index+1'b1; state <= VERIFY_REQ; end
                end
                VERIFY_CHECK: if (~verify_crc == EXPECTED_CRC) state <= DONE;
                    else begin state <= ERROR; debug_error_stage_o <= 3; end
                DONE, ERROR: begin end
                default: begin state <= ERROR; debug_error_stage_o <= 2; end
            endcase
        end
    end
endmodule
