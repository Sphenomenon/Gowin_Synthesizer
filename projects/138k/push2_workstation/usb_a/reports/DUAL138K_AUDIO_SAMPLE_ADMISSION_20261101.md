# Native sample admission: maintained source and offline validation

The actual native event workstation now uses the reviewed same-cycle `core_ce` cofactor. Known render-eligible controls force event/mode dispatch low, so stored runtime quiescence replaces the redundant current event/sample-ready/PANIC path. Lifecycle, native clear, real configuration, fault, effect-slot and joined-frame fences remain explicit. Five other known selector cases are zero; X/Z selectors retain the original complete expression. No register, sample cycle, interface, parameter authority or event contract changes.

Maintained event SHA256: `5569269a1d5ef02f2b1702f928d282fbab7455fba9af6ac229a97cbf8dc77bc9`. The new simulation-only complete fixture preserves exact pre-change bytes `fad0203c4322b54271ef6f413a7523478cfa5101609f5b2f72e280ae3894bf09`. Exact inversion and every NBA target/RHS/order are checked. Existing effect/event proofs explicitly verify this inverse before retaining their original source/priority gates. The unchanged render-service source stays pinned.

Validation consumed the maintained implementation:

- Two unrestricted binary source-equation proofs pass; ten removed-veto mutations have SAT counterexamples. Two exact source drift controls and three actual-source four-state mutations are rejected. Actual-source four-state tests cover139,792 vectors each for synth/no-synth.
- Complete M miter compares50 public outputs and31 private boundaries, including actual sample CE, PANIC, public parameter/config commits and pending state. It passes48,691 requests/responses, independent modeled wet PCM24,323 frames at48k and24,322 at44.1k,1074 cancellation edges, epoch wrap,12 cancellation boundaries and12 first legal followups.
- Complete W/legacy miters pass34 requests/responses each, all50 public outputs,25 common and7 native boundaries. W covers27 configuration commits,37 histories,88 events and28 fault checks.
- Existing event proof passes147,456 four-state vectors,7 misuse controls including3 actual-module runtime negatives. Existing effect-slot/configuration proof remains passing.

M compile warnings retain the reviewed candidate counts: PINMISSING35, TIMESCALEMOD1, WIDTHEXPAND42, WIDTHTRUNC12 and UNSIGNED2. No UNOPTFLAT is present. These are not zero-warning results. Every recorded proof/miter input is rehashed after completion.

Re-run with Python3 plus z3-solver, Icarus and Verilator. The two existing complete runners now offer explicit `--sample-admission-miter`; previous M13/M11 modes keep their original selection. On this host the existing Miniforge Python supplies z3, while the worktree login system Python does not; no environment was changed. Commands and exact inputs are in the JSON report and fixture README.

These are source/offline stages. They do not prove full-module formal equivalence, routed timing/resource improvement, hardware acceptance or deployment. Selected profile locks and input gates remain root-owned; prepare, synthesis/live mapping, P&R and real board audio/HDMI checks must follow under new candidate identities. The release-selection chain is unchanged.
