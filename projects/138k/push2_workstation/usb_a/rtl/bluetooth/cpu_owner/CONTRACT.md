# AE350 BLE business owner, revision 2

Only the explicit `custom138k-workstation-ae350-business-v1` profile, revision 2,
selects this native composition and `ae350_ble_business_owner_v2` policy. Its
selector copies versioned bytes and removes staged `ble_recording.v`; no legacy
recorder text generation runs. Existing default/accepted profiles, vendor and
25K bytes retain their selection. The profile has a new source/candidate
identity; first-batch evidence remains fixed to its recorded source commit.
`provenance.json` preserves the one-time derivation and protected encoder,
transfer-bank and wire-message hashes.

## Ownership

`ble_business_owner.c` solely owns eight operation tasks, monotonic operation /
object / transfer IDs, START/STOP/GET/CLEAR, all OPEN modes, READ/ACK/combined
ACK, explicit resume offsets, CLOSE/CANCEL, pending/confirmed offsets, duplicate
ACK identity and the 30-second transfer policy. There is no hardware task table,
ID allocator, confirmed cursor, pending-ACK cursor, last-ACK record or transfer
timeout. The physical engine holds C-supplied borrowed object/data tags.

The FPGA retains fragment/CRC/nonce/session validation, the original 32-slot
request/reply cache, exact wire replay detection, S1a transport and link limits.
It also retains autonomous capture, four-byte PCM CRC, media seal, native drain,
raw DDR/cache fetch, Rice, transfer RAM and wire framing. C never copies PCM or
performs a sample/codec loop. The protected codec and frame-byte implementation
remain byte-identical to the locked legacy data plane. Audio has no CPU-ready
signal; paused/faulted software cannot stop capture or hardware media sealing.

The independent R00 `f8040000` object64/first 64-KiB window remains separate.
BLE uses the existing second 64-KiB window from `ddr_address_map.vh`: byte
`0x30510000..0x3051ffff`, native words `0x0c144000..0x0c147fff`, 16,384 stereo
frames at the existing format-1 48 kHz. No DDR allocation, external wire opcode,
18-bit event field, capacity or dual-rate BLE capability changes.

## Commands and download lifecycle

The unchanged S1a slot transports one already-validated 16-byte command and a
64-byte result. Admission, CLAIM, application and publication are separate.
START PENDING requires actual raw START acceptance; its task succeeds only at
an actual complete first frame. STOP waits for READY and the native committed
prefix; zero-frame START fails after terminal sealing. Task retention uses
physical first-frame/terminal timestamps. CLEAR waits for actual raw completion.

OPEN is a C operation: it validates immutable object, subscription, physical
buffer availability, explicit aligned byte offset, mode and ID exhaustion. Its
response preserves negotiated limits and flags. CLOSE requires no pending ACK,
confirmed EOF and the object CRC. CANCEL retires the C lease. Resume uses a new
monotonic transfer ID and the caller's explicit verified checkpoint offset.

READ validates mode, transfer, window-one ownership, confirmed offset,
alignment, range and the negotiated limit. Combined ACK validates both the old
block identity/CRC and the next range before submitting anything. A physical
READ descriptor contains object/tag, request/nonce, offset/length and borrowed
frame mode bits; the engine checks physical identity and memory bounds. It
reports actual read admission, actual PCM CRC completion and immutable echoed
identity. C commits a combined ACK only after read admission. A later physical
failure can retain the already-committed prior ACK; it cannot fabricate a new
CRC-complete block. A descriptor accepted by APB but rejected before physical
read admission cannot commit that ACK.

ACK compares the actual pending block end and PCM CRC. A fresh request with the
last accepted ACK pair is idempotent. Failed ACK/combined requests do not mutate
confirmed or pending state. OPEN and accepted READ/ACK refresh the C deadline;
wire replays do not refresh it. Unsigned subtraction handles elapsed-ms wrap.
At the first pump observing 30 seconds, C expires the lease and its mode/ACK
policy. If CPU service pauses, bounded physical data may remain buffered until
transport consumption/disconnect; the next pump rejects expired lease commands.
This is not a hardware interrupt or a claim of CPU-independent business service.

Nondata exact replay still returns the hardware cache without calling C. For
data replay, the parser first compares every original request byte, then offers
the original command through S1a. On admission, the physical service latches
only the replay flag and cached object tag. Its read-only mirror exposes the
current slot's existing full ticket/owner/session/boot key. C's bounded INSPECT
phase matches that complete key before using the replay metadata. No S1a ABI or
reserved field is changed. A mismatched/torn key is retried for at most 1000 ms,
then fenced without a primitive. Data replay rebuilds the original borrowed
request/tag without changing the current C lease, ACK cursor or ID counters.
Legacy mode checks, downgrade/reopen behavior and raw replay after timeout are
preserved. Cleared/replaced objects are rejected by C before physical submission.

