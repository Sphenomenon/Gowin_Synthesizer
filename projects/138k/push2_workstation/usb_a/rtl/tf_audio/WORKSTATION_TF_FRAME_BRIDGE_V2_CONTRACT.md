# TF frame bridge v2 — atomic LAST and command identity

This unselected version derives from `workstation_tf_frame_bridge.sv` without
changing its bytes, users, profiles, FIFO/cancellation algorithm or clocks. The
versioned RTL is consumed directly; its checked derivation and patch are audit
artifacts. The original bridge's transport, Gray-generation, real quiet proof,
whole-reset and physical CDC/skew requirements remain applicable.

V2 adds `source_last_i` and `source_session_generation_i` to each accepted
source PCM transaction, with matching `tf_last_o` and
`tf_session_generation_o` in the compute-domain held packet. Storage is 118 bits:
transport generation32, caller session generation32, sample rate20, error1,
LAST1, left16 and right16. FIFO depth remains `2**FIFO_ADDRESS_BITS` plus the
existing held compute head. No file/DDR API, rate authority or clock generator
is added. Unsupported rates remain explicit zero/error packets; LAST cannot
convert a bad packet into successful playback.

Transport generation belongs to the existing registered Gray cancellation
barrier. Caller session generation is frozen metadata from the accepted file
command; it is distinct from transport identity and never becomes another
authoritative copy of a common parameter. Both identities, rate, error, LAST
and PCM are atomic across the same FIFO and held head. Ordinary backpressure
retains all bits. Invalidate/quiesce may withdraw the whole packet; new source
packets remain blocked until the matching generation barrier returns.

Pause does not use quiesce/invalidate: the caller gates source admission and the
unique compute TF admission while the serial schedule continues using explicit
silence. The next queued compute head is retained exactly. Stop/failure/apply
use the generation barrier and the real owner/bridge quiet acknowledgements.
No fixed delay substitutes for the SPI payload/CRC drain or FIFO quiet proof.

LAST is an ordered local marker, not EOF success. The unique final router's
actual TF transaction binds its LAST to that request's rate/epoch/sequence.
Only a matching real serializer completed frame, without frame error, session
cancellation or observation loss, may complete the tail. The bridge itself
does not produce physical EOF, select an output source, create serial requests,
replace `workstation_runtime_audio` or prove whole-workstation owner4 traffic.

The source-domain direct producer's local `sample_request_i` must not be driven
by a free-running test tick and presented as downstream I2S demand. Physical
underflow belongs to actual downstream request/admission and completion/error
evidence. Source local drain, FIFO transfer and physical frame completion are
separate boundaries.
