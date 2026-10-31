// Explicit physical ROM96 candidate; shared CPU/HCI/PCM business sources.
`define WORKSTATION_AE350_PCM
`define WORKSTATION_AE350_ROM96
`include "rtl/workstation/workstation_profile_hci_owner_v1.sv"
`undef WORKSTATION_AE350_ROM96
`undef WORKSTATION_AE350_PCM
