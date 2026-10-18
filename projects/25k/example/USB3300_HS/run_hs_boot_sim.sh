#!/bin/sh
set -eu
task_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
sim_dir=$(mktemp -d "${TMPDIR:-/tmp}/usb2-hs-boot-sim.XXXXXX")
trap 'rm -rf "$sim_dir"' EXIT HUP INT TERM
iverilog -g2012 -Wall -s tb_usb2_hs_boot -o "$sim_dir/boot.vvp" \
    "$task_dir/hs/usb2_hs_boot.v" "$task_dir/sim/tb_usb2_hs_boot.sv"
vvp "$sim_dir/boot.vvp"
