create_clock -name clk_50mhz -period 20.000 [get_ports {clk_50mhz}]
create_clock -name clk_ulpi60 -period 16.666 [get_ports {clk_ulpi60}]
# USB3300 table 6-2 plus 0.5 ns board skew budget.
set_input_delay -clock clk_ulpi60 -max 5.500 [get_ports {ulpi_data[*] ulpi_dir ulpi_nxt}]
set_input_delay -clock clk_ulpi60 -min 1.500 [get_ports {ulpi_data[*] ulpi_dir ulpi_nxt}]
set_output_delay -clock clk_ulpi60 -max 5.500 [get_ports {ulpi_data[*] ulpi_stp}]
set_output_delay -clock clk_ulpi60 -min -0.500 [get_ports {ulpi_data[*] ulpi_stp}]

# Gowin hierarchical pin separator is '/'. Synthesis renames instances whose
# names collide with port/net names, e.g. usb -> usb_33, touch -> touch_33,
# ble -> ble_33. Retain those hierarchy prefixes with a suffix wildcard.
# Four FIFOs have 64 Gray first-stage D pins (2*(7+7+9+9)).
# Bound pointer routing below the fastest source period; only first-stage
# HOLD capture is exempt. Do not false-path setup or either synchronizer's
# first-to-second-stage path, and do not use blanket asynchronous clock groups.
set_max_delay 15.000 -from [get_clocks {clk_50mhz clk_ulpi60}] -to [get_pins {usb*/bridge/*/rd_gray_w1_*_s0/D usb*/bridge/*/wr_gray_r1_*_s0/D}]
set_false_path -hold -from [get_clocks {clk_50mhz clk_ulpi60}] -to [get_pins {usb*/bridge/*/rd_gray_w1_*_s0/D usb*/bridge/*/wr_gray_r1_*_s0/D}]
# hs_active is unused at the board boundary; hs_sync is optimized away.

# Mechanical contacts: exempt only their dedicated first sampling register.
set_false_path -from [get_ports {sw1_a}] -to [get_pins {e1/ab_meta_1_s0/D}]
set_false_path -from [get_ports {sw1_b}] -to [get_pins {e1/ab_meta_0_s0/D}]
set_false_path -from [get_ports {sw1_key_n}] -to [get_pins {e1/key_meta_s0/D}]
set_false_path -from [get_ports {sw2_a}] -to [get_pins {e2/ab_meta_1_s0/D}]
set_false_path -from [get_ports {sw2_b}] -to [get_pins {e2/ab_meta_0_s0/D}]
set_false_path -from [get_ports {sw2_key_n}] -to [get_pins {e2/key_meta_s0/D}]
# UART and shared QT2160 CHANGE also enter a two-flop synchronizer.
set_false_path -from [get_ports {module_uart_tx}] -to [get_pins {ble*/transport/uart/rx_sync_0_s0/D}]
set_false_path -from [get_ports {touch_change_n}] -to [get_pins {touch*/change_meta_s0/D}]
# Open-drain bus observation includes external ACK/data and SCL stretching.
# Preserve timing from meta to sync and throughout each register-bus engine.
set_false_path -from [get_ports {touch1_scl}] -to [get_pins {touch*/keypad/bus/scl_meta_s0/D}]
set_false_path -from [get_ports {touch1_sda}] -to [get_pins {touch*/keypad/bus/sda_meta_s0/D}]
set_false_path -from [get_ports {touch2_scl}] -to [get_pins {touch*/slider/bus/scl_meta_s0/D}]
set_false_path -from [get_ports {touch2_sda}] -to [get_pins {touch*/slider/bus/sda_meta_s0/D}]
set_false_path -from [get_ports {pca_scl}] -to [get_pins {lamps*/bus/scl_meta_s0/D}]
set_false_path -from [get_ports {pca_sda}] -to [get_pins {lamps*/bus/sda_meta_s0/D}]
# LCD TE is intentionally unused by the snapshot display; no TE path exists.
