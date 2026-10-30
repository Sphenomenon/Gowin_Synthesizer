# Explicit runtime CDC/reset source inventory

Date: 2026-10-30. This is a source inventory for the explicit runtime candidate. No profile, constraints or RTL changed. Source-to-netlist evidence is now attached for the exact second synthesis snapshot. No routed timing, physical CDC or hardware result is marked passed.

Identity: `runtime-cdc-source-inventory-v2-c8daba6ec2fa3199`. The JSON records 150 crossing records, prepare-time source hashes and actual second-netlist mapping relative to `workstation_custom_138k_top`. All 21 Gray groups (400 first-stage bits) have unique source-register/first-stage/clock mapping. Other records include candidate endpoints and direct payload connections; complete endpoint mapping and every physical acceptance field remain false.

The companion JSON is `reports/workstation_task_20261030/runtime_cdc_source_inventory.json`. It uses the real instance composition, including generated delay effects hierarchy. The crossing table below retains source-level names; its hierarchy column is not an SDC selector. The JSON separates actual Gray mapping from candidate non-Gray groups and explicitly unresolved merged/pruned paths. Do not paste these selectors blindly into SDC.

## Clock and propagation policy

| Clock | Frequency | Period ns |
| --- | ---: | ---: |
| control50 | 50,000,000 | 20.000000000 |
| compute76m8 | 76,800,000 | 13.020833333 |
| memory100 | 100,000,000 | 10.000000000 |
| pclk50 | 50,000,000 | 20.000000000 |
| usb48 | 48,000,000 | 20.833333333 |
| selected48 | 12,288,000 | 81.380208333 |
| selected44 | 16,934,400 | 59.051398337 |

Both selected MCLK modes share the DCS output `u_managed/runtime/clocks/selector/CLKOUT`. The stricter59.051398ns source-period limit applies to selected-clock Gray paths across both modes. Compute, DDR, USB and APB clocks remain distinct domains even when generated from a common board oscillator or nominally equal in frequency. DDR UI100 has an opaque vendor-IP boundary; source-plan declarations are not a mapped/routed proof.

Gray bits need registered source unit steps, coherent first-stage sampling, and source-period max flight/skew. A broad setup false path would remove the required bound. The prepared runtime SDC adds a 10.000 ns `memory_gray*`→`gray_meta*` max-delay plus a hold-only exception. The actual 32 source/first-stage bits now map; exact tool-query resolution and routed delay are still pending.

Held payloads remain immutable until ACK; the receiver token/settle protocol provides capture margin. This inventory recommends the conservative limit of one destination period for payload flight, while separately checking the real capture edge and source hold. A token synchronizer alone is not a payload timing constraint. FIFO storage additionally needs actual RAM/slot ownership and collision checks.

Single-bit exceptions apply only to the asynchronous first stage; interstage timing, placement, pulse persistence and MTBF remain checks. Resets require minimum physical pulse, actual async-pin fanout and recovery/removal analysis, with local edge-based release. Availability/PLL loss must not clear runtime session identity.

## Exact second synthesis mapping

The sole evidence target is `/Users/sphenicidition/.cache/gw138k-task-20261030/runtime-rev4-synthesis-41e653fe/workstation/Prj1/impl/gwsynthesis/custom_138k_integration.vg`, SHA-256 `2319746ad8eabba1e19721908402dd0c25bd91aba52b896650d82153e6c4e3da`. Its process evidence confirms synthesis-only completion with exit 0 and all 560 staged inputs unchanged. The JSON retains all 560 input hashes, original-source snapshot hashes, staged support/SDC hashes and parser/generator identities. It does not bind a later source edit or bitstream to this identity. During finalization, the workspace TF service had changed from snapshot `a359be17c8767932f967d6c53cb3c93faa3edb22c2e82c6c9281cb8feadf5179` to `c61e4cbdfa1b204cd95cf6d0d282feccb446c272ec716034fe07038ebc2604e2` for the separate `memory_quiet` repair. This inventory does not validate that repair; the JSON records the drift explicitly.

The existing read-only `workstation_synthesis_netlist.py` parser expands 287 modules, 287 hierarchy frames and 173,201 cells, including 55,394 DFF leaf cells. This parsed DFF count has different accounting from Gowin's reported register resource; opaque memories/vendor primitives prevent treating it as the synthesis register total.

| Gray groups | Bits per group | Actual source clock → first-stage clock |
| --- | ---: | --- |
| guard-heartbeat | 32 | `memory_clk` → `clk_50m` |
| midi-drop-count | 32 | `clk_50m` → `audio_clk` |
| clock-reference_48_monitor | 32 | `clk_12m288` → `clk_50m` |
| clock-reference_44_monitor | 32 | `clk_16m9344` → `clk_50m` |
| clock-selected_monitor | 32 | `dac_mclk_d` → `clk_50m` |
| delay-write-wptr / delay-read-rptr | 10 each | `audio_clk` → `memory_clk` |
| delay-write-rptr / delay-read-wptr | 10 each | `memory_clk` → `audio_clk` |
| physical-observer-wptr / physical-observer-drops | 5 / 32 | `dac_mclk_d` → `audio_clk` |
| physical-observer-rptr | 5 | `audio_clk` → `dac_mclk_d` |
| display-memory-drops | 32 | `clk_50m` → `memory_clk` |
| tf-frames-wptr / tf-generation | 5 / 32 | `clk_50m` → `audio_clk` |
| tf-frames-rptr / tf-generation-ack | 5 / 32 | `audio_clk` → `clk_50m` |
| tf-byte-capture-wptr / tf-byte-playback-rptr | 13 each | `clk_50m` → `memory_clk` |
| tf-byte-capture-rptr / tf-byte-playback-wptr | 13 each | `memory_clk` → `clk_50m` |

