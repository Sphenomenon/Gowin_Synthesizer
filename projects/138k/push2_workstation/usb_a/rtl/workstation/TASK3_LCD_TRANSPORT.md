# Task3 LCD experimental transport

This is a new LCD-only experimental wire contract between the two 138K boards.
It does not replace USB PL or BLE protocols. The paired business endpoints own
their channel payloads. Physical measurements have not been made; simulation
RTT values are local clock cycles and must not be presented as board latency.

## Pins and clocks

The reviewed [40-pin plan](../../boards/custom_138k/task3_lcd_probe_pinplan.json)
and isolated [CST fragment](../../boards/custom_138k/task3_lcd_probe.cst) use the
user-confirmed same-number network mapping, M.FPC4.n to W.FPC4.n. Cable contact
orientation does not introduce an n-to-41-n transformation. M drives R[4:0],
B0 and B1; W drives G[5:0] and B2. The other eleven programmable lines always
remain high impedance. The two hard +5V connections cannot be isolated by RTL.
The raw schematic PDF is absent from this worktree; the pin-plan source basis
identifies the reviewed schematic transcription and existing LCD example.

`workstation_task3_lcd_pins` requires compile-time `EXPERIMENT_ENABLE=1` and
runtime `drive_enable_i=1` before any pad drives. Its default is all-Z. Roles
must be complementary; two M or two W recipes can contend. VCCIO, supply
topology, physical continuity and both candidate identities remain physical
gates before enabling this experiment.

Each direction has a fixed four-bit data lane, request and peer acknowledge.
Every nibble uses request-high, acknowledge-high, request-low,
acknowledge-low. Bytes send the low nibble first. There is no direction turn
or shared signal driver. All state uses an existing local clock; LCD pins
never become FPGA clocks. Request, acknowledge and PANIC use two-stage
synchronizers. Data has three stages and two additional receive guard cycles.
Data remains stable until acknowledge. This bundled-data implementation
still requires routed CDC and electrical validation.

## Frames and queues

Frames contain 52 bytes, including zero padding. Integers and CRC are little
endian. CRC16-CCITT uses initial FFFF, polynomial 1021 and covers bytes 0–49.
The transmit CRC processes one byte per local cycle to avoid a large
combinational CRC path.

| Bytes | Field |
|---|---|
| 0–1 | D3, protocol version 1 |
| 2 | kind: 0 heartbeat, 1 probe request, 2 probe echo, 3 control, 4 business |
| 3–5 | channel, payload length 0–32, reserved zero |
| 6–9 | sender boot identity, nonzero |
| 10–13 | shared session, nonzero |
| 14–17 | sequence, starts at zero after rearm |
| 18–49 | up to 32 payload bytes, remaining bytes zero |
| 50–51 | CRC16 |

Heartbeat and probe use channel 0; control uses channel 0. Business uses
channels 1–15, including channel 8 actual endpoint model/status messages.
There are no synthetic model-status messages in the transport. The expected
peer boot/session and exact next sequence are checked before publication.
Sequence wrap is rejected. Probe request/echo carry a 32-bit local timestamp
and token; automatic probes report last/max RTT in that sender's cycles.

The typed application interface is valid/ready, four-bit channel, six-bit
length and 256-bit payload. One transmit frame, one held receive transaction
and one pending probe echo are bounded storage. There is no packet-level
remote credit protocol. A second unread receive transaction or second
pending echo fails explicitly and increments overflow. Heartbeat, probe
and echo bypass held application output; echo has highest transmit priority.
Maintenance priority and wire occupancy can backpressure commands. Local
lengths above 32 are not accepted. `congestion_cycles_o` counts presented but
unaccepted transactions; these waits cannot gate M's audio sample clock.

## Qualification, cancellation and reconnect

`link_ready_o` means a valid peer frame was received; it is not a measured
bandwidth qualification. `business_ready_o` additionally requires both
`ALLOW_BUSINESS=1` and external `budget_validated_i=1`. Default compilation
allows only maintenance/control. Neither heartbeat nor probe can set the
external budget flag. The experimental paired build may compile business
logic for resource analysis while keeping the runtime budget reset to zero.

Budget withdrawal immediately masks held business output and new business
input; held or in-flight business then faults, clears and requires rearm.
Restoring the flag does not replay canceled output. A remote business frame
received without qualification is rejected. Dropping enable clears volatile
queues/qualification/fault/sequence and releases pads through the companion
pin module, while cumulative diagnostic counters remain. Rearm both sides
with agreed nonzero boot identities and a new session. One-sided rearm in
the same session is not an implicit reconnect and can fail sequence checks.

PANIC has dedicated fixed-direction pins and bypasses normal packet queues.
It revokes local handshakes immediately and clears peer-held output after
the synchronizer. PHY stalls, heartbeat/probe timeout, CRC errors, identity
changes, malformed headers, overflow and sequence errors latch a fault.
Disable/rearm is required; there is no automatic replay or retransmission.
The default PHY stall limit is 50,000 local cycles and the heartbeat/probe
timeout is 5,000,000. Both peers must be enabled within the startup watchdog
window; a later peer requires a new coordinated rearm. Stopping the peer
clock produces a bounded handshake or heartbeat failure.

| Failure code | Cause |
|---|---|
| 1 | invalid or changed boot/session configuration |
| 2 | local or synchronized peer PANIC |
| 3 | PHY stall |
| 4 | peer heartbeat/probe timeout |
| 5 | sequence mismatch or wrap |
| 6 | CRC mismatch |
| 7 | malformed header, wrong peer/session or unexpected probe echo |
| 8 | bounded receiver/echo overflow |
| 9 | business received or retained without its external budget |

Before carrying production PCM, both directions still need measured payload
throughput, round-trip latency, jitter and congestion behavior with the final
queues and competing traffic. The probe's fixed-frame overhead is 52/32 at
full payload and 52/N at N-byte payload; handshake and maintenance costs
must also be counted. No throughput is inferred from local clock frequency.
Real-time remote reverb and Bluetooth audio remain unqualified.

## Reproducible offline check

Run `python3 sim/workstation/run_task3_lcd_transport.py --output <new-directory>`
from this `usb_a` directory. It runs business-forbidden and business-enabled
dual-clock models, frame corruption, replay, congestion, budget withdrawal,
PANIC and peer-clock-stop cases. Icarus provides four-state all-Z and
complementary ownership checks. The receipt preserves exact source hashes,
commands, log hashes and input stability. It does not synthesize, route,
program or operate a board.
