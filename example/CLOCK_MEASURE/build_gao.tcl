set project_dir [file dirname [file normalize [info script]]]
cd $project_dir
set_device -name GW5AST-138C GW5AST-LV138PG484AC2/I1
set_option -top_module clock_measure_top
set_option -output_base_name freq138k
set_option -synthesis_tool gowinsynthesis
set_option -verilog_std v2001
set_option -opt_goal area
set_option -bit_security 0
set_option -user_code 13802420
set_option -use_jtag_as_gpio 0
set_option -use_cpu_as_gpio 1
set_option -use_sspi_as_gpio 1
set_option -use_mspi_as_gpio 1
set_option -unused_pin default
set_option -gen_text_timing_rpt 1
set_option -gen_io_cst 1
set_option -cst_warn_to_error 1
set_option -timing_driven 1
set_option -correct_hold_violation 1
set_option -place_option 2
set_option -route_option 1
foreach source_file [glob rtl/*.v] { add_file $source_file }
add_file constraints/clocks.cst
add_file constraints/clocks.sdc
add_file debug/frequency.gao
run all
