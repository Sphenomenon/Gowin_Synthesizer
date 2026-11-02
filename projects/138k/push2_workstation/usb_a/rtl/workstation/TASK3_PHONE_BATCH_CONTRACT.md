# Explicit paired phone batch v3

This is an internal LCD extension, not a BLE format. Default/old profiles retain
window-v2. Both roles explicitly select PHONE_BATCH=1 and negotiate version3,
features0xc0080601; no mixed ARM. Original M PCM1 remains the only queue/SRC/source
owner and final M history/sample application remains authoritative. Production
PCM1 sustained capability stays false.

The explicit `custom138k-workstation-task3-{m,w}-paired-phone-batch-v1` profiles
select this RTL/firmware under independent source locks. Their source closure,
firmware review and observer-reset binding are separate from physical audits;
old profile seals must not be refreshed to select this implementation silently.

Request channel6 length30, low fields:

| Bits | Value |
|---|---|
|31:0|pair generation token|
|63:32|monotonic request sequence, no wrap|
|95:64|controller epoch|
|127:96|HCI generation|
|159:128|stream|
|191:160|physical epoch|
|223:192|PCM block sequence|
|226:224|opcode0 snapshot;1 ARM;2 COMMIT;3 SELECT;4 STOP;5 CANCEL|
|227|rate:0=48000,1=44100|
|229:228|slot0..3|
|237:230|frames0..128 (COMMIT1..128); non-COMMIT slot/frames/block sequence all zero|
|255:238|zero|

The M batch executor receives decoded packet fields and a full32bit pair token.
Only one request/response exists. It validates full shape/token/strict transaction
sequence, never retries an uncertain command, replays the original key and
staging writes through the original APB CDC, checks original owner ID/version/
CAPS and command_id progression, then captures a compute-domain atomic snapshot.
Snapshot query opcode0 does not execute source commands. Original bitmap/slot/
key/error checks remain intact. The endpoint admits batch traffic only while the
phone ingress is armed and normal/window owners are idle; overlap fails phone.

Reply channel7 length32, low eight32bit words:

|Word|Value|
|---|---|
|0|pair generation token|
|1|request sequence|
|2|real accepted command_id|
|3|real source applied_id|
|4|real expected PCM block sequence|
|5|strict nonzero capture_id|
|6|actual physical epoch|
|7|status[7:0],free_slot_mask[11:8],queued[21:12],failure[25:22],live_epoch_generation_match[26],active_full_key_match[27],owner_or_protocol_error[28],snapshot_valid[29],rate44100[30],actual_sustained_cap3[31]|

`free_slot_mask` is the original owner's four-bit `~owned` bitmap, not a count:
15 means all four slots are free,14 means slot0 is owned,0 means all slots are
owned. W preserves every bitmap value unchanged.

The live match compares actual live controller/generation with the requested full
32bit fields; the active match compares all five active tuple fields. The reply
must never invent actual epoch/generation: firmware can use its requested tuple
only with the corresponding match flag. The actual physical epoch/rate are
returned to allow initial ARM. M packs only after reading one frozen capture.
It must never combine multiple captures. Accepted and applied IDs remain distinct:
COMMIT acceptance does not mean a source-switch history barrier has completed.

Lease revocation must reset or safely drain the original observer APB CDC before
a new lease issues commands. Dropping valid can leave its COMPLETE response
pending; reopening without reset/drain must fail closed. The opt-in model resets
only this observer bridge when phone_owner_live falls. The original PCM owner
keeps its root reset, retired stream and capture counter; an observer reset is
not an owner lifetime reset. Batch errors revoke output/commands immediately but
retain the transport error reply until consumed or the outer lease is revoked.

Owner snapshot feature is explicitly parameterized, default off. An accepted
read0x090 atomically latches the complete live/active tuples, status/free/queue,
failure, IDs, rate, capabilities, and a nonzero monotonically increasing capture
ID in compute_clk. Frozen words0..19 are read at0x100+4*n. Raw layout:
0 live controller,1 live generation,2 active controller,3 active generation,
4 active stream,5 active rate,6 active physical,7 actual physical,8 actual rate,
9 status,10 free slot mask,11 queued,12 failure,13 expected block sequence,14 command_id,
15 applied_id,16 capabilities,17 capture_id,18 reserved0,19 reserved0.
Read0x090 returns0x50434d53. Capture overflow fails closed; all frozen reads are
side-effect free and snapshot capture cannot stop the sample schedule.

W exposes a NEW virtual batch page; it never intercepts legacy staging writes:
0x100 identity0x50434d42,0x104 version0x00010000,0x108 available;
key/staging writes0x110 controller,114 generation,118 stream,11c rate,
120 physical,124 slot,128 frames,12c PCM block sequence;
write0x130 opcode starts one bounded transaction; response ready means matched
real M completion. Read0x140..15c returns the last complete8-word reply atomically.
Invalid shape, token, duplicate/reordered response, timeout, link/PANIC/HCI loss,
identity change or overlap invalidates reply and fails this phone branch. No replay.
The adapter holds one local APB command, one transaction and one reply; key fields
are intent, never authority. Before sending it asserts explicit window flush and
waits for original window_tx busy=0 (all real M applied ACKs received). Clock and
legacy commands still use original proxy and retain their remote completion scope.

New paired firmware uses an explicit initializer; legacy initializer remains
unchanged. It uses batch snapshot/commands, compares actual command progression,
requires live/full-key match as appropriate, uses a bounded snapshot during the
at-most8 partial submissions of one128-frame block, and refreshes on block/state
change, non-writing/slot wait or exhausted reuse. Runtime100ms PCM timeout and
transport timeouts remain. Cached facts never authorize M output or bypass M
window/COMMIT checks. New model-only injection may override the capability read
in the verification fixture; production capability is unchanged.

No physical link budget, routed CDC/STA, RF/SBC, D effect or DAC acceptance follows
from this contract. Implementation and validation remain separate stages.
