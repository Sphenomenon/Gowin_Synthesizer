set project_dir [file dirname [file normalize [info script]]]
cd $project_dir
set_device -name GW5A-25A GW5A-LV25MG121NC1/I0
set_option -synthesis_tool gowinsynthesis
set_option -top_module lcd_bringup_top
set_option -output_base_name lcd_bringup
set_option -verilog_std v2001
set_option -use_cpu_as_gpio 1
set_option -use_sspi_as_gpio 1
set_option -use_jtag_as_gpio 0
# Local SRAM bring-up: allow Programmer readback/verify of this test image.
set_option -bit_security 0
set_option -unused_pin default
set_option -gen_text_timing_rpt 1
set_option -gen_io_cst 1
set_option -cst_warn_to_error 1
set_option -timing_driven 1
add_file src/lcd_spi_byte.v
add_file src/lcd_init_rom.v
add_file src/lcd_bringup_top.v
add_file src/lcd_bringup.cst
add_file src/lcd_bringup.sdc
run all
