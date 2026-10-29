# Native controlled runtime integration — 2026-10-30

The new opt-in `rtl/workstation/workstation_runtime_controlled.sv` composes the
existing CPU/APB, UART and USB control contracts with the native dual-clock
runtime. Its only event/session/parameters owner is `runtime.service`. The
maintained consumer composition keeps the real FFT256, 96-bit capture FIFO and
256-cue score player on **physical completed I2S frames**. Accepted top/profile
selection and physical deployment are separate from this stage.

## Identity and source policy

- Identity: `native-runtime-controlled-offline-v1-90448edf646b8a37`.
- Input-set SHA-256: `90448edf646b8a37c8c7674ed07cc4545eff1244cdcc48db9a4320c9445d0d67`.
- Full input hashes, commands, logs and metrics: [runtime_controlled_native.json](workstation_task_20261030/runtime_controlled_native.json).
- Explicit prepared reference: `custom138k-workstation-v1-f5b723250388add5` from
  `/Users/sphenicidition/.cache/gw138k-task-20261030/clean-rev2-profile-candidate/workstation/Prj1`.
- Final run: `/tmp/runtime-controlled-20261030-v5-final`. It follows the separate
  `core_ce` / reverb `local_history_clear` declaration-order repair. The final
  input hashes remained unchanged throughout the run. Earlier development runs
  are not the identity of this result.
- Source policy: the clean prepared reference supplies locked CPU/APB/UART,
  legacy FFT and remaining DSP dependencies. Maintained native runtime,
  controlled services, observation bridge, wrapper and consumers are explicit
  inputs. Every compiled source and memory input is hashed. No source lock,
  frozen/vendor byte, accepted top or profile was changed by this phase.
- Bitstream: none. SRAM and Flash deployment: none. Rollback is to leave this
  opt-in composition unselected; this phase has no board-state change.

## Resulting contracts

The wrapper retains the 448-bit performance layout, control/pitch/PC-health
packing, 31,250- and 115,200-baud UART byte CDCs, APB held-payload/predecode
boundary, panel commands and fair explicit-lifecycle USB/CPU merge. `preset_n`
resets services without resetting DSP notes or parameters. Owner-6 DDR comes
straight from `runtime.delay_dma`; there is no additional legacy DMA.

Switch controls remain 50 MHz. Recording enable, running score and TF active or
busy inhibit a new switch. A recording/score launch during an already-started
switch explicitly fails rather than silently producing a successful partial
operation. CPU APB command acceptance retains its original meaning.

The 98-bit physical observation carries rate/epoch/sequence/error/PCM. Display
CDC carries these same tags together with the old 128-bit projection in one
194-bit payload. Revision/voices/core health describe compute receipt time.
Epoch-local serializer counters cross as one epoch-tagged held health snapshot,
including the tested non-monotonic N→0 reset, instead of unit-step Gray CDC.

Context changes, gaps, errors and CDC loss invalidate recording, discard FFT
windows and stop score playback. Saturated observation-drop count permanently
removes trust until common reset. Normal recording STOP retains the queue for
the existing firmware's STOP→POP→READ→RELEASE flow; failed recordings flush and
require disable before retry. The unchanged 96-bit capture packet has no rate,
epoch or error metadata, so it explicitly accepts only 48 kHz. This does not
claim a 44.1-kHz recording object or BLE/long-recording backend.

The exact port domains, failure codes, launch-edge convention and remaining
caller duties are in [RUNTIME_CONTROLLED.md](../rtl/workstation/RUNTIME_CONTROLLED.md).

## Verification

```sh
python3 projects/138k/push2_workstation/usb_a/sim/audio/run_runtime_controlled.py \
  --project /Users/sphenicidition/.cache/gw138k-task-20261030/clean-rev2-profile-candidate/workstation/Prj1 \
  --output /tmp/runtime-controlled-20261030-v5-final
```

All three checks passed:

| Verification | Evidence |
|---|---|
| Complete real wrapper | 1,070 physical frames = 1,070 observed frames; independently decoded I2S PCM, error and identity match |
| Dual-rate observations | 353 frames at 48 kHz and 717 at 44.1 kHz; 971 nonzero frames |
| Atomic display context | 1,069 independently checked display PCM/rate/epoch/sequence/error tuples |
| Real FFT in complete wrapper | 384 nonzero bins: 128 at 48 kHz, 256 at 44.1 kHz; context tags checked |
| APB/services | 1,066 transactions; native ID, snapshot placement, preset isolation, CPU events, all 256 cue slots, capture STOP/POP/READ/RELEASE |
| Input/control behavior | Both UART bauds and framing health; 33 USB events, 18 CPU events, concurrent producer progress; lifecycle cancellation reaches real DSP |
| Switch/media behavior | 3 busy-source policy rejections; REC/score/TF block switch; 2 actual rate switches preserve held notes; concurrent REC explicitly fails |
| Health CDC | Real nonzero physical-error count, followed by stream reset to zero, arrives as a coherent new-epoch snapshot |
| DDR | 265 ordered writes, 4 ordered read/fence responses through the single owner-6 channel |
| Consumer directed checks | 11 checks, 9 failed-session cases; enable-edge sample, normal STOP retention, overflow/gap/error/epoch/loss/44.1/race, permanent-loss rearm rejection |
| FFT/score directed checks | Partial FFT window discarded; 128 zero-input bins from a new complete window; all 256 cues execute; broken timebase stops score |
| Stalled lifecycle merge | Existing dedicated real-merge regression: stalled old event cancelled, immediate priority, CPU backpressure, completion handshake, resume |

The parent independently reran the complete runner against the separately prepared
revision-3 reference `custom138k-workstation-v1-d23d498ea824c9f9` in
`runtime-controlled-parent-final`. All metrics match, maintained input hashes
agree, and inputs were unchanged. The separate parent source-set and verification
hashes are recorded in the machine evidence; path/reference differences make its
source-set identity distinct.

There are zero warnings in the new wrapper, consumer and fixtures and no
`UNOPTFLAT`; inherited DSP/vendor warnings remain in the hashed compile log.
The real native DSP, official DCS simulation primitive, serial I2S, actual
observation FIFO and existing capture/FFT/score blocks are compiled. DDR uses
an ordered functional memory model; TF uses a coherent same-domain fixture.
Qualification windows and DAC startup are shortened for this integration test;
production startup was covered separately by the runtime-audio stage.

## Remaining validation

This is offline functional and physical-interface simulation, with no claim of
wrapper synthesis/P&R, routed timing/CDC/PLL/resource acceptance, board top
selection, SRAM deployment or Flash deployment. The new caller must handle the
explicit media failure outputs and atomic display tags. Physical held-payload/
Gray constraints, TF file-bridge composition and recording-object metadata stay
separate integration work. The wrapper does not turn source implementation or
APB ACK into physical hardware acceptance.
