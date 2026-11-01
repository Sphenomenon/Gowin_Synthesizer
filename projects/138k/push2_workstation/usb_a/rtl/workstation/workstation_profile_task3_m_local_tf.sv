// Task3 local TF checkpoint. CNN/long recording/Bluetooth belong to W.
// The existing TF DDR service remains selected until direct playback is integrated.
`define WORKSTATION_NO_BLUETOOTH
`define WORKSTATION_NO_LOCAL_PANEL
`define WORKSTATION_NO_CNN
`define WORKSTATION_TF_MENU_WITHOUT_CNN
`define WORKSTATION_DEMO_NO_LOCAL_RECORD
`define WORKSTATION_DEMO_NO_LOCAL_SCORE
`include "rtl/workstation/workstation_profile_runtime.sv"
`undef WORKSTATION_DEMO_NO_LOCAL_SCORE
`undef WORKSTATION_DEMO_NO_LOCAL_RECORD
`undef WORKSTATION_TF_MENU_WITHOUT_CNN
`undef WORKSTATION_NO_CNN
`undef WORKSTATION_NO_LOCAL_PANEL
`undef WORKSTATION_NO_BLUETOOTH
