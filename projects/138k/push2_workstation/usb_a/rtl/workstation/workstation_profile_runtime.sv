// Explicit dual-rate complete-workstation composition. Accepted/pinned and
// unprofiled native entry points continue using their own providers.
`define WORKSTATION_CUSTOM_138K
`define WORKSTATION_RUNTIME_NATIVE
`include "rtl/workstation/gw138k_push_workstation_top.v"
`include "rtl/workstation/workstation_profile_hdmi.sv"
`undef WORKSTATION_RUNTIME_NATIVE
`undef WORKSTATION_CUSTOM_138K
