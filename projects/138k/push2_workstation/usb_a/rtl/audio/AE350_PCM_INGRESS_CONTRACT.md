# AE350 decoded PCM ingress, source stage v1

This contract is the F8060000 **byte-addressed APB page** owned by
`workstation_ae350_pcm_owner.sv`. It is an explicit, disabled-by-default
candidate (`WORKSTATION_AE350_PCM`, `ENABLE_AE350_PCM=1`). It does not change
accepted profile identities, the existing 18-bit event format, parameter
ownership, PANIC semantics, DDR allocation, or the F803 physical-clock owner.
A fresh source-locked integration candidate must select its sources, merged
HCI wrapper ports and new CDC constraints before synthesis or board acceptance.

## Composition and clock ownership

The CPU supplies actual decoded PCM16 blocks; this PL owner holds the only
committed block queue, stream identity, source selector and adaptive-SRC state.
A native `gw138k_apb_cdc` crosses **whole held commands** into the compute
clock. Its CPU reset revokes the old stream without resetting audio parameters,
held notes, DSP, or the physical sample schedule. CPU RAM pointers never cross.

Selected stereo samples enter `workstation_audio_render_service` at its
existing PCM input, before its gain/mixer and existing delay/chorus/reverb.
The existing `workstation_final_pcm_router` owns the sole final master volume
and retains TF selection. It receives `{pcm_cancel_epoch[21:0],panic_epoch[9:0]}`
as its internal cancellation token; this is not added to the 18-bit event ABI.
Source history clearing uses the existing DSP request/acknowledgment, with
configuration priority explicitly respected. Held notes and common parameters
survive source changes. The existing PCM gain CC16 still applies, including its
normal ramp; Bluetooth does not create a parallel gain/parameter authority.

F803 still seals recording and stops TF before a physical rate switch. A
nominal 44100/48000 change must use that service, wait for actual applied
rate/physical epoch, then ARM a fresh stream. F806 never initiates a physical
rate switch. TF becoming active/busy or a switch starting terminates Bluetooth
and returns to legacy after history clearing. It never changes TF ownership.

## Queue and publication

There are four slots of 128 interleaved stereo frames, totaling 2048 bytes;
no DDR is allocated. A word has signed left PCM16 in bits15:0 and signed right
PCM16 in bits31:16, matching little-endian C stereo. CPU duplicates mono.
Window offsets are 800–9ff, a00–bff, c00–dff and e00–fff (hex).

Only FREE slots are writable; only aligned, full 32-bit stores are accepted.
COMMIT requires every word `[0,frames)` to have been written since that slot
was freed. It publishes the whole immutable slot. A slot returns to FREE only
after its last input frame is **consumed**, not when prefetched by the SRC.
FIFO slot order is 0,1,2,3; block sequence starts at zero, increases by one,
and refuses `ffffffff` rather than wrapping. Full/busy rejection never
replaces committed data and increments overflow-attempt telemetry. Simultaneous
publication and consumption combine both occupancy/ownership updates.

The CPU keeps the complete private decoded block until acceptance, writes a
bounded slice per pump, and commits only after all stores. A failed/uncertain
command is not safe to replay blindly: read accepted command ID and authoritative
queue/key/sequence facts; otherwise cancel/fence and start a fresh stream.

## Identity, source selection and failure

ARM locks `{controllerEpoch,PLClassicGeneration,ClassicStreamEpoch,rateHz,
physicalAudioEpoch}`. Live PL and physical context must match; the source must
be legacy and no history/source operation may be pending. Stream epoch must
be nonzero and strictly increase within one controller/PL-generation key.
A real new controller/generation can restart at nonzero1. The retired key is
not cleared by CPU-interface reset. Command IDs and the internal 22-bit cancel
identity refuse wrap; exhausted identity requires the containing audio-owner
reset, not a CPU reset.

SELECT_BT requires at least256 queued input frames, a valid interpolation pair,
a live matching context and no TF/switch. It holds future serial delivery,
clears effect history, changes selector after ACK and reports applied source
command ID only at the **first actual renderer sample acceptance**. Accepted
command ID is distinct from applied source-command ID.

CANCEL must match the complete staged key. It may preempt a pending SELECT or
history operation; a matching already-canceled stream is idempotent. A stale
key only rejects and cannot cancel a newer owner. SELECT_LEGACY and cancellation
flush the old queue; neither automatically restarts Bluetooth.

CPU reset, PL session revocation, physical context change, TF preemption,
underflow, matching malformed descriptor/sequence, or failed history completion
terminate the stream. Old PCM becomes unusable immediately; queue ownership is
cleared and DSP history is cleared before returning to legacy. Missing source
samples are never filled by replaying a previous sample. A stale other-key
COMMIT only rejects. A matching bad descriptor/sequence terminates that owner.
History timeout is a sticky hard fault that retains serial hold/quarantine.
A fresh ARM can clear an ordinary old-stream failure after retirement; the CPU
must not interpret the failed bit as a requirement to reset all audio owners.

