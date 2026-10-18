#!/bin/sh
set -eu
project_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$project_dir"
python3 generate_init.py --check
sim_dir=$(mktemp -d "${TMPDIR:-/tmp}/nv3007-lcd-sim.XXXXXX")
trap 'rm -rf "$sim_dir"' EXIT HUP INT TERM
IVERILOG="${IVERILOG:-iverilog}"
VVP="${VVP:-vvp}"
"$IVERILOG" -g2012 -Wall -s tb_lcd_spi_byte -o "$sim_dir/tb_lcd_spi_byte" \
    src/lcd_spi_byte.v sim/tb_lcd_spi_byte.v
"$VVP" "$sim_dir/tb_lcd_spi_byte"
"$IVERILOG" -g2012 -Wall -s tb_lcd_bringup -o "$sim_dir/tb_lcd_bringup" \
    src/lcd_spi_byte.v src/lcd_init_rom.v src/lcd_bringup_top.v sim/tb_lcd_bringup.v
"$VVP" "$sim_dir/tb_lcd_bringup"
