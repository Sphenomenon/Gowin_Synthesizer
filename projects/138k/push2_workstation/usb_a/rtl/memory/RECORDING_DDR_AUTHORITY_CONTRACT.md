# Recording DDR controller/ledger authority

`workstation_recording_ddr_authority` grants a recording transport at most one
controller/ledger epoch per genuine common root reset. It reuses the maintained
runtime memory guard for clock qualification and post-grant availability loss,
and adds two memory-domain state bits to cover ledger loss before that guard's
first grant. It owns no recording object, parser, address allocation or data.

## Ports and binding

| Port | Binding and ownership |
| --- | --- |
| `root_reset_ni` | Genuine system root reset only. It must assert the actual native DDR controller/PLL reset and all global command/return ledger and queue resets. Do not include UI/video/BIST/calibration, CPU-only, BLE-object, mux-local or compute-only resets. |
| `control_clk_i` | Continuously running 50 MHz reference clock used by the existing guard. |
| `memory_clk_i` | Actual DDR UI/owner-ledger clock. |
| `ledger_reset_ni` | Reset deasserted for every global DDR command queue and return ledger that can produce the recording response. It must be low whenever any such identity is reset. Assertion may be asynchronous; release must be local to `memory_clk_i`. |
| `backend_ready_i` | Continuous recording-use qualifications, such as calibration and BIST complete/pass, plus any required compute qualification. This status proves readiness, not response draining. |
| `channel_ready_o` | Memory-domain admission/native-accept/response authority, with asynchronous closure on loss. Bind the mux's `channel_ready_i` here and gate every bypass path consistently. |
| `started_o` | Existing guard's control-domain sticky first startup acknowledgment. It survives local ledger/backend loss; only root reset clears it. |
| `boot_seen_o`, `epoch_survived_o`, `epoch_lost_o` | Memory-domain diagnostic state. `epoch_lost_o=boot_seen_o && !epoch_survived_o` remains asserted after ledger loss. Synchronize these before another clock domain samples them. |
| `fault_o` | Asynchronously asserted summary of epoch loss or the existing guard fault. Use as a fail-stop input; synchronize it for control/status sampling. It is not a source of reset or automatic retry. |

The authority's two-edge local root release must complete **before the first
edge on which the global DDR ledger accepts requests**. This is a required
integration condition, not a reason to postpone `boot_seen` until readiness.
For the audited e855 native composition, platform `ui_rst_n` releases after
three UI edges, and HDMI's shared `ui_rst_n` after another three UI edges; the
authority's root release therefore completes before the ledger's first usable
edge. Recheck this relation if those boundaries change. Do not drive this port
with a CPU-only reset or a readiness bit that can miss an actual ledger reset.

## Epoch policy

`boot_seen` resets only for local release of the genuine root reset. At the
first memory edge with `ledger_reset_ni=1`, it becomes one. The separate
`epoch_survived` flop has the single asynchronous clear
`root_memory_reset_n && ledger_reset_ni`; it may become one only while the old
`boot_seen` value is zero. Thus the first usable edge records and survives the
epoch together. A later ledger-reset pulse clears survival immediately, even
if the memory clock stops. Because `boot_seen` stays one, recovery cannot set
survival again. No opposite asynchronous set/reset controls are required.

Survival qualifies both the existing guard's backend-ready input and the final
`channel_ready_o` output. A reset before BIST/ready, after the first usable
ledger edge, is permanent failure just like a reset after recording startup.
This includes an epoch containing only BIST or another non-recording read:
old global responses have no recording subowner or reset-generation tag.

Before the first usable ledger edge, no global command can have been accepted
under this reset scope, so initial reset waiting and pulses may wait for the
first release. Readiness changes before grant may also wait while the ledger
identity survives. After the existing guard grants startup, readiness loss or
clock-heartbeat expiry remains permanent failure, even without ledger reset.

Any loss must invalidate/fail affected objects. A new BLE recording, CPU reset,
connection, object ID, task generation, successful BIST, local mux reset, or
recovered PLL cannot reopen the channel. Keep object state independent from
controller recovery and do not replay accepted reads.

## Audited native reset scope

In e855 `rtl/workstation/workstation_hdmi_display.sv`, shared release includes
root reset, platform memory reset, and video source reset. That local UI reset
resets BIST and the real owner8 queues/core. Its exported ready is local UI
reset AND calibration AND BIST done/pass. A video PLL loss can therefore clear
the global owner ledger while the DDR controller itself is not reset. Repeated
ready assertions are not a proven generation fence.

The native top connects root `reset_n` to `ddr3_platform.rst_n`. The platform
connects it to `ddr_recovery_guard.reset_n`; the guard holds actual
`controller_reset_n` low for 256 reference cycles. This net resets the real
DDR PLL and drives the real vendor controller `rst_n`. Root reset also reaches
HDMI's shared UI reset and the global queues/core. Consequently a genuine root
reset asserts the actual controller reset as well as forgetting local tags.
The custom top ties the button input high; its normal root reset is FPGA
configuration/power-up, not a CPU, BLE or UI recover command.

The vendor controller implementation is encrypted. These source facts prove
reset wiring and complete platform reinitialization intent, not physical
read-return flushing, reset pulse integrity or hardware acceptance. A new
startup after root reset must retain the controller's own reset/recalibration
contract; the strongest operational recovery is full FPGA reconfiguration or
power cycle until board evidence validates a warm common reset.

## Verification and limits

`sim/memory/run_recording_ddr_authority.py --output <new-directory>` runs actual
authority/guard RTL with ten memory/reference clock phases. Each phase checks
17 scenarios and 666 conditions, including pre-ready and first-edge ledger
loss, short reset pulses, stopped-high/low memory clocks, readiness loss,
startup retention and root-only rearm. Six executable source mutations must
fail. The independent review additionally runs one phase with Verilator.

The review's boundary fixture instantiates the real e855 owner8 queues/core,
the actual two native bridges and mux. It reproduces old-return/new-subowner
aliasing under naive readiness, reproduces the existing guard's pre-grant gap,
and verifies the added authority blocks both pre/post-grant loss. Native read
returns and recovered BIST readiness are adversarial boundary inputs in that
fixture; it does not simulate the complete BIST FSM or encrypted DDR IP, and
does not claim that the full physical controller produced that sequence.

No production build selects this component yet. Production gate/reset wiring,
all bypass directions, fault-object behavior, first-edge release ordering,
minimum reset pulse widths, synchronizer routing, CDC/STA, native-controller
flushing, synthesis/resources and hardware acceptance remain separate checks.
Retain the existing memory guard's Gray-bus timing/skew constraints. Do not use
unit-test passes to claim safe repeated local rearm, DDR drain or deployment.
