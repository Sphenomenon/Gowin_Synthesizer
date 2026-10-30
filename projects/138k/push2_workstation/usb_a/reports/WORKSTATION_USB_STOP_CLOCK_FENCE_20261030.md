# USB event queue fence while compute is stopped — 2026-10-30

## Result and selection

The opt-in queue fence passes the real MMIO service adapter → maintained USB owner → original generated asynchronous FIFO → real session regression. A detach/reattach or PANIC that completes while compute is stopped cannot make pre-boundary FIFO RAM contents appear as new events after compute resumes. Normal event stores remain stalled until the destination has completed both the reset hold and drain acknowledgement.

This is an offline source candidate. `STOP_CLOCK_QUEUE_FENCE` defaults to zero in both the owner and wrapper. This run verifies the option directly and records that the native top has **not yet selected it** (`native_profile_opt_in_verified: false`). Native top selection, source-profile locking, synthesis, routed timing/CDC, resources, SRAM deployment and board acceptance remain later stages. No accepted profile or generated/vendor FIFO bytes were changed by this work.

The subsequent parent run explicitly selects `.STOP_CLOCK_QUEUE_FENCE(1)` only inside the top's `WORKSTATION_RUNTIME_NATIVE` branch and repeats the full regression with `--require-native-opt-in`. It passes with the same enabled/legacy metrics and `native_profile_opt_in_verified: true`. Its distinct identity is `native-usb-stop-clock-fence-offline-v1-6c62d7d5926489cc`; `workstation_task_20261030/usb_stop_clock_fence_native_selection.json` records the final maintained top, complete source hashes, explicit revision4-v2 support paths and parent checks. The child identity above remains bound to its earlier top and revision2 support. The native selection still requires a newly locked profile and new synthesis; it is not included in the historical revision4 bitstream identity.

The existing reset-isolation evidence remains separate in `WORKSTATION_USB_RUNTIME_RESET_ISOLATION_20261030.md` and `workstation_task_20261030/usb_runtime_reset_isolation.json`; those historical files were not rewritten.

## Source identity and reproduction

- Identity: `native-usb-stop-clock-fence-offline-v1-220c00c7113b8aa2`.
- Complete source-set SHA-256: `220c00c7113b8aa2853e3a2b04743675b7babfc9ff951659cfa171c2563a6c77`.
- Verification JSON SHA-256: `88b3e50f960e0b9bc5b3e7f5384e7b1f6c360f9e1ddcf16bcb158d38f6408a38`.
- Versioned evidence: `workstation_task_20261030/usb_stop_clock_fence.json`, an exact copy of the run's `verification.json`.
- Local run: `/tmp/workstation-usb-stop-clock-fence-20261030-v1/`.
- Explicit prepared support: `/Users/sphenicidition/.cache/gw138k-task-20261030/clean-rev2-profile-candidate/workstation/Prj1`.
- Original generated event FIFO SHA-256, checked against the frozen reset-isolation evidence: `2084bead34bf421610fd20489ece66601823b87f72887228be25de5374a956c6`.
- Bitstream identity: none; no synthesis or programming in this verification stage.

```sh
python3 projects/138k/push2_workstation/usb_a/sim/usb2/run_workstation_usb_stop_clock_fence.py \
  --project /Users/sphenicidition/.cache/gw138k-task-20261030/clean-rev2-profile-candidate/workstation/Prj1 \
  --output /tmp/workstation-usb-stop-clock-fence-20261030-v1
```

The output directory must be new. After the native composition explicitly selects `.STOP_CLOCK_QUEUE_FENCE(1)`, repeat in a new output directory with `--require-native-opt-in`; it fails if the preprocessed top has not selected that value. The runner hashes the top, owner, wrapper, testbenches, runners, contract, frozen evidence and explicit prepared support/metadata, then rejects source drift during verification.

Parent reproduction:

```sh
python3 projects/138k/push2_workstation/usb_a/sim/usb2/run_workstation_usb_stop_clock_fence.py \
  --project /Users/sphenicidition/.cache/gw138k-task-20261030/native-runtime-profile-rev4-v2/workstation/Prj1 \
  --output /Users/sphenicidition/.cache/gw138k-task-20261030/usb-stop-clock-fence-parent-final \
  --require-native-opt-in
```

