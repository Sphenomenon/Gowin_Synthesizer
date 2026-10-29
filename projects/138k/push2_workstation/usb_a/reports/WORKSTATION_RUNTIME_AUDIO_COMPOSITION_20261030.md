# Native runtime audio composition: offline integration, 2026-10-30

The independently selectable native audio owner now connects the actual
qualified dual clocks/official GW5A DCS, switch transaction, full dual-rate
render service, owner-6 delay DMA, final PCM router, tagged request/return
bridge, error-enabled I2S serializer and physical-frame taps. It is **source
implemented and offline verified**. It is not selected by an accepted profile,
not synthesized/routed, and not a hardware or deployment acceptance.

## Identity and source policy

- Offline composition identity:
  `native-runtime-audio-offline-v1-29d0083ec95f4ed3`.
- Exact input-set SHA256:
  `29d0083ec95f4ed3e92b151f4010183e9cf8ce0cbbc00f4eed7204618fb2daa4`.
- Prepared reference assets:
  `/Users/sphenicidition/.cache/gw138k-task-20261030/f03-scan-window-profile-revision3/workstation/Prj1`,
  reference identity `custom138k-workstation-v1-d23d498ea824c9f9`.
  That prepared profile supplies locked legacy dependencies/data. Its selected
  top and original 48-kHz policy are not changed or relabeled as this dual-rate
  composition. The runner explicitly lists maintained runtime source owners.
- The full installed GW5A `prim_sim.v` is compiled and hashed; DCS is not a
  replacement clock model. Actual native A/B/C/vector and all effects run.
- Both complete final runs record every source, data, preset, prepared-profile
  and integration-manifest hash and verify no changes during execution.
  The evidence writer independently rechecked all those hashes afterward.
- Bitstream identity: none. No EDA or board operation belongs to this stage.

Machine evidence, full commands, input/log hashes and warning counts are in
`workstation_task_20261030/runtime_audio_composition.json`. The implementation
contract is in `rtl/workstation/RUNTIME_AUDIO_COMPOSITION.md`.

## Composition and readiness changes

The 50-MHz staged rate/epoch uses an immutable mailbox. Its returned ACK means
the service has finished all engine/effect/history ACKs and exposes the expected
rate. The compute-side context can prefill the new epoch before the clock
transaction publishes its public committed epoch; there is no duplicate public
parameter/rate authority.

Old-frame quiescence combines actual bridge, final-router and full-service
quiescence, first registered in the compute domain and then synchronized into
50 MHz. External media quiescence remains a separate caller-owned contract.
The serializer retains local reset until synchronized context-ready/quiesce
flags settle and eight genuine selected-clock edges pass. Its serial rate and
epoch lock before release and stay unchanged during the old frame's QUIESCE.
This specifically prevents the lost first request caused by enabling a
serializer before the bridge's global-release/quiesce synchronizers settle.

Common DSP/parameter/bridge resets never become stream-switch resets. The
serializer alone has the local stream reset; the physical fanout retains common
reset so new epochs remain observable. Analysis and record backpressure produce
their own explicit losses/faults and never stop audio.

CPU/MIDI/PC event APIs and service telemetry are directly forwarded. Switch
authorization, TF/record busy policy, asynchronous TF transport, other DDR
clients and display snapshots stay outside this composition. No new CC mapping
or recording behavior is invented.

## Final verification

The main test retains 76.8-MHz compute, 100-MHz memory, the real 12.288/16.9344-MHz
reference periods, real production ring/history sizes and the 2,000,000-cycle
50-MHz switch-state timeout. Only clock qualification and DAC startup counts
are shortened for the extended failure/stress run.

| Main integration result | Verified value |
| --- | ---: |
| Completed physical frames decoded and compared | 20,190 |
| Good frames / nonzero frames | 20,184 / 20,057 |
| Expected zero/error frames, identity preserved | 6 |
| Mid-frame 48→44.1→48 switches | 8 |
| Successful first request slots / all-ACK configurations | 13 / 14 |
| Explicit parameter events / NoteOff events | 768 / 26 |
| Actual loader overlaps with accepted sample slots | 6 |
| DDR writes / completed ordered fences | 5,036 / 21 |
| Analysis / record sink drops, explicitly reported | 6,735 / 12,108 |

Every A/B/C source has 32 actual voices; vector has eight. The test holds their
notes through both switch directions. The C source warms the actual 9,600-sample
48-kHz and 8,820-sample 44.1-kHz DDR echo histories, chorus and reverb, observing
nonzero wet data from all three stages and actual FDN tails in both rates.
Continuous parameter/program events and NoteOff events share the unchanged
event boundary. A real NoteOn loader is deliberately started just before the
physical request. Independent BCK-bit decoding equals each completed physical
PCM frame; the tagged frame equals the single final PCM owner's return and both
taps. Normal steady frames cannot pass by being replaced with zero/error.

