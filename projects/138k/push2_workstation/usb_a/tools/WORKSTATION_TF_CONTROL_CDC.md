# TF control snapshot audit: explicit c7 scope

`workstation_tf_control_cdc.py` is a read-only structural and Boolean audit of
`runtime-r00-no-local-panel-tf-control-v1`. It accepts only candidate
`custom138k-workstation-r00-no-local-panel-v1-c7d66b419868f7f4`, actual synthesis
VG `8c5d1e5a30baad7a7e4cd705cfdcf4fcc301369bcb6c69d78f9a7f47c10acb2c`.
It rechecks the c7 policy's 593 staged inputs, 269 enabled inputs and order,
the completed synthesis process seal, maintained and staged TF source bytes,
and the actual imported first-party helper closure before and after auditing.
It neither builds RTL nor modifies the VG, SDC or a board. A different candidate,
including the later Chorus narrowing candidate, requires its own explicit
review and fresh endpoint identity; matching counts do not extend this scope.

The maintained source hashes are:

| Source | SHA-256 |
| --- | --- |
| `rtl/tf_audio/workstation_tf_frame_bridge.sv` | `eb5895b975dc699178a6e451f2f05d481f63424848ebe153c1402a21a63baf31` |
| `rtl/tf_audio/workstation_tf_runtime_service.sv` | `debe8ca8c0515ea0ef5b1c7c45c9835373a4720731df0cef97f11daddb467612` |

## Registered single-bit contracts

The producer is declared by its actual FF identity before receiver D is checked.
No producer is inferred from the receiver or accepted by a name prefix. The
seven direct registered-Q contracts are:

| Declared producer below `u_tf_audio/` | First / second below the same scope | Source → receiver clock |
| --- | --- | --- |
| `frames/quiet_published_s0` | `frames/quiet_sync_0_s0` / `quiet_sync_1_s0` | audio → 50 MHz |
| `frames/expected_generation_valid_o_s0` | `frames/expected_valid_sync_0_s0` / `expected_valid_sync_1_s0` | audio → 50 MHz |
| `frames/quiesce_sync_1_s0` | `frames/quiesce_return_sync_0_s0` / `quiesce_return_sync_1_s0` | audio → 50 MHz |
| `memory_stop_s1` | `memory_gate_sync_0_s0` / `memory_gate_sync_1_s0` | 50 MHz → memory |
| `memory_quiet_s0` | `memory_quiet_sync_0_s0` / `memory_quiet_sync_1_s0` | memory → 50 MHz |
| `control_request_s2` | `request_sync_0_s0` / `request_sync_1_s0` | 50 MHz → audio |
| `control_ack_s0` | `ack_sync_0_s0` / `ack_sync_1_s0` | audio → 50 MHz |

Closing the memory-stop second-Q fanout exposes a further return crossing:
declared `memory_gate_sync_1_s0` Q in the memory domain is inverted into
`memory_open_sync_0_s0`, then shifted into `memory_open_sync_1_s0` at 50 MHz.
This eighth pair has an exact Boolean complement check, rather than a false
direct-Q declaration. Every first Q has exactly one consumer: its second D.
Both receiver stages have unconditional CE and zero INIT. Source D/CE
combinational frontiers are inventoried completely and must terminate only
at FFs of the publishing clock, or constants. This checks the immediate
publisher boundary; it does not accept upstream CDC into those local FFs.

`workstation_tf_control_cdc_endpoints.json` fixes all source-Q and second-Q
consumers, including local FF D/CE/CLEAR, opaque primitive ports and top
exports. It is compared as a complete object and pinned by bytes; it is never
regenerated to accommodate a failing run. The manifest is a c7 topology
declaration, not a generally reusable endpoint count.

The primitive roles matter. `RAM16SDP4/WRE` uses its `CLK` at 50 MHz.
Playback `SDPB/CEA` uses `CLKA=memory_clk`; `CLKB=clk_50m` belongs to the other
port and is retained. `MULTALU27X18/A` consumers use the audio clock; the
clock vector is resolved bit by bit, including constant slots. Unknown
primitive/port roles, foreign clocks and absent functional clocks fail.

The common asynchronous assertion is actual `CLEAR n41_5`, exhaustively
proved as `!(reset_n && memory_guard_started)`. It is not just raw `reset_n`.
The TF frame bridge's local three-edge release pipelines are separate from
this common assertion. The audit does not prove recovery/removal, minimum
reset pulse widths, local release sequencing or the full reset inventory.

## Held 36-bit control transaction

Actual `held_control_[0:35]_s0` publish in the 50 MHz domain. Actual
`compute_control_[0:35]_s0` capture in the audio domain. Their D bindings are
checked bit by bit. Exact mapped LUT truth tables and the observed vendor
NE ALU mode are reduced to Boolean decision diagrams. No ALU is treated as
an arbitrary Boolean box, and any other mode or nonzero I3 fails. The tests
also execute the exact unmodified installed vendor ALU module for all 16
`I3/CIN/I1/I0` values and compare both outputs with the audit evaluator.

The source effective next-Q proof covers all 36 held bits and request:

```text
update = (ACK_sync1 == request) && (held != desired)
held_next = update ? desired : held
request_next = request XOR update
```

