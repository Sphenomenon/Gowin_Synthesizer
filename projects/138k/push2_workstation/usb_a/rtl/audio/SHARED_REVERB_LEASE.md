# W existing-engine lease experiment

The target is the existing W reverb subtree (20 BSRAM equivalents and 19
MULT27X36 in the retained hierarchy). The lease adds control and muxes, not
another reverb. M's possible savings remain those declared in
`REMOTE_EFFECT_STREAM.md`; no new full-system resource or timing claim is made.

The local full effects chain must stop admitting samples/configuration and
complete its current work. A real history transaction then traverses all
three stages and the delay DDR's ordered fence before remote ownership is
granted. Local input readiness stays closed during the lease. No local or
remote configuration/history completion is synthesized from a mute bit.

The physical engine's rate remains observable. During remote ownership the
private local chain cannot compare a different owner's physical rate with
its own delay/chorus rate. That check is suspended only while the reverb is
away and resumes after a real clear/configure acknowledgement restores the
saved local rate. The saved rate is restoration state, not an application
parameter authority; M remains the remote stream's authority.

A local preemption, PANIC, remote context change or claim withdrawal revokes
the remote result/command path immediately, clears the engine and restores
the local rate before reopening the local path. Failed drain/fence requests
are denied within 4096 clocks; a failed 512-clock restoration latches fault
and keeps admission closed until reset. A drain denial never forges a DDR
completion or resets a still-owned local transaction. Retry requires claim
withdrawal; the stream worker additionally requires a fresh context after
losing a granted lease. The protocol owner must propagate denial/fault and
obtain a lease before advertising effect readiness.

The experiment uses a checked, reversible projection of the maintained
stereo-effects source to expose its existing reverb ports. Other DSP and
DDR owners retain their original implementations. The projection is not a
production source policy and no profile selects it. Its exit is an explicit
native source/profile integration after ownership, negotiated transport,
measured communication budget and full physical gates pass. Historical
profiles, source locks and baselines are preserved. No additional Gowin
synthesis or P&R belongs to this experiment.

From the repository root, run:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -B projects/138k/push2_workstation/usb_a/sim/audio/run_shared_reverb_lease.py --output <new-cache-directory>
```

The runner uses
the real delay DMA, the checked maintained DDR model, all three local
effects, and an elaborated hierarchy check for exactly one reverb instance.
Eight runs cover W 25/50 MHz, local 48/44.1 kHz with the opposite remote rate,
and lost restoration readiness/acknowledgement. Each checks a local frame
already in flight at claim, an ordered DDR fence held for 10 microseconds,
2300 continuous remote frames, local preemption during a remote frame,
an 8300-cycle fence hold with only one denial, recovery, PANIC and sticky
restoration failure. The local mask is zero while all maintenance stages
still execute; dry PCM is checked against an independent gain/rounding model.
Remote PCM/clip and both full 32-bit inputs are checked at the actual engine
boundary. This tests routing and ownership, not a new arithmetic reference.

Eight source-copy mutations must compile and then fail behavior assertions:
open reset admission, premature grant, skipped DDR fence, open local admission, wrong restored
rate, cross-owner completion, missing restoration timeout, and PANIC
clearing a sticky restoration fault. The only forced signals are disclosed
test injections at the engine configuration ready/applied boundary. The
simulation DDR watchdog is 65536 memory cycles so the independent 7-ns
half-period memory clock can outlast the directed two-drain-window hold;
production defaults and constraints are unchanged. No transport model,
CDC closure, P&R resource measurement or board acceptance is implied.
