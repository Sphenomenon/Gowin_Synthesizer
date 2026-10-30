# Runtime memory qualification and permanent isolation

`workstation_runtime_memory_guard.sv` grants a single memory-backed runtime
startup after the backend is available and the memory clock is progressing.
After that grant, a loss closes the channel permanently until a common system
reset. Backend recovery does not constitute a new session and must not replay
an accepted read, clear notes, reset parameter state, change the runtime epoch,
or grant the client a replacement DDR transaction identity.

## Inputs and clock ownership

| Signal | Contract |
| --- | --- |
| `reset_ni` | Common system reset only. Do not include DDR/UI/calibration/BIST, CPU-only reset, video readiness, or compute PLL readiness in this reset. Assertion must satisfy device reset pulse requirements. |
| `clk_50m_i` | Continuously running 50 MHz control/reference clock. Watchdog bounds assume this clock continues. |
| `memory_clk_i` | Actual memory-client clock, not a nominally related substitute. Heartbeat and channel release run here. |
| `backend_reset_ni` | Memory-client domain reset deasserted, e.g. DDR `ui_rst_n`. Assertion is an availability loss, not a common reset. |
| `backend_ready_i` | All qualifications required continuously while this runtime uses memory: e.g. DDR reset deasserted, calibration complete, BIST complete/pass, and compute PLL qualification. Any included qualification falling after grant is permanent failure. |

The HDMI memory authority supplies `ddr_client_reset_no=ui_rst_n` and
`ddr_client_ready_o=ui_rst_n && calib && bist_done && !bist_failed`. The explicit
runtime top may combine the latter with compute PLL qualification as
`backend_ready_i`; the guard does not own either backend status or PLL policy.

The common reset asserts asynchronously and releases independently after three
local control/memory edges. Backend availability is a separate asynchronous
assertion, three-control-edge release stretcher. This captures a short reset or
ready pulse between both clocks and gives the sticky fault latch time to record
it. Minimum physical reset pulse width and routing remain implementation checks.

## Outputs and lifecycle

| Signal | Contract |
| --- | --- |
| `clock_alive_o` | At least one synchronized registered-Gray heartbeat change has been observed and the last observed progress has not aged out. Liveness only; this does not certify memory clock frequency or timing. |
| `channel_open_o` | Memory-domain transaction gate. Opens after three memory edges following the first grant; closes asynchronously on raw/stretched availability loss, common reset or sticky fault, even with the memory clock stopped. |
| `started_o` | Sticky startup acknowledgment in the control domain, set only after the real memory gate has opened and its acknowledgment has crossed back. Only common reset clears it. A later fault must not reset the runtime. |
| `start_ready_o` | Started, open acknowledged, stretched backend availability present, and no sticky fault. Falls immediately with stretched availability or sticky fault. |
| `mute_o` | Inverse of `start_ready_o`; the top must safely cross/assert it into the output mute path. This module has no compute clock or DSP reset output. |
| `fault_o` / `fault_code_o` | Permanent fault once the first grant is armed; code 1 is backend/PLL qualification lost, code 2 is heartbeat expired, code 0 is no fault. Backend loss wins when both first appear together. The first code is retained. |

Before the first grant, missing readiness or heartbeat may wait indefinitely
without latching a fault. The fault latch arms before the memory gate can open,
so a loss between grant and `started_o` cannot reopen or retry. Once started,
the top must derive runtime reset from `common_reset_n && started_o`; adding
backend readiness or PLL qualification would wrongly erase notes and epochs.

The source-domain heartbeat counter resets only for common reset. Binary count
and Gray encoding of the next count are registered together, and Gray crosses
two reference flops. The default 32-bit counter is sampled by a 50 MHz control
clock. A test-only four-bit counter exercises repeated wraps. Choose counter
width and timeout so ordinary progress cannot alias an entire counter wrap
between every reference sample; no frequency acceptance claim follows from
this liveness monitor.

With the default `HEARTBEAT_TIMEOUT_CYCLES=500`, the digital stopped-clock bound
after prior startup is at most 505 control edges from stopping at either level,
including synchronization and latch latency: 10.1 microseconds at 50 MHz.
The directed asynchronous-phase test observes 504 edges. This is a cycle-model
bound with a continuing control clock, not an absolute metastability resolution
or physical propagation guarantee. Shorter tests use a 12-edge timeout.

## Required integration

Gate request validity, upstream ready/acceptance, and response validity with
the same `channel_open_o` for every affected client, including delay and both
TF service/command-buffer paths. Gating only requests permits old responses or
apparent acceptance to escape. The common gate prevents delivery after loss;
it does not revoke data already delivered before the loss or inspect DDR tags.

Each owner must fail or invalidate the affected object and reject later
continuations. A new request, object, CPU reset, epoch value, backend recovery,
or clock-service recover request cannot rearm this gate. A full common reset
may establish a fresh startup only when the backend's own common-reset contract
also clears old arbiter/queue identities. No automatic read replay is allowed.

Use the sticky fault for the aggregate clock/DSP failure policy, TF failure and
display/BLE trust status. Keep realtime sample scheduling independent of TF,
display and status handling; fault handling must mute or provide defined silent
data rather than stall the schedule. Cross the mute into the compute domain
with asynchronous assertion and local synchronous release in the owning top.

Physical implementation must constrain `memory_gray[*]` to `gray_meta[*]`
maximum path delay and bus skew to at most one actual memory clock period,
and check the resulting routed CDC/reset paths. Broad false paths alone do not
preserve Gray coherence. `ASYNC_REG`/`syn_preserve` mark the synchronizers but
do not replace routed constraints, CDC review or board acceptance.

## Verification boundary

`sim/memory/run_runtime_memory_guard.py` exercises the actual guard with 50/100
MHz clocks at different phases in Verilator and Icarus. A transaction-boundary
model retains one accepted read across a fault and verifies that its response
cannot escape; it also verifies that new acceptance and requests remain closed.
The regression covers initial wait, stale-clock startup refusal, gate
acknowledgment, repeated heartbeat wraps, sub-cycle ready/reset loss,
pre-acknowledgment loss, source stop high/low, source stop plus backend loss,
sticky startup and common-reset-only rearm, including the default timeout.

This targeted proof does not instantiate the DDR controller, real arbiter,
delay/TF DMA or DSP. Integration must separately validate all three directions
at each boundary, object invalidation, note/parameter/epoch preservation,
physical timing/CDC, hardware mute and board recovery. This change alone does
not qualify a build profile, bitstream, SRAM deployment or Flash deployment.
