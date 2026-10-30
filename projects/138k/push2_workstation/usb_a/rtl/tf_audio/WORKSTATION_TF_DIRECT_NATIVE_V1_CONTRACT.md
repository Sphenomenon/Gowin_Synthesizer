# Unselected native TF direct composition v1

`workstation_tf_direct_native_v1.sv` composes the independently versioned
`storage/workstation_tf_file_reader.sv` and `workstation_tf_direct_ingress_v1.sv`.
Their contracts remain authoritative for file/SPI/FAT and byte/WAV/PCM behavior.
This module adds command/session sequencing and failure cancellation. It does
not change either implementation or select a profile. The current workstation
still uses its existing selected TF DDR service.

The complete component and its caller use one intended 50 MHz clock/reset. SPI
is driven by the sole native file owner, sector reader and SPI session. There
is no second SD controller, DDR port/client, asynchronous FIFO, source selector,
rate authority, clock generator or physical-frame acknowledgement in this
component. Caller-domain reset is a whole-owner reset, not a CPU observer reset.

## Command and session sequencing

| Interface | Meaning |
|---|---|
| `request_valid_i/ready_o` with track, generation, expected rate | One accepted slot. Hold request payload while valid and not ready. On handshake freeze all three fields; later idle input changes do not replace them. Caller supplies a snapshot of already committed state and cancels if that authoritative context changes. |
| `request_accepted_o` | Same-edge ready/valid acceptance event. It does not mean a file was found, format admitted, PCM prefilled or sound completed. |
| `request_pending_o` | Accepted command awaits the native file owner's actual applied/error/cancel terminal event. Requests are backpressured while occupied. |
| `request_applied_o` | Actual file-owner `track_applied` for the frozen slot, with stop/error fences. This event alone starts direct ingress and commits its held generation/rate snapshot. It means file position applied; format/prefill and playback eligibility remain separate. |
| `request_failed_o`, code | One-cycle terminal result if the accepted slot gets file-owner sticky error without an application event, including invalid track. The slot cannot wait forever for a nonexistent `track_applied`. The native file-error code is retained. |
| `request_cancelled_o` | One-cycle terminal result for a pending accepted slot cancelled by stop. Stop wins simultaneous request/application/error. This command result does not replace the subsequent real transport drain acknowledgement. |
| `stop_i` | Immediately revoke PCM and file admission. Hold stop at the sole file owner and clear local ingress queues. Even a one-cycle stop sets a wait latch until actual payload/CRC drain. Held stop accepts no new command; release does not replay a stopped request. |
| `cancelled_o` | The actual native file-owner drained cancellation pulse. Local queues have already been revoked. A new explicit command can proceed after this event and stop release. No fixed delay substitutes for this ACK. |
| `stop_completed_o` | One-cycle successful terminal for an external stop edge, including an idempotent repeated stop using the retained real drain proof while internal failure stop remains held. It is separate from raw `cancelled_o` and physical EOF success. Repeated stop edges while one drain is pending coalesce into that stop operation. |
| `stop_failed_o` | One-cycle terminal when an external/pending stop encounters native sticky file error, whose code remains on `file_error_code_o`. Transport is failed and whole-owner reset/remount is required; no successful drain is fabricated. Mutually exclusive with stop completion. |

A live switch retains the old ingress generation/queue until the accepted new
file actually applies at a drained sector boundary. This lets already queued
old frames continue in order while the old sector finishes. At actual apply,
old local data is discarded and the new session starts from a complete fresh
WAV header. Only one pending request is accepted, so file-owner latest-request
coalescing cannot detach an index from its generation/rate snapshot. No 18-bit
event or external protocol layout changes.

Requests presented during held stop have not been accepted. The requester must
withdraw a cancelled valid request; a still-asserted valid after ready returns
is a new normal handshake. A valid empty file may produce native apply/EOF
simultaneously, but zero file bytes are malformed WAV; it is not fabricated
empty PCM success. Stop masks that simultaneous application/EOF at the composed
session boundary.

## Failure and recovery

`file_error_o` and `file_error_code_o` remain the native owner's sticky error.
They fence admission and bytes, terminate a pending command and require a whole
owner reset, remount/scan and a new explicit request. Card return alone does not
recover. There is no physical card-detect port; removal is discovered on an
actual command/probe, and fast unseen card swaps remain a documented limitation.
Payload after a token is still not CRC validated; this composition does not
upgrade that transport guarantee.

