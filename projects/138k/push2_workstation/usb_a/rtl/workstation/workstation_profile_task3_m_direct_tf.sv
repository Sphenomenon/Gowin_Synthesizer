// Explicit task3 M: real native TF owner and ordered physical output tail.
// CNN/Bluetooth/long recording belong to W; this profile does not enable the
// unmeasured inter-board transport or change any existing DEMO selection.
`define WORKSTATION_NO_BLUETOOTH
`define WORKSTATION_NO_LOCAL_PANEL
`define WORKSTATION_NO_CNN
`define WORKSTATION_TF_MENU_WITHOUT_CNN
`define WORKSTATION_TF_DIRECT_NATIVE
`define WORKSTATION_DEMO_NO_LOCAL_RECORD
`define WORKSTATION_DEMO_NO_LOCAL_SCORE
`include "rtl/workstation/workstation_profile_runtime.sv"
`undef WORKSTATION_DEMO_NO_LOCAL_SCORE
`undef WORKSTATION_DEMO_NO_LOCAL_RECORD
`undef WORKSTATION_TF_DIRECT_NATIVE
`undef WORKSTATION_TF_MENU_WITHOUT_CNN
`undef WORKSTATION_NO_CNN
`undef WORKSTATION_NO_LOCAL_PANEL
`undef WORKSTATION_NO_BLUETOOTH
