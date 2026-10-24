create_clock -name clk_50mhz -period 20.000 [get_ports {clk_50mhz}]
create_generated_clock -name pixel_clk -source [get_ports {clk_50mhz}] -multiply_by 63 -divide_by 100 [get_pins {clockgen/PLL_inst/CLKOUT0}]
create_generated_clock -name lcd_sample -source [get_pins {clockgen/PLL_inst/CLKOUT0}] -divide_by 1 -invert [get_ports {lcd_pclk}]
# Provisional 5 ns setup / 2 ns hold budget, not panel-datasheet signoff.
set_output_delay -clock lcd_sample -max 5.000 [get_ports {lcd_r[*] lcd_g[*] lcd_b[*] lcd_hsync lcd_vsync lcd_de}]
set_output_delay -clock lcd_sample -min -2.000 [get_ports {lcd_r[*] lcd_g[*] lcd_b[*] lcd_hsync lcd_vsync lcd_de}]
set_false_path -from [get_ports {restart_n}]
