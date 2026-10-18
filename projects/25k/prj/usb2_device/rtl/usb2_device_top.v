`timescale 1ns/1ps
`default_nettype none
// First USB2 image: ULPI register self-test, independent board-clock telemetry.
// USB3300 drives its 60 MHz clock into this input. No FPGA PLL drives this pin.
module usb2_device_top (
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
    wire probe_done, id_ok, scratch_ok, error;
    wire [7:0] stage, func_ctrl, if_ctrl, otg_ctrl, last_read;
    wire [15:0] vendor_id, product_id, rxcmd_count, rxdata_count;
    usb2_ulpi_probe u_probe (
        .clk_ulpi60(clk_ulpi60), .reset_n(reset_n),
        .ulpi_data(ulpi_data), .ulpi_dir(ulpi_dir), .ulpi_nxt(ulpi_nxt),
        .ulpi_stp(ulpi_stp), .probe_done(probe_done), .id_ok(id_ok),
        .scratch_ok(scratch_ok), .error(error), .stage(stage),
        .vendor_id(vendor_id), .product_id(product_id),
        .func_ctrl(func_ctrl), .if_ctrl(if_ctrl), .otg_ctrl(otg_ctrl),
        .last_read(last_read), .rxcmd_count(rxcmd_count), .rxdata_count(rxdata_count)
    );
    wire [127:0] live_snapshot = {
        vendor_id, product_id, func_ctrl, if_ctrl, otg_ctrl, last_read,
        stage, 4'b0, probe_done, id_ok, scratch_ok, error, rxcmd_count,
        rxdata_count, ulpi_data, 5'b0, ulpi_dir, ulpi_nxt, ulpi_stp
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
    assign led_done = result_flags[3] && result_flags[2] && result_flags[1] && !result_flags[0];
endmodule
`default_nettype wire
