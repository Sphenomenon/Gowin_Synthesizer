# A07 runtime effects stage 3: independent Chorus

2026-10-30. The independently named native
`rtl/audio/workstation_runtime_chorus_effect.sv` is offline verified and remains
unselected by every profile/build/top. Full input hashes and scenario results are
in [`workstation_task_20261030/runtime_chorus.json`](workstation_task_20261030/runtime_chorus.json).

The reference is the exact `serial_chorus_effect` slice in actual F02 rev2
prepared `legacy/rtl/audio/stereo_effects.sv`, commit
`3d4b3175d0f20d0b787b61b43e4543739b26bca1`, source identity
`custom138k-workstation-v1-f5b723250388add5`. Prepared slice SHA256 is
`2801a8f9ec570f992bc0e88d9ab6d457c4e17085da810ccf6d9fbaca2b3a5f84`;
native SHA256 is
`8a6fa6ea9158cc983c9d48cc9e92f01da2e10950214d3d2bb2cb7bb0b67b4cf4`.
Adjacent provenance reverses every exact edit and the test requires those original
bytes to match the versioned baseline. No private staging/results directory is a
test dependency. Frozen inputs and public event contracts remain unchanged.

## Behavior

48 kHz preserves original arithmetic, latency, integer tap sequence and 349/frame
LFO increment. At 44.1 kHz the full instantaneous Q16 delay
`480 + triangle*96/65536` scales by `147/160` before one nearest rounding. This
produces taps 441…529 in the same 1024-slot stereo memory. Exhausting all 65536
triangle values gives maximum error 0.4999816895 sample, about 11.3375 us.

The 44.1 kHz LFO increment is 379 plus carried 127/147. Its total over 147 frames
is exactly 55840, preserving the original 0.9984970093 Hz modulation rate. Wet
slew is 139 plus carried 47/147, preserving the physical duration of the original
128/frame ramp. Neither conversion changes the canonical 48 kHz branch.

`config_valid_i/rate_44100_i/config_ready_o` is a valid/ready request at true
quiescence, including the output-valid tail and collision with `valid_i`. Config
has priority over the separate `history_clear_i/history_ready_o` request. Both
logically clear history while retaining wet gain, LFO phase and both remainders;
config also applies the rate. `config_applied_o/history_done_o` pulse at the
single-clock application edge. The requester drops valid after acceptance.

Legacy `clear_i` aborts immediately and resets wet gain as before. It preserves
the original LFO phase and the new LFO fractional remainder, while resetting the
gain remainder. RAM contents need no physical clear: reset logical pointers and
the existing initialized-frame gate prevent stale history from contributing.

## Validation

```sh
python3 projects/138k/push2_workstation/usb_a/sim/test_workstation_runtime_chorus.py
```

All six tests passed with Verilator 5.052. Exact compile-warning counts are
checked: two inherited missing-timescale warnings, eight signed-widening warnings
and two original integer-to-16-bit reset assignments across native/reference.
There are no new rate-path or testbench width warnings.

- 60000 frames compare every clock against the exact prepared 48 kHz reference:
  ready/valid/active, PCM/clip, LFO phase and tap, including 3391 clipping outputs,
  logical clear, memory wraps and a complete LFO cycle.
- 60000 frames at 44.1 kHz compare an independent integer physical-time and
  abs-round/saturate model, including 3384 clipping outputs, a complete LFO wrap,
  both tap extremes and every phase/tap/gain/remainder update.
- 6000 frames cover 48→44.1, history-only, 44.1→48→44.1 with preserved phase,
  gain and fractional state. Clear cancels each of the five FSM states; held
  config and config/history priority are also checked. A numerical test exhausts
  all triangle values and verifies the exact rational LFO average.

This is a component source/behavior result. Runtime Reverb and complete effects
chain order/mask/maintenance validation remain separate work. Constant delay
division still needs synthesis and routed timing evaluation. There is no resource,
CDC, board, SRAM, Flash or perceptual acceptance claim. Rollback is omission of
this independently named source; accepted selection has not changed.
