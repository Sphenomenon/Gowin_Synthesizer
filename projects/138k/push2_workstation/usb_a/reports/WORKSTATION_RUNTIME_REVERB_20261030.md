# A07 runtime effects stage 4: independent fixed-point Reverb

2026-10-30. `rtl/audio/workstation_runtime_spatial_reverb.sv` is independently
implemented and offline verified. No profile/build/top selects it. Full identities
and metrics are in
[`workstation_task_20261030/runtime_reverb.json`](workstation_task_20261030/runtime_reverb.json).

## Source and behavior

The exact reference is actual F02 rev2 `rtl/audio/serial_spatial_reverb.sv`,
commit `3d4b3175d0f20d0b787b61b43e4543739b26bca1`, identity
`custom138k-workstation-v1-f5b723250388add5`. Prepared source SHA256 is
`cd07919c8fd4903c4ebf1b821346afa6c6df381e61d9bf7d3eab2ea85378cd39`;
native SHA256 is
`31ec6580986a0848ca13c80f4fb08759489ee5e49bbaa2fabeeb4c163c241619`.
Adjacent provenance reverses every exact edit to those bytes. Tests reconstruct
the reference, original preset, arithmetic package and banked RAM from versioned
baselines, without a private staging/results dependency. Frozen sources, manifests
and public events remain unchanged.

The module uses the stage-1 versioned runtime coefficient bank. 48 kHz retains
the original six stereo early reflections, FDN lengths `[1429,1789,1999,2131]`,
exact `(old+tail)>>>1` damping, Hadamard/2 network, feedback rounding and output
arithmetic. At 44.1 kHz the logical FDN lengths are `[1313,1644,1837,1957]` and
early taps come from the matching bank. Damping uses complementary signed Q31
coefficients `1009899529` and `1137584119`, summing to `2^31`; signed 64-bit
products and sum shift right by 31 before saturation. These preserve the matched
physical pole established in stage 1. Wet slew is 139 plus carried 47/147 rather
than the original 128/frame.

RAM capacities stay at the original 48 kHz lengths and 2048 early words. Rate
changes alter logical wrapping and initialized-frame gates, without adding DDR
allocation or extending arrays. This is source geometry, not a physical resource
count or acceptance result.

`config_valid_i/rate_44100_i/config_ready_o` and
`history_clear_i/history_ready_o` are valid/ready requests at true quiescence.
Config has priority. Both clear logical pointers, damping, tails and initialized
frames while preserving wet gain/remainder; config also applies the rate.
`config_applied_o/history_done_o` pulse at the single-domain application edge.
Requesters drop valid after acceptance. Legacy clear immediately cancels work and
resets gain/remainder. The banked RAM clears pending read/write control, leaving
payload untouched and masked by logical history gates.

Quiescence includes the output-valid tail and the high-half write following the
output frame. Tests check every actual banked RAM `write_pending` is clear when
the module reports quiescent. Thus a rate/history request cannot cut through the
second half of an accepted RAM word.

## Offline validation

```sh
python3 projects/138k/push2_workstation/usb_a/sim/test_workstation_runtime_reverb.py
```

Six tests passed with Verilator 5.052. Exact compile-warning counts are checked:
one inherited package timescale, 26 signed-widening warnings across the exact
reference/native arithmetic and frozen RAM, and eight frozen RAM index-width
warnings. Coefficient/config logic and the testbench add no width warnings.

- 30000 signed random 48 kHz frames compare every clock against the exact
  prepared reference and every output against an independent frame-domain integer
  model, including 249 clipping outputs and legacy clear.
- Three-second impulse responses compare every output and clip: 144000 frames
  at 48 kHz, also per-clock against prepared reference, and 132300 at 44.1 kHz.
  First wet arrivals are frames 159 and 146 respectively. Impulse tests do not clip.
- 18000 frames cover rate changes, history-only and legacy clear with gain and
  fractional state retained where required. Sixteen RAM/pipeline cancellation
  boundaries and held-config priority are checked. Observed component render
  latency is 80 clocks at both rates; this is not a whole-chain audio budget.

The deterministic fixed-point tail metric integrates stereo response energy
backward, normalizes at 30 ms after dry/early reflections, fits −5…−25 dB and
extrapolates to 60 dB:

| Rate | T20-extrapolated RT60 | Final 0.25 s peak | Final stereo sample |
| --- | --- | --- | --- |
| 48 kHz | 1.522436291 s | 4 LSB | `[-1,0]` |
| 44.1 kHz | 1.519286430 s | 5 LSB | `[-1,-1]` |

The relative decay difference is −0.206896%. This definition differs from the
stage-1 float64 FDN-only measurement and is not measured acoustic RT60. Few-LSB
residuals remain after three seconds; the result does not establish zero limit
cycles or infinite-horizon nonlinear stability.

Complete effects chain order/mask/maintenance and the global runtime controller
remain separate integration work. Signed coefficient multiplication and delay
selection still need synthesis, resources, routed timing and CDC checks. No board,
SRAM, Flash or perceptual acceptance is claimed. Rollback is omission of this
independently named source; accepted profile selection has not changed.
