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
