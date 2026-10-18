set_property -dict {PACKAGE_PIN Y16 IOSTANDARD LVCMOS33 PULLUP TRUE DRIVE 8 SLEW SLOW} [get_ports touch_scl]
set_property -dict {PACKAGE_PIN AA14 IOSTANDARD LVCMOS33 PULLUP TRUE DRIVE 8 SLEW SLOW} [get_ports touch_sda]
set_property -dict {PACKAGE_PIN V15 IOSTANDARD LVCMOS33 PULLUP TRUE} [get_ports touch_change_n]
# Only asynchronous pads and first synchronizer stages are excluded.
set_false_path -from [get_ports {touch_scl touch_sda touch_change_n}]
set_false_path -to [get_ports {touch_scl touch_sda}]
