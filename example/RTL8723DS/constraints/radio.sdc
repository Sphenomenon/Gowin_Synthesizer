create_clock -name clk_50mhz -period 20.000 -waveform {0.000 10.000} [get_ports {clk_50mhz}]
# External inputs enter two-register synchronizers. Cut only port-to-first
# stage paths; never cut first-to-second or subsequent internal logic paths.
set_false_path -from [get_ports {module_uart_tx restart_n}]
set_false_path -from [get_ports {wifi_sd_cmd wifi_sd_dat[*]}]
# Native SDIO input is oversampled at 50MHz and consumed at 250kHz rising
# card ticks, after a full falling-to-rising half period. No multicycle paths.
