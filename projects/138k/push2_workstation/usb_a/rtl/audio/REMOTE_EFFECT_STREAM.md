# Task3 optional asynchronous effect boundary

This source experiment is not selected by a workstation profile. It must not
replace the independent M or paired fallbacks before the integration gates
below pass. M owns committed parameters and the final audio sample schedule.

## Expected benefit and ownership

The retained M reverb hierarchy costs 20 BSRAM equivalents and 19 MULT27X36
instances (see `DUAL138K_TASK3_LCD_REVERB_BUDGET_20261106.json`). Replacing
that engine with bounded send/result storage could remove that arithmetic
from M. Queue, CDC and transport costs offset the benefit; no full-system
savings or timing improvement is established. M F7's worst setup is a glide
path, so moving reverb alone does not close M timing.
The default M data arrays hold 12048 bits (dry/wet, tags/flags and request
queue); W's work/result/current arrays hold 3217 bits, excluding scalar state,
CDC and transport. These are declared bit counts, not mapped resources.

W already contains a real `workstation_runtime_spatial_reverb`. The worker
wrapper instantiates no engine. Production integration must lease that exact
engine exclusively, fencing its current local effects owner, parameters,
DDR/readiness dependencies and completion route. Muting W's serial output
does not release the engine. Lease acquisition/arbitration is a remaining
composition change, not provided by these wrappers.

## Local transaction contract

All ports use their local clock. The 192-bit key is
`{Mboot32,Wboot32,linkSession32,mediaGeneration32,parameterRevision32,audioEpoch32}`.
Boot/session/generation/epoch must be nonzero; parameter revision may be zero.
Rate is part of the context. Keys must remain unique across cancellations and
reconnections; reset requires a fresh external boot identity. Values are committed by M; this wrapper cannot
apply parameters independently. The 18-bit interaction event is unchanged.

Requests carry key, rate, sequence, enable and signed stereo32 PCM. Results
carry key, rate, sequence, error, clip and signed stereo32 processed PCM
(the existing engine's dry-plus-wet result). There is no PCM16 truncation.

M always accepts local samples. Its optional stage adds exactly 64 sample
periods (1.333333 ms at 48 kHz; 1.451247 ms at 44.1 kHz), followed by one
local register edge. Before priming it emits silence. Each subsequent input
completes on that edge using the matching result or the corresponding delayed
dry sample. Transport backpressure never changes this schedule. Current
enable and the original sample's enable must both hold to use a result;
release immediately selects dry, including buffered/in-flight results.

The 16-frame request queue drops new work when full and discards expired
heads without waiting for transport. Stale, duplicate, unissued, wrong-key,
wrong-rate and failed responses drain and increment a saturating counter.
A valid response arriving at the exact output deadline can be used. Sequence
wrap is forbidden: after `0xffffffff` no further requests use that key;
local dry scheduling continues.

W has 16 request and 16 result slots. Requests must increase strictly within
a key; gaps are allowed but clear/configure effect history before work.
First work and enable transitions also clear/configure history. W reserves
a result slot before starting the engine. Configuration or processing that
fails to finish within 512 W clocks clears the engine and returns an error
with the original dry PCM. A full result queue suspends background work.

Link/lease loss flushes remote work. Clear/PANIC, rate changes, link or lease revocation
requires a fresh key before remote work resumes; clear cannot reuse sequence
0 under the old key. Rate-only changes revoke work until a new key is supplied,
so switching rates away and back cannot alias an old result. M retains its delayed dry timeline on link loss. A key
or rate change cancels and re-primes that timeline; clear suppresses output
valid, while subsequent sample completions remain bounded. Production PANIC
must also retain the existing final-output cancellation policy. Reset is a
new-boot boundary and must have fresh externally supplied boot identifiers.

## Communication admission

The maintained LCD transport has 52-byte frames and 32-byte payloads. All
15 typed channels in `task3_paired_channels.vh` are allocated. These internal
ports add no wire format, channel assignment, capability or business admission.
Any integration needs an explicit negotiated extension to the maintained
protocol, full context binding, cancellation and credit accounting.

As a PCM-only lower bound, an 8-byte token/index header leaves space for
3 full stereo32 samples per frame. This omits per-sample enable/error/clip
metadata and is not a complete packet design. Under that assumption,
each direction requires at least `52 * sample_rate / 3` bytes/s:

| Rate | Additional M to W | Additional W to M |
| --- | ---: | ---: |
| 48000 | 832000 B/s | 832000 B/s |
| 44100 | 764400 B/s | 764400 B/s |

At 48 kHz the previous simultaneous minima are 1378000 B/s M to W and
546000 B/s W to M. Adding this stream gives 2210000 and 1378000 B/s,
before credits, status, ARM, retries and congestion headroom. The earlier
416000 B/s estimate assumed stereo16 and cannot justify this stereo32 path.
For a conservative envelope that reserves two more bytes for count/flags,
only two stereo32 samples fit: 1248000 B/s in each direction at 48 kHz,
1146600 at 44.1 kHz. The 48 kHz simultaneous totals then become 2626000
M to W and 1794000 W to M, still excluding control/credit overhead.
These alternatives are budget assumptions, not assigned packet formats.
Without concurrent analysis the M to W minimum falls by 416000 B/s at
48 kHz; downloads must be throttled from the remaining measured headroom.
No mode may admit remote effects by assuming those background streams are
free or by dropping the live phone/recording stream silently.
The 58–62 us logical LCD RTT estimate already exceeds the old single-frame
512-at-76.8-MHz deadline. The new window tolerates bounded delay but is not a
physical bandwidth measurement. Background analysis/download traffic needs
an explicit scheduling budget; this interface supplies no such guarantee.

Physical business admission stays closed until same-number LCD pin mapping,
electrical direction/level/clock, effective throughput, RTT/jitter and
congestion are measured. W cannot access M's TF/USB/DDR/HDMI/DAC directly.
Bluetooth's role also remains subject to measured capacity and latency.

## Integration gates

Real-engine asynchronous FIFO simulation must cover both rates, independent
clocks, congestion, fault/context fences and fixed M output scheduling. That
is source evidence only. Reusing W's existing engine still requires exclusive
ownership and composition tests, the maintained protocol extension and a
measured concurrent budget. New full candidates subsequently need complete
CDC/PLL/resources/routed timing and correct-target sound/latency acceptance.
No extra synthesis or P&R is part of this source experiment; A/B/C retain
their original results and budget usage.
