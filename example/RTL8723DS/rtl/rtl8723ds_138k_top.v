// GW5AST-LV138PG484AC2/I1 custom expansion board, 50MHz V22.
// UART names are MODULE viewpoint: W12 receives, T14 transmits.
module rtl8723ds_138k_top #(
    parameter integer CLK_HZ=50000000,
    parameter integer SD_HZ=250000,
    parameter integer WIFI_POWER_MS=200
)(
    input wire clk_50mhz, restart_n, module_uart_tx,
    inout wire module_uart_rx, module_bt_dis_n,
    output wire module_wl_dis_n,
    output wire wifi_sd_clk,
    inout wire wifi_sd_cmd,
    input wire [3:0] wifi_sd_dat,
    output wire debug_uart_tx
);
    // Keep diagnostics alive even while the user holds the radio in reset.
    reg [10:0] status_por = 0;
    reg [31:0] heartbeat = 0;
    (* ASYNC_REG = "TRUE" *) reg [1:0] reset_sync = 2'b11;
    (* ASYNC_REG = "TRUE" *) reg [1:0] rx_sync = 2'b11, cmd_sync = 2'b11;
    reg rx_previous = 1'b1;
    reg [15:0] rx_edges = 0;
    reg [15:0] raw_bytes = 0;
    reg [7:0] raw_errors = 0, raw_last = 0;
    wire raw_valid, raw_error;
    wire [7:0] raw_data;
    // Independent 8E1 receiver includes early module boot traffic.
    bt_uart #(.CLK_HZ(CLK_HZ),.BAUD(115200)) raw_uart (
        .clk(clk_50mhz),.resetn(status_por[10]),.enable(1'b1),
        .rx(module_uart_tx),.tx(),.tx_data(8'd0),.tx_valid(1'b0),
        .tx_ready(),.tx_done(),.rx_data(raw_data),.rx_valid(raw_valid),.rx_error(raw_error));
    always @(posedge clk_50mhz) begin
        if (!status_por[10]) status_por <= status_por + 1'b1;
        heartbeat <= heartbeat + 1'b1;
        reset_sync <= {reset_sync[0], restart_n};
        rx_sync <= {rx_sync[0], module_uart_tx};
        cmd_sync <= {cmd_sync[0], wifi_sd_cmd};
        rx_previous <= rx_sync[1];
        if (rx_previous && !rx_sync[1] && rx_edges != 16'hffff) rx_edges <= rx_edges + 1'b1;
        if (raw_valid) begin
            raw_last <= raw_data;
            if (raw_bytes != 16'hffff) raw_bytes <= raw_bytes + 1'b1;
        end
        if (raw_error && raw_errors != 8'hff) raw_errors <= raw_errors + 1'b1;
    end
    wire [767:0] ble_status;
    wire [255:0] wifi_status;
    wire board_resetn;
    ble_bringup_top #(.CLK_HZ(CLK_HZ),.SESSION_MS(0)) ble (
        .clk_50mhz(clk_50mhz),.restart_n(restart_n),.module_uart_tx(module_uart_tx),
        .module_uart_rx(module_uart_rx),.module_bt_dis_n(module_bt_dis_n),
        .usb1_dp(1'b1),.usb1_dm(1'b1),.led_ready(),.led_done(),
        .debug_status(ble_status),.board_resetn(board_resetn));
    sdio_identify #(.CLK_HZ(CLK_HZ),.SD_HZ(SD_HZ),.POWER_MS(WIFI_POWER_MS)) wifi (
        .clk(clk_50mhz),.resetn(board_resetn),.sd_clk(wifi_sd_clk),.sd_cmd(wifi_sd_cmd),
        .sd_dat(wifi_sd_dat),.wl_enable(module_wl_dis_n),
        .done(),.identified(),.failed(),.debug(wifi_status));
    // GAO words 32/33 add raw line activity independent of BLE parsing.
    (* syn_keep = 1, syn_preserve = 1 *) reg [1087:0] radio_debug;
    always @(posedge clk_50mhz) radio_debug <= {{raw_bytes,raw_errors,raw_last},
                          {rx_edges,heartbeat[11:4],4'b0000,cmd_sync[1],rx_sync[1],reset_sync[1],board_resetn},
                          wifi_status, ble_status};
    radio_status_uart #(.CLK_HZ(CLK_HZ)) status_uart (
        .clk(clk_50mhz),.resetn(status_por[10]),.debug({wifi_status,ble_status}),
        .serial_out(debug_uart_tx));
endmodule
