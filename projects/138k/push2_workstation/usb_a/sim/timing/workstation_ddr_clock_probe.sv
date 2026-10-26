module workstation_ddr_clock_probe (
    input wire clk_50m, reset_n,
    output wire observed,
    output wire [14:0] ddr_addr,
    output wire [2:0] ddr_bank,
    output wire ddr_cs, ddr_ras, ddr_cas, ddr_we,
    output wire ddr_ck, ddr_ck_n, ddr_cke, ddr_odt, ddr_reset_n,
    output wire [3:0] ddr_dm,
    inout wire [31:0] ddr_dq,
    inout wire [3:0] ddr_dqs, ddr_dqs_n
);
    wire ui_clk, ui_reset_n, calibrated, locked;
    reg [7:0] ui_counter = 0;
    always @(posedge ui_clk or negedge ui_reset_n)
        if (!ui_reset_n) ui_counter <= 0;
        else ui_counter <= ui_counter + 1'b1;
    assign observed = ^ui_counter ^ calibrated ^ locked;
    ddr3_platform u_memory (
        .clk_50m(clk_50m), .rst_n(reset_n), .ui_clk(ui_clk), .ui_rst_n(ui_reset_n),
        .calib_done(calibrated), .pll_locked(locked),
        .app_cmd(3'd0), .app_en(1'b0), .app_addr(29'd0), .app_rdy(),
        .app_wdata(256'd0), .app_wmask(32'd0), .app_wren(1'b0), .app_wend(1'b0), .app_wrdy(),
        .app_rdata(), .app_rvalid(), .app_rend(),
        .ddr_addr(ddr_addr), .ddr_bank(ddr_bank), .ddr_cs(ddr_cs), .ddr_ras(ddr_ras),
        .ddr_cas(ddr_cas), .ddr_we(ddr_we), .ddr_ck(ddr_ck), .ddr_ck_n(ddr_ck_n),
        .ddr_cke(ddr_cke), .ddr_odt(ddr_odt), .ddr_reset_n(ddr_reset_n), .ddr_dm(ddr_dm),
        .ddr_dq(ddr_dq), .ddr_dqs(ddr_dqs), .ddr_dqs_n(ddr_dqs_n)
    );
endmodule
