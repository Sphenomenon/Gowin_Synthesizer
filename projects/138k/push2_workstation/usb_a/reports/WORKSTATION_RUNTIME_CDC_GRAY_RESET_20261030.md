# Runtime CDC Gray bounds and BLE reset aliases — 2026-10-30

## Result and scope

The reviewed source-netlist tranche passes: 21 Gray groups, 400 first-stage bits, ten explicit registered-binary MSB aliases and two actual BLE reset-release aliases. The versioned runtime preparation now composes 43 proposed constraint lines: one source-period maximum flight bound and one hold-only exception per Gray group, plus one union of the two BLE release CLEAR selectors. The non-runtime preparation branch retains its existing SDC composition and passes its exact SDC equality regression.

This is endpoint-development evidence against the separately sealed historical revision4-v2 synthesis. The old SDC does **not** contain the proposed constraints; the default installed-constraint gate rejects it and writes no acceptance artifact. `candidate_constraints_installed` is false and `endpoint_development_only` is true. Whole-inventory, held-payload, FIFO payload/restart, remaining reset/level, routed timing, STA, physical CDC, hardware and release flags remain false. No new runtime candidate was prepared, synthesis invoked, bitstream generated, SRAM programmed or Flash written by this phase.

The original inventory has 150 records, including these 21 Gray records. This tranche does not close the other records. Product changes made after the historical snapshot, including the USB queue fence, TF clear/drain work and new media/rate-switch orchestration, require a refreshed inventory, fresh candidate lock and new synthesis. The old TF LUT topology and aliases below must not be transferred to changed RTL as proof.

## Identity and evidence

- Audit identity: `runtime-cdc-gray-reset-source-v1-419fd8ea7ec7bfc8`.
- Audit source-set SHA-256: `419fd8ea7ec7bfc88ba6e6c8f6c82e9155bfa151da1f407153c859a94de0a708`.
- Versioned verification: `workstation_task_20261030/runtime_cdc_gray_reset.json`, SHA-256 `c0eda7fed95844d7eb45c22bfe8adced487f56192a4e53638039f8ae6a77f16e`.
- Local final run: `/Users/sphenicidition/.cache/gw138k-task-20261030/runtime-cdc-gray-reset-final-v2/`.
- Raw final audit JSON SHA-256: `b130c05fce6f4fa72e976d4cd4e951f6c881df1a9829c34e01d222736fd188de`.
- Historical synthesis candidate: `custom138k-workstation-v1-41e653fe462e5ea3`, synthesis-only; 560 staged inputs are independently rehashed before and after the audit and compared to the prepared profile's full input closure.
- Historical VG SHA-256: `2319746ad8eabba1e19721908402dd0c25bd91aba52b896650d82153e6c4e3da`.
- Historical SDC SHA-256: `636effbaeaa496ba74f12aa4ba622766a3e13e5833e62d32aa1b077890eab8ad`.
- Historical process evidence SHA-256: `3265bee262fec902496b483bfdcc9a9fcf328fd7ac98460cb215fd5d914ddb71`.
- New bitstream identity: none.

The identity combines the historical synthesis seal with hashes of the current maintained audit/preparation tools and tests. It identifies this audit result; it does not identify a newly synthesized product. The versioned JSON includes all reviewed bit paths, exact selectors, full historical input hashes, clock audit, mutations and verification commands.

## Reviewed constraints and topology

| Groups | First-stage bits |
| --- | ---: |
| Memory guard heartbeat | 32 |
| MIDI drop count | 32 |
| Three reference/selected clock monitors | 96 |
| Four delay FIFO pointer directions | 40 |
| Physical observation pointers and drop count | 42 |
| Display memory drop count | 32 |
| TF frame pointers, generation and acknowledgement | 74 |
| Four TF byte FIFO pointer directions | 52 |
| Total | 400 |

Each source and first-stage selector enumerates an exact bit and permits only the synthesis suffix wildcard. This prevents `write_gray_*` from also selecting `write_gray_meta` or `write_gray_sync`. All 802 selectors expand exactly: 400 source Q pins, 400 first-stage D pins and six BLE CLEAR pins. The audit rejects absent, duplicate, extra or misconnected bits; a unique Q producer, actual source/destination clocks, unconditional first/second-stage enables and first-stage fanout to only the expected second-stage data path are required.

The flight limits round **down** to three decimals: memory `10.000ns`, compute `13.020ns`, control `20.000ns`, reference48 `81.380ns`, reference44 and selected `59.051ns`. Selected-clock paths use the stricter period for both modes. These are proposed maximum flight bounds, with hold-only exceptions on the same endpoint pairs. Nonnegative individual flight bounded by one producing period also bounds propagation skew by that period. Actual routed flight/skew and Gowin object resolution remain unverified; source Gray encoding and restart protocol behavior are separate proof obligations.

Ten source MSBs are accepted only through explicit registered-binary aliases: the four delay pointer MSBs, physical-observer read pointer, TF frame read pointer, TF generation, TF generation acknowledgement and two TF byte read pointers. Arbitrary missing Gray bits or producer discovery do not create additional accepted aliases.

