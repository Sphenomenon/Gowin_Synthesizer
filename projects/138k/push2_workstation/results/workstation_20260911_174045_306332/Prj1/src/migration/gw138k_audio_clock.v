// 138K migration candidate: 50 MHz -> 76.8 MHz -> 48 kHz at 1600 clocks/frame.
// Clock limits: UG306-1.0.9 pp.34-36,40-42,49-51; DS1239-1.0.3 p.43.
// PLL cell adapted from Prj1/vendor/sipeed_dvi/video_pll_1080p_gw5a.v.
// The original generated B-version header below records provenance only; the
// migration project target is GW5AST-LV138PG484AC2/I1, device GW5AST-138C.
// Uses Prj1/vendor/sipeed_dvi/video_pll_init.v unchanged.
`timescale 1ns/1fs
`default_nettype none

module gw138k_audio_clock #(
    parameter SIMULATION = 0,
    parameter LOCK_STABLE_CYCLES = 100000
) (
    input wire clk_50m,
    input wire reset_n,
    output wire audio_clk,
    output wire audio_reset_n,
    output wire pll_locked
);
    wire raw_lock;
    // Start this independent PLL helper after a short local initialization
    // interval. Its enable/reset state remains distinct from the video PLL
    // helper, permitting each routed control cone to be audited separately.
    reg [5:0] init_count = 0;
    always @(posedge clk_50m or negedge reset_n)
        if (!reset_n) init_count <= 0;
        else if (!init_count[5]) init_count <= init_count + 1'b1;
    wire init_ready = reset_n & init_count[5];
    generate
        if (SIMULATION) begin : g_simulation
            // Ideal frequency/reset model only. It does not model analog PLL
            // acquisition, fractional-divider jitter or a missing reference.
            reg model_clk = 1'b0;
            reg [3:0] model_lock_pipe = 4'b0000;
            always #(1000.0/153.6) model_clk = ~model_clk;
            always @(posedge clk_50m or negedge init_ready) begin
                if (!init_ready) model_lock_pipe <= 4'b0000;
                else model_lock_pipe <= {model_lock_pipe[2:0],1'b1};
            end
            assign audio_clk = model_clk;
            assign raw_lock = model_lock_pipe[3];
        end else begin : g_hardware
            // PFD=50 MHz; VCO=50*24=1200 MHz; ODIV0=15+5/8.
            // No dependency on DDR calibration, video lock or UI progress.
            gw138k_audio_pll_cell u_pll (
                .clkin(clk_50m), .init_clk(clk_50m), .reset(!init_ready),
                .enable0(1'b1), .lock(raw_lock),
                .clkout0(audio_clk), .clkout1()
            );
        end
    endgenerate

    // Same continuous-lock qualification rule as the existing video platform.
    // Any raw lock loss asserts reset immediately; re-entry requires >=2 ms.
    localparam COUNTER_WIDTH = (LOCK_STABLE_CYCLES < 2) ? 1 : $clog2(LOCK_STABLE_CYCLES);
    localparam [COUNTER_WIDTH-1:0] LAST_COUNT = LOCK_STABLE_CYCLES - 1;
    wire qualification_reset_n = reset_n & raw_lock;
    (* syn_preserve=1 *) reg [1:0] lock_sync = 2'b00;
    reg [COUNTER_WIDTH-1:0] lock_count = 0;
    reg stable_lock = 1'b0;
    always @(posedge clk_50m or negedge qualification_reset_n) begin
        if (!qualification_reset_n) begin
            lock_sync <= 0;
            lock_count <= 0;
            stable_lock <= 0;
        end else begin
            lock_sync <= {lock_sync[0],1'b1};
            if (!lock_sync[1]) lock_count <= 0;
            else if (!stable_lock) begin
                if (lock_count == LAST_COUNT) stable_lock <= 1;
                else lock_count <= lock_count + 1'b1;
            end
        end
    end
    assign pll_locked = stable_lock;

    wire audio_ready = reset_n & stable_lock;
    (* syn_preserve=1 *) reg [3:0] audio_reset_pipe = 4'b0000;
    always @(posedge audio_clk or negedge audio_ready) begin
        if (!audio_ready) audio_reset_pipe <= 4'b0000;
        else audio_reset_pipe <= {audio_reset_pipe[2:0],1'b1};
    end
    assign audio_reset_n = audio_reset_pipe[3];
endmodule

//Copyright (C)2014-2024 Gowin Semiconductor Corporation.
//All rights reserved.
//File Title: IP file
//Tool Version: V1.9.9.01 (64-bit)
//Part Number: GW5AST-LV138PG484AC2/I1
//Device: GW5AST-138B
//Device Version: B
//Created Time: Tue Mar 12 14:17:48 2024

module gw138k_audio_pll_cell #(
    parameter INPUT_MHZ = "50",
    parameter MULTIPLY_INTEGER = 24,
    parameter MULTIPLY_EIGHTHS = 0,
    parameter OUTPUT_DIV0 = 15,
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
// This audio PLL uses the independent board clk50 initialization reference.
// MULTI_FAC selects only the <=16, <=34, >34 analog search tables. Integer
// MDIV=24 uses the <=34 table. ODIV0=15+5/8 produces nominal 76.8 MHz.
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
defparam PLL_inst.ODIV0_FRAC_SEL = 5;
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

endmodule //gw138k_audio_pll_cell


`default_nettype wire
