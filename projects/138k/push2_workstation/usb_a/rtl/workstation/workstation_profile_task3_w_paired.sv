// Explicit W paired role. Reuses the maintained native board, HCI/GATT and
// headless media firmware; paired profile helper replaces only reviewed wiring.
`define WORKSTATION_TASK3_W_PAIRED
`define WORKSTATION_TASK3_CNN_SIGNAL_BSRAM
`define WORKSTATION_TASK3_CNN_CQT_BSRAM
`include "rtl/workstation/workstation_profile_task3_w_media.sv"
`undef WORKSTATION_TASK3_CNN_CQT_BSRAM
`undef WORKSTATION_TASK3_CNN_SIGNAL_BSRAM
`undef WORKSTATION_TASK3_W_PAIRED
