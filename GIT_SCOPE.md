# FPGA workspace Git scope

This repository was initialized on 2026-09-13 for the active Gowin Push 2
USB-A audio workstation. The tracked construction source is the canonical
`migration/gw138k_audio/push2_workstation/results/workstation_20260911_174045_306332/Prj1`
tree together with the Push USB-A build, simulation, programming, audit, and
board-record files under `migration/gw138k_audio/push2_workstation/usb_a`.
The small frozen USB Host source set, its input manifest, and the audited DDR
reference netlist live under `usb_a/vendor`, so a fresh clone can prepare a
build without another migration tree.

The original Xilinx tree (`fpga/`), the separate Mega138K project
(`Mega_138K/`), unrelated migration experiments, generated build/capture
directories, and FPGA implementation databases are intentionally ignored.
Bitstreams are not tracked as source; their SHA256, UserCode, SRAM write/read
back, and acceptance state are recorded in the version JSON and verification
documents. The protected D50E hotplug bitstream remains at its existing path
and is not modified by Git setup.

For a new source file inside the canonical tree, add it normally. A new build
result or capture should remain outside Git; preserve its path and hash in the
corresponding verification record.
