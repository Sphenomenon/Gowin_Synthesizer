#!/bin/sh
set -eu
task_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
sim_dir=$(mktemp -d "${TMPDIR:-/tmp}/usb2-termination-sim.XXXXXX")
trap 'rm -rf "$sim_dir"' EXIT HUP INT TERM
for phy_soft_reset in 0 1; do
for full_scratch_test in 0 1; do
iverilog -g2012 -Wall -s tb_usb2_termination_probe \
    -Ptb_usb2_termination_probe.PHY_SOFT_RESET="$phy_soft_reset" -o "$sim_dir/probe.vvp" \
    -Ptb_usb2_termination_probe.FULL_SCRATCH_TEST="$full_scratch_test" \
    "$task_dir/rtl/usb2_termination_probe.v" \
    "$task_dir/sim/tb_usb2_termination_probe.sv"
vvp "$sim_dir/probe.vvp"
done
done
prim_sim=${GW25K_PRIM_SIM:-/Applications/GowinIDE.app/Contents/Resources/Gowin_EDA/IDE/simlib/gw5a/prim_sim.v}
iverilog -g2012 -s tb_usb2_termination_pads -o "$sim_dir/pads.vvp" \
    "$prim_sim" "$task_dir/rtl/usb2_termination_probe.v" \
    "$task_dir/rtl/usb2_termination_top.v" \
    "$task_dir/debug/usb2_status_50mhz.v" \
    "$task_dir/sim/tb_usb2_termination_pads.sv"
vvp "$sim_dir/pads.vvp"
