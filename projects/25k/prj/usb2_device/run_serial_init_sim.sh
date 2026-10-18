#!/bin/sh
set -eu
task_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
sim_dir=$(mktemp -d "${TMPDIR:-/tmp}/usb2-serial-init-sim.XXXXXX")
trap 'rm -rf "$sim_dir"' EXIT HUP INT TERM
iverilog -g2012 -Wall -s tb_usb2_serial_init -o "$sim_dir/init.vvp" \
    "$task_dir/rtl/usb2_serial_init.v" "$task_dir/sim/tb_usb2_serial_init.sv"
vvp "$sim_dir/init.vvp"
