`timescale 1ns/1ps
`default_nettype none
// Independent 50 MHz observer stays operational while USB3300 stops CLKOUT.
module usb2_device_top #(
    parameter [7:0] FS_OTG_CTRL = 8'h00
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
    wire reset_n = powerup[12];
    wire done, error, id_ok, clock_alive, clock_stop_seen;
    wire [3:0] errorcode;
    wire [7:0] stage, fc, if_ctrl, otg;
    wire [15:0] vid, pid, direct_masks, phase_flags;
    wire [7:0] direct_last;
    wire [31:0] sample_counts;
    wire [7:0] data_out, data_in;
    wire drive_ready;
    usb2_lowpower_diag #(.FS_OTG_CTRL(FS_OTG_CTRL)) u_diag (
        .clk50(clk_50mhz), .clk60(clk_ulpi60), .reset_n(reset_n),
        .data_i(data_in), .data_o(data_out), .drive_ready(drive_ready),
        .dir(ulpi_dir), .nxt(ulpi_nxt), .stp(ulpi_stp),
        .done(done), .error(error), .errorcode(errorcode), .stage(stage),
        .id_ok(id_ok), .vid(vid), .pid(pid), .fc(fc), .if_ctrl(if_ctrl), .otg(otg),
        .direct_masks(direct_masks), .direct_last(direct_last),
        .phase_flags(phase_flags), .sample_counts(sample_counts),
        .clock_alive(clock_alive), .clock_stop_seen(clock_stop_seen)
    );
    genvar pad;
    generate for (pad=0; pad<8; pad=pad+1) begin: pads
        wire output_disable;
        LUT2 #(.INIT(4'hb)) u_enable /* synthesis syn_dont_touch=1 */ (
            .I0(ulpi_dir), .I1(drive_ready), .F(output_disable)
        );
        IOBUF u_pad (
            .I(data_out[pad]), .O(data_in[pad]),
            .OEN(output_disable), .IO(ulpi_data[pad])
        );
    end endgenerate

    // All diagnostic outputs are in the 50 MHz domain. Unlike the other USB2
    // images, this capture never waits for a mailbox response from CLKOUT.
    wire [127:0] live_pages = {
        vid, pid, fc, if_ctrl, otg, errorcode, 4'b0,
        direct_masks, phase_flags, sample_counts
    };
    reg [127:0] pages_hold = 0;
    reg [7:0] stage_hold = 0;
    reg [4:0] flags_hold = 0;
    reg [4:0] page_phase = 0;
    reg heartbeat = 0;
    always @(posedge clk_50mhz) begin
        page_phase <= page_phase + 1'b1;
        heartbeat <= ~heartbeat;
        if (page_phase == 5'd31) begin
            pages_hold <= live_pages;
            stage_hold <= stage;
            flags_hold <= {clock_stop_seen, done, id_ok, error, clock_alive};
        end
    end
    wire [31:0] payload = page_phase[4:3] == 0 ? pages_hold[127:96] :
                          page_phase[4:3] == 1 ? pages_hold[95:64] :
                          page_phase[4:3] == 2 ? pages_hold[63:32] : pages_hold[31:0];
    wire [63:0] status_raw = {payload, 16'b0, stage_hold, flags_hold,
                             page_phase[4:3], heartbeat};
    reg [63:0] status_50mhz /* synthesis syn_preserve=1 syn_keep=1 */;
    always @(posedge clk_50mhz) status_50mhz <= status_raw;
    assign led_ready = clock_alive;
    assign led_done = done && id_ok && !error;
endmodule
`default_nettype wire
