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

## Feature placement (2026-09-20)

This repository is the single deliverable repository for the competition
build. Anything another person must be able to clone and build has to end up
on this repository's `usb_a/` build path; code living elsewhere is either a
vendored source set with a manifest, or a process artifact.

Two features are in flight:

- **Score / melody guidance** lives on branch `codex/post-p28-product-features`
  (checked out at `.codex/worktrees/0979`), one commit ahead of `main`. Its
  final integration point is `usb_a/build.py` plus the full top, so the
  committed `Prj1` builds the accepted P29A candidate. Develop on the branch;
  the merge target is `main`.
- **TF-card MP3/WAV decode core** currently lives in the separate
  `Mega_138K/Dev` repository under `Prj1/src/storage/`. `Mega_138K` is
  downgraded to an upstream/source tree, not a deliverable. The long-term home
  is `usb_a/vendor/tf_audio/` (self-contained, with an `inputs.json` manifest
  like `usb_a/vendor/usb_host_fs_8fc3`), feeding PCM16/48 kHz into the audio
  path.

Rules for the split:

1. Every feature stays rebasable onto this repository's `main`.
2. UserCodes are globally unique across branches. `0x00000029` is owned by the
   physically accepted P29A guidance build; the never-downloaded P29 USB-IN
   diagnostic candidate must be rebuilt with the next free UserCode
   (`0x0000002A`) before it is ever downloaded. See
   `usb_a/P29_USB_IN_DIAGNOSTICS_CANDIDATE.json`.
3. New evidence goes to a new result directory and candidate JSON; never write
   into an accepted baseline directory.
4. `Prj1/vendor/sipeed_dvi/video_pll_init.v` is pinned to CRLF checkout so the
   raw PLL_INIT audit SHA is identical in the main checkout and any worktree.

The archived evidence trees, the relocation of the frozen baseline out of
`results/`, and the consolidation of dead-end routes are deliberately deferred.

## RTL8723DS BLE migration (2026-10-07)

The teammate's portable BLE export is frozen under
`usb_a/vendor/rtl8723ds_ble/` with its original manifest, notice, firmware and
regressions. The GW138K adapter, J8/PMOD1 constraints and diagnostic UART live
under `usb_a/rtl/bluetooth/`; `tools/build_rtl8723ds_ble.py` creates isolated
standalone or full-workstation candidates. Target synthesis attributes are
applied only to staged vendor copies.

UserCode `0x00000086` belongs to the independently routed BLE candidate;
`0x00000087` records its failed route-option-1 integration attempt;
`0x00000088` is reserved for the route-option-2 integration retry;
`0x00000089` is reserved for the optional compact-HCI integration candidate;
`0x00000090`/`0x00000091` are reserved for joint HCI+H5 compact integration/standalone candidates. These
are offline candidates, with 138K module hardware acceptance pending. The
joint compact standalone 0x91 closes 50 MHz timing; full integration 0x90 is
routed but has BLE/DDR timing regressions and is not release eligible. Their
records are in `usb_a/reports/RTL8723DS_BLE_MIGRATION_20261007.*`. The build does
not update `LATEST_WORKSTATION.json`; full-workstation acceptance remains
separate from standalone BLE validation.

The frozen BLE export is stored without Git newline conversion. Its original
firmware, utilization reports and portable regression logs are manifest inputs
and are tracked explicitly; newly generated build outputs still stay local.
