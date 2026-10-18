// Tang Mega 138K SOM DDR3 platform, GW5AST-138C / PG484A.
// Native controller port: 100 MHz, 256 data bits, one BL8 = 32 bytes.
// app_addr is a 32-bit DQ-word address (NOT a byte address); advance by 8
// per transfer, keep app_addr[2:0]=0 and app_addr[28]=0 (one physical rank).
// Detailed provenance, pin mapping and reset sequence: docs/ddr_platform_notes.md.
module ddr3_platform (
    input  wire         clk_50m,
    input  wire         rst_n,
    output wire         ui_clk,
    output wire         ui_rst_n,
    output wire         calib_done,
    output wire         pll_locked,
    input  wire [2:0]   app_cmd,
    input  wire         app_en,
    input  wire [28:0]  app_addr,
    output wire         app_rdy,
    input  wire [255:0] app_wdata,
    input  wire [31:0]  app_wmask,
    input  wire         app_wren,
    input  wire         app_wend,
    output wire         app_wrdy,
    output wire [255:0] app_rdata,
    output wire         app_rvalid,
    output wire         app_rend,
    output wire [14:0]  ddr_addr,
    output wire [2:0]   ddr_bank,
    output wire         ddr_cs,
    output wire         ddr_ras,
    output wire         ddr_cas,
    output wire         ddr_we,
    output wire         ddr_ck,
    output wire         ddr_ck_n,
    output wire         ddr_cke,
    output wire         ddr_odt,
    output wire         ddr_reset_n,
    output wire [3:0]   ddr_dm,
    inout  wire [31:0]  ddr_dq,
    inout  wire [3:0]   ddr_dqs,
    inout  wire [3:0]   ddr_dqs_n
);
    wire memory_clk;
    wire pll_stop;
    wire controller_reset;
    wire controller_ready;
    wire controller_wrdy;
    wire controller_rvalid;
    wire controller_rend;
    wire controller_calibrated;

    // IPUG281 section 4.4.3: release rst_n in the clk domain. A later
    // loss of lock must reinitialize the PHY, not reuse old calibration.
    wire controller_rst_n, qualified_lock;
    ddr_recovery_guard u_recovery (
        .clk(clk_50m),.reset_n(rst_n),.pll_locked(pll_locked),
        .calibrated(controller_calibrated),
        .controller_reset_n(controller_rst_n),.lock_stable(qualified_lock)
    );

    // The C-version IP deliberately gates CLKOUT2 during PHY initialization.
    // Preserve the vendor's direct pll_stop -> ENCLK2 connection and the
    // PLL_INIT analog search sequence; do not replace this with a free PLL.
    ddr3_pll u_pll (
        .clkin(clk_50m), .init_clk(clk_50m), .reset(!controller_rst_n),
        .enclk0(1'b1), .enclk1(1'b1), .enclk2(pll_stop),
        .clkout0(), .clkout1(), .clkout2(memory_clk), .lock(pll_locked)
    );

    // Asynchronous assertion handles loss of memory clock; release is local
    // to the controller clock and requires successful PHY calibration.
    wire ui_reset_release = controller_rst_n && pll_locked && qualified_lock && !controller_reset &&
                            controller_calibrated;
    reg [2:0] ui_reset_sync = 3'b000;
    always @(posedge ui_clk or negedge ui_reset_release) begin
        if (!ui_reset_release)
            ui_reset_sync <= 3'b000;
        else
            ui_reset_sync <= {ui_reset_sync[1:0], 1'b1};
    end
    assign ui_rst_n = ui_reset_sync[2];
    assign calib_done = controller_calibrated;
    assign app_rdy = controller_ready && ui_rst_n;
    assign app_wrdy = controller_wrdy && ui_rst_n;
    assign app_rvalid = controller_rvalid && ui_rst_n;
    assign app_rend = controller_rend && ui_rst_n;

    DDR3_Memory_Interface_Top u_ddr3 (
        .clk(clk_50m), .memory_clk(memory_clk), .pll_lock(pll_locked),
        .rst_n(controller_rst_n), .pll_stop(pll_stop), .clk_out(ui_clk),
        .ddr_rst(controller_reset), .init_calib_complete(controller_calibrated),
        .cmd(app_cmd), .cmd_en(app_en && ui_rst_n), .addr(app_addr),
        .cmd_ready(controller_ready), .wr_data(app_wdata),
        .wr_data_mask(app_wmask), .wr_data_en(app_wren && ui_rst_n),
        .wr_data_end(app_wend && ui_rst_n), .wr_data_rdy(controller_wrdy),
        .rd_data(app_rdata), .rd_data_valid(controller_rvalid),
        .rd_data_end(controller_rend),
        .sr_req(1'b0), .ref_req(1'b0), .sr_ack(), .ref_ack(), .burst(1'b0),
        .O_ddr_addr(ddr_addr), .O_ddr_ba(ddr_bank), .O_ddr_cs_n(ddr_cs),
        .O_ddr_ras_n(ddr_ras), .O_ddr_cas_n(ddr_cas), .O_ddr_we_n(ddr_we),
        .O_ddr_clk(ddr_ck), .O_ddr_clk_n(ddr_ck_n), .O_ddr_cke(ddr_cke),
        .O_ddr_odt(ddr_odt), .O_ddr_reset_n(ddr_reset_n), .O_ddr_dqm(ddr_dm),
        .IO_ddr_dq(ddr_dq), .IO_ddr_dqs(ddr_dqs), .IO_ddr_dqs_n(ddr_dqs_n)
    );
endmodule
