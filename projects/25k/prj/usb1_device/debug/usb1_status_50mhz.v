`timescale 1ns/1ps
`default_nettype none
// Optional observation only. All counters and GAO data use the board clock,
// so loss of PLL output does not stop USB-line/lock diagnostics.
module usb1_status_50mhz (
    input wire clk_50mhz,
    input wire usb_dp,
    input wire usb_dm,
    input wire [6:0] stable_flags_async,
    output wire [63:0] status_50mhz
);
    // Input flag order: lock, reset60n, USB bus reset released, attach intent,
    // overflow sticky, received sticky, source heartbeat. No one-cycle pulse
    // or multi-bit 60 MHz counter crosses into this observer.
    (* ASYNC_REG = "TRUE" *) reg [6:0] flags_meta = 0;
    (* ASYNC_REG = "TRUE" *) reg [6:0] flags_sync = 0;
    (* ASYNC_REG = "TRUE" *) reg [1:0] line_meta = 0;
    (* ASYNC_REG = "TRUE" *) reg [1:0] line_sync = 0;
    reg [2:0] settle = 0;
    reg [25:0] heartbeat = 0;
    reg [1:0] previous_line = 0;
    reg [15:0] transitions = 0;
    reg [15:0] se0_streak = 0;
    reg [15:0] j_streak = 0;
    reg [7:0] se1_streak = 0;
    reg activity_seen = 0;
    reg se0_long_seen = 0;
    reg se1_long_seen = 0;
    reg j_long_seen = 0;
    wire settled = &settle;

    always @(posedge clk_50mhz) begin
        flags_meta <= stable_flags_async;
        flags_sync <= flags_meta;
        line_meta <= {usb_dp, usb_dm};
        line_sync <= line_meta;
        heartbeat <= heartbeat + 1'b1;
        if (!settled) begin
            settle <= settle + 1'b1;
            previous_line <= line_sync;
        end else begin
            previous_line <= line_sync;
            if (line_sync != previous_line) begin
                activity_seen <= 1'b1;
                if (transitions != 16'hffff) transitions <= transitions + 1'b1;
            end
            if (line_sync == 2'b00) begin
                if (se0_streak != 16'hffff) se0_streak <= se0_streak + 1'b1;
                if (se0_streak >= 16'd149) se0_long_seen <= 1'b1;
            end else se0_streak <= 0;
            if (line_sync == 2'b10) begin
                if (j_streak != 16'hffff) j_streak <= j_streak + 1'b1;
                if (j_streak >= 16'd149) j_long_seen <= 1'b1;
            end else j_streak <= 0;
            if (line_sync == 2'b11) begin
                if (se1_streak != 8'hff) se1_streak <= se1_streak + 1'b1;
                if (se1_streak >= 8'd149) se1_long_seen <= 1'b1;
            end else se1_streak <= 0;
        end
    end

    // 63:48 transitions; 47:32 consecutive SE0 cycles; 31:16 consecutive J;
    // 15 lock,14 reset60n,13 bus-reset released,12 attach intent,11:10 DP/DM;
    // 9 overflow sticky,8 received sticky,7 HB50,6 HB60,5 line activity;
    // 4 long SE0,3 long SE1,2 monitor settled,1 long J,0 reserved.
    assign status_50mhz = {
        transitions, se0_streak, j_streak,
        flags_sync[6:3], line_sync, flags_sync[2:1], heartbeat[25],
        flags_sync[0], activity_seen, se0_long_seen, se1_long_seen,
        settled, j_long_seen, heartbeat[0]
    };
endmodule
`default_nettype wire
