## 25K BLE protocol and shared Android update (2026-10-20)

`projects/25k/example/RTL8723DS_PROTOCOL/` contains the accepted 25K business-GATT/recording/lossless source, frozen vendor inputs, tests and round18 hardware evidence. `clients/android/` is the only Android source; the standalone project's relative symlink preserves its existing tool interface. SOURCE_IMPORT.json binds imported file bytes and documents relocated documentation. Earlier raw captures/source snapshots remain at the original project; historical summaries and current evidence are retained. APKs, bitstreams, build databases, new captures and signing material remain ignored. Historical firmware manifests retain their original paths/hashes and require a local rebuild on a new clone. This import does not alter the 138K hardware top or establish its physical BLE acceptance.

# FPGA workspace Git scope

## Android control client (2026-10-20)

`clients/android/` is the independently buildable Kotlin/Compose mobile client
for workstation settings, recording control/download and live status. Its
source, pinned Gradle wrapper, protocol/file tests and validation records are
tracked alongside the board projects. It does not enter the FPGA `usb_a/`
build path. Shared Bluetooth protocol and implementation plans remain at the
Git root; new board references use `projects/138k/`.

Android SDK paths, dependency caches, build outputs, debug APK artifacts and
signing keys remain local and ignored. The validation record identifies the
tested debug APK by SHA256. Simulated protocol validation does not establish
real BLE or FPGA business-firmware acceptance.

## Board project layout (2026-10-18)

The Git root remains `fpga/`, with the common parent `projects/` containing
peer directories `138k/` and `25k/`. The existing 138K tree was moved intact to
`projects/138k/`; `projects/25k/` contains the panel source imported from
the local `GW_25K` project on 2026-10-19. Shared interface planning stays at the Git root.
There are no nested repositories for these board projects.

`migration/gw138k_audio` is a compatibility symlink to `../projects/138k`.
New references use `projects/138k`; historical evidence and pinned manifests
retain their original paths and bytes. Local results moved with the project
and remain ignored. The previously frozen source exceptions and vendor
newline attributes apply at the new paths. Other worktrees are unchanged.

This repository was initialized on 2026-09-13 for the active Gowin Push 2
USB-A audio workstation. The tracked construction source is the canonical
`projects/138k/push2_workstation/results/workstation_20260911_174045_306332/Prj1`
tree together with the Push USB-A build, simulation, programming, audit, and
board-record files under `projects/138k/push2_workstation/usb_a`.
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

## Standalone touchboard signal test

`projects/138k/push2_workstation/touchboard_test/` contains the
independent QT2160 signal probe, its frozen netlist and schematic, wiring
references, RTL and host tools, simulation models, and dated debug records.
It is a standalone SRAM test project; hardware touch acceptance is still
pending because the recorded raw sampling anomalies remain unresolved.

Source, input documents and debug summaries are tracked. Generated builds,
captures and verification output stay in its ignored `results/` directory.
The `LATEST_*.txt` files are local pointers into that directory and are ignored.

## 25K panel source import (2026-10-19)

`projects/25k/` preserves the original `GW_25K` source layout, with the
complete MIDI keyboard under `example/MIDI_KEYBOARD`, standalone peripheral
examples, bring-up projects, constraints, tests, hardware inputs, and existing
verification summaries. `SOURCE_IMPORT.json` records the imported file hashes.
The import preserves existing behavior and historical acceptance boundaries;
it does not establish new 138K/25K integration or board acceptance.

`builds/`, `impl/`, simulation scratch, generated bitstreams and normal tool
logs remain untracked. Original BLE firmware and manifest-bound upstream
reports/logs are explicit source-input exceptions. Existing manifests keep
their historical paths and hashes; their bitstreams require a local rebuild.
Imported files disable Git newline conversion to preserve frozen input bytes.
