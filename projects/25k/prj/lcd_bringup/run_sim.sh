#!/bin/sh
set -eu
cd "$(dirname "$0")"
python3 generate_init.py --check
mkdir -p sim/build
IVERILOG="${IVERILOG:-/opt/homebrew/bin/iverilog}"
VVP="${VVP:-/opt/homebrew/bin/vvp}"
"$IVERILOG" -g2012 -Wall -s tb_lcd_spi_byte -o sim/build/tb_lcd_spi_byte \
    src/lcd_spi_byte.v sim/tb_lcd_spi_byte.v
"$VVP" sim/build/tb_lcd_spi_byte
"$IVERILOG" -g2012 -Wall -s tb_lcd_bringup -o sim/build/tb_lcd_bringup \
    src/lcd_spi_byte.v src/lcd_init_rom.v src/lcd_bringup_top.v sim/tb_lcd_bringup.v
"$VVP" sim/build/tb_lcd_bringup
