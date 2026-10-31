// Explicit AE350 business-owner candidate. Existing providers retain their source policy.
`define WORKSTATION_CPU_BLE_BUSINESS
`ifndef WORKSTATION_AE350_PCM
`define WORKSTATION_CPU_BLE_DIAGNOSTICS
`endif
`include "rtl/workstation/workstation_profile_r00_no_local_panel.sv"
`undef WORKSTATION_CPU_BLE_DIAGNOSTICS
`undef WORKSTATION_CPU_BLE_BUSINESS