The parent additionally compares normalized preprocessed top tokens before and after the selection for both macro-off Dock and custom-board providers; both are identical. The ten accepted/pinned source-selection regressions pass. These checks preserve source-selection boundaries and default behavior; they do not claim that every legacy project using the default parameter was rebuilt.

## Implementation and timing budget

The option belongs to `push2_usb_a_control`; `workstation_usb2_input` only forwards the parameter. The generated FIFO keeps its original reset/read/write ports, and the 18-bit event/lifecycle format and session application rules are unchanged. `rtl/workstation/USB_INPUT_QUEUE_FENCE.md` records the maintained boundary contract.

The original FIFO releases read reset after two resumed destination edges. Its producer pointer takes two synchronization edges and a third edge before read logic can use zero. A short source reset that ends before destination resumes can therefore release read reset before the reset producer pointer becomes usable, allowing old RAM contents to replay. The default-zero negative control reproduces this failure.

The selected owner holds the original FIFO reset for six actual compute edges after the source boundary. Producer zero is usable by edge three while the read pointer stays reset through edges three to six. A further six actual compute edges drain the buffered output and keep normal data fenced. The ready level then uses the existing two-USB-edge write release. A second stop inside either interval cannot finish its edge count or acknowledge fresh stores early.

At continuous USB 48MHz and compute at most 76.8MHz, zero read pointer by edge three precedes destination ready at edge twelve by at least nine compute periods, `117.1875ns`. This exceeds both the generated pointer return/application budget of three USB edges (`62.5ns`) and the buffered-consume return path's four USB edges (`83.333333ns`). Two additional USB edges precede write release. At each first fresh write the test checks the actual generated read/write pointers, buffered-consume feedback and released read reset; this is not solely a timing-delay assertion.

Control MMIO and lifecycle cancellation retain their existing path. Repeated source connection changes while destination is stopped restart the queue fence, while the existing session still coalesces detached/latest-attachment state. This option does not introduce a connection event log or alter PANIC toggle semantics.

## Verification

The test uses the real service adapter, maintained owner, original generated FIFO and real `workstation_session`, including its 13 initialization events per attachment. Final held-note and volume application are explicitly modeled. It exercises complete detach/reattach while compute is absent, PANIC while compute is absent, and two repeated detach/reattach pulses while compute remains absent. For all three cases, fresh MMIO data is attempted during the stopped interval and must not be acknowledged. Compute then stops again after two hold edges and after two drain edges.

| Metric | Fence enabled | Default-zero negative control |
| --- | ---: | ---: |
| Attach / barrier / detach / PANIC | 3 / 4 / 2 / 1 | 3 / 4 / 2 / 1 |
| Initialization events | 39 | 39 |
| Stale post-boundary notes | 0 | 8 |
| Fresh note applications | 3 | 6 (replay included) |
| Stores blocked while stopped | 3 | 3 |
| Stops inside reset hold / drain | 3 / 3 | 0 / 0 |
| First fresh write pointer checks | 3 | 0 |
| Completed source MMIO stores | 18 | 18 |

The separate old reset-isolation runner also passes on the default-zero RTL with metrics exactly equal to its frozen original evidence: current wiring has two attaches, three barriers, one detach, one PANIC, 26 defaults, two retained queued events after ordinary clock recovery and five note applications. Its old PLL-qualified reset negative control still produces two phantom attaches, 26 extra defaults and 123 note applications. This preserves the earlier reset fix and default behavior while adding the explicit option.

The directed build reports zero owned RTL/testbench warnings and no `UNOPTFLAT`. Existing support-source width warnings are counted in JSON (34 truncation, 27 expansion). Python syntax checks and `git diff --check` pass.

## Limits and rollback

This evidence does not exercise ULPI traffic, USB enumeration, the DSP/audio serial path, physical PLL behavior, routed timing/CDC, FPGA resource use or hardware. USB must continue at 48MHz for the stated return-pointer budget; independently stopping USB without reset belongs to a separate recovery contract.

For rollback before deployment, leave or restore the native selection to the default-zero value and prepare a new source-identified candidate through the existing profile entry point. Do not reuse this identity for changed inputs. Any later SRAM deployment needs its own bitstream identity, readback and physical acceptance evidence; Flash is not part of this stage.
