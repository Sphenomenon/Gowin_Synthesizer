#!/bin/sh
set -eu
cd "$(dirname "$0")"
python3 generate_core.py
build_dir=$(mktemp -d /private/tmp/gw25k-usb1-sim-XXXXXX)
trap 'rm -rf "$build_dir"' EXIT HUP INT TERM
iverilog -g2012 -s tb_usb1_cdc_loopback -o "$build_dir/tb" \
    sim/tb_usb1_cdc_loopback.sv rtl/usb1_cdc_loopback.v rtl/usb1_address_filter.v \
    generated/usbfs_core_top.v \
    ../vendor/fpga_usb_device/RTL/usb_class/usb_serial_top.v \
    ../vendor/fpga_usb_device/RTL/usbfs_core/usbfs_transaction.v \
    ../vendor/fpga_usb_device/RTL/usbfs_core/usbfs_bitlevel.v \
    ../vendor/fpga_usb_device/RTL/usbfs_core/usbfs_packet_rx.v \
    ../vendor/fpga_usb_device/RTL/usbfs_core/usbfs_packet_tx.v \
    ../vendor/fpga_usb_device/RTL/usbfs_core/usbfs_debug_monitor.v \
    ../vendor/fpga_usb_device/RTL/usbfs_core/usbfs_debug_uart_tx.v
vvp "$build_dir/tb"
