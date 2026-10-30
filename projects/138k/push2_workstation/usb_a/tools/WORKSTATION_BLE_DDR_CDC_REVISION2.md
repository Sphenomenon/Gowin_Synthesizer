# Revision 2 BLE DDR CDC source review

The explicit review scope is `runtime-r00-no-local-panel-ble-ddr-v2`.
It selects prepared revision 2 of `custom138k-workstation-r00-no-local-panel-v1`,
with complete canonical configuration SHA-256
`91b4e11fd6c293d58784d38726c542e4f2379bfb3a1503cd8eb2aa21b2508f7c`.
The prior no-panel configuration identity and default audit entry points remain
unchanged and reject this configuration. A matching profile name alone cannot
select this scope.

`workstation_ble_ddr_cdc_scope.py` pins the composition, seal bridge, authority,
owner mux, memory guard and FIFO source bytes. It checks exact recording/BLE
metadata, disjoint address allocation and the checked BLE adaptation closure.
The prepared profile digest is historical provenance; current root profile-byte
equivalence is not claimed. All public full audits seal synthesis and audit
inputs before and after reviewing the original VG.

The scope also pins the 269 prepared enabled input identities (canonical-map SHA-256
`2079bd030f6011aa74592f5916b60998e00ec007d3346fd3220346584b473d40`)
and the actual GPRJ compilation order (canonical-list SHA-256
`8aa696190fcc15a6a8019c07e7221ae1f9f35df31e2d0865c275071e3d5e967f`).
The GPRJ enabled paths and actual bytes must exactly match prepared
`enabled_inputs`. The legacy serial
`src/migration/gw138k_counter_cdc.sv` must be compiled. A future balanced decode
selection must receive a separate review even if its business configuration,
register names and staged-but-disabled legacy bytes remain identical.

The shared review adds an explicit `--precision-profile` value with the above
name. It retains the original exact 88-line object checks, status producers,
Gray/payload bounds and first-stage fanout checks. The public clock audit still
checks the disabled panel configuration. The USB2 owner reset review adds
`--scope` with the same value and retains its three exact receiving CLEAR pins
and complete downstream reset fanout checks. Its `--profile` still names the
prepared no-panel profile.

The recording phase1 review adds the same explicit `--scope`; its default is
`legacy-v1`. The revision 2 PCM/APB structure remains 425 FFs, 42 Gray bits and
82 held payload bits. The common recording reset is now the second stage of
the declared root-only memory-clock release. The APB assertion also includes
`preset_n`. Ledger/UI reset is observed by authority and cannot reopen the
untagged return epoch.

Gowin merged the seal destination two-stage release with the first two stages
of `u_recording/pcm_cdc/drops/destination_release`. The exact source equations
share the reset, memory clock, zero assertion and constant-one shift. Stage 1
therefore also reaches ten seal functional CLEAR pins through one inverter.
The revision 2 checker pins that entire combined closure; it does not permit
arbitrary extra first-stage consumers. The old phase1 endpoint hashes are
preserved. Eight final source-closure identities remain equal to revision 1;
four changed identities reflect explicit service/backend D/CE factoring and a
prefetch FF suffix change, while their 68 opaque primitive endpoints are
unchanged. The APB release's two opaque CPU port names changed. Opaque primitive
semantics remain unaccepted.

`workstation_ble_ddr_cdc_inventory.py` is a separate source endpoint inventory.
It checks eight raw-store ordinary pairs, four seal pairs, one authority open
pair and all 50 Gray bits: two nine-bit FIFO pointers plus the authority's
32-bit heartbeat. Every first D binds to an explicitly declared unique FF Q;
every first Q reaches only its declared second D. The two pointer MSBs use
explicit binary-MSB aliases supported by the pinned binary/Gray equations.
The top qualified-channel pair has an explicit Boolean proof for the grant
and survival producers and is identified as a safety assertion boundary.

The four raw-store payload groups declare 528 bits, with 524 actual source FFs.
The checked adapter drives `command_length[13]` from zero; the raw-store BL8
publication path keeps `return_word[2:0]` zero. All live bitmaps and 42 complete
source/reset/safety closures are pinned separately from legacy identities.
The raw control release shares the observed PLL-init `enable_r[1:0]` physical
chain, and the raw memory release shares the top `recording_memory_release`
chain. Their clock, root assertion, zero INIT, CE and shifts are checked, and
all combined consumers, primitives and top exports are retained in inventory.

The seal declares a failed bit and a four-bit code payload. Only the failed FF
survives in this candidate. The four absent code bits are reported explicitly;
their elimination is not accepted as a constant/alias or complete handshake
proof. Source inventory also does not accept raw FIFO RAM ownership, held
payload capture timing, reset assertion pulse width, recovery/removal or
metastability margins. It emits no SDC proposal. The phase1 SDC remains a
proposal with exactly 18 raw receiving CLEAR cuts, never functional CLEAR or
whole-domain cuts.

All complete CDC/reset, physical, routed timing, hardware and deployment flags
remain false. Source implementation, synthesis, endpoint review and an SRAM
deployment are separate evidence stages.

Run the scope regression with `GW138K_BLE_DDR_CDC_STAGE` and
`GW138K_BLE_DDR_CDC_PROCESS` pointing at a completed sealed candidate:

```sh
python3 projects/138k/push2_workstation/usb_a/sim/test_workstation_ble_ddr_cdc_scope.py
```

Without those variables it checks the exact profile gates and skips the actual
VG tests. The optional actual-VG negatives mutate in-memory parsed objects and
never rewrite the original netlist or SDC. No command in these auditors runs
EDA or operates hardware.
