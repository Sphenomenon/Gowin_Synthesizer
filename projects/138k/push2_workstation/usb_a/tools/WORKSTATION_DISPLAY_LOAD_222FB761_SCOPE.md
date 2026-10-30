# Fixed 222fb761 structural review scope

This independent audit helper set selects only
`custom138k-workstation-r00-no-local-panel-v1-222fb761448fb6c0`, VG
`f621fcbecb79012c0486e248a1cc686437b9d11ab887c22b2c8554a62f8b49af`.
Its compiled source is commit `9bc8fc5063f34c914553e725264a0566eba7cea0`.
The helper commit is a later, separate identity and is not a synthesis input.

The old serial, prefix, Chorus and pitch/FIFO scope files remain unchanged and
continue to reject a different candidate. The new named copies retain their
strict algorithms and use explicit new source, compilation and closure
declarations. No graph producer is guessed from a receiving pin to make a
missing declared producer pass. No SDC is generated or installed.

The retained scope inventories 13 phase1 and 42 raw source fanout groups and
the 88 shared installed constraints. It checks registered producers, declared
first and second receiving stages, local clocks/CE/reset structure and complete
FF D/CE/CLEAR, primitive and top-output fanout. Exact endpoint declarations
include the current recording backend D/CE mapping and registered display
load-request consumer. Additional native Delay mapping and TF/counter semantic
review have separate receipts.

Run the public entry with `--project <fixed-stage>/workstation/Prj1`,
`--synthesis-evidence <fixed-stage>/runtime_synthesis_evidence/process.json`,
`--output <fresh-report>` and
`--precision-profile runtime-r00-no-local-panel-display-load-222fb761-v1`:

```
python3 -B tools/workstation_display_load_222fb761_shared.py ...
```

Set `GW138K_PITCH_FIFO_CDC_STAGE`, `GW138K_PITCH_FIFO_CDC_PROCESS` and optionally
`GW138K_PITCH_FIFO_CDC_TEST_EVIDENCE`, then run
`sim/test_workstation_display_load_222fb761_scope.py` for the adapted source,
prepared-input and actual-graph negative controls. The environment variable
names preserve the test harness ABI; the explicit new scope gates the candidate.

This is a fixed experiment helper set, not another production build entry.
Before another candidate, either integrate this declaration into a maintained
explicit scope catalog with equivalent negative controls or retire these
candidate-specific copies. Do not replace a VG hash and retain acceptance.

Complete CDC/reset, payload flight and setup/hold, RAM ownership/data arcs,
PLL/routed STA, physical resources, hardware and deployment remain unaccepted.
