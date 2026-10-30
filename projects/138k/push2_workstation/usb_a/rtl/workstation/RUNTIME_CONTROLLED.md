# Native controlled runtime boundary

`workstation_runtime_controlled.sv` is an explicit opt-in composition above
`workstation_runtime_audio.sv`. The explicit custom-workstation revision-4
composition selects it; accepted, pinned and unspecified-profile entries keep
their own sources. Changed inputs require a new source lock and candidate, and
source composition does not establish deployment acceptance.
Its compute clock remains continuous 76.8 MHz; the
selected 12.288/16.9344 MHz clock drives only the physical audio side. Source
selection and the remaining physical integration require a new candidate.

## Owners and compatibility

`runtime.service` owns the only event workstation, session and committed
parameters. UART MIDI at 31,250 baud and PC MIDI at 115,200 baud each keep the
existing eight-bit CDC. The PC framing sticky bit, UART CDC-drop indication and
decoder-overflow bit retain their existing `pc_health` positions. USB and CPU
service events share the existing fair `gw138k_usb_lifecycle_merge` with
`EXPLICIT_LIFECYCLE=1`, including its unbuffered lifecycle/cancel lane. There is
no second event workstation or legacy controlled adapter.

The PC CDC-drop indication is reduced from the binary counter and registered
at 50 MHz before its two compute-domain synchronizer stages. This adds one
source edge; it retains the existing `count != 0` behavior, including counter
wrap, rather than introducing another counter or a new sticky authority.

The native exact controlled-services copy retains its APB register map, panel
score/record toggles and 448-bit performance word:

```text
{0x43545231, snap_sequence, snap_right, snap_left, snap_status,
 control_pitch, control_options, held_notes[127:0], pc_health,
 control_state, applied_events}
control_state = {master_volume[15:0], voices[5:0], profile[2:0],
                 route[1:0], mode[1:0], effect_mask[2:0]}
control_pitch = {panic_epoch[9:0], pitch[21:0]}
```

The existing APB CDC captures a held request into the compute domain and gives
the service predecode registers one cycle before `command_valid`. `preset_n`
resets only this CDC and CPU services. It does not reset UART inputs, merge,
runtime DSP, notes, parameters, serial audio or physical observation.

The wrapper exports `runtime.delay_dma`'s owner-6 DDR channel directly. Addresses
are native 32-bit words under `ddr_address_map.vh`. It adds no DDR client and
does not instantiate the legacy delay DMA alongside the runtime DMA.

| Port group | Clock domain |
|---|---|
| I2S pins, `frame_*`, raw per-epoch `underrun_count` | selected MCLK, which may stop |
| Event input/ready, parameters, `pc_health`, observed PCM/sample-valid, FFT, REC, score | continuous compute |
| DDR request/response | memory |
| APB bus request/response | `pclk` |
| Clock requests/status, display tuple and tags, effect projection, MIDI UART framing/drop counter | 50 MHz |

The CPU service sees an atomic compute-domain health snapshot, rather than the
raw `underrun_count` port. External users of a raw per-epoch counter must also
cross it as a snapshot; it is not a monotonic common-reset Gray count.

## Switch policy and concurrent media

`request`, requested rate, caller permit, recover and media-quiescent inputs
remain 50-MHz interfaces. The caller must pulse a request, observe acceptance
and await `applied` or `failed`; no rate command is invented in CC/APB.

The wrapper registers the compute-domain busy proof (`record_enable`, running
score, TF active or TF busy). That proof asynchronously asserts a conservative
50-MHz inhibit; deassertion requires three destination clocks. A request while
inhibited generates `policy_rejected` without entering the clock transaction.
`switch_block_reason[3:0]` supplies synchronized diagnostic levels
`{TF, score, REC, !caller_permit}`; reason levels can lag the inhibit. The
three compute-domain reason levels are registered before their two-stage
50-MHz crossing, adding one compute edge of diagnostic latency. Their TF
reason combines active and busy locally; these diagnostics never authorize
the switch, which continues to use the separate registered busy proof.
The runtime's `rejected/reject_code` describe clock-transaction rejections, while
`policy_rejected` describes this pre-transaction policy rejection. Failed REC
with `record_enable=1` continues to inhibit switching until software disables
it. TF busy includes file work even when no source sample is currently active.

The reciprocal race is explicit: a clock transaction already in progress is
synchronized into the media consumers. The public clock-owner `busy || quiesce`
union is registered at 50 MHz; that single source flop asynchronously asserts
the compute inhibit, whose release waits for two compute edges. The source
register resets asserted under the local 50-MHz reset; the compute stages reset
to `11` under the local compute reset. The extra source capture adds one
50-MHz edge before assertion/release; another two assertion capture edges
would let an in-flight frame-zero score end without its failure being latched.
Only the release uses those two stages. This avoids a combinational multibit-FSM
decode as the CDC source without redefining the owner's public busy/quiesce
outputs or success ACK.
A new recording fails with code 7; a
new score start is rejected and sets `score_failed`. An already-running media
consumer also fails/stops if this condition arrives. This is an asynchronous
boundary, so the software/caller should serialize launches for a successful
operation. A command's old APB ACK is still command acceptance, not successful
completion of recording or score playback. Source faults and a changed physical
epoch remain independent termination conditions, covering the remaining CDC
latency. No old packet layout is expanded to pretend these are existing MMIO
fields; the new failure outputs require explicit caller integration.

## Physical observers and consumer failure

