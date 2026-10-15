// Example chip-level integration. Supply a real 50 MHz clock and board reset.
// Replace pin constraints/clock generation with those for your board.
module rtl8723ds_ble_board_top (
    input wire clk_50mhz,
    input wire resetn,
    input wire enable, // synchronous to clk_50mhz
    input wire module_uart_tx,
    inout wire module_uart_rx,
    inout wire module_bt_dis,
    inout wire module_wl_dis,
    output wire initialized,
    output wire connected,
    output wire subscribed,
    output wire failed,
    output wire [767:0] debug
);
    wire tx, bt_enable, outputs_active;
    rtl8723ds_ble driver (
        .clk(clk_50mhz), .resetn(resetn), .enable(enable),
        .uart_rx(module_uart_tx), .uart_tx(tx), .bt_enable(bt_enable),
        .outputs_active(outputs_active), .initialized(initialized),
        .connected(connected), .subscribed(subscribed), .failed(failed),
        .debug(debug)
    );
    // Tri-states belong at chip I/O boundaries. FPGA tools infer I/O buffers.
    assign module_uart_rx = outputs_active ? tx : 1'bz;
    assign module_bt_dis = outputs_active ? bt_enable : 1'bz;
    assign module_wl_dis = outputs_active ? 1'b0 : 1'bz;
endmodule
