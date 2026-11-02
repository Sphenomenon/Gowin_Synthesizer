// One explicit paired-only compilation unit. Canonical HCI/business sources
// remain separately staged and hashed; their standalone FileList entries are
// disabled only for this role so these modules have one compilation owner.
`define WORKSTATION_TASK3_W_PAIRED
`include "rtl/bluetooth/workstation_bluetooth.sv"
`include "native_bluetooth/bt_verilog_core.v"
`include "native_bluetooth/bt_gatt.v"
`include "native_bluetooth/ble_protocol_command.v"
`undef WORKSTATION_TASK3_W_PAIRED