The default source is `runtime.frame_*`, the completed physical I2S frame.
`compute_render_done` is not connected to any observer. The maintained 98-bit
observation bridge carries `{rate, epoch, sequence, error, stereo_pcm16}` into
compute and converts signed PCM16 to Q1.31 by appending 16 zero bits. The
serializer is never backpressured. The raw bridge and its persistent loss
telemetry are documented in [PCM_OBSERVATION_BRIDGE.md](../audio/PCM_OBSERVATION_BRIDGE.md).

`workstation_observation_consumers.sv` retains the real FFT256, 96-bit capture
FIFO and 256-cue score player. Its first frame establishes context. A later
rate/epoch change, sequence gap, physical error or observation drop:

- immediately hides pending FFT bins, resets its partial/finished window and
  resumes only with a complete new window; bins carry `fft_44k1`, `fft_epoch`
  and `fft_context_valid`;
- invalidates and flushes an active recording, latching failure until software
  has observed it and disabled recording; no automatic resume yields a
  successful partial object;
- stops a score, clears LEDs, suppresses completion and sets `score_failed`;
  downloaded cues remain stored and an explicit later start can clear failure.

`destination_drop_event` reports new loss. If its 32-bit source-drop counter
has saturated at `0xffffffff`, loss remains asserted permanently until common
reset. Disable/re-enable cannot make a saturated, unobservable stream trusted.
It also prevents new score starts and FFT windows from appearing trustworthy.

The old capture packet remains exactly `{local_sequence32, left_q31, right_q31}`.
It has no rate, epoch or error metadata. This wrapper deliberately admits only
48 kHz recording; enabling it on a 44.1-kHz physical stream fails explicitly.
Normal `REC_ENABLE=0` stops writes and **retains readable queued packets**, as
required by the existing firmware's stop-then-POP/READ/RELEASE sequence. A good
frame sampled with `record_enable=1` is accepted without a reset-release bubble.
If an APB write changes the enable output on that same edge, the frame saw the
previous enable value and precedes the new session; the next physical frame is
the first eligible one. STOP uses the same edge convention. A FIFO overflow
fails and flushes the active object. The default FIFO
retains its 256-packet capacity; it is not a long recording backend.

| Recording failure code | Cause |
|---|---|
| 1 | physical rate/epoch changed |
| 2 | physical sequence gap |
| 3 | physical frame error |
| 4 | observation CDC loss, including permanent counter saturation |
| 5 | unsupported 44.1-kHz legacy capture format |
| 6 | capture FIFO overflow |
| 7 | recording overlaps an already-started clock transaction |

`record_drop` is a saturating lower bound on lost/rejected capture packets: one
increment terminates each newly failed active session, and later frames are
ignored. It is not the full number of samples after the failure. Explicit
`record_failed/code` are the result authority; the old APB record-status bits
are not redefined. A CPU's already-popped snapshot is still CPU-owned historical
data and does not become a valid recording object when the session fails.

Score cues remain absolute **physical frame counts**, not milliseconds. Both
rates retain 256 cues, but a running score blocks a deliberate rate switch.
No 44.1-kHz recording file/object or 138K BLE recorder integration is claimed.

Display PCM comes from the same physical observation and crosses as one complete
194-bit tuple to 50 MHz: the physical rate/epoch/sequence/error accompany the
existing 128-bit PCM/reference/voices/health projection. The caller must use
these atomic physical tags; it cannot append the current public rate to old
PCM, or label 44.1-kHz PCM with a fixed-48-kHz display packet. Its reference/revision, voice mask and core health are
sampled at compute observation time; they are telemetry, not additional
authoritative parameter state or a historical per-render voice identity.
Serializer health counters reset per epoch, so they cross in a separate held
96-bit `{epoch, underruns, source_errors}` completed-frame snapshot. They never
use unit-increment Gray counter CDC across the reset jump. CPU/display counters
are the last received snapshot and can lag; `health_drop` separately counts
missed health snapshots. A stopped clock's final completed frame is not assumed
to have crossed; clock fault and consumer abort remain separate evidence.

## Verification and remaining integration

```sh
python3 projects/138k/push2_workstation/usb_a/sim/audio/run_runtime_controlled.py \
  --project <explicit-clean-prepared-Prj1> --output <new-output-directory>
```

The runner uses real APB/services, both UARTs, fair merge, native DSP, owner-6
DMA, official DCS simulation primitive, I2S serializer, physical PCM CDC and
real FFT/capture/score consumers. A separate consumer TB checks context failure,
stop-first firmware reads, enable-edge capture, FFT restart and all 256 cues.
It also checks switch-coincident score start and final-cue suppression. The
controlled TB checks source-register edge timing, the added switch-launch
edge, a real UART drop-counter carry with compute stopped before audio boot,
TF busy-to-active diagnostic handoff, and actual APB REC/score races across
both physical rates. Ideal RTL assertions do not model gate-delay glitches,
metastability or routed CDC.
`--inflight-score-boundary` additionally aligns a real in-flight APB score start
to the first compute edge after rate-request acceptance with a frame-zero cue.
It requires explicit failure and also rejects a temporary source-registered
two-capture-edge bridge copy, which loses that terminal result. This negative
control reproduces functional latency, not an analog CDC fault.
Inputs and the prepared reference identity are hashed and must remain stable.

This is source and offline functional verification. Reprepared full-profile
source identity, held-payload and Gray physical constraints, routed
timing/CDC/PLL/resource gates, complete firmware failure-result handling,
recording-object metadata and hardware acceptance remain separate work. This
component does not program SRAM or Flash and does not reuse an accepted identity.