All 400 first-stage D inputs trace to a unique source register on the expected clock. In 17 groups they are direct Q→D. Each of the four TF byte FIFO groups instead passes through a local-clear `LUT3`, `INIT=8'h90`: `I2` is the Gray source and `I0/I1` are local `clear_meta/clear_seen`. This is `Gray AND (clear_meta XNOR clear_seen)`. The max-delay path must include that LUT. Gray MSBs can share a binary-MSB register, and identical clear-meta registers can merge between capture/playback FIFOs; the JSON follows actual Q drivers. None of this proves safe non-unit pointer clear, local release timing or routed propagation.

Actual hierarchy uses `runtime_effects.effects` for the effects generate and `u_tf_audio/frames/frames_0` for the child frame FIFO. Exact first-stage paths, canonical Q/D nets, clocks and any local-clear LUT are stored per bit. The earlier first-netlist draft is superseded and is not acceptance evidence.

Of the other 129 source records, 114 have named destination register candidates. Direct named held-payload Q→D links are recorded with actual clocks, including 49-bit APB requests, 33-bit responses/context, 65-bit render requests, 36-bit TF controls and retained display/feedback banks. Physical PCM reply data reaches 32 `serializer/next_pcm` registers plus `next_error`; reply identity also controls comparisons/enable logic, so this list is not a complete payload timing endpoint set. Synthesis retains fewer fields in several display/health/feedback mailboxes. Candidate counts do not justify a source field's pruning or an exception.

The two delay FIFOs each map to 544 `RAM16SDP4` primitives and 130 bank-head DFFs; physical observation maps to 25 `RAM16SDP4`, TF frames to 22, and each byte FIFO to two `SDPB` plus eight output-data DFFs. Those are actual synthesis structures, not physical BSRAM equivalence. The shallow asynchronous-read RAM paths still require destination-consumer/collision/ownership analysis. A pointer synchronizer does not itself constrain payload output/capture paths.

Several source-local reset labels disappear after synthesis, including the PC/health/display/BLE mailbox chains and parameter APB's p-domain chain. The JSON preserves sample consumer async-pin cones and possible shared chain candidates as explicitly unverified. It also leaves unused MIDI, busy-reason/TF-bank diagnostics and input-size paths unresolved until constant/unused/alias evidence is complete. A zero local label count is not evidence of an unsynchronized design, and finding a similarly named chain is not equivalence proof.

Gowin's synthesis Timing Clock Summary lists ULPI, the reference clocks and selected MCLK with default 100 MHz entries. These values cannot certify the actual 60 MHz ULPI, 12.288/16.9344 MHz references or DCS output constraints. Audit actual generated clocks, both selected modes and every SDC query before physical timing analysis. `NL0002` also sweeps `u_scan_window`, `taps`, `midi_uart` and observation spectrum. The report records them as feature-preservation gates requiring explicit disabled/unused-path evidence against each public adapter. The source inventory does not mark them accepted merely because synthesis succeeded.

Read-only verification command:

```sh
python3 /Users/sphenicidition/.cache/gw138k-task-20261030/runtime-cdc-endpoints-v2/verify_inventory.py
```

The fresh parse checks all 560 sealed staged inputs, all 150 unique source records and false physical/hardware flags, 21 Gray groups with 400 unique first-stage Q-to-D/cone/clock mappings, 938 direct held-payload connections, and six FIFO storage groups. It also checks the local-clear LUT truth table. Results are in `runtime-cdc-endpoints-v2/verification.json` under the same cache root. This is identity/connectivity validation only; candidate non-Gray completeness stays false.

## Crossings

