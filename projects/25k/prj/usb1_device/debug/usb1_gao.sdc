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
