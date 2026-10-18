# E2 is the unchanged 50 MHz board oscillator (the package pin is in the CST).
create_clock -name clk_50mhz -period 20.000 -waveform {0.000 10.000} [get_ports {clk_50mhz}]
# PLLA: 50 MHz / IDIV(1) * FBDIV(1) * MDIV(24) / ODIV0(20).
create_generated_clock -name clk_usb60 -source [get_ports {clk_50mhz}] -multiply_by 6 -divide_by 5 [get_pins {u_clock/u_pll/CLKOUT0}]
# Only the asynchronous reset synchronizer's CLEAR inputs are exempt from
# hold/removal against the 50 MHz helper LOCK. Three DFFCE stages (D=1 then
# Q->D->D) synchronize release; raw LOCK still asserts reset asynchronously.
# Preserve recovery, inter-stage timing and all downstream reset checks.
# SUG940-2.0.4E section 5.4.1: -hold covers hold AND removal analysis.
set_false_path -hold -from [get_pins {u_clock/u_pll_init/rLockOut_s0/Q}] -to [get_pins {u_clock/reset_release_0_s0/CLEAR u_clock/reset_release_1_s0/CLEAR u_clock/reset_release_2_s0/CLEAR}]
# No clock-group exemptions or invented USB output delays.

# Merged after the normal 50/60 MHz SDC: Gowin enables one SDC at a time.
# Post-synthesis GAO inserts this GW_JTAG. Its tck_o clocks the analyzer's
# control registers; dedicated JTAG pads are not normal top-level ports.
# The selector must resolve and the final timing report must show this clock.
# Post-synthesis GAO injects its TCK clock after user SDC processing. The
# verified report supplies tck_pad_i, 50 ns / 20 MHz, object tck_ibuf/I.
# Its generated objects cannot be targeted by a user create_clock here.
# FT2CH programmer choices in this installation top out at 15 MHz.
# Stable USB-domain flags are deliberately sampled through two 50 MHz FFs.
# Exempt only their first sampling stage, retaining meta->sync and all GAO
# control/data clock crossings for timing review.
set_false_path -from [get_clocks {clk_usb60}] -to [get_pins {u_status_observer/flags_meta_*_s0/D}]
# No CDC clock groups/false paths are added. Review any 50/60/TCK crossing
# endpoints, including tool-generated GAO logic, rather than hiding violations.
