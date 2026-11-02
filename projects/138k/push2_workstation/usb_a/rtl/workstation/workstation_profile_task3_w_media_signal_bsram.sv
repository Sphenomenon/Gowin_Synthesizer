// Explicit W CNN placement: local shared signal RAM, DDR CQT/front coefficients.
`define WORKSTATION_TASK3_CNN_SIGNAL_BSRAM
`include "rtl/workstation/workstation_profile_task3_w_media.sv"
`undef WORKSTATION_TASK3_CNN_SIGNAL_BSRAM
