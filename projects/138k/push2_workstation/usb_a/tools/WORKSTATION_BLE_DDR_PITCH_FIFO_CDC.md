# Explicit 18ed pitch/FIFO CDC review scope

`runtime-r00-no-local-panel-ble-ddr-pitch-fifo-v1` binds the completed
`custom138k-workstation-r00-no-local-panel-v1-18ed947312186187` synthesis.
Its 599 staged inputs and 269 enabled inputs are checked independently,
including enabled order, disabled legacy counter, native counter selection,
BLE raw-DDR metadata, Chorus provenance, registered TF bridge, pitch source
`c4053635...`, and delay FIFO source `ca9f50cd...` plus both provenance sidecars.
The root profile's current helper lock bytes are review identity; the fixed
prepared profile/source and synthesis identities remain separate. Updating
these review helpers does not claim new RTL synthesis or reuse its identity.

The endpoint table is extracted independently from the actual 18ed VG
`c9f88c71d63478c0e659806f5497ab867e2a5f01e3d924f1bf5938f884a51e7b`.
All 13 phase1 and 42 raw producer groups begin at their declared registers
and traverse complete combinational fanout through FF D/CE/CLEAR, primitive
and top-output terminals. The retained PcmNetlist strict named-port lexer
checks every instance, escaped formals, duplicate bindings and unparsed text;
OwnerResetNetlist retains its exact observed owner reset formal adapter.
Serial, c7 and 6b source/endpoint modules remain unchanged and reject 18ed.
The new table rejects their VGs. Different actual closure D/CE mappings are
reviewed anew; matching payload bitmaps or reset aliases confer no acceptance.

Run the four existing public audit tools with this explicit scope (shared
uses `--precision-profile`; the others use `--scope`). They check 88 retained
shared lines, three USB2 owner CLEAR receivers and their fanout, phase1
425 reviewed FFs / 42 Gray first bits / 82 held payload bits, and raw
13 ordinary pairs / 50 Gray bits / 528 logical and 524 mapped payload FFs.
The phase1 SDC is a proposal output only. No constraints are installed.

`sim/test_workstation_ble_ddr_pitch_fifo_cdc_scope.py` runs source negatives
by default. To check the immutable completed stage and actual graph mutants,
set `GW138K_PITCH_FIFO_CDC_STAGE`, `GW138K_PITCH_FIFO_CDC_PROCESS` and optionally
`GW138K_PITCH_FIFO_CDC_TEST_EVIDENCE`. It never prepares, synthesizes, rewrites
the VG/SDC or operates hardware. Cross-scope negative runs additionally reject
serial/c7/6b/new candidate substitution through all four public dispatchers.

This is source and mapped structural review only. Missing seal-result code
bits, full reset/CDC inventory, physical RAM ownership, MTBF, routed timing,
board acceptance and deployment remain separate work. No full CDC, release,
SRAM/Flash deployment or hardware acceptance is asserted by this scope.
