#!/bin/sh
set -eu
cd "$(dirname "$0")"
python3 generate_serial_core.py
build_dir=$(mktemp -d /private/tmp/gw25k-usb2-integration-sim-XXXXXX)
trap 'rm -rf "$build_dir"' EXIT HUP INT TERM
for d1_invert in 0 1; do
for activity_diag in 0 1; do
iverilog -g2012 -s tb_usb2_serial_integration \
    -Ptb_usb2_serial_integration.DUT_D1_INVERT="$d1_invert" \
    -Ptb_usb2_serial_integration.PHY_D1_INVERT="$d1_invert" \
    -Ptb_usb2_serial_integration.ACTIVITY_DIAG="$activity_diag" \
    -o "$build_dir/tb" \
    sim/tb_usb2_serial_integration.sv sim/usb3300_serial_phy_model.sv \
    rtl/usb2_serial_top.v rtl/usb2_serial_init.v rtl/usb2_cdc_loopback.v \
    rtl/usb2_serial_activity.v \
    debug/usb2_status_50mhz.v \
    generated/usbfs_core_top.v generated/usb_serial_top.v \
    generated/usb2_address_filter.v \
    ../vendor/fpga_usb_device/RTL/usbfs_core/usbfs_transaction.v \
    ../vendor/fpga_usb_device/RTL/usbfs_core/usbfs_bitlevel.v \
    ../vendor/fpga_usb_device/RTL/usbfs_core/usbfs_packet_rx.v \
    ../vendor/fpga_usb_device/RTL/usbfs_core/usbfs_packet_tx.v \
    ../vendor/fpga_usb_device/RTL/usbfs_core/usbfs_debug_monitor.v \
    ../vendor/fpga_usb_device/RTL/usbfs_core/usbfs_debug_uart_tx.v
vvp "$build_dir/tb"
done
done
