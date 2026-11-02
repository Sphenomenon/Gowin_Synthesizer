// Independent CNN filming candidate; full83 algorithm plus custom board I/O.
`define WORKSTATION_CUSTOM_138K
`define WORKSTATION_CNN_DEMO
`define WORKSTATION_NO_LOCAL_PANEL
`define WORKSTATION_NO_BLUETOOTH
`include "rtl/workstation/gw138k_push_workstation_top.v"
`undef WORKSTATION_NO_BLUETOOTH
`undef WORKSTATION_NO_LOCAL_PANEL
`undef WORKSTATION_CNN_DEMO
`undef WORKSTATION_CUSTOM_138K
