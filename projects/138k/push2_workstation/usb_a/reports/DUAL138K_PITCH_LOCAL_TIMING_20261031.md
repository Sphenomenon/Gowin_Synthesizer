# M native pitch/divider local timing revision — 2026-10-31

The two maintained RTL changes passed exact offline arithmetic, cancellation
and32-voice oscillator regressions. They add no clock cycles. A new full
synthesis/P&R must establish timing and resources; this report records no
post-change timing benefit, physical acceptance or SRAM/Flash deployment.

## Actual paths and bounded changes

M5's `m-demo-base-v5-physical-v1/impl/pnr/custom_138k_integration.tr` reports
-3.135ns from `panic_epoch` through event/parameter admission to a coefficient
divider data CE. Its trace includes a1263-fanout shared gate, then a100-fanout
divider gate. `workstation_runtime_div147` already clears every valid bit on
flush and gates its final valid output immediately. Private data and tag
registers now advance under their local valid bit, including speculative work
on a flush edge. Their values cannot become a valid result after that flush.
Reset/flush of valid storage, immediate output suppression, fixed latency,
quiescent state and tag alignment retain the original contracts. Public voice,
ADSR, coefficient, parameter and session state are unchanged. Invalid scratch
values may advance; their bits are not a valid-payload contract.

M5's glide path is -3.084ns from `pitch/n23_s/DOUT` to `glide_ratio`. The trace
crosses the residual add, reciprocal DSP, step add, and a deep magnitude
comparison. `workstation_rate_pitch_expression` keeps its exact reciprocal
arithmetic and uses23-bit subtract-borrow tests for the final strict distance
comparisons: `distance-step-1` is nonnegative exactly when `distance>step`.
The selected upward/downward distance is nonnegative. A raw zero glide step
jumps directly to target; the existing reachable remainder invariant0..146
makes it equivalent to testing the derived step. Ratio clamp, continuous
vibrato depth behavior, fractional remainder, LFO phase, sample CE and every
output cycle remain unchanged.

No clocks, timing exceptions, ordinary modes, vector features, polyphony,
ADSR, audio precision or deadline were removed or relaxed. The oscillator
and vector RTL themselves were not edited.

## Verification

Combined local record: `/tmp/dual138k-pitch-local-pipeline-verification-v1.json`.

| Check | Actual result | Evidence |
| --- | --- | --- |
| Full-width independent pitch model |280k+ clocks,95k+ accepted samples;integer `/147` oracle checks continuous output,phase,glide and remainder each cycle;adjacent CE,immediate parameter/rate changes,full16-bit API,zero and max steps,clamps and adjacent saturation boundaries;locked48k16000-cycle reference preserved | `/tmp/dual138k-pitch-borrow-v2.log` |
| Pitch behavior mutations |Wrong upward borrow boundary and wrong zero-step predicate both rejected | same log |
| Exact reciprocal domain |16777220 combinational cases,40017 transactions;65536×256 input combinations;6 existing reciprocal/range/reset/state mutations rejected | `/tmp/dual138k-pitch-exact-v1.log` |
| Actual div147/helper |8 width/tag configurations spanning widths8..80 and tag RAM/register paths;53167 valid quotient/tag comparisons;416 flush edges;162 flush collisions with a currently visible result,including immediate pre-clock output kill;valid latency/quiescence/reset and tag reuse checked | `/tmp/dual138k-local-flush-arithmetic-v3/verification.json` |
| Six helper mutations |Wrong divisor,stale tag,wrong tag-ring address,retained flush valid,removed immediate output kill,skipped quotient digit all rejected | same record |
|32-voice oscillator and old independent oracle |672 frames,606 audible,688128 slot comparisons,34 PANIC cases;all A/B/C modes at both48k/44.1k;PCM/envelopes/slots/public state equivalent;max cycles69/165/1061 by mode at both rates,within1599-cycle assertion | same record |
| Oscillator mutations |Wrong slot tag and wrong gain tag rejected | same record |
| Source stability |All targeted-runner input hashes unchanged during run;`git diff --check` passed | same record and working diff |

The default complete arithmetic runner found a pre-existing current vector
source/provenance mismatch before compilation. Its default gate remains
active. New explicit `--oscillator-only` limits this targeted regression to
the changed helper and ordinary oscillator; it does not claim a complete
vector arithmetic regression. The helper's broad width/tag/flush regression
also checks its reusable contract. Generated oracles are test-only, reconstructed
from unchanged checked provenance and versioned baseline inputs.

Commands:

```sh
python3 projects/138k/push2_workstation/usb_a/sim/test_workstation_rate_pitch_expression.py
python3 projects/138k/push2_workstation/usb_a/sim/test_pitch_div147_exact.py
python3 projects/138k/push2_workstation/usb_a/sim/audio/run_runtime_arithmetic_pipeline.py --oscillator-only --output /tmp/dual138k-local-flush-arithmetic-v3
```

## Source identity and rollback

| Input | Before SHA-256 | Current SHA-256 |
| --- | --- | --- |
| `rtl/audio/workstation_runtime_div147.sv` | `359350552b6aa00a512068bd68a35cda7a15fad52faf5b23a0f91a893eca1d63` | `baf45bdf6374bdaf96bd20cd15269653103130bf803e36e588c81e904f966bf9` |
| `rtl/audio/workstation_rate_pitch_expression.sv` | `c4053635f66995bba38cf7726bff58a74308d7b2c85f4023548f16780f81d6f0` | `8d69922207e47c009c2340e18cd3704c0f433ed485338e8e03fe0fde2a30e8ef` |

The pre-change maintained inputs are present in commit `97700e8`. Rollback of
these two local edits restores those exact bytes; it does not reselect any
accepted profile or assert board state. New M/W profiles must bind changed
release inputs under new candidate identities. Original manifests, frozen
baselines, vendor bytes and accepted profile locks were not refreshed here.
