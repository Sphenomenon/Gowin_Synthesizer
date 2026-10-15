// 50 MHz GW5AST link adapter. All status/data stay in this clock domain.
module gw138k_ble_link #(
    parameter integer CLK_HZ = 50000000,
    parameter integer DISABLE_MS = 200,
    parameter integer STARTUP_MS = 2000,
    parameter integer SESSION_MS = 180000,
    parameter integer NOTIFY_MS = 500,
    parameter PATCH_FILE = "vendor/rtl8723ds_ble/rtl8723ds_patch.mem"
) (
    input wire clk, resetn, enable,
    input wire module_uart_tx,
    output wire module_uart_rx_value,
    output wire module_bt_dis_value,
    output wire outputs_active,
    output wire initialized, connected, subscribed, failed,
    output wire [767:0] debug
);
    wire core_active;
    rtl8723ds_ble #(
        .CLK_HZ(CLK_HZ), .DISABLE_MS(DISABLE_MS), .STARTUP_MS(STARTUP_MS),
        .SESSION_MS(SESSION_MS), .NOTIFY_MS(NOTIFY_MS), .PATCH_FILE(PATCH_FILE)
    ) u_driver (
        .clk(clk), .resetn(resetn), .enable(enable), .uart_rx(module_uart_tx),
        .uart_tx(module_uart_rx_value), .bt_enable(module_bt_dis_value),
        .outputs_active(core_active), .initialized(initialized),
        .connected(connected), .subscribed(subscribed), .failed(failed),
        .debug(debug)
    );
    // Immediate output release even before the synchronous core sees reset.
    assign outputs_active = resetn && enable && core_active;
endmodule
