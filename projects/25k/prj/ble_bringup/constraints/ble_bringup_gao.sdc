# Same user-clock constraints as the normal build, plus only the dedicated
# JTAG clock inserted by GAO. Keep the plain build's SDC unchanged.
create_clock -name clk_50mhz -period 20.000 -waveform {0.000 10.000} [get_ports {clk_50mhz}]
set_false_path -from [get_ports {module_uart_tx}]
set_false_path -from [get_ports {restart_n}]
set_false_path -from [get_ports {usb1_dp}]
set_false_path -from [get_ports {usb1_dm}]
# The previous generated GAO netlist contains top-level tck_pad_i, an IBUF,
# then GW_JTAG.tck_o. Constrain the actual input, not a guessed internal pin.
# 33.333 ns covers FT2232HL MPSSE TCK rates up to 30 MHz. Keep the selected
# capture cable at or below 30 MHz; review the actual PnR clock report.
create_clock -name gao_jtag_tck -period 33.333 -waveform {0.000 16.666} [get_ports {tck_pad_i}]
# Do not false-path the 50 MHz core or blanket-cut clock domains here.
# If GAO reports crossings, inspect their endpoints before adding exceptions.
