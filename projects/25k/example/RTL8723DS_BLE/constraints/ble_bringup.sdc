create_clock -name clk_50mhz -period 20.000 -waveform {0.000 10.000} [get_ports {clk_50mhz}]
# UART and button enter two-flop synchronizers. Cut only the external paths;
# do not false-path the synchronizer's first-to-second stage.
set_false_path -from [get_ports {module_uart_tx}]
set_false_path -from [get_ports {restart_n}]
set_false_path -from [get_ports {usb1_dp}]
set_false_path -from [get_ports {usb1_dm}]
