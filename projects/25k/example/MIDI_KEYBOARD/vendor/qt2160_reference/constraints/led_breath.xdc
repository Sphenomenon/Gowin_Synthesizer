# Board IO names and BANK 34 VCCO = 3.3 V confirmed by the user.
# Package coordinates verified against the Vivado device database.
# M19 = IO_L13P_T2_MRCC_34: single-ended 50 MHz active oscillator.
set_property -dict {PACKAGE_PIN M19 IOSTANDARD LVCMOS33} [get_ports clk]
create_clock -name sys_clk -period 20.000 -waveform {0.000 10.000} [get_ports clk]

# P20/P21 are used as TWO INDEPENDENT single-ended active-high LED outputs.
# They are not a differential output in this design.
# P20 = IO_L18P_T2_34; P21 = IO_L18N_T2_34.
set_property -dict {PACKAGE_PIN P20 IOSTANDARD LVCMOS33 DRIVE 8 SLEW SLOW} [get_ports led1]
set_property -dict {PACKAGE_PIN P21 IOSTANDARD LVCMOS33 DRIVE 8 SLEW SLOW} [get_ports led2]

# LEDs have no receiving clock or synchronous output timing requirement.
set_false_path -to [get_ports {led1 led2}]
