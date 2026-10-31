# AE350 explicit BSRAM snapshot source stage — 2026-10-31

This report covers source implementation, ordinary firmware compilation, RTL
simulation, synthesis-structure gate tests and offline prepare. It performs no
synthesis/P&R, JTAG, SRAM or Flash action and does not establish hardware
acceptance. The root agent owns subsequent physical work and its own evidence.

## Fixed inputs and distinct mode

Base: `c229a50444bfcdabbe4e89bed7ef12b1e54e0208`.
Compiled-source commit: `2690a6c31c4bad57b75542c30d61a8238ea553b8`.
The follow-up report/audit commit does not change compiled RTL, firmware, pin
constraints, clocks or prepared bytes.

`--ae350-local-memory-probe --ae350-probe-gao bsram4` explicitly selects schema
`A1386403`. Old `full64`/`banked4`, schema `A1386402` and their physical evidence
remain distinct. The new prepare uses `C21031CF`; testbenches use offline-only
`C21031D2`. Neither test identity claims a deployed board.

The maintained top instantiates `workstation_ae350_probe_snapshot_ram` as
`u_uart`. Eight native16-bit synchronous `workstation_sdp` lanes store two
immutable banks. This retains the pclk held snapshot while removing the
reference-domain2048-bit words,2080-bit publication and2080-bit frozen copies.
It adds page0 preparation512bits, next-page prefetch384bits and UART cache32bits.
These are source-declared storage changes, not measured CLS or physical BSRAM
savings. The preserved top GAO bank remains704bits. Physical resource mapping
requires the new actual netlist and route.

The mode preserves64words, UART format/CRC, freshness and sequence semantics,
four pages and four reference clocks per page. A fresh held capture needs16
COPY edges and one PUBLISH edge before the exporter can adopt it at page3→0.
The UART cache may wait one sixteen-clock read sweep and one later launch edge.
The exact bank ownership, reset, timeout and CDC rules are in
`rtl/probe/AE350_BSRAM_SNAPSHOT_CONTRACT.md`.

## Validation

- New end-to-end suite:9tests PASS. Actual UART serial bytes are CRC-decoded and
  matched to all64GAO words for each sequence. Async pclk data changes every
  edge; tests check atomicity, lane order, page cadence, sequence and freshness.
- Baud divisors1/4 and the official GW5A SDPB synchronous simulation model PASS.
  Local/common reset, initial timeout/recovery, retention after timeout and
  actual maintained top/DAC safety pass. Three source mutations are rejected:
  forged local-reset ACK, wrong synchronous read phase and live-bank overwrite.
- Strict actual-primitive netlist parser fixture: baseline plus14negative
  controls PASS. Includes wrong output enable, clock, width/mode, reset,
  addresses, alias/missing bits and decoy RAM data paths. This fixture is not an
  actual new synthesis netlist. Root must run the gate on its fresh actual VG.
- Existing banked9, full GAO5, local probe9 and accepted-source17tests PASS.
  Narrow Verilator lint and `git diff --check` pass.
- Offline CF prepare passes44input hashes/9compiled sources. Seven semantic
  mutations fail even after direct file-hash refresh: missing mode, old schema,
  wrong GAO bit, missing RAM source, audit dependency drift, missing dependency,
  and obsolete CDC endpoint. Native snapshot/audit/decoder contract files are
  explicitly included and hashed as noncompiled dependencies.
- CF ELF, binary, ROM and unchanged firmware sources are byte-identical to the
  prior banked/C11 preparation. Binary is36368bytes; cold ROM is65536bytes.

The source-stage delivery is
`/Users/sphenicidition/.cache/gw138k-task-20261030/ae350-bsram-snapshot-delivery-v1`.
Its `prepare-bsram4/inputs.json` SHA256 is
`da6cde61cf706b9fa4a7fdb55ffc13511db4ba4207be84fa001fd5a15d583b13`.
It contains original RTL logs, physical UART bytes, GAO CSV and decoded records
for seven positive scenarios, mutation logs, tool identities and exact source
copies. The outer manifest/verifier seals the complete file set independently
of the repository checkout. The compile closure and later audit closure are
recorded separately; the original prepare is never rewritten to match later
audit code.

## Remaining acceptance and rollback

Actual VG must prove eight SDPB native16 lanes, correct output/read enables,
canonical50MHz clocks and addresses, intact1858nonconstant held bits, bounded
reference FFs, no redundant wide snapshot FFs and all128RAM data bits reaching
GAO. Source attributes or a primitive-name count alone cannot satisfy that gate.
The new held→native DI CDC target must resolve in actual VG/STA; all clock,
hold/recovery/removal, RTC, core PLL placement and resource gates remain active.

Only subsequent dated physical evidence can establish routed timing/resources,
JTAG UserCode, SRAM functionality and external UART reception. IO remains RTL
drive-state observation only. A failed candidate rolls back to the root's prior
hash-checked SRAM candidate. No source-stage action changes Flash or declares a
prior accepted candidate failed.
