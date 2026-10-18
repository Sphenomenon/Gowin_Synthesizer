# Run with Gowin gw_sh; this script changes into its own directory so the
# bitstream ROM path and all project source paths are reproducible.
set project_dir [file dirname [file normalize [info script]]]
cd $project_dir
source prepare_sources.tcl
set_device -name GW5A-25A GW5A-LV25MG121NC1/I0
set_option -top_module ble_bringup_top
set_option -output_base_name ble_bringup
set_option -synthesis_tool gowinsynthesis
set_option -verilog_std v2001
set_option -opt_goal area
set_option -map_option 2
# Debug image: allow temporary SRAM Program+Verify readback.
set_option -bit_security 0
set_option -use_jtag_as_gpio 0
# E2 is shared with dedicated CPU/SSPI functions on this part. The official
# Primer-25K examples enable both reuse options for the external clock pin.
set_option -use_cpu_as_gpio 1
set_option -use_sspi_as_gpio 1
# SUG1220-2.0E, section 3.3.20, printed pages 46/47 (PDF pages 53/54).
set_option -use_ready_as_gpio 1
set_option -use_done_as_gpio 1
# This GW5A part rejects the RECONFIG_N option; leave its default role.
# Undeclared USB/LCD/other I/O remain inputs with the tool's weak pull-up.
set_option -unused_pin default
set_option -gen_text_timing_rpt 1
set_option -gen_io_cst 1
set_option -cst_warn_to_error 1
set_option -timing_driven 1
foreach source_file [glob ../vendor/rtl8723ds_ble/rtl/*.v] {
    if {[file tail $source_file] in {bt_h5_transport.v bt_gatt.v}} {
        add_file [file join generated rtl [file tail $source_file]]
    } else {
        add_file $source_file
    }
}
add_file $generated_top
add_file ../usb1_bringup/rtl/usb1_passive_monitor.v
add_file constraints/ble_bringup.cst
add_file constraints/ble_bringup.sdc
run all
