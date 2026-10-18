#!/bin/sh
set -eu
task_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
sim_dir=$(mktemp -d "${TMPDIR:-/tmp}/usb2-measure-sim.XXXXXX")
trap 'rm -rf "$sim_dir"' EXIT HUP INT TERM
prim_sim=${GW25K_PRIM_SIM:-/Applications/GowinIDE.app/Contents/Resources/Gowin_EDA/IDE/simlib/gw5a/prim_sim.v}
iverilog -g2012 -s tb_usb2_measure -o "$sim_dir/measure.vvp" \
    "$prim_sim" "$task_dir/rtl/usb2_lowpower_diag.v" \
    "$task_dir/rtl/usb2_measure_top.v" \
    "$task_dir/sim/tb_usb2_measure.sv"
vvp "$sim_dir/measure.vvp"
