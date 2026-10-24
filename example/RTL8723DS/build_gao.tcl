set project_dir [file dirname [file normalize [info script]]]
cd $project_dir
source prepare_sources.tcl
set_device -name GW5AST-138C GW5AST-LV138PG484AC2/I1
set_option -top_module rtl8723ds_138k_top
set_option -output_base_name radio138k
set_option -synthesis_tool gowinsynthesis
set_option -verilog_std v2001
set_option -opt_goal area
set_option -map_option 2
set_option -bit_security 0
set_option -user_code 13802301
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
foreach source_file [glob vendor/rtl8723ds_ble/rtl/*.v] {
    if {[file tail $source_file] in {bt_h5_transport.v bt_gatt.v bt_verilog_core.v}} {
        add_file [file join generated rtl [file tail $source_file]]
    } else { add_file $source_file }
}
add_file $generated_top
foreach source_file [glob rtl/*.v] {
    if {[file tail $source_file] ne "ble_bringup_top.v"} { add_file $source_file }
}
add_file constraints/radio.cst
add_file constraints/radio.sdc
add_file debug/radio.gao
run all
