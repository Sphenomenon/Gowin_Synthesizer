create_clock -name clk_50mhz -period 20.000 [get_ports {clk_50mhz}]
create_clock -name clk_12m288 -period 81.380208 [get_ports {clk_12m288}]
# Registered Gray counters enter two-stage synchronizers. Limit propagation
# to the FIRST stage to less than one 12.288 MHz period. Clocks are unrelated;
# a synchronous hold relationship does not apply to these first-stage inputs.
# Second-stage and all subsequent paths retain normal setup/hold analysis.
set_max_delay 70 -to [get_regs {cg1* fg1* pins1*}]
set_false_path -hold -to [get_regs {cg1* fg1* pins1*}]
set_false_path -from [get_ports {restart_n plug_det}]
# ADCLRC ready and held result are asynchronous to 50MHz. Cut only their
# first receiver stage; result is used after synchronized ready completion.
set_false_path -to [get_regs {power/ready_meta* power/value_meta*}]
