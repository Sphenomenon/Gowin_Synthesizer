# Selected runtime shared CDC source audit

`workstation_runtime_shared_cdc.py` resolves and structurally checks the shared
constraints that the selected no-CNN runtime actually installs. It does not run
EDA, modify RTL/SDC, program a board or establish physical CDC acceptance.

The default `--precision-profile generic` delegates to the unchanged
`workstation_custom_clocks.audit_shared_cdc()` and its original 157-line scope.
It does not filter missing endpoints or guess a runtime profile from the VG.
The explicit `--precision-profile runtime-no-cnn-v1` requires the prepared
`custom138k-workstation-no-cnn-v1` identity, the exact versioned configuration, a valid historical profile-source digest,
and the exact disabled recognition policy. Unknown profiles, enabled recognition,
configuration drift and malformed historical source identities fail. The prepared
profile digest remains historical provenance: later descriptive edits in the active
root profile do not establish or invalidate the sealed VG by byte equivalence.
The output records both source digests and explicitly declines that root-equivalence
claim.
There is no silent fallback between the two modes.

For the explicit no-CNN profile, the tool reconstructs generic 157 → runtime105
with the existing runtime adapter, then verifies the existing full recognition
retirement metadata byte for byte. Nineteen full-SDC commands retire, seventeen
inside the shared bundle; the retained shared bundle contains 88 commands.
Each retained command must occur exactly once in the sealed SDC and each retired
shared command must be absent. Every non-opaque member of a query union must
resolve independently. Thirteen shared queries inside the opaque DDR PHY remain
explicitly deferred; these are not the count of all opaque full-SDC queries.

The declared source structure contains 43 ordinary first-stage bits, eight Gray
groups/182 first-stage bits, and fourteen held pairs/1308 live payload bits.
The checks include producer identities, clocks, unconditional synchronizer CE,
common CLEAR, unique Q drivers, exact D/shift bit mapping, complete first-Q
consumers and complete payload/Gray source consumer inventories. A named external
DDR-calibrated, PLL-LOCK or HPD producer is an explicit boundary, never an unknown
free signal. The playlist broad wildcards' source/meta/sync overmatch is fully
listed; actual producer FFs and the registered read-MSB alias are independently
declared. Local playlist RAM WRE consumers are explicitly listed and checked
against their source clock. No reviewed source may silently export to a top-level
output.

Two functional special cases have independent Boolean checks: the scanout's
20-bit held request captures only under its existing RTL condition, and the DDR
recovery status pair has the two existing same-domain synchronous-zero AND gates.
The USB defaults source is checked against the existing `!generic_midi || gw25k`
policy rather than a generated LUT/net number. Status cones containing LUT logic
are inventoried without claiming pulse/glitch safety. All 110 retained
reset/primitive pins are resolved and recorded; their full reset semantics remain
separate work.

Example (paths must refer to a completed, sealed prepare/synthesis pair):

```sh
python3 projects/138k/push2_workstation/usb_a/tools/workstation_runtime_shared_cdc.py \
  --project /absolute/selected/workstation/Prj1 \
  --synthesis-evidence /absolute/selected/runtime_synthesis_evidence/process.json \
  --precision-profile runtime-no-cnn-v1 \
  --output /absolute/review/shared-cdc.json
```

The completed synthesis process, original VG, prepared profile and every staged
input are independently hashed before and after. Audit tool/test/document/config
identities are also recorded and checked for drift. The tool's identity includes
the explicit precision profile. No developer cache, historical staging path or
unversioned input is used by the implementation.

The targeted regression always checks default delegation and profile policy. Set
`GW138K_SHARED_CDC_STAGE` and `GW138K_SHARED_CDC_PROCESS` to add the actual sealed
netlist tests; missing variables explicitly skip that class without running EDA.
`GW138K_SHARED_CDC_TEST_EVIDENCE` optionally selects the mutation evidence file.

```sh
python3 projects/138k/push2_workstation/usb_a/sim/test_workstation_runtime_shared_cdc.py
```

The actual-netlist negatives disconnect D/shift, alter clocks/CE/reset, add
asynchronous/enable consumers, hide an empty union member, swap a Gray bit,
disconnect a held capture and corrupt both recovery gates. Separate tests change
the defaults Boolean function and recompute recognition metadata around a relaxed
retained delay; both fail. The mutations are in-memory parsed actual-VG objects,
not deployable VG files. Original inputs are checked again after the suite.

This is an additional source-structure gate, with a deliberately partial scope.
Gray sequence behavior, held stability/handshake behavior, status waveform safety,
all reset assertion/release semantics, tool-time queries, DDR internals, routed
propagation/skew/MTBF, both switched physical clock modes and workstation hardware
acceptance remain separate gates. `constraints_complete`, `physical_cdc_accepted`,
`routed_timing_verified`, `release_ready` and `deployment_allowed` remain false.
The generic checker and accepted production source selections are unchanged.
