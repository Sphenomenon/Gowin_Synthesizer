# Owner8 recording: PCM pointers/counter and APB mailbox review

`workstation_recording_phase1_cdc.py` is a read-only source/netlist auditor and
SDC proposal generator. It does not install constraints or invoke synthesis,
P&R, programming or hardware operations. Its explicit supported prepared profile
is `custom138k-workstation-r00-no-local-panel-v1`, with the exact configuration
digest `fe57acb99ab96c773148a10bd41401eaa55ca069f2ff9d1def1daa254dd5d241`
and unchanged owner8 recording metadata/address-map provenance. Other profiles
must not inherit this result by relabelling.

The implemented scope is deliberately partial:

| Boundary | Source structure checked | Outside this result |
|---|---|---|
| PCM observation | Exact 244 FFs; 5-bit read/write Gray pointers and 32-bit drop Gray crossing; four 3-stage release chains | FIFO RAM data arcs, complete ownership proof and physical bit flight |
| APB commands | Exact 181 FFs; request/ACK synchronizers; 49-bit request and 33-bit response held payloads; two 3-stage release chains | Physical held-word setup/hold and opaque CPU interface timing |
| Seal | Explicitly excluded | Raw functional reset, request/result/hold synchronizers, combinational ready cone and result stability |
| Service/native/DDR | Explicitly excluded | Backend, native acceptance, owner8 slots/tags and full reset inventory |

The auditor independently checks the completed synthesis process, every staged
input, prepared profile and original VG before and after. Five reviewed source
revisions are explicit; frozen APB/counter sources come only from their sealed
reconstructed inputs. The maintained source bytes must match their reviewed
revisions, and the prepared top must retain the exact physical-frame, clock,
reset and AE350 APB composition. No fallback reconstruction is consulted.
The public wrapper also runs the existing disabled-panel clock audit. APB FFs
must use the actual `ram_clk`, not the unrelated `clk_50m` net; PCM source FFs
must use the selected `dac_mclk_d`, with memory-domain consumers on `memory_clk`.
The external DDR clock implementation remains opaque to this source audit.

All 425 reviewed FFs must be the declared unique DFFCEs, with their exact clocks,
INIT0 and local functional CLEAR producer. Additional or missing FFs fail.
The 42 Gray first-stage sources and the two ordinary synchronizer sources are
predetermined unique registered Qs. Every first D must equal its declared source
Q, every second D must equal first Q, synchronizer CE must be unconditional, and
the complete first-Q fanout must contain exactly the next D. The read-pointer
MSB is explicitly the actual `read_binary[4]` Q; it is not guessed from first D.

Every reviewed source's full combinational consumer closure is recorded,
including same-domain D/CE/CLEAR consumers, RAM input pins and the two opaque
CPU pins reached through APB-ready gating. An endpoint identity digest is checked
for each of thirteen source groups. Its canonical representation is sorted JSON
with compact separators over `ff_endpoints` (full pin path → canonical clock net)
and `primitive_endpoints` (full pin path → kind and canonical clock pins).
No endpoint is removed by clock, path prefix or primitive type. A new export to
a top output fails. The thirteen declarations were reviewed against the sealed
e855 source topology; they are not a generic allowance for future consumers.
Changes to recording/other consumers require a fresh source review and new
declarations, even if source widths and first-D counts stay unchanged.
Primitive endpoint listing does not accept primitive timing semantics.

The protocol source basis is distinct from the topology check. The exact FIFO
RTL advances binary and registered Gray pointers only on a successful local
transaction. The audit enumerates all 32 adjacent values including wrap for its
5-bit code. For a 32-bit counter increment with k trailing ones,
`n xor (n+1) = (1 << (k+1))-1`, so the Gray difference is exactly `1 << k`;
higher bits cancel. All 32 carry classes are checked, and saturation holds the
code unchanged. `next_drop` feeds the registered encoder, allowing the last
drop to commit on the same source edge even if MCLK then stops. These arithmetic
and source-contract checks are not a formal gate-level encoder proof.

APB has one outstanding transaction. IDLE captures request data and changes the
request toggle on the same pclk edge; WAIT_RESPONSE/COMPLETE preserve the held
request. The destination captures it at the third observing edge, before a later
local decode. Command acceptance captures response data and ACK on the same
memory edge; the source observes ACK through meta/sync/settled and captures the
response at the fourth observing APB edge. The auditor checks common launch CE,
exact payload bit mapping, capture CE, request toggle inversion and ACK identity.
The response CE proof applies to legal source states 00/01/10; it explicitly does
not accept the illegal 11 state. Metastability can delay detection and is not
simulated or accepted by these digital checks. Existing asynchronous functional
regressions supply separate bounded simulation evidence, not physical proof.

The 35-line SDC proposal contains only these exact receiving pins and held paths:

- Six raw-reset receiving CLEAR groups (18 pins), and twelve interstage limits.
- Two ordinary first-D exceptions and two interstage limits.
- Three Gray flight/hold pairs and three first-to-second stage limits.
- Two held-payload flight/hold pairs.

The Gray flight proposal is 10 ns, at most the minimum source period among the
100 MHz memory and both selected DAC modes. The held request/response proposals
are one destination period (10 ns/20 ns), below their receiving-edge waits.
The 2 ns interstage value is a new proposal, not inherited physical acceptance.
Every suffix selector must expand to exactly one actual leaf pin, including
rejection of unexpected nonnumeric or extended suffix overmatches. The proposal
must cut exactly the 18 receiving CLEAR pins. It cannot cut functional CLEAR,
whole clocks, or a missing selector. Static resolution is separate from Gowin
Tcl query resolution. The tool never installs or appends these lines.

The 25 RAM16SDP4 instances holding the 16×98 PCM queue are inventoried with their
selected write clock. RAM data flight, settled read data and complete ownership
are not constrained or accepted here. Full recording CDC, reset assertion pulse/
glitch/flight, recovery/removal, metastability margin, routed setup/hold, both
selected clock modes and hardware acceptance remain false. In particular the
seal ready cone contains reset qualification as well as destination state, and
its 18 functional FFs use the common reset directly. This phase does not upgrade
those boundaries or the service/native/owner8 path to accepted.

```sh
python3 projects/138k/push2_workstation/usb_a/tools/workstation_recording_phase1_cdc.py \
  --project /absolute/selected/workstation/Prj1 \
  --synthesis-evidence /absolute/selected/runtime_synthesis_evidence/process.json \
  --output /absolute/review/recording-phase1.json \
  --proposal-output /absolute/review/recording-phase1-proposal.sdc
```

The optional regression uses `GW138K_RECORDING_PHASE1_STAGE` and
`GW138K_RECORDING_PHASE1_PROCESS`. It never invokes EDA when those are absent.
`GW138K_RECORDING_PHASE1_TEST_EVIDENCE` optionally records the actual-VG in-memory
negative controls. They alter producer/shift/clock/CE/reset/bit order, add a source
consumer, bypass release and attempt to cut functional CLEAR or entire clocks.
The original VG/SDC and complete input seal are checked again after the suite.

```sh
python3 projects/138k/push2_workstation/usb_a/sim/test_workstation_recording_phase1_cdc.py
```
