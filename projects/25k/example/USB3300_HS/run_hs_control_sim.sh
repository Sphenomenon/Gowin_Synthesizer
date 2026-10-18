#!/bin/sh
set -eu
cd "$(dirname "$0")"
build_dir=$(mktemp -d /private/tmp/gw25k-usb2-hs-control-XXXXXX)
trap 'rm -rf "$build_dir"' EXIT HUP INT TERM
iverilog -g2012 -s tb_usb2_hs_control -I vendor/ultraembedded_usb_hs/cdc \
    -o "$build_dir/tb" sim/tb_usb2_hs_control.sv hs/usb_cdc_core.v \
    hs/usb_desc_rom.v vendor/ultraembedded_usb_hs/cdc/usbf_device_core.v \
    vendor/ultraembedded_usb_hs/cdc/usbf_sie_tx.v \
    vendor/ultraembedded_usb_hs/cdc/usbf_sie_rx.v \
    vendor/ultraembedded_usb_hs/cdc/usbf_crc16.v
vvp "$build_dir/tb"
