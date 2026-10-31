# AE350 cache/PMA probe source candidate C21031D3

This source candidate adds an explicit `cache-pma-v1` standalone program and a
burst-aware isolated PL memory owner. It is prepared with UserCode C21031D3 and
bsram4 transport. It has no synthesis, routed timing, JTAG, SRAM, Flash or board
acceptance; earlier D0 snapshot evidence does not apply to changed inputs.
Production cache remains off. The existing local-memory program is the default.

The old probe observed cache-off and optional PMA configuration but did not read
PMAADDRs or exercise maintenance/cache behavior. The new program reads actual
32KiB I/D geometry and feature CSRs, requires all existing PMACFGs disabled,
saves all16 PMAADDRs, and explicitly attributes an isolated4KiB page plus its
uncached backing alias. It tests dirty writeback, shared-data invalidation,
actual PL instruction fetch returning17 then29 after maintenance, and repeated
uncached MMIO reads. Ordinary terminal paths disable caches and restore PMA;
traps record cause/PC and fail closed through a stackless cleanup. Unsupported
cleanup or a stalled hard-IP operation still requires host timeout/reset.

`firmware/ae350/probes/CACHE_PMA_PROBE.md` records the official manual pages,
pinned Andes/Gowin reference versions, exact attribute encoding, scratch map,
AHB phases/errors, diagnostics and remaining limits. The PMA field definitions
come from pinned Andes-authored references because the included official Gowin
manuals do not document them. No vendor implementation is copied into firmware.

Offline validation completed:

- Actual compiled ELF/ROM runs to PASS in an explicitly abstract cache/PMA
  model, with2308 CCTL commands,17/17/29 instruction observations, cache off and
  all PMA addresses/configuration restored. Firmware4416bytes; conservative
  acyclic stack bound64bytes within the16KiB reserve. Model hits/fills are
  synthetic and provide no hardware performance measurement.
- Seven actual-firmware/model/decoder/disassembly tests cover wrong geometry,
  missing features, active PMA, pre-enabled/mode controls, unsupported CSR,
  ignored enables, ineffective writeback/invalidate, alias and MMIO cache faults,
  stuck PMA, armed terminal trap, exact literal-page call frame/target,
  forbidden CSR, unknown indirect call, dynamic/oversized stack, identity/CRC,
  stale latest snapshots and wrong schema/program.
- Three RTL tests exercise the actual AHB owner, frozen-wrapper top integration,
  masks/alias/write→read forwarding, INCR/WRAP4/8/16/BUSY,64-bit line refill,
  malformed sequences/alignment/size/address/1KiB crossings, two-cycle ERROR,
  reset pending-write cancellation, APB counter write rejection and permanent
  DAC mute/reset. Six representative RTL fault variants are detected.
- `test_current_workstation_sources.py`:17 tests;
  `test_ae350_local_probe.py`:9;
  `test_ae350_banked_gao.py`:9;
  `test_ae350_snapshot_ram.py`:9;
  `test_ae350_snapshot_ram_audit.py`:3; all pass. Verilator lint and diff check pass.
- Explicit D3 prepare v3 passes independent input/ROM/firmware/composition audit:
  inputs SHA256 `043ce96e4cc711cf51e139a8cf9ca879a93ee57204afb6f7f28dfc79569547f4`.
  The failed v1/v2 attempts retained their partial outputs; metadata was initially
  copied under firmware before its exclusive creation. Copy order is corrected.

External evidence is under
`/Users/sphenicidition/.cache/gw138k-task-20261030/ae350-cache-pma-evidence-v1`,
prepare under `ae350-cache-pma-D3-prepare-v3`, and pinned references under
`ae350-cache-pma-reference-v1`. The sealed delivery includes exact source,
prepare, model/raw decoder evidence, test logs and references with complete-file
inventory/hash verification. Generated artifacts are outside Git.

Remaining: new actual synthesis and inferred RAM resource/held-bit/CDC audit,
routed timing and real hard-IP/JTAG/fresh UART+GAO behavior, with rollback bound
to a previous accepted SRAM identity. The structural gate expects the additional
word60 APB counter in this variant, but that expectation is not physical proof.
Only4KiB page behavior is exercised; full32KiB/all-way stress, shared DDR
coherence, real performance and workstation integration are separate work.

## Main integration and independent root checks

Main commit `a5370b2` imports the isolated probe source. The root reran seven actual-firmware/abstract-model tests, three RTL tests, 17 accepted-source tests, nine local-memory, nine banked, nine snapshot and three snapshot-audit tests; all passed. The 296-file author delivery was independently reverified. These checks exercise the actual compiled probe in an abstract cache model, not encrypted hard-IP cache behavior.

A fresh main prepare uses UserCode `C21031D5`, manifest SHA256 `c7eb105fe96ab297a18411032799400cf364f82266d3e806536f3c4173c7610b`: 46 inputs, ten compiled sources, 4,416-byte firmware and 64 KiB ROM. D5 is prepare only and is not queued for physical implementation. The failed D0 GAO route does not provide physical acceptance for this changed program.

All nine complete-workstation source locks pass after refreshing the changed `build.py` CLI hash. Only the two profiles with a closed full-firmware inventory add the exact three new standalone probe files. No old source hash, reference firmware identity or ROM96 decoder was substituted. Fresh ROM96 candidate `b36c837269036d3e` passes its verifier; all 637 staged inputs and 283 enabled inputs remain byte-identical to the earlier `9d02b8107b256773` candidate. The standalone files affect source provenance without entering that workstation build.

The [main machine record](workstation_task_20261030/ae350_cache_pma_main.json) binds 29 source snapshots and 1,200 external records. Immutable evidence: `/Users/sphenicidition/.cache/gw138k-task-20261030/ae350-cache-pma-main-parent-v1`; seal SHA256 `aa22fb17b86e18d54b4c07d52610d7f88b78ee7bfb7a62caa6acc70f85b03584`. Recheck with its `verify.py`. Production cache remains off; full cache capacity, shared DDR coherence, synthesis, physical timing and hardware behavior remain unverified.