| ID / class | Source hierarchy | Direction | Producer → first destination | Required flight ns |
| --- | --- | --- | --- | ---: |
| guard-reset / reset_assert_release | `u_runtime_memory_guard` | asynchronous reset/qualification → control50 / memory100 | `reset_ni` → `control_reset_pre*,control_reset_n / memory_reset_pre*,memory_reset_n` | review |
| guard-availability / reset_assert_release | `u_runtime_memory_guard` | asynchronous reset/qualification → control50 | `backend_reset_ni && backend_ready_i` → `availability_release*` | review |
| guard-heartbeat / gray_counter_or_pointer | `u_runtime_memory_guard` | memory100 → control50 | `memory_gray*` → `gray_meta*` | 10.000000 |
| guard-grant / single_bit_or_independent_levels | `u_runtime_memory_guard` | control50 → memory100 | `armed` → `grant_release*` | review |
| guard-open-ack / single_bit_or_independent_levels | `u_runtime_memory_guard` | memory100 → control50 | `grant_release[2]` → `open_meta` | review |
| guard-channel-close / reset_assert_release | `u_runtime_memory_guard` | asynchronous reset/qualification → memory100 | `memory_reset_n && raw_available && available && !fault_o` → `grant_release*` | review |
| compute-output-safe / reset_assert_release | `top` | asynchronous reset/qualification → compute76m8 | `reset_n && audio_reset_n && !memory_guard_mute` → `output_safe_compute*` | review |
| hardware-smute / asynchronous_output | `top` | control50 / compute76m8 → DAC pin | `memory_guard_mute / runtime_smute` → `dac_smute` | review |
| clock-apb-req-payload / held_payload | `u_clock_control` | pclk50 → control50 | `request_held*` → `request_local*` | 20.000000 |
| clock-apb-req-request / single_bit_or_independent_levels | `u_clock_control` | pclk50 → control50 | `request_toggle` → `req_meta` | review |
| clock-apb-req-ack / single_bit_or_independent_levels | `u_clock_control` | control50 → pclk50 | `acknowledge_toggle` → `ack_meta` | review |
| clock-apb-req-reset / reset_assert_release | `u_clock_control` | asynchronous reset/qualification → pclk50 / control50 | `common reset` → `p_release* / a_release*` | review |
| clock-apb-response / held_payload | `u_clock_control` | control50 → pclk50 | `response_held*` → `response_local*` | 20.000000 |
| parameter-apb-req-payload / held_payload | `u_managed/control_cdc` | pclk50 → compute76m8 | `request_held*` → `request_local*` | 13.020833 |
| parameter-apb-req-request / single_bit_or_independent_levels | `u_managed/control_cdc` | pclk50 → compute76m8 | `request_toggle` → `req_meta` | review |
| parameter-apb-req-ack / single_bit_or_independent_levels | `u_managed/control_cdc` | compute76m8 → pclk50 | `acknowledge_toggle` → `ack_meta` | review |
| parameter-apb-req-reset / reset_assert_release | `u_managed/control_cdc` | asynchronous reset/qualification → pclk50 / compute76m8 | `common reset` → `p_release* / a_release*` | review |
| parameter-apb-response / held_payload | `u_managed/control_cdc` | compute76m8 → pclk50 | `response_held*` → `response_local*` | 20.000000 |
| midi-byte-payload / held_payload | `u_managed/midi_bytes` | control50 → compute76m8 | `held_data*` → `destination_data*` | 13.020833 |
| midi-byte-request / single_bit_or_independent_levels | `u_managed/midi_bytes` | control50 → compute76m8 | `request_toggle` → `req_meta` | review |
| midi-byte-ack / single_bit_or_independent_levels | `u_managed/midi_bytes` | compute76m8 → control50 | `acknowledge_toggle` → `ack_meta` | review |
| midi-byte-reset / reset_assert_release | `u_managed/midi_bytes` | asynchronous reset/qualification → control50 / compute76m8 | `common reset` → `source_release* / destination_release*` | review |
| pc-byte-payload / held_payload | `u_managed/pc_bytes` | control50 → compute76m8 | `held_data*` → `destination_data*` | 13.020833 |
| pc-byte-request / single_bit_or_independent_levels | `u_managed/pc_bytes` | control50 → compute76m8 | `request_toggle` → `req_meta` | review |
| pc-byte-ack / single_bit_or_independent_levels | `u_managed/pc_bytes` | compute76m8 → control50 | `acknowledge_toggle` → `ack_meta` | review |
| pc-byte-reset / reset_assert_release | `u_managed/pc_bytes` | asynchronous reset/qualification → control50 / compute76m8 | `common reset` → `source_release* / destination_release*` | review |
| midi-drop-count / gray_counter_or_pointer | `u_managed/midi_drops` | control50 → compute76m8 | `gray*` → `meta*` | 20.000000 |
| pc-health / single_bit_or_independent_levels | `u_managed` | control50 → compute76m8 | `pc_drop!=0 / pc_framing_sticky` → `pc_health_meta*` | review |
| media-reasons / single_bit_or_independent_levels | `u_managed` | compute76m8 → control50 | `tf_active/busy,score_running,record_enabled` → `reasons_meta*` | review |
| media-inhibit / reset_assert_release | `u_managed` | asynchronous reset/qualification → control50 | `media_busy_compute / rst_ni` → `media_busy_50*` | review |
| switch-busy / single_bit_or_independent_levels | `u_managed` | control50 → compute76m8 | `busy_o || quiesce_o` → `switch_busy_compute*` | review |
| health-tuple-payload / held_payload | `u_managed/health_snapshot` | selected_both → compute76m8 | `held_data*` → `destination_data*` | 13.020833 |
| health-tuple-request / single_bit_or_independent_levels | `u_managed/health_snapshot` | selected_both → compute76m8 | `request_toggle` → `req_meta` | review |
| health-tuple-ack / single_bit_or_independent_levels | `u_managed/health_snapshot` | compute76m8 → selected_both | `acknowledge_toggle` → `ack_meta` | review |
| health-tuple-reset / reset_assert_release | `u_managed/health_snapshot` | asynchronous reset/qualification → selected_both / compute76m8 | `common reset` → `source_release* / destination_release*` | review |
| display-tuple-payload / held_payload | `u_managed/display` | compute76m8 → control50 | `held_data*` → `destination_data*` | 20.000000 |
| display-tuple-request / single_bit_or_independent_levels | `u_managed/display` | compute76m8 → control50 | `request_toggle` → `req_meta` | review |
| display-tuple-ack / single_bit_or_independent_levels | `u_managed/display` | control50 → compute76m8 | `acknowledge_toggle` → `ack_meta` | review |
| display-tuple-reset / reset_assert_release | `u_managed/display` | asynchronous reset/qualification → compute76m8 / control50 | `common reset` → `source_release* / destination_release*` | review |
| display-loss / single_bit_or_independent_levels | `u_managed/display_observation_health` | compute76m8 → control50 | `loss_level*` → `loss_meta*` | review |
| controlled-reset / reset_assert_release | `u_managed` | asynchronous reset/qualification → control50 / compute76m8 | `runtime_reset_n` → `reset_50_pipe* / reset_compute_pipe*` | review |
| runtime-reset / reset_assert_release | `u_managed/runtime` | asynchronous reset/qualification → control50 / compute76m8 / memory100 | `runtime_reset_n` → `control_release* / compute_release* / memory_release*` | review |
| dsp-fault / single_bit_or_independent_levels | `u_managed/runtime` | compute76m8 → control50 | `compute_fault` → `fault_sync*` | review |
| all-quiet / single_bit_or_independent_levels | `u_managed/runtime` | compute76m8 → control50 | `all_quiet` → `quiet_sync*` | review |
| serial-prefill / single_bit_or_independent_levels | `u_managed/runtime` | selected_both → control50 | `serial_prefill` → `prefill_sync*` | review |
| serial-running / single_bit_or_independent_levels | `u_managed/runtime` | selected_both → control50 | `serial_running` → `running_sync*` | review |
| runtime-context-payload / held_payload | `u_managed/runtime` | control50 → compute76m8 | `context_payload*` → `pending_rate,pending_epoch*` | 13.020833 |
| runtime-context-request / single_bit_or_independent_levels | `u_managed/runtime` | control50 → compute76m8 | `context_toggle` → `context_sync*` | review |
| runtime-context-ack / single_bit_or_independent_levels | `u_managed/runtime` | compute76m8 → control50 | `context_ack` → `ack_sync*` | review |
| runtime-context-reset / reset_assert_release | `u_managed/runtime` | asynchronous reset/qualification → control50 / compute76m8 | `common reset` → `control_release* / compute_release*` | review |
| serial-quiesce / single_bit_or_independent_levels | `u_managed/runtime` | control50 → selected_both | `quiesce_o` → `serial_quiesce*` | review |
| serial-resume / single_bit_or_independent_levels | `u_managed/runtime` | control50 → selected_both | `!dac_mute` → `serial_resume*` | review |
| serial-context-ready / single_bit_or_independent_levels | `u_managed/runtime` | control50 → selected_both | `context_ready_o` → `serial_context_ready*` | review |
| serial-context-payload / held_payload | `u_managed/runtime` | control50 → selected_both | `clocks/transaction/staged_44k1_o,staged_epoch_o*` → `serial_rate,serial_epoch*` | 59.051398 |
| serial-safe / reset_assert_release | `u_managed/runtime` | asynchronous reset/qualification → selected_both | `audio_reset_n && !dsp_fault_o` → `serial_guard*,serial_reset_n,serial_quiesce*,serial_resume*,serial_context_ready*` | review |
| clock-reference_48_monitor / gray_counter_or_pointer | `u_managed/runtime/clocks/reference_48_monitor` | selected48 → control50 | `source_gray*` → `gray_meta*` | 81.380208 |
| clock-level-reference_48_monitor / single_bit_or_independent_levels | `u_managed/runtime/clocks/reference_48_monitor` | selected48 → control50 | `source_clk_i` → `level_meta` | review |
| clock-source-reset-reference_48_monitor / reset_assert_release | `u_managed/runtime/clocks/reference_48_monitor` | asynchronous reset/qualification → selected48 | `rst_ni` → `source_reset_pre*,source_reset_n` | review |
| clock-reference_44_monitor / gray_counter_or_pointer | `u_managed/runtime/clocks/reference_44_monitor` | selected44 → control50 | `source_gray*` → `gray_meta*` | 59.051398 |
| clock-level-reference_44_monitor / single_bit_or_independent_levels | `u_managed/runtime/clocks/reference_44_monitor` | selected44 → control50 | `source_clk_i` → `level_meta` | review |
| clock-source-reset-reference_44_monitor / reset_assert_release | `u_managed/runtime/clocks/reference_44_monitor` | asynchronous reset/qualification → selected44 | `rst_ni` → `source_reset_pre*,source_reset_n` | review |
| clock-selected_monitor / gray_counter_or_pointer | `u_managed/runtime/clocks/selected_monitor` | selected_both → control50 | `source_gray*` → `gray_meta*` | 59.051398 |
| clock-level-selected_monitor / single_bit_or_independent_levels | `u_managed/runtime/clocks/selected_monitor` | selected_both → control50 | `source_clk_i` → `level_meta` | review |
| clock-source-reset-selected_monitor / reset_assert_release | `u_managed/runtime/clocks/selected_monitor` | asynchronous reset/qualification → selected_both | `rst_ni` → `source_reset_pre*,source_reset_n` | review |
| clock-control-reset / reset_assert_release | `u_managed/runtime/clocks` | asynchronous reset/qualification → control50 | `rst_ni` → `control_reset_pre*,control_reset_n` | review |
| selected-clock-release / reset_assert_release | `u_managed/runtime/clocks` | asynchronous reset/qualification → selected_both | `rst_ni && requested_audio_reset_n && selected_qualified_o` → `reset_release*` | review |
| pcm-render-request-payload / held_payload | `u_managed/runtime/bridge` | selected_both → compute76m8 | `held_request*` → `render_44k1_o,render_epoch_o*,render_sequence_o*` | 13.020833 |
| pcm-render-request-request / single_bit_or_independent_levels | `u_managed/runtime/bridge` | selected_both → compute76m8 | `request_toggle` → `request_sync*` | review |
| pcm-render-request-ack / single_bit_or_independent_levels | `u_managed/runtime/bridge` | compute76m8 → selected_both | `request_ack` → `request_ack_sync*` | review |
| pcm-render-request-reset / reset_assert_release | `u_managed/runtime/bridge` | asynchronous reset/qualification → selected_both / compute76m8 | `common reset` → `serial_release*,serial_reset_n / compute_release*,compute_reset_n` | review |
| pcm-render-return-payload / held_payload | `u_managed/runtime/bridge` | compute76m8 → selected_both | `held_reply*` → `serializer sample capture` | 59.051398 |
| pcm-render-return-request / single_bit_or_independent_levels | `u_managed/runtime/bridge` | compute76m8 → selected_both | `reply_toggle` → `reply_sync*` | review |
| pcm-render-return-ack / single_bit_or_independent_levels | `u_managed/runtime/bridge` | selected_both → compute76m8 | `reply_ack` → `reply_ack_sync*` | review |
| pcm-render-return-reset / reset_assert_release | `u_managed/runtime/bridge` | asynchronous reset/qualification → compute76m8 / selected_both | `common reset` → `serial_release*,serial_reset_n / compute_release*,compute_reset_n` | review |
| pcm-source-quiet / single_bit_or_independent_levels | `u_managed/runtime/bridge` | selected_both → compute76m8 | `source_quiet` → `source_quiet_sync*` | review |
| pcm-quiesce-selected_both / single_bit_or_independent_levels | `u_managed/runtime/bridge` | control50 → selected_both | `quiesce_i` → `serial_quiesce_sync*` | review |
| pcm-quiesce-compute76m8 / single_bit_or_independent_levels | `u_managed/runtime/bridge` | control50 → compute76m8 | `quiesce_i` → `compute_quiesce_sync*` | review |
| delay-write-wptr / gray_counter_or_pointer | `u_managed/runtime/service/workstation/runtime_effects/effects/delay_stage/u_write_fifo` | compute76m8 → memory100 | `write_gray*` → `write_gray_meta*` | 13.020833 |
| delay-write-rptr / gray_counter_or_pointer | `u_managed/runtime/service/workstation/runtime_effects/effects/delay_stage/u_write_fifo` | memory100 → compute76m8 | `read_gray*` → `read_gray_meta*` | 10.000000 |
| delay-write-payload / fifo_payload | `u_managed/runtime/service/workstation/runtime_effects/effects/delay_stage/u_write_fifo` | compute76m8 → memory100 | `g_small_head/memory* or g_large_head/*memory*` → `destination consumer / g_large_head/even_q*,odd_q*` | 10.000000 |
| delay-read-wptr / gray_counter_or_pointer | `u_managed/runtime/service/workstation/runtime_effects/effects/delay_stage/u_read_fifo` | memory100 → compute76m8 | `write_gray*` → `write_gray_meta*` | 10.000000 |
| delay-read-rptr / gray_counter_or_pointer | `u_managed/runtime/service/workstation/runtime_effects/effects/delay_stage/u_read_fifo` | compute76m8 → memory100 | `read_gray*` → `read_gray_meta*` | 13.020833 |
| delay-read-payload / fifo_payload | `u_managed/runtime/service/workstation/runtime_effects/effects/delay_stage/u_read_fifo` | memory100 → compute76m8 | `g_small_head/memory* or g_large_head/*memory*` → `destination consumer / g_large_head/even_q*,odd_q*` | 13.020833 |
| delay-memory-heartbeat / single_bit_or_independent_levels | `u_managed/runtime/service/workstation/runtime_effects/effects/delay_stage` | memory100 → compute76m8 | `delay_dma/heartbeat_counter[4]` → `peer_meta` | review |
| delay-compute-heartbeat / single_bit_or_independent_levels | `u_managed/runtime/delay_dma` | compute76m8 → memory100 | `delay_stage/heartbeat_counter[4]` → `peer_meta` | review |
| delay-dma-fault / single_bit_or_independent_levels | `u_managed/runtime/service/workstation/runtime_effects/effects` | memory100 → compute76m8 | `delay_dma/fault_o` → `dma_fault_meta` | review |
| physical-observer-wptr / gray_counter_or_pointer | `u_managed/observation/frames` | selected_both → compute76m8 | `write_gray*` → `write_gray_meta*` | 59.051398 |
| physical-observer-rptr / gray_counter_or_pointer | `u_managed/observation/frames` | compute76m8 → selected_both | `read_gray*` → `read_gray_meta*` | 13.020833 |
| physical-observer-payload / fifo_payload | `u_managed/observation/frames` | selected_both → compute76m8 | `g_small_head/memory* or g_large_head/*memory*` → `destination consumer / g_large_head/even_q*,odd_q*` | 13.020833 |
| physical-observer-drops / gray_counter_or_pointer | `u_managed/observation/drops` | selected_both → compute76m8 | `gray*` → `meta*` | 59.051398 |
| ble-physical-tuple-payload / held_payload | `u_ble_pcm_cdc` | selected_both → control50 | `held_data*` → `destination_data*` | 20.000000 |
| ble-physical-tuple-request / single_bit_or_independent_levels | `u_ble_pcm_cdc` | selected_both → control50 | `request_toggle` → `req_meta` | review |
| ble-physical-tuple-ack / single_bit_or_independent_levels | `u_ble_pcm_cdc` | control50 → selected_both | `acknowledge_toggle` → `ack_meta` | review |
| ble-physical-tuple-reset / reset_assert_release | `u_ble_pcm_cdc` | asynchronous reset/qualification → selected_both / control50 | `common reset` → `source_release* / destination_release*` | review |
| display-memory-tuple-payload / held_payload | `u_video/u_runtime_display/observation` | control50 → memory100 | `held_data*` → `destination_data*` | 10.000000 |
| display-memory-tuple-request / single_bit_or_independent_levels | `u_video/u_runtime_display/observation` | control50 → memory100 | `request_toggle` → `req_meta` | review |
| display-memory-tuple-ack / single_bit_or_independent_levels | `u_video/u_runtime_display/observation` | memory100 → control50 | `acknowledge_toggle` → `ack_meta` | review |
| display-memory-tuple-reset / reset_assert_release | `u_video/u_runtime_display/observation` | asynchronous reset/qualification → control50 / memory100 | `common reset` → `source_release* / destination_release*` | review |
| display-memory-drops / gray_counter_or_pointer | `u_video/u_runtime_display/drops` | control50 → memory100 | `gray*` → `meta*` | 20.000000 |
| display-trust / single_bit_or_independent_levels | `u_video/u_runtime_display` | control50 → memory100 | `observation_trusted_i && !drop_wrap_fault` → `trusted_sync*` | review |
| display-local-reset / reset_assert_release | `u_video` | asynchronous reset/qualification → control50 / memory100 / video pixel | `shared_release=reset_n && memory_reset_n && video_source_reset_n` → `source_reset_pipe* / ui_reset_pipe* / pixel_reset_pipe*` | review |
| tf-control-payload / held_payload | `u_tf_audio` | control50 → compute76m8 | `held_control*` → `compute_control*` | 13.020833 |
| tf-control-request / single_bit_or_independent_levels | `u_tf_audio` | control50 → compute76m8 | `control_request` → `request_sync*` | review |
| tf-control-ack / single_bit_or_independent_levels | `u_tf_audio` | compute76m8 → control50 | `control_ack` → `ack_sync*` | review |
| tf-control-reset / reset_assert_release | `u_tf_audio` | asynchronous reset/qualification → control50 / compute76m8 | `common reset` → `held_control*,control_request,ack_sync* / request_sync*,control_ack,compute_control*` | review |
| tf-frames-wptr / gray_counter_or_pointer | `u_tf_audio/frames/frames` | control50 → compute76m8 | `write_gray*` → `write_gray_meta*` | 20.000000 |
| tf-frames-rptr / gray_counter_or_pointer | `u_tf_audio/frames/frames` | compute76m8 → control50 | `read_gray*` → `read_gray_meta*` | 13.020833 |
| tf-frames-payload / fifo_payload | `u_tf_audio/frames/frames` | control50 → compute76m8 | `g_small_head/memory* or g_large_head/*memory*` → `destination consumer / g_large_head/even_q*,odd_q*` | 13.020833 |
| tf-generation / gray_counter_or_pointer | `u_tf_audio/frames` | control50 → compute76m8 | `source_generation_gray*` → `generation_meta*` | 20.000000 |
| tf-generation-ack / gray_counter_or_pointer | `u_tf_audio/frames` | compute76m8 → control50 | `ack_gray*` → `ack_meta*` | 13.020833 |
| tf-source-alive / single_bit_or_independent_levels | `u_tf_audio/frames` | control50 → compute76m8 | `source_seen_edge` → `source_alive_sync*` | review |
| tf-expected-valid / single_bit_or_independent_levels | `u_tf_audio/frames` | compute76m8 → control50 | `expected_generation_valid_o` → `expected_valid_sync*` | review |
| tf-quiesce / single_bit_or_independent_levels | `u_tf_audio/frames` | control50 → compute76m8 | `source_quiesce_i` → `quiesce_sync*` | review |
| tf-quiet / single_bit_or_independent_levels | `u_tf_audio/frames` | compute76m8 → control50 | `media_quiescent_o` → `quiet_sync*` | review |
| tf-quiesce-return / single_bit_or_independent_levels | `u_tf_audio/frames` | compute76m8 → control50 | `quiesce_sync[1]` → `quiesce_return_sync*` | review |
| tf-memory-stop / single_bit_or_independent_levels | `u_tf_audio` | control50 → memory100 | `memory_stop` → `memory_gate_sync*` | review |
| tf-memory-open / single_bit_or_independent_levels | `u_tf_audio` | memory100 → control50 | `!memory_gate` → `memory_open_sync*` | review |
| tf-memory-quiet / single_bit_or_independent_levels | `u_tf_audio` | memory100 → control50 | `memory_gate && !memory_read_pending` → `memory_quiet_sync*` | review |
| tf-memory-ready / single_bit_or_independent_levels | `u_tf_audio` | memory100/backend qualification → control50 | `memory_ready_i && memory_reset_ni` → `memory_ready_sync*` | review |
| tf-busy-inhibit / reset_assert_release | `u_tf_audio` | asynchronous reset/qualification → compute76m8 | `busy_50_o / rst_ni` → `busy_release*` | review |
| tf-byte-capture-wptr / gray_counter_or_pointer | `u_tf_audio/path/u_capture_fifo` | control50 → memory100 | `wr_gray*` → `wr_gray_r1*` | 20.000000 |
| tf-byte-capture-rptr / gray_counter_or_pointer | `u_tf_audio/path/u_capture_fifo` | memory100 → control50 | `rd_gray*` → `rd_gray_w1*` | 10.000000 |
| tf-byte-capture-clear-control50 / single_bit_or_independent_levels | `u_tf_audio/path/u_capture_fifo` | control50 → control50 | `path/restart_toggle` → `clear_wr_meta` | review |
| tf-byte-capture-clear-memory100 / single_bit_or_independent_levels | `u_tf_audio/path/u_capture_fifo` | control50 → memory100 | `path/restart_toggle` → `clear_rd_meta` | review |
| tf-byte-capture-payload / fifo_payload | `u_tf_audio/path/u_capture_fifo` | control50 → memory100 | `mem*` → `rd_data*` | 10.000000 |
| tf-byte-playback-wptr / gray_counter_or_pointer | `u_tf_audio/path/u_playback_fifo` | memory100 → control50 | `wr_gray*` → `wr_gray_r1*` | 10.000000 |
| tf-byte-playback-rptr / gray_counter_or_pointer | `u_tf_audio/path/u_playback_fifo` | control50 → memory100 | `rd_gray*` → `rd_gray_w1*` | 20.000000 |
| tf-byte-playback-clear-memory100 / single_bit_or_independent_levels | `u_tf_audio/path/u_playback_fifo` | control50 → memory100 | `path/restart_toggle` → `clear_wr_meta` | review |
| tf-byte-playback-clear-control50 / single_bit_or_independent_levels | `u_tf_audio/path/u_playback_fifo` | control50 → control50 | `path/restart_toggle` → `clear_rd_meta` | review |
| tf-byte-playback-payload / fifo_payload | `u_tf_audio/path/u_playback_fifo` | memory100 → control50 | `mem*` → `rd_data*` | 20.000000 |
| tf-capture-eof / single_bit_or_independent_levels | `u_tf_audio/path/u_dma` | control50 → memory100 | `path/capture_done_toggle` → `capture_meta` | review |
| tf-path-restart / single_bit_or_independent_levels | `u_tf_audio/path/u_dma` | control50 → memory100 | `path/restart_toggle` → `restart_meta` | review |
| tf-playback-start / single_bit_or_independent_levels | `u_tf_audio/path` | memory100 → control50 | `u_dma/playback_start_toggle` → `pb_meta` | review |
| tf-playback-done / single_bit_or_independent_levels | `u_tf_audio/path` | memory100 → control50 | `u_dma/playback_done_toggle` → `pb_done_meta` | review |
| tf-file-status / single_bit_or_independent_levels | `u_tf_audio/path` | memory100 → control50 | `u_dma/capacity_error,bank0_valid,bank1_valid,file_size_valid` → `ddr_error_meta,bank0_meta,bank1_meta,file_size_valid_meta` | review |
| tf-staged-size / held_status_payload | `u_tf_audio/path` | memory100 → control50 | `u_dma/staged_file_size*` → `file_size_meta*` | 20.000000 |
| tf-input-size / unused_or_conditional_payload | `u_tf_audio/path/u_dma` | control50 → memory100 | `path/file_size_latched*` → `size_meta*` | review |
| tf-scope-control-payload / held_payload | `u_tf_control_cdc` | compute76m8 → control50 | `held_data*` → `destination_data*` | 20.000000 |
| tf-scope-control-request / single_bit_or_independent_levels | `u_tf_control_cdc` | compute76m8 → control50 | `request_toggle` → `req_meta` | review |
| tf-scope-control-ack / single_bit_or_independent_levels | `u_tf_control_cdc` | control50 → compute76m8 | `acknowledge_toggle` → `ack_meta` | review |
| tf-scope-control-reset / reset_assert_release | `u_tf_control_cdc` | asynchronous reset/qualification → compute76m8 / control50 | `common reset` → `source_release* / destination_release*` | review |
| service-feedback-payload / held_payload | `u_service_push_cdc` | compute76m8 → usb48 | `held_data*` → `destination_data*` | 20.833333 |
| service-feedback-request / single_bit_or_independent_levels | `u_service_push_cdc` | compute76m8 → usb48 | `request_toggle` → `req_meta` | review |
| service-feedback-ack / single_bit_or_independent_levels | `u_service_push_cdc` | usb48 → compute76m8 | `acknowledge_toggle` → `ack_meta` | review |
| service-feedback-reset / reset_assert_release | `u_service_push_cdc` | asynchronous reset/qualification → compute76m8 / usb48 | `common reset` → `source_release* / destination_release*` | review |
| display-feedback-payload / held_payload | `u_display_push_cdc` | memory100 → usb48 | `held_data*` → `destination_data*` | 20.833333 |
| display-feedback-request / single_bit_or_independent_levels | `u_display_push_cdc` | memory100 → usb48 | `request_toggle` → `req_meta` | review |
| display-feedback-ack / single_bit_or_independent_levels | `u_display_push_cdc` | usb48 → memory100 | `acknowledge_toggle` → `ack_meta` | review |
| display-feedback-reset / reset_assert_release | `u_display_push_cdc` | asynchronous reset/qualification → memory100 / usb48 | `common reset` → `source_release* / destination_release*` | review |
| native-usb-runtime-reset / reset_assert_release | `u_native_usb/input_owner` | asynchronous reset/qualification → usb48 / compute76m8 | `runtime_reset_n AND usb reset` → `event_release*,audio_release*,queue_release*` | review |

