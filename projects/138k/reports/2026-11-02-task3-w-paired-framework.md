# Task3 W paired framework, 2026-11-02

W now has an explicit paired role with real CNN work and a single 60-second
recording store. Its source composition includes the shared LCD/F808 binding;
complete board validation is pending. No board, SRAM, JTAG or Flash was operated.

| Boundary | Actual implementation |
|---|---|
| Native memory | `workstation_task3_w_paired`: one `workstation_media_memory`, real CNN stream/task on owner5, maintained delay on owner6, one raw recording store on owner8 |
| CNN | Real deferred-seal `workstation_task3_cnn_stream_w`; existing 4 Hz guidance geometry; SIGNAL and CQT coefficient BSRAM parameters selected explicitly |
| Recording authority | Existing full HCI/GATT physical engine and CPU business owner own the same object, CRC, tasks and download; no R00 or second backend |
| Recording samples | Actual M final serializer observation → bounded M exporter → typed ch4/5 arm/frames/ACK → W real ingress → existing engine/raw store |
| Actual REC_START | CPU/BLE request → bounded source gate in the same `ble_protocol_command` → ch9 demand → M final ARM decision → actual observed source → original held command to the same recording engine |
| Release | Frozen/error object withdraws ch9 demand and cancels M tap; acquisition timeout returns the engine's actual source failure and cannot arm later |
| Phone playback | Existing W PCM1/F806 and clock/F803 commands → held remote proxy → M existing PCM/clock authority; decoded PCM is pre-master; M applies D effects and gain and schedules final output |
| Source status | Actual HCI epoch/generation/ready plus backend/model readiness; current status must be sent before phone ARM |
| Reboot fencing | Phone retains explicit common identity; recording has its own M generation, mapped to a W-root monotonic ingress generation, including independent M reboot |

The physical object now exports its continuous empty state; a seal snapshot or
raw-store readiness is insufficient. The opt-in output passes through four
maintained HCI layers. Macro-off preprocessing against HEAD was token-identical
for all four. Busy/nonempty objects reject ARM without blocking shared receive.
Invalid format/sequence, overflow, storage fault, timeout, cancellation, link
loss and PANIC revoke only their branch. M physical samples have no ready input.

The source gate waits at most 2,500,000 control clocks (50 ms at 50 MHz).
This is an acquisition failure bound, not a measured control-to-sound latency.
The paired firmware has one temporary, hash-locked source adaptation deferring
REC_START's preliminary source-good rejection to the actual engine after
acquisition. Original C bytes and old source review are unchanged. The adapter
checks original `e7d4b9dc032d2a4e494baf90364c13230f3550627d8658751c1ecd910ef15122`,
selected `c8fe79dd01ea477d39ecd9ea2fa631501030e25eed1c5d75786e749fdf7bad19`,
unique anchor and exact inverse. The paired actual ELF/stack/callback audit
passed with 167 reviewed JALR sites. The old default media ELF, BIN and boot ROM
were rebuilt with the same compiler and are byte-identical to W media v13.

Validation receipts under `/Users/sphenicidition/.cache/gw138k-task3-20261101/`:

- `paired-business-endpoints-v6/verification.json`: 89 checks, 21 final tap
  frames, both original remote APB targets, actual status-before-ARM, malformed
  padding, busy-object rejection, cancellation, phone timeout, independent M
  reboot mapping, source acquisition timeout, no late arm, actual REC_START
  demand, four frames captured and sealed by the real maintained engine, and
  automatic terminal cancellation. The small 32-frame simulation RAM is an
  oracle; production W selects the unique 2,880,000-frame raw DDR store.
- `w-paired-media-firmware-v2/verification.json` and
  `media_callgraph_verification.json`: actual paired ELF build, source adaptation,
  callback tables/sites and stack checks. Compiler is the same xPack 15.2 tool
  used by the W media v13 comparison.
