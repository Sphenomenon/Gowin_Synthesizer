`timescale 1ns/1ps
// Temporary SRAM-only isolation diagnostic. Uses the actual external DDR PHY,
// original 16-bit model parser/CDC client, and no CPU/display/audio DMA clients.
module flash_ddr_probe (
    input wire clk_50m,button1_n,flash_miso,
    output wire debug_uart_tx,flash_cs_n,flash_clk,flash_mosi,flash_wp_n,flash_hold_n,
    output wire [14:0] ddr_addr, output wire [2:0] ddr_bank,
    output wire ddr_cs,ddr_ras,ddr_cas,ddr_we,ddr_ck,ddr_ck_n,ddr_cke,ddr_odt,ddr_reset_n,
    output wire [3:0] ddr_dm,
    inout wire [31:0] ddr_dq, inout wire [3:0] ddr_dqs,ddr_dqs_n
);
    reg [19:0] startup=0;
    wire reset_n=&startup && button1_n;
    always @(posedge clk_50m) if(!button1_n) startup<=0;else if(!(&startup))startup<=startup+1'b1;
    wire memory_clk,memory_reset_n,memory_calibrated,memory_locked;
    wire [2:0] app_cmd;
    wire app_en,app_rdy,app_wren,app_wrdy,app_rvalid,app_rend;
    wire [28:0] app_addr;
    wire [255:0] app_wdata,app_rdata;
    wire [31:0] app_wmask;
    ddr3_platform u_memory (
        .clk_50m(clk_50m),.rst_n(reset_n),.ui_clk(memory_clk),.ui_rst_n(memory_reset_n),
        .calib_done(memory_calibrated),.pll_locked(memory_locked),
        .app_cmd(app_cmd),.app_en(app_en),.app_addr(app_addr),.app_rdy(app_rdy),
        .app_wdata(app_wdata),.app_wmask(app_wmask),.app_wren(app_wren),.app_wend(app_wren),
        .app_wrdy(app_wrdy),.app_rdata(app_rdata),.app_rvalid(app_rvalid),.app_rend(app_rend),
        .ddr_addr(ddr_addr),.ddr_bank(ddr_bank),.ddr_cs(ddr_cs),.ddr_ras(ddr_ras),
        .ddr_cas(ddr_cas),.ddr_we(ddr_we),.ddr_ck(ddr_ck),.ddr_ck_n(ddr_ck_n),
        .ddr_cke(ddr_cke),.ddr_odt(ddr_odt),.ddr_reset_n(ddr_reset_n),.ddr_dm(ddr_dm),
        .ddr_dq(ddr_dq),.ddr_dqs(ddr_dqs),.ddr_dqs_n(ddr_dqs_n));
    wire spi_cs,spi_clk,spi_mosi,model_serial;
    wire [3:0] status;
    wire [1:0] source,flash_error,model_error;
    wire [31:0] expected,actual,addr;
    wire [15:0] data,rdata;
    wire req,wr,ready,rsp;
    basic_pitch_flash_serial_boot u_transport (
        .clk_i(clk_50m),.rst_ni(reset_n),.boot_ready_i(memory_reset_n && memory_calibrated),
        .serial_i(1'b1),.flash_miso_i(flash_miso),.model_status_i(status),.serial_o(model_serial),
        .flash_cs_n_o(spi_cs),.flash_clk_o(spi_clk),.flash_mosi_o(spi_mosi),
        .source_o(source),.error_stage_o(flash_error),.state_o());
    basic_pitch_uart_model_loader u_parser (
        .clk_i(clk_50m),.rst_ni(reset_n),.serial_i(model_serial),.done_o(),.status_o(status),
        .debug_expected_crc_o(expected),.debug_actual_crc_o(actual),.debug_error_stage_o(model_error),
        .mem_req_o(req),.mem_write_o(wr),.mem_byte_addr_o(addr),.mem_wdata_o(data),
        .mem_ready_i(ready),.mem_rsp_valid_i(rsp),.mem_rdata_i(rdata));
    wire fifo_valid,fifo_ready,cmd_valid,cmd_ready,rsp_valid,rsp_ready;
    wire [48:0] fifo_data,cmd_data;
    wire [15:0] rsp_data;
    music_async_fifo #(.WIDTH(49),.ADDRESS_BITS(4)) u_req_cdc (
        .write_clk_i(clk_50m),.write_rst_ni(reset_n),.write_valid_i(req),.write_ready_o(ready),
        .write_data_i({wr,addr,data}),.read_clk_i(memory_clk),.read_rst_ni(memory_reset_n),
        .read_valid_o(fifo_valid),.read_ready_i(fifo_ready),.read_data_o(fifo_data));
    basic_pitch_ddr_command_buffer u_command (
        .clk_i(memory_clk),.rst_ni(memory_reset_n),.in_valid_i(fifo_valid),.in_data_i(fifo_data),
        .in_ready_o(fifo_ready),.out_valid_o(cmd_valid),.out_data_o(cmd_data),.out_ready_i(cmd_ready));
    music_async_fifo #(.WIDTH(16),.ADDRESS_BITS(2)) u_rsp_cdc (
        .write_clk_i(memory_clk),.write_rst_ni(memory_reset_n),.write_valid_i(rsp_valid),
        .write_ready_o(rsp_ready),.write_data_i(rsp_data),.read_clk_i(clk_50m),.read_rst_ni(reset_n),
        .read_valid_o(rsp),.read_ready_i(1'b1),.read_data_o(rdata));
    wire ddr_req,ddr_write,ddr_ready;
    basic_pitch_ddr16_port u_ddr16 (
        .clk_i(memory_clk),.rst_ni(memory_reset_n),
        .req_valid_i(cmd_valid && memory_calibrated && (cmd_data[48] || rsp_ready)),
        .req_write_i(cmd_data[48]),.req_byte_addr_i(cmd_data[47:16]),.req_wdata_i(cmd_data[15:0]),
        .req_ready_o(cmd_ready),.rsp_valid_o(rsp_valid),.rsp_rdata_o(rsp_data),
        .ddr_req_o(ddr_req),.ddr_write_o(ddr_write),.ddr_address_o(app_addr),
        .ddr_data_o(app_wdata),.ddr_mask_o(app_wmask),.ddr_ready_i(ddr_ready),
        .ddr_response_i(app_rvalid),.ddr_read_data_i(app_rdata));
    assign app_cmd=ddr_write?3'b000:3'b001;
    assign ddr_ready=memory_reset_n && app_rdy && (!ddr_write || app_wrdy);
    assign app_en=ddr_req && ddr_ready;
    assign app_wren=app_en && ddr_write;
    basic_pitch_flash_io_guard u_io (
        .spi_cs_n_i(spi_cs),.spi_clk_i(spi_clk),.spi_mosi_i(spi_mosi),
        .flash_cs_n_o(flash_cs_n),.flash_clk_o(flash_clk),.flash_mosi_o(flash_mosi),
        .flash_wp_n_o(flash_wp_n),.flash_hold_n_o(flash_hold_n),.owned_o());
    (* ASYNC_REG="TRUE" *) reg [2:0] flags_meta,flags_sync;
    always @(posedge clk_50m or negedge reset_n)
        if(!reset_n)begin flags_meta<=0;flags_sync<=0;end
        else begin flags_meta<={memory_locked,memory_reset_n,memory_calibrated};flags_sync<=flags_meta;end
    basic_pitch_link_uart u_report (
        .clk_i(clk_50m),.rst_ni(reset_n),.bp_report_i(32'h44445250),.tf_report_i(expected),
        .nn_report_i(actual),.sd_report_i({19'd0,flags_sync,source,model_error,status,2'b11}),
        .tick_o(),.sending_o(),.serial_o(debug_uart_tx));
endmodule
