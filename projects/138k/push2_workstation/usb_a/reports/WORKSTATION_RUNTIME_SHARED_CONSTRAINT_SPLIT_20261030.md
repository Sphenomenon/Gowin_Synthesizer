# Runtime shared CDC query member preservation — 2026-10-30

The runtime constraint selector now removes replaced hierarchy members from each Tcl object list independently. The previous whole-line filter dropped three commands that also contained surviving CPU/USB endpoints. The locked parent has 157 shared CDC commands; the new selection retains 106 (103 unchanged and three adapted) and omits 51 whose query side becomes empty. It does not rebind old runtime endpoints to new owners or change the default/accepted selection.

Evidence identity: `runtime-shared-constraint-split-v1-e632045a177875e1`. `workstation_task_20261030/runtime_shared_constraint_split.json` records the original commands, removed members, selected commands, all omissions, source hashes and static matched pins. The selected shared SDC is a new input requiring a new profile identity; the existing revision4 candidate remains immutable.

| Restored command destination | Actual revision4-v2 pins | Clock |
| --- | ---: | --- |
| `u_runtime/u_cpu_cdc/{source_release,destination_release}*/CLEAR` | 3 + 3 | CPU RAM 50 MHz / control 50 MHz |
| `u_runtime/u_cpu_cdc/{req_meta,ack_meta}*/D` | 1 + 1 | control 50 MHz / CPU RAM 50 MHz |
| `u_native_usb/input_owner/analysis_done_meta*/D` | 1 | USB 48 MHz |

These are inherited first-stage/reset exceptions for unchanged owners. The static source-netlist model finds all nine restored pins in the exact VG `2319746ad8eabba1e19721908402dd0c25bd91aba52b896650d82153e6c4e3da`. The audit first checks the completed synthesis process against the prepared profile's complete 560-input keys/hashes and independently hashes the files, then repeats the seal after parsing. It does not use the current dirty product RTL to interpret this historical VG. Pin existence and clock identity do not establish physical reset release, metastability performance or tool-side query resolution.

The selector accepts only the parent's simple braced `get_regs`, `get_pins`, `get_ports` and `get_clocks` lists. It fails if a retired hierarchy remains in unsupported syntax. If either source or destination query becomes empty, the whole command is omitted with an explicit inventory entry; it cannot turn into an unbounded one-sided exception. Surviving commands retain their original delay/options and ordering.

Validation:

```sh
python3 projects/138k/push2_workstation/usb_a/sim/test_workstation_runtime_sources.py -v
python3 projects/138k/push2_workstation/usb_a/sim/test_current_workstation_sources.py -v
python3 /Users/sphenicidition/.cache/gw138k-task-20261030/audit_runtime_shared_constraint_split.py
```

The runtime-source suite passes ten tests and explicitly skips its complete prepared-source audit because the historical profile is intentionally no longer the current source lock. Four targeted cases cover mixed lists on both sides, empty-side omission, unsupported query rejection and reconstruction of the exact locked parent from `resource_rework_route0` plus the maintained Gray aliases. The ten accepted/pinned source-selection tests also pass. Complete source preparation/preprocessing will run after the reviewed product changes receive a new profile lock.

No EDA, SRAM, Flash or board action occurred in this phase. The remaining runtime CDC inventory, stale BLE reset aliases and legacy TF-run selector, Gray/held-payload bounds, actual Gowin queries and routed timing remain separate gates. `constraints_complete` and deployment permission stay false. Rollback is restoration of the previous runtime selector followed by a newly identified preparation; frozen baselines and historical evidence are unchanged.
