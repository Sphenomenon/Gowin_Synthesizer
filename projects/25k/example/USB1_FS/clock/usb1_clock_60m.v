// GW5A-25A USB full-speed clock: 50 MHz -> 60 MHz, integer PLLA dividers.
// UG306-1.0.7E, section 5.2. Includes the installed official PLL_INIT helper.
module usb1_clock_60m (
    input  wire clk_50mhz,
    output wire clk_usb60,
    output wire pll_locked,
    output wire reset_60mhz_n
);
    wire pll_lock_raw;
    wire pll_lock_ready;
    wire pll_reset;
    wire md_inc;
    wire [1:0] md_opc;
    wire [7:0] md_write;
    wire [7:0] md_read;

    // The helper calibrates the PLL through mDRP even for a fixed frequency.
    // Both its initialization clock and the PLL reference are the board's 50 MHz.
    PLL_INIT #(.CLK_PERIOD(20), .MULTI_FAC(24)) u_pll_init (
        .I_RST(1'b0),
        .I_MD_CLK(clk_50mhz),
        .O_RST(pll_reset),
        .O_MD_INC(md_inc),
        .O_MD_OPC(md_opc),
        .O_MD_WR_DATA(md_write),
        .I_MD_RD_DATA(md_read),
        .I_LOCK(pll_lock_raw),
        .O_LOCK(pll_lock_ready),
        .PLL_INIT_BYPASS(1'b0),
        .MDRDO(),
        .MDOPC(2'b00),
        .MDAINC(1'b0),
        .MDWDI(8'h00)
    );

    PLLA #(
        .FCLKIN("50"),
        .IDIV_SEL(1),
        .FBDIV_SEL(1),
        .CLKFB_SEL("INTERNAL"),
        .MDIV_SEL(24),
        .MDIV_FRAC_SEL(0),
        .ODIV0_SEL(20),
        .ODIV0_FRAC_SEL(0),
        .CLKOUT0_EN("TRUE"),
        .CLKOUT1_EN("FALSE"),
        .CLKOUT2_EN("FALSE"),
        .CLKOUT3_EN("FALSE"),
        .CLKOUT4_EN("FALSE"),
        .CLKOUT5_EN("FALSE"),
        .CLKOUT6_EN("FALSE"),
        .CLK0_IN_SEL(1'b0),
        .CLK0_OUT_SEL(1'b0),
        .CLKOUT0_DT_DIR(1'b1),
        .CLKOUT0_DT_STEP(0),
        .CLKOUT0_PE_COARSE(0),
        .CLKOUT0_PE_FINE(0),
        .DE0_EN("FALSE"),
        .DYN_DPA_EN("FALSE"),
        .DYN_PE0_SEL("FALSE"),
        .RESET_I_EN("FALSE"),
        .RESET_O_EN("FALSE"),
        .ICP_SEL(6'bXXXXXX),
        .LPF_RES(3'bXXX),
        .LPF_CAP(2'b00),
        .SSC_EN("FALSE")
    ) u_pll (
        .CLKIN(clk_50mhz),
        .CLKFB(1'b0),
        .CLKOUT0(clk_usb60),
        .CLKOUT1(), .CLKOUT2(), .CLKOUT3(),
        .CLKOUT4(), .CLKOUT5(), .CLKOUT6(), .CLKFBOUT(),
        .LOCK(pll_lock_raw),
        .MDRDO(md_read),
        .RESET(pll_reset),
        .PLLPWD(1'b0),
        .RESET_I(1'b0),
        .RESET_O(1'b0),
        .PSSEL(3'b000),
        .PSDIR(1'b0),
        .PSPULSE(1'b0),
        .SSCPOL(1'b0),
        .SSCON(1'b0),
        .SSCMDSEL(7'b0000000),
        .SSCMDSEL_FRAC(3'b000),
        .MDCLK(clk_50mhz),
        .MDOPC(md_opc),
        .MDAINC(md_inc),
        .MDWDI(md_write)
    );

    // Use raw LOCK as well as the qualified helper result so loss of lock
    // asserts reset without waiting for the helper's 50 MHz state machine.
    assign pll_locked = pll_lock_raw & pll_lock_ready;

    // Assertion is asynchronous; release requires three rising 60 MHz edges.
    (* syn_preserve = 1 *) reg [2:0] reset_release = 3'b000;
    always @(posedge clk_usb60 or negedge pll_locked) begin
        if (!pll_locked)
            reset_release <= 3'b000;
        else
            reset_release <= {reset_release[1:0], 1'b1};
    end
    assign reset_60mhz_n = reset_release[2];
endmodule
