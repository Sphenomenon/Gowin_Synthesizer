# Native PCM/context CDC source policy

`workstation_runtime_pcm_cdc.py` owns one independent, partial source audit. It does not modify `workstation_runtime_cdc.py`, the older Gray/media-fence identity, locked baselines, vendor files, or RTL. It introduces no builder and runs no EDA or hardware operation.

The selected input policy is the maintained native composition in `rtl/workstation/workstation_runtime_audio.sv`: `bridge` owns two held mailboxes, `service/delivery` is compute-local, and `serializer` owns the physical stream. Accepted full83/full85 and resource profiles do not opt in through this module. Runtime profile installation is a separate reviewed change, followed by source-lock refresh and a new prepare/synthesis identity.

## Audited contracts

The bundle has exactly 50 lines. Each wildcard selects one enumerated register bit and pin; the actual source VG must resolve every selector to precisely that FF. Empty, duplicate, extra or changed inventories fail.

| Payload | Width | Flight budget | First consumer pins |
|---|---:|---:|---:|
| selected request → compute render identity | 65 | 13.020 ns | 65 D |
| compute reply → selected serializer | 98 | 13.020 ns | 134 D + 161 CE constrained; 263 actual dependency pins |
| control context → compute pending tuple | 33 | 13.020 ns | 33 D |
| control staged tuple → selected serial tuple | 33 | 20.000 ns | 33 D |

The first-FF closure must match the complete declared inventory, including source-domain feedback/comparators and the first selected ready synchronizer. No clock/prefix filter may discard an unexpected consumer. The four full closures have 65/263/141/207 endpoint pins. Unknown primitives touched by a payload, unknown vector bindings, extra FFs and synchronizer first-Q fanout fail.

`paired-nextq-v2` adds the other D/CE pin only for the 32 existing FFs `underrun_count_o[0]` and `wanted_sequence[1..31]`. Each of these FFs must have exactly one actual D-or-CE dependency; all remaining reply pins and the full reply consumer FF set remain exact. A missing FF, both D and CE dependencies, a third pin, or a new FF/MEM consumer fails. The paired constraint selectors bind both pins to the same reviewed FF, so their 13.020 ns flight and hold policy survives the observed synthesis migration. The bundle still has 50 lines and 896 statically resolved selectors. Only the two reply lines differ from the 263-pin `legacy-v1` bundle; no clock budget or reset exception changes.

The request payload and toggle publish on one source event, only with free request credit. Its earliest ideal capture is two compute periods, about 26.041667 ns; using the slow selected source period of 59.051 ns as a request flight budget is invalid. Reply capture is no earlier than two fastest selected periods, about 118.102797 ns. Context includes CFG_SETTLE and waits at least three compute edges. Staged serial capture waits for actual configuration application, the returned ACK, selected ready synchronization and guard0; guard7 releases the serializer. These ideal waits still require routed clock-to-Q/setup/uncertainty/PVT evidence.

The tool checks producer and consumer tuple mappings, publication credit, context comparison/ACK, the reply header and next tuple gate, explicit cancellation/ACK behavior, and serial guard capture/release. The reply bus also feeds the current PCM frame-boundary bypass; its full D/CE consumption closure is included. This source check does not prove the whole serializer FSM, analog audio, FIFO RAM data timing or every CDC in the workstation.

The pin alternatives also require an independent effective-next-Q proof. For every wanted-sequence bit, `Q_next = Q XOR (advance AND all lower wanted bits)`. `advance` requires configured state, the exact mode-dependent half-count match, BCK high, position63, the 1,028-frame startup equality, resume, no quiesce, and either playing or an available next frame. Availability is `have_next OR live_matching_reply`, with the independently checked configured/reset/quiesce/token/credit/rate/epoch/sequence handshake. Underrun bit0 toggles only on `advance AND NOT available AND NOT (&underrun_count)`. Thus saturation and the frame boundary bypass are included; an error reply is available and does not count as an underrun. All 32 wanted bits (including the unchanged bit0 anchor) and underrun bit0 are proved.

These equations are built from predetermined publisher Qs, not from destination D drivers. Exact LUT/INV functions from the actual VG are reduced into canonical ordered Boolean decision diagrams and compared for all assignments. The only internal cuts are the reply NE header predicates after their complete operand sets and primitive semantics pass the independent comparison proof. The proof rejects unknown FF leaves, unsupported primitives, cycles, ambiguous drivers, changed clocks/resets, and resource-bound overflow. It samples no states and does not assume the CE form. Scalar small-cone truth-table proofs retain their original bound. Request eligibility uses the same decision-diagram method with the independently checked named fault owner boundary expanded, because synthesis may duplicate its decode without traversing the boundary's net alias; it introduces no free fault cut.

Sixteen two-stage control paths have explicit producer identities or independently checked owner boundaries. Each first-Q drives only its second D; second stages use the actual destination clock and unconditional CE. Five global release groups bind to the reviewed `!(reset_n && memory_guard_started)` assertion and validate every constant seed and shift. The clock transaction's payload reset owner is separately checked. Bridge global reset, runtime stream assertion and serializer local reset remain distinct.

Quiesce and mute publish from their exact control-domain DFFPE Qs, preset asserted and CE unconditional. Resume is the unique runtime-local inverter driven by the known mute publisher Q, with its Boolean inversion checked; it is not inferred by tracing backward from a destination D0 or by reusing a generated numeric net alias. Both publisher D pins belong to the context and staged-tuple complete feedback closures. Their functional next-state decode remains owned by the rate transaction RTL and its independent behavior regression. Stream flush has no consumer in the selected complete-workstation composition and is optimized away; this audit does not invent a retained flush register or claim its hardware acceptance.

