# Physical PCM observation crossing

`workstation_pcm_observation_bridge` transfers completed physical frames from
selected MCLK into a fixed compute clock. It is independently selectable and
does not change the frozen runtime composition or any selected profile/top.
It owns bounded observation transport, not sample scheduling, synthesis,
parameters, recording objects, FFT windows, score policy or display state.

The complete atomic 98-bit payload is `{actual44k1, epoch32, sequence32,
error, stereoPCM32}`. Left is PCM bits31:16 and right bits15:0. Neither payload
nor error is rewritten. Optional Q1.31 outputs are exactly the signed PCM16
value shifted left by 16; they are a representation change and introduce no
second gain or sample conversion. There is no active-mask/reference port:
unrelated live control state cannot masquerade as matching frame metadata.

## Queue and destination interface

The existing maintained `music_async_fifo` owns the Gray-pointer payload
crossing. Default capacity is 16 whole frames (`FIFO_ADDRESS_BITS=4`), with
supported explicit sizes 4..256. One source-clock `frame_valid_i` pulse offers
one physical frame. There is **no source ready or backpressure port**. When full,
the complete frame is dropped and the source counter increments; audio keeps
its physical schedule. Conservative synchronized full-pointer release may
drop a frame even shortly after a destination pop, as in the existing FIFO.

At the destination, `frame_valid_o` and `frame_ready_i` form a normal held-head
transaction. All PCM/metadata, `stream_change_o` and `sequence_gap_o` stay stable
while that head is stalled. Previous identity advances only on valid-and-ready.
The first accepted head and any rate/epoch change flag stream change. Sequence
comparison is within one rate/epoch and naturally wraps from `0xffffffff` to
zero; it never invents continuity across an epoch change. An input error is
reported with its own frame and is independent of sequence-gap detection.

## Persistent loss independent of frames

`source_drop_count_o` saturates at `0xffffffff` by default. The optional smaller
`DROP_COUNTER_BITS` exists for bounded saturation verification; its public
ports remain 32-bit. The existing `gw138k_counter_cdc` helper crosses registered
Gray state into the destination. Its source input is the **post-drop next
count**, so the final drop is registered into Gray on that same source edge.
Even if selected MCLK then stops high with no next edge or frame, the running
destination can observe that count.

`destination_drop_count_o` is a delayed coherent cumulative count.
`destination_drop_event_o` is high for a destination cycle when that observed
count changes; several drops may be coalesced into one change.
`destination_loss_seen_o` stays true after any observed loss until coordinated
common reset. Loss does not depend on a consumer accepting a packet or on a
subsequent frame arriving. Saturation keeps loss visible; it cannot count
further drops. A consumer must not infer a new loss-free lifetime by subtracting
two saturated counts.

Loss telemetry is independent of queued packet age. It does not identify which
queued frame preceded a missing frame. The next accepted packet can additionally
reveal a sequence gap. Consumers own prompt recording failure/window discard/
score stop policy and any source-quiescence/drain barrier before finalizing an
object. A count snapshot alone cannot replace that barrier.

## Reset and physical constraints

Only a coordinated common reset is accepted. Assertion is asynchronous and
release synchronizes in both domains. It intentionally discards queued old
observations and clears both lifetime counters and previous stream identity.
Rate/epoch changes have no reset port and never clear queued data or loss.
Independent reset of one FIFO peer is not supported. A stopped source need not
produce an edge for common reset assertion; after release it must produce local
release edges before it can offer another valid frame.

This wrapper reuses, rather than changes, the FIFO and registered-Gray helper.
Future profile/top integration must constrain the existing FIFO Gray pointers,
stable held payload memory path and all registered loss-Gray bit flights using
their actual source/destination clocks and hierarchy. In particular the loss
counter can change once per source edge; the old helper's MIDI-only use does not
provide timing evidence for this new instance. Digital simulation and lint do
not prove physical CDC constraints or routed acceptance.

## Verification

`sim/audio/run_pcm_observation.py --project <exact prepared Prj1> --output <new
directory>` binds and hashes the maintained FIFO, unchanged prepared counter
helper and profile metadata, new wrapper/TB and runner. Three independent clock
phases exercise actual 12.288/16.9344-MHz source clocks and 76.8-MHz destination,
then a deliberately slower destination. Both the default 16-deep/32-bit instance
and a four-deep/three-bit saturation instance run together.

The scoreboard compares complete accepted packets and signed Q31 conversion,
stalled head stability, errors, epoch/rate changes, sequence wrap and real holes.
Tests fill queues, drop complete frames, stop the source high on the final drop
edge, drain while stopped, stop low, recover, retain loss across stream changes,
saturate and assert common reset with a nonempty queue/stopped source. No source
clock or frame producer waits for destination ready.
