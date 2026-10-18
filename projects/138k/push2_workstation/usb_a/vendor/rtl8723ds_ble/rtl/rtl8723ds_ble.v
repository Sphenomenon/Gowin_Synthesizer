// Portable RTL8723DS ROM-v2 BLE wrapper. No PS, debug IP or I/O primitives.
// enable must be synchronous to clk. resetn may assert asynchronously;
// its release is synchronized below. Apply outputs_active to board I/O OEs.
module rtl8723ds_ble #(
    parameter CLK_HZ = 50000000,
    parameter DISABLE_MS = 200,
    parameter STARTUP_MS = 2000,
    parameter SESSION_MS = 180000,
    parameter NOTIFY_MS = 500,
    parameter PATCH_FILE = "rtl8723ds_patch.mem"
) (
    input wire clk,
    input wire resetn,
    input wire enable,
    input wire uart_rx,
    output wire uart_tx,
    output wire bt_enable,
    output wire outputs_active,
    output wire initialized,
    output wire connected,
    output wire subscribed,
    output wire failed,
    output wire [767:0] debug
);
    wire core_resetn;
    reset_release_sync reset_sync (
        .clk(clk), .arstn(resetn), .resetn(core_resetn)
    );
    // The HCI baud command and supplied controller config both select 115200.
    // PATCH_BYTES and BAUD are intentionally fixed to the validated image.
    bt_verilog_core #(
        .CLK_HZ(CLK_HZ), .BAUD(115200),
        .DISABLE_MS(DISABLE_MS), .STARTUP_MS(STARTUP_MS),
        .SESSION_MS(SESSION_MS), .NOTIFY_MS(NOTIFY_MS),
        .PATCH_BYTES(30147), .PATCH_FILE(PATCH_FILE)
    ) core (
        .clk(clk), .resetn(core_resetn), .enable(enable), .uart_rx(uart_rx),
        .uart_tx(uart_tx), .bt_enable(bt_enable), .outputs_active(outputs_active),
        .initialized(initialized), .connected(connected),
        .subscribed(subscribed), .failed(failed), .debug(debug)
    );
endmodule
