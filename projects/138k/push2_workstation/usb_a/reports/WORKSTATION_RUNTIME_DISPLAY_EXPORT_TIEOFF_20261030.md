# Native runtime HDMI unused export inputs — 2026-10-30

The first actual rev4 Gowin synthesis of `custom138k-workstation-v1-eeca04948a6f07bb` reported three EX1998 undriven-net warnings for `shared_read_enable`, `shared_read_kind[1]` and `shared_read_addr[15]` in native HDMI. The runtime branch disables the legacy display writer and sets renderer `SHARED_EXPORT=0`, but its legacy export read inputs still referenced the old writer's now-undriven signals.

`workstation_hdmi_display.sv` now connects only those three renderer inputs to explicit zero constants under `WORKSTATION_RUNTIME_NATIVE`. The macro-disabled branch retains its exact prior connections. The provenance manifest records this as a separate reversible edit and pins the changed native source SHA-256 `e159563aa97e4ee74d7ac41e70ba61ebc5a684e8b961aa601c63633e709df2b7`. The existing display analysis/cache/raster contracts, source tuple width and DDR/video reset behavior are unchanged. The earlier runtime display report and JSON remain historical evidence for their original source identity.

Validation command:

```sh
python3 projects/138k/push2_workstation/usb_a/sim/display/run_workstation_display_runtime.py \
  --project /Users/sphenicidition/.cache/gw138k-task-20261030/clean-rev2-profile-candidate/workstation/Prj1 \
  --output /tmp/workstation-display-runtime-export-tieoff-20261030-v1
```

| Check | Result |
|---|---|
| Default compatibility | PASS, all 3,210 macro-disabled preprocessed HDL tokens match the pre-runtime native composition |
| Exact provenance | PASS, reverse edits recover both the pre-runtime native bytes and original parent bytes |
| Complete HDMI elaboration | PASS, macro off/on with official GW5A primitives and GSR |
| Runtime renderer input topology | PASS, compiled Icarus netlist gives each of the three inputs exactly one constant-zero driver, at widths 1/2/16 |
| Real analysis/DDR/cache regression | PASS, six publications, nine DDR commits, 128,702 atomic tuple checks, 1,024 waveform samples, 131,072 XY pixels and 1,024 FFT columns |
| Context cancellation and lease | PASS, both rates, old epoch, stalled commit tail, partial reader, final CDC loss, zero epoch and raster cache ownership |
| Verilator | Zero owned implementation/fixture warnings apart from missing timescales; no UNOPTFLAT |

Evidence identity: `native-runtime-display-offline-v1-151421fb0d9384f0`. Source-set SHA-256: `151421fb0d9384f02490c915cc0ef1939ae6d8c19a964fe4c22a22665e1c04e4`. Exact commands, all input hashes, regression metrics and constant-driver elaboration details are in `reports/workstation_task_20261030/runtime_display_export_tieoff.json`. The complete runner output is `/tmp/workstation-display-runtime-export-tieoff-20261030-v1/verification.json`.

The old eeca0494 synthesis copy is retained unchanged as evidence. This phase establishes the corrected source and offline verification; the next separately identified prepared candidate must demonstrate that the three EX1998 warnings disappear in actual Gowin synthesis. It makes no new synthesis, P&R, timing, physical CDC/resource, board, SRAM or Flash acceptance claim. Rollback deselects the explicit native runtime profile; an accepted identity is never reused for changed release inputs.

Parent independent verification reran the complete display runner into `/Users/sphenicidition/.cache/gw138k-task-20261030/runtime-display-export-tieoff-parent-final`, reproduced the same identity, pipeline metrics, default tokens and both official-primitive elaborations, and rechecked all input hashes. It independently inspected the compiled runtime renderer netlist: each old export input has exactly one zero driver of width 1, 2 or 16. The machine-readable report retains this evidence. Actual Gowin warning removal remains a separate new-candidate synthesis check.
