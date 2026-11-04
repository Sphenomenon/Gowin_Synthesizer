# Repository Engineering Rules

## Read Before Changing

- Inspect the selected `projects/138k/push2_workstation/usb_a/boards/custom_138k/workstation_profile*.json` and `tools/workstation_profile.py` for source policies and provenance. Inspect the owning RTL modules for runtime boundaries.
- Inspect maintained USB PL and BLE protocol definitions and board composition before changing cross-board behavior; do not invent a competing wire specification.
- Check `git status` before editing. Preserve unrelated and untracked user work, including historical architecture notes and reports.

## Scope And Ownership

- `projects/138k/` owns the workstation, common parameters, audio, recognition, and public display state.
- Push and `projects/25k/example/MIDI_KEYBOARD/` are interaction adapters. Push and 25K currently alternate on the same 138K USB-A port; do not assume simultaneous attachment or USB High-Speed support.
- `projects/25k/example/RTL8723DS_PROTOCOL/` is an independently validated BLE business-protocol project, not an integrated 138K recording backend.
- `clients/android/` keeps its existing dependency direction: app → data → ble → protocol. Do not put packet encoding in UI code.
- Common parameters need one authoritative application point. Local controls, CPU services, and displays must not introduce parallel authoritative copies.
- Keep top-level integration focused on composition, interfaces, CDC, and readiness. Add business behavior inside its owning subsystem.
- For the resource-timing development candidate, maintain the native composition in `usb_a/rtl/workstation/`; inspect its versioned composition owners. Session fencing belongs to `rtl/control/workstation_session.sv`, committed parameter state to `rtl/control/workstation_parameters.sv`, playback policy to `rtl/services/workstation_playback_service.sv`, cancellation-to-serial frame delivery to `rtl/audio/workstation_frame_delivery.sv`, and final serial output/tap selection to `rtl/audio/workstation_output_router.sv`. Do not reintroduce text-generated implementations of these boundaries or silently switch accepted profiles to the resource candidate.
- Do not stop the audio sample schedule for display updates, file operations, recognition, BLE, or downloads. Specify overflow, cancellation, and failure behavior at each boundary.

## Build Provenance

- Inspect the selected build profile before changing RTL. Active `usb_a/rtl` files are not automatically the inputs consumed by accepted full83 builds.
- `build.py --current-workstation`, its pinned `--cnn-timing85` option, and `--resource-rework --resource-timing` have different source policies. Do not silently mix them.
- The current complete-workstation profiles reconstruct locked inputs from `usb_a/baselines/`; inspect `baselines/index.json` and the selected descriptor before changing source selection. Missing or changed locked inputs must fail, never fall back to private historical staging.
- Legacy numbered builders still have historical local dependencies. Preserve their checks and evidence; do not treat them as the default production path or remove their inputs opportunistically.
- Do not add another long-lived numbered production builder or copy a complete project to deliver a feature. Prefer the existing entry point, explicit configurations, and reusable build functions.
- Experiments may use separate outputs, but must not become the sole undocumented production input. Record their source policy and integration or retirement criteria.
- Move stable first-party changes toward versioned source. Any temporary text overlay needs checked input identity, exact anchors, failure on drift, targeted verification, and an exit plan.
- Do not modify frozen baselines, vendor bytes, original manifests, or historical evidence to make a changed build pass. Keep adaptations separate and retain license and line-ending requirements.
- New code and documentation use `projects/138k/` and `projects/25k/`; preserve historical paths and the migration compatibility link where they are evidence.

## Contracts And Resource Limits

- Preserve the current 18-bit event layout and existing lifecycle/PANIC semantics unless an explicit interface change is part of the task. Source/session/revision metadata is not implicitly present in that layout.
- Use `projects/138k/push2_workstation/usb_a/rtl/ddr_address_map.vh` as the DDR allocation authority. Distinguish byte addresses from native word addresses and account for existing clients before allocating storage.
- Keep real-time streams, command acceptance/application, background task results, and display snapshots as distinct contracts.
- Retain routed timing, CDC, PLL, feature-preservation, and resource checks. Do not hide violations by relaxing clocks or false paths, removing features, or confusing synthesis-equivalent and physical BSRAM counts.
- Require separate audio-path, protocol, timing, and hardware checks for D mode, long recording, and 138K BLE business integration.

## Validation And Delivery

- Start with targeted tests for the modified subsystem. Build preparation, synthesis, P&R, and physical board tests are different validation stages.
- For accepted input-boundary changes, run `python3 projects/138k/push2_workstation/usb_a/sim/test_current_workstation_sources.py` and the relevant additional regression.
- For baseline reconstruction changes, also run the firmware and baseline tests. Use `GW138K_VERIFY_CLEAN_PREPARE=1` with `sim/test_workstation_baselines.py` to verify the three complete-workstation prepare paths without private staging inputs.
- A tool exit code or `release_ready` field alone is not hardware acceptance. Distinguish source implementation, offline verification, hardware acceptance, SRAM deployment, and Flash deployment.
- Use dated structured candidate/deployment evidence under `usb_a/reports/`; do not infer the current board from historical P28/P29 records or a local latest-build pointer.
- New candidates need explicit source identity, configuration, input hashes, bitstream identity, validation scope, remaining gaps, and rollback information. Do not reuse an accepted identity for changed release inputs.
- Do not program SRAM, write Flash, or operate a board merely because a build passed. Those actions require explicit user authorization and separate readback/acceptance evidence.
- Keep generated implementation databases, bitstreams, waves, and captures out of source changes. Do not delete ignored historical trees while existing builders still depend on them.
- Update stable architecture only when boundaries change; put experiment logs and version-specific evidence in reports instead of appending them indefinitely to entry-point documentation.
