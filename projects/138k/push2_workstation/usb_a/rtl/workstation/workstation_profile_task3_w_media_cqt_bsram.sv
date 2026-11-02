// Explicit W CNN placement: local signal and CQT ROM, DDR front coefficients.
`define WORKSTATION_TASK3_CNN_SIGNAL_BSRAM
`define WORKSTATION_TASK3_CNN_CQT_BSRAM
`include "rtl/workstation/workstation_profile_task3_w_media.sv"
`undef WORKSTATION_TASK3_CNN_CQT_BSRAM
`undef WORKSTATION_TASK3_CNN_SIGNAL_BSRAM
