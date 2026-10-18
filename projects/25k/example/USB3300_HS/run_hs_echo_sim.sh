#!/bin/sh
set -eu
project_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
sim_dir=$(mktemp -d "${TMPDIR:-/tmp}/usb2-hs-echo-sim.XXXXXX")
trap 'rm -rf "$sim_dir"' EXIT HUP INT TERM
iverilog -g2012 -s tb_usb2_hs_echo -o "$sim_dir/echo.vvp" \
    "$project_dir/sim/tb_usb2_hs_echo.sv" "$project_dir/hs/usb2_hs_echo.v"
vvp "$sim_dir/echo.vvp"
