# Stream epoch owner and optional nonzero policy

The always-on `workstation_sample_rate_switch` is the only authoritative owner
of the 32-bit audio stream epoch. It stages a new rate/epoch before DSP history
configuration and serial prefill, and publishes it only after actual output
RUN acknowledgement. Same-rate requests do not replace a stream. A failed
transaction leaves the last committed epoch unchanged; recovery commits a new
stream only on successful output acknowledgement. The initial active stream
uses the configured seed; boot does not report a user command's applied event.

The default `RESERVE_ZERO_EPOCH=0`, `INITIAL_STREAM_EPOCH=0` retains the previous
full-u32 range and natural wrap. The explicit `RESERVE_ZERO_EPOCH=1` option
starts at 1 by default, advances through `0xffffffff`, then continues at 1.
A reserved-zero seed of 0 is a configuration error. The seed parameter allows
near-wrap verification without simulating billions of switches. It is not a
runtime command or a writable parallel parameter owner.

`workstation_audio_clock_domain`, `workstation_runtime_audio` and
`workstation_runtime_controlled` forward the same options to that single
owner. DSP configuration, physical I2S frames, observation CDC and displays
receive its actual value unchanged. No observer adds one or borrows a frame
sequence to manufacture identity. The optional clock-command service must use
the same `RESERVE_ZERO_EPOCH` value when correlating an expected result. Its
feature register bit 3 exposes that configuration; it still reads actual state
from the runtime.

The opt-in nonzero policy satisfies DISPLAY_DATA_LAYOUT_V1.md v1.1's nonzero
epoch contract. This source addition selects no top/profile. A future complete
candidate must choose the policy explicitly, regenerate its complete source
identity and validate both clock modes and physical CDC. Prior synthesized
netlists do not contain this source/configuration merely because the default
behavior is preserved.

Epoch is finite and scoped to a common-reset incarnation. Every FIFO, held
context and local observer must be cleared by common reset; it must not restore
old frames into the new incarnation. Within one incarnation, no consumer may
retain a frame across a complete epoch-space reuse (2^32 streams for default,
2^32-1 for reserved-zero). Recording objects and external transfers need their
separate boot/object identities; the epoch does not replace them. The 18-bit
event layout and its separate PANIC/session semantics are unchanged.

Verification exercises default, nonzero seed 1 and near-wrap `0xfffffffe`
against the real switch plus official GW5A DCS through the same bidirectional,
no-op, rejection, fault and recovery workload. The real APB CDC/command service
checks the same three policies at three asynchronous phases, including result
correlation through wrap. A complete native DSP/final-PCM/I2S run with the
nonzero owner verifies that observers receive the actual epoch. These are
offline checks; no routed or board acceptance follows from them.
