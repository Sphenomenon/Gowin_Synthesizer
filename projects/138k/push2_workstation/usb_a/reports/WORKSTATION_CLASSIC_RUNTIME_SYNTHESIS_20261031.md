# Classic runtime / HCI / PCM whole-workstation synthesis

The frozen ROM128 candidate `custom138k-workstation-classic-runtime-v1-3855490f159913c6` passed actual Gowin synthesis with all 636 staged inputs unchanged. This is the first resource measurement for this joint candidate; it is not a same-function savings comparison with the earlier BLE business candidate.

| Synthesis resource | Count |
|---|---:|
| Logic | 124,974 |
| LUT | 90,575 |
| ALU | 31,495 |
| RAM16 | 484 |
| Register | 66,818 |
| BSRAM | 299 |

Logic uses the report's `LUT + ALU + 6 × RAM16` accounting. Physical CLS, physical BSRAM and routed timing have not been measured for this candidate. The largest top-level consumers include Bluetooth (27,568 LUT / 5,609 ALU), the managed audio/control subsystem (26,721 / 12,989), and video (11,176 / 6,192). Boot memory uses 72 synthesis BSRAM. These figures guide further implementation work and do not authorize feature removal.

The source checkpoint is `ed1441d`, integrated by main milestone `335e876`. The actual VG SHA256 is `09e1a0e81ddd61b617e0bdc349a6ae79fcc756e0e7f1da6e8bf4f9c5447c6ff7`. Synthesis consumed 283 enabled inputs and completed in 446.482 seconds; 151 warnings remain. No Gowin AG loop diagnostic was emitted. Clock/RTC source and netlist audits passed within their recorded scope; the complete CDC, legacy feature-path, PLL and physical gates are not accepted by this result. The original prepare was verified with the frozen full source checkout, and the implementation copy was independently hashed, including Gowin's additional `Prj1.gprj.user` file.

ILM and DLM allocation, the firmware identity and disabled production runtime/security gates remain those of the [source milestone](WORKSTATION_CLASSIC_RUNTIME_MAIN_20261031.md). Subsequent START/context fixes are separate source changes and are absent from this netlist. Cache remains disabled. There is no P&R, SRAM programming, Flash write, actual phone audio or CPU deadline acceptance.

The [machine record](workstation_task_20261030/classic_runtime_main_synthesis.json) binds the complete audit and resource hierarchy. Immutable evidence is under `/Users/sphenicidition/.cache/gw138k-task-20261030/classic-runtime-main-synthesis-parent-v1`, with 1,038 source snapshots and 1,719 external input/output records. Seal SHA256: `e4698fa5bf4fba62cacf2251018084f1abed2784b80869e84194f776b134a8f9`.

Recheck with `python3 /Users/sphenicidition/.cache/gw138k-task-20261030/classic-runtime-main-synthesis-parent-v1/verify.py`. This checks the sealed source and output identities; it does not rerun EDA or confer routed acceptance. ROM96 and matching new-source ROM128 syntheses remain separate same-code comparison candidates.
