# M public configuration ready: maintained source verification

M17 far measured an audio configuration feedback path of −1.767 ns (default −1.945 ns). The maintained `gw138k_event_workstation.sv` now uses the existing broadcast cofactor for public `rate_ready_o` only when `{rate_commit_i,busy,event_rate_commit_i}` is exactly `3'b101`. A plain `case` sends every other or unknown control value through the original expression. No register, latency, sample/event admission, parameter broadcast or NBA changes.

The immutable prechange fixture is `5569269a1d5ef02f2b1702f928d282fbab7455fba9af6ac229a97cbf8dc77bc9`; maintained RTL is `b689d16fc95be1b25627d1471345f572292ec72f465e6e1ff80753e558abc1a6`. The versioned proof checks the exact whole-source inverse. Older proofs consume this checked inverse only for verification, never as a production input. All ten delivery files are listed with hashes in the adjacent JSON.

Validation passed:

- Unrestricted binary equivalence is UNSAT; five faulty implementations produce counterexamples.
- Actual M/W modules each passed 1,792 four-state vectors, including 768 unknown-rate and 80 idle-event vectors; five actual-module negative controls were rejected.
- Unreordered complete Verilator M/W/legacy services compare 50 public outputs, 25 common and seven native boundaries over 88,191 / 88,191 / 88,223 halfcycles. M/W each complete 34 request/responses and exercise 27 configurations, 37 histories, 88 events, 22 collisions and 28 fault checks.
- Six existing regression groups passed: sample admission, event configuration including module negatives, effect-slot admission, native protocol, composition and accepted-source 17/17. Eight owned Python files parse; diff whitespace check passed.
- Root independently reread 121 artifacts, 159 inputs and ten maintained/source snapshot pairs with zero hash differences. The agent also independently reconciled 157 hashes declared by final test results.

Icarus four-state execution requires cache-local same-scope declaration reordering; token identity and hashes are recorded. Sequential Verilator uses original declarations. Earlier failed attempts remain separate and are not counted as passes.

Evidence root: `/Users/sphenicidition/.cache/gw138k-dual-20261031/m17-config-ready-maintained-delivery-v1`. Seal SHA256 `7c520c8e33dae431dd54d9acff676dc1566ea30604da5b79f14a3335e06f0000`; verification `9de3cc7afa90df4331548ce7bef111fcb8f5abf4359aae5825923e56766a0b2f`; source list `c16be9939df3a49555b9b77ce8f32f741e7dc495b085a3268676ffba9570f6cf`. The adjacent JSON includes root review and complete input identities.

This is maintained-source/offline acceptance only. The M17/W15 locked and physical candidates remain unchanged. DEMO locks will be refreshed after the concurrent maintenance stages are sealed; the next candidate must prove actual consumption and measure synthesis/routed resources and timing. No resource or timing benefit, SRAM/Flash deployment, sound/video, wireless or two-board acceptance is claimed.
