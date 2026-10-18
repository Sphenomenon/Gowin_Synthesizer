create_clock -name clk_50mhz -period 20.000 [get_ports {clk_50mhz}]
create_clock -name clk_ulpi60 -period 16.666 [get_ports {clk_ulpi60}]
# USB3300 DS00001783C table 6-2: tDOUT 2..5ns, tDIN setup 5ns,
# hold 0ns. Budget 0.5ns for board clock/data skew, both directions.
set_input_delay -clock clk_ulpi60 -max 5.500 [get_ports {ulpi_data[*] ulpi_dir ulpi_nxt}]
set_input_delay -clock clk_ulpi60 -min 1.500 [get_ports {ulpi_data[*] ulpi_dir ulpi_nxt}]
set_output_delay -clock clk_ulpi60 -max 5.500 [get_ports {ulpi_data[*] ulpi_stp}]
set_output_delay -clock clk_ulpi60 -min -0.500 [get_ports {ulpi_data[*] ulpi_stp}]
# Exempt only asynchronous first sampling stages. All synchronizer chains,
# ULPI datapaths, board-clock logic and analyzer crossings remain timed.
set_false_path -from [get_clocks {clk_50mhz}] -to [get_pins {reset_release_0_s0/D u_observer/request_meta_s0/D}]
set_false_path -from [get_clocks {clk_ulpi60}] -to [get_pins {u_observer/ack_meta_s0/D}]
# Bound Gray routing below one source period so consecutive Gray transitions
# cannot overtake each other. This is an asynchronous data capture; only hold
# is exempted at its first stage, not its inter-stage synchronizer paths.
set_max_delay 15.000 -from [get_pins {u_observer/ulpi_gray_*_s0/Q}] -to [get_pins {u_observer/gray_meta_*_s0/D}]
set_false_path -hold -from [get_clocks {clk_ulpi60}] -to [get_pins {u_observer/gray_meta_*_s0/D}]
# The mailbox source is held stable until the destination has acknowledged
# capture. Data has 3 destination settling cycles after the source latch.
set_max_delay 40.000 -from [get_pins {u_observer/snapshot_hold_*_s0/Q}] -to [get_pins {u_observer/snapshot_50_*_s0/D}]
set_false_path -hold -from [get_pins {u_observer/snapshot_hold_*_s0/Q}] -to [get_pins {u_observer/snapshot_50_*_s0/D}]
# GAO inserts and constrains its dedicated TCK during post-synthesis insertion.