## APB physical primitive v3

`f8050000..ff` remains S1a. `f8050100..1ff` is independently probed as physical
ID `52434403`, caps `00301002` (48-byte result, 16-byte payload, one descriptor).
It is not R00's API. Misaligned/unknown accesses, partial writes, invalid flags,
reserved bits, stale/zero sequences and unavailable submissions return APB
error with immediate local ready. Accepted descriptors remain immutable even
while later staging registers are written. No bus access waits for radio/DDR.

| Primitive offset | Meaning |
| --- | --- |
| 00 / 04 | Physical v3 ID / caps |
| 08 | Submit staged descriptor exactly once |
| 0c | Record state[7:0], descriptor busy[8], observer fence[9], source good[10], media hold[11], physical DATA valid[12], reserved[13], enabled[14], subscribed[15] |
| 10 / 14 | Staged object32 / five borrowed frame flags: compact, bulk, direct, lossless, second |
| 1c / 20 | Actual object32 / zero; distinct from R00 object64 |
| 24 / 28 | Existing rate 48000 / no new epoch claim |
| 2c / 30 / 34 / 38 | Captured / native committed frames / object CRC / stop reason |
| 40 / 44 / 48 | Current ATT value limit / physical command admission ms / elapsed ms |
| 4c / 50 / 54 | Accepted / completed descriptor sequence / common-reset lifetime 1 |
| 58 / 5c / 60 / 64 | Staged sequence / transfer tag / physical opcode / payload length |
| 68 / 6c / 70 / 74..80 | Request ID / nonce low/high / four payload words |
| 84 | Result status[7:0], length[14:8], CRC complete[15], physical READ admitted[16]; remaining bits zero |
| 88 / 8c / 90..bc | Actual block PCM CRC / physical admission ms / immutable result payload |
| c0 / c4 | Actual first-frame / terminal event ms |
| c8 / cc | Admitted parser replay flag / cached object tag |
| d0 / d4 / d8 / dc / e0 | Existing S1a slot ticket / owner / session / boot low/high mirror |

Only physical START/STOP/CLEAR and READ are submitted. OPEN/CLOSE/CANCEL/ACK
are never delegated back to hardware. Disconnect/disable aborts an in-flight
physical READ with an explicit completion and clears output availability; it
cannot leave a permanently busy descriptor or publish late data into a new link.
Actual raw CLEAR remains autonomous once accepted.

## Failure and reset

A failed final submit ACK is observed by the exact sequence, never retried.
Unaccepted after 1000 ms records SUBMIT_UNOBSERVED. A failed COMPLETE ACK is
observed by the original full key; no RESULT/PUBLISHED after 1000 ms records
COMPLETE_UNOBSERVED. Advisory STALE from torn state/key/meta remains OBSERVE;
only a separate coherent session change retires that observation. Accepted work
and task facts are preserved. Invalid result identity or transport IO fences C.

Observer reset cannot restart same-boot counters: the existing sticky hardware
fence requires common reset or separately implemented recovery. Capture/object
and autonomous seal remain physical facts. Reconnect retires the C transfer
lease while retaining object/tasks/counters. Session generations do not wrap.

## Build and validation

Only the explicit business firmware sets `A138_BLE_BUSINESS`, uses the 64-KiB
cold-ROM/ILM/DLM composition and calls the real init/pump. Each pump has fixed
work, no heap/waits and at most one primitive or publication. New data helpers
stay under the macro so the default and recording-API 16-KiB binaries remain
byte-identical to the parent. Actual input/disassembly/callsite-target proof
binds every reachable indirect call; unknown sites still fail closed.

The regression links maintained C with actual APB CDC, S1a, parser, physical
engine and native DDR fixture. Its control clock is 20 ns and memory clock
14 ns; final evidence records timeprecision explicitly. The first-batch test
used timeInc(1) with 1-ps precision, making control 20 ps versus memory 14 ns.
That older evidence proves its recorded adverse ratio, not the intended clock
ratio. Revision 2 reruns the original cases and expanded wire/behavior vectors
at the corrected ratio; historical outputs are retained unchanged. Routed
resources/timing/full CDC, CPU performance/watermark, Android and hardware
acceptance remain separate candidate stages.
