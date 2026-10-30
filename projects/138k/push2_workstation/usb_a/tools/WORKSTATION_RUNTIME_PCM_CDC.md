# Native PCM/context CDC source policy

`workstation_runtime_pcm_cdc.py` owns one independent, partial source audit. It does not modify `workstation_runtime_cdc.py`, the older Gray/media-fence identity, locked baselines, vendor files, or RTL. It introduces no builder and runs no EDA or hardware operation.

The selected input policy is the maintained native composition in `rtl/workstation/workstation_runtime_audio.sv`: `bridge` owns two held mailboxes, `service/delivery` is compute-local, and `serializer` owns the physical stream. Accepted full83/full85 and resource profiles do not opt in through this module. Runtime profile installation is a separate reviewed change, followed by source-lock refresh and a new prepare/synthesis identity.

## Audited contracts

The bundle has exactly 50 lines. Each wildcard selects one enumerated register bit and pin; the actual source VG must resolve every selector to precisely that FF. Empty, duplicate, extra or changed inventories fail.

| Payload | Width | Flight budget | First consumer pins |
|---|---:|---:|---:|
| selected request → compute render identity | 65 | 13.020 ns | 65 D |
| compute reply → selected serializer | 98 | 13.020 ns | 103 D + 160 CE |
| control context → compute pending tuple | 33 | 13.020 ns | 33 D |
| control staged tuple → selected serial tuple | 33 | 20.000 ns | 33 D |

The first-FF closure must match the complete declared inventory, including source-domain feedback/comparators and the first selected ready synchronizer. No clock/prefix filter may discard an unexpected consumer. The four full closures have 65/263/141/207 endpoint pins. Unknown primitives touched by a payload, unknown vector bindings, extra FFs and synchronizer first-Q fanout fail.

The request payload and toggle publish on one source event, only with free request credit. Its earliest ideal capture is two compute periods, about 26.041667 ns; using the slow selected source period of 59.051 ns as a request flight budget is invalid. Reply capture is no earlier than two fastest selected periods, about 118.102797 ns. Context includes CFG_SETTLE and waits at least three compute edges. Staged serial capture waits for actual configuration application, the returned ACK, selected ready synchronization and guard0; guard7 releases the serializer. These ideal waits still require routed clock-to-Q/setup/uncertainty/PVT evidence.

The tool checks producer and consumer tuple mappings, publication credit, context comparison/ACK, the reply header and next tuple gate, explicit cancellation/ACK behavior, and serial guard capture/release. The reply bus also feeds the current PCM frame-boundary bypass; its full D/CE consumption closure is included. This source check does not prove the whole serializer FSM, analog audio, FIFO RAM data timing or every CDC in the workstation.

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

The default is proposal-only and requires none of the 50 exact bundle lines to be present; a partial or already installed bundle is an error. `--installed` requires all 50 lines exactly once in the sealed stage SDC. Both modes independently hash all recorded staged inputs, profile, process and VG before and after the audit, as well as audit-source dependencies. An unsealed ad hoc SDC append cannot satisfy the stage identity.

`validate_constraints(..., installed=True)` may also check review text in isolation. That result is static installation evidence only. Public acceptance evidence must come from `run_audit`, which binds the text to a completed, sealed synthesis process. Proposal and installed runs receive different new `runtime-pcm-context-source-v1-*` identities.

Regression selects an explicit existing synthesis stage; it never synthesizes or searches private historical caches:

```sh
GW138K_RUNTIME_PCM_CDC_STAGE="$PCM_STAGE" \
GW138K_RUNTIME_PCM_CDC_PROCESS="$PCM_PROCESS" \
GW138K_RUNTIME_PCM_CDC_TEST_EVIDENCE="$PCM_TEST_JSON" \
GW138K_RUNTIME_PCM_CDC_INSTALLED=1 \
python3 sim/test_workstation_runtime_pcm_cdc.py
```

Set the installed selector to1 only when the explicitly selected sealed candidate contains the reviewed50 lines. Omit it for a proposal-only stage. Without stage/process, only standalone policy/lexer tests run and the actual-VG class is skipped. Negative controls mutate parsed actual VG cells in memory, restore them between cases, and separately corrupt installed SDC text. They cannot change the sealed product files or inherit old 25/77 evidence.

All whole-workstation CDC/reset completeness, Gowin tool-side query resolution, routed propagation/setup/hold, reset recovery/removal, hardware, SRAM/Flash deployment and release gates remain false. Exit requires a new sealed candidate with the installed bundle, real Gowin reports for the exact actual endpoints and required/propagation timing in both selected modes, independent complete reset and FIFO RAM proofs, and separately authorized hardware acceptance. A tool exit status or these source checks alone cannot promote a deployment.
