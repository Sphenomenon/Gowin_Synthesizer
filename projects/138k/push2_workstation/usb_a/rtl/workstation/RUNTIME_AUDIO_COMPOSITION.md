# Native runtime audio composition

`workstation_runtime_audio.sv` is an explicit opt-in owner of composition and
readiness. No accepted profile selects it. It connects existing native owners;
it does not generate DSP text, duplicate common parameters or map new CPU/CC
commands. The existing profile/top/source-lock selection is unchanged.

## Owners and clocks

The qualified raw clocks, official GW5A falling-edge DCS, stopped-low proof,
switch state and public committed rate/epoch belong to
`workstation_audio_clock_domain`. Control runs at 50 MHz. The full runtime
`workstation_audio_render_service`, final PCM router and render side of the
frame bridge run on the continuously running 76.8-MHz compute clock.
`workstation_parameters` inside that service remains the sole common parameter
authority. Event layout and lifecycle/PANIC handling are unchanged.

The service opts into both native engines and native effects. Its owner-6
runtime delay DMA runs on the supplied memory clock, with its existing
byte-0x30000000/128-KiB allocation and native **32-bit-word** DDR addresses.
It retains ordered fence readback, both FIFO directions and mutual heartbeat;
the composition creates no new DDR allocation. Memory and compute resets derive
from the common reset, with local synchronized release. Neither domain is reset
by an audio stream switch.

The error-enabled I2S serializer and physical-frame fanout run on selected MCLK.
Only `serializer.frame_*` feeds the default analysis/record fanout. Every PCM,
rate, epoch, sequence and error is unchanged at that fanout. Sink backpressure
increments explicit loss/fault counters and never stalls audio. The fanout has
common reset, so local serializer resets do not erase epoch-change evidence.

## Configuration and the first request

Each new staged `{rate,epoch}` enters one held-word 50-to-compute mailbox. The
source payload stays immutable until a returned toggle ACK. The receiver waits
two request synchronizer edges plus a settling edge, drains the old router and
service, asserts config valid independently of ready, and waits for the
service's **all-engine/all-effect/history ACK**. It verifies the applied rate
before updating its private render context and returning the ACK. This context
is an interface identity for prefill, not a second public rate authority.

The clock transaction publishes the actual new rate/epoch only after prefill
and a completed good physical frame. That ordering requires the router to use
the already acknowledged staged context while the public old context remains
committed. No prefill is relabeled as hardware acceptance.

Selected-domain reset release first synchronizes the returned context-ready
and quiesce flags. It locks the bundled serial rate/epoch while reset remains
asserted, then waits eight genuine selected-clock edges. The bridge's global
release and quiesce synchronizers therefore settle **before** the serializer
can emit its first request. The serial configuration remains locked throughout
the whole old frame in QUIESCE; a new stage cannot reset or retime that frame.
The serializer also retains its own configured-rate latch.

The compute domain registers the AND of bridge, router and real service
quiescence before a two-flop transfer to 50 MHz. The switch also requires the
external media-quiescent ACK. Serializer prefill/running flags cross separately
to 50 MHz and are qualified with the matching atomic context ACK. These are
different proofs; a cancellation response alone is never engine quiescence.

## External contracts

- `request_*`, `switch_permit`, `recover` and `media_quiescent` are already in
  the 50-MHz domain. The caller owns authorization and the TF/record busy policy.
  Denied requests pulse `policy_rejected` without entering the clock transaction.
  Accepted requests remain unqueued and keep existing busy/clock-reject semantics.
- MIDI/PC bytes, CPU events, input PCM, mute and coherent TF packets are already
  in the compute domain. The TF producer must transfer the entire stereo/rate/
  generation/error payload atomically. Its actual asynchronous file transport
  is outside this module. Scope selection and master volume come from the
  authoritative service; final selection/quantization/master gain occur once.
- DDR request/ready/response ports are in the memory domain and retain the
  existing owner-6 queue/ordering contract. Other DDR clients and arbitration
  remain external.
- Tap enable/ready, valid, PCM and metadata are in selected MCLK. Consumers in
  another domain need an entire tagged-payload CDC plus their own window/object
  failure policy. A naked synchronized PCM bus is insufficient.
- All service telemetry is directly exposed, including pitch, public gain and
  route/profile/effects, event health, panel command, scope and TF control. It
  has the original compute-domain meaning; the top must publish coherent display
  snapshots separately. Existing score/extensions and lifecycle adapters remain
  outside this component and must be preserved by any future top integration.

## Failures and reset

Clock loss asserts local serializer reset and physical mute even if MCLK stops
high. The existing clock controller handles qualification, controlled DCS stop,
timeouts and retry of the last committed rate with a new epoch. Common DSP,
held-note and parameter state survive those operations.

The service/DMA's sticky DSP fault, or an impossible context-ACK rate mismatch,
also quarantines physical output and public validity. A new DSP fault pulses
the composition's `failed` aggregate. Existing clock transactions can still
reach their ordinary quiesce/prefill timeout; `recover` only retries the clock
controller. It never clears DSP fault, fabricates readiness or reapplies an
accepted identity. A real coordinated common reset is required for that fault.

The supplied common reset must cover the complete participating compute/memory
system and its clock/DDR readiness. This component is not a replacement PLL or
DDR calibration supervisor. Global reset is distinct from the stream-local
reset; independent peer resets must not silently restart one half of a FIFO.

For a frame canceled by a new PANIC epoch, the service/router/bridge preserve
zero/error to the physical output. A fresh request accepted while already
PANIC-muted is a completed deterministic good-zero slot after the real DSP
result drains. This allows an empty-held-note rate switch to finish normally;
it does not count silent data as evidence of audible synthesis.

## Validation and selection

`sim/audio/run_runtime_audio.py` consumes an exact prepared project's locked
legacy assets plus the listed maintained native owners. It compiles the full
installed official GW5A simulation library, not a replacement DCS. It records
all input hashes and fails if inputs change during the run.

The main fixture uses production 76.8-MHz compute and both real MCLK periods,
the actual full effects/ring sizes and the 40-ms switch-state timeout. Short
qualification windows and three startup frames accelerate fault/stress cases.
`--production-startup` separately restores the default 50,000-cycle/four-window
clock qualification, 500-cycle loss, 16-cycle stop-low, 4-frame PDN and
1,028-frame DAC startup, exercising 48-kHz boot and the first 44.1-kHz switch.

The test uses an ordered functional DDR queue and coherent TF packet fixture;
it is not physical DDR timing, a migrated production TF CDC, P&R, DAC/USB
readback or board acceptance. Promotion requires a new explicit profile/top
revision, exact source/constraints and bitstream identity, preservation checks,
routed timing/CDC/resources and separate hardware evidence. Rollback is to keep
the existing selected profile; this module can remain unselected or be removed
without reconstructing or changing accepted inputs.
