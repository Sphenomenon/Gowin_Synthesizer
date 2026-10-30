# Experimental bounded classic sink component

This component is an **unselected B04 source-stage**. It is not a complete or
conforming A2DP 1.4 Sink, a selected workstation input, phone interoperability,
ROM-fit or C04 timing acceptance, or hardware deployment. Its SDP record is an
experimental record targeting A2DP 1.4: mandatory Sink Delay Reporting is missing.
Do not expose this record in a production image as a qualified standard Sink.

`classic_service.c/.h` implements a single BR/EDR Basic-mode connection with SDP,
one AVDTP signaling channel/one Sink SEP, and one inbound SBC media channel.
There is no second HCI owner, RTOS, heap, UART/H5, transport retry engine, physical
credit counter, MMIO driver, whole-song cache, or output-clock authority here.
The code is first-party; reference identities are in
[classic_source_provenance.json](classic_source_provenance.json). The existing
Apache Android/OI decoder is used unchanged by the end-to-end test.

## Ownership and transport adapter

A cooperative CPU owner allocates `struct a138_classic_service` in local RAM.
`begin(link_epoch, PL_generation, handle, tx_payload_limit)` binds it to a real
BR/EDR connection already accepted by connection/security policy. Epochs strictly
increase for this object's lifetime. The transmit limit is immutable and is
`min(controller BR ReadBufferSize ACL-data length, 276)`, range 4..276. It is a
packet-size limit, not a physical-credit ledger. Controller-to-host HCI ACL
fragments must be bounded independently to 276 data bytes (280 including header).
The sole PL HCI owner validates/routes handles and owns all physical credits.

Feed complete original `{event_code, parameter_length, parameters}` events with
`event()`, and original `{handle/PB/BC, length_le16, payload}` ACL fragments with
`acl()`, always carrying the exact link epoch and PL generation. This component
only retires a matching successful Disconnection Complete event. HCI boot,
Connection Request/Complete, pairing, PIN/SSP, authentication/encryption, security
policy, scan/visibility and event-driven connection acceptance remain missing
CPU connection-policy work. Other events must still reach their actual owners.
There is no HCI-command producer in this component.

RX has one 676-byte reassembly buffer. A complete second PDU can wait while the
control response is pending. `BUSY` consumes no bytes: retain the exact ACL packet.
`OK`, `DROPPED` and `MALFORMED` consume that packet. `STALE` is a different session;
never pass it to the new one. The adapter owns the finite wait deadline and may
cancel/drop the classic session if it cannot retain a packet. It must allow PL
to retire/return each host-RX lease and keep BLE progressing. Holding classic
backpressure forever, suppressing host-credit returns, or stalling the audio
sample schedule is forbidden. No deadline or host-credit API is implemented here.

`tx_peek()` returns immutable original HCI ACL bytes and a token. Submit these to
the sole owner. `tx_result(ACCEPTED)` advances only the accepted fragment. A
conclusive `REJECTED` keeps the same token/bytes for an explicit retry. An
`UNCERTAIN` outcome fences the link and drops local queues; never replay it.
Acceptance is owner queue acceptance, not remote receipt or application. AVDTP
configuration/state changes commit after acceptance of the final response
fragment. There are no ordinary-command or Host Number Of Completed Packets
credit paths in this CPU module.

Before integration the sole transport must provide Host Buffer Size=276,
Set Controller To Host Flow Control, bounded per-handle host-RX lease/return
(including the special HCI0x0c35 path), valid BR handle generations, and retirement
of any old competing BLE GATT/bridge physical-credit authority. An ACL API alone
does not supply those capabilities. CPU reset requires PL retirement/fencing of
all old descriptors before reinitializing CPU objects.

## L2CAP, SDP and AVDTP bounds

- SDP/AVDTP receive MTU is 672 bytes, distinct from physical HCI fragments. A2DP1.4
  section5.2.1 requires at least335; no 240-byte MTU assumption is made. Peer MTU
  is directional and separately limits SDP replies. This Sink sends no media.
- Local CIDs are0x40 SDP,0x41 AVDTP signaling,0x42 media. Signaling CID1 uses a
  48-byte limit and supports multiple commands. Connection/configuration,
  disconnection, Echo and basic Information are handled; unsupported PSMs,
  mandatory options and cross-PSM SCID aliases are rejected. Envelope errors
  during a partial control response fence it before any response escapes.
