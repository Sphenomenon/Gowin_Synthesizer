// Prj1 adaptation of the Sipeed/Gowin generated PLL wrapper.
// Kept separate from the first revision's 25 MHz VGA PLL.
// Two legal PLL stages produce an exact nominal 148.5/742.5 MHz from 50 MHz.
// Source attribution: docs/third_party_video.md. Limits: docs/video_1080p_notes.md.
`default_nettype none

module video_pll_1080p_gw5a #(
    // UG306 requires LOCK to remain asserted for at least 2 ms (50 MHz x 2 ms).
    parameter LOCK_STABLE_CYCLES = 100000
) (
    input wire clk_50m,
    input wire reset_n,
    output wire pixel_clk,
    output wire serial_clk,
    output wire serializer_reset_n,
    output wire serializer_reset,
    output wire locked
);
    wire reference_clk, reference_lock, tmds_lock;
    wire reference_ready, tmds_ready;
    // VCO = 50 * (24 + 6/8) = 1237.5 MHz; output = 49.5 MHz.
    video_pll_1080p_cell u_reference (
        .clkin(clk_50m), .init_clk(clk_50m), .reset(!reset_n),
        .enable0(1'b1), .lock(reference_lock),
        .clkout0(reference_clk), .clkout1()
    );
    video_pll_lock_filter #(.STABLE_CYCLES(LOCK_STABLE_CYCLES)) u_reference_filter (
        .clk(clk_50m), .reset_n(reset_n), .raw_lock(reference_lock),
        .stable_lock(reference_ready)
    );
    // VCO = 49.5 * 15 = 742.5 MHz. The pixel clock uses the dedicated HCLK
    // divider, preserving the OSER10 FCLK/PCLK phase relation (UG304/UG306).
    // PLL2 is held in reset until PLL1's output is stable, including after lock loss.
    video_pll_1080p_cell #(
        .INPUT_MHZ("49.5"), .MULTIPLY_INTEGER(15), .MULTIPLY_EIGHTHS(0),
        .OUTPUT_DIV0(1), .OUTPUT_DIV1(5), .OUTPUT1_ENABLE("FALSE")
    ) u_tmds (
        .clkin(reference_clk), .init_clk(clk_50m), .reset(!reset_n || !reference_ready),
        .enable0(locked), .lock(tmds_lock),
        .clkout0(serial_clk), .clkout1()
    );
    video_pll_lock_filter #(.STABLE_CYCLES(LOCK_STABLE_CYCLES)) u_tmds_filter (
        .clk(clk_50m), .reset_n(reset_n & reference_ready), .raw_lock(tmds_lock),
        .stable_lock(tmds_ready)
    );
    // Keep FCLK and PCLK stopped while releasing the serializer/divider reset.
    // UG306 ENCLK0 controls the dedicated PLL output gate, not a fabric AND.
    video_serializer_startup u_startup (
        .clk(clk_50m), .reset_n(reset_n), .qualified_lock(reference_ready & tmds_ready),
        .serializer_reset_n(serializer_reset_n), .serializer_reset(serializer_reset), .clock_enable(locked)
    );
    // Reset is released 80 ns before ENCLK0 enables the first serial edge.
    // Downstream logic remains reset for four complete pixel clock cycles.
    CLKDIV u_pixel_div (
        .HCLKIN(serial_clk), .RESETN(serializer_reset_n), .CALIB(1'b0), .CLKOUT(pixel_clk)
    );
    defparam u_pixel_div.DIV_MODE = "5";
endmodule

// A separate slow-clock startup sequence makes reset release safe for both
// OSER10 clock domains without routing 742.5 MHz into fabric flip-flops.
// Lock loss/reset asserts all resets and disables the output asynchronously;
// another complete PLL qualification interval precedes each restart.
module video_serializer_startup (
    input wire clk, reset_n, qualified_lock,
    output wire serializer_reset_n, clock_enable,
    (* syn_preserve=1, syn_keep=1 *) output reg serializer_reset = 1'b1
);
    wire startup_reset_n = reset_n & qualified_lock;
    (* syn_preserve=1, syn_keep=1 *) reg [4:0] startup_pipe = 5'b00000;
    always @(posedge clk or negedge startup_reset_n) begin
        if (!startup_reset_n) begin
            startup_pipe <= 5'b00000;
            serializer_reset <= 1'b1;
        end else begin
            startup_pipe <= {startup_pipe[3:0],1'b1};
            serializer_reset <= 1'b0;
        end
    end
    assign serializer_reset_n = startup_pipe[0];
    assign clock_enable = startup_pipe[4];
endmodule

// Asynchronous lock loss assertion; synchronized input and continuous qualification
// before reset release. A short lock glitch cannot release downstream logic.
module video_pll_lock_filter #(
    parameter STABLE_CYCLES = 100000
) (
    input wire clk,
    input wire reset_n,
    input wire raw_lock,
    output reg stable_lock
);
    localparam COUNTER_WIDTH = (STABLE_CYCLES < 2) ? 1 : $clog2(STABLE_CYCLES);
    localparam [COUNTER_WIDTH-1:0] LAST_COUNT = STABLE_CYCLES - 1;
    wire qualification_reset_n = reset_n & raw_lock;
    reg [1:0] lock_sync;
    reg [COUNTER_WIDTH-1:0] count;
    always @(posedge clk or negedge qualification_reset_n) begin
        if (!qualification_reset_n) begin
            lock_sync <= 0;
            count <= 0;
            stable_lock <= 0;
        end else begin
            lock_sync <= {lock_sync[0], 1'b1};
            if (!lock_sync[1]) count <= 0;
            else if (!stable_lock) begin
                if (count == LAST_COUNT) stable_lock <= 1;
                else count <= count + 1'b1;
            end
        end
    end
endmodule

//Copyright (C)2014-2024 Gowin Semiconductor Corporation.
//All rights reserved.
//File Title: IP file
//Tool Version: V1.9.9.01 (64-bit)
//Part Number: GW5AST-LV138PG484AC2/I1
//Device: GW5AST-138B
//Device Version: B
//Created Time: Tue Mar 12 14:17:48 2024

module video_pll_1080p_cell #(
    parameter INPUT_MHZ = "50",
    parameter MULTIPLY_INTEGER = 24,
    parameter MULTIPLY_EIGHTHS = 6,
    parameter OUTPUT_DIV0 = 25,
    parameter OUTPUT_DIV1 = 25,
    parameter OUTPUT1_ENABLE = "FALSE"
) (lock, clkout0, clkout1, clkin, reset, enable0, init_clk);

output wire lock;
output wire clkout0;
output wire clkout1;
input wire clkin;
input wire init_clk;
input wire reset;
input wire enable0;

// UG306 PLL_init uses its own stable 1--100 MHz initialization clock.
// Both cascade stages use board clk50 here, including the 49.5 MHz PLL input.
// MULTI_FAC selects only the <=16, <=34, >34 analog search tables. Integer
// 24 and fractional 24.75 select the same table; MDIV_FRAC below still sets 6/8.
// Keep PLL_inst at this hierarchy for existing clock and reset-path audits.
wire pll_raw_lock, pll_reset;
wire [5:0] pll_icpsel;
wire [2:0] pll_lpfres;
video_pll_init #(.CLK_PERIOD(20), .MULTI_FAC(MULTIPLY_INTEGER)) u_pll_init (
    .CLKIN(init_clk), .I_RST(reset), .PLLLOCK(pll_raw_lock),
    .O_RST(pll_reset), .ICPSEL(pll_icpsel), .LPFRES(pll_lpfres), .O_LOCK(lock)
);

wire clkout2;
wire clkout3;
wire clkout4;
wire clkout5;
wire clkout6;
wire clkfbout;
wire gw_vcc;
wire gw_gnd;

assign gw_vcc = 1'b1;
assign gw_gnd = 1'b0;

PLL PLL_inst (
    .LOCK(pll_raw_lock),
    .CLKOUT0(clkout0),
    .CLKOUT1(clkout1),
    .CLKOUT2(clkout2),
    .CLKOUT3(clkout3),
    .CLKOUT4(clkout4),
    .CLKOUT5(clkout5),
    .CLKOUT6(clkout6),
    .CLKFBOUT(clkfbout),
    .CLKIN(clkin),
    .CLKFB(gw_gnd),
    .RESET(pll_reset),
    .PLLPWD(gw_gnd),
    .RESET_I(gw_gnd),
    .RESET_O(gw_gnd),
    .FBDSEL({gw_gnd,gw_gnd,gw_gnd,gw_gnd,gw_gnd,gw_gnd}),
    .IDSEL({gw_gnd,gw_gnd,gw_gnd,gw_gnd,gw_gnd,gw_gnd}),
    .MDSEL({gw_gnd,gw_gnd,gw_gnd,gw_gnd,gw_gnd,gw_gnd,gw_gnd}),
    .MDSEL_FRAC({gw_gnd,gw_gnd,gw_gnd}),
    .ODSEL0({gw_gnd,gw_gnd,gw_gnd,gw_gnd,gw_gnd,gw_gnd,gw_gnd}),
    .ODSEL0_FRAC({gw_gnd,gw_gnd,gw_gnd}),
    .ODSEL1({gw_gnd,gw_gnd,gw_gnd,gw_gnd,gw_gnd,gw_gnd,gw_gnd}),
    .ODSEL2({gw_gnd,gw_gnd,gw_gnd,gw_gnd,gw_gnd,gw_gnd,gw_gnd}),
    .ODSEL3({gw_gnd,gw_gnd,gw_gnd,gw_gnd,gw_gnd,gw_gnd,gw_gnd}),
    .ODSEL4({gw_gnd,gw_gnd,gw_gnd,gw_gnd,gw_gnd,gw_gnd,gw_gnd}),
    .ODSEL5({gw_gnd,gw_gnd,gw_gnd,gw_gnd,gw_gnd,gw_gnd,gw_gnd}),
    .ODSEL6({gw_gnd,gw_gnd,gw_gnd,gw_gnd,gw_gnd,gw_gnd,gw_gnd}),
    .DT0({gw_gnd,gw_gnd,gw_gnd,gw_gnd}),
    .DT1({gw_gnd,gw_gnd,gw_gnd,gw_gnd}),
    .DT2({gw_gnd,gw_gnd,gw_gnd,gw_gnd}),
    .DT3({gw_gnd,gw_gnd,gw_gnd,gw_gnd}),
    .ICPSEL(pll_icpsel),
    .LPFRES(pll_lpfres),
    .LPFCAP({gw_gnd,gw_gnd}),
    .PSSEL({gw_gnd,gw_gnd,gw_gnd}),
    .PSDIR(gw_gnd),
    .PSPULSE(gw_gnd),
    .ENCLK0(enable0),
    .ENCLK1(gw_vcc),
    .ENCLK2(gw_vcc),
    .ENCLK3(gw_vcc),
    .ENCLK4(gw_vcc),
    .ENCLK5(gw_vcc),
    .ENCLK6(gw_vcc),
    .SSCPOL(gw_gnd),
    .SSCON(gw_gnd),
    .SSCMDSEL({gw_gnd,gw_gnd,gw_gnd,gw_gnd,gw_gnd,gw_gnd,gw_gnd}),
    .SSCMDSEL_FRAC({gw_gnd,gw_gnd,gw_gnd})
);

defparam PLL_inst.FCLKIN = INPUT_MHZ;
defparam PLL_inst.IDIV_SEL = 1;
defparam PLL_inst.FBDIV_SEL = 1;
defparam PLL_inst.ODIV0_SEL = OUTPUT_DIV0;
defparam PLL_inst.ODIV1_SEL = OUTPUT_DIV1;
defparam PLL_inst.ODIV2_SEL = 8;
defparam PLL_inst.ODIV3_SEL = 8;
defparam PLL_inst.ODIV4_SEL = 8;
defparam PLL_inst.ODIV5_SEL = 8;
defparam PLL_inst.ODIV6_SEL = 8;
defparam PLL_inst.MDIV_SEL = MULTIPLY_INTEGER;
defparam PLL_inst.MDIV_FRAC_SEL = MULTIPLY_EIGHTHS;
defparam PLL_inst.ODIV0_FRAC_SEL = 0;
defparam PLL_inst.CLKOUT0_EN = "TRUE";
defparam PLL_inst.CLKOUT1_EN = OUTPUT1_ENABLE;
defparam PLL_inst.CLKOUT2_EN = "FALSE";
defparam PLL_inst.CLKOUT3_EN = "FALSE";
defparam PLL_inst.CLKOUT4_EN = "FALSE";
defparam PLL_inst.CLKOUT5_EN = "FALSE";
defparam PLL_inst.CLKOUT6_EN = "FALSE";
defparam PLL_inst.CLKFB_SEL = "INTERNAL";
defparam PLL_inst.CLKOUT0_DT_DIR = 1'b1;
defparam PLL_inst.CLKOUT1_DT_DIR = 1'b1;
defparam PLL_inst.CLKOUT2_DT_DIR = 1'b1;
defparam PLL_inst.CLKOUT3_DT_DIR = 1'b1;
defparam PLL_inst.CLKOUT0_DT_STEP = 0;
defparam PLL_inst.CLKOUT1_DT_STEP = 0;
defparam PLL_inst.CLKOUT2_DT_STEP = 0;
defparam PLL_inst.CLKOUT3_DT_STEP = 0;
defparam PLL_inst.CLK0_IN_SEL = 1'b0;
defparam PLL_inst.CLK0_OUT_SEL = 1'b0;
defparam PLL_inst.CLK1_IN_SEL = 1'b0;
defparam PLL_inst.CLK1_OUT_SEL = 1'b0;
defparam PLL_inst.CLK2_IN_SEL = 1'b0;
defparam PLL_inst.CLK2_OUT_SEL = 1'b0;
defparam PLL_inst.CLK3_IN_SEL = 1'b0;
defparam PLL_inst.CLK3_OUT_SEL = 1'b0;
defparam PLL_inst.CLK4_IN_SEL = 2'b00;
defparam PLL_inst.CLK4_OUT_SEL = 1'b0;
defparam PLL_inst.CLK5_IN_SEL = 1'b0;
defparam PLL_inst.CLK5_OUT_SEL = 1'b0;
defparam PLL_inst.CLK6_IN_SEL = 1'b0;
defparam PLL_inst.CLK6_OUT_SEL = 1'b0;
defparam PLL_inst.DYN_DPA_EN = "FALSE";
defparam PLL_inst.CLKOUT0_PE_COARSE = 0;
defparam PLL_inst.CLKOUT0_PE_FINE = 0;
defparam PLL_inst.CLKOUT1_PE_COARSE = 0;
defparam PLL_inst.CLKOUT1_PE_FINE = 0;
defparam PLL_inst.CLKOUT2_PE_COARSE = 0;
defparam PLL_inst.CLKOUT2_PE_FINE = 0;
defparam PLL_inst.CLKOUT3_PE_COARSE = 0;
defparam PLL_inst.CLKOUT3_PE_FINE = 0;
defparam PLL_inst.CLKOUT4_PE_COARSE = 0;
defparam PLL_inst.CLKOUT4_PE_FINE = 0;
defparam PLL_inst.CLKOUT5_PE_COARSE = 0;
defparam PLL_inst.CLKOUT5_PE_FINE = 0;
defparam PLL_inst.CLKOUT6_PE_COARSE = 0;
defparam PLL_inst.CLKOUT6_PE_FINE = 0;
defparam PLL_inst.DYN_PE0_SEL = "FALSE";
defparam PLL_inst.DYN_PE1_SEL = "FALSE";
defparam PLL_inst.DYN_PE2_SEL = "FALSE";
defparam PLL_inst.DYN_PE3_SEL = "FALSE";
defparam PLL_inst.DYN_PE4_SEL = "FALSE";
defparam PLL_inst.DYN_PE5_SEL = "FALSE";
defparam PLL_inst.DYN_PE6_SEL = "FALSE";
defparam PLL_inst.DE0_EN = "FALSE";
defparam PLL_inst.DE1_EN = "FALSE";
defparam PLL_inst.DE2_EN = "FALSE";
defparam PLL_inst.DE3_EN = "FALSE";
defparam PLL_inst.DE4_EN = "FALSE";
defparam PLL_inst.DE5_EN = "FALSE";
defparam PLL_inst.DE6_EN = "FALSE";
defparam PLL_inst.RESET_I_EN = "FALSE";
defparam PLL_inst.RESET_O_EN = "FALSE";
defparam PLL_inst.ICP_SEL = 6'bXXXXXX;
defparam PLL_inst.LPF_RES = 3'bXXX;
defparam PLL_inst.LPF_CAP = 2'b00;
defparam PLL_inst.SSC_EN = "FALSE";
defparam PLL_inst.DYN_IDIV_SEL = "FALSE";
defparam PLL_inst.DYN_FBDIV_SEL = "FALSE";
defparam PLL_inst.DYN_MDIV_SEL = "FALSE";
defparam PLL_inst.DYN_ODIV0_SEL = "FALSE";
defparam PLL_inst.DYN_ODIV1_SEL = "FALSE";
defparam PLL_inst.DYN_ODIV2_SEL = "FALSE";
defparam PLL_inst.DYN_ODIV3_SEL = "FALSE";
defparam PLL_inst.DYN_ODIV4_SEL = "FALSE";
defparam PLL_inst.DYN_ODIV5_SEL = "FALSE";
defparam PLL_inst.DYN_ODIV6_SEL = "FALSE";
defparam PLL_inst.DYN_DT0_SEL = "FALSE";
defparam PLL_inst.DYN_DT1_SEL = "FALSE";
defparam PLL_inst.DYN_DT2_SEL = "FALSE";
defparam PLL_inst.DYN_DT3_SEL = "FALSE";
defparam PLL_inst.DYN_ICP_SEL = "TRUE";
defparam PLL_inst.DYN_LPF_SEL = "TRUE";

endmodule //video_pll_1080p_cell

`default_nettype wire
