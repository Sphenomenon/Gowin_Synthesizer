// Explicit R00 configuration retaining HDMI and the USB interaction displays.
// Existing R00/default providers keep the local LCD and their original tokens.
`define WORKSTATION_NO_LOCAL_PANEL
`define WORKSTATION_BLE_RAW_DDR
`include "rtl/workstation/workstation_profile_r00_runtime.sv"
`undef WORKSTATION_BLE_RAW_DDR
`undef WORKSTATION_NO_LOCAL_PANEL