- Configuration continuation, retries/timers, option adjustment/re-negotiation,
  ERTM/streaming/extended flow specifications and other channels are missing.
  Configuration Responses validate every option envelope; unsupported mandatory
  adjustments/continuation or non-success results drop the provisional channel.
  If aggregated responses exceed the 48-byte signaling bound, the stage fences
  rather than emitting an oversized or partially acknowledged response.
- SDP exposes one experimental Audio Sink record, Service Search, Service
  Attribute and Search Attribute requests, UUID16/32/128 search patterns and
  attribute IDs/ranges. Responses honor peer MTU, requested maximum bytes and a
  bounded stateless continuation token; transaction IDs may change between
  requests. The query including its maximum-byte count must remain identical.
  The token is query validation, not authentication. No dynamic record database.
- AVDTP supports Discover/GetCapabilities/GetAllCapabilities/SetConfiguration/
  GetConfiguration/Open/Start/Suspend/Close/Abort for one SEP. Signaling fragments
  use at most128 bytes. Reconfigure, SecurityControl and DelayReport are rejected;
  optional reporting/recovery/multiplexing/content protection are not advertised.
  **Mandatory A2DP1.4 Sink Delay Reporting is unimplemented.** Close/Abort clear
  audio and await the peer's media-channel disconnection; a local disconnect
  initiator, response timers and a full connection recovery policy are absent.

## Audio boundary

Only negotiated 44.1/48kHz SBC, mono/dual/stereo/joint,4/8 subbands,4/8/12/16
blocks, loudness/SNR, bitpool2..53 are accepted. Capabilities do not imply that a
complete SBC decoder, CPU deadline or output transport has been accepted on board.
An actual selected format is available only after its response is accepted.
`audio_ready(epoch,generation,selected_rate,1)` is an external grant from the
actual audio owner. Start is rejected until granted and the media channel is
configured. This module never switches a clock, writes PCM, or applies a common
parameter. Revoking the grant clears queued audio; revoking it while a Start
acceptance is pending fences the uncertain transition.

RTP validates version2, dynamic payload type96..127, M=0, X=0, CSRC/padding bounds,
sequence wrap, duplicate/reordered packets, SSRC identity and SBC frame sizes.
SBC fragments validate3,2,1-style remaining counts, start/end flags, common
timestamp and equal nonfinal packet size. The receive implementation tolerates
structurally valid SBC fragmentation even when a compliant source should have
packed the complete small frame under the negotiated672-byte MTU. CRC and actual
codec correctness belong to `sbc_decoder_service`, not the wire framing parser.

Only four complete SBC frames (each at most224 bytes) are queued. Whole-media-PDU
validation precedes publication. Malformed media, loss or queue overflow clears
all queued frames/fragments and increments `stream_epoch`; duplicates/reordering
are dropped without re-decoding or disturbing already queued audio. A changed
SSRC is dropped until a new stream establishes identity. A forward sequence gap
can accept the current fresh packet under a greater stream epoch. Epoch/token
exhaustion fences rather than wrapping. These metadata are internal; the existing
18-bit workstation event wire layout remains unchanged.

The consumer begins/resets the actual decoder on every new stream epoch, decodes
one complete frame, and publishes PCM only on decoder success after rechecking
link/PL generation and the active audio owner. Suspend/Abort/cancel/disconnect,
CPU reset and decode failure must retire old work. Decoder failure policy and a
hardware PCM queue handoff are not wired by this component. Same-rate source/sink
clock drift, SRC/elastic buffering and physical output latency remain integration
work; switching between44.1/48kHz alone does not solve long-term drift.

## Verification and selection policy

Run from the repository root, with a new external output directory:

```sh
python3 projects/138k/push2_workstation/usb_a/sim/run_ae350_classic_service.py --output /absolute/new/output
```

The runner compiles actual C natively and with ASan/UBSan; tests wire bytes,
structural truncations/overflow, deterministic valid-envelope SDP/AVDTP fuzz,
identity/token/cancellation behavior, slow/full queues and actual SBC reference
PCM. Sanitizer fixtures poison unused RX buffer tails so stale-byte reads beyond
the current PDU are detected even inside a larger allocated object. Behavior
mutants must fail. RV32 object sections and function stack frames are measured
separately. Complete firmware link/fit, call-chain stack, cycles/worst service
interval, MMIO/RTL glue, simultaneous BLE/BR routing, feature/resource/timing/CDC
checks, HCI controller behavior, phone interoperability and physical sound still
need acceptance. No builder/profile/source list, boot image or frozen baseline
selects these files. Integration must use a new explicit source identity after
these gaps are addressed; this experiment cannot become an undocumented input.
