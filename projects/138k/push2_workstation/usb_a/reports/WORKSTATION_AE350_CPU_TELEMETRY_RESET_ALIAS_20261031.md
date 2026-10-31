# AE350 business CPU telemetry reset selector correction (2026-10-31)

The existing business profile's full synthesized netlist
`903cd61c606b6419bd45ee2004b3e9d93520509d2e6cdb2ee4654ca52e0cf916`
contains no `u_runtime/u_cpu_cdc/{source,destination}_release` flip-flops.
Gowin rejected the old reset-only selector with TA2003 at SDC line 203.
The mailbox and its data/handshake flip-flops remain present.

Independent inspection of this actual VG identifies the surviving shared
three-stage release chains as `business_commands/p_release_{0,1,2}_s0`
(`ram_clk`) and `business_commands/a_release_{0,1,2}_s0` (`clk_50m`).
Their final stages feed the CPU telemetry's two reset nets through two INV
cells. All 455 mailbox FF consumers agree with those reset/clock domains.
The old selector matches zero pins; the replacement matches exactly these
six release-register CLEAR pins. It does not cut data/handshake FF CLEARs.
The existing SDC did not otherwise cover these six release-register pins.

Only `custom138k-workstation-ae350-business-v1` now replaces the exact old
constraint with:

```tcl
set_false_path -to [get_pins {business_commands/p_release*/CLEAR business_commands/a_release*/CLEAR}]
```

Missing, modified, duplicate, or already-installed anchors fail preparation.
The profile verifier checks the selected constraint and its recorded evidence.
All other constraints are preserved; profile revisions/features and frozen
baselines are unchanged. Current source hashes are refreshed for shared helpers.
A changed candidate must still prove the actual six-pin aliases before use.

Validation: the 11 business tests pass, including three tests against the real
272-input prepare `custom138k-workstation-ae350-business-v1-d219952502eb142f`.
The current-workstation source suite passes 17 tests; the profile suite passes
7 tests with 15 external-profile tests skipped. Firmware preparation uses the
same explicit xPack GCC 15.2.0 prefix as the locked callback/disassembly review.

Evidence remains outside source under
`~/.cache/gw138k-task-20261030/business-empty-reset-sdc-v1/`:
`actual_reset_alias_proof.json` SHA256
`bccaaa65fdce85c7f39c3169a49f819029dd58a40ecbcdfd2b014a0bb9bce69d`,
plus `business-prepare-v3/`. No source RTL or firmware bytes are changed here.

The same VG's E1 physical experiment (empty line removed, before this exact
alias correction) failed PR0004 with 2841 unrouted nets after 1203.787 s:
CLS 62005/69120, physical BSRAM 297/340. It produced no FS/TR/SDF. Its input and
tool identities are unchanged. E2 retains the corrected physical inputs but
was withdrawn before taking the build lock or invoking EDA after the root's
instruction to evaluate routing feasibility first. Neither experiment is a
routed timing/CDC acceptance or an SRAM/Flash deployment.
