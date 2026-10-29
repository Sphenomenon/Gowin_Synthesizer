# A07 runtime effects stage 5: native complete effects composition

2026-10-30. `rtl/audio/workstation_runtime_stereo_effects.sv` composes the
independently verified native Delay, Chorus and Reverb. It remains unselected by
profile/build/top. Input identities and all nine scenarios are in
[`workstation_task_20261030/runtime_effects.json`](workstation_task_20261030/runtime_effects.json).

## Provenance and normal rendering

The policy reference is the exact `stereo_effects` module in actual F02 rev2
prepared `legacy/rtl/audio/stereo_effects.sv`, commit
`3d4b3175d0f20d0b787b61b43e4543739b26bca1`, identity
`custom138k-workstation-v1-f5b723250388add5`. Prepared slice SHA256 is
`5fcabe0bb792efb13a791b3e6f91b6d156dd074d8a89421dedde09a124539742`;
native SHA256 is
`d8a0d2c787bc8c222bf4dde74069db41163988a646fd70c32774387bfe23a689`.
Adjacent provenance reverses exact edits to those original bytes. References and
banked RAM reconstruct from versioned baselines and independently reversible
Delay migrations, with no private staging/results test dependency.

The native composition retains input mixing, frame snapshots, last nonzero order,
active-tail policy, clipping and dry maintenance semantics. Every accepted frame
processes each effect exactly once, applying the selected ordered stages and
maintaining remaining stages with dry input. The original shared `work_enabled`
and active behavior are retained in the independent frame model, including their
effect on which input enters an inactive stage's history. Synth/PCM gain updates
retain the prepared SCALE edge, including cancellation there. At 48 kHz the step
is exactly 128; at 44.1 it is 139 plus carried 47/147. Public parameter ownership
does not move into the effect chain.

## Configuration and PANIC

Config and history requests use the same valid/ready naming as the individual
components. `config_ready_o` requires true chain/child quiescence and excludes a
competing render input. The accepted request broadcasts to all three components
on one edge, closes rendering, and waits for all child ACKs, all child quiescence
and rates matching the pending request. The Delay ACK includes its old-read drain
and ordered post-write fence. Only then does the chain pulse
`config_applied_o/history_done_o`. History-only uses the same barrier while
preserving rate, dry/wet gains and fractional state.

An accepted broadcast cannot be retracted by PANIC/legacy clear. PANIC clears
wet/history and coalesces into the existing Delay transaction, or starts a second
fenced clear if Delay already ACKed. The original configuration must complete at
the requested new rate or fail sticky. The chain never exposes ready during
partial application or reports an old-rate completion. Its absolute transaction
deadline continues through PANIC; repeated clears cannot extend it indefinitely.

`applied_rate_44100_o` and `applied_transaction_o` directly project Delay's local
state. **They may change before the entire barrier finishes.** The upstream
switch remains the sole public committed-rate authority and must wait for chain
done before consuming the projection. Delay's private transaction ID can advance
again for PANIC and must not become a public epoch/revision. `pending_rate` is a
private matching snapshot, not another public parameter truth.

During a barrier or fault, `ready_o=0`, `valid_o=0`, and PCM payload is zero.
The caller still must keep the physical serial sample schedule running through
controlled mute. Child stream faults, synchronized DMA faults, timeout and rate
mismatch latch chain failure until coordinated reset. Clock heartbeats retain
the independently verified Delay contract; detecting both clocks stopped requires
an external always-on monitor.

## Offline evidence

```sh
python3 projects/138k/push2_workstation/usb_a/sim/test_workstation_runtime_effects.py
```

Nine tests passed with Verilator 5.052 and independent 14 ns/20 ns clocks. The DDR
model queues accepted writes before four-clock execution; held fence reads make
acceptance/completion distinct. DUT and exact prepared reference have separate
DDR memories. Reviewed compile counts are guarded: one inherited timescale,
65 inherited arithmetic expansions and 16 inherited truncation/index/integer
parameter warnings, including exact prepared DMA widths. New barrier logic and
testbench add no width warnings.

| Scenario | Frames | Clip outputs | Evidence |
| --- | --- | --- | --- |
| Normal 48 kHz | 36288 | 3503 | Per-clock exact prepared ready/valid/PCM/clip and independent integer model |
| Complete 44.1 kHz wet path | 24288 | 2341 | Independent full chain integer model |
| 48→44.1→history→48 | 44512 | 4837 | 11000 frames per wet segment, then bypass maintenance |

Both normal-rate suites warm 12000 frames before testing all six effect
permutations × eight masks, so the real 9600/8820-frame Delay paths contribute.
Each output checks exactly one call to all three stages, and each stage covers
both apply and maintenance. The 48 kHz suite includes clear and another 12000
frames. Normal rendering remains per-clock exact; comparison pauses during the
intentional new clear barrier that waits for the real DDR roundtrip.

The remaining tests cover PANIC before Delay ACK, PANIC just after Delay ACK
requiring a second fence, rejected extra requests while pending, missing/late
fence, either stopped clock, and nine top/stage cancellation boundaries. They
assert controlled zero/no ready, no false completion, sticky failure, preservation
of the accepted new rate, and the original dry gain update edge. Observed render
latency is at most 105 clocks with this uncongested modeled DDR; it is a subsystem
measurement, not a whole-workstation or physical timing budget.

Storage remains the existing 128 KiB ring, 1024-slot Chorus and original 48 kHz
Reverb capacities. Event/render-service integration, final serial schedule,
recognition/capture and global runtime switch acceptance remain separate work.
No synthesis, P&R, CDC, resources, board, SRAM, Flash or perceptual acceptance is
claimed. Rollback is omission of this independent composition; accepted source
selection has not changed.
