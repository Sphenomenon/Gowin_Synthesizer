create_clock -name clk_50m -period 20.000 -waveform {0.000 10.000} [get_ports {clk}]
// Encoder contacts are asynchronous. Each passes through a dedicated two-flop
// synchronizer before filtering; the second stage remains normally timed.
set_false_path -from [get_ports {sw1_a}] -to [get_pins {enc1/ab_meta_1_s0/D}]
set_false_path -from [get_ports {sw1_b}] -to [get_pins {enc1/ab_meta_0_s0/D}]
set_false_path -from [get_ports {sw1_key_n}] -to [get_pins {enc1/key_meta_s0/D}]
set_false_path -from [get_ports {sw2_a}] -to [get_pins {enc2/ab_meta_1_s0/D}]
set_false_path -from [get_ports {sw2_b}] -to [get_pins {enc2/ab_meta_0_s0/D}]
set_false_path -from [get_ports {sw2_key_n}] -to [get_pins {enc2/key_meta_s0/D}]
// LCD SPI uses registered outputs, 1 MHz mode 0 as verified on this board.
// No panel AC/PCB limits are available to specify external output delays.
