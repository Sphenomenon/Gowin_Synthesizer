// W-only compile selection; preserve the default maintained modules and
// their hierarchy for M and all accepted providers. Audio observations remain
// available to the real runtime/APB/25K feedback; no display or FFT is compiled.
`define WORKSTATION_RUNTIME_NO_DISPLAY
`include "rtl/workstation/workstation_runtime_controlled.sv"
`include "rtl/audio/workstation_observation_consumers.sv"
`undef WORKSTATION_RUNTIME_NO_DISPLAY
