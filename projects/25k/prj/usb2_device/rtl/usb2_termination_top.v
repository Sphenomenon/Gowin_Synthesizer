`timescale 1ns/1ps
`default_nettype none
// ULPI-only four-phase termination diagnostic; no USB device protocol.
// USB3300 drives its 60 MHz clock into this input. No FPGA PLL drives this pin.
module usb2_device_top #(
    parameter [0:0] RXCMD_DIAG = 1'b0,
    parameter [0:0] PHY_SOFT_RESET = 1'b0,
    parameter [0:0] FULL_SCRATCH_TEST = 1'b0
) (
    input wire clk_50mhz,
    input wire clk_ulpi60,
    inout wire [7:0] ulpi_data,
    input wire ulpi_dir,
    input wire ulpi_nxt,
    output wire ulpi_stp,
    output wire led_ready,
    output wire led_done
);
    reg [12:0] powerup = 0;
    always @(posedge clk_50mhz)
        if (!powerup[12]) powerup <= powerup + 1'b1;
    (* ASYNC_REG = "TRUE" *) reg [2:0] reset_release = 0;
    always @(posedge clk_ulpi60) begin
        reset_release <= {reset_release[1:0], powerup[12]};
    end
    wire reset_n = reset_release[2];
    wire probe_done, id_ok, error;
    wire [3:0] error_code;
    wire [7:0] stage, func_ctrl, if_ctrl, otg_ctrl;
    wire [15:0] vendor_id, product_id, rxcmd_count, rxdata_count;
    wire [15:0] line_seen_masks, phase_last_status;
    wire [15:0] rxcmd_seen_masks;
    wire [31:0] phase_last_rxcmd;
    wire [8:0] scratch_verified_count;
    wire [7:0] scratch_mismatch_expected, scratch_mismatch_actual;
    wire [7:0] init_data_out;
    wire [7:0] init_data_in;
    wire init_data_oe;
    wire init_drive_ready;
    // Give the host time to debounce attachment and attempt bus reset before
    // finishing the sixteen samples; the short-window probe is preserved in
    // build_20261016_100552_875557 for comparison.
    usb2_termination_probe #(
        .SETTLE_CYCLES(6000000), .SAMPLE_GAP_CYCLES(600000),
        .PHY_SOFT_RESET(PHY_SOFT_RESET), .FULL_SCRATCH_TEST(FULL_SCRATCH_TEST)
    ) u_init (
        .clk_ulpi60(clk_ulpi60), .reset_n(reset_n),
        .ulpi_data_i(init_data_in), .ulpi_data_o(init_data_out),
        .ulpi_data_oe(init_data_oe),
        .ulpi_drive_ready(init_drive_ready),
        .ulpi_dir(ulpi_dir), .ulpi_nxt(ulpi_nxt), .ulpi_stp(ulpi_stp),
        .done(probe_done), .id_ok(id_ok), .error(error), .error_code(error_code),
        .stage(stage), .vendor_id(vendor_id), .product_id(product_id),
        .func_ctrl(func_ctrl), .if_ctrl(if_ctrl), .otg_ctrl(otg_ctrl),
        .line_seen_masks(line_seen_masks), .phase_last_status(phase_last_status),
        .rxcmd_seen_masks(rxcmd_seen_masks), .phase_last_rxcmd(phase_last_rxcmd),
        .scratch_verified_count(scratch_verified_count),
        .scratch_mismatch_expected(scratch_mismatch_expected),
        .scratch_mismatch_actual(scratch_mismatch_actual),
        .rxcmd_count(rxcmd_count), .rxdata_count(rxdata_count)
    );
    // A separate preserved enable LUT per pad avoids routing one enable
    // across all eight IOBs. OEN=DIR || !ready; raw DIR still releases every
    // pad immediately, and ready retains the master's turnaround guard.
    genvar pad;
    generate for (pad=0; pad<8; pad=pad+1) begin: pads
        wire output_disable;
        LUT2 #(.INIT(4'hb)) u_enable /* synthesis syn_dont_touch=1 */ (
            .I0(ulpi_dir), .I1(init_drive_ready), .F(output_disable)
        );
        IOBUF u_pad (
            .I(init_data_out[pad]), .O(init_data_in[pad]),
            .OEN(output_disable), .IO(ulpi_data[pad])
        );
    end endgenerate
    wire [3:0] flags = {probe_done, id_ok, 1'b0, error};
    wire [7:0] rxcmd_summary = rxcmd_count > 16'd255 ? 8'hff : rxcmd_count[7:0];
    wire [7:0] rxdata_summary = rxdata_count > 16'd255 ? 8'hff : rxdata_count[7:0];
    wire [31:0] page0 = FULL_SCRATCH_TEST ?
        {7'b0, scratch_verified_count, scratch_mismatch_expected, scratch_mismatch_actual} :
        RXCMD_DIAG ? phase_last_rxcmd : {vendor_id, product_id};
    wire [31:0] page3 = RXCMD_DIAG ?
        {rxcmd_seen_masks, rxcmd_summary, rxdata_summary} :
        {phase_last_status, rxcmd_summary, rxdata_summary};
    wire [127:0] live_snapshot = {
        page0, func_ctrl, if_ctrl, otg_ctrl,
        5'b0, ulpi_dir, ulpi_nxt, ulpi_stp,
        stage, error_code, flags, line_seen_masks,
        page3
    };
    wire [63:0] status_raw;
    wire [3:0] result_flags;
    wire clock_alive;
    usb2_status_50mhz u_observer (
        .clk_50mhz(clk_50mhz), .clk_ulpi60(clk_ulpi60),
        .live_snapshot(live_snapshot), .status_50mhz(status_raw),
        .result_flags(result_flags), .clock_alive(clock_alive)
    );
    reg [63:0] status_50mhz /* synthesis syn_preserve=1 syn_keep=1 */;
    always @(posedge clk_50mhz) status_50mhz <= status_raw;
    assign led_ready = clock_alive;
    assign led_done = result_flags[3] && result_flags[2] && !result_flags[0];
endmodule
`default_nettype wire
