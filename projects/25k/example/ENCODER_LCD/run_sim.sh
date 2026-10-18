#!/bin/sh
set -eu
project_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$project_dir"
python3 generate_init.py --check
mkdir -p reports
sim_dir=$(mktemp -d "${TMPDIR:-/tmp}/encoder-lcd-sim.XXXXXX")
trap 'rm -rf "$sim_dir"' EXIT HUP INT TERM
IVERILOG="${IVERILOG:-iverilog}"
VVP="${VVP:-vvp}"
"$IVERILOG" -g2012 -Wall -s tb_encoder_input -o "$sim_dir/input" \
    src/encoder_input.v sim/tb_encoder_input.v
"$VVP" "$sim_dir/input"
"$IVERILOG" -g2012 -Wall -s tb_encoder_response -o "$sim_dir/response" \
    src/encoder_input.v sim/tb_encoder_response.v
"$VVP" "$sim_dir/response"
"$IVERILOG" -g2012 -Wall -s tb_encoder_lcd_view -o "$sim_dir/view" \
    src/encoder_lcd_view.v sim/tb_encoder_lcd_view.v
"$VVP" "$sim_dir/view" +OUT=reports/encoder_lcd_preview.ppm
"$IVERILOG" -g2012 -Wall -s tb_encoder_lcd_display -o "$sim_dir/display" \
    src/lcd_spi_byte.v src/lcd_init_rom.v src/encoder_lcd_display.v sim/tb_encoder_lcd_display.v
"$VVP" "$sim_dir/display"
"$IVERILOG" -g2012 -Wall -s tb_encoder_lcd_top -o "$sim_dir/top" \
    src/*.v sim/tb_encoder_lcd_top.v
"$VVP" "$sim_dir/top"
