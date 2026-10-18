# USB1 full-speed CDC SRAM experiment. Use build.sh to build.
set project_dir [file dirname [file normalize [info script]]]
cd $project_dir
source prepare_sources.tcl
set_device -name GW5A-25A GW5A-LV25MG121NC1/I0
set_option -top_module usb1_device_top
set_option -output_base_name usb1_cdc
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
foreach source_file [glob clock/*.v rtl/*.v] {
    add_file $source_file
}
foreach source_file [glob vendor/fpga_usb_device/RTL/usbfs_core/*.v] {
    if {[file tail $source_file] eq "usbfs_core_top.v"} {
        add_file generated/usbfs_core_top.v
    } else {
        add_file $source_file
    }
}
add_file vendor/fpga_usb_device/RTL/usb_class/usb_serial_top.v
add_file constraints/usb1_device.cst
add_file clock/usb1_clock.sdc
run all
