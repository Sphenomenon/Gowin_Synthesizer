# Runtime clock and DCS source topology — 2026-10-30

The explicit runtime candidate's clock declarations and static source-netlist connections pass this bounded audit. The new tool reuses the maintained `workstation_custom_clocks.audit_clocks` for the old 13-clock prefix, then checks the second reference, two DCS modes, visible primitives, select registers and audio consumers. This is not STA, a physical clock-tree check or proof of dynamic DCS behavior. The default/accepted build profiles, frozen inputs, runtime RTL and existing CDC report are unchanged by this phase.

Evidence identity: `runtime-clock-source-audit-v1-4cf8f6511f055554`. The exact target is `/Users/sphenicidition/.cache/gw138k-task-20261030/runtime-rev4-synthesis-41e653fe/workstation/Prj1/impl/gwsynthesis/custom_138k_integration.vg`, SHA-256 `2319746ad8eabba1e19721908402dd0c25bd91aba52b896650d82153e6c4e3da`. `reports/workstation_task_20261030/runtime_clock_topology.json` retains all 560 staged input hashes, the synthesis process/VG identities, the eight audit-source hashes, exact consumer register names, modes, clocks and negative cases. The cached `workstation_profile.json` is the completeness authority: its `candidate_identity` and complete `staged_input_sha256` keys and hashes must equal the process evidence before any actual file hashing. A process manifest cannot define its own smaller closure. The prepared-profile SHA, every staged input, VG and audit source are sealed before and after the audit; no live workspace/profile reconstruction is used. Later TF/USB repairs need a new synthesis identity; this snapshot does not validate them.

## Declarations and static connections

The actual staged SDC begins with the exact maintained 13-clock bundle. `audit_clocks` receives the actual remaining suffix through `extra_sdc`; that establishes prefix identity and deliberately does not claim that every suffix constraint is correct. This new audit checks the three additional clock declarations and both selected-mode exclusion declarations. The remaining 200 suffix lines, tool-side object-query resolution and routed exceptions remain outside its scope.

| Declaration | Frequency | Static evidence |
| --- | ---: | --- |
| `clk_50m` | 50 MHz | Top input; old primary declaration |
| `ulpi_60m` | 60 MHz | Top `usb2_ulpi_clk` input; old primary declaration |
| `dac_ref12m288` | 12.288 MHz | Top input and actual DCS `CLKIN0` |
| `audio_76m8` | 76.8 MHz | Audio PLL ratio and source wiring |
| `lcd_pixel31m5` | 31.5 MHz | LCD PLL ratio and source wiring |
| `usb_48m` | 48 MHz | USB PLL ratio and source wiring |
| `ddr_mem400` | 400 MHz | Actual `u_memory/u_pll/u_pll_0/PLL_inst/CLKOUT2` ratio and wiring |
| `ddr_ui100` | 100 MHz declared | Opaque DDR wrapper output and three reset observers mapped; internal divider unverified |
| `video_ref49` | 49.5 MHz | Video reference PLL ratio and wiring |
| `video_serial742` | 742.5 MHz | TMDS PLL ratio and 49.5 MHz input |
| `video_pixel148` | 148.5 MHz | Visible divide-by-5 CLKDIV; preserved `-edges {1 7 11}` waveform |
| `cpu_ram50` | 50 MHz | CPU PLL `CLKOUT0` ratio and wiring |
| `cpu_core100` | 100 MHz | CPU PLL `CLKOUT1` ratio and wiring |
| `dac_ref16m9344` | 16.9344 MHz | Top input; exact 59.051398337 ns declaration and actual DCS `CLKIN1` |
| `selected48` | 12.288 MHz mode | DCS output, master `dac_ref12m288`, divide-by-1 |
| `selected44` | 16.9344 MHz mode | Same DCS output, master `dac_ref16m9344`, divide-by-1 with `-add` |

The source netlist contains exactly seven visible PLLs, one visible video CLKDIV and one DCS. The seven PLL instances are audio, CPU, LCD, DDR `u_pll_0`, USB, video reference and TMDS. The maintained auditor verifies enabled output ratios, static divider/phase settings and source connectivity. The DDR PLL's real hierarchy includes `u_pll_0`; simplified synthesis-log names do not replace the actual VG path.

The internal DDR UI target `u_memory/u_ddr3/gw3_top/u_ddr_phy_top/fclkdiv/CLKOUT` remains opaque in this synthesis VG. The existing auditor maps a distinct wrapper output to all three UI reset observers and retains the declared 100 MHz value while leaving its internal frequency/divider proof deferred. This phase does not inherit the separate isolated DDR physical probe as full-runtime evidence. Consequently whole-source-clock topology completeness stays false.

## DCS and selected-clock consumers

The only DCS is `u_managed/runtime/clocks/selector`, with `DCS_MODE="FALLING"`. Its `CLKIN0/1` trace through input buffers to the real `clk_12m288` and `clk_16m9344` top inputs. `CLKIN2`, `CLKIN3`, `SELFORCE` and select bits 2/3 resolve to actual GND primitives. This checks constant drivers, not a net merely named GND.

