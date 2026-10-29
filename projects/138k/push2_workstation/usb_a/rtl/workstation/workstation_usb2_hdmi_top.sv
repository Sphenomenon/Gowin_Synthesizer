module workstation_usb2_hdmi_top (
    input wire clk_50m, pc_uart_rx_i,
    output wire debug_uart_tx,
    input wire usb2_ulpi_clk, usb2_ulpi_dir, usb2_ulpi_nxt,
    inout wire [7:0] usb2_ulpi_data,
    output wire usb2_ulpi_stp,
    input wire hdmi_hpd,
    inout wire hdmi_cec,
    output wire tmds_clk_p, tmds_clk_n,
    output wire [2:0] tmds_data_p, tmds_data_n,
    output wire [14:0] ddr_addr,
    output wire [2:0] ddr_bank,
    output wire ddr_cs, ddr_ras, ddr_cas, ddr_we,
    output wire ddr_ck, ddr_ck_n, ddr_cke, ddr_odt, ddr_reset_n,
    output wire [3:0] ddr_dm,
    inout wire [31:0] ddr_dq,
    inout wire [3:0] ddr_dqs, ddr_dqs_n
);
    workstation_usb2_hotplug_top u_usb (
        .clk_50m(clk_50m), .pc_uart_rx_i(pc_uart_rx_i), .debug_uart_tx(debug_uart_tx),
        .usb2_ulpi_clk(usb2_ulpi_clk), .usb2_ulpi_dir(usb2_ulpi_dir), .usb2_ulpi_nxt(usb2_ulpi_nxt),
        .usb2_ulpi_data(usb2_ulpi_data), .usb2_ulpi_stp(usb2_ulpi_stp)
    );
    workstation_hdmi_probe_top u_hdmi (
        .clk_50m(clk_50m), .hdmi_hpd(hdmi_hpd), .hdmi_cec(hdmi_cec),
        .tmds_clk_p(tmds_clk_p), .tmds_clk_n(tmds_clk_n),
        .tmds_data_p(tmds_data_p), .tmds_data_n(tmds_data_n),
        .ddr_addr(ddr_addr), .ddr_bank(ddr_bank), .ddr_cs(ddr_cs), .ddr_ras(ddr_ras),
        .ddr_cas(ddr_cas), .ddr_we(ddr_we), .ddr_ck(ddr_ck), .ddr_ck_n(ddr_ck_n),
        .ddr_cke(ddr_cke), .ddr_odt(ddr_odt), .ddr_reset_n(ddr_reset_n),
        .ddr_dm(ddr_dm), .ddr_dq(ddr_dq), .ddr_dqs(ddr_dqs), .ddr_dqs_n(ddr_dqs_n)
    );
endmodule
