# BLE raw DDR staged adaptation, 2026-10-30

The default-off adaptation is implemented and passed offline transaction,
protocol, source-identity and tamper regressions. It preserves BLE ownership of
objects/tasks/CRC/codec/wire data while replacing only opted-in recorder raw PCM
storage with the reviewed DDR store. Accepted profiles, 25K originals, frozen
inputs and vendor bytes are unchanged. Native top/map/mux/profile integration is
separate work.

Candidate identity: `native-ble-raw-ddr-adaptation-v1-fcd56b001b5d87c9`.
Source-set SHA-256:
`fcd56b001b5d87c9db328b77b4e454247c1cb28f91d2adca77e625513a884c0c`.
The compact machine result is
[`ble_raw_ddr_adaptation_20261030.json`](ble_raw_ddr_adaptation_20261030.json).
The full local evidence is
`/Users/sphenicidition/.cache/gw138k-task-20261030/ble-ddr-adaptation-regression-final-v4/verification.json`,
SHA-256 `dd4195a665d13e1416cdb68e5d4db76c0de10180a86ea7af34cffe9b93f1186f`.

The raw-store lock is
`422a1bb4c3b0cf842b416b65f714d023c65b270d0fa5219f9adec1c72d290ede`;
its contract lock is
`86dd2b30edf3772dd637d2766d1b89120c1c4ef2216aa87c744ee76414519763`.
This includes the registered native protocol-fault output and the independently
reviewed generation/held-valid fix. The staged recorder SHA-256 is
`9de775e873895153059513bb85eb2e01b2bbcacac9d0f00c3570758c648fabd4`.
All five input/output identities, the checked upstream closure, generator hash,
protected encoder/transfer-bank/wire-message hashes and timeout policy are in the
machine result. No bitstream was produced by this stage.

`prepare(root, stage, enabled=True)` adds checked ports through the five existing
layers after normal BLE preparation and native-wrapper copying. It checks all
inputs and complete output identities before writing. `verify_prepared` checks
the closure again at profile publication, including rejection of changed output
bytes accompanied by forged output hashes. Opt-in needs external PCM, external
seal, capacity no greater than 16,384 frames and an explicitly reviewed drain
budget. The production budget is 5,000,000 control cycles (100 ms at 50 MHz);
legacy RAM retains 64 cycles. Raw native command/read budgets remain 10,000
memory cycles each. Full behavior and the temporary overlay exit plan are in
[`WORKSTATION_BLE_RAW_DDR_ADAPTATION.md`](../rtl/bluetooth/WORKSTATION_BLE_RAW_DDR_ADAPTATION.md).

The final regression passed:

- 24 real owner/store/native-DDR transactions per memory-clock configuration;
  asynchronous memory: 472,541 checks; 100 MHz memory: 470,038 checks.
- 17,427 wire bytes per configuration compared against the original RAM recorder,
  including RAW, Rice and second-order encoding, object/block/frame CRC, both
  cache banks, 8,112-byte aligned download and the worst aligned protocol start
  at byte 28 requiring 255 padded native read beats.
- All 1–7 frame partial final beats; remote STOP at six CRC phases; local seal
  drain; pre-ready START with no object/task allocation; overflow without audio
  backpressure; disconnect/late old fetch and reconnect; explicit replay object
  identity; timeout with stopped memory and late cleanup; accepted CLEAR after
  disconnect/disable; and three exact final-drain-edge source-loss cases.
- Six real framed protocol/request-cache cases and three staged five-layer seal
  cases with the actual raw store. Only link state and the chain's command
  injection are forced.
- Six behavioral negative controls: early READY, timeout resurrection, source
  failure overwritten by finalization, stale cache authorization, CLEAR tied to
  caller lifetime, and a missing raw-close connection in one hierarchy layer.
  The timeout mutant removes both intentionally redundant terminal guards.
- Twenty-one source/output/evidence tamper controls, including all five source
  identities and output identities, forged output evidence, missing inventory,
  anchor/protected-code drift, raw-store/contract drift and failure before stage
  publication. All 27 negative controls were rejected.
- Default-off preparation changed no bytes; default RAM live PCM regression
  passed; all source inputs remained unchanged during verification.

The unchanged accepted-source regression also passed 17 tests, and the existing
BLE regression passed eight tests including the original UART/H5 patch, GATT,
request cache, live PCM and wire checks. Commands:

```
python3 sim/usb2/run_workstation_ble_raw_ddr.py --output /absolute/new/output
python3 sim/test_current_workstation_sources.py
python3 sim/test_workstation_bluetooth.py
```

For this isolated development checkout, the first command used
`--raw-source-root /Users/sphenicidition/.cache/gw138k-task-20261030/ble-raw-ddr-independent-review-v1/tree/projects/138k/push2_workstation/usb_a`
to consume the sealed component without copying uncommitted parallel work into
this branch. The normal default consumes the integrated `usb_a` source tree.

Validation is offline only. Physical RAM mapping, reset/CDC extraction, routed
timing, synthesis, P&R, full native candidate prepare, board acceptance and
SRAM/Flash deployment remain false/unclaimed here. The simulation uses a
50,000-cycle endpoint budget to make timeout tests finite; it does not reduce the
5,000,000-cycle production policy. Pending storage/switch commands may wait;
audio capture events never wait or retry.

Rollback is to omit the adaptation call and keep the default parameter 0. No
accepted release identity or deployment is reused. Any integration selecting
this candidate must retain its own configuration/source hashes and later-stage
validation evidence before making hardware acceptance claims.
