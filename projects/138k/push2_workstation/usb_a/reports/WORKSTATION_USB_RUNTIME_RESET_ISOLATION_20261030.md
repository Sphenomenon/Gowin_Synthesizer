# Native USB input reset isolation — 2026-10-30

The native top connects `u_native_usb.audio_reset_n` to `runtime_reset_n`, which is `reset_n && memory_guard_started`. Compute PLL qualification loss must not reset USB input lifecycle state while the independently owned runtime retains its session and committed parameters. The earlier connection to `audio_reset_n` could invent another attach on PLL recovery and emit attach initialization again.

The new regression uses the maintained `workstation_usb2_service_adapter`, `push2_usb_a_control`, Push mapper and real generated asynchronous event FIFO, followed by the real `workstation_session` that emits the 13 attach initialization events. Only final held-note and volume application are modeled. Normal-event backpressure is modeled while lifecycle cancellation retains priority. A second instance uses the old PLL-qualified audio reset as a negative control with the same actual RTL and stimulus. No production RTL, profile or locked input changes are made by this phase.

The runner preprocesses the actual native/custom top and requires the selected `u_native_usb` to use `audio_reset_n(runtime_reset_n)`, `reset_n(usb_reset_n)`, `clk_audio(audio_clk)` and `FEEDBACK_AUDIO_DOMAIN(1)`. It also verifies the real USB wrapper forwards the audio reset to the input owner and selects it for compute-domain feedback. Source hashing covers those bindings, the fixture, runner, actual queue/adapter/session dependencies and explicit prepared support metadata, with drift rejection after execution.

Validation command:

```sh
python3 projects/138k/push2_workstation/usb_a/sim/usb2/run_workstation_usb_runtime_reset.py \
  --project /Users/sphenicidition/.cache/gw138k-task-20261030/clean-rev2-profile-candidate/workstation/Prj1 \
  --output /tmp/workstation-usb-runtime-reset-20261030-v3
```

| Check | Result |
|---|---|
| Actual top/wrapper binding | PASS, native branch selects the runtime reset and compute-domain feedback; USB reset retains its separate USB qualification |
| Initial GW25K attach | PASS, actual MMIO store produces one attach and all 13 session initialization events before its barrier |
| Short qualification pulse | PASS, a modeled 3ns PLL qualification loss causes no current-path attach/defaults or modeled parameter/note loss |
| Compute stop/recovery | PASS, compute pauses while the USB side continues, MMIO still reports attachment, recovery creates no current-path attach/defaults |
| Real queued events | PASS, two already queued note events survive current-path compute pause and arrive in order after recovery; the prior modeled volume/note state remains |
| Old reset negative control | PASS, the two qualification/recovery cases produce exactly two extra attaches and 26 extra real initialization events; reset/queue disruption also replays old events in this control |
| Real MMIO detach/reattach after recovery | PASS, a queued old note is flushed even with normal-event backpressure; one detach, fresh Push attach/defaults and working Push pad mapping |
| PANIC | PASS, real Push PANIC clears modeled held state, keeps the changed modeled volume, emits its synchronization barrier and does not reapply defaults; repeated held button does not fire twice |
| Verilator | Zero fixture warnings; no UNOPTFLAT |

The current instance finishes with two legitimate attaches, three barriers (including PANIC), one detach, one PANIC, 26 initialization events, two retained queued events and five note events. The old connection finishes with four attaches, five barriers and 52 initialization events. Both use 14 actual MMIO stores. Evidence identity: `native-usb-runtime-reset-offline-v1-6fc93c527da53b05`. Source-set SHA-256: `6fc93c527da53b05deb93fe46488627d76dde548893c4d38c84dd37992feba4f`. Full commands, binding proof, input hashes and metrics are in `reports/workstation_task_20261030/usb_runtime_reset_isolation.json` and `/tmp/workstation-usb-runtime-reset-20261030-v3/verification.json`.

Parent independent verification reran the complete command into `/Users/sphenicidition/.cache/gw138k-task-20261030/usb-runtime-reset-parent-final` with the explicit `f03-scan-window-profile-revision3` prepared reference. It passed with identical metrics and actual top binding. All 15 maintained input hashes match; the four prepared support source hashes match after normalizing their project roots. Every recorded parent input also matches current disk bytes. Its identity is `native-usb-runtime-reset-offline-v1-2c9a2ff1cc7002c7`, source-set SHA-256 `2c9a2ff1cc7002c7c0eb8fdf4a6fab2df3946163f9a7dca8b931893c42fbfdcc`. This differs transparently because absolute prepared paths and the separately prepared profile/integration metadata are included in source identity; the metadata bytes themselves differ, while the normalized support RTL bytes are equal. Parent verification SHA-256 is `75f959d47d6476684cf4cfdb3d65e5d4bcad55c46a2922c6c751221c8a98eb08`. The machine-readable report records this comparison without replacing the original child identity.

An additional exploratory case placed both a real MMIO detach and reattach entirely inside a stopped-compute interval. Its lifecycle edges arrived after resume, but the generated FIFO replayed old RAM events after the short reset pulse. That failed model run is retained in `/tmp/usb-runtime-reset-dev-20261030-v1/stopped_detach_replay_tb.sv`, `stopped_detach_replay.log` and `stopped_detach_replay.json`. The passing regression verifies real hotplug after compute recovery; it does not claim to resolve hotplug entirely during a stopped destination clock. This separate queue/reset boundary needs its own source change and verification if supported recovery requires it.

This is adapter/lifecycle verification. It does not exercise a ULPI peer, USB enumeration, production USB firmware, DSP, physical audio continuity, actual PLL behavior, synthesis, P&R, physical CDC/timing/resources or a board. The separate runtime guard fixture covers real runtime behavior under backend failure; this report does not substitute modeled held state for that evidence. No SRAM or Flash deployment occurred.
