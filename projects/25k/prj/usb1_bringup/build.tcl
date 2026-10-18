set script_dir [file dirname [file normalize [info script]]]
cd $script_dir
set_device -name GW5A-25A GW5A-LV25MG121NC1/I0
add_file -type verilog rtl/usb1_passive_monitor.v
add_file -type verilog rtl/usb1_monitor_top.v
add_file -type cst usb1_monitor.cst
add_file -type sdc usb1_monitor.sdc
set_option -top_module usb1_monitor_top
set_option -output_base_name usb1_monitor
set_option -synthesis_tool gowinsynthesis
set_option -verilog_std v2001
# E2 is a CPU/SSPI multiplexed pin on this part.
set_option -use_cpu_as_gpio 1
set_option -use_sspi_as_gpio 1
set_option -use_i2c_as_gpio 1
set_option -use_jtag_as_gpio 0
run all
