// WORKSTATION_RUNTIME_NATIVE is supplied only by an explicit runtime profile.
// This provider does not define it; the default display remains metadata v1.0.
// Explicit workstation profile provider; select instead of the parent HDMI.
`define WORKSTATION_DDR_SCAN_WINDOW_ENABLE
`include "rtl/workstation/workstation_hdmi_display.sv"
`undef WORKSTATION_DDR_SCAN_WINDOW_ENABLE