The JSON retains per-record protocol notes, activity/pruning expectations, skew bounds and explicit pending fields alongside the second-netlist mapping. Widths include33-bit runtime context,65-bit render request,98-bit render return/physical PCM,203-bit completed display snapshot,204-bit receipt-trusted display tuple,36-bit TF control,85-bit TF PCM and65-bit delay FIFO entries. These contracts are distinct from18-bit input events, APB command acceptance and background object results.

## Findings and unfinished physical gates

- All 21 Gray groups and 400 source/first-stage bits map to the exact second VG; routed flight/skew and actual SDC query resolution remain unverified.
- Runtime notes/parameters/epoch reset only through common AND sticky started. Compute PLL/readiness instead closes/mutes permanently.
- The runtime-only native USB adapter uses `runtime_reset_n`, avoiding synthetic attach/default replay on compute PLL qualification recovery. Dedicated adapter coverage is now reported in `WORKSTATION_USB_RUNTIME_RESET_ISOLATION_20261030.md`; hotplug entirely during stopped compute remains a separate queue/reset gap.
- Display effect mask/order now share203-bit completed-frame mailbox, rather than independent naked multibit synchronizers.
- In this exact second snapshot, TF `memory_quiet` is a combinational aggregate crossing; register it or prove protocol prevents hazardous sampled transitions before physical acceptance. A later repair requires a new source/netlist identity.
- Legacy TF byte FIFO clear resets Gray pointers non-unit to zero; only explicit held/drained clear protocol makes restart safe, source-period constraints alone do not prove restart.
- Top custom MIDI input tied1 and unused reference monitor stopped-low outputs may cause endpoint pruning; require mapped constant/unused evidence for each missing endpoint.
- TF DMA input size_meta/size_sync appear functionally unused; document pruning if absent, do not invent data authority.

