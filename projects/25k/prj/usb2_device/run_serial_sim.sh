#!/bin/sh
set -eu
cd "$(dirname "$0")"
python3 generate_serial_core.py
build_dir=$(mktemp -d /private/tmp/gw25k-usb2-serial-sim-XXXXXX)
trap 'rm -rf "$build_dir"' EXIT HUP INT TERM
iverilog -g2012 -s tb_usb2_cdc_loopback -o "$build_dir/tb" \
    sim/tb_usb2_cdc_loopback.sv rtl/usb2_cdc_loopback.v \
    generated/usbfs_core_top.v generated/usb_serial_top.v \
    generated/usb2_address_filter.v \
    ../vendor/fpga_usb_device/RTL/usbfs_core/usbfs_transaction.v \
    ../vendor/fpga_usb_device/RTL/usbfs_core/usbfs_bitlevel.v \
    ../vendor/fpga_usb_device/RTL/usbfs_core/usbfs_packet_rx.v \
    ../vendor/fpga_usb_device/RTL/usbfs_core/usbfs_packet_tx.v \
    ../vendor/fpga_usb_device/RTL/usbfs_core/usbfs_debug_monitor.v \
    ../vendor/fpga_usb_device/RTL/usbfs_core/usbfs_debug_uart_tx.v
vvp "$build_dir/tb"
