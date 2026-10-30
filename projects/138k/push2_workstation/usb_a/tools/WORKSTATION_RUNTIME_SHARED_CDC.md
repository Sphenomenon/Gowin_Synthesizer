# Selected runtime shared CDC source audit

`workstation_runtime_shared_cdc.py` resolves and structurally checks the shared
constraints that the explicitly selected no-CNN or R00 runtime installs. It does not run
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
There is no silent fallback between the modes.

The separate `--precision-profile runtime-r00-v1` requires the prepared
`custom138k-workstation-r00-v1` identity, the exact current R00 configuration,
the same disabled recognition policy and exact `native_owner8_pcm_ddr_r00_v1`
recording metadata. Its supported configuration has canonical JSON SHA-256
`b5c30ab0d1d4ec9b3470599f390596f1cf618c52a20b643522b19ed7e3746313`.
The public audit verifies the completed synthesis seal, all staged inputs and
VG before and after, and verifies the selected owner8 address-map provenance.
The profile-source digest remains sealed historical provenance, not a claim
that later descriptive root profile bytes equal the prepared version.
Additional native recording CDC is explicitly outside this shared result:
`u_recording/pcm_cdc`, `commands`, `seal_cdc`, `service`, `native_commit` and
`u_video/u_arbiter/g_recording/u_core` need their own checks. Recording, whole
workstation, complete reset, physical timing and deployment are not accepted.

For either explicit profile, the tool reconstructs generic 157 → runtime105
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

R00 has a separate declaration for three actual status net aliases:
`bist_done`, `bist_failed` and `u_video/front_valid`, in place of the old
`u_video/bist_done`, `u_video/bist_failed` and `u_video/front_valid_Z`.
The audited RTL basis is `rtl/workstation/workstation_hdmi_display.sv`:
`u_bist.done/failed`, `u_scanout.front_valid`, the exact `memory_status[7:0]`
concatenation and the `flags_meta` capture are checked against the sealed
source. The actual VG must keep the corresponding unique FF Q producer and
memory-domain source clock. All first/second stages and complete first-Q
fanouts remain checked; aliases are not optional endpoints. Other no-CNN
status declarations retain their original behavior.

The b9a2 full SDC retains the four peripheral LCD commands from
`workstation_board_peripherals.LCD_SDC` and its generated clock. The four CDC
commands are outside the shared 88-line bundle; this result does not accept
their endpoint structure or physical behavior. The full input seal preserves
those bytes. A future LCD-off configuration cannot inherit this result: its
different configuration must receive an explicit constraint retirement and
topology review. No LCD selector or endpoint is silently removed here.

The distinct `--precision-profile runtime-r00-no-local-panel-v1` requires
`custom138k-workstation-r00-no-local-panel-v1` and source
`boards/custom_138k/workstation_profile_r00_no_local_panel_v1.json`. Its exact
configuration is R00 plus `local_panel_policy=disabled_local_lcd_touch_v1`,
canonical configuration SHA-256
`fe57acb99ab96c773148a10bd41401eaa55ca069f2ff9d1def1daa254dd5d241`.
The prepared descriptor digest must be 64 lowercase hexadecimal characters;
its changing source-lock bytes are not pinned to the later active descriptor.
Disabled recognition and owner8 recording metadata remain exact requirements.

This separate mode requires the retired LCD commands/clock to be absent from
the full SDC and LCD cells to be absent from the VG. It retains the same 88
shared commands because the four peripheral LCD CDC commands were never inside
that bundle. It does not infer a profile or remove a failed query. Its public
entry additionally requires the explicit disabled-panel clock audit, which owns
the 12-clock prefix, six-PLL inventory and LCD/touch retirement checks. The clock
adapter is a separate prerequisite; this patch does not change it.
The no-panel mode must pass its own completed synthesis/input/VG seal and every
retained source structure check. The b9a2 LCD-on result is not inherited. Until
that new VG exists, policy fixtures and old-candidate refusal tests establish
only the mode selection and refusal rules, not actual no-panel acceptance.

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

The R00 regression is separate and never upgrades the old 525 result. Set
`GW138K_R00_SHARED_CDC_STAGE` and `GW138K_R00_SHARED_CDC_PROCESS` to a completed
R00 synthesis pair, optionally adding `GW138K_R00_SHARED_CDC_TEST_EVIDENCE` and
`GW138K_R00_SHARED_CDC_POSITIVE_EVIDENCE` for the actual reports. Its additional
negative controls target the three declared status aliases, registered producer
clock/identity and complete first-Q fanout.

```sh
python3 projects/138k/push2_workstation/usb_a/sim/test_workstation_runtime_r00_shared_cdc.py
```

The no-panel policy/old-candidate refusal regression is separate. Optional
`GW138K_OLD_R00_STAGE` and `GW138K_OLD_R00_PROCESS` select a sealed old R00 pair
for identity refusal; the test does not relabel or modify that candidate.

```sh
python3 projects/138k/push2_workstation/usb_a/sim/test_workstation_no_local_panel_precision.py
```

This is an additional source-structure gate, with a deliberately partial scope.
Gray sequence behavior, held stability/handshake behavior, status waveform safety,
all reset assertion/release semantics, tool-time queries, DDR internals, routed
propagation/skew/MTBF, both switched physical clock modes and workstation hardware
acceptance remain separate gates. `constraints_complete`, `physical_cdc_accepted`,
`routed_timing_verified`, `release_ready` and `deployment_allowed` remain false.
The generic checker and accepted production source selections are unchanged.

The optional `--usb2-owner-reset` adds the separate
[USB2 owner reset-chain review](WORKSTATION_USB2_OWNER_RESET.md) only with
`--precision-profile runtime-no-cnn-v1`. The default scope is unchanged.
The independent reset CLI also accepts an explicitly selected R00 candidate;
that result does not accept R00 recording or whole-workstation shared CDC.
The R00 shared precision profile likewise excludes this optional reset flag;
use the independent reset CLI to examine that separate boundary.
