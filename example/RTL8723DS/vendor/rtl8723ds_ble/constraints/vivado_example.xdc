# For examples/rtl8723ds_ble_board_top.v with an actual 50 MHz clock.
# Add PACKAGE_PIN and IOSTANDARD constraints for your board separately.
create_clock -period 20.000 -name driver_clk [get_ports clk_50mhz]
# Cut only asynchronous UART input to synchronizer stage 0.
set_false_path -from [get_ports module_uart_tx] -to [get_cells -hier -regexp {.*rx_sync_reg\[0\]}]
# Do not false-path stage 0 -> stage 1; both must remain ASYNC_REG and timed.
