create_clock -name clk_ref -period 20.000 [get_ports {clk_50mhz}]
create_clock -name clk_a -period 81.380208 [get_ports {clk_12m288}]
create_clock -name clk_b -period 59.051398 [get_ports {clk_16m9344}]
# Source Gray buses are registered. Bound their first-stage arrival to less
# than the shortest source period; second stages retain setup/hold checks.
set_max_delay 40 -to [get_regs {meter/a_meta* meter/b_meta*}]
set_false_path -hold -to [get_regs {meter/a_meta* meter/b_meta*}]
set_false_path -from [get_ports {restart_n}]