Here desired is cut at the actual 36 payload D expressions; this proof accepts
the handshake's data-independent behavior, not an independently reconstructed
business meaning for every desired bit. Compiled source identity remains a
separate mandatory gate. While an issued snapshot is unacknowledged, source
changes coalesce into the latest desired state without overwriting the held
transaction. An ACK permits a subsequent snapshot only after its return
synchronizers have delivered it to the source logic.

The destination effective next-Q proof covers all 36 compute bits, ACK and
the explicit capture-delay register:

```text
compute_next = capture ? held : compute
ACK_next = capture ? request_sync1 : ACK
capture_next = !capture && (request_sync1 != ACK)
```

In ideal sampling the first new request reaches sync0 at receiving edge 1,
sync1 at edge 2, sets capture at edge 3, and captures payload/ACK at edge 4.
The complete held-Q closure has 113 FF endpoints: 77 local endpoints and 36
audio capture Ds. There are no primitive or top exports. Compute-Q closure
contains 108 audio FF endpoints and two audio multiplier A ports. Capture-Q
consumers are also fixed in the manifest.

The source RTL wire `control_active` and output `tf_active` do not survive as
standalone mapped wires. The audit instead declares actual live
`u_managed/n1033_s1/F`, net `u_managed/n1033_4`, and proves:

```text
active = compute_control[2] && expected_valid &&
         (compute_control[35:4] == tf_expected_generation[31:0])
```

All 32 actual generation boundary bits have live drivers and only local audio
FFs in their complete combinational frontiers. This gate proof prevents a
stale snapshot from remaining active once the independently received expected
generation advances. Transport/Gray correctness of that generation remains a
separate proof; the gate audit does not infer vanished formals or substitute a
new 32-bit source contract.

## Stopped clocks, cancellation and checks

`sim/tf_audio/run_tf_control_snapshot.py` extracts the exact original control
always blocks and consumer gate from the pinned source into an audit-only
wrapper. It never generates a production replacement. The wrapper supplies
abstract desired and expected-generation boundary inputs. Three clock
ratios/phases verify every source and destination next-Q, rapid desired-state
coalescing, either clock stopped high or low, common asynchronous assertion
while a clock is stopped, and cancellation after the last source edge.

When the receiving clock stops, a held transaction remains immutable and no
ACK appears. When the source stops, the destination may finish the issued
snapshot but cannot publish a newer desired state. An independent generation
advance revokes the old active snapshot even if source clock never resumes.
Resume must not resurrect it. A common assertion clears both domains without
needing an edge. These are ideal clocked protocol observations, not physical
metastability or pulse-width models.

The actual frame bridge decoder/transport regression and the full runtime
service clear/stop regression link these abstract boundary tests to the
maintained TF path. The latter exercises buffered/unbuffered storage, final
mailbox ACK before stop completion, stopped-source cancellation, common reset,
and a structurally rejected original combinational stop loop. Their own
source hashes and explicit limits remain part of delivery evidence.

Run the narrow audit and optional actual-VG fault controls with explicit
stage/process paths:

```sh
python3 tools/workstation_tf_control_cdc.py \
  --scope runtime-r00-no-local-panel-tf-control-v1 \
  --stage /absolute/c7/workstation/Prj1 --process /absolute/c7/runtime_synthesis_evidence/process.json \
  --output /new/audit/output
GW138K_TF_CDC_STAGE=/absolute/c7/workstation/Prj1 \
GW138K_TF_CDC_PROCESS=/absolute/c7/runtime_synthesis_evidence/process.json \
python3 sim/test_workstation_tf_control_cdc.py
python3 sim/tf_audio/run_tf_control_snapshot.py --output /new/protocol/output
```

Fault controls rebuild the graph after each mutation. They reject publisher
and receiving clocks, receiver CE/INIT/CLEAR, first-D/second-D bypass, first-Q
extra D or CE consumers, foreign publisher frontiers, extra local consumers,
held overwrite/capture/ACK/request changes, wrong payload bit, LUT/ALU
corruption and associated primitive-clock changes. Raw bindings are taken from
the same actual scope and checked against the intended canonical net.

## Remaining boundaries and exit conditions

The `source_seen_edge` alias is explicitly unaccepted here. Its actual first-D
driver is `u_managed/midi_bytes/source_release_0_s0`, not the frame bridge's
similarly named release FF. Establishing that optimization needs an independent
source/top/reset equivalence and complete shared fanout review. Neither name
similarity nor a receiver-discovered producer is sufficient.

TF FIFO/Gray pointers and payload memory, combinational source-quiesce and
memory-ready inputs, source-loss behavior, all local/common reset releases,
and unrelated primitive clocks remain separate work. No source/second-stage
or payload timing exception is installed. The report only lists exact
first-D candidates for later constraint review; it emits no SDC. Held-data
flight bounds, setup/hold, both selected clock modes, routed timing and board
tests remain required. All complete-CDC, physical-CDC, hardware and deployment
acceptance flags remain false. Source simulation, synthesis identity, P&R,
hardware acceptance, SRAM and Flash are distinct evidence stages.

No runtime source or candidate is changed by this tool. Rollback removes the
new helper, manifest, documentation and tests; it does not change source
selection, installed constraints or board state. To extend the scope, declare
new producer and consumer identities first, add fault controls, obtain fresh
sealed synthesis and route/board evidence, and preserve existing scope gates.
