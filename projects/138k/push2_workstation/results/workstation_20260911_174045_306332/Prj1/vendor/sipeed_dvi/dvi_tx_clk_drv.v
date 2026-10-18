module dvi_tx_clk_drv(
	
	input				pixel_clock,
	input				ddr_bit_clock,
	input				serializer_reset,
	output	[1 : 0]		tmds_clk
);
	
	wire tmds_clk_pre;
	// Match the same-board Gowin cam_dvi DVI_TX_Top.vo clock lane:
	// D0..D4=0, D5..D9=1. Its falling edge marks data bit D0.
	// CLKDIV /5 has a 60/40 duty cycle; forwarding it directly is unsuitable
	// for the TMDS reference. Serialize five low/five high unit intervals so
	// clock and data share their reset, word boundary and output pipeline.
	OSER10 tmds_serdes_inst0 (
		.Q(tmds_clk_pre),
		.D0(1'b0), .D1(1'b0), .D2(1'b0), .D3(1'b0), .D4(1'b0),
		.D5(1'b1), .D6(1'b1), .D7(1'b1), .D8(1'b1), .D9(1'b1),
		.PCLK(pixel_clock), .FCLK(ddr_bit_clock), .RESET(serializer_reset)
	);
	
	ELVDS_OBUF tmds_bufds_isnt0 (
		.I(tmds_clk_pre),
		.O(tmds_clk[1]),
		.OB(tmds_clk[0])
	);
	
endmodule
