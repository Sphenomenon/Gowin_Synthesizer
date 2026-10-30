# TF LAST transport and physical-tail endpoint source candidate

This unselected source candidate extends native TF playback through the real
final-router, PCM frame bridge, I2S serializer and completed-frame observation
boundary. It adds reusable components and a simulation fixture. It does not
select another production audio top, modify accepted profiles or integrate the
complete workstation. The eventual composition point remains the unique
`workstation_runtime_audio` audio owner.

Base source is `232a3eba6b7af5226ea477976b448c54ee949e4c` (native SPI/FAT/WAV
composition, integrated upstream as `94fd199`). All prior tracked files,
sealed owner bytes, the four profile JSON files and `build.py` remain unchanged.
The final external receipt records the candidate commit and every input hash;
no bitstream was produced.

## Components and contracts

- `workstation_tf_frame_bridge_v2.sv` is a checked, reversible derivative of the
  maintained bridge. Its existing FIFO/cancellation algorithm is unchanged.
  The 118-bit packet carries atomic LAST and frozen caller session generation,
  separately from the transport's Gray cancellation generation. Its versioned
  provenance ledger and exact patch reproduce and reverse every edit.
- `workstation_tf_physical_tail_v1.sv` is a reusable two-domain endpoint. ARM
  crosses an immutable mailbox and captures the real observation source-drop
  baseline in the serial domain. Actual TF admission waits for the matching
  ACK. Only the actual final-router TF handshake binds LAST to that request's
  epoch/sequence. Completion needs both its exact serializer receipt and the
  matching completed-frame observation. The serial receipt samples the source
  drop prefix on the following real source edge, including the tail frame's
  actual FIFO accept/drop action. Baseline and prefix travel with the same
  session. Errors, cancellation, drop notifications, unequal/decreasing drop
  counts and saturation fail closed. Stream cancellation never resets an
  in-flight mailbox. A late old reply can retire its slot but cannot arm or
  complete a newer session.

The contracts next to these modules define port domains, failure/cancellation
and quiet semantics. The observation producer must be the existing monotonic
saturating 32-bit counter; a wrapping producer is incompatible. Explicit stop
still combines native SPI payload/CRC drain, shallow transport generation/FIFO
quiet and the actual router/PCM bridge/serializer quiet acknowledgement.

## Offline evidence

Evidence root:
`/Users/sphenicidition/.cache/gw138k-task-20261030/tf-direct-physical-native-v1/`.
The two primary native-chain receipts are `physical-controls-v1` (3 cases) and
`physical-final15-v1` (15 cases); their complete input-hash maps are identical.
This avoids repeating the eight-minute FAST12 run without mixing source bytes.

The 18 real-chain cases use native SPI wire transactions, FAT16 superfloppy or
FAT32 MBR, strict WAV/direct ingress, atomic shallow transport, the unchanged
final PCM router/frame bridge/I2S serializer/observation queue and independent
PCM/serial-pin oracles. Source is 50 MHz, compute 76.8 MHz and serial MCLK is
12.288 MHz at 48 kHz or 16.9344 MHz at 44.1 kHz. Fractional-clock scheduling
bounds absolute rounding rather than accumulating period rounding. The source
ingress `sample_request_i` is constant zero: actual serializer/router requests
own underflow deadlines. Fixture silence rendering is explicit and does not
consume TF while ARM, pause or tail closure blocks admission.

Both rates cover normal two-track completion, pause preserving the next TF
head across 200 real physical frames, cancellation with LAST in the shallow
FIFO, at LAST admission, after router completion and during serialized tail,
plus suppression of the actual final PCM return. The last case produces real
serializer underrun/error and no successful EOF. A real observation FIFO
overflow case isolates the serial source-drop prefix even when destination
gap/drop notifications are masked at the endpoint input; it rejects EOF and
then completes an explicitly recovered second track with a nonzero baseline.

FAST12 uses an actual 11,000-frame first track and fails the real router supply
deadline after 7,790 admitted frames, while the producer's local deadline is
disabled and `native_failed` remains false. It performs actual cancellation,
payload/CRC and audio quiet drain, then completes a distinct 97-frame track.
The slow card setting is not claimed as continuous 48 kHz supply.

Across all 18 cases, the fixture verifies 20,990 completed physical frames,
10,975 TF-labelled physical frames, 21,032 router requests, 2,710,497 BCK edge
checks and 21,174 LRCK period checks. There are 22 successful physical EOF
events, all from eligible completed sessions. The four deliberate underruns
belong only to the two suppressed-return cases; the two deliberate observation
drops belong only to the source-prefix rejection case.

The actual elaborated closure has 18 RTL instances and zero DDR request ports
or sources. This is a component closure, not a complete workstation owner-4
trace. The fixture uses public interfaces and contains no force/deposit or
private serializer state acknowledgement.

`tail-endpoint-v2` adds 11 bounded public-port protocol cases: both completion
arrival orders, exact `FFFFFFFF`/zero sequence identities, router-error range
across wrap, saturated ARM baseline, incremented/saturated/decreasing source
prefix, the next-edge FIFO watermark, physical and observation errors, stopped
serial-clock cancellation, late old replies and explicit new-session recovery.
Seven elaborated behavioral mutants are rejected: early observation-only EOF,
ignored sequence, ignored epoch, ignored fence, ignored source prefix,
acceptance of saturated ARM and sampling before the actual FIFO edge. These
synthetic endpoint cases are separate from the real native-chain proof.

`bridge-v2-initial` passes two cancellation-generation seeds (zero and
`FFFFFFFD`), real 48/44.1 kHz WAV decode, atomic metadata, FIFO stalls, clock
stop high/low, quiet invalidation and actual router mismatch. Its four mutants
lose LAST, session identity, quiet proof or a Gray prefix and are rejected.
The original bridge regression and all 17 accepted-source boundary tests pass.
Tail endpoint Verilator lint has zero warnings. Bridge v2 has the same three
warnings as the unchanged bridge: two reset-release `SYNCASYNCNET` notices and
the existing FIFO `RAM_STYLE` unused parameter; no warning is suppressed.

## Acceptance limits and rollback

No synthesis, P&R, physical CDC/skew/metastability analysis, full workstation
owner-4 closure, hardware operation, SRAM or Flash deployment occurred. Real
card latency, the physical 50 ms budget, routed resources and hardware EOF
acceptance remain open. This candidate grants no deployment readiness.

Rollback is removal of this unselected candidate commit. Existing selected
profiles, baseline reconstruction and prior native owners retain their bytes.
The next integration must connect the reusable components to the unique audio
owner and establish composition, routed timing/CDC/resources and hardware
acceptance as separate gates. No text overlay or alternate production builder
is introduced by this candidate.