The serializer completes the current whole physical frame, discards cached
following samples and late old replies, and continues sequential zero/error
slots while held. It suppresses new requests through two complete boundary
guards after release. Clocks and slot sequences continue. These intentional
zero slots increment the ordinary underrun counter; this source stage does not
claim a zero-underrun source transition.

## Adaptive stereo SRC and truthful capabilities

A shared Q24 phase linearly interpolates both channels from synchronous
prefetches, consumes zero/one/two input frames per output sample, and preserves
slot boundaries. A 1024-output-frame occupancy average targets256 input frames.
The PI term uses proportional512 and integral8 Q24 units per error frame;
correction clamps to ±33554 Q24 units (approximately ±2000 ppm) and slews by at
most1024 Q24 units per1024 output frames (approximately61 ppm per window).
Interpolation truncates the fractional result toward negative infinity. The
same phase/step is used for left and right; no independent channel correction.

CAPS bit0 queue, bit1 history/source owner, bit2 adaptive linear SRC implemented,
bit3 sustained/drift plus full system service-budget accepted, bit4 measured
total delay valid, bit5 stereoPCM16, bit6 both nominal rates. **Current CAPS is
0x67: bit3 and bit4 remain false.** Four actual RTL runs of576000 output frames
at nominal44100/48000 and ±2000ppm with block jitter, each exceeding FIFO-sized
accumulated drift, verify the algorithm in isolation. They do not prove CPU
HCI/SBC pump budgets, routed CDC/timing, uninterrupted physical playback or
whole-workstation sustained operation. Do not set bit3 from those tests alone.
Queue delay is real queued input frames including prefetched frames. Total
DSP/output delay is unknown and its validity register is zero; zero is not a
measured total latency.

## Register map

All offsets are hexadecimal bytes. Registers not marked writable are read-only.
Unknown/misaligned addresses, partial stores, and illegal commands return error.

| Offset | Meaning |
|---|---|
|000 /004|ID `50434d31` / version `00010000`|
|008 /00c /010|CAPS / STATUS / failure reason|
|014 /018 /01c|FREE_MASK low4 / queued input frames / next block sequence|
|020–030|Writable staging controller, PL generation, stream epoch, rate, physical epoch|
|034 /038 /03c|Writable staging slot / frames1..128 / block sequence|
|040|Writable command:1 ARM,2 COMMIT,3 SELECT_BT,4 SELECT_LEGACY,5 CANCEL|
|044 /048 /04c|Last accepted command ID / applied source-command ID / source0 legacy,1 BT|
|050|SRC step Q24|
|054 /058|Minimum / maximum queue watermark while selected|
|05c /060|Consumed input / output frame telemetry|
|064 /068 /06c|Required prefill256 / queued delay frames / total-delay-valid0|
|070 /074|Actual compute-context rate / physical audio epoch|
|078 /07c /080|Live PL generation / controller epoch / active stream epoch|
|088 /08c|Saturating underflow / overflow attempt counts|
|800–fff|Four writable FREE-slot windows|

STATUS bits0armed,1BTselected,2prefillReady,3streamFailed,4sourceCommandPending,
5historyPending,6contextReady,7PLlive. Failure reasons1CPUreset,2session,
4underflow,5descriptor,6sequence,7physicalContext,8TF,10historyTimeout.
Input-frame telemetry wraps naturally at32bits; command and block identities do
not. Watermarks are512/0 before any selected sample observation.

## CDC review and remaining physical gates

The HCI wrapper provides one registered 50MHz `classic_ready_o`. While high,
epoch/generation are immutable; every key change holds it low for at least one
whole source cycle. Disconnect, fence, CPU observer reset and overflow revoke
at the dispatch edge. A decoder-internal newly raised fault can revoke one
further50MHz cycle (20ns) later. This bounded source delay is part of the
contract; no combinational multi-bit asynchronous reset is used.

`workstation_ae350_pcm_session` asynchronously closes `live_o` and its release
pipe on that registered ready level, then waits three compute synchronizer edges
and captures the tuple at a fourth edge. Source data never drives asynchronous
reset. Actual source registers relative to `u_bluetooth` are
`u_core/initializer/boot_id[63:0]` and
`u_core/owner/flow/{generations[0..1],active,is_le}`; output tuple uses muxes.
`u_core/owner/{published_epoch,published_generation}` are comparison state, not
the actual tuple sources. Ready source is `u_core/owner/classic_ready_o`.
Destination under `u_managed/runtime/cpu_pcm/session` is the epoch/generation
capture. A fresh synthesis must enumerate the real mux source endpoints and
all destination bits, bound held data propagation before capture, and audit
registered ready→async-close plus synchronizer release/recovery paths. RTL
hierarchical names are proposals until resolved against the sealed netlist.

Also audit the new APB held-command bridge, CPU reset→stream revoke,
`switch_inhibit_50`→compute inhibit and owner hold→selected-MCLK hold crossings.
No new blanket false path or relaxed audio clock is supplied by this source
stage. Actual endpoint coverage, constraints, routed propagation/setup/hold,
resources, full service budget, HCI/SBC integration, hardware audio/tap evidence
and a separate deployment identity remain required before physical acceptance.
