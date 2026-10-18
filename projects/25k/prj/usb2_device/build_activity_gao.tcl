# USB2 serial activity diagnostic image, separate GAO identity D2A8.
set project_dir [file dirname [file normalize [info script]]]
cd $project_dir
source prepare_activity_sources.tcl
set_device -name GW5A-25A GW5A-LV25MG121NC1/I0
set_option -top_module usb2_device_top
set_option -output_base_name usb2_serial_activity
set_option -synthesis_tool gowinsynthesis
set_option -verilog_std v2001
set_option -use_cpu_as_gpio 1
set_option -use_sspi_as_gpio 1
set_option -use_ready_as_gpio 1
set_option -use_done_as_gpio 1
set_option -use_jtag_as_gpio 0
set_option -bit_security 0
set_option -unused_pin default
set_option -gen_text_timing_rpt 1
set_option -gen_io_cst 1
set_option -cst_warn_to_error 1
set_option -timing_driven 1
add_file generated/usb2_activity_top.v
add_file rtl/usb2_serial_init.v
add_file rtl/usb2_cdc_loopback.v
add_file rtl/usb2_serial_activity.v
add_file generated/usb2_address_filter.v
add_file generated/usbfs_core_top.v
add_file generated/usb_serial_top.v
foreach source_file [glob ../vendor/fpga_usb_device/RTL/usbfs_core/*.v] {
    if {[file tail $source_file] ne "usbfs_core_top.v"} { add_file $source_file }
}
add_file debug/usb2_status_50mhz.v
add_file constraints/usb2_device.cst
add_file constraints/usb2_device.sdc
add_file debug/usb2_activity_status.gao
run all
