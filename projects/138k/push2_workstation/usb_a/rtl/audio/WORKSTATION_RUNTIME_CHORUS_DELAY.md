# Native Chorus delay arithmetic

`workstation_runtime_chorus_effect.sv` keeps the audited fixed parameters:
1024 history slots, base480 and depth96. The module rejects other values.
The explicit native dual-rate workstation profiles select this source; accepted
full83/full85 and the locked resource baseline retain their original inputs.

Only the combinational `rate_delay` function is narrowed. Sample acceptance,
read address registration, the five FSM states, wet slew, LFO phase/fraction,
configuration/history handshakes and legacy clear cancellation retain their
previous source bytes. No register, clock, cycle, buffer or DDS latency is added.

For every16-bit triangle value `t`, the old44.1k tap was:

```
floor(((480*65536 +96*t)*147 +5242880)/10485760)
= floor((144670720 +441*t)/327680)
= floor(floor((144670720 +441*t)/65536)/5)
```

The first equality cancels32 exactly, including the nearest-rounding offset.
The second follows from integer division composition for nonnegative integers.
`441*t <=28900935` fits25 bits; the rounded numerator is at most173571655 and
fits28 bits. Its high12 bits are divided by5. The resulting tap range is441..529.

At48k, `480 +floor(96*t/65536) =480 +floor(3*t/2048)`. The product is at most
196605 and fits18 bits; every original tap is retained, in range480..575.

The original `.provenance.json` remains immutable. The separate
`.rate_delay_narrowing.json` binds the exact old/new source hashes and one
function replacement. `tools/workstation_chorus_provenance.py` requires the
explicit `narrow_exact_rate_delay_v1` policy, reverses that replacement, then
verifies the unchanged original prepared-baseline chain. Runtime preparation
records this gate as `chorus_source`; it never generates the production RTL.
Changed or missing sources/manifests/anchors fail.

`sim/audio/run_runtime_chorus_delay.py` invokes both actual whole-module
functions for both rates and all65536 triangle values, comparing the exact old
native source and an independent64-bit physical-time rational. Width, rounding,
divisor and shift faults must fail; the provenance gate has separate negative
controls. The existing Chorus and full effect-chain regressions cover actual
PCM, clipping, LFO periods, rate/configuration/history changes and clear/PANIC.
Fresh synthesis and routed timing must establish the physical improvement;
functional equivalence does not establish timing or hardware acceptance.
