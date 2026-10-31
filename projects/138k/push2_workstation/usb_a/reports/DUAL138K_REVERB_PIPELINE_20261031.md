# M/W native Reverb local pipeline — 2026-10-31

Maintained source and offline regression passed. This revision requires a new
candidate source identity and actual synthesis/P&R before any timing claim;
it is not SRAM, physical audio/HDMI or dual-board acceptance. No clocks,
exceptions, effect coefficients, room lengths, sample precision or features
were relaxed. Accepted profile hashes remain unchanged.

## Actual failure and local change

M's `m-demo-base-v5-physical-v1/impl/pnr/custom_138k_integration.tr` reports
6389 setup violations in `audio_76m8`. Reverb's worst path is -3.144ns from
`frames` to a DSP A input; a second path from applied rate to a Reverb DSP A
input is -3.142ns. The path trace crosses the history predicate, a combinational
DSP multiply, wide carry/saturation logic and the next DSP's input register.
These are measured pre-change failures, not predicted post-change timing.

The maintained Reverb now registers FDN history-valid bits when accepting the
frame, and registers each early tap's history-valid bit/gain while preparing
its existing RAM address. The 44.1kHz damping's two exact 64-bit products are
registered in state2 and summed/saturated in state3; 48kHz keeps its original
signed mean. Hadamard pair sums move to state4, h/tail mix to state5, loop gain
to state6, and feedback to state3 of tap1. These operations use existing early
RAM wait cycles. All twelve taps, FDN memory accesses, final frame publication,
gain slew, clip detection, configuration fences and PANIC behavior retain their
external cycles. Explicit signed extensions document existing arithmetic and
remove width warnings from the maintained Reverb.

The original `.provenance.json` remains byte-for-byte unchanged. New additive
`workstation_runtime_spatial_reverb.pipeline.json` records exact reversible
steps from the original native source through the already-maintained scratch
split to this pipeline. `tools/workstation_reverb_provenance.py` checks each
identity and anchor, round-trips every step, and reaches the unchanged frozen
prepared baseline. It is a verifier, not generated production RTL. The
independent Reverb test reconstructs the old scratch module only as a test
reference and compares every external output/control on every clock.

## Validation

Combined local record: `/tmp/dual138k-reverb-pipeline-verification-v1.json`.
Generated simulations, binaries and logs stay outside source.

| Check | Result | Evidence |
| --- | --- | --- |
| Independent Reverb and old prepared/scratch references |6 tests passed;132300 frames at44.1kHz,144000 at48kHz,30000 random frames,18000 rate/history changes; every output/control cycle compared with old scratch;174000 frames also compare old48kHz prepared output; max80 cycles | `/tmp/dual138k-reverb-pipeline-v3.log` |
| Tail statistics |Three-second fixed-point impulses passed; dual-rate extrapolated RT60 relative difference -0.206896%; functional model statistics, not measured acoustic RT60 | same log |
| Cancellation and configuration |16 RAM/pipeline cancellation boundaries and held configuration/history priority, including complete high-half RAM write drain | same log |
| Complete default native effects |14 tests passed;48kHz36288 exact reference frames;44.1kHz24288 frames;44512 reorder/bypass/maintenance frames; max105 cycles; PANIC/rate collisions and stopped clock/fence failures retained | `/tmp/dual138k-reverb-effects-v2.log` |
| D-only full native effects |2292 frames,17 events,dual rate;27 retired reads/27 retired writes rejected;128 FFT bins | `/tmp/dual138k-reverb-d-only-v2/verification.json` |
| Provenance drift rejection |Changed maintained source, original provenance or additive adaptation each rejected | `/tmp/dual138k-reverb-provenance-v1.json` |
| Warning gates |Maintained Reverb has zero compile warnings; strict reference/support warning totals retained (independent26 width-expand/8 truncate, effects55/16,each plus one historical timescale warning) | unit logs |

Commands:

```sh
/opt/homebrew/bin/python3.14 projects/138k/push2_workstation/usb_a/sim/test_workstation_runtime_reverb.py
python3 projects/138k/push2_workstation/usb_a/sim/test_workstation_runtime_effects.py
python3 projects/138k/push2_workstation/usb_a/sim/audio/run_demo_d_only.py --project /Users/sphenicidition/.cache/gw138k-dual-20261031/m-demo-base-v5/workstation/Prj1 --output /tmp/dual138k-reverb-d-only-v2
```

The first independent run under macOS system Python3.9 completed its RTL
comparisons but could not compute `statistics.linear_regression`. The final
complete run uses the existing Python3.14; no assertion or model was removed.

## Bound source identities and next physical check

| Maintained input | SHA-256 |
| --- | --- |
| `rtl/audio/workstation_runtime_spatial_reverb.sv` | `3e5e46d80f19d46347dc25dc6493a5f7290c8056846a9a17ced70673e3def846` |
| Original `.provenance.json` | `3ca4cbf55bb0dea90f67f08388fee5fd2460532ed8a64cc7f64a9d3b8bf01a52` |
| Additive `.pipeline.json` | `fa5d015a145ba4b89ece7b8662eb3e2d7e7fc1c811131ec7a173fab19b415328` |
| `tools/workstation_reverb_provenance.py` | `42ed59e654d63706dfda75f64ef9490ec3be9b4b013382d66821556e51a2fe7b` |

New M/W source preparation must consume these maintained bytes and bind the
additive provenance/verifier. The unchanged scratch parent is
`e9a93b4cf51fe8aae7ff46cd92e08b073314e87241d786eea7f445bc6bebbbb1`;
the original native parent is
`fc4cacd3acd2c0cd6b73ee496bfa4db30e17be9d8018a9364e51eeff07c0d05d`.
These identify the exact rollback path; they do not inherit physical acceptance.
The next full P&R must measure DSP register placement, all remaining audio
paths, actual resources, CDC and every required clock. No resource benefit or
timing closure is pre-recorded here.
