create_clock -name clk_50mhz -period 20.000 [get_ports {clk_50mhz}]
create_clock -name clk_ulpi60 -period 16.666 [get_ports {clk_ulpi60}]
# USB3300 DS00001783C table 6-2: tDOUT 2..5ns, tDIN setup 5ns,
# hold 0ns. Budget 0.5ns for board clock/data skew in both directions.
set_input_delay -clock clk_ulpi60 -max 5.500 [get_ports {ulpi_data[*] ulpi_dir ulpi_nxt}]
set_input_delay -clock clk_ulpi60 -min 1.500 [get_ports {ulpi_data[*] ulpi_dir ulpi_nxt}]
set_output_delay -clock clk_ulpi60 -max 5.500 [get_ports {ulpi_data[*] ulpi_stp}]
set_output_delay -clock clk_ulpi60 -min -0.500 [get_ports {ulpi_data[*] ulpi_stp}]
# Only asynchronous first-stage D pins are exempt. The synchronizer chains,
# normal ULPI IO, OE paths and GAO logic remain timed.
set_false_path -from [get_clocks {clk_50mhz}] -to [get_pins {u_master/run_meta60_s0/D u_master/request_meta60_s0/D}]
set_false_path -from [get_clocks {clk_ulpi60}] -to [get_pins {ack_meta50_s0/D awake_meta50_s0/D}]
# Mailbox fields remain held until acknowledged. Bound the first-stage route
# within one destination period; later synchronizer/consumption stages are timed.
set_max_delay 15.000 -from [get_pins {request_write50_s0/Q request_addr50_*_s0/Q request_data50_*_s0/Q}] -to [get_pins {u_master/write_meta60_s0/D u_master/addr_meta60_*_s0/D u_master/data_meta60_*_s0/D}]
set_false_path -hold -from [get_clocks {clk_50mhz}] -to [get_pins {u_master/write_meta60_s0/D u_master/addr_meta60_*_s0/D u_master/data_meta60_*_s0/D}]
set_max_delay 18.000 -from [get_pins {u_master/response_error_s0/Q u_master/response_data_*_s0/Q}] -to [get_pins {error_meta50_s0/D response_meta50_*_s0/D}]
set_false_path -hold -from [get_clocks {clk_ulpi60}] -to [get_pins {error_meta50_s0/D response_meta50_*_s0/D}]
# DIR is independently synchronized for startup qualification in the 50MHz domain.
set_false_path -from [get_ports {ulpi_dir}] -to [get_pins {dir_meta50_s0/D}]
# Bound Gray routing below one source period so transitions cannot overtake.
# Only asynchronous capture hold is exempt, not meta -> sync paths.
set_max_delay 15.000 -from [get_pins {clock_gray60_*_s0/Q}] -to [get_pins {clock_gray_meta50_*_s0/D}]
set_false_path -hold -from [get_clocks {clk_ulpi60}] -to [get_pins {clock_gray_meta50_*_s0/D}]
# Async reset assertion is deliberate; deassertion is synchronized in clk60.
set_false_path -from [get_clocks {clk_50mhz}] -to [get_pins {reset_meta60_s0/CLEAR reset_sync60_s0/CLEAR}]
# These 50MHz controls assert wake or remove DATA drive on startup/failure.
# Normal master STP, DATA and output-enable paths retain the ULPI constraints.
set_false_path -from [get_pins {force_stp50_s0/Q powerup_12_s*/Q}] -to [get_ports {ulpi_stp}]
set_false_path -from [get_pins {run_request50_s0/Q powerup_12_s*/Q}] -to [get_ports {ulpi_data[*]}]
# GAO adds and constrains its dedicated TCK during post-synthesis insertion.
