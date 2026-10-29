// Explicit workstation profile provider; select instead of the parent HDMI.
`define WORKSTATION_DDR_SCAN_WINDOW_ENABLE
`include "rtl/workstation/workstation_hdmi_display.sv"
`undef WORKSTATION_DDR_SCAN_WINDOW_ENABLE