In the historical TF byte FIFO, both synchronization stages have a destination-local clear LUT. For all 52 bits, both LUTs must be `LUT3 INIT=8'h90`, use the expected Gray/first-stage Q on I2 and have the same I0/I1 conditions driven by unique local-clock registers. The first-stage Q may feed only the second LUT's I2. Mapping these gates does not establish FIFO ownership or restart-clear safety; the newer runtime TF implementation needs its own audit.

The actual BLE source release is merged into `u_managed/observation/drops/source_release_{0,1,2}_s0` on the selected MCLK. The destination release is merged into `u_managed/midi_bytes/source_release_{0,1,2}_s0` on 50MHz. Each is an unconditional three-register VCC shift chain. Their stage-two Qs feed the expected BLE first-stage CLEAR through an inverter. All six release CLEARs share the actual `LUT2 INIT=4'h7` assertion cone `!(reset_n && memory_guard_started)`. Recovery/removal, pulse widths, placement and physical release remain gates.

Native runtime alone removes the exact legacy `tf_run_meta*/D` exception. The VG must contain neither `tf_run_meta` nor `tf_run_audio`; the native 50MHz producer is not rebound to a different register. A changed legacy constraint shape fails closed. The earlier three restored mixed-query commands remain preserved.

## Installation gate and regressions

The installation check requires each proposed line exactly once. It rejects setup cuts on reviewed source/first-stage paths, source-only/global cuts, combined hold/setup flags, new broad hold exceptions, extra overriding max-delay constraints, and every unreviewed SDC command or timing-query shape. This includes `set_clock_groups`, `set_disable_timing`, `set_multicycle_path`, external `source`, nested Tcl evaluation and command separators. Existing exact DDR minimum-delay, Flash input-delay and four report commands remain permitted. The two existing, explicitly reviewed selected48/selected44 mode exclusions are the only whole-clock exceptions accepted. The full clock auditor separately checks the exact clock declarations. These text/netlist checks do not confirm that Gowin resolves the queries or satisfies their physical constraints.

The final actual-VG suite passes 14 tests and rejects all 31 deliberate corruptions. Cases include wrong Gray bit/clock/second stage, disconnected binary MSB alias, extra bit, both TF LUT functions, TF local clear clock and differing clear conditions, wrong BLE shift, missing/duplicate/relaxed bounds, setup/hold cuts and unsupported timing/Tcl commands. The installation test also accepts a constructed full-SDC text fixture with only the old guard lines and unused TF selector replaced; this fixture is not a prepared or accepted candidate.

Six declaration/shared-constraint tests, ten accepted/pinned source-selection tests, Python syntax checks and owned-file whitespace checks pass. The non-runtime full prepare test passes with the explicit xPack RISC-V toolchain and checks exact SDC equality, compilation-input closure, preprocessed ports and disabled release paths. Its instance assertion compares complete tokens while ignoring whitespace introduced by the runtime-only USB parameter preprocessor block.

```sh
GW138K_RUNTIME_CDC_STAGE=/Users/sphenicidition/.cache/gw138k-task-20261030/runtime-rev4-synthesis-41e653fe/workstation/Prj1 \
GW138K_RUNTIME_CDC_PROCESS=/Users/sphenicidition/.cache/gw138k-task-20261030/runtime-rev4-synthesis-41e653fe/runtime_synthesis_evidence/process.json \
GW138K_RUNTIME_CDC_TEST_EVIDENCE=/path/to/new-evidence/mutations.json \
python3 projects/138k/push2_workstation/usb_a/sim/test_workstation_runtime_cdc.py -v

python3 projects/138k/push2_workstation/usb_a/tools/workstation_runtime_cdc.py \
  --project /Users/sphenicidition/.cache/gw138k-task-20261030/runtime-rev4-synthesis-41e653fe/workstation/Prj1 \
  --synthesis-evidence /Users/sphenicidition/.cache/gw138k-task-20261030/runtime-rev4-synthesis-41e653fe/runtime_synthesis_evidence/process.json \
  --output /path/to/new-evidence/audit.json --endpoint-development
```

Omit `--endpoint-development` for the future newly sealed candidate: proposed constraints must actually be installed or the audit fails. A pass still leaves physical/whole-inventory flags false.

## Integration and rollback

The maintained implementation is `tools/workstation_runtime_cdc.py`; `workstation_runtime_profile.py` supplies its separate `runtime_cdc_sdc`, and only the runtime branch of `workstation_custom_board.py` installs it. No product RTL, frozen baseline, vendor FIFO, accepted profile or historical evidence was changed by this tranche.

The parent must lock the changed tools and product owners with a fresh candidate identity, resynthesize, update the manifest for changed topology and run the default installation gate on that actual sealed VG/SDC. Remaining CDC contracts, routed clocks/timing/resources and feature preservation still precede any deployment claim. A later SRAM run needs its own bitstream identity, programming/readback and board acceptance evidence. No physical rollback is needed for this phase; source rollback must restore the runtime constraint integration and prepare a new candidate identity instead of reusing this evidence.

## Independent parent verification

The parent recompiled/reran the 14-test actual-VG suite in a separate evidence directory: all 31 mutation records match, and every raw development-audit field matches the child result exactly. Six shared/declaration tests and the full non-runtime prepare with exact SDC equality also pass. The [parent record](workstation_task_20261030/runtime_cdc_gray_reset_parent.json) preserves separate evidence hashes. This does not promote the old candidate to installed-constraint or physical acceptance.
