# Run: gw_sh scripts/build.tcl . Default all; env PRJ1_FLOW=syn limits to synthesis.
set root [file normalize [file join [file dirname [info script]] ..]]
cd $root
open_project [file join $root Prj1.gprj]
set_option -top_module gw138k_push_workstation_top
set_option -output_base_name Prj1
set_option -verilog_std sysv2017
set_option -use_sspi_as_gpio 1
set_option -use_mspi_as_gpio 1
set_option -use_cpu_as_gpio 1
set_option -timing_driven 1
set_option -correct_hold_violation 1
# Explicit timing-priority placement (IDE rtlplaceoptions.xml algorithm 2).
# Keep PLL_INIT's independent 10ns routed propagation audit unchanged.
set_option -place_option 2
# SUG100: search for better routing even if it takes longer to compile.
set_option -route_option 1
set_option -gen_text_timing_rpt 1
set_option -gen_sdf 1
set_option -gen_verilog_sim_netlist 1
set flow all
if {[info exists ::env(PRJ1_FLOW)]} { set flow $::env(PRJ1_FLOW) }
if {$flow ni {syn pnr all}} { error "PRJ1_FLOW must be syn, pnr or all" }
run $flow
