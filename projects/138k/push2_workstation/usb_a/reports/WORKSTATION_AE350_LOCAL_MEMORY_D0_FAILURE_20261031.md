# AE350 local-memory D0 physical failure review — 2026-10-31

Candidate `custom138k-ae350-local-memory-probe-C21031D0` (`0xC21031D0`), prepared from source `b3b487700f5c35703bdadf2ef3b7f741363e7ddd`, failed physical implementation. The final process completed with exit code 1 after 1516.173 seconds and unchanged inputs. The exact final error is:

```text
ERROR  (PR0009) : Failed to route with '1' unrouted nets for GAO design
```

There is no `impl/pnr/ao_0.fs`, final `.tr`, or `.sdf`. D0 was not programmed, and is not a physical CDC or timing acceptance. A process sample identifies GAO fuse-map generation and secondary maze routing after 95%; earlier “Timing analysis completed” text does not establish successful final implementation.

## Reproducible evidence

The independent review verified all 45 process inputs, all 31 implementation outputs, the final log, and the vendor tool hashes. It also checked the complete implementation-file inventory and the absence of success artifacts. Full fanout and constraint-query inventories remain outside Git in the sealed review directory; the [compact record](workstation_task_20261030/ae350_local_memory_d0_failure_review.json) binds their exact hashes.

- Review directory: `/Users/sphenicidition/.cache/gw138k-task-20261030/ae350-bsram-probe-independent-v14`.
- Review SHA-256: `7cae4557419ff6e100905483e49bac2de003c87d89a4f6a70476b09a10da934b`.
- Seal SHA-256: `2a3be33a56197e48e1f9051834712233fbee4d652debdc755b260fca6357a75f`.
- Recheck: `python3 /Users/sphenicidition/.cache/gw138k-task-20261030/ae350-bsram-probe-independent-v14/verify_seal.py`.
- Seal verification passed for 13 evidence files, 84 external inputs/outputs, seven preserved review helpers, and two vendor executables. This recheck verifies sealed evidence; it does not rerun EDA.

No RTL, constraints, firmware, frozen baseline, or D0 artifacts were modified for this report.

## Actual netlist findings and limits

The VG/VO review resolves the RTC source to `u_rtc/rtc_tick_s1/Q` and the actual native hard-IP terminal `u_cpu/u_RiscV_AE350_SOC/u_AE350_SOC/RTC_CLK`. The unique CPU PLL ratios and its actual VO connection to hard-IP `CORE_CLK` match the candidate inputs. `PLL_R[0]` remains a mandatory source placement constraint, but actual-site acceptance is unverified without final physical evidence.

Ten synchronizer pairs have the expected actual clocks and complete first-stage fanout to only the next-stage D pin. The APB clock is independently resolved as `ram_clk`; the optimized UART wrapper no longer has a `pclk` formal, so constructing that absent formal name would be invalid evidence.

The snapshot uses eight native 16-bit SDPB lanes. All 1858 held source bits reach active RAM inputs. Its complete held fanout includes 128 active native SDPB DI bits **and 512 first-page cache D pins** in the 50 MHz reference domain. The cache paths retain ordinary setup/hold requirements; filtering only RAM consumers would omit them. The source SDC specifies 20 ns max delay and a hold-only cut to the native DI endpoints. The independent VG object model resolves these queries, but no Gowin query-engine object export or final routed propagation proves their physical application.

The 704 preserved GAO capture bits and ordered GAO configuration match four pages of 16 words plus 192 metadata bits at depth 128, schema `A1386403`. Without FS there is no FS GAOCRC verification. Setup, hold, recovery, removal, minimum pulse width, routed held-data flight, and hardware acceptance all remain unverified.

## Resource comparison and next experiment

| Synthesis resource | C10 main | C10 GAO | D0 main | D0 GAO |
|---|---:|---:|---:|---:|
| Registers | 7180 | 2392 | 6058 | 3032 |
| LUTs | 3929 | 897 | 4812 | 1071 |
| ALUs | 87 | 10 | 184 | 10 |
| Synthesis BSRAM | 40 | 16 | 48 | 20 |

D0's physical report separately lists **48 main BSRAM and 40 GAO BSRAM**. The synthesis GAO count of 20 is not the physical count. Total synthesized FF count falls from 9572 to 9090, while GAO width grows from 544 to 704 bits and total LUT count grows by 1057; total FF count alone does not explain the failed route.

A separate, explicitly identified next candidate may reduce the exported capture to eight words per page, eight pages, and 192 metadata bits (448 capture bits), retaining all 64 canonical diagnostic words, UART access, and full decoding. Four clocks per page give 32 clocks per sweep and four sweeps at depth 128. Four words per page (320 bits, 64 clocks per sweep) is a smaller fallback. These are proposals only; no source, clocks, exceptions, or accepted profile changed in this review. Their physical resource use and route success need new evidence.

D0 remains a sealed failed candidate. Any replacement requires a new identity and fresh physical, SRAM, and readback/capture acceptance; this report does not alter the board or the rollback record.
