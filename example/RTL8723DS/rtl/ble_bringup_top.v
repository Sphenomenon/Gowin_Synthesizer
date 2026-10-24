// Portable BLE board boundary reused from GW_25k; physical pins live in the 138K wrapper.
// UART names follow the MODULE viewpoint. No USB1/LCD pin is driven here.
module ble_bringup_top #(
    parameter CLK_HZ = 50000000,
    parameter DISABLE_MS = 200,
    parameter STARTUP_MS = 2000,
    parameter SESSION_MS = 180000,
    parameter NOTIFY_MS = 500,
    parameter PATCH_FILE = "vendor/rtl8723ds_ble/rtl8723ds_patch.mem"
) (
    input wire clk_50mhz,
    input wire restart_n,        // SW1_KEY / L10, pressed = low
    input wire module_uart_tx,   // U3 UART_OUT / J8, FPGA input
    input wire usb1_dp,          // L6: passive input only, pull disabled
    input wire usb1_dm,          // K6: passive input only, pull disabled
    inout wire module_uart_rx,   // U3 UART_IN / K9, FPGA TX
    inout wire module_bt_dis_n,  // U3 BT_DIS# / K8, low resets module
    output wire [767:0] debug_status,
    output wire board_resetn,
    output reg led_ready,
    output reg led_done
);
    // Gowin registers support bitstream initialization. Hold the driver in
    // reset for 1024 clocks after configuration, with its output OEs disabled.
    reg [10:0] powerup = 0;
    wire powerup_done = powerup[10];
    always @(posedge clk_50mhz)
        if (!powerup_done) powerup <= powerup + 1'b1;

    wire driver_resetn;
    ble_restart_filter #(.CLK_HZ(CLK_HZ)) restart_filter (
        .clk(clk_50mhz), .powerup_done(powerup_done),
        .restart_n(restart_n), .resetn(driver_resetn)
    );

    assign board_resetn = driver_resetn;
    wire tx, bt_enable, active, initialized, connected, subscribed, failed;
    // Preserve the portable driver's 24 status words for read-only JTAG/GAO
    // bring-up without allocating any further physical output pins.
    (* syn_keep = 1 *) wire [767:0] status;
    assign debug_status = status;
    rtl8723ds_ble #(
        .CLK_HZ(CLK_HZ), .DISABLE_MS(DISABLE_MS), .STARTUP_MS(STARTUP_MS),
        .SESSION_MS(SESSION_MS), .NOTIFY_MS(NOTIFY_MS), .PATCH_FILE(PATCH_FILE)
    ) driver (
        .clk(clk_50mhz), .resetn(driver_resetn), .enable(driver_resetn),
        .uart_rx(module_uart_tx), .uart_tx(tx), .bt_enable(bt_enable),
        .outputs_active(active), .initialized(initialized),
        .connected(connected), .subscribed(subscribed), .failed(failed),
        .debug(status)
    );

    // These are chip-level I/O boundaries. Reset independently gates OE;
    // the portable core's outputs_active alone is not reset-gated.
    wire drive_pins = driver_resetn && active;
    assign module_uart_rx = drive_pins ? tx : 1'bz;
    assign module_bt_dis_n = drive_pins ? bt_enable : 1'bz;

    // Keep USB1 truly passive: declare both pins as inputs and explicitly
    // disable pulls in CST instead of inheriting the unused-pin weak pull-up.
    (* syn_keep = 1 *) wire [1:0] usb1_line_state;
    (* syn_keep = 1 *) wire [31:0] usb1_transition_count;
    (* syn_keep = 1 *) wire usb1_activity_seen, usb1_se0_long;
    (* syn_keep = 1 *) wire usb1_se0_long_seen, usb1_se1_long_seen;
    usb1_passive_monitor #(.CLK_HZ(CLK_HZ)) usb1_monitor (
        .clk(clk_50mhz), .rst(!driver_resetn),
        .usb_dp(usb1_dp), .usb_dm(usb1_dm),
        .line_state(usb1_line_state), .transition_count(usb1_transition_count),
        .activity_seen(usb1_activity_seen), .se0_long(usb1_se0_long),
        .se0_long_seen(usb1_se0_long_seen), .se1_long_seen(usb1_se1_long_seen)
    );

    // Use the core's millisecond counter: no new clock domain is introduced.
    wire [31:0] uptime_ms = status[3*32 +: 32];
    wire ended = status[2*32 + 6];
    always @* begin
        led_ready = 1'b0;
        led_done = 1'b0;
        if (driver_resetn) begin
            if (failed) led_ready = uptime_ms[7];       // ~3.9 Hz failure
            else if (ended) led_ready = 1'b1;           // timed out, DONE off
            else led_ready = uptime_ms[9];             // ~1 Hz heartbeat
            if (!failed && !ended) begin
                if (subscribed) led_done = uptime_ms[7]; // fast: notifications
                else if (connected) led_done = uptime_ms[9]; // slow: connected
                else led_done = initialized;           // solid: advertising
            end
        end
    end
endmodule

// Synchronize the mechanical button, then require 20 ms of a stable level.
// A held button resets/stops the session; releasing starts a fresh session.
module ble_restart_filter #(
    parameter CLK_HZ = 50000000
) (
    input wire clk,
    input wire powerup_done,
    input wire restart_n,
    output wire resetn
);
    localparam MS_TICKS = CLK_HZ / 1000;
    (* ASYNC_REG = "TRUE" *) reg [1:0] restart_sync = 2'b11;
    reg [31:0] ms_div = 0;
    reg [4:0] stable_ms = 0;
    reg released = 1'b1;
    always @(posedge clk) begin
        restart_sync <= {restart_sync[0], restart_n};
        if (!powerup_done) begin
            ms_div <= 0;
            stable_ms <= 0;
            released <= 1'b1;
        end else if (ms_div == MS_TICKS - 1) begin
            ms_div <= 0;
            if (restart_sync[1] == released) stable_ms <= 0;
            else if (stable_ms == 19) begin
                released <= restart_sync[1];
                stable_ms <= 0;
            end else stable_ms <= stable_ms + 1'b1;
        end else ms_div <= ms_div + 1'b1;
    end
    assign resetn = powerup_done && released;
endmodule
