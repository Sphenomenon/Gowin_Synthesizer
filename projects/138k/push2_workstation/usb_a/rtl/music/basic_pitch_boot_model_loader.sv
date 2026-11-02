`timescale 1ns/1ps
`include "basic_pitch_flash_map.svh"
// Runtime selection: try read-only Flash boot once; on an explicit header,
// payload CRC or DDR CRC error release the original BPN1 UART recovery loader.
// Error handover occurs with no outstanding read. Queued writes retain order
// in the shared DDR request FIFO. A successful Flash model is immutable until
// reset; analysis_restart does not disturb it.
module basic_pitch_boot_model_loader #(
    parameter integer WORDS = `BP_FLASH_MODEL_WORDS,
    parameter logic [23:0] FLASH_BYTE_BASE = `BP_FLASH_MODEL_BYTE_BASE,
    parameter integer CLK_DIV = 4,
    parameter integer CLK_HZ = 50_000_000,
    parameter integer UART_BAUD = 115200,
    parameter bit VERIFY_DDR = 1'b1
) (
    input wire clk_i, rst_ni, boot_ready_i, serial_i, flash_miso_i,
    output wire flash_cs_n_o, flash_clk_o, flash_mosi_o,
    output wire done_o,
    output wire [3:0] status_o,
    output wire [1:0] source_o, flash_error_o,
    output wire [31:0] debug_expected_crc_o, debug_actual_crc_o,
    output wire [1:0] debug_error_stage_o,
    output wire mem_req_o, mem_write_o,
    output wire [31:0] mem_byte_addr_o,
    output wire [15:0] mem_wdata_o,
    input wire mem_ready_i, mem_rsp_valid_i,
    input wire [15:0] mem_rdata_i
);
    logic fallback;
    wire f_done,u_done,f_req,u_req,f_write,u_write;
    wire [3:0] f_status,u_status;
    wire [1:0] f_error,u_error;
    wire [31:0] f_expected,u_expected,f_actual,u_actual,f_addr,u_addr;
    wire [15:0] f_data,u_data;
    always @(posedge clk_i or negedge rst_ni)
        if (!rst_ni) fallback <= 0;
        else if (f_status == 15) fallback <= 1;
    assign source_o = fallback ? 2'd2 : (f_done ? 2'd1 : 2'd0);
    assign flash_error_o = f_error;
    assign done_o = fallback ? u_done : f_done;
    assign status_o = fallback ? u_status : f_status;
    assign debug_expected_crc_o = fallback ? u_expected : f_expected;
    assign debug_actual_crc_o = fallback ? u_actual : f_actual;
    assign debug_error_stage_o = fallback ? u_error : f_error;
    assign mem_req_o = fallback ? u_req : f_req;
    assign mem_write_o = fallback ? u_write : f_write;
    assign mem_byte_addr_o = fallback ? u_addr : f_addr;
    assign mem_wdata_o = fallback ? u_data : f_data;
    basic_pitch_flash_model_loader #(.WORDS(WORDS),.FLASH_BYTE_BASE(FLASH_BYTE_BASE),.CLK_DIV(CLK_DIV),.VERIFY_DDR(VERIFY_DDR)) u_flash (
        .clk_i(clk_i),.rst_ni(rst_ni),.boot_ready_i(boot_ready_i),.flash_miso_i(flash_miso_i),
        .flash_cs_n_o(flash_cs_n_o),.flash_clk_o(flash_clk_o),.flash_mosi_o(flash_mosi_o),
        .done_o(f_done),.status_o(f_status),.debug_expected_crc_o(f_expected),
        .debug_actual_crc_o(f_actual),.debug_error_stage_o(f_error),
        .mem_req_o(f_req),.mem_write_o(f_write),.mem_byte_addr_o(f_addr),.mem_wdata_o(f_data),
        .mem_ready_i(mem_ready_i && !fallback),.mem_rsp_valid_i(mem_rsp_valid_i && !fallback),
        .mem_rdata_i(mem_rdata_i));
    basic_pitch_uart_model_loader #(.WORDS(WORDS),.CLK_HZ(CLK_HZ),.BAUD(UART_BAUD),.VERIFY_DDR(VERIFY_DDR)) u_uart (
        .clk_i(clk_i),.rst_ni(rst_ni && fallback),.serial_i(serial_i),
        .done_o(u_done),.status_o(u_status),.debug_expected_crc_o(u_expected),
        .debug_actual_crc_o(u_actual),.debug_error_stage_o(u_error),
        .mem_req_o(u_req),.mem_write_o(u_write),.mem_byte_addr_o(u_addr),.mem_wdata_o(u_data),
        .mem_ready_i(mem_ready_i && fallback),.mem_rsp_valid_i(mem_rsp_valid_i && fallback),
        .mem_rdata_i(mem_rdata_i));
endmodule
