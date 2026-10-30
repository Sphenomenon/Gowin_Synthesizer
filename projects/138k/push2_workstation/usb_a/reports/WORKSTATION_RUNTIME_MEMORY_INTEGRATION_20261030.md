# Real runtime state and owner-6 isolation under memory failure

Date: 2026-10-30. This phase adds a new testbench and runner around the actual
`workstation_runtime_controlled` and `workstation_runtime_memory_guard` owners.
It changes no runtime implementation, existing controlled regression, selected
profile, baseline, vendor model or build tool. No EDA or board action was run.

## Result and scope

The real APB path establishes held note 60 and nondefault volume/expression.
The original 16K-sample ring and 9600-sample delay run without state forces or
parameter shortcuts. After its normal warmup, an ordinary read is accepted
into an ordered functional DDR queue and retained across an availability loss.
The queue later returns that old read, but the guard suppresses its delivery.

Four fault cases pass: a 1 ns backend-ready loss, a 1 ns compute PLL
qualification loss, memory clock stopped high, and memory clock stopped low.
Every case preserves actual held notes, committed controls, panic identity,
applied-event count and nonzero stream epoch across failure, backend recovery,
CPU-only reset, attempted rate request and attempted recover request. The
hardware SMUTE composition asserts, while actual I2S decoding confirms 64
subsequent zero frames. A complete common reset then starts a fresh working
runtime; backend recovery alone never opens another transaction.

This is RTL composition verification using an ordered functional DDR backend,
not a DDR controller or a complete top-level simulation. The PLL qualification
input is controlled; no PLL primitive or actual compute clock loss is modeled.
The complete USB adapter and TF service are not instantiated. Routed CDC,
physical mute latency, metastability, timing and hardware acceptance remain
separate gates.

## Frozen inputs and reproduction

The fixture is independent of the existing controlled TB/runner. Prepared
reference dependencies follow the same source policy as that regression:
locked/prepared packages and migrations plus versioned native runtime sources.
The real official GW5A DCS model participates unchanged.

```sh
python3 projects/138k/push2_workstation/usb_a/sim/memory/run_runtime_memory_integration.py \
  --project /Users/sphenicidition/.cache/gw138k-task-20261030/f03-scan-window-profile-revision3/workstation/Prj1 \
  --output /Users/sphenicidition/.cache/gw138k-task-20261030/runtime-memory-integration-review
```

| Input | SHA-256 |
| --- | --- |
| `sim/memory/tb_workstation_runtime_memory_integration.sv` | `ed3cfac90569d981c081bcbcb400bea5cc5daaa22b92a0601ede48d8b1478d9b` |
| `sim/memory/run_runtime_memory_integration.py` | `3e8f420490faa1220ae1d253fc6f73b53fbfa87e66ad777a1361d93ceb1c78f7` |
| Guard dependency | `c07b1db351c3a2851e5ba9446801a73cad99e90b5155afaed8c2fec6c4b3424d` |
| Actual controlled dependency | `ce4f7c86e5412673698e4575a65ef312ba93a443f5fba757613a994cfdcb9b51` |

Final evidence directory:
`/Users/sphenicidition/.cache/gw138k-task-20261030/runtime-memory-integration-r2/`.

- Identity: `native-runtime-memory-integration-offline-v1-b11323ecf9606c66`.
- Source-set SHA-256: `b11323ecf9606c66c7e5bd02c134e6cdc63b0b97fc1d31728b3156d5ce9de319`.
- `verification.json` SHA-256: `94bcefe7d83f1d06218342a4d93200aa5429a5442c9affbdd8cce207e7ecd134`.
- Prepared reference identity: `custom138k-workstation-v1-d23d498ea824c9f9`.
- Input hashes, compiler command, logs and original data identities are sealed
  in that JSON. All inputs were unchanged before/after the final run.

The test uses real 76.8 MHz compute, 100 MHz memory and 50 MHz control clocks
with different phases, both audio reference clocks and the official DCS.
Startup qualification is shortened to the controlled regression's 500-cycle,
three-window setup; serializer mute/PDN use three/one frames. The memory guard
timeout is 25 control cycles; its separate primitive regression tests the
unchanged default 500-cycle watchdog. The delay ring, allocation, echo length,
queue data and runtime note/parameter implementations retain their real values.

## Measured coverage

| Metric | Final result |
| --- | ---: |
| Fault cases | 4 |
| Checks | 975,384 |
| Actual decoded physical I2S frames | 10,034 |
| Nonzero physical frames | 9,436 |
| Fault frames explicitly checked as zero with SMUTE asserted | 64 |
| Real APB transactions | 15 |
| Accepted/completed owner-6 reads | 6 / 6 |
| Old queued read returned after fault | 1 |
| Returned responses delivered after fault | 0 |
| Cycles with an actual DMA request blocked by the gate | 114,922 |
| Real backend writes | 2,488 |
| Simulation time | About 210 ms |

