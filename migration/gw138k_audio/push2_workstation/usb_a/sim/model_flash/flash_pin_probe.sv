`timescale 1ns/1ps
// Temporary SRAM diagnostic only: full NOR payload CRC and local BSRAM CRC.
// Not the workstation, not DDR validation, never persisted as configuration.
module flash_pin_probe (
    input wire clk_50m,button1_n,flash_miso,
    output wire debug_uart_tx,flash_cs_n,flash_clk,flash_mosi,flash_wp_n,flash_hold_n
);
    reg [19:0] startup=0;
    wire reset_n=&startup && button1_n;
    always @(posedge clk_50m) if(!button1_n) startup<=0;else if(!(&startup))startup<=startup+1'b1;
    wire spi_cs,spi_clk,spi_mosi,done,req,wr;
    wire [3:0] status;
    wire [1:0] error_stage;
    wire [31:0] expected,actual,addr;
    wire [15:0] data;
    reg rsp=0;
    reg [15:0] rdata=0;
    (* ram_style="block",syn_ramstyle="block_ram" *) reg [15:0] local_memory[0:52238];
    wire [15:0] index=addr[16:1];
    always @(posedge clk_50m) begin
        rsp<=req && !wr;
        if(req && wr) local_memory[index]<=data;
        if(req && !wr) rdata<=local_memory[index];
    end
    basic_pitch_flash_model_loader u_flash (
        .clk_i(clk_50m),.rst_ni(reset_n),.boot_ready_i(1'b1),.flash_miso_i(flash_miso),
        .flash_cs_n_o(spi_cs),.flash_clk_o(spi_clk),.flash_mosi_o(spi_mosi),
        .done_o(done),.status_o(status),.debug_expected_crc_o(expected),.debug_actual_crc_o(actual),
        .debug_error_stage_o(error_stage),.mem_req_o(req),.mem_write_o(wr),.mem_byte_addr_o(addr),
        .mem_wdata_o(data),.mem_ready_i(1'b1),.mem_rsp_valid_i(rsp),.mem_rdata_i(rdata));
    basic_pitch_flash_io_guard u_io (
        .spi_cs_n_i(spi_cs),.spi_clk_i(spi_clk),.spi_mosi_i(spi_mosi),
        .flash_cs_n_o(flash_cs_n),.flash_clk_o(flash_clk),.flash_mosi_o(flash_mosi),
        .flash_wp_n_o(flash_wp_n),.flash_hold_n_o(flash_hold_n),.owned_o());
    basic_pitch_link_uart u_report (
        .clk_i(clk_50m),.rst_ni(reset_n),.bp_report_i(32'h50524F42),.tf_report_i(expected),
        .nn_report_i(actual),.sd_report_i({22'd0,1'b0,done,error_stage,status,2'b11}),
        .tick_o(),.sending_o(),.serial_o(debug_uart_tx));
endmodule
