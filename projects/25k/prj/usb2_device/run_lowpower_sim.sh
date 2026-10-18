#!/bin/sh
set -eu
task_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
sim_dir=$(mktemp -d "${TMPDIR:-/tmp}/usb2-lowpower-sim.XXXXXX")
trap 'rm -rf "$sim_dir"' EXIT HUP INT TERM
for fs_otg_ctrl in 0 4; do
iverilog -g2012 -Wall -s tb_usb2_lowpower_diag \
    -Ptb_usb2_lowpower_diag.FS_OTG_CTRL="$fs_otg_ctrl" -o "$sim_dir/lowpower.vvp" \
    "$task_dir/rtl/usb2_lowpower_diag.v" \
    "$task_dir/sim/tb_usb2_lowpower_diag.sv"
vvp "$sim_dir/lowpower.vvp"
done
prim_sim=${GW25K_PRIM_SIM:-/Applications/GowinIDE.app/Contents/Resources/Gowin_EDA/IDE/simlib/gw5a/prim_sim.v}
iverilog -g2012 -s tb_usb2_lowpower_pads -o "$sim_dir/pads.vvp" \
    "$prim_sim" "$task_dir/rtl/usb2_lowpower_diag.v" \
    "$task_dir/rtl/usb2_lowpower_top.v" \
    "$task_dir/sim/tb_usb2_lowpower_pads.sv"
vvp "$sim_dir/pads.vvp"
