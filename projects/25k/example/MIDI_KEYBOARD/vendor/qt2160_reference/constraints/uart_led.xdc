# PL UART, 3.3 V TTL, 115200 8N1. RX is asynchronous to the 50 MHz clock.
# Schematic pages 3 and 7: CH340 TXD -> M17, CH340 RXD <- L17.
# M17 = IO_L4N_T0_34 (FPGA RX); L17 = IO_L4P_T0_34 (FPGA TX).
# Independent single-ended signals, not a differential pair.
set_property -dict {PACKAGE_PIN M17 IOSTANDARD LVCMOS33 PULLUP TRUE} [get_ports uart_rx_pin]
set_property -dict {PACKAGE_PIN L17 IOSTANDARD LVCMOS33 DRIVE 8 SLEW SLOW} [get_ports uart_tx_pin]
# Only the asynchronous input path is excluded; the synchronizer's internal
# register-to-register path remains timed by the 50 MHz clock.
set_false_path -from [get_ports uart_rx_pin]
set_false_path -to [get_ports uart_tx_pin]
