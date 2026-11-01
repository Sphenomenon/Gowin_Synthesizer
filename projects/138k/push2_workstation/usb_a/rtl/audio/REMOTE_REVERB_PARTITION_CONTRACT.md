# Source-stage M/W reverb partition

This opt-in experiment moves actual `workstation_runtime_spatial_reverb`
computation and history storage from the M effects chain to W. It is not a
selected complete-workstation profile, a physical LCD protocol, a bitstream or
hardware acceptance. [Task3](../../../../task3.md) owns integration and gates.

## Composition and compatibility

`WORKSTATION_REMOTE_REVERB_PARTITION` exposes the experimental chain ports and
`REMOTE_REVERB_ENABLE`. With the macro absent, the preprocessed original
effects token stream and `reverb_stage` hierarchy remain identical. The
original provenance JSON stays immutable; the separate reviewed adaptation
reconstructs the exact previous source before its existing provenance checks.
The independent task2 checkout, source locks and candidate directories are
unchanged. This branch does not refresh old DEMO source locks to disguise new
inputs. Prepare task2 from its original checkout or frozen commit; new final
profiles are not registered by this source stage.

With the macro enabled, `REMOTE_REVERB_ENABLE=0` keeps the real local reverb;
`=1` selects `workstation_remote_reverb_m` in its place, with no local reverb
instance. Delay, Chorus, serial effect order, gains, precision and maintenance
remain in the existing chain. W uses `workstation_remote_reverb_w` around the
same maintained reverb. W receives M's committed per-frame enable/rate; it
does not own another parameter application point or modify local MIDI events.

## Bounded local schedule

M has one held frame/request and one cached response. A frame accepted at the
stage input releases exactly `DEADLINE_CYCLES` local clocks later (512 in the
experiment). There is no wait for link or request ready. A matching successful
response must be cached **before** that release edge; otherwise the output is
the exact original signed 32-bit stereo dry pair, with a fallback counter.
`rsp_ready_o` drains both useful and stale results; it is not an application
ACK. At 76.8 MHz, 512 clocks are 6.667 microseconds of stage latency, excluding
the remaining effect chain, control, DAC and acoustic path. This is a digital
schedule bound, not measured end-to-end performance or a proven LCD budget.

W has one request/result slot. It holds its response under backpressure and
does not accept another request until that slot retires. Its configurable
compute watchdog produces a held error result on timeout and clears real
engine history. M rejects errors and retains its local release schedule.
The current source-stage parameters permit one complete transaction per
sample only if the actual link/CDC/engine path meets the deadline. No
production stream, bus width, pin direction or clock is selected here.

The exposed request is 163 bits and response 164 bits: at least 21 bytes each
when packed, or 24 bytes if word aligned, before external framing/CRC. At
48 kHz that is 1,008,000 or 1,152,000 bytes/s in **each** direction. At the
unmeasured 5 MB/s design target, packed request plus response serialization
alone takes 8.4 microseconds, exceeding the experimental 6.667-microsecond
deadline before W compute/CDC. A direct synchronous test cannot establish that
wire deadline. Use measured faster transport or separately redesign context
encoding/pipelining/topology; never promote this interface from its average
bandwidth estimate alone.

## Context and cancellation

All sideband ports are synchronous to each endpoint's `clk_i`. A future
transport must provide atomic CDC, length/version checks, CRC, credits and a
new nonzero handshake session after either board's boot. The exposed buses
must not be wired asynchronously between physical boards. The single-frame
sequence is internal to this stage, not metadata invented inside the 18-bit
event format or a replacement for the final serializer's sequence.

Requests and responses carry session, nonzero local generation, sequence,
rate, full 32-bit stereo data and enable/reset-gain semantics. W returns
active/clip/error. M rejects results from any other frame/context. W remembers
the highest admitted identity even after watchdog/history invalidation:
duplicates, old generations/sequences and rate mutation within one generation
are rejected before reaching the engine. Modulo serial comparison admits
forward wrap and rejects ambiguous half-range jumps. A forward sequence gap
clears history; a new generation reconfigures the actual engine before use.

M increments generation and revokes cached/inflight results on PANIC, accepted
history/rate configuration or link/session changes. PANIC/config/history
cancel the current stage frame; the existing chain owns its cancellation and
barrier. Link loss during an accepted frame preserves its original local
deadline and emits dry. Reconnection never makes an old cached result valid.

Local configuration/history ACK means M's dry-path context is committed and
its old work revoked. It does **not** claim W has applied configuration. W
clears/configures the real reverb before consuming the next matching frame.
Normal configuration/history preserves wet slew state as the original
reverb does; PANIC/link restart resets wet gain. When no further request
arrives, W may retain inaccessible old history; a new context must clear it
before computing. Final integration still needs an explicit control/status
channel for remote readiness and cancellation telemetry.

## Validation and integration exit

`sim/audio/run_remote_reverb.py --output <new-dir>` compares real W output to
an independent maintained local reverb, including actual wet histories, both
rates and fault/replay/cancellation cases. The macro-on full-chain runner
`sim/audio/run_remote_reverb_chain.py` retains the independent PCM model and
checks all effect orders/masks. Default effects/provenance regressions retain
their original exact-cycle checks.

`tools/workstation_reverb_partition.py prepare --output <new-dir>` stages
explicit source hashes, locked support and matched dynamic-port LOCAL/M/W
subsystems. Only explicit `--synthesize` runs synthesis. The actual emitted
VG must contain one real reverb in LOCAL/W and zero in M. Primitive counts
are synthesis instances, not routed physical BSRAM or whole-board savings.
There is no P&R or programming path in this experiment tool.

Before final profile selection: measure the correctly wired LCD link under
simultaneous traffic; budget framing/CRC/context/credits and worst RTT; connect
the seam through the native runtime wrappers using real reset/epoch fences;
expose fallback/unavailable separately from successful effect application;
retain 32 voices and the local sample schedule; then prepare both complete
roles and pass full physical timing, PLL, CDC and feature gates. If the link
misses this deadline, keep the experiment disabled and evaluate a separately
specified bounded pipeline or asynchronous analysis/storage migrations. The
subsystem experiment is retired or retained only as regression evidence after
whole-workstation comparisons replace it.
