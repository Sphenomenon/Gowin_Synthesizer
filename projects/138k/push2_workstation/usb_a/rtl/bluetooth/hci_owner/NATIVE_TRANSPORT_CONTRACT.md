# Native shared HCI transport v1

This is the experimental native PL/AE350 contract. It does not change BLE
UUIDs, ATT values, the recording business protocol, or the 18-bit event bus.
The opt-in transport replaces both old physical controller credit authorities.
All registers below use the existing f8050xxx APB CDC, little endian, aligned
32-bit access, full write strobes. Other pages retain their previous owners.

The controller epoch is the nonzero low32 of the initializer's real LE_Rand
boot_id, or high32 when low32 is zero. It identifies the common controller
reset, not CPU reset. Random collisions are possible; this is not a persistent
monotonic counter. A common reset clears H5, every PL reader and descriptor,
and all ledgers together. An AE350 observer reset fences Classic and flushes
only CPU copies after their bounded internal RAM read pipeline; it never
resets H5, BLE, generations, or either physical packet ledger.

| offset | access | meaning |
|---|---|---|
| 200 | R | ID 0x48434931 (HCI1) |
| 204 | R | 0x01040114: ABI[31:24]=1, slots[23:16]=4, data limit[15:0]=276 |
| 208 | R | bit0 ready,1 controller fault,2 Classic fenced,3 CPU queue copying,4 BR admission available |
| 20c | R | current external controller epoch |
| 210 | RW | staged TX epoch |
| 214 | RW | staged TX generation |
| 218 | RW | staged TX token, nonzero strictly increasing per epoch |
| 21c | RW | type[3:0], length[24:16], other bits0 |
| 220 | W | BEGIN=1, only with TX empty; clears staging metadata/byte count |
| 224 | W | COMMIT=1, after exactly length sequential TX_BYTE writes |
| 228 | W | append one complete HCI packet byte in bits7:0; other bits0 |
| 22c | R | state[3:0], response retired bit8, accepted bit9, transport retired bit10 |
| 230 | W | ACK exact TX token; requires DONE+response, REJECTED or UNCERTAIN |
| 234 | R | TX reject/fault reason |
| 238 | R | TX number of bytes staged |
| 23c | RW | release key epoch, required with RX RELEASE |
| 240 | R | CPU RX count[7:0], head present bit8, copy busy bit9 |
| 244 | R | head epoch |
| 248 | R | head authoritative handle generation,0 for prelink events |
| 24c | R | head ticket, nonzero monotonic until common reset |
| 250 | R | raw HCI type[3:0], owner[9:8], response bit10, length[24:16] |
| 254 | R | handle[11:0], retired bit16 |
| 258 | R | original command token for owner2 response, otherwise0 |
| 25c | RW | head packet byte read index0..length-1 |
| 260 | R | head byte[7:0], synchronous RAM; PREADY waits the read pipeline |
| 264 | W | RELEASE exact head ticket and23c epoch; no active read survives it |
| 268 | R | dropped CPU copies, saturated |
| 26c | R | rejected stale/invalid CPU operations, saturated |
| 270 | R | actual BR limit[15:0], LE limit[31:16] |
| 274 | R | BR available[15:0], LE available[31:16]; diagnostic only |
| 278 | R | independent reference-clock time_ms32, wraps, unaffected by CPU/ready |
| 27c | W | request Classic FENCE using exact current nonzero epoch |

HCI type1 is a complete ordinary command (opcodeLE16,param length8,params),
type2 a complete physical ACL packet including its four-byte HCI header,
type4 a complete original event including event code and parameter length.
CPU only submits type1 or type2. The PL fixes its command owner to2; owner0
belongs to initializer/bootstrap,1 BLE,3 dedicated hardware0c35. CPU cannot
submit0c35, Reset, host-flow/buffer commands, LE advertising commands, or spoof
another owner. Before a BR link commands use generation0; afterwards commands
and ACL use the actual PL BR generation. ACL packet length must respect the
actual BR data limit; L2CAP fragmentation/reassembly remains a CPU service.

The explicit `SESSION_ONLY_PAIRING` policy also permits parameterless
`Read_BD_ADDR` (1009) and `Read_Scan_Enable` (0c19), each exactly three HCI
command bytes. The same CPU command owner, private packet copy, physical
command credit and original owner2 completion apply. The session service
checks its actual address and scan state before declaring startup ready;
these reads do not grant reset, advertising or another producer's ownership.
The default policy rejects both commands.

BEGIN/staging/COMMIT never mean irreversible acceptance. TX states are0 EMPTY,
1 STAGING,2 PENDING,3 ACCEPTED,4 TRANSPORT_DONE,5 REJECTED,6 UNCERTAIN.
ACCEPTED occurs only after the entire payload is in a private PL RAM and the
sole flow owner and H5 irreversible acceptance happen on the same edge.
H5 retransmissions never debit again. State4 proves only this exact token's
actual transport retirement. For an ordinary command the slot remains immutable
until both its owner2-routed original CC/CS and its transport retire; these may
arrive in either order. A successful CS does not imply an asynchronous command
procedure succeeded. Raw owner2 CC/CS descriptor258 identifies the original TX
token. ACK is the explicit final retirement; neither a BLE result nor an
unrelated H5 done can advance the CPU token. Rejection consumes no controller
credit. Accepted transport uncertainty faults the controller; CPU must recover,
never replay it automatically.

RX is an ordered four-slot private CPU copy queue. Publication happens only
after every byte has been copied through the actual synchronous read pipeline.
A CPU read cannot see a partially written slot. Disconnect marks copies of the
old generation retired; their bytes/ticket remain immutable through exact
RELEASE, including same-handle reuse. CPU reset or queue overflow fences
Classic; PL lifecycle, NCP, BLE routing and host credit return continue without
waiting for the CPU. The router discards further Classic copies and schedules a
bounded HCI Disconnect for an active BR link through the same command owner.
CPU queue overflow is never reported as continuous media. Hardware leases are
released only after the real CPU-copy/LE-reader completes; CPU RELEASE retires
its independent copy and cannot refund physical controller credits.

The audio identity output is a source-clock register plus the immutable epoch/BR
generation bundle. `hci_classic_ready_o` stays low for at least one complete
50MHz clock when the tuple changes. Actual successful BR disconnect and Classic
fence withdraw it on the ledger/fence edge. A newly registered decoder fault
withdraws it within one additional50MHz clock (20ns); this bounded propagation
does not wait for the CPU. The independent audio owner must synchronize this
ready and coherently capture the bundle, reject mismatches before consuming
PCM/results, and keep the physical audio frame schedule running.
