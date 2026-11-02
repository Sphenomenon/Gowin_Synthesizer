# Task3 logical audio endpoints

`workstation_task3_audio_exchange` is the complete same-clock logical audio
composition for the paired framework. It connects the following real subsystem
boundaries through typed endpoint transactions:

1. M physical final-tap exporter → explicit W arm result ACK → maintained W
   `workstation_task3_record_ingress` → existing HCI single recording owner.
2. W existing PCM1 and clock command callers → command mux → one remote proxy →
   M guarded ingress → **separate** existing PCM1 and clock authority commands,
   with matched responses back to the original W caller.

This composition and its endpoints are unselected source components.
They do not change the task2/W21 fallback, production providers, source locks,
LCD pin direction, clocks or deployment. All their ports belong to one local
clock. The shared logical hub must validate/cross complete transactions before
driving them; no packet layout or electrical LCD protocol is defined here.

## M final output to W recording

`workstation_task3_final_tap_export` observes **physical serializer completion**,
after M's final output choice, master gain and mute. Bind its source to the
existing completed-frame fanout, never to a pre-serial diagnostic or W local
DAC. It has no source ready output and cannot stop M's sample schedule.

The arm identifies nonzero boot/session/generation, physical epoch and the next
completed physical sequence. Only stereo16/48k format1 is supported, matching
the existing recording protocol. A higher generation is required for rearm.
The receiver must return explicit arm acceptance before frame delivery.
`arm_tx_ready_i` accepts only the descriptor; `arm_result_accepted_i` confirms
the real receiver accepted it. An explicit rejection fails the source. The hub
must return that result using the same common identity and retain the barrier
between arm and frame lanes. A local arm queue credit cannot confirm W accepted.

The default 256-frame queue bounds transport delay; it is not a measured LCD
budget. Backpressure leaves the same head transaction stable. An epoch/sequence
gap, 44.1k frame, frame error, overflow, link loss, cancellation or PANIC discards
the queued tail and sends a terminal cancel. The observer does not substitute
zeros or silently skip recorded samples. The existing W
`workstation_task3_record_ingress` then feeds the **one** HCI/GATT recording
engine and owner8 raw store. It checks identity, order and a source lease again.
Its `object_idle_i` must come from the actual retired/cleared object, not a
constant in a board composition. CPU and BLE retain the same object authority.

Logical payloads, in addition to the common boot/session/generation, are:

| Transaction | Payload |
| --- | --- |
| Arm | physical epoch32, first physical sequence32, implicit format1 |
| Frame | 44k1 flag1, error flag1, physical epoch32, physical sequence32, PCM32 |
| Cancel | matching common identity; failure code is local diagnostics |

PCM32 follows M physical-frame order `{left16,right16}`. The existing HCI
wrapper performs its own documented channel conversion; do not swap it twice.

## W decoded phone PCM to M D source

`workstation_task3_phone_command_ingress` carries the existing **PCM1 register
and RAM-window contract** to M's existing `workstation_ae350_pcm_owner`, and the
existing clock contract to M's `workstation_audio_clock_service`. It does
not implement another PCM queue, SRC, effects, parameters or audio owner. The
real owner retains its four slots, prefill, interpolation/drift control,
history-clear barrier, cancel epoch, TF conflict and physical-rate checks.
M then applies its existing D hold/release effects and final gain/output path.
W's post-master local DAC PCM must never be forwarded as the decoded source.

`pcm_media.c` already uses a generic `a138_hci_bus` read/write adapter for PCM1,
and an `a138_clock_bus` for physical-rate tickets. The new W
`workstation_task3_phone_command_proxy` accepts the **existing command CDCs**
behind these same MMIO apertures. The explicit paired board profile must select
these remote targets for both apertures, preserving unchanged firmware address,
register encoding and uncertain-result behavior. It must disable their old W
local target bindings; PCM1 must not go to M while rate tickets still go to W.
The existing W local composition remains the fallback. No profile selects this
new paired composition yet, and no physical HCI/SBC→LCD route is claimed.

The logical request is `{sequence32,target1,write1,address12,data32,strobes4}`
(82 bits), where target0 is PCM1 and target1 is M's existing clock authority.
A response
contains `{sequence32,error1,data32}` and repeats the request's common identity.
Request sequence starts at zero on a fresh arm. Only one command/response can be
outstanding. The W command mux holds a whole caller through remote completion
and valid release, and gives only that caller ready; both can remain pending
without exchanging identities. The receiver holds the command address for one
predecode edge before asserting valid, matching the real clock service's
original APB boundary. It waits for the selected authority's ready or reports a
bounded timeout. An owner response error remains an error response
and is not converted to success. A request with stale identity or wrong sequence
never reaches the owner and fails the arm. Generation exhaustion requires a
coherent endpoint reset; reconnect alone cannot reopen a retired arm.

`owner_live_o` must gate the original owner's `session_live_i`, in addition to
its normal current controller/generation binding. Link loss, matching cancel
and PANIC revoke it immediately, including while a command or response waits.
It must not be used as a condition for the M base sample tick. A command already
accepted by the owner cannot be undone by a later disconnect; responses remain
identified so the requesting side can reject an obsolete epoch. The W proxy
matches the complete returned identity and sequence before completing the CPU
transaction. A wrong response or missing return produces an error, fences the
proxy and sends matching cancellation to M; it never retries an uncertain
command automatically. Caller observer reset must cancel/fence this transport,
not clear the retained generation while an old response can remain in flight.

An arm requires the actual owner idle/retired condition and no pending response.
The board adapter must supply the owner's full idle condition, including armed,
selected, pending history and serial state. `!selected` alone is insufficient.
The small fixture uses `!selected` only while it never attempts to rearm an
active PCM1 stream; it is not a board-level idle binding.

## Small composition check

`sim/audio/run_workstation_task3_audio_endpoints.py --output <new directory>`
runs the separate endpoint fixture (281 checks), then instantiates the complete
`audio_exchange` composition with the actual PCM1 owner and M clock service
(283 checks). Each fixture transfers 16 ordered physical-frame samples and
commits 256 real PCM1 window/descriptor frames. The composition checks clock
target/predecode, concurrent callers and response correlation, stale response
boot and lost return cancellation; the endpoints check stale request boot,
disconnect, overflow, owner timeout and pending-command PANIC.

The fixtures do not run a real serializer, radio, SBC decoder, D DSP, long DDR
recording or BLE download. They do not apply a real 44.1k clock switch/barrier.
Resource/timing, actual board-profile composition, packet CRC,
LCD/CDC/electrical behavior and real latency remain separate gates.
