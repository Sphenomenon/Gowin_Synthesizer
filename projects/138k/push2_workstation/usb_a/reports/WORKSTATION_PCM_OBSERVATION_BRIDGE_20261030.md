# Physical PCM observation CDC, 2026-10-30

The new maintained `workstation_pcm_observation_bridge` transfers completed
physical PCM frames from selected MCLK into fixed compute clock without audio
backpressure. It reuses the maintained `music_async_fifo` and unchanged existing
`gw138k_counter_cdc` helper. The frozen runtime audio composition, old wrappers,
profile/source locks and board are unchanged.

This is **source implementation plus offline asynchronous verification**. It is
not synthesis/P&R, physical CDC timing, profile selection or hardware acceptance.

## Source identity

- Offline identity: `pcm-observation-offline-v1-7fd9cf0ee1352f9e`.
- Exact source-set SHA256:
  `7fd9cf0ee1352f9ea19ecb183f3607f302b4c674acb354872451443edb8c5123`.
- New RTL SHA256:
  `198dbf39ff6b6cfb6fe308444274849c507f222edcb0ea651abeb8d719f62c17`.
- Prepared helper/profile identity:
  `custom138k-workstation-v1-d23d498ea824c9f9`, under
  `/Users/sphenicidition/.cache/gw138k-task-20261030/f03-scan-window-profile-revision3/workstation/Prj1`.
  No private historical tree or generated implementation database is an input.
- Full file/log hashes, exact commands, phases and per-run metrics are in
  `workstation_task_20261030/pcm_observation_bridge.json`.
- Bitstream identity: none; no EDA or deployment operation was performed.

The runner hashes every actual RTL/helper/TB/runner/profile input before the
tests and verifies them afterward. The evidence writer independently rechecked
those hashes before delivery.

## Interface and ownership

The FIFO transfers one immutable 98-bit transaction:
`{actual44k1, epoch32, sequence32, error, stereoPCM32}`. It preserves every bit.
Optional signed Q1.31 outputs are exactly PCM16 left/right shifted left by 16,
with no new gain, resampling or source selection. No active-mask/reference
signal is added; unrelated current control state cannot be labeled as a matching
physical frame.

The source has no ready port. Its frame pulse proceeds regardless of destination
ready. The default bounded FIFO has 16 complete-frame entries; a full queue
drops the entire offered frame and increments a saturating 32-bit source count.
Destination valid/ready only consumes its held FIFO head. PCM, tags and flags
stay stable under backpressure.

The destination marks the first frame and each rate/epoch change as a stream
change. Sequence gaps are evaluated only within one stream and modulo 32 bits.
Previous identity advances only on a valid/ready transaction. The original
frame error is forwarded independently.

Independent registered-Gray telemetry transfers the **post-drop next count**
on the exact source edge of a drop. A last dropped frame followed immediately by
a stopped-high source therefore remains visible to the running destination,
without a subsequent source edge, frame or mailbox ACK. Cumulative count,
change indication and persistent loss-seen status are independent of accepting
a queued frame. Count changes may coalesce; they are not one pulse per drop.

Only coordinated common reset clears queue, counters and previous stream
identity. Rate/epoch changes cannot erase loss. The destination's recording,
FFT-window and score owners must decide how stream changes/errors/loss affect
their objects; this transport adds no parameter or lifecycle authority.

## Targeted verification

Three independent source/destination phases run actual 12.288/16.9344-MHz source
clocks and a 76.8-MHz destination, with 256/384 source-cycle frame cadences. A
later phase deliberately slows the destination and sends bursts. Two instances
run together: the default 16-entry/32-bit-counter bridge and a four-entry bridge
with a three-bit counter, so saturation is reached by real frame loss.

Each phase verifies:

| Four-entry saturation fixture | Result |
| --- | ---: |
| Offered frames, with no producer wait for sink ready | 72 |
| Whole frames accepted / dropped | 51 / 21 |
| Frames compared, after one intentional queued-frame reset discard | 50 |
| Stream changes / sequence gaps | 8 / 2 |
| Error-bearing frames preserved | 14 |
| Observed loss-count changes | 6 |
| Default 16-entry instance frames independently compared | 63 |

The scoreboard compares complete stereo/rate/epoch/sequence/error payloads,
signed extrema and Q31 conversion; it detects duplicate, torn, reordered or
silently changed packets. Destination head/flags remain stable while stalled.
The directed cases cover:

- Exact four-entry and sixteen-entry capacity, conservative full handling,
  complete-frame drops, saturated small counter and default count exceeding
  seven without accidental truncation.
- A fifth frame dropped from the full small queue, with source stopped high on
  that very edge. Its count becomes visible without another frame/source edge;
  existing queued frames drain while the source remains stopped.
- Stopped-low source, recovery, persistent loss across rate/epoch changes and
  overflow recovery at a slower unrelated destination clock.
- `0xfffffffe → 0xffffffff → 0 → 1` continuity, followed by a deliberate hole;
  another hole caused by an actual dropped whole frame.
- Error flags with exact payload preservation, queued epoch changes and common
  reset during a nonempty/stalled queue with the source stopped. Old queued
  data/counters cannot reappear after local release.

All three runs pass with input identity unchanged. RTL lint has **zero
warnings**. Runner Python syntax, new-file whitespace and the current-workstation
source-boundary regression (**10/10**) pass.

## Limits and integration requirements

The crossing needs the FIFO's actual Gray-pointer/payload constraints plus
registered loss-Gray bit-flight/skew constraints at its new hierarchy. The
helper's prior MIDI-only deployment is not physical timing evidence for a
counter that can update once per source clock. Independent FIFO peer reset is
unsupported; a coordinated common reset must cover both domains.

Loss telemetry is delayed and does not identify the age of a queued packet.
Consumers need their own failure/window-discard/score-stop policy and a real
drain/quiescence barrier before claiming a completed loss-free object. Counter
saturation keeps fault visible and cannot distinguish further drops. The old
96-bit record format does not thereby gain rate/epoch/error fields.

No native control wrapper, register map, record object, display snapshot, source
profile or top is changed here. This observer supplies that next integration
with a concrete transport; it does not claim that integration complete.
Rollback is to leave the current selected profile/top unchanged. These six new
source/test/document/evidence files can remain unselected or be removed without
touching accepted locked inputs or hardware.

## Reproduction

```sh
python3 projects/138k/push2_workstation/usb_a/sim/audio/run_pcm_observation.py \
  --project /Users/sphenicidition/.cache/gw138k-task-20261030/f03-scan-window-profile-revision3/workstation/Prj1 \
  --output /Users/sphenicidition/.cache/gw138k-task-20261030/pcm-observation-final-identity
python3 projects/138k/push2_workstation/usb_a/sim/test_current_workstation_sources.py
```

Use a fresh output directory; the runner refuses to reuse one.

父级以独立输出 `pcm-observation-parent-final` 复跑全部三异步相位，72 offered/51 accepted/21 dropped/50 checked、默认容量 63 帧、停钟及饱和检查均复现；所有输入哈希结束后独立复核一致。机器记录绑定该独立证据身份。