The low select bits connect directly to unique register Q outputs:

| DCS select | Actual producer | Producer clock |
| --- | --- | --- |
| bit 0 | `u_managed/runtime/clocks/transaction/clock_select_o_0_s1` | `clk_50m` |
| bit 1 | `u_managed/runtime/clocks/transaction/clock_select_o_1_s1` | `clk_50m` |

There is no combinational selector logic between those Q outputs and `CLKSEL`. This static observation does not prove one-hot transitions, legal switch sequencing, glitch freedom, stopped-input behavior or recovery under a missing source.

DCS `CLKOUT` resolves to `dac_mclk_d`. All 322 retained serializer DFFs use that net, and `dac_mclk_obuf/I` connects directly to it. `hp_bck`, `hp_ws` and `hp_din` each have one OBUF driven directly by the corresponding serializer `bck_o_s0`, `lrck_o_s0` or `data_o_s0` register, also clocked by `dac_mclk_d`.

The reference-48, reference-44 and selected monitors each retain 67 source-side registers on their corresponding raw/selected source clock. Their 162, 163 and 169 destination/control registers respectively use 50 MHz. Thus the selected monitor measures the actual selected net rather than either fixed reference. The report records exact names; these counts are this snapshot's evidence, not a physical clock coverage claim.

## Validation and remaining gates

Audit command:

```sh
python3 projects/138k/push2_workstation/usb_a/tools/workstation_runtime_clock_audit.py \
  --project /Users/sphenicidition/.cache/gw138k-task-20261030/runtime-rev4-synthesis-41e653fe/workstation/Prj1 \
  --synthesis-evidence /Users/sphenicidition/.cache/gw138k-task-20261030/runtime-rev4-synthesis-41e653fe/runtime_synthesis_evidence/process.json \
  --output /Users/sphenicidition/.cache/gw138k-task-20261030/runtime-clock-audit-v2-closure/audit.json
```

Regression command:

```sh
GW138K_RUNTIME_CLOCK_STAGE=/Users/sphenicidition/.cache/gw138k-task-20261030/runtime-rev4-synthesis-41e653fe/workstation/Prj1 \
GW138K_RUNTIME_CLOCK_PROCESS=/Users/sphenicidition/.cache/gw138k-task-20261030/runtime-rev4-synthesis-41e653fe/runtime_synthesis_evidence/process.json \
GW138K_RUNTIME_CLOCK_TEST_EVIDENCE=/Users/sphenicidition/.cache/gw138k-task-20261030/runtime-clock-audit-v2-closure/mutations.json \
python3 projects/138k/push2_workstation/usb_a/sim/test_workstation_runtime_clocks.py -v
```

The four new tests pass in 51.227 seconds: real source topology/false acceptance flags, 23 rejected declaration/netlist mutations, and 15 rejected provenance cases. Mutations cover changed periods/master clocks, loss of `-add` or mode exclusion, extra clock/DCS, wrong references or constants, invalid selector ownership/clock, wrong serializer/monitor clocks or output wiring, PLL ratio/dynamic divider, pixel divide ratio, missing DDR instance path and missing reference input. The provenance cases cover incomplete synthesis, changed/missing actual files, wrong project/output identity, empty closure, a process seal that omits one otherwise valid input, same keys with a changed hash, process/prepared candidate identity mismatch, missing prepared profile, and a matching but unsafe manifest path outside the project. The real-netlist tests require explicit existing stage/process environment variables and never fall back to preparing or synthesizing a project.

The three maintained clock-plan tests for declarations, unsafe frequency/waveform drift and source/opaque-target ordering also pass. Only these three methods were run; the separate Gowin STA syntax probe was not invoked. No EDA process or board operation occurred in this phase.

The parent independently repeated the four tests in 51.148 seconds and reran the command-line auditor into `/Users/sphenicidition/.cache/gw138k-task-20261030/runtime-clock-audit-parent-final/`. Every auditor field exactly matches the versioned JSON and the identity remains `runtime-clock-source-audit-v1-4cf8f6511f055554`; the report-only regression and scope fields are additive.

Gowin's synthesis Timing Clock Summary still shows default 100 MHz entries for some ULPI/reference/selected clocks. Source ratios and declaration text do not establish that STA consumed the intended clocks. Before acceptance, validate Gowin query resolution and propagated generated clocks, both selected modes, all remaining constraints, opaque DDR implementation, clock-tree/PLL legality and resource placement, routed setup/hold/recovery/removal, then dynamic switching/clock-loss behavior and physical I2S/MCLK observations. `constraints_complete`, STA/route/physical-clock/DCS-dynamic/hardware acceptance, release readiness and deployment permission remain false.

Rollback is removal of this additive tool, regression and two dated reports. Existing profile selection, constraints and hardware state were not changed.
