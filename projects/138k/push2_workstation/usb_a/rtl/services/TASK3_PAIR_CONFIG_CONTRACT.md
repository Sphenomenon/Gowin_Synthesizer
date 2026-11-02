# Task3 paired configuration owner

`workstation_task3_pair_config_service` is the common M/W F808 service after
the existing APB CDC, using its 50 MHz destination clock and owner-reset
signal. It performs immediate command admission; every transaction returns
ready or error without waiting for the peer, CNN, recording or audio.
CPU commands do not alter the authoritative common musical parameters.

All identity/configuration outputs reset to zero. Firmware must actually
write a nonzero local boot nonce, expected peer nonce, shared session and
generation. The service does not generate a nonce or insert constant boot 1;
firmware remains responsible for obtaining fresh boot/session values. Local
and peer nonces must differ. Full-word aligned writes are required.

Enabling probe validates all four freshly written fields and freezes them.
The generation must strictly exceed the previously enabled generation and
the session must differ from the previous enabled session. No wrap is
accepted. Owner/CPU reset clears staged values and grants but preserves the
generation/session history until FPGA reset. Rebooting the FPGA starts a
new nonce lifetime and requires fresh CPU writes.

Probe enable is independent of business. A live peer never asserts the
budget flag. Firmware may assert that flag only after physical budget
evidence exists; the register stores this explicit assertion, without
purporting to verify the measurement. `ALLOW_BUSINESS=0` rejects both budget
and business enable commands. Enabling business also requires an enabled
probe, a live peer and the explicit budget flag. The transport retains its
own compile/runtime gate. Actual endpoints must use the business grant,
while the LCD transport uses probe enable.

CPU reset, explicit probe disable, transport fault, peer PANIC and loss of
a previously live link clear all staged fields and grants and issue a local
record-cancel request. Withdrawing an asserted budget or disabling granted
business does the same, so reenabling requires a higher generation and a new
session. Initial probe startup may wait for its first peer; transport timeout
remains a separate bounded failure. Command admission is never stalled.

Record arm, record cancel and PANIC are one-cycle local request pulses;
admission is not downstream application or physical acceptance. Record arm
requires a current business grant. Record cancel itself leaves the link
configuration active, but downstream generation/replay fences still apply;
it does not authorize another recording with reused identity. PANIC revokes
all local grants and pulses its request. The board binding must separately
hold a physical dedicated PANIC level long enough for the peer synchronizer
and acknowledge the result. Closing probe and emitting a one-cycle request
alone cannot prove a physical peer received PANIC.

All offsets below are relative to the new F808 aperture. The paired profile
must explicitly decode and connect it; this module alone does not add a CPU
bus region or enable a pin. Writes to read-only, unmapped, misaligned or
partially strobed locations fail without modifying configuration.

| Offset | Register |
|---|---|
| 000 | RO identity 54335001 |
| 004 | RO status: bit0 all fields written, 1 owner live, 2 probe, 3 budget, 4 business, 5 peer live, 6 peer PANIC, 7 link fault, 8 previously live; bits12:9 last revoke reason |
| 008 | RO bit0 compile-time ALLOW_BUSINESS |
| 010 / 014 / 018 / 01c | RW local boot / peer boot / session / generation, only while disabled |
| 020 | RW probe enable, 0 or 1 |
| 024 | RW measured budget assertion, 0 or 1 |
| 028 | RW business enable, 0 or 1 |
| 02c / 030 / 034 | W1 record arm / record cancel / PANIC requests |
| 038 / 03c | RO last enabled generation / session |
| 040 / 044 | RO saturating revoke / rejected-command counts |
| 048 / 04c | RO last revoke reason / command rejection |
| 050 / 054 | RO actual transport TX / RX packet counters |
| 058 / 05c / 060 | RO CRC / sequence / rejected transport counters |
| 064 / 068 | RO overflow / congestion cycles |
| 06c / 070 / 074 / 078 | RO last RTT / max RTT in local cycles / probes / timeouts |
| 07c | RO actual transport failure code |

Revoke reasons are 1 owner reset, 2 explicit disable, 3 link loss, 4 transport
fault, 5 peer PANIC, 6 local PANIC, 7 budget withdrawal, 8 business disable.
Command rejection codes are 1 unmapped/read-only, 2 alignment, 3 write
strobes, 4 inactive owner or frozen/fenced state, 5 invalid value, 6 incomplete
or reused identity/session, 7 non-increasing generation, 8 compile denial,
9 unavailable live/budget grant. Diagnostic readbacks use actual inputs;
they do not create model availability or measured acceptance evidence.

`sim/workstation/run_task3_pair_config_service.py --output <new-directory>`
runs both compile-gate configurations and preserves source, commands and log
hashes. It performs no synthesis, board access or hardware programming.
