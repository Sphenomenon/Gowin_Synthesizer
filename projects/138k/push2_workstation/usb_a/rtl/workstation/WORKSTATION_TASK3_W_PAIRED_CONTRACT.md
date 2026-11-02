# W paired board composition

This explicit role preserves the existing W demo/media profiles and their
immutable candidates. W has one native DDR fabric: real deferred-seal CNN on
owner5, the maintained delay port on owner6, and the same 2,880,000-frame raw
recording store on owner8. The existing full HCI/GATT engine and CPU business
owner remain the sole recording object, CRC, task and download authority.

The typed endpoint connects M final serializer frames to the real recording
ingress. It requires explicit arm acknowledgement, the actual empty-object
state, storage readiness, a nonzero physical epoch and monotonic generation.
A reserved delivery register respects the ingress pulse/credit contract.
Overflow, sequence/format error, storage failure, cancellation, link loss and
PANIC invalidate the source; a failed object must be retired before rearm.
The source cannot backpressure M's physical sample schedule.

The actual shared CPU/BLE REC_START command requests its source through a
bounded gate in `ble_protocol_command`. Ch9 sends `{kind2,common96}`: ARM
requests acquisition and CANCEL withdraws a request or releases the tap when
the same physical object becomes terminal. M retains final acceptance and
allocates an independent record generation, without interrupting the phone
session. W maps each fresh wire `{Mboot,session,recordGeneration}` to its own
root-monotonic ingress generation; an independently rebooted M cannot collide
with W's retired ingress generation. Duplicate/stale keys cannot rearm it.

Acquisition has a 50 ms bound at 50 MHz. It waits for actual source readiness,
including a real observed PCM frame, then releases the original held command
to the same physical recording engine. A timeout also releases that command;
the engine returns its actual source failure, and the expired demand cannot
arm later. Source demand persists through raw-start, recording and drain, then
automatically cancels the M tap. Busy/nonempty objects retain their original
rejection behavior. No source-good fact is forged.

The explicit paired ELF has a single hash-locked temporary C adaptation:
REC_START's preliminary `source_good` rejection is deferred to the real engine
after acquisition. Original C bytes, old media review, old flags and default
firmware behavior remain intact. `workstation_task3_w_paired_firmware.py`
checks the entire original and adapted source, unique anchor and exact inverse;
the real ELF callback/stack audit checks the resulting build. This adaptation
must become an explicit native firmware role after paired hardware gates close.

W's existing PCM1 aperture at `0xf8060000` and clock aperture at `0xf8030000`
terminate at the remote command proxy. Completion means a matching response
from M's existing owner, never local transport credit. The existing media
firmware supplies decoded pre-master PCM; M applies its D effects, master gain
and final output scheduling. W's local output is muted. A successful ch8 status
transfer containing the actual HCI epoch/generation/readiness precedes phone
ARM. A changed/rebooted context fences outstanding requests; M must supply a
new generation. Uncertain timeout returns an error and cancellation without
automatic retry. F807 software PCM injection is retired for this role.

Channel payloads are defined by `task3_paired_channels.vh`: exact lengths and
zero high padding are mandatory. CNN descriptors, PCM, seal and cancel go to
the real stream/task service; terminal/score messages return to M. Actual
model/backend readiness is reported, rather than the retired local TF stub.
SIGNAL and CQT coefficient storage use BSRAM with unchanged algorithm geometry.

The maintained paired board opts into `BLOCK_PCM=1` and the
[PCM block contract](TASK3_PCM_BLOCK_CONTRACT.md). Analysis descriptors and
SEAL have bounded pending slots, while analysis and recording PCM each have
eight independent block slots and absolute credit. Shared RX never waits for
the CNN consumer to free a media slot; accepted credit has already reserved
space. Invalid/over-credit packets are consumed and revoke the affected
stream, with a token-bound fault reported to M. Only complete block retirement
returns a slot. SEAL waits for its stream's data drain; cancellation bypasses
the slow consumer and clears pending media. Capability, full-context identity,
monotonic token and old-DATA rejection prevent mixed-version media acceptance.
The same original recording ingress and CPU/BLE object remain authoritative.

Physical pin/framing CDC and business-budget enable are separate boundaries.
No business exchange is enabled until the measured LCD budget is configured.
Bluetooth remains on W for actual phone ingest and reliable recording download;
no throughput, radio, D DSP, DAC, 60-second capture or board acceptance is claimed
by logical endpoint/source checks. Owner6 remains connected but heavy effect
migration is not claimed by this composition.
