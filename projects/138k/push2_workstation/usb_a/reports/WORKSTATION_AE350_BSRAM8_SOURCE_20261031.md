# AE350 bsram8 source candidate C21031D4

This explicit candidate reduces the registered GAO bus from704 to448bits while
retaining all64 diagnostic words and the same canonical RAM snapshot/UART
publisher. It follows D0's failed GAO routing attempt, reported by the root task
as PR0009/one unrouted GAO design connection. Reduced width is a routing
experiment; no new EDA, JTAG, SRAM, Flash or board acceptance is claimed here.

Select `--ae350-local-memory-probe --ae350-probe-gao bsram8`. The default program
remains `local-memory`; cache-pma-v1 remains restricted to its independent
bsram4 candidate. Full64/banked4/bsram4 defaults and schemas are retained.

The maintained snapshot module now has an explicit PAGE_WORDS parameter,
default16. The8-word configuration exports8 ordered pages×4cycles per page,
new schema A1386404,256 data bits plus192 metadata bits. Page0 preparation uses
256FF bits and next-page prefetch128, compared with512/384 in bsram4. The same
8×16-bit synchronous RAM lanes and128-bit read bus serve two groups per narrow
page; UART waits for tagged data within one32-clock sweep and never steals a
read cycle. There is no second wide frozen snapshot. The one-edge pclk held
capture,16-group inactive-bank copy, atomic publication, frozen IO/health,
timeout/old-bank flags and DAC safety remain covered by the consumer oracle.

`rtl/probe/AE350_BSRAM8_GAO_CONTRACT.md` specifies the new geometry, metadata,
read schedule, freshness and expected netlist structure. The separate decoder
requires explicit448-bit/8-page manifest geometry and rejects old schemas.

Validated source/prepare stages:

- Nine narrow RTL tests cover actual frozen-wrapper top wiring/448 registered
  fields/all64 words/DAC safety, end-to-end matching UART/GAO at baud divisors1
  and4, native GW5A synchronous primitive, local reset, initial timeout/recovery,
  stale old-bank timeout, common reset, and three rejected protocol mutants.
  The seven positive scenarios each produce three complete CRC-valid UART
  frames and matching complete eight-page observations. Data is an RTL fixture,
  not an actual CPU/board capture.
- Six independent decoder tests reject missing/out-of-order/unstable pages,
  metadata drift, unknown/latest partial tails, stale flags, reset context mix,
  identity/schema/geometry/radix/bit-column/legacy-width substitutions.
- Two structural fixture tests plus eight negative variants cover448 actual top
  FFs,1858 held bits,8 native lanes,128 read bits reaching GAO and UART, held
  capture reaching RAM,256/128/32bit caches and unchanged CDC constraints.
  The1100 reference-register limit is a gate expectation, not an actual count.
- Eight prepared-input mutations are rejected even when the modified file's
  hash is refreshed: geometry/mode/program/macro, decoder inventory, compiled
  closure, extra TCL source and malformed native RAM CDC target.
- Existing bsram4:9 tests, banked4:9, full64:5, current sources:17,
  snapshot structure:3 and cache owner/top:3 pass. Verilator lint passes for
  both PAGE_WORDS8 and16, without warning suppressions; diff check passes.

Final prepare is
`/Users/sphenicidition/.cache/gw138k-task-20261030/ae350-bsram8-D4-prepare-v3`,
inputs SHA256 `e9716f07e4510771834bdd12fcd38a2c1ac29be6fbaf304a605e366237fab34f`.
It explicitly uses xPack GCC15.2.0, the same compiler as D0; actual ELF/bin/ROM
hashes each match D0 prepare-v2 exactly. Earlier v1/v2 used the host's default
GCC16 and are retained as nonaccepted preparation attempts. They are not the
same-firmware comparison inputs. No frozen baseline or old prepared candidate
has been modified.

Raw narrow evidence: `ae350-bsram8-rtl-evidence-v2`; final test logs and prepared
negative controls: `ae350-bsram8-checks-v1`, under the same external cache root.
A sealed delivery includes exact source, prepare, raw/decoded evidence and
strict complete-file inventory/hash verification. Generated files stay outside
Git. Root owns new actual synthesis/resource/CDC/PLL/routed timing validation,
JTAG identity and any explicitly authorized deployment/rollback. The cache/PMA
probe is a separate subsequent physical experiment.

## Main integration

Main `fcbd008` imports the explicit bsram8 mode. The root independently verified the complete 317-file author delivery and reran nine narrow RTL, six decoder, two audit-fixture, 17 accepted-source, nine legacy bsram4 and three legacy RAM-audit tests; all passed. The root refreshed only the changed `build.py` source hash in nine workstation profiles, and all nine source locks pass. No workstation source selection changed.

Fresh main prepare `C21031D6` has 46 inputs / nine compiled sources and manifest SHA256 recorded in the [main machine record](workstation_task_20261030/ae350_bsram8_main.json). Its ELF, BIN and ROM bytes each match frozen D0 exactly. D6 is prepare only. Separately, the actual D4 runner uses the immutable author prepare-v3 and the shared EDA lock; its future result must be recorded under D4, with fresh actual-netlist, routed timing and hardware evidence.

Immutable main evidence is `/Users/sphenicidition/.cache/gw138k-task-20261030/ae350-bsram8-main-parent-v1`, with 27 source snapshots and 372 external records. Seal SHA256: `005928abaf91e5ac7e2c7d426a72006322dc325c4b1b4a72344abf229b86c70e`. Its `verify.py` rechecks these identities; no actual synthesis, physical or hardware acceptance is claimed by this source stage.
