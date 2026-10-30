# Pitch /147 exact arithmetic candidate

This is a source and offline verification change. It replaces the native
runtime pitch glide's combinational division/remainder with a smaller exact
reciprocal expression. It adds no registers, ports, audio cycles, state-machine
states, clock constraints or effect-policy changes. It does not establish a
synthesis, P&R, routed timing, hardware, SRAM or Flash result.

## Locked input and reason

The source base is `d80b94a95d4b5ce7afd9d8eba6bc823f5bda859f`.
`rtl/audio/workstation_rate_pitch_expression.sv` initially hashes to
`12f54fa7783ea740b06c94c912a8517f6584c1e77668da995642c50f72ccf6a2`,
identical to that compiled in source candidate
`custom138k-workstation-r00-no-local-panel-v1-6b9610324164f0c9`.

That candidate's actual synthesis top path starts at pitch `n27_s/DOUT[16]`
(a clocked memory output), traverses `rate_glide_product`, and ends at
`glide_ratio_21_s0/D`: 36 logic levels, 30.438 ns arrival, 13.559 ns required,
and -16.879 ns slack. This is the existing synthesis estimate, not routed STA.
The independent review locks VG SHA256
`2cfe81e54a9257d212f4b54cecac56853a50e969dbf532d6857d45ce8fe316c8`.

## Exact arithmetic

For unsigned step `s` and retained remainder `r`, the old expression is
`q=(160*s+r)/147`, `next_r=(160*s+r)%147`.
Use `160=147+13` to define `t=13*s+r`, so
`q=s+floor(t/147)` and `next_r=t-147*floor(t/147)`.

For every 16-bit step and every 8-bit remainder, `0<=t<=852210` fits 20 bits.
The reciprocal is `M=456523=ceil(2^26/147)`, with
`147*M=2^26+17`. If `t=147*a+b` and `0<=b<=146`, then

`t*M/2^26 = a + b/147 + t*17/(147*2^26)`.

Because `852210*17=14487570 < 67108864=2^26`, the last term is less than
`1/147`. The fractional part stays below one, including `b=146`, so
`floor(t/147)=(t*M)>>26` exactly. The result is never rounded or corrected.
The 20x19 product fits 39 bits; its upper 13 bits hold the extra quotient.
The final 17-bit step retains the maximum reachable value 71331.

The reachable state remains `r=0..146`, initialized to 73. Only an accepted
44.1 kHz sample with nonzero step updates it. Zero step immediately follows
the target and retains the remainder; 48 kHz uses the original full 16-bit
step. Rate switches retain glide, phase and remainder. The continuous
one-clock vibrato modulation pipeline is unchanged.

The direct original-numerator alternative is also exact with
`M=14608733`, shift31 and a 48-bit product. The selected residual expression
reduces its arithmetic widths. Actual DSP mapping, logic levels, area and
timing still require a fresh synthesis and physical candidate; source width
alone is not evidence of improvement.

## Offline verification

- `sim/test_pitch_div147_exact.py`: all 852211 residual-numerator values by an
  independent integer proof; actual RTL all 65536x256 step/remainder pairs,
  full 48 kHz step range and 40017 clock transactions against the original
  division/modulo formula. Transactions cover reset73, step0 remainder hold,
  CE hold, 44.1/48 switches, arbitrary depth changes, up/down glide and output
  clamps without an added cycle.
- Six negative controls must compile and then fail: adjacent reciprocal
  constants, 16-bit quotient truncation, reset bias removal, zero-step clear,
  and updating the remainder in 48 kHz mode.
- `sim/test_workstation_rate_pitch_expression.py`: original locked 48 kHz
  bit equivalence, 44.1 kHz cumulative glide/physical duration, LFO, maximum
  step and forward/reverse switch state.
- `sim/test_current_workstation_sources.py`: 17 source-boundary tests.
- `sim/audio/run_runtime_audio.py` against the locked 6b prepared source:
  20192 checked frames, 14 configuration acknowledgements, 12 applications,
  8 mid-frame switches, maximum 1204 render clocks, both-rate wet paths and
  actual oscillator/effects/final PCM/serial composition. Source hashes stay
  unchanged throughout the run. This is functional simulation only.

No accepted build-profile selection or frozen baseline is changed. Rollback
is the parent commit's single pitch RTL file; the new tests/report can remain
as independent verification material. Integration requires a new source
identity and fresh synthesis/physical evidence before deployment claims.
