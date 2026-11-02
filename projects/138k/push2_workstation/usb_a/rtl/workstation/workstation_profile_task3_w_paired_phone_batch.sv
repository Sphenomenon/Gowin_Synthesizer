// Explicit paired W atomic phone batch v3; old providers keep their own policy.
`define WORKSTATION_TASK3_PHONE_WINDOW_BLOCK
`define WORKSTATION_TASK3_PHONE_BATCH
`include "rtl/workstation/workstation_profile_task3_w_paired.sv"
`undef WORKSTATION_TASK3_PHONE_BATCH
`undef WORKSTATION_TASK3_PHONE_WINDOW_BLOCK
