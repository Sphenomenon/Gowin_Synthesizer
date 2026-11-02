// Independent BLE business image: real instrument, full HDMI and final DAC PCM.
// The original BLE UART/H5/HCI owner and live PCM RAM are selected by this image.
// CPU recording, cue playback, TF, CNN and local LCD are absent.
`define WORKSTATION_NO_LOCAL_PANEL
`define WORKSTATION_NO_CNN
`define WORKSTATION_DEMO_NO_TF
`define WORKSTATION_DEMO_NO_LOCAL_RECORD
`define WORKSTATION_DEMO_NO_LOCAL_SCORE
`define WORKSTATION_PUSH_RATE_CONTROL
`define WORKSTATION_XY_TRACE
`define WORKSTATION_XY_STEREO
`include "rtl/workstation/workstation_profile_runtime.sv"
`undef WORKSTATION_XY_STEREO
`undef WORKSTATION_XY_TRACE
`undef WORKSTATION_PUSH_RATE_CONTROL
`undef WORKSTATION_DEMO_NO_LOCAL_SCORE
`undef WORKSTATION_DEMO_NO_LOCAL_RECORD
`undef WORKSTATION_DEMO_NO_TF
`undef WORKSTATION_NO_CNN
`undef WORKSTATION_NO_LOCAL_PANEL
