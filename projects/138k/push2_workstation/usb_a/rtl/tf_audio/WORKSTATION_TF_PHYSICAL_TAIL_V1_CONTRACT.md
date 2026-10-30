# TF physical tail receipt v1

This reusable unselected endpoint adds no audio renderer, clock generator,
serializer, source selector, file owner or DDR client. The unique workstation
audio owner supplies real router and physical completion endpoints. Its fixture
composes those unchanged real modules with native SPI/FAT/WAV and explicit
silence rendering; that fixture is not a second production audio top.

All arm, admission, router and observation ports belong to `compute_clk_i`.
`physical_*` and `observation_source_drops_i` belong to the real serializer clock.
Only coordinated whole reset resets either mailbox endpoint. Stream cancel or
serializer local reset must not erase an outstanding receipt. Both producing
clocks must run for their actual handshakes; a stopped clock never creates a
successful completion or quiet acknowledgement.

## Arm, ordered LAST and successful completion

The caller first submits one stable arm request containing current transport
generation, frozen command/session generation, committed rate and final-router
epoch. It must hold that tuple under valid/backpressure and withdraw valid
after acceptance. The request crosses in an immutable bundled mailbox. The
serial endpoint captures the real observation queue's source-drop baseline and
returns the same session identity. Only its matching successful ACK asserts
`armed_o`/`tf_admit_o`; the caller must not consume TF before this ACK. Serial
cadence continues with explicit non-consuming silence while arming.

On the unique final router's actual `tf_valid && tf_ready`, `tf_fire_i` records
the same packet's rate, transport/session identity and LAST. LAST binds to
that exact accepted router request's epoch/sequence. This closes further TF
admission while serial requests continue with explicit silence. Local decoder
EOS, source-tail drain and pre-serial router completion are diagnostics only.

The serial endpoint matches the bound token against the real completed frame.
On the following real serial edge it captures the registered observation-source
drop counter, which now includes the matched frame's actual FIFO accept/drop
action. This is a source receipt pipeline with an explicit data dependency, not
a timed guess that another boundary drained. Its immutable reply carries both
the serial-captured baseline and tail prefix from the same armed session.

Compute emits one `physical_eos_o` only after BOTH that successful receipt and
the actual completed-frame observation match rate/epoch/sequence. Any frame
error, relevant router error, transport fault, observation gap/drop notification
or fence revokes eligibility. Baseline/prefix mismatch, a decreasing counter,
or either prefix at `FFFFFFFF` also fails closed. The counter producer must be
the existing monotonic saturating observation counter; modulo/wrapping counters
are not compatible. Saturation cannot be interpreted as unchanged loss.

## Cancellation, failure and retirement

`fence_i` is a compute-domain event for lifecycle/generation cancellation. It
immediately withdraws admission and pending success, advances a registered Gray
cancellation identity and leaves mailbox bundles immutable until retirement.
The serial endpoint retires an old token as cancelled when that identity
changes. A late previous-session reply may free the mailbox but cannot arm or
complete the new session. A new arm waits for the old slot to retire. Held or
repeated fence events are explicit events, not an independent parameter owner.

`tail_cancelled_o` reports revoked local tail/session eligibility, not native
SPI cancellation. Native payload/CRC drain and the TF shallow bridge's real
source/compute quiet proofs remain separate. The caller combines those with
the unique PCM bridge/router/serializer quiet acknowledgement; no fixed delay
or local drain substitutes for them. Stop/EOF are distinct terminals.

Failure is sticky until a new explicit arm operation. Caller lifecycle policy
must cancel/drain and issue a new file command before rearming; this endpoint
never retries a source. It permits no second LAST or data admission after tail
closure. Unexpected traffic and mismatched identity are errors. Pause uses
non-consuming silence at the unique compute admission and retains the shallow
head; it is not a fence, mute-only TF consumption, or source-clock stop.

Physical Gray bit-flight/skew and mailbox timing constraints, metastability,
routed clocks/CDC/resources and hardware remain independent gates. Source
simulation validates protocol and real serial bits, not physical CDC closure.