- `w-default-media-firmware-preservation-v2/default_preservation.json`:
  default boot ROM `b69c202a59e583d3c231df76a5fc4cb16d4ee59eb159e63bfae55c60fa771f90`,
  ELF `84df1ee82770fe05160c61dbb33aefa2ce616bbf1da17464355107ccd8021ce2`,
  BIN `29b60700043397cafe50baa84410bd40b22c61438c8215d1298816512fad4d77`;
  all three byte-identical to the frozen comparison outputs.
- `w-paired-common-source-v1/verification.json`: exact common-link then W-role
  inverse restores the locked parent. Wrong inverse order and common/role/padding
  mutations are rejected. No maintained raw top is consulted when proving an
  already copied stage.
- `w-paired-classic-dispatch-v1/verification.json`: 56 legacy selection cases
  retain their previous results; paired W is an explicit dispatch and cannot
  reuse the old media identity. Actual paired and old media firmware verification
  both pass.
- `w-paired-native-cnn-selection-v1/verification.json` and
  `w-paired-native-cnn-prepare-v1/native_prepare_verification.json`: strict native
  input selection, four drift/policy controls, and actual complete resource-parent
  preparation pass. Both source audit and metadata bind the resulting file hashes.
- `w-default-resource-builder-preservation-v1/verification.json` is an earlier
  diagnostic: both builders rejected the native-parameter link at the original
  literal anchor, with 448 identical files before rejection. That broken default
  entry was deliberately fixed after the required clean-checkout regression
  exposed it. This failure-preservation receipt is superseded by the next one.
- `default-resource-native-selection-v1/verification.json`: the default resource
  entry now selects the same strict native transform only when both maintained
  link/task SHA-256 values match exactly, and records
  `exact_maintained_native_parameter_inputs` as its origin. Explicit paired
  selection retains its separate origin and strict input check. All 450 native
  stage files match between automatic and explicit selection. The legacy literal
  fixture retains all 450 stage files and metadata byte-for-byte against the old
  builder; four native drift cases and legacy anchor drift are rejected.
- `default-resource-native-clean-prepare-v1.log`: required
  `GW138K_VERIFY_CLEAN_PREPARE=1` baseline suite passes all 23 tests, including
  clean reconstruction of accepted full83, timing85 and the default resource
  entry without private historical inputs. This used the same xPack 15.2 tool path.
- `w-paired-ae350-memory-selection-v1/verification.json`: the paired remote-PCM,
  sole recording/raw-store, native CNN and closed LCD budget configuration
  explicitly selects ILM/DLM 64 KiB and physical ROM 128 KiB. All 17 other
  registry selections retain the previous result; 16 individual paired policy
  mutations are rejected, including a smaller ROM under the paired identity.
- `w-paired-hci-scope-fixture-v1/verification.json`: complete actual staged
  preprocessing includes the four HCI layers, idle/source-demand ports and real
  recording source gate, plus the full CNN parameter chain. Eight wiring and
  four duplicate-compilation mutations are rejected. The failed original v2
  stage remains intact; the fix was checked in a separate cache fixture.
- `w-paired-classic-source-verify-v3fix/verification.json`: the original v3 stage
  passes the complete Classic source selection and verification with the CDC
  projection fix, including actual full preprocessing and installed SDC. Six
  legacy positive/negative cases match the old verifier; four paired marker
  and budget mutations are rejected. This check leaves the failed v3 stage
  unchanged and writes its receipt separately.

The paired caller opts into
`build_resource_rework.prepare(native_cnn_parameters=True)` together with the
resource-timing policy. It locks the maintained link/task inputs, adapts only
the staged native link default declarations to 44,100 samples, 8 frames,
22,050/4 CQT hop, 16 columns and coarse guidance, then retains the original
diagnostic CDC transform. Input, intermediate and output SHA-256 values are
recorded. W's stream explicitly selects the same geometry; task-owner and link
parameter forwarding remain intact through the actual pipeline. Exact maintained
native input recognition also repairs the default resource entry; an unknown
native input is rejected. Legacy literal inputs retain their original transform.
No CNN accuracy, model availability or physical resource result is inferred from
these source checks.

