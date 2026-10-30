# Runtime memory guard: startup qualification and permanent loss isolation

Date: 2026-10-30. Scope: a new standalone runtime guard, its contract and its
targeted regression. This report does not qualify a selected build profile or
claim synthesis, routing, board behavior, SRAM deployment or Flash deployment.

## Problem and behavior

Using DDR/UI/calibration readiness as the runtime reset would clear notes,
parameters or epoch on backend recovery while an arbiter might retain an old
transaction identity. The new guard separates one-time startup from continuing
availability. First startup waits for backend qualification, a real memory
heartbeat, a three-memory-edge gate release, and acknowledgment of that gate.
Thereafter any detected availability or clock failure permanently closes the
channel and mutes. `started_o` remains asserted; only common system reset clears
the startup grant and fault. There is no replay, epoch input or recovery input.

`reset_ni` is common system reset only. DDR client reset/readiness and compute
PLL qualification belong to backend availability; they must not clear the
runtime session. The top owns `runtime_reset_n=common_reset_n && started_o`,
all request/ready/response gates, fault propagation and the compute mute CDC.

The availability stretcher captures a pulse between both clocks and holds it
for three control edges. The fault latch is armed before a grant can reach the
memory domain, including the interval before startup is acknowledged. The
registered Gray heartbeat is reset only by common reset and detects a source
stopped high or low without depending on another source edge to close the gate.
The backend fault code is 1; heartbeat timeout is 2; the first code is retained.

## Frozen implementation

All paths in this table are relative to `projects/138k/push2_workstation/usb_a/`.

| Input | SHA-256 |
| --- | --- |
| `rtl/memory/workstation_runtime_memory_guard.sv` | `c07b1db351c3a2851e5ba9446801a73cad99e90b5155afaed8c2fec6c4b3424d` |
| `rtl/memory/RUNTIME_MEMORY_GUARD_CONTRACT.md` | `4edc8afa7874a5f2be68e2d7ac2be70fb3d54cedeb7fbef9005733cab99ed98e` |
| `sim/memory/tb_workstation_runtime_memory_guard.sv` | `9f178c1d84b15479700beed4991222f9fcb972454e17249ecb9e372e937dabf9` |
| `sim/memory/run_runtime_memory_guard.py` | `f084e8b8ebdf0f60a17c7918349f6476ac2051275c51a454d533900a920369ac` |

The guard allocates no DDR storage, changes no event format, and has no DSP
reset output. This six-file phase does not edit accepted providers, locked
baselines, vendor bytes, top-level composition or build source-selection tools.
Parent integration is separate work with separate source identity and checks.

## Targeted verification

Reproduce from the repository root, choosing a new output directory:

```sh
python3 projects/138k/push2_workstation/usb_a/sim/memory/run_runtime_memory_guard.py \
  --output /Users/sphenicidition/.cache/gw138k-task-20261030/runtime-memory-guard-review
```

Final evidence:

- Directory: `/Users/sphenicidition/.cache/gw138k-task-20261030/runtime-memory-guard-r5/`.
- Identity: `runtime-memory-guard-offline-v1-87c482b44a9cd5b8`.
- Source-set SHA-256: `87c482b44a9cd5b8f698d57ea3cb57a0bd115f1d9cc2bee1ec6e6291bb6da071`.
- `verification.json` SHA-256: `34a1e54530efdd174f7b3cba96d9eb6013835f8c516463e7f1f5c186d537650d`.
- Standalone Verilator lint: passed, zero warnings. Verilator guard/TB
  compile: zero warnings. Icarus compile: zero diagnostics.
- Verilator and Icarus: identical metrics, 10 phases, 2,270 checks, 129 source
  counter wraps, one pre-loss accepted read and zero delivered responses.
- Inputs were hashed before/after and unchanged throughout the final run.

The clocks are 50 MHz reference and 100 MHz memory, with memory first rising at
7 ns rather than at a reference edge. A 12-cycle/four-bit instance accelerates
fault tests and exercises many counter wraps. A separate unmodified default
500-cycle/32-bit instance checks production parameter behavior.

| Phase | Evidence |
| --- | --- |
| Initial wait | More than a timeout with backend unavailable never faults; backend ready with a stale stopped clock cannot start; fresh heartbeat permits first startup. |
| Normal progress | Repeated source counter wraps do not spuriously fault; startup is observed only after actual memory gate acknowledgment. |
| Sub-cycle ready loss | A 1 ns pulse between both clocks closes/mutes immediately and remains captured after raw availability returns; a queued old response and new requests/acceptance remain blocked. |
| Sub-cycle reset loss | A 1 ns backend reset pulse closes the gate without waiting for a memory edge and locks fault code 1. |
| Loss before startup acknowledgment | Once the grant is armed, a loss permanently prevents first startup and cannot grant a second attempt. |
| Source stopped high | Fault code 2 after 16 reference cycles with timeout 12; gate closes despite no new memory edge. |
| Source stopped low | Same 16-cycle result and asynchronous closure at a fixed-low memory clock. |
| Backend loss while stopped | Availability still closes the channel asynchronously and preserves fault code 1. |
| Default watchdog | Timeout 500 faults after 504 reference edges with the source stopped; recovery cannot reopen. |
| Common reset | Clears the grant/fault and permits a fresh legitimate startup. Faults before reset preserve started/runtime reset. |

The conservative nominal digital clock-loss limit is 505 reference edges,
10.1 microseconds at 50 MHz. This includes heartbeat synchronization, age and
fault-latch latency. Availability loss has asynchronous closure, subject to
device minimum reset pulse width and routed propagation. The final fixture
uses an explicit first reset edge after event controls are active; preliminary
or failed test-harness caches are not acceptance evidence.

## Remaining integration and physical checks

Gate request validity, upstream ready/acceptance and returned response validity
together for every affected client. This regression uses a boundary model that
retains one accepted read; it does not instantiate real DDR arbitration or TF/
delay DMA. The owners must fail/invalidate affected objects, and a common reset
must reset the real arbiter/queue identities before a fresh startup can be safe.
Responses already delivered before the fault cannot be withdrawn.

The top must separately prove that DSP note/parameter/epoch state is preserved,
TF fails closed, display/BLE trust degrades, clock-service recover cannot hide
the fault, and mute crosses with asynchronous assertion/local synchronous
release. Realtime sample scheduling must continue with defined silent output.

Constrain `memory_gray[*]` to `gray_meta[*]` maximum delay and bus skew to one
actual memory clock period; retain second stage `gray_sync`. A broad false path
is insufficient. Review routed CDC/reset release, synthesize/route the explicit
profile, verify hardware SMUTE/serial behavior and gather actual fault/recovery
board evidence separately. No such physical stage was run in this phase.

Rollback: remove this standalone guard from the explicit runtime composition
and restore the previous composition source identity as a separate candidate.
Do not silently replace an accepted profile or treat the pre-guard composition
as backend-loss safe. This phase itself changes no accepted build selection.

Parent independent verification reran the complete runner into `/Users/sphenicidition/.cache/gw138k-task-20261030/runtime-memory-guard-parent-final`. Both simulators reproduced all 10 phases, 2,270 checks, 129 wraps, suppression of the previously accepted read, and the 504-cycle default stopped-clock result. Every recorded source hash was independently rechecked. The machine-readable report retains the parent verification SHA-256 and matching metrics.
