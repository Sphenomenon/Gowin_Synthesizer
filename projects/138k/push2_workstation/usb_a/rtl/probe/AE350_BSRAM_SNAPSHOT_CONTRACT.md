# Explicit AE350 BSRAM snapshot probe

`build.py --ae350-local-memory-probe --ae350-probe-gao bsram4` selects this
development probe. It does not select a complete workstation profile. The old
`full64` and `banked4` modes retain their separate implementations and evidence.
Every changed physical candidate requires a fresh UserCode and source manifest.

## Diagnostic and publication contract

The firmware, 64 diagnostic words, UART `A138LM01` header, 280-byte frame,
little-endian sequence and reflected CRC32 are unchanged. Word61 bits0..3 are
the synchronized platform flags; bit4 marks a snapshot timeout. A timeout is a
new publication and sequence, with stale prior diagnostic data. It is never
reported as a fresh capture.

The pclk request/ACK bridge still captures all source words on one edge into
`held_words`. APB-local reset suppresses a new capture; it cannot reset ACK or
modify the held bundle. Common transport reset resets both sides. Following ACK
synchronization and three settling edges, a fresh capture takes exactly sixteen
50MHz COPY edges and one subsequent PUBLISH edge. This additional bounded
publication latency is specific to `bsram4`. The first timeout also initializes
an entire zero bank before publication. Later timeouts retain the prior bank
and publish only new sequence/flags.

Eight native 16-bit `workstation_sdp` lanes hold two banks of sixteen 128-bit
groups. COPY writes an inactive bank. The published bank becomes immutable
until UART finishes and the exporter adopts it. No request starts before that
ownership handoff. RAM contents have no reset; validity and ownership prevent
consumers from observing uninitialized storage. Common reset clears validity,
sequence, output and caches, and requires a complete new bank before validity.

## GAO and UART delivery

Schema `A1386403` is distinct from banked schema `A1386402`. The top-level
`status_50mhz[703:0]` remains a preserved 704-bit register bank. It carries four
16-word pages in order 0,1,2,3, each stable for exactly four reference clocks.
Sequence, flags, IO and health remain frozen for the sweep. A new publication
can replace the frozen bank only at the page3-to-page0 boundary. Page0 uses a
512-bit preparation cache filled during COPY; later pages use synchronous RAM
readout with a 384-bit prefetch and the final 128-bit read response. A timeout
overlays word61 flags without mutating a live data bank.

The read port continuously supplies one 128-bit group per reference clock.
UART borrows that stream through a tagged 32-bit word cache. A requested word
is encountered within one sixteen-clock sweep; UART waits for the matching
cache tag before launching its payload byte. It never steals a GAO read cycle.
The cache register is consumed on a later edge, so payload launch can add one
further reference edge after the matching RAM response. CRC covers the exact
bytes physically serialized. Baud divisors1 and4 exercise the cache wait in
simulation; physical configuration retains divisor434.

IO describes RTL output-drive levels and a modulo2^30 transition counter. It
does not establish pad behavior, external UART reception or measurement time.
The probe keeps DAC mute asserted, PDN low and digital audio clocks/data low.

## CDC, structure and acceptance

The held pclk bundle remains stable during COPY. `bsram4` retargets its bounded
20ns data-path constraint to native RAM DI pins; synchronizer exceptions retain
their existing request/ACK/flags ownership. The selected native DI paths and
timing/hold treatment require verification against the new actual VG/STA. No
old physical result establishes the new path.

The strict synthesis audit requires actual SDPB primitives, native16 synchronous
read mode, canonical50MHz clocks, shared valid addresses/control, grounded reset
and unused pins, independent active data bits, intact held captures, bounded
reference FFs, expected small caches, no old full/frozen snapshot FF copies,
and actual RAM read paths reaching all GAO payload lanes. Negative controls
exercise wrong clocks/modes/addresses, data aliases, missing bits and decoy RAM.
The source uses eight logical lanes; only actual synthesis and P&R determine
physical BSRAM count, CLS use and timing. Logical lanes are not a physical saving
claim.

Prepared inputs include this contract and exact audit/decoder dependencies.
Offline prepare, RTL simulation, synthesis, routed CDC/timing/resources, JTAG
identity, SRAM deployment, hardware acceptance and Flash are separate stages.
The source report does not claim EDA or hardware acceptance. Rollback selects a
previous hash-checked candidate; this mode never changes Flash implicitly.