The compute output-safe chain and guard hard SMUTE are output protection, not DSP/session reset. The guard tracks actual memory progress and permanently quarantines requests, acceptance and responses; a new object, epoch, CPU reset or backend return cannot rearm. Display-local shared UI/video resets may invalidate observations while the runtime identity survives.

The source audit of TF memory quiet/clear is intentionally conservative: functional directed tests do not settle combinational CDC hazards or simultaneous restart pointer jumps. Do not mark these physical paths accepted merely because their ordinary payloads cross through maintained FIFOs.

The original shared USB/video/DDR/CPU IP internal inventories remain separate. The parent has 157 shared CDC commands; runtime retains 103 and explicitly omits 54 mixed old-hierarchy commands. All retained commands and applicable endpoints inside omitted commands must be audited against the new complete netlist; this report does not expand source scope into vendor IP or silently cut all clocks. Unused custom MIDI/reference-level/size paths need explicit constant or unused evidence if optimized away.

Before a physical candidate can pass, complete all non-Gray endpoint and merged/pruned mapping in the exact VG, validate every SDC query, preserve source-identity and vendor opacity evidence, then measure routed delay/skew/reset paths and both selected modes. Full TF fault integration, stopped-compute USB hotplug resolution and physical board tests remain outstanding. The real controlled+guard owner6 fixture is reported separately; it is not a CDC or PLL physical proof.

Rollback is removal of these two source-inventory reports only. No build input policy, constraint, accepted profile or board state changed.

Parent verification reran the fresh parser against the sealed second VG and all 560 inputs, reproducing 21 groups/400 unique Gray first stages, 938 direct payload links and six FIFO storage groups. An independent check also confirmed all 21 proposed max-flight/skew values equal their source period, using 59.051398 ns for the faster selected-clock mode. These results establish identity/connectivity only; the 129 non-Gray records and all physical gates remain incomplete.
