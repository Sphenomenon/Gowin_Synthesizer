create_clock -name clk50 -period 20.000 [get_ports {clk_50m}]
# Only asynchronous pin -> first synchronizer stage. Stage 0 -> 1 is timed.
set_false_path -from [get_ports {ble_module_uart_tx}] -to [get_pins {u_ble/u_driver/core/transport/uart/rx_sync_0_s1/D}]
# External reset assertion is asynchronous; both reset-release stages survive.
set_false_path -from [get_ports {button1_n}]
# External module UART and status UART are asynchronous serial outputs.
set_false_path -to [get_ports {ble_module_uart_rx ble_module_bt_dis ble_module_wl_dis debug_uart_tx}]