Actual preparation exposed a macro-scope integration error: the board provider
defined the paired role only while including the top, whereas the four HCI
files were standalone compilation units. The new explicit
`workstation_task3_w_paired_hci.sv` scopes the same macro around the four canonical
staged HCI/business inputs. Only the paired helper disables their four standalone
FileList entries and records the unchanged canonical source hashes. Both the
wrapper and actual module uniqueness are checked. Old providers and macro-off
behavior remain separate; the source verifier was not weakened to accept a
missing recording chain.

The subsequent v3 check also exposed a verification composition error: projecting
the Classic CDC bundle through the full W role adapter appended all media-owned
constraints and incorrectly treated those extra lines as Classic bundle members.
The paired Classic path now strictly removes the final common marker, then checks
only the existing Classic bundle after the same role selector transformation.
The full W media constraints retain their separate inverse/roundtrip proof.
No clock, held-payload budget or exception was relaxed.

The exact staged top adapter retains parent top
`4b4a99f674a7033b032a3e82b98e553d7d7675689627ca4fb0cebf9746738d0f`,
checks its reference SHA and forward/inverse round trip. SDC first applies the
old reviewed media retirement, then rebinds CNN task hierarchy and the original
PCM APB budgets to their actual paired hierarchy; it retires only absent local
PCM/clock/F807 selectors. Surviving clocks and budgets are not relaxed.

The clean paired W v4 candidate is
`custom138k-workstation-task3-w-paired-v1-dbd0aa27d30ff935` in
`w-paired-board-prepare-v4`. Its source lock contains 1,023 entries and its actual
enabled compilation list contains 196 inputs. Independent `profile.verify` and
all eight source mutations pass in
`w-paired-v4-independent-review-v1/verification.json`; this receipt is 5,930 bytes,
references the original firmware metadata by hash, and does not alter the
candidate. The independently inspected actual source has one memory fabric,
one raw store, the real CNN stream/task/pipeline, all four scoped HCI layers,
the continuous idle output and the real recording source gate.

| v4 identity | SHA-256 / value |
|---|---|
| Profile configuration file | `8157194b7dcc291b4eb70a09daa336aabd27792be71973d060e437ae4e6b9642` |
| Profile artifact | `43282989327c51d444716e22956a72b084fb1948022aff5c571d8607925847f3` |
| Actual preprocessed source | `a489674750d47d132af6b678ed53c68e58ace071ee9d4c2d9d7628414a87617f` |
| Paired firmware ELF | `067b15a0d8d0f22bdf75bc21ff8e0205d341a47b3487f00be8dfec5917324df4` |
| Paired firmware binary | `73a8cc93a78a0a84ebcab50fe7fac040b3ee70a8d3928fcf8288e0bb1f67da8b` |
| Installed boot ROM | `d5082e31e1845268b80a7362c0dfb81f0e9dbd5e569fa782782929f44f27a719` |
| Firmware storage | ILM/DLM 64 KiB each, physical boot ROM 128 KiB, binary 90,416 bytes; 167 reviewed JALR sites |
| Bitstream | none from prepare; no physical acceptance or deployment |

This v4 independent receipt records the source lock at verification time. The
subsequent intentional default-builder repair requires a new locked candidate;
it does not relabel v4 or imply a fresh synthesis of that new candidate. Actual
synthesis/public-gate outcomes and the later candidate comparison belong to the
[combined task3 record](../task3.md).

Remaining: complete routed STA/PLL/CDC and physical resource acceptance;
LCD electrical/throughput/latency
and congestion measurements; physical HCI/SBC streaming, M D/DAC behavior and
control-to-sound latency; actual 60-second DDR recording and reliable BLE
download. Owner6 remains connected but W heavy effect execution is not claimed.
Bluetooth/LCD audio suitability remains a measurement decision. Business link
budget defaults closed. Existing W demo/media/task2 candidates remain rollback
sources, and the connected board assigned to another branch was untouched.

