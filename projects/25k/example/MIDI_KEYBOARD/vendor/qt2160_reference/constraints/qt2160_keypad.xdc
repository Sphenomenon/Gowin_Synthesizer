# Second QT2160, 2x8 independent keys, external pull-ups required.
set_property -dict {PACKAGE_PIN AA17 IOSTANDARD LVCMOS33 PULLUP TRUE DRIVE 8 SLEW SLOW} [get_ports keypad_scl]
set_property -dict {PACKAGE_PIN AB17 IOSTANDARD LVCMOS33 PULLUP TRUE DRIVE 8 SLEW SLOW} [get_ports keypad_sda]
set_false_path -from [get_ports {keypad_scl keypad_sda}]
set_false_path -to [get_ports {keypad_scl keypad_sda}]
