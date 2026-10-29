# A07 runtime effects stage 2: independent DDR Delay

2026-10-30. This stage implements and verifies independently named native Delay
consumer/DMA modules. It does not select them in a profile, build or top. The
machine-readable input identities and 13 verification scenarios are in
[`workstation_task_20261030/runtime_delay.json`](workstation_task_20261030/runtime_delay.json).
There is no synthesis, routed timing, CDC signoff, resource, board, SRAM or Flash
acceptance claim for these modules.

## Source identity

The reference is actual F02 rev2 prepared input from commit
`3d4b3175d0f20d0b787b61b43e4543739b26bca1`, source identity
`custom138k-workstation-v1-f5b723250388add5`:

| Native source | Exact prepared source SHA256 | Native SHA256 |
| --- | --- | --- |
| `rtl/audio/delay_ddr/workstation_runtime_delay_effect_ddr.sv` | `e5764ef18a0c8a1918369121b1b27124eb9e5c0b6cfe4922a65cfd14d2d6eff6` | `879a5d93fb3ee547cd517344a495452f7cb37f28c0605ceee2cb625f2126c62d` |
| `rtl/audio/delay_ddr/workstation_runtime_delay_ddr_dma.sv` | `9486da957457b8b632c92c42bc630e4723bc3f04eef09f723b29bc8c82af3e61` | `4486bddae55e89c191cace04fdfad6163b71af9a1c43b5369e8fabc0d7e42551` |

Adjacent provenance JSON records reversible exact edits. The test reverses every
edit and requires the original prepared hash. Reference arithmetic reconstructs
from the versioned `resource_rework_route0` baseline, extracting the exact
prepared `serial_delay_effect` module. The actual prepared FIFO is separately
hash-checked. Tests do not depend on a private staging/results directory. Frozen
baselines, historical sources and public 18-bit event contracts are unchanged.

## Rate and history contract

The consumer accepts `config_valid_i/rate_44100_i` only with `config_ready_o` at
true quiescence, with no competing input frame. The request changes the applied
rate and logically clears history; wet gain and fractional slew state survive.
`history_clear_i/history_ready_o` is a separate valid/ready request preserving the
rate and those gain states. Config has priority over history-only. Requesters
drop valid after acceptance. `config_applied_o` and `history_done_o` pulse only
after the matching memory transaction ACK reaches the audio domain.

The legacy `clear_i` remains an immediate local abort and wet-gain reset. It
coalesces during an existing transaction and also waits for the real roundtrip
before `ready_o` reopens. `quiescent_o` includes the output-valid tail and pending
transaction/marker, rather than only state 0. A caller must maintain the final
sample schedule through controlled mute while this effect closes `ready_o`.

At 48 kHz, Delay arithmetic, 9600-frame echo and 128/frame wet slew preserve the
prepared implementation exactly. At 44.1 kHz the echo is 8820 frames, still
200 ms. Wet slew increments 139 plus a carried 47/147, averaging
`128 * 160/147`. Feedback remains one half with the existing signed rounding and
saturation. The ring is still the same 128 KiB at byte `0x30000000`, native-word
`0x0c000000`, with four stereo pairs per 256-bit chunk and word-address stride 8.
No DDR allocation is added.

## Ordered barrier and faults

PCM and private markers use the existing 65-bit FIFO transport. Marker bit 64 is
one, bits 63:33 must be zero, bits 32:1 are a local 32-bit transaction ID, and bit
0 is the requested rate. This metadata does not alter the public event layout.

The DMA drains/discards any old outstanding read, preempts remaining old read
burst data when the marker reaches the FIFO head, then submits a read of the
last accepted write address. That read travels after older posted writes through
the same ordered owner6 command path. Only its returned response permits the
matching ACK to enter the return FIFO. The audio consumer discards stale PCM
until that matching marker, then applies rate/transaction state and reports
completion. Old PCM ahead of the marker also must drain first. Thus an old read
or command held indefinitely causes a bounded transaction failure, never an
early completion.

This relies on the existing native queue's accepted command ordering. The
fence response establishes completion through that command contract; there is
no invented electrical DDR write-completion port. The simulated DDR deliberately
queues accepted writes before executing them, so write-ready alone cannot
satisfy the tested barrier.

Missing/late fence responses, bad marker payloads and stopped-peer clocks are
sticky fatal faults until coordinated reset, with no ACK. Both domains expose a
divide-by-32 heartbeat and synchronize their peer through two flops. The surviving
domain detects either single-clock stop. If both clocks stop, an external
always-on monitor is required. Default transaction/peer timeouts are 1048576
local clocks; tests shorten them to 2048/512. Stream underflow substitutes wet
zero and overflow drops the new feedback sample, sets observable sticky flags,
and retains render progress. Legacy clear resets those stream flags. Underflow
shifts the stored sequence until a clear; callers still need a system policy.

## Offline validation

Run:

```sh
python3 projects/138k/push2_workstation/usb_a/sim/test_workstation_runtime_delay.py
```

All 13 tests passed with Verilator 5.052, independent 14 ns/20 ns clock periods.
Exact compile-warning counts are checked: two inherited missing-timescale
warnings and sixteen inherited signed-widening arithmetic warnings across the
native/reference pair. There are no transaction logic or testbench width warnings.

- 30000 accepted 48 kHz frames compare ready, valid, active, PCM and clip each
  cycle against the exact prepared BRAM reference, including 726 clipping frames,
  a ring wrap and a clear barrier.
- 19000 accepted 44.1 kHz frames compare against an independent abs-round,
  saturate and feedback model. The first impulse echo is exactly frame 8820.
- Delayed old read, three posted writes, old PCM FIFO backlog, old read burst,
  ACK FIFO backpressure, matching IDs, 48→44.1→48 and history-only requests all
  verify the barrier and preserved gain/remainder.
- Missing/late fence, wrong/stale transaction, reserved bits, each stopped clock,
  five pipeline clear offsets, held-clear coalescing and config/history priority
  verify failure/cancellation behavior. A sustained DDR stall still emits 1100
  further frames with observable underflow/overflow and dry output after depletion.

Chorus, runtime reverb and full chain order/mask/maintenance validation remain
separate stages. No whole-workstation dual-rate claim follows from this component
test. Rollback is omission of these independently named, currently unselected
modules; accepted source selection has not changed.
