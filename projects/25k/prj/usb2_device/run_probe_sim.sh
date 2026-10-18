#!/bin/sh
set -eu
task_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
sim_dir=$(mktemp -d "${TMPDIR:-/tmp}/usb2-probe-sim.XXXXXX")
trap 'rm -rf "$sim_dir"' EXIT HUP INT TERM
iverilog -g2012 -Wall -s tb_usb2_ulpi_probe -o "$sim_dir/probe.vvp" \
    "$task_dir/rtl/usb2_ulpi_probe.v" "$task_dir/sim/tb_usb2_ulpi_probe.sv"
vvp "$sim_dir/probe.vvp"