`ingress_failed_o` and its code remain the direct owner's sticky local failure,
including rate/format errors, overflow and true post-prefill deadline misses.
The composition then holds native stop and waits its real cancelled/drained
state. A new explicit command is admitted only after this drain. That command
releases the internal stop, keeps the old failure/output invalid while the
native owner applies the new track, and clears local failure only on that real
new application. A failure cannot cause an automatic retry/replay. If native
transport also failed, whole-owner reset remains required.

An external stop after that local-failure drain is already acknowledged does
not arm another wait for a native stop edge: internal failure stop is still
held high and no second transport ACK exists. The retained real quiet proof
satisfies this repeated stop. Likewise, an actual cancelled ACK on the same
edge as external stop wins wait-latch arming. Both paths still require a new
explicit command and never manufacture a second `cancelled_o` pulse. They do
produce the explicit stop operation's separate `stop_completed_o`, so a caller
does not wait forever for a second raw transport edge. Acceptance clears the
quiet proof and releases failure hold, preventing reuse for a newer session.
Overlapping local failure and held external stop keep one uninterrupted native
stop level through its real ACK; release cannot create a second drain operation.

`pause_i` only affects the direct consumer. It preserves the exact queued head,
does not change generation or re-run prefill, and can fill bounded PCM/byte RAM.
Backpressure reaches data-sector allowance; native FAT/probe bytes remain
metadata and never enter WAV. One full 512-byte data sector plus two pipeline
positions is reserved before every launch, including a partial final sector.
Real file EOF after the final FAT/EOC check retires unused final reservation.

`sample_request_i` is a qualified deadline event in this same domain, unrelated
to SPI waiting. The caller continues its schedule through pause, stop and
failure. This module does not create/gate a sample clock, stop the external
scheduler or backpressure audio timing. Only file rate matching the committed
session snapshot is accepted; there is no SRC.

## Local EOS and DDR scope

Held PCM16 stereo pairs and `last` come directly from the versioned strict WAV
path, after complete RIFF/chunk/frame checks and tail metadata. `decoded_eos_o`
is validated local parse completion. `local_tail_drained_o` only means the marked
last pair transferred to this same-domain consumer. Neither status is final
I2S completion, release of a downstream frame bridge, physical success or an
implicit command to stop a different clock domain.

Later integration must version `last` across the shallow tagged frame bridge
or use a bounded ordered tail-token protocol. The final TF transfer must be
associated with the final router's assigned epoch/sequence, then confirmed by
matching real serializer completion without cancellation, frame error or
observation loss. This component performs none of that cross-domain protocol.

The no-DDR assertion is specifically the elaborated component boundary: seven
RTL module instances (composition, file owner, native sector, SPI session,
direct ingress, strict WAV decoder and parser), zero DDR request ports and zero
DDR request-generator instances. The SPI/FAT/WAV/PCM fixture is active and has
nonzero actual CMD17/data/metadata/PCM traffic. A synthetic elaborated extra DDR
requester is rejected as a scope negative; the real legacy TF service's DDR
interface is retained as an independent nonempty source-interface control.
This does not prove selected workstation owner4 slot/core/native counts or
contention behavior; no profile/top/arbiter has been changed.

## Configuration and validation limits

Default SPI_FAST remains 12 and storage is byte4096/PCM4096/prefill3072, inherited
as explicit source parameters. Bounded buffering cannot fix permanent supply
shortage, particularly one-sector clusters requiring a FAT read after each data
sector. Digital fixtures using FAST2 only validate protocol/flow behavior and
are not a real-card throughput/IO qualification. The regression separately
retains default-FAST12 continuous-supply failure and explicit recovery; no
healthy-card 50 ms budget is claimed. Actual measured cumulative deficit,
recovery rate, physical RAM cost, routed timing/CDC/PLL and hardware remain
separate gates.

Use `sim/tf_audio/run_workstation_tf_direct_native_wire.py --output <new-dir>`.
It drives actual SPI edges into sparse FAT16/FAT32 superfloppy/MBR volumes,
fragmented multi-sector WAV files, full PCM oracles and public controls only.
No DUT register force/deposit, alternate session stub or direct file-byte
injection substitutes for the integrated data path. Profile selection and
physical deployment remain outside this source stage.
