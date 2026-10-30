# AE350 BLE business owner, first batch

Only `custom138k-workstation-ae350-business-v1` selects these versioned 138K
sources. Its source selector copies bytes and removes the old staged
`ble_recording.v`; it does not run the legacy recorder text adaptation. The
unchanged 25K project, vendor, baseline and earlier providers keep their source
policies. `provenance.json` records the one-time derivation. The retained Rice
encoder, transfer banks and wire-message function must match their original
protected hashes. This is the exit from the recorder text overlay for this
candidate, not a rewrite of the protocol or transport.

`ble_business_owner.c` is the sole owner of the eight operation tasks and
operation/object/transfer ID allocation. It implements operation query,
START/STOP/GET/CLEAR and transfer OPEN/CLOSE/CANCEL. The physical engine holds
borrowed tags with the actual active capture or download lease. Those tags do
not allocate identities or create another task table. Its state, frames, CRC,
native commits and physical event timestamps are hardware facts consumed by C.
The task retention deadline uses the actual physical event timestamp, rather
than the later CPU observation time.

The first batch retains the download READ/ACK/combined-ACK/resume policy,
confirmed/pending offsets, block CRC checks and 30-second transfer timeout in
the data engine. These are explicit second-batch work. Capture/CRC, normal media
seal, native drain, fetch cache, Rice encoding, transfer RAM and wire framing
remain hardware in both batches. This source change alone proves no net CLS,
physical BSRAM, routed timing, complete CDC or hardware acceptance.

## Parsed-command boundary

The existing hardware parser performs fragment checks, complete-message CRC,
nonce/session checks and exact replay before `DISPATCH`. HELLO and the existing
state summary remain hardware protocol operations. New business requests use
the original S1a mailbox ABI and one immutable 16-byte request / 64-byte result
slot. Admission and CLAIM are transport facts. A C PENDING result requires an
already-reserved task ID and actual engine command completion. START completion
means the first accepted PCM frame, STOP completion requires all four CRC bytes
and native accepted/committed counts matching the captured prefix. CLEAR only
clears the borrowed identity after actual raw-store completion.

Nondata exact replay uses the unchanged response cache without calling C again.
Data replay uses its cached object ID and immutable original block descriptor
to rebuild bytes, without allocating C identities. The original high-water and
request/reply cache advance only after normal business completion. Local
mailbox rejection produces the existing BUSY error. An uncertain claimed
observation also fences further mutating requests for that connection; GET and
operation query can inspect the actual C owner. A reconnect creates a new
protocol session but preserves C counters/tasks and the physical object. A
local observation loss never reports that a task was cancelled.

Session generations increment on a new established business session and never
wrap. The existing nonzero HCI boot identity remains the external authority.
The owner cannot open before the protocol session exists. A new boot or owner
generation cannot silently reuse C IDs. First-batch firmware has no persisted
task recovery: observer reset fences future primitive submissions until common
reset or a separately implemented recovery. It preserves capture/object and
accepted physical work, while the original hardware media seal remains able to
finish without CPU service. No lost C task table is reconstructed by clearing
hardware IDs. Ordinary audio scheduling has no CPU ready signal.

## APB and physical descriptor

The explicit candidate owns APB `0xf8050000`, through the existing checked
`gw138k_apb_cdc` to the continuously running 50-MHz control domain. Offsets
`0x000..0x0ff` are the unchanged S1a mailbox. `0x100..0x1ff` are the physical
primitive below, addressed through the existing `recording_service` callback
API's explicitly probed v2 helpers. Unknown/misaligned accesses, partial writes
and invalid state return an APB error. Every access has an immediate local
ready; raw work is submitted once and observed by sequence. No bus transaction
waits for CPU, radio or native DDR.

| Primitive offset | Meaning |
| --- | --- |
| 00 / 04 | ID `52434402`, caps `00301001`; 48-byte result, 16-byte request, one descriptor |
| 08 | Submit command 1; the API stages the complete descriptor |
| 0c | Physical record state[7:0], busy[8], observer fence[9], source good[10], media hold[11], lease open[12], block pending[13], enabled[14], subscribed[15] |
| 10 | Staged C object32 tag |
| 1c / 20 | Current physical object32 tag / zero; distinct from R00 object64 |
| 24 / 28 | Existing BLE format-1 rate 48000 / no new epoch claim |
| 2c / 30 / 34 / 38 | Captured frames / native committed frames / object CRC / physical stop reason |
| 40 / 44 / 48 | Active transfer tag / hardware confirmed byte offset / elapsed ms |
| 4c / 50 / 54 | Accepted descriptor sequence / completed descriptor sequence / common-reset lifetime 1 |
| 58 / 5c / 60 / 64 | Staged sequence / C transfer tag / opcode / length |
| 68 / 6c / 70 | Staged request ID / nonce low / nonce high |
| 74..80 | Four little-endian payload words |
| 84 / 90..bc | Completion status[7:0], length[14:8] / immutable 48-byte result |
| c0 / c4 | Actual first-frame / terminal event ms |

Sequences are nonzero, strictly increasing within the common-reset lifetime.
Accepted does not mean the engine completed. The submitted descriptor stays
immutable until its actual completion; later bus staging cannot alter it. A
failed final write ACK is observed using that same sequence and never retried.
If that sequence is still unaccepted after 1000 elapsed milliseconds, C records
SUBMIT_UNOBSERVED and fences its owner. It neither allocates the candidate IDs
nor retries an uncertain side effect. Accepted work remains a physical fact.
A failed final mailbox COMPLETE ACK is likewise observed by its exact request
key. No RESULT/PUBLISHED fact within 1000 ms records COMPLETE_UNOBSERVED and
fences C without cancelling the real task or capture. An advisory STALE from
key/state/meta tearing remains in OBSERVE; it is not proof of retirement. Only
a separately coherent context showing a new session ends the old publication
observation. No completion is blindly repeated.
Direct MMIO bus faults trap/fence firmware; a callback failure does not imply a
write was uncommitted. Bounded polls may return an unstable advisory snapshot
when the physical object changes; C retries reading on a later pump, without
resubmitting work. READY descriptors and completed result slots are immutable.

The independent R00 APB `0xf8040000`, object64 and first 64-KiB recording window
are preserved. BLE still uses `PRJ1_DDR_RECORDING_BLE_*`, byte
`0x30510000..0x3051ffff`, native words `0x0c144000..0x0c147fff`. The existing
common DDR authority, owner8 mux and native-accept bridge remain authoritative.
There is no new DDR allocation, CPU PCM polling/copy loop or cacheable DMA area.

## Firmware integration and validation scope

The explicit firmware build sets `A138_BLE_BUSINESS`, links the mailbox,
recording helpers and C owner, and calls `a138_ble_business_firmware_init` once
after startup, then `a138_ble_business_firmware_pump` once per bounded UI loop.
Other builds leave the macro undefined. A pump allocates no heap and never
waits; each helper has a fixed access count and at most one descriptor or result
is submitted per pump. Full ELF, local-memory image, actual callback targets,
whole-call-chain stack are bound to actual disassembly and reviewed callback
targets. Physical service performance remains separate C06/C02 acceptance.

The local Verilator regression links the actual maintained C files against the
actual APB CDC, mailbox, parser, physical engine, raw store and native bridge,
with a DDR model separating local submission, native acceptance and read return.
The same packet driver and PCM source exercise the locked old RTL reference for
wire-byte comparison. Its source identity and cases are recorded by
`sim/services/run_ae350_ble_business.py`. Synthesis, P&R, full reset/CDC/timing,
board audio, Android, SRAM and Flash require separate candidate evidence.
