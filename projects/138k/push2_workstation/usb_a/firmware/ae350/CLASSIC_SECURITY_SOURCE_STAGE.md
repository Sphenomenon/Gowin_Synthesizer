# Experimental BR/EDR connection and security owner

`classic_security.c/.h` is a new, unselected first-party source component, frozen
from parent `4f8e42d` before this batch. It implements the actual bounded HCI
command/response/asynchronous-event chain into `classic_service`'s default-deny
non-SDP admission. It is not native transport wiring, a persistent key backend,
phone pairing/interoperability, qualification, linked-firmware fit or hardware
acceptance. No Flash, board, EDA, vendor or accepted-profile input is changed.

The deliberately limited policy is BR/EDR SSP Security Mode4 Level2,
NoInputNoOutput, no OOB, General Bonding, no MITM and no Secure Connections or
legacy PIN pairing. SSP creates unauthenticated P-192 combination keys (type4);
the atomic store may also return an existing authenticated P-192 key (type5),
without claiming this NoIO owner created MITM protection. New type5, debug,
legacy/unit, changed-combination and SC keys are rejected. A remote MITM
requirement is rejected because this owner cannot meet it. There is no fixed
PIN, invented numeric comparison, passkey UI or claim that encryption proves
MITM. Explicit forget is required before replacing a stored type5 key through
this limited NoIO policy.

## Required external ownership

Start once with a nonzero external common-controller-reset epoch, the sole PL
owner's actual BR payload limit, a Classic object and three atomic bond-store
callbacks. The caller must have genuinely completed host-flow bootstrap, kept
page/inquiry scans disabled, retired the old initializer/command/credit owners,
and have no BR/EDR link. Current native startup does not meet this handoff yet.
The initialization call does not manufacture evidence for those prerequisites.

All ordinary commands are owner2 inputs to the existing sole HCI flow owner.
This CPU owns no command quota, ACL credit, Host Number Of Completed Packets,
UART/H5 retry, controller reset, RF or output-clock authority. Existing BLE and
Classic must share the same external command/ACL ledger. That native replacement,
payload RAM/router/MMIO, original bridge/GATT credit retirement and BLE fairness
remain future integration work. Nothing here selects a new production source.

The queue holds at most8 commands, each at most25 bytes. `tx_peek` retains the
front token/bytes. REJECTED consumes nothing; ACCEPTED is actual irreversible
owner2/private transport acceptance; UNCERTAIN fences and demands external
controller recovery. Only the exact accepted token's transport completion and
matching owner2-routed CommandComplete/Status retire bytes. A response arriving
before transport completion cannot let another command overwrite the source.
Other owners' responses are ignored. No automatic retry/refund follows uncertain
acceptance. An observer reset revokes media and requests external recovery; it
does not reset the PL ledger or invent a new external epoch.

The adapter supplies complete original events in transport order, with the
actual newly admitted PL generation on ConnectionComplete and the same generation
on all later link events. Only a real ACL ConnectionRequest, available PL handle
capacity and a free local context produce AcceptConnectionRequest. Duplicate
pending requests cannot race themselves with a Reject. Unsolicited successful
connections, reused generations or admission inconsistencies require recovery.
Disconnect cancels unsent commands; an actually accepted old command retains its
bytes until retirement and cannot change a later link. One Classic connection is
supported, alongside whatever BLE link the sole external owner admits.

## Actual command and event chain

Startup performs ReadLocalSupportedFeatures0x1003 (controller SSP/extended
features), WriteSimplePairingMode0x0c56=1, ReadLocalExtendedFeatures0x1004 page1
(actual host SSP bit set, SC host bit absent), then WriteScanEnable0x0c1a=2.
All require successful exact-length CommandComplete. Page scan is enabled only
after the successful SSP verification; inquiry discovery is outside this batch.
There is no radio Reset or advertising command here.

After actual successful ACL ConnectionComplete and authoritative generation,
the owner calls the real Classic `begin` with security denied. It reads remote
controller and host SSP features through0x041b/0x041c and their matching complete
events. It initiates AuthenticationRequested0x0411 unless the peer already
started authentication. Real LinkKeyRequest can interleave feature discovery:
the bounded store returns a checked key or the owner emits a negative reply.
An early IO request is held for at most1000ms while actual remote features are
verified, then receives real NoIO/OOB0/GeneralBonding4 or an explicit negative
reply. Peer-initiated authentication does not cause a duplicate local request.

IOCapabilityResponse and UserConfirmationRequest are checked for the exact
peer/generation, actual remote capabilities and numeric range. JustWorks
confirmation is automatic under the stated unauthenticated policy; it is not a
user numeric comparison. PIN, passkey and OOB requests receive the corresponding
negative HCI reply. Unknown peers receive negative replies without loading their
key or granting the active peer anything. Old-generation events for the same
peer are ignored rather than replying into a new pairing. A second LinkKeyRequest
within the same attempt is conservatively rejected; an identical duplicate key
notification is idempotent, while a changed duplicate closes the attempt.

