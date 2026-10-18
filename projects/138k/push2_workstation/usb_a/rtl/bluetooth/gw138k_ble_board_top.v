// NEO Dock-138K 31005 / GW5AST-LV138PG484AC2/I1 independent BLE candidate.
// button1_n restarts the finite 180 s session; upstream tested timing retained.
module gw138k_ble_board_top #(
    parameter integer CLK_HZ = 50000000,
    parameter integer DISABLE_MS = 200,
    parameter integer STARTUP_MS = 2000,
    parameter integer SESSION_MS = 180000,
    parameter integer NOTIFY_MS = 500,
    parameter integer REPORT_MS = 1000,
    parameter PATCH_FILE = "vendor/rtl8723ds_ble/rtl8723ds_patch.mem"
) (
    input wire clk_50m, button1_n,
    input wire ble_module_uart_tx,
    inout wire ble_module_uart_rx, ble_module_bt_dis, ble_module_wl_dis,
    output wire debug_uart_tx
);
    wire tx_value, bt_value, active;
    wire [767:0] debug;
    gw138k_ble_link #(
        .CLK_HZ(CLK_HZ), .DISABLE_MS(DISABLE_MS), .STARTUP_MS(STARTUP_MS),
        .SESSION_MS(SESSION_MS), .NOTIFY_MS(NOTIFY_MS), .PATCH_FILE(PATCH_FILE)
    ) u_ble (
        .clk(clk_50m), .resetn(button1_n), .enable(1'b1),
        .module_uart_tx(ble_module_uart_tx), .module_uart_rx_value(tx_value),
        .module_bt_dis_value(bt_value), .outputs_active(active),
        .initialized(), .connected(), .subscribed(), .failed(), .debug(debug)
    );
    assign ble_module_uart_rx = active ? tx_value : 1'bz;
    assign ble_module_bt_dis = active ? bt_value : 1'bz;
    assign ble_module_wl_dis = active ? 1'b0 : 1'bz;
    gw138k_ble_status_uart #(.CLK_HZ(CLK_HZ), .REPORT_MS(REPORT_MS)) u_status (
        .clk(clk_50m), .resetn(button1_n), .debug(debug), .serial_out(debug_uart_tx)
    );
endmodule
