# Explicit Chorus narrowing candidate CDC review

`runtime-r00-no-local-panel-ble-ddr-chorus-v1` selects only candidate
`custom138k-workstation-r00-no-local-panel-v1-6b9610324164f0c9`, input identity
`6b9610324164f0c96ff4acf36c15190b627b4848f6d79a5b6a1ddf1e37e94a13`.
It retains the prefix counter and registered TF publisher and adds the checked
`narrow_exact_rate_delay_v1` Chorus provenance. The old serial and c7 prefix
source/endpoint scopes keep their existing identities and selection behavior.
The c7 source and endpoint modules remain byte-identical. No old candidate
acceptance authorizes this new candidate.

The source gate verifies all 596 staged file hashes, the integration/prepared
maps, all 269 enabled identities, actual GPRJ order and input bytes, disabled
serial/enabled native declarations and counter provenance. It checks maintained
business/counter/TF/Chorus source hashes, the address map and BLE adaptation,
and requires exact Chorus provenance in maintained, staged, prepared and
integration sources. Chorus evidence records zero added clock latency and
false physical timing/hardware inheritance. The old business helper is reused
only for metadata validation; its compilation and mapped closure tables are
never applied to this scope. Historical profile hashes remain provenance.

The new endpoint module binds only completed VG SHA-256
`2cfe81e54a9257d212f4b54cecac56853a50e969dbf532d6857d45ce8fe316c8`.
All 13 phase1 and 42 raw source groups were independently extracted from their
declared producer registers, including every D/CE/CLEAR, opaque primitive and
top output endpoint. These full closures, source registers, combinational cell
counts, raw live bitmaps and the shared seal reset alias equal the c7 results.
The new table is separately bound to the actual new VG; there is no table
fallback, endpoint filtering or producer inference from receiving D.

Shared video status has an actual naming change: the new VG uses
`u_video/front_valid_Z`, while c7 uses `u_video/front_valid`. Only the new scope
selects its independently verified spelling. The unique declared
`u_video/u_scanout/front_valid_s0` producer Q is checked against
`flags_meta[3]/D`, with source clock `memory_clk` and receiving clock `clk_50m`.
The matching serial spelling does not confer serial candidate acceptance.

Public shared, USB2 owner reset, phase1 and raw inventory APIs/CLIs require
this scope explicitly. Shared retains all 88 installed lines; USB2 retains
three receiving CLEAR pins and complete downstream fanout; phase1 retains
425 FFs, 42 Gray first bits and 82 held payload bits; raw retains 13 ordinary
pairs, 50 Gray bits and 528 logical/524 mapped payload FFs. The generic clock
and strict `paired-nextq-v2` PCM audits also bind the completed synthesis
identity. Public auditors hash their source dependencies and recheck the
fixed source/synthesis inputs before and after review. No SDC is changed or
installed; phase1 output remains a proposal.

Run `sim/test_workstation_ble_ddr_chorus_cdc_scope.py` with explicit
`GW138K_CHORUS_CDC_STAGE`, `GW138K_CHORUS_CDC_PROCESS` and optional
`GW138K_CHORUS_CDC_TEST_EVIDENCE`. Without them, immutable stage/VG classes
skip without preparation or EDA. Negative controls alter only in-memory
metadata or parsed netlists. They cover every maintained source hash, input
selection/order/maps, Chorus provenance, candidate separation, raw/phase1
producer/receiving/fanout changes and the shared video producer.

This review does not close whole-workstation CDC/reset, physical bit flight,
MTBF, held payload capture, RAM ownership, routed timing or hardware gaps.
The missing seal result-code bits remain unaccepted as constants, aliases or
a complete handshake proof. Physical, hardware, deployment and release flags
remain false. TF-control CDC has its own separately reviewed scope and does
not inherit acceptance from these six audit categories.
