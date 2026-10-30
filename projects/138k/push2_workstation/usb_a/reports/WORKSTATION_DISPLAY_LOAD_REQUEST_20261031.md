# Runtime display registered load boundary — 2026-10-31

The completed 18ed synthesis report's slowest path starts at
`u_video/u_runtime_display/drops/sync_value_12_s0` and ends at
`u_video/u_runtime_display/reader/state_3_s0/D`: 24 logic levels, slack
−7.184 ns, arrival 17.767 ns, required 10.584 ns in the memory 100 MHz domain.
The original owning source SHA256 is
`2df452ca8789ba882f5011865e877564988d2f478628cef0bc2f5ac8709f2aeb`.
An independent audit checked all 104 reported path rows against the actual
VG's strict named-port parser and inter-cell nets. No timing exception changed.

`workstation_display_runtime.sv` now registers current-context load qualification
before the real reader's start/state decode. Acceptance checks the registered
request, enabled/live transaction, reader idle/loading and raster busy/start.
This adds one memory clock of request latency. Source-context loss still
immediately revokes current-image/raster/summary eligibility. A loss arriving
on the acceptance edge can launch at most one old private-cache read, bounded
by the existing minor1 reader to 365 ordered BL8 requests with one outstanding;
its completion fails the full context/live/loading validation and is discarded.
No audio clock or sample schedule depends on this display transaction.

A separate export-live bit keeps disable/context cancellation sticky until the
next actual writer export starts. Disable clears pending/request/loading/image
eligibility; summary also gates enabled directly. A late old writer tail or
reader result cannot become publishable after re-enable. Successful completion
requires an accepted loading token, enabled/live export, reader success and
current rate/epoch/local cancellation generation. Failed reloads within the
same context retain the previous validated image. Ports, minor1 metadata,
common parameter authority and the immutable 18ed stage remain unchanged.

Validation from isolated base `eff1d7d34d243b93d008141b70e032271cf449b4`:

- Real runtime analysis/DDR/cache: 6 publications, 9 commits, 128702 atomic
  tuples, 1024 waveform samples, 131072 XY pixels, 1024 FFT columns and final
  CDC-loss cancellation; three complete HDMI macro/owner8 elaborations pass.
- Minor1 transport, minor0 exact compatibility and real atomic-context FFT/
  waveform/XY analysis pass at both rates; no writer/reader/metadata change.
- Complete shared raster/default parity: 2073600 pixels, known/negative
  spectrum/XY checks, output stalls and 365 real reader requests pass.
- New directed real writer/reader regression: 12 race cases, 47 assertions,
  10 accepted loads and 3286 DDR reads. It covers one-cycle request latency,
  raster busy/start, each context tag, acceptance-edge loss, disabled pending,
  reader flight and writer tail, failed reload retention and unsolicited done.
  Four temporary behavioral mutants must fail the corresponding assertions.
- Accepted source boundary: 17 tests pass. Profile/runtime/counter/precision:
  46 tests pass with 18 existing optional stage cases skipped. Four profile
  changes retain configurations/revisions and update only the owning RTL hash; the separate source seal binds the
  updated contract and new validation fixtures.

New owning source SHA256:
`1e5bc96dc3c96907f9f83e89be604dc6a846867855844ce984bc8d6a0023952d`.
Source evidence is sealed separately under
`~/.cache/gw138k-task-20261030/runtime-display-load-request-v1/`.
The reusable race command is:

```sh
python3 projects/138k/push2_workstation/usb_a/sim/display/run_workstation_display_load_request.py \
  --project <fixed-prepared-Prj1> --output <new-evidence-directory>
```

No synthesis, P&R, SRAM/Flash or board operation occurred in this source phase.
Timing improvement, physical CDC/resource checks and hardware behavior require
a separately identified candidate. The frozen 18ed result is historical
comparison evidence; this changed source cannot reuse its candidate identity.
Rollback restores the prior owning module and profile source hash; accepted
and pinned profiles retain their existing source selection policies.