The first fault arrives after more than 8,000 additional physical frames from
the saved note/control snapshot; an ordinary ring read is genuinely pending.
The backend queue ignores client backend qualification/reset loss and only
forgets its identity on complete common reset. This deliberately challenges
the gate with the retained-response hazard rather than synthesizing DMA
completion or clearing the old queue at the failure.

Each failure immediately checks the three gate directions and hardware mute,
then restores backend/clock qualification. The physical serializer keeps
producing frames during the checked interval. After a four-frame drain margin,
16 frames per fault must be zero at the actual I2S pins and match the physical
PCM tap. State snapshots are compared after the fault, after 20 physical frames
following recovery, after CPU-only reset and after switch/recover attempts.
This finite interval is not a claim about unlimited fault operation or every
later watchdog transition.

Verilator reports zero warnings in the new fixture or guard, and no
`UNOPTFLAT`. The full closure retains 186 diagnostics outside those new files:
90 `IEEEMAYDEPRECATE`, 61 `WIDTHEXPAND`, 17 `WIDTHTRUNC`, 15 `PINMISSING`, two
`UNSIGNED` and one `TIMESCALEMOD`, from the unchanged official model and existing
native/legacy inputs. They are recorded and not suppressed or repaired in this
phase. A preliminary fixture checked audible output before the retained slow
attack had developed; the final run uses the existing controlled regression's
192-frame note settling interval. Preliminary cache r1 is not acceptance evidence.

## Read-only top composition review

Snapshot reviewed: `rtl/workstation/gw138k_push_workstation_top.v` SHA-256
`834d33600b26144d4009b8fc895295747b85ede87ad9152450a7c780e1de6249`.
These are source findings; this report does not assert mapped netlist endpoints
or routed path bounds for that top.

- The guard has only complete system `reset_n` as common reset. Its availability
  includes DDR client reset/readiness and compute PLL qualification. Runtime
  reset is `reset_n && memory_guard_started`, preserving session identity after
  backend loss. Controlled and runtime local DSP release chains depend on that
  runtime reset, so neither UI reset nor PLL qualification directly resets notes.
- The native delay request, returned ready and response all use the same gate.
  TF service acceptance/response, command-buffer input valid/output ready and
  final arbiter request are also gated. The command buffer has no response
  port. Its local DDR reset cannot grant reuse because the external guard stays
  permanently closed. TF traffic is source-reviewed only by this phase.
- An actual indirect reset hazard was found: passing compute `audio_reset_n`
  into `u_native_usb` cleared the retained adapter's `audio_online` state while
  leaving `connected` set. PLL recovery could manufacture a kind-15 attach,
  clear held notes and apply defaults despite a preserved runtime reset. The
  parent fixed only the explicit runtime branch at top lines 345–348 to pass
  `runtime_reset_n`; the original branch remains at line 350. Real USB detach
  and PANIC behavior remain owned by their existing lifecycle path. The fix is
  source-reviewed here, not exercised by this fixture's APB-only event source.
- The parent combines guard fault into clock-service aggregate DSP fault and
  TF runtime fault; display/BLE trust also requires guard readiness. The compute
  output-safe chain asserts asynchronously and releases after three compute
  edges, and physical SMUTE ORs the guard mute. Only the matching guard/mute and
  owner-6 composition is exercised by this regression.

## Remaining gates and rollback

Complete-top elaboration, a real USB adapter qualification-loss fixture, TF
object failure/late-response integration and full CDC/PLL endpoint mapping are
still required. Source mailboxes, Gray counters/pointers, independent status
bits, reset release and selected-clock paths need exact netlist endpoints and
routed propagation checks. Do not replace these with a broad false path or
claim this functional result is physical acceptance.

No board state changed. Rollback removes only the new fixture/report files;
the independently committed guard and the parent's top/profile changes retain
their own candidate identities and rollback procedures. Generated binaries,
waveforms and logs remain in cache rather than the source change.

父级独立复验完整运行同一 runner 至 `/Users/sphenicidition/.cache/gw138k-task-20261030/runtime-memory-integration-parent-final`，重现相同输入身份、四个阶段、975,384 检查、10,034 物理帧、9,436 非零帧及 64 个故障后零帧。真实旧 DDR 读返回一次、泄漏零次，所有输入重新核对一致；机器报告保留父级 verification SHA256 和指标。这仍是报告所述功能模型范围。
