# Unselected native TF direct composition v1 — source stage

This stage composes the native file/SPI/FAT owner with the versioned strict
WAV/PCM direct ingress through their public ABI. It adds one accepted command
slot and command/session fencing. Neither dependency changes, no profile selects
the composition, and the selected workstation's existing TF DDR path is retained.

## Source identity and boundaries

The source commit and exact hashes are recorded in the external delivery receipt
`tf-direct-native-integration-v1/final_verification.json`; its one-time byte seal
is `seal.json`. The isolated clone started at `045aa86`, imported file owner
`f317bf1fdf1ecb970bf12631e0664304b5a34614` as local `d58a8eb`, and direct ingress
`195050ead3f27da69df66584f73009c3b69d2584` as local `a7cc8e8`. The new composition
commit contains only the wrapper, contract, integrated fixture/runner and this
report. The two imported deliveries' 18 files remain byte-identical. Their
provenance, patches, licenses, prior tests and reports are retained.

`workstation_tf_direct_native_v1.sv` has one intended 50 MHz clock/reset and
exactly seven elaborated RTL instances: wrapper, native file owner, native
sector reader, SPI session, direct ingress, strict WAV decoder and strict parser.
No alternate SD owner, DDR API/request generator, clock generator, CDC or source
selector belongs to this boundary. No baseline, build configuration, clock or
timing constraint was changed.

Acceptance freezes track, generation and expected rate. Only the file owner's
real `track_applied` starts the new ingress; old local PCM remains live until
that drained boundary. A pending invalid track receives one failure terminal
even though no application pulse exists. Stop wins application/error, clears
pending commands and masks local file/PCM paths. A one-cycle stop fences new
commands until the actual native payload/CRC cancellation acknowledgement.
Local decoder/rate/underrun failures stop and drain the owner, then allow a new
explicit request. Native transport/file errors remain sticky and reset-only.
Card return, stop release and failure alone cannot replay a track.

Independent real-wire review reproduced two stop-wait deadlocks in the initial
unselected wrapper: external stop after local-failure drain, and stop coincident
with its actual ACK. The fixed wrapper uses retained real quiet proof while
failure stop remains held and lets the same-edge ACK win wait-latch arming.
Separate `stop_completed_o` and `stop_failed_o` report the explicit stop
operation; raw `cancelled_o` is never fabricated. Overlapping failure/held stop
keeps one uninterrupted native stop level. A new accepted session clears the
quiet proof. Dedicated positives and bounded mutants cover readiness and these
terminal semantics, including reset-required native error.

## Offline evidence

The accepted external run is `evidence/final-v5/verification.json` and
`final-v5.log`. Reproduce in a fresh output directory with:

```sh
python3 -B projects/138k/push2_workstation/usb_a/sim/tf_audio/run_workstation_tf_direct_native_wire.py --output <new-dir>
```

All 24 real-wire cases pass. Eight cover FAT16/FAT32, superfloppy/MBR and
48/44.1 kHz with fragmented, multi-sector files. Sixteen controls cover full
pause backpressure, live switch with generation wrap, pending cancellation,
stop during payload, a full one-cycle stop, removal/reset recovery, pause/probe
removal, wrong rate, truncated WAV, invalid track terminal, simultaneous
stop/application, empty-file application/EOF, simultaneous stop/file error and
default-FAST12 persistent supply shortage with drain/explicit recovery, stop
after an already acknowledged failure drain, stop coincident with that ACK and
local failure overlapping held stop.

The card model handles actual SPI edges and sparse FAT data/metadata sectors;
the unmodified real owners and strict WAV kernel feed independent Python PCM
oracles. The second track has distinct inverted payload to detect stale frames.
No DUT force/deposit, session stub or direct file-byte injection substitutes for
the integrated path. Every positive case has nonzero CMD17, metadata, file data
and PCM traffic. Held PCM, exact local `last`, snapshots, stop/error priority,
deadline continuity and finite capacities are checked.

The fixture's independent 50 MHz fractional scheduler has an exact average
44.1/48 kHz rate and continues through owner reset, pause, stop and SPI waits.
This is a same-domain local deadline stimulus; it is not a physical serializer
request or proof of downstream consumption. Cross-session fixture peak counters
retain capacity evidence after the owner resets per-session high-water values
at the recovery track's application.

The 24 positives transfer 47,697 oracle-checked PCM frames through 526 file-data
sector launches, 1,133 CMD17 commands, 265,475 file bytes and 76,255 local
deadlines. The fixture evaluates 17,120 explicit checks, including per-cycle
stop-drain fencing checks; these are evaluations rather than unique properties.
Pause reaches PCM4096 and byte4002. The default FAST12 case reaches PCM3094,
transfers 7,790 frames before real underrun, receives its real cancellation
ACK, then completes the explicit 97-frame recovery track. Across the suite,
explicit stops produce nine successful operation terminals and one native-error
failure terminal, distinct from twelve raw owner cancellation ACKs.

Eleven behavioral mutants are rejected by specific bounded assertions: raw caller
pins bypassing snapshots, cancelling before actual apply, removing failure-drain
admission, omitting invalid-slot terminal, removing stop-wait fencing and
unmasking EOF during stop, rearming held failure stop and rearming stop on an
actual drain ACK, releasing overlapping failure stop, omitting the cached
stop-completion terminal and omitting the file-error stop terminal. A twelfth
structural control elaborates an extra synthetic DDR requester and the closure
check rejects it. The closure is parsed
from actual elaborated module/port scopes for every positive case. The retained
real legacy service's DDR output is a separate source-interface positive control;
it is not a legacy traffic simulation or whole-workstation owner4 trace.

The 17 accepted-source boundary tests pass. File-owner forward/reverse ledger
reconstruction and both strict WAV derivation patches reproduce exact bytes.
All four accepted/resource profiles and `build.py` are unchanged. Lint reports
zero warnings owned by the new wrapper; existing frozen dependency width
warnings are recorded explicitly in the primary result and not hidden by edits.

## Throughput, physical EOS and remaining gates

Default FAST12 and byte4096/PCM4096/prefill3072 are unchanged. FAST2 fixtures
validate digital protocol/flow behavior, not real-card IO or throughput. The
separate actual FAST12 case retains a real post-prefill underrun with one-sector
clusters and a FAT read after each cluster. It must report failure code 6,
drain the active native transport and recover only on a new explicit request.
Bounded buffering does not cure this permanent supply deficit. No healthy-card
50 ms guarantee, measured real-card cumulative-deficit budget, physical BSRAM
cost or routed timing result is claimed.

Decoded EOS and local-tail-drained only describe this source-domain parse and
consumer boundary. The last sample has not crossed the 50/compute shallow
bridge, final router, PCM return bridge or real I2S serializer in this stage.
Physical success still requires the ordered last marker to bind to the final
router-assigned epoch/sequence and a matching real completed serial frame,
without session cancellation, frame error or observation loss. That protocol
belongs to a subsequent versioned component/fixture, then the unique workstation
audio owner; local drain must never stand in for physical EOF success.

No whole-workstation owner4 slot/core/native zero-DDR trace, real-card trial,
implementation/CDC/PLL/physical resource check, EDA build, SRAM programming,
Flash operation or hardware acceptance occurred. This source stage does not
complete M03, D random access or long recording. Rollback is to omit the new
unselected composition commit; existing selected paths and sealed owners retain
their prior identities. Parent owns independent replay, integration, staged
pushes and separately qualified candidate/hardware work.
