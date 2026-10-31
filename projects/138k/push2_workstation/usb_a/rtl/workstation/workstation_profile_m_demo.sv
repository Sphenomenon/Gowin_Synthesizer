// M-DEMO base: complete local instrument/HDMI/TF; no BLE or recording owner.
// CNN is added in a separately identified revision after this base is measured.
`define WORKSTATION_NO_BLUETOOTH
`define WORKSTATION_NO_LOCAL_PANEL
`define WORKSTATION_NO_CNN
`define WORKSTATION_DEMO_NO_LOCAL_RECORD
`define WORKSTATION_DEMO_NO_LOCAL_SCORE
`include "rtl/workstation/workstation_profile_runtime.sv"
`undef WORKSTATION_DEMO_NO_LOCAL_SCORE
`undef WORKSTATION_DEMO_NO_LOCAL_RECORD
`undef WORKSTATION_NO_CNN
`undef WORKSTATION_NO_LOCAL_PANEL
`undef WORKSTATION_NO_BLUETOOTH
