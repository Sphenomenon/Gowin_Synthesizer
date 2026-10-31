// Explicit CPU Classic runtime + native shared HCI + decoded PCM + ROM128.
// These capabilities remain absent from every other compilation provider.
`define WORKSTATION_AE350_PCM
`define WORKSTATION_AE350_ROM128
`include "rtl/workstation/workstation_profile_hci_owner_v1.sv"
`undef WORKSTATION_AE350_ROM128
`undef WORKSTATION_AE350_PCM
