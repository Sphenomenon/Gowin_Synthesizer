# Task3 W-media native boundary

This is an unselected source stage, not a complete board profile. It does not
change W21, task2, accepted baselines, existing pin assignments or deployment.

`workstation_task3_w_media.sv` composes the actual maintained memory BIST,
owner5 CNN task/broker, owner6 delay channel and one owner8 raw recording store.
The existing HCI/GATT physical engine and `ble_business_owner` remain the sole
recording object/task/protocol authority. The raw store does not allocate another
business object. R00 and its F804 backend are not instantiated by this component.

## Interfaces and clocks

| Boundary | Domain | Meaning |
| --- | --- | --- |
| `raw_*` | `clk_i`, normally 50 MHz | Existing HCI physical-engine storage contract; bind all fields, including faults and native commitment counters |
| CNN descriptors/PCM/scores/terminal | `clk_i` | Offline bounded task; existing task ID, generation, ordered frame index and CRC contract |
| owner6 delay | `memory_clk_i` | Maintained D delay client; independent of CNN and recording credits |
| DDR app and native accept | `memory_clk_i` | Actual controller joint command/write acceptance and routed read returns |
| `control_ready_o` | `clk_i` | Two-stage synchronized real BIST/client readiness; does not claim radio or transport readiness |
| `workstation_task3_record_ingress` | one `clk_i` | Already validated packet deliveries; the transport/CDC implementation is external |

The memory boundary retains separate local-slot, core and native acknowledgments.
CNN uses only `native_accept_o[5]`; raw recording uses `[8]`. Local admission
cannot publish recording drain or CNN DDR commitment. An unowned native return
quarantines all clients. Recovery requires coherent service/FIFO/controller reset;
resetting one client while old DDR responses remain outstanding is unsupported.

The map guard remains elaborated. `rtl/ddr_address_map.vh` is the allocation
authority. The raw object contains 2,880,000 stereo16/48k frames, 11,520,000 bytes,
at byte `0x30600000..0x310fc7ff`, native word `0x0c180000..0x0c43f1ff`.
Its last BL8 starts at `0x0c43f1f8`; the 14,336 pool-padding bytes are not capture
or fetch capacity. CNN input is a separate 96,000-frame task reservation at
`0x31100000..0x3115dbff`, not a view of the recording fetch cache.

## Recording packet pacing and failure

The existing physical recording engine needs five clocks between PCM acceptance
edges: acceptance enters state2, four CRC byte steps return it to state0, then the
next acceptance can occur. `workstation_task3_record_ingress` defaults to a
256-frame FIFO and at least five clocks between output pulses. The default source
lease is 200,000 clocks, or 4 ms at 50 MHz; neither value is a measured LCD budget.

`frame_valid_i` is a single-cycle, already CRC-validated transport delivery
attempt. `frame_ready_o` is its credit, not a held ready/valid offer. A sender
must not attempt delivery without credit. Overflow fails the current source;
the adapter never waits on or slows M's physical sample scheduler. Input session,
generation, physical epoch, sequence, format and error status are checked before
delivery. It admits format1/48k only. It does not resample, interpolate, hide
missing samples, correct sustained clock drift or turn 44.1k PCM into format1.

Overflow, identity/sequence/format error, disconnect/transport fault, expired
lease, PANIC or matching cancellation immediately suppress output/source-ready,
discard the queued tail and latch a failure. The existing physical engine must
observe source failure and fail the same recording object. A fresh arm requires
both a higher nonzero generation and `object_idle_i`; this signal must come from
the actual object's retired/cleared state. A stale cancellation cannot fence a
new generation. No automatic rearm or download of a partial object is provided.

The physical sequence and epoch remain available for provenance. The adapter's
separate local observer sequence stays contiguous across arms, allowing the
existing HCI wrapper to detect lost delivery pulses without confusing a valid
new physical epoch with a dropped pulse. This does not conceal a physical gap:
that gap already fails the source before either output is published.

## Headless firmware

