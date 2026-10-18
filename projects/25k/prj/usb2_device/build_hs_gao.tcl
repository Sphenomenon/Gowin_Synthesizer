# USB2 480Mbps ULPI CDC experiment; preserve previous FS/probe artifacts.
set project_dir [file dirname [file normalize [info script]]]
cd $project_dir
set_device -name GW5A-25A GW5A-LV25MG121NC1/I0
set_option -top_module usb2_device_top
set_option -output_base_name usb2_hs_cdc
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
exec python3 prepare_hs_sources.py
add_file hs/usb2_hs_top.v
add_file hs/usb2_hs_boot.v
add_file hs/usb2_hs_echo.v
add_file hs/usb_cdc_core.v
add_file hs/usb_desc_rom.v
foreach f [glob generated/hs_*.v] { add_file $f }
add_file debug/usb2_status_50mhz.v
add_file constraints/usb2_device.cst
add_file constraints/usb2_device.sdc
add_file debug/usb2_hs_status.gao
run all