The constraints consist of four payload flight/hold pairs, sixteen first-D-only cuts and 2 ns second-stage bounds, and ten internal reset-release bounds. No asynchronous CLEAR/PRESET assertion, recovery/removal or pulse-width path is cut by this policy.

## Source parser and primitive model

The shared `SynthesisNetlist` source remains unchanged. Its named-port regex omits Gowin escaped formal names followed by their mandatory whitespace delimiter. `PcmNetlist` first constructs the maintained parser, then strictly reads named-port bindings from the original instance text and updates the shared instance dictionaries. It rejects duplicate/ambiguous formals, unparsed connection text, inconsistent original bindings and changed instance inventories. It does not rewrite the original VG or treat transformed text as an equivalent product input.

Escaped scalar formal aliases are followed only when a declared formal matches. This resolves actual compute-reset and `runtime_configuration.failed` routes; an unresolved or multiply driven producer fails, rather than becoming a free Boolean input. The result retains the lexical audit; sealed VG bytes are independently hashed through the synthesis identity tool.

Comparison carry chains require GW5A ALU mode `NE=3`, COUT, zero I3, a zero/XOR seed and exactly the declared operand pairs. Its inductive formula is `COUT = (I0 != I1) || CIN`, from Gowin GW5A `prim_sim.v`, module ALU. The ready comparison requires either all33 epoch/rate operand pairs in its carry, or exactly32 epoch pairs with the remaining scalar rate equality exhaustively proved in the gate. The reply header requires either all64 sequence/epoch operand pairs in its carry chains, or exactly63 with only epoch31 moved to the exhaustively proved scalar gate. Scalar rate equality is always checked in the reply gate. These are exact operand sets, selected from the actual VG structure; generated numeric aliases do not select a form. The result records the chosen pair counts and scalar forms. No optimized-away scalar tag check may be silently assumed. The primitive model is read-only first-party audit code; no vendor bytes are copied or modified.

Retire this local lexer adapter when the shared parser supports escaped named-port delimiters and aliases with the same actual-VG and duplicate-binding regression. Any topology, primitive ABI, synthesis alias, capture policy or clock change requires a fresh source review and negative controls; there is no permissive fallback.

## Invocation and acceptance semantics

```sh
python3 tools/workstation_runtime_pcm_cdc.py \
  --project "$PCM_STAGE" --synthesis-evidence "$PCM_PROCESS" --output "$PCM_AUDIT_JSON"
```

The default constraint revision is `paired-nextq-v2`. Proposal-only requires none of its 50 exact bundle lines to be present; a partial or already installed bundle is an error. `--installed` requires all 50 selected lines exactly once in the sealed stage SDC. Both modes independently hash all recorded staged inputs, profile, process and VG before and after the audit, as well as audit-source dependencies. An unsealed ad hoc SDC append cannot satisfy the stage identity.

Historical review must explicitly select `--constraint-revision legacy-v1`; there is no automatic revision fallback. An exact legacy installation reports `legacy_constraints_installed`, but never sets `candidate_constraints_installed` for the paired policy. Every revision separately reports actual destination dependency pins absent from its selectors in `uncovered_payload_pins` and sets `selected_constraint_capture_coverage_verified` false if any are missing. On e855, 29 actual reply pins are uncovered by the sealed legacy lines. Its source/next-Q proof therefore does not claim the new paired constraints were installed. Production installation requires a new prepare and synthesis seal, independent of this helper change.

`validate_constraints(..., installed=True)` may also check review text in isolation. That result is static installation evidence only. Public acceptance evidence must come from `run_audit`, which binds the text to a completed, sealed synthesis process. Proposal, installed and explicit historical runs receive different new `runtime-pcm-context-source-v2-*` identities.

Regression selects an explicit existing synthesis stage; it never synthesizes or searches private historical caches:

```sh
GW138K_RUNTIME_PCM_CDC_STAGE="$PCM_STAGE" \
GW138K_RUNTIME_PCM_CDC_PROCESS="$PCM_PROCESS" \
GW138K_RUNTIME_PCM_CDC_TEST_EVIDENCE="$PCM_TEST_JSON" \
GW138K_RUNTIME_PCM_CDC_INSTALLED=1 \
python3 sim/test_workstation_runtime_pcm_cdc.py
```

Set the installed selector to1 only when the explicitly selected sealed candidate contains the selected50 lines. For a historical stage also set `GW138K_RUNTIME_PCM_CDC_CONSTRAINT_REVISION=legacy-v1`. Omit the installed selector for a proposal-only stage. Without stage/process, only standalone policy/lexer/BDD tests run and the actual-VG class is skipped. Negative controls mutate parsed actual VG cells in memory, restore them between cases, and separately corrupt installed SDC text. D/CE inversions retain the full dependency closure and must fail the next-Q proof; carry, saturation, header operands, third pins, and added FF/MEM consumers also fail. They cannot change the sealed product files or inherit old 25/77 evidence.

All whole-workstation CDC/reset completeness, Gowin tool-side query resolution, routed propagation/setup/hold, reset recovery/removal, hardware, SRAM/Flash deployment and release gates remain false. Exit requires a new sealed candidate with the installed bundle, real Gowin reports for the exact actual endpoints and required/propagation timing in both selected modes, independent complete reset and FIFO RAM proofs, and separately authorized hardware acceptance. A tool exit status or these source checks alone cannot promote a deployment.