## Paired W retained CDC and SDC iteration

The subsequent actual v4 synthesis exposed old DEMO assumptions in the public
audit: paired W is headless, its display mailbox is absent, and PC/health
mailboxes use the real startup root rather than the old constant-reset policy.
`workstation_task3_w_paired_cdc_audit.py` now selects only that explicit W
composition. The shared DEMO boundary, native-protocol and performance-reset
auditors remain byte-for-byte unchanged.

Actual synthesis proves the retained PC 8-bit and health 32-bit held payloads,
the three-stage request capture and two-stage return ACK, no overwrite while
awaiting ACK, exact payload mapping and complete first-stage/payload fanout.
The 35-bit startup proof is reused with the exact W source/provider selection.
PC/health releases fill on three receiving edges; APB's real source release
is merged into `u_task3_pair_link/config_cdc/p_release`, with the original
root-and-CPU assertion preserved. The shared PLL/control second release has
14,361 FF, 245 primitive and three output endpoints; its complete closure is
hash-locked, and it has no early PC/health functional consumer. This narrow
proof does not certify reset semantics for those other clients.

The paired-only SDC adaptation additionally retires absent media-stop source
registers, serializer sequence, local rate and unused epoch state. Both retained
media-stop first D inputs are physically constant zero. Four actual startup
register groups use `DFFCE/CLEAR`, so their old `/RESET` selectors are rebound
to those exact live `/CLEAR` pins. CNN's old `model_memory_meta` is physically
merged into `task_service/backend_meta`; its complete first-Q closure contains
only the live `cnn/model_memory_ready/D`, with the same reset and 50 MHz clock.
No clock or delay budget changes. Old W/DEMO profiles do not opt into this
adapter, and the original v4 installed SDC is left intact.

`w-paired-cdc-retirement-v1/verification.json` records six actual-netlist test
groups and 31 rejected destructive mutations, with original candidate hashes
unchanged. The separate `proposed_W.sdc` fixture passes all visible selectors,
retired/rebound endpoint resolution and 28 exact retained mailbox/APB/heartbeat
constraints. Payload setup remains 13.020/20.000 ns, second stages 2.000 ns;
later-stage false paths, whole-clock cuts and weaker overriding bounds fail.
The fixture SHA-256 is
`1af567d969001840675e1d076d6f8817ce40428d7d6af8dc9f54c726065d26ce`.
These are synthesis/graph checks over frozen v4 plus a separately prepared SDC
fixture. A new locked candidate and its synthesis/public audit remain required;
routed CDC, STA, physical timing, metastability MTBF, measured latency and all
hardware acceptance are pending. No board operation occurred.

## Actual v6 synthesis and public audit

The new W candidate is
`custom138k-workstation-task3-w-paired-v1-3d33fb0c0c41caec`.
Fresh synthesis completed with 46,554 registers, 59,478 LUTs and 308 synthesis
BSRAM equivalents. All 196 enabled nonconstraint inputs remain byte-identical
to frozen v4; the only changed enabled input is the reviewed SDC. The actual
v6 public synthesis-structure audit passes 17/17 gates, including the retained
W CDC boundaries and exact constraint retirement/rebinding. This supersedes
the projected-fixture check only for that synthesis-structure scope.

The 50 MHz and 76.8 MHz synthesis estimates are 48.889 and 72.616 MHz, both
below requirement. Whole-source CDC, routed PLL/STA/resources, electrical
acceptance and hardware/deployment remain false; bitstream and physical
latencies remain null. The paired report records source identities, hashes,
negative controls and the still-failing M full TF CDC gate:
[v6 combined audit evidence](../push2_workstation/usb_a/reports/DUAL138K_TASK3_PAIRED_AUDIT_ALIGNMENT_20261102.json).
