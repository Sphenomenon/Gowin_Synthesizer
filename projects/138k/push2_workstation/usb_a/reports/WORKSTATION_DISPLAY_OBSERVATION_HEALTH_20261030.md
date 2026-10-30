# Display upstream observation loss health — 2026-10-30

`workstation_runtime_controlled.sv` now exposes the final port `display_observation_fault_o`, a sticky 50MHz display-only fault. Either physical observation FIFO loss or compute-to-50MHz display mailbox loss sets it. The native top must include its inverse in HDMI observation trust. Only the common runtime reset clears it; CPU reset, rate changes, serializer restart and later good frames cannot rearm publication. Audio sampling, the unique stream epoch and parameter/event ownership are unchanged.

The compute-to-50MHz display mailbox now crosses 203 bits, appending the three-bit effect mask and six-bit effect order to the previous 194-bit physical frame/control snapshot. This replaces two independent multi-bit 2FF copies, so effect metadata is captured on the same observation edge and delivered with the matching physical epoch/sequence/PCM. Existing fields and the 448-bit performance layout retain their contracts. All display fields require `display_valid_o`; reset/idle order can be zero before the first complete tuple. The downstream HDMI tuple remains 204 bits including its trust bit.

The helper stays in the controlled-runtime source, so the compile closure needs no additional source. Physical loss has already crossed selected MCLK into compute using the observation bridge's post-drop Gray register; the decoded count may jump and is never Gray-encoded again. Each compute-domain count becomes an independent sticky single-bit level before a two-stage 50MHz synchronization and final sticky latch. The source level includes the current count being nonzero as well as source sticky state. This catches a first drop whose count changes on the final compute edge, even when the clock stops before source sticky can sample that new value. Sticky state also prevents a later display counter wrap from restoring trust.

Validation command:

```sh
python3 projects/138k/push2_workstation/usb_a/sim/audio/run_display_observation_health.py \
  --project /Users/sphenicidition/.cache/gw138k-task-20261030/clean-rev2-profile-candidate/workstation/Prj1 \
  --output /absolute/new/output
```

The final local run used `/tmp/display-observation-health-20261030-v2` and reran the complete controlled regression in its `controlled/` directory. Every recorded input was rehashed after completion and matched its initial bytes. The earlier 194-bit development evidence is superseded by this identity.

| Check | Result |
|---|---|
| Actual physical observation bridge | PASS, four-slot FIFO filled, final fifth frame drops, selected MCLK stops before another edge, post-drop count and 50MHz fault still arrive |
| Actual 203-bit display mailbox | PASS, final tuple drops and compute stops on that edge; source sticky is still zero while current-nonzero level raises the fault |
| No following source frame | PASS for both final-drop cases; fault remains latched while source clocks are stopped |
| Counter wrap | PASS, actual first mailbox drop establishes sticky loss, near-wrap seed followed by its normal increment to zero does not restore trust |
| Common reset | PASS, four reset/release cases, including reset while clocks are stopped |
| Complete healthy controlled runtime | PASS, 1,078 physical and 1,078 observed frames, 361 at 48k and 717 at 44.1k, 1,077 display frames, two rate switches and CPU-reset checks; display fault remains clear |
| Atomic effect metadata | PASS, all 1,077 received display frames match an independent source-edge effect-pair oracle keyed by physical epoch/sequence; four observed pair states at 48k and three at 44.1k |
| Real audio and DDR work | PASS, I2S/PCM comparison, 384 FFT bins, 267 writes, four reads, USB/CPU events and parameter transactions |
| Verilator | Zero new controlled composition/fixture warnings apart from missing timescales; no UNOPTFLAT |

Evidence identity: `native-display-observation-health-v1-198b140e3528e9c3`. Source-set SHA-256: `198b140e3528e9c3ddd6aa7adb49134eae7ed79e5f76f39f3d967065922269fa`. Full source hashes, exact commands and metrics are in `reports/workstation_task_20261030/display_observation_health.json` and `/tmp/display-observation-health-20261030-v2/verification.json`. The underlying complete-runtime identity is `native-runtime-controlled-offline-v1-nonzero-a779c3f75b5ccd4b`.

This is offline directed transport/source-stop verification and complete functional runtime verification. It does not claim physical timing, physical CDC/resource closure, board acceptance, SRAM or Flash deployment. Existing completed video may keep scanning after a loss; new display publication stays disabled until common reset. Automatic same-session recovery would require an explicitly transported loss generation and a fresh complete analysis window. Deselecting the optional native runtime returns to the previously accepted profile; no accepted profile identity or default source selection changes in this phase.

Parent independent verification reran the complete runner, including the nonzero-epoch controlled regression, into `/Users/sphenicidition/.cache/gw138k-task-20261030/display-observation-health-parent-final`. It reproduced both identities, all final-drop/source-stop checks, the 1,078 physical frames, 1,077 atomic effect snapshots and zero new warnings. Every recorded source hash was independently rechecked; the machine-readable report includes the parent evidence SHA-256.
