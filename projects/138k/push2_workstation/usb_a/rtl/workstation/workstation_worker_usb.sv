// Explicit W-DEMO provider. Compile this instead of rtl/push2_usb_a_control.sv
// so retirement does not depend on macro state crossing compilation units.
`define WORKSTATION_DEMO_D_ONLY
`include "rtl/push2_usb_a_control.sv"
`undef WORKSTATION_DEMO_D_ONLY
