create_clock -name clk_50m -period 20.000 [get_ports {clk}]
# Asynchronous external bus inputs end at the first synchronizer registers.
set_false_path -from [get_ports {usb_dp usb_dm}]
