# Chorus44.1k exact affine replacement — 2026-11-01

The maintained Chorus now replaces only the44.1k `rate_delay` product/divide chain with one unsigned affine product and shift. The M12b far routed path identified the original triangle×441 followed by divide-by5 before the read address. No resource or routed timing improvement is claimed until a fresh physical candidate measures it.

For every16-bit triangle `t`, the old result is `floor((144670720+441*t)/327680)`. The new result is `441+((361267*t+134225920)>>28)`. The complete sum fits35bits. State0 sampling, registers, latency, PCM arithmetic, history behavior, clear behavior, and the48k branch remain unchanged.

The complete old M12 module is retained as a pinned simulation-only fixture (`a2e09369634b35628920c3198b0020a51a0d4154fe690a2faf93465f8ff57900`). New production source SHA256 is `28ef32d47d55a0d44eef8ec23fa3437cdbef647d4ca0b023f98cb184bd8ce50c`; provenance tool SHA256 is `d27fb401157c4b936400d06a677a054f0d35ba4797aba3598e2f046165304dd7`. The new reversible layer restores those exact M12 bytes before the unchanged scratch, narrowing, and original prepared-source chain. Original manifests are unchanged. Two targeted lineage tests prove byte roundtrip and reject identity, missing/duplicate anchor, and parent drift.

Validation passed:

- Actual SV function execution:131072 checks, all65536triangles at both rates, compared with the exact complete M12 fixture, the original native reference, and a separate64-bit physical-time oracle. Four source mutants and eight provenance negatives were rejected.
- Actual-source Z3:44.1k old/new mismatch UNSAT over the complete16-bit domain;35-bit overflow UNSAT;48k independent tap-rule mismatch UNSAT. Wrong coefficient, wrong bias, and truncated assignment each produce a reproduced counterexample.
- Complete Chorus:8tests; five scenarios;3026811half-cycle comparisons of all12public outputs plus pipeline/history/PCM state. Includes60000frames per rate, complete44.1k LFO cycle,6000switch/history frames, cancellation in all five FSM states, and held configuration/backpressure. The independent PCM/time oracle also passes.
- Complete effects chain:16tests;105088long-scenario frames, all effect orders/masks, maintenance, PANIC/fence collisions, and stopped-clock failure behavior. Maximum observed valid latency remains105cycles. An initial missing `sample_slot_ready_o` testbench hookup failed the strict warning check; the unused output is now explicitly connected and the unchanged warning checks pass. Its initial failure log is retained.

The fixture contributes its inherited product-extension/base-truncation warnings to the complete Chorus test; the new affine arithmetic contributes none. Complete effects warnings remain the existing1timescale/55expand/16trunc set. No warning allowlist was relaxed to conceal the missing pin.

Machine-readable identities and retained evidence hashes are in [the JSON report](dual138k_chorus_affine44_20261101.json). Evidence directory: `/Users/sphenicidition/.cache/gw138k-dual-20261031/chorus-affine44-20261101-v1/`; final exhaustive report is under `exhaustive-final/`, SMT queries and counterexamples under `smt/`.

Reproduce from `projects/138k/push2_workstation/usb_a` with Python3: `sim/audio/run_runtime_chorus_delay.py --output <new-cache-dir>`, `sim/test_workstation_runtime_chorus.py -v`, and `sim/test_workstation_runtime_effects.py -v`. Run `sim/audio/prove_chorus_affine44.py --output <new-cache-dir>` with a Python containing Z3 (this verification used `/Users/sphenicidition/miniforge3/bin/python3`).

This is an offline source stage. It does not accept synthesis, P&R, hardware, SRAM, or Flash deployment, and carries no bitstream identity. Existing sealed W11 and M12b candidates remain unchanged. Rollback is the exact old M12 source plus reversal of this isolated provenance/test stage.
