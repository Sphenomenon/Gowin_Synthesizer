// Explicit R00 configuration retaining HDMI and the USB interaction displays.
// Existing R00/default providers keep the local LCD and their original tokens.
`define WORKSTATION_NO_LOCAL_PANEL
`include "rtl/workstation/workstation_profile_r00_runtime.sv"
`undef WORKSTATION_NO_LOCAL_PANEL