The test checks BCK half-periods throughout the old frame, old rate/epoch tags
and serial latches while the new stage changes in the frame's middle. It also
checks first-slot bridge readiness at each local reset release.

The separate production-startup run restores all composition defaults:
50,000-cycle/four-window qualification, 500-cycle loss detection, 16-cycle
stopped-low proof, four-frame PDN hold and 1,028-frame DAC startup. Complete
48-kHz boot and first 44.1-kHz configuration/prefill/start finish in 57 ms of
simulation under the unchanged 40-ms **per-state** timeout. It compares 211 good
physical frames, including 127 nonzero frames; both first slots and both DSP
configurations complete. Its maximum observed render is 1,146 compute clocks;
the sampled request-to-consume measure is 1,172 clocks.

All new composition/TB warnings: **0**. Combinational-loop warnings: **0**.
Inherited vendor/dependency warnings remain visible in both logs and machine
evidence; none are hidden by a blanket diagnostic removal. Source-boundary
regression: **10/10**. Runner Python syntax and new-file whitespace checks pass.

## Failure and latency evidence

The complete main run independently verifies:

- Selected clock stops high, then low in a later epoch: local reset and physical
  mute assert without requiring another selected edge. Recovery retries the
  last committed rate with a new epoch; held notes/common parameters survive.
- PANIC arrives during a real in-flight render and a pending switch: old
  canceled output retains zero/error; held/active state clears. New requests
  accepted while already muted complete as actual good-zero DSP slots, so an
  empty-held-note switch commits without a new NoteOn. A later NoteOn restores
  actual nonzero synthesis. Silent slots are not counted as source acceptance.
- A coherent TF packet at the wrong rate is not consumed/held/decimated into
  the stream. It produces explicit tagged zero/error. A matching-rate nonzero
  packet returns normally. This fixture does not migrate the real file CDC.
- External media quiescence is withheld: the real 40-ms QUIESCE timeout leaves
  the committed epoch and held notes intact. Recovery works after the boundary
  acknowledges.
- An actual ordered owner-6 fence response is withheld until the real DMA
  timeout. Sticky DSP fault quarantines serial reset, pins and public validity.
  Restoring memory responses and calling clock `recover` cannot clear it: the
  retried clock transaction times out in PREFILL and never reports ready/applied.

Maximum observed full-service render is **1,184 compute clocks (15.417 us)**;
all-ACK configuration is **455 clocks (5.925 us)**, including actual ordered DDR
work after wet-history use. The serial request pulse sampled on falling MCLK to
sample consumption on rising MCLK is at most **1,210 ceil compute clocks**.
Adding the worst 40.691-ns generation-to-observation half-MCLK gives a measured
fixture bound of **15.796 us**, below the 20.833-us 48-kHz sample window.
This is not proof of the separate whole-system 12-us objective; that threshold
remains unmet by this measured bound and needs separate optimization/evidence.
No audio clock or sample schedule is relaxed to obtain these results.

## Remaining scope and rollback

The DDR queue is a functional ordering model, not DDR pin timing. TF input is an
atomic packet fixture, not the production asynchronous file path. CPU/command
authorization, TF/record state policy and cross-domain tap consumers are still
external. The module requires a coordinated common reset covering compute,
memory/FIFOs and their PLL/DDR readiness; clock-only recover is not that reset.

There is no native top/profile selection, synthesis/P&R, physical resource/CDC
gate, USB/TDM capture, DAC acceptance or SRAM/Flash deployment in this report.
Future selection needs a new explicit source/profile identity and preservation
of score/extensions, existing interface adapters and every required feature.
Rollback is to keep the existing selected top/profile. These six new opt-in
source/test/document/evidence files can remain unselected or be removed without
changing locked baselines, accepted inputs or hardware.

## Reproduction

```sh
python3 projects/138k/push2_workstation/usb_a/sim/audio/run_runtime_audio.py \
  --project /Users/sphenicidition/.cache/gw138k-task-20261030/f03-scan-window-profile-revision3/workstation/Prj1 \
  --output /Users/sphenicidition/.cache/gw138k-task-20261030/runtime-audio-final-main
python3 projects/138k/push2_workstation/usb_a/sim/audio/run_runtime_audio.py \
  --project /Users/sphenicidition/.cache/gw138k-task-20261030/f03-scan-window-profile-revision3/workstation/Prj1 \
  --output /Users/sphenicidition/.cache/gw138k-task-20261030/runtime-audio-final-production \
  --production-startup
python3 projects/138k/push2_workstation/usb_a/sim/test_current_workstation_sources.py
```

Use fresh output directories; the runner deliberately refuses to reuse them.

Parent independent reruns used fresh `runtime-audio-parent-final-main` and `runtime-audio-parent-final-startup` output directories. Both passed with the exact same input-set identity and metrics above; every input hash was independently checked again after completion. Main run: 20,190 physical frames, 20,057 nonzero, 1,210-clock sampled slot maximum. Production defaults: 211 good frames, 127 nonzero. Separate evidence file hashes are retained in the machine record.
