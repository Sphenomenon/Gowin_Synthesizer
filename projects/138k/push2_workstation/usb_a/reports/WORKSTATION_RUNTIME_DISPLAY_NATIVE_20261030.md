# Explicit native runtime HDMI display — 2026-10-30

The optional `WORKSTATION_RUNTIME_NATIVE` branch now connects the frozen A07 actual-PCM analysis producer, minor1 writer and minor1 reader to the maintained HDMI raster/DDR composition. `workstation_profile_hdmi.sv` does not define the macro; existing default selection retains exactly the previous 3,210 preprocessed HDL tokens. Reverse provenance reproduces the original parent SHA-256. This phase changes no top, profile JSON or profile tooling; those remain separately owned integration work.

The new `workstation_display_runtime.sv` crosses the complete 204-bit physical-frame/control/trust tuple from 50MHz to memory/UI clock through the maintained held-word CDC, with independent trust revocation and a Gray-crossed drop counter. It owns observation cancellation, analysis and display scheduling. Export may run with a raster; coherent reader loading waits for the raster/cache lease to finish. HDMI extends that lease from renderer_start through the final P5 metadata DDR acknowledgment, including the renderer_done/meta_pending transition gap. The raster reads the validated local cache with its own analysis disabled and keeps its existing capture only as frame pacing.

The initial raster requires a complete current-context image. Writer completion, reader start/completion, new raster and summary publication compare rate/epoch/local cancellation generation against the current source. A sealed old packet may drain after loss but cannot become a new raster/summary. A partial reader can drain without publishing a stale raster. A previously completed physical framebuffer may continue scanning. The unique audio owner's epoch remains opaque and nonzero; no display-side remapping is introduced.

Runtime-only HDMI ports are `frame_44k1_i`, `frame_error_i`, `frame_epoch_i[31:0]`, `frame_sequence_i[31:0]`, `observation_trusted_i`, `display_observation_drop_o[31:0]`, `ddr_client_reset_no` and `ddr_client_ready_o`. The first fields accompany the existing same-50MHz completed-frame PCM/reference/voices/status. Drop count is source-50MHz; the final two ports observe memory-domain `ui_rst_n` and `ui_rst_n && memory_calibrated && bist_done && !bist_failed`. They do not change reset behavior. DDR/video reset-domain separation is not implemented; the platform guard must fail-stop after readiness/reset loss. Full integration details and compile replacements are in `rtl/workstation/RUNTIME_DISPLAY.md`.

Validation command:

```sh
python3 projects/138k/push2_workstation/usb_a/sim/display/run_workstation_display_runtime.py \
  --project /Users/sphenicidition/.cache/gw138k-task-20261030/clean-rev2-profile-candidate/workstation/Prj1 \
  --output /tmp/workstation-display-runtime-20261030-v2
```

| Check | Result |
|---|---|
| Default compatibility | PASS, all 3,210 preprocessed HDL tokens equal previous native HDMI composition |
| Provenance | PASS, exact reverse edits restore pre-runtime native and original parent bytes |
| Complete HDMI elaboration | PASS, macro off/on, real maintained renderer/DDR/scanout, official GW5A PLL/TMDS primitives and GSR; only existing primitive empty-sensitivity warnings |
| Actual PCM→analysis→DDR→cache composition | PASS, 6 current-context publications, 9 DDR commits |
| Atomic 50MHz→memory context/control tuple | PASS, 128,702 complete 204-bit tuple checks |
| Independent physical-input oracle | PASS, 1,024 unfiltered wave samples, 131,072 XY pixels, 1,024 actual FFT log columns |
| Actual-rate stereo FFT peaks | PASS, bin32/bin64 at both 48000/44100; actual frequency follows the tagged rate |
| Publication cancellation | PASS, old epoch queued behind active raster, stalled COMMIT_GLOBAL tail, partial reader copy, error frame, zero epoch |
| Same-epoch observation overflow | PASS, 60 mailbox drops, final drop detected while later frame strobes are paused, fresh complete analysis required |
| Cache ownership | PASS, reader never copies/flips while the external raster lease is active |
| Verilator | Zero owned pipeline/fixture/modified-display warnings apart from missing timescales; no UNOPTFLAT |

Evidence identity: `native-runtime-display-offline-v1-cc2f1094e1b08a34`. Source-set SHA-256: `cc2f1094e1b08a344a59ac4a35cb63ac3861833cb82b6248f0999dbaa532d38c`. Full source/prepared-profile/official primitive hashes, exact commands and metrics are preserved in `reports/workstation_task_20261030/runtime_display_native.json` and `/tmp/workstation-display-runtime-20261030-v2/verification.json`. The runner checks the separately frozen A07 prerequisite hashes, exact reverse provenance, default tokens, no source drift and no new implementation warnings. No frozen/vendor bytes were changed.

Parent independent verification reran the complete command into `/Users/sphenicidition/.cache/gw138k-task-20261030/runtime-display-parent-final`, reproduced the same identity, metrics, default token equality and both official-primitive elaborations, and rechecked every recorded input hash against disk. Its verification file hash and results are included in the machine-readable report.

The functional DDR and accelerated input packets do not validate physical I2S scheduling, complete framebuffer pixels, live HDMI, synthesis, P&R, resource allocation, physical CDC/timing constraints or a board. No bitstream was created or deployed by this phase. Additional CDC instances need the existing held-data/Gray-bus constraints in the selected physical profile. Upstream loss without a later sequence gap must revoke input trust. Rollback deselects `WORKSTATION_RUNTIME_NATIVE` and returns to the existing minor0 fixed-48k display contract; accepted identities are not reused for changed inputs.