`worker_media_main.c` is a separate root. It calls the actual Classic runtime
init/pump, which already initializes and pumps the one C/BLE business owner.
It does not call the business pump a second time. `ui_main` and `ui_render` are
absent. `A138_WORKER_AUDIO_ONLY` is forbidden; session-only Classic, actual SBC,
PCM and BLE business remain compiled. CPU submit/poll/facts APIs address the same
`firmware_owner`; no M command-transport frontend is bound in this stage.

`tools/workstation_task3_w_media_firmware.py` is an isolated explicit-role build,
not a numbered production builder. Its capacity compiler define comes from the
versioned DDR map and appears in every actual TU command. The original firmware
manifest/reviews are unchanged. Exact inverse capacity lineage proves the parent
source, while compilation uses current C/header bytes. A separate current-source
points-to review audits this new ELF's actual JALR sites, SBC tables, reachable
roots and stack. The added physical-capacity MMIO read in
`a138_ble_business_pump` has the sole `record_mmio_read` target. Graph UI, R00
control APIs and unavailable durable-store callbacks must remain unreachable.

The firmware's physical-capacity check will fail unless the board shell binds
the actual service/engine and raw store to the same map capacity. Compiling this
firmware alone does not establish that binding or runtime execution.

## Minimal remaining board-profile integration

1. Add an explicit headless-media trait/provider/registry configuration, distinct
   from W21 audio-only. Retain full native shared HCI/Classic/GATT source selection;
   do not run `workstation_worker_audio_only` trimming or restore display/FFT/UI.
2. Select the new firmware role and current-source audit in the existing build
   entry. Retain the ROM128/ILM64/DLM64 geometry and source/ELF identities. Split
   recording data API, owner8 infrastructure and R00 backend selection; do not
   select all R00 sources merely to enable the C data API.
3. Bind full HCI engine/service capacity and raw interface to this component.
   Keep `SINGLE_BLE_RECORDING`, `EXTERNAL_RAW_STORE`, explicit sealing and bounded
   drain timeout. Reject F804 and retain exactly one physical recording engine.
4. Replace W's old TF-follow CNN link with this task interface. Add explicit
   command/result MMIO or transport adapters, cancellation and generation fencing;
   do not silently restore TF/USB/HDMI ownership on W.
5. Retire/rebind only actually absent display constraints. Preserve all surviving
   clocks, native owner5/6/8 CDC/reset/fault contracts and full timing budgets.
   Validate actual VG/VO endpoints before any physical CDC claim.
6. Bind recorder input to M's actual completed final-output tap after a validated
   electrical/packet/CDC boundary. Until then leave its source-ready false.
   Do not substitute W's local final tap while labeling it M's output.
7. Keep phone decoded-PCM egress, M final-tap recording ingress and offline TF/CNN
   ingress as independent bounded branches. Their ready signals must never be
   ANDed into M's sample schedule. W's present local final PCM already includes
   master gain; forwarding it as an unscaled M source would apply gain twice.
   The first final phone path should export decoded PCM to M's D/final-gain/output
   scheduler, or explicitly export pre-master W DSP PCM after deadline validation.

Only LCD is the known wired inter-board connector. No pin direction, voltage,
clock, measured throughput/latency, congestion policy or connected transport is
invented by these source modules. W21's local phone/D/DAC route remains an
independent fallback until the actual final W→M route is verified.

## Evidence scope

The dated report `reports/DUAL138K_TASK3_W_MEDIA_NATIVE_20261102.json` records:

- Actual native composition, production CNN dimensions unchanged, complete real
  read-only SPI model boot and native DDR readback CRC, independent owner6 writes,
  24-frame owner8 capture/drain/download/clear and common fault quarantine.
- Separate actual headless-media ELF, per-TU capacity flags, parent lineage,
  current-machine callback/table checks and conservative stack bound.
- Burst adapter with the actual maintained recording engine as a simulation
  pacing/CRC oracle, plus rejected spacing/overflow/generation mutations.

The first test does not run CNN inference, HCI radio, actual D DSP or a full
60-second recording. The already recorded CNN-task and 60-second single-object
component regressions provide separate evidence, not concurrent whole-system
acceptance. No board profile, synthesis/P&R/resource count, measured LCD or BLE
timing, real M-tap recording, SRAM programming or Flash write is claimed here.
