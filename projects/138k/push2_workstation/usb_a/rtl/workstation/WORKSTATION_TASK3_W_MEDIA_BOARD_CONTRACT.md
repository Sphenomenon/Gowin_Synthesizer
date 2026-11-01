# Explicit task3 W-media board profile

`custom138k-workstation-task3-w-media-v1` is a separate prepare/synthesis candidate.
It does not select or modify W21, accepted inputs, or frozen bitstreams.

The native shared HCI owner includes actual Classic/H5/A2DP/SBC/PCM and GATT.
The maintained phone -> decoded PCM -> D effects -> local W DAC path remains
an independent fallback. It is not the final M audio path and does not claim M
parameter authority. The actual CNN task owns native DDR owner5, D delay owns6,
and the single C/BLE recording raw store owns8. Recording holds 2,880,000 PCM16
stereo frames at48kHz (60s). Capacity and byte/native-word addresses come only
from `rtl/ddr_address_map.vh`. No R00 recorder is instantiated. C and BLE use
the same existing recording engine/object; CPU frontend commands remain the
maintained C API, with no new M-command frontend implied.

## Bounded input and truthful connectivity

The physical LCD link is unmeasured and remains down (`lcd_link_ready_i=0`).
No LCD output, pin direction, clock, voltage or bidirectional transport is guessed.
The board keeps the reviewed pins inactive. There is no direct W access to M
USB/TF/DDR/HDMI/DAC. W graphics/TF/local synth are retired from this explicit
profile. M's 32-voice ordinary/vector target is unaffected.

F8070000 is a new 4-KiB APB page inside the documented F8000000..FBFFFFFF
extended APB window (`docs/ae350/README.md`). Maintained pages F800..F806 were
searched before allocation; no existing F807 address owner was found. This is
an explicit local allocation, not a claim that a central MMIO registry exists.

A `gw138k_apb_cdc` mailbox sends one command to50MHz and acknowledges without
waiting for CNN/model/DDR/packet credits. Illegal/alignment/partial writes or
an unavailable action return an immediate bus error. Commands and results
remain different contracts. Every task descriptor, PCM word and cancellation
is reachable through APB; descriptors are not tied to zero. Scores and terminal
results remain stable until explicit pop/ack.

The software M-final-tap injection aperture is CLOSED after reset. Opening it
requires F8070118=1, independently of the hard-zero LCD-ready observation. This
is offline/software injection evidence only. It never selects W's local DAC.
F8070100..0110 stage session/generation/physical-epoch/first-sequence/format;
0114=1 arms only if the actual raw store is empty and ready. The existing object
must be cleared before rearm. 011C..0130 stage frame identity/sequence/PCM/flags;
0134=1 is one delivery attempt requiring credit. The256-frame ingress validates
identity and48kHz and delivers no faster than one frame per5clocks. It carries
its continuous local observer sequence separately from physical identity.
Closing the aperture, owner reset, backend fault, overflow, identity/format
error,4ms source lease, matching cancellation(0138=1) or PANIC(0150=1) fence and
discard this source. Stale cancellation cannot kill a later generation. Only
higher generations with an empty recording object can rearm. Communication
never waits in or backpressures M's sample schedule. Native ledger faults stay
quarantined until the existing common reset policy permits recovery.

## APB registers

All offsets are relative to F8070000; words use full strobes and4-byte alignment.
000 ID;004 status (backend/start/frame/score/terminal/fatal/tap-open/LCD/model).
010 task ID;014 generation;018 frames;01C CRC;020 format;024 start=1;
028 frame index;02C PCM;030 commit=1;034 matching task cancellation=1.
038 score valid/note;03C index;040 score pop=1;044 terminal valid/fatal/code;
048 terminal ack=1;04C accepted;050 committed;054 replayed;058 seal CRC;
05C first result;060 active ID;064 active generation;068 accepted starts;
06C rejected starts;070 last rejection;074 seals.
100..150 implement the separate software tap aperture described above;
13C reports queue/failure/armed/fault/credit;140 accepted;144 delivered;
148/14C accepted/rejected arms. Read and write actions never block on results.

## Gates and rollback

Source/firmware/behavioral preparation is distinct from synthesis, real VG/VO
endpoint resolution, complete CDC/PLL/routed setup/hold, electrical checks,
LCD throughput/jitter/roundtrip/congestion, phone/D/DAC acceptance and60s
capture/download. None are inferred from a tool exit or resource estimate.
The new source/constraint adapters retain exact reverse/forward evidence;
unchanged profiles keep their original budgets. New scoped constraints remain
candidates until physical endpoint and clock/reset checks pass.

Rollback selects the frozen W21 candidate for local phone/D demonstrations and
the separately frozen M candidate. No flash write is included. Source changes
require a distinct candidate/bitstream identity; SRAM acceptance remains a
separate explicitly authorized stage.
