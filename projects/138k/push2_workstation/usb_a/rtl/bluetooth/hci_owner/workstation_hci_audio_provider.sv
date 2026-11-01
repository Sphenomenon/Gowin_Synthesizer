// W audio-only compilation provider. Shared H5/HCI/Classic transport and
// controller initialization stay maintained in their existing owners.
// GATT, recording, Rice/CRC/download and final-frame capture are not elaborated.
`define WORKSTATION_HCI_AUDIO_ONLY
`include "rtl/bluetooth/hci_owner/workstation_hci_bluetooth.sv"
`include "rtl/bluetooth/hci_owner/workstation_hci_native_core.v"
`undef WORKSTATION_HCI_AUDIO_ONLY
