`timescale 1ns/1ps
`default_nettype none
module midi_usb1_clock (
    input wire clk_50m,
    output wire clk_48m, locked_o, reset_n_o
);
    wire lock_raw, lock_ready, pll_reset, md_increment;
    wire [1:0] md_operation;
    wire [7:0] md_write, md_read;
    PLL_INIT #(.CLK_PERIOD(20), .MULTI_FAC(24)) init (
        .I_RST(1'b0), .I_MD_CLK(clk_50m), .O_RST(pll_reset),
        .O_MD_INC(md_increment), .O_MD_OPC(md_operation), .O_MD_WR_DATA(md_write),
        .I_MD_RD_DATA(md_read), .I_LOCK(lock_raw), .O_LOCK(lock_ready),
        .PLL_INIT_BYPASS(1'b0), .MDRDO(), .MDOPC(2'b00), .MDAINC(1'b0), .MDWDI(8'd0)
    );
    PLLA #(
        .FCLKIN("50"), .IDIV_SEL(1), .FBDIV_SEL(1), .CLKFB_SEL("INTERNAL"),
        .MDIV_SEL(24), .MDIV_FRAC_SEL(0), .ODIV0_SEL(25), .ODIV0_FRAC_SEL(0),
        .CLKOUT0_EN("TRUE"), .CLKOUT1_EN("FALSE"), .CLKOUT2_EN("FALSE"),
        .CLKOUT3_EN("FALSE"), .CLKOUT4_EN("FALSE"), .CLKOUT5_EN("FALSE"), .CLKOUT6_EN("FALSE"),
        .CLK0_IN_SEL(1'b0), .CLK0_OUT_SEL(1'b0), .CLKOUT0_DT_DIR(1'b1),
        .CLKOUT0_DT_STEP(0), .CLKOUT0_PE_COARSE(0), .CLKOUT0_PE_FINE(0),
        .DE0_EN("FALSE"), .DYN_DPA_EN("FALSE"), .DYN_PE0_SEL("FALSE"),
        .RESET_I_EN("FALSE"), .RESET_O_EN("FALSE"),
        .ICP_SEL(6'bXXXXXX), .LPF_RES(3'bXXX), .LPF_CAP(2'b00), .SSC_EN("FALSE")
    ) pll (
        .CLKIN(clk_50m), .CLKFB(1'b0), .CLKOUT0(clk_48m),
        .CLKOUT1(), .CLKOUT2(), .CLKOUT3(), .CLKOUT4(), .CLKOUT5(), .CLKOUT6(), .CLKFBOUT(),
        .LOCK(lock_raw), .MDRDO(md_read), .RESET(pll_reset), .PLLPWD(1'b0),
        .RESET_I(1'b0), .RESET_O(1'b0), .PSSEL(3'd0), .PSDIR(1'b0), .PSPULSE(1'b0),
        .SSCPOL(1'b0), .SSCON(1'b0), .SSCMDSEL(7'd0), .SSCMDSEL_FRAC(3'd0),
        .MDCLK(clk_50m), .MDOPC(md_operation), .MDAINC(md_increment), .MDWDI(md_write)
    );
    assign locked_o = lock_raw && lock_ready;
    (* ASYNC_REG="TRUE", syn_preserve=1 *) reg [2:0] release_q = 0;
    always @(posedge clk_48m or negedge locked_o)
        if (!locked_o) release_q <= 0;
        else release_q <= {release_q[1:0], 1'b1};
    assign reset_n_o = release_q[2];
endmodule
`default_nettype wire