CommandStatus0 from AuthenticationRequested only accepts the procedure. A matching
successful AuthenticationComplete is required. Likewise SetConnectionEncryption
0x0413 requires the matching EncryptionChange, followed by successful exact-handle
ReadEncryptionKeySize0x1408. The size must be7..16 bytes and cannot downgrade a
stored bond's size. Only a previously durable checked key or actual successful
atomic replacement of the new key permits the owner to call the real Classic
security grant. An SSP status, H5 ACK, local boolean or key notification alone
never authorizes AVDTP.

Classic permits SDP before that grant. An unencrypted AVDTP ConnectionRequest
returns L2CAP security-block0x0003, allocates no channel and causes the security
owner to submit actual HCI Disconnect after its response is irreversibly accepted
or100ms elapse. This fixed NoIO policy does not wait for product user input, so it
does not claim a pending-user-interaction/RTX/ERTX implementation. General L2CAP
timers remain an independent missing feature.

Encryption loss, authentication/encryption failure, failed key refresh or bad key
size revoke the actual Classic grant, clear non-SDP channels and queued media,
and disconnect. A successful refresh also revokes/clears non-SDP work until a new
key-size check completes; this experimental policy requires channel reopening
and does not implement transparent stream continuation. Delay/Classic fencing
also closes the connection. A rejected Disconnect or a missing disconnect event
cannot leave an indefinitely authorized context: it requires external recovery.

## Atomic persistent-owner contract and limits

The external bounded owner atomically maintains peer BD_ADDR,16-byte key, key
type, minimum negotiated size, version1 and strictly increasing nonzero revision.
Load results must match the requested complete peer identity and policy. Atomic
replace/delete compare the expected revision. OK means actual durable completion;
BUSY means no mutation committed, and ERROR cannot authorize. Torn records,
unobserved committed mutations and rollback must be solved by that backend's
idempotent owner, not by pretending this callback implemented Flash storage.

The fixture uses an in-memory atomic model. There is **no physical persistent key
backend in this batch**. New pairing cannot become usable without one at native
integration. Writes, space exhaustion/CAS failure and revocation persistence are
explicit failure boundaries, and no key is written to the board's Flash here.
Known-key authentication failure0x05/0x06 requests atomic deletion, then disconnects;
the next real connection can pair afresh. No infinite authentication retry occurs
on the same link. Explicit forget revokes an active peer and durably deletes its
record through the same callback. No product UI is added.

Only atomic replace/delete BUSY results are polled, with the stated1000ms bound.
A LinkKeyRequest load BUSY/error/corrupt result is conservatively treated as an
unavailable trusted key: a negative reply and connection close follow. A forget
load BUSY/error/corrupt result fences the observer and requests external recovery.
These are explicit conservative failure policies, not a claim that every store
operation supports deferred polling. An interrupted uncommitted pairing clears
its temporary key facts on real disconnect, so it cannot block forget forever.

Tick uses an independent monotonic uint32 millisecond source, called before each
pass at least every100ms. Forward wrap is valid; backward/ambiguous jumps fence.
Every offered/accepted command including quota/transport stalls has a1000ms
deadline. Connection/security attempts are bounded by30000ms, a deferred IO reply
and atomic mutation by1000ms, and close by5000ms. Deadlines checked before incoming
success win. Pumps never wait, allocate heap or drive the audio sample schedule;
at most one persistent callback occurs per pump. These are software work bounds,
not measured CPU service deadlines or H5/phone performance.

Verification entry: `sim/run_ae350_security.py --output /absolute/new/external-dir`.
It executes actual maintained command/event/Classic code under native and
ASan/UBSan, policy/identity/storage/transport negatives and valid-envelope fuzz,
behavioral mutants, all preceding Delay/Classic/SBC reference regressions and
incremental RV32 object/state/individual-function stack measurements. Prior
protocol fixtures now supply an explicit trusted grant; the new fixture earns
it through actual HCI events and durable-model completion. Full ROM128 linking,
whole-call-chain/callback stack, cycles, native BLE preservation, real phone,
audio-delay/drift, routed timing and hardware acceptance remain separate.

The immediate security-block/close policy for an unencrypted AVDTP service request
is conservative. Phones may use the service request to trigger authentication;
the actual phone/session timing has not been tested. Native integration must
validate this interaction instead of assuming the offline security chain proves
phone compatibility. Late old ACL, peer-security events and command results may
not reactivate a disconnected context. Procedure error status is recorded as a
cause and mapped to valid Disconnect reason0x05 (security failure) or0x13 (explicit
forget), rather than copied into a field with a different allowed-value contract.

Normative basis: Core6.0 HCI connection/reply/authentication/encryption commands,
SSP mode and corresponding events; Core6.0 GAP BR/EDR Security Mode4, bonding,
NoIO/JustWorks and SDP exception; A2DP1.4 Table6.1/section6.2 bondable mode.
Source URLs/hashes are recorded in `classic_source_provenance.json`; external
standards receipts remain immutable and no copyrighted standard body is copied.
