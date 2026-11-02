# Task3 paired PCM blocks

This is an internal M-to-W media contract for the explicit paired profiles.
The existing LCD PHY, 52-byte CRC/boot/session/sequence frame and F808 probe,
budget and business gates remain separate. It does not change BLE, USB PL,
the 18-bit performance event, the PCM1 aperture or M's final parameter owner.
The legacy endpoint parameter default is `BLOCK_PCM=0`. New paired board
composition explicitly selects `BLOCK_PCM=1`; historical candidates remain
immutable and are not a compatible media peer merely because framing works.

## Context and payload

Complete analysis descriptors and recording ARM messages establish the full
boot/session/task/generation or boot/session/generation/epoch context. A block
token is the corresponding nonzero generation, used only inside that accepted
context. Identity changes, cancel, PANIC, fault and link loss withdraw the
context, buffered partial blocks and credit. A retired generation cannot rearm
the same stream. Counter exhaustion fails rather than wrapping.
Packets already queued in the ordered transport may still arrive; token,
context and fault gates reject them without reviving the retired stream.

| Channel | Payload, low bits first | Length |
|---|---|---:|
| 10, analysis PCM | token32, first index32, 1–6 stereo16 pairs | 8 + 4 × count |
| 11, recording PCM | token32, first physical sequence32, 1–6 stereo16 pairs | 8 + 4 × count |
| 12, absolute credit | token32, grant limit32, stream1 | 9 bytes |
| 13, capability | version and exact block/credit feature identity | See header |
| 14, media fault | token32, stream1, reason4 | 5 bytes |

The header `task3_paired_channels.vh` defines exact bit positions. Valid block
lengths are 12, 16, 20, 24, 28 and 32. All unused high payload bits, including
the high bits of the last byte, must be zero. The receiver checks the active
token, contiguous first index, sample count and nonwrapping interval before
accepting a block. Recording epoch/rate/error have already been checked by
M's nonblocking final-tap exporter; W reconstructs them from the accepted ARM
and delivers original sequence/PCM to its existing recording ingress.

The explicit capability exchange must complete before block media starts.
Unsupported or missing peer capability fails within a finite bound; it never
stalls M's local performance sampling. In block mode old per-sample DATA is
rejected. A legacy and block candidate must not silently negotiate partial
functionality from the common LCD framing alone.

## Queues and credit

Analysis and recording each own eight receive-block slots. Credit is an
absolute count of block slots granted in the current context, not a count of
samples or acknowledgement of DSP execution. M reserves one credit for every
block handed to the ordered transport. W returns a slot only after its last
sample is consumed. Duplicate credit cannot grant additional slots, and a
stale token cannot replenish a new context. Credit updates may combine freed
slots to reduce reverse traffic; neither counter may wrap.

A legal in-credit block has reserved capacity and does not wait for CNN or
recording readiness at the shared LCD receive slot. A malformed, stale or
over-credit packet is consumed and rejected so it cannot hold that slot.
An active-stream violation withdraws that stream and reports its token and
reason to M. Separate queues prevent CNN backpressure from occupying recording
capacity. Media arbitration is fair between the two data streams; control,
cancel and terminal paths remain bounded and do not require PCM credit.

Analysis SEAL follows all queued data, including a final partial block, before
W may seal the real clip. Cancellation clears both pending SEAL and partial
PCM; late credit, data and completion cannot revive the canceled task. M TF
analysis may pause its reader. Recording queue exhaustion invalidates the same
CPU/BLE object; it cannot backpressure M's physical frame input. The existing
recording lease, frame validation and single storage backend remain in force.

## Budget and evidence

At six samples per block, each 48 kHz stereo16 stream needs 8,000 data frames/s.
Two M-to-W streams need 16,000 data frames/s or 832,000 B/s of fixed 52-byte
wire frames, plus descriptors, partial blocks, status, control, maintenance
and credit in the reverse direction. Eight blocks hold up to 48 samples,
about 1 ms at 48 kHz. Collecting six continuously available 48 kHz samples
adds five sample intervals, about 104.2 microseconds. Credit, arbitration and
source-queue delays are additional and require separate bounded acceptance;
offline analysis may remain backpressured. These are format calculations, not measured latency or
permission to enable real-time media.

Required offline checks cover partial/full blocks, random backpressure,
zero padding, token/index/credit errors, cancellation and identity changes,
SEAL drain order, independent queue exhaustion and sustained dual-stream
traffic over the actual LCD transport/PHY model. Component tests and ideal
wire models do not establish full CNN/recording concurrency, physical CDC,
metastability bounds, routed timing or real LCD/Bluetooth throughput/jitter.
Phone PCM1 remains a per-command round trip and needs a separate bounded
stream integration. F808 business budget defaults closed pending physical
electrical and measured link acceptance.
