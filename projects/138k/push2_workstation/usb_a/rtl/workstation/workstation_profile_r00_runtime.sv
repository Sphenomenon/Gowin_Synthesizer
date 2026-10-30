// Explicit R00 production composition; old runtime/BLE backends keep their defaults.
`define WORKSTATION_RECORDING_DDR
`include "rtl/workstation/workstation_profile_no_cnn_runtime.sv"
`undef WORKSTATION_RECORDING_DDR
