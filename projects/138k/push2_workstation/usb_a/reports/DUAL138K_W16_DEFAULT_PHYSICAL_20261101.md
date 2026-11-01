# W16 default full physical measurement

W16 `D2110118` completed full P&R in 476.022 seconds and generated a bitstream. Full STA remains failed, and the dedicated mailbox CDC audit confirms a separate finite-constraint gap. This image is not deployable.

| Measurement | Actual value |
|---|---|
| Logic / registers / CLS | 73,321 / 45,092 / 53,289 |
| Physical BSRAM / DSP | 293 / 66.5 |
| Setup violated endpoints / worst | 4,489 / −4.472 ns |
| Hold violated endpoints / worst | 3 / −3.683 ns |
| Worst recovery / removal | +1.869 / +0.278 ns |
| Four clk50 report worst slacks | −4.442 / +0.175 / −4.442 / −3.683 ns |

Worst setup is DDR recording arbiter read_pointer0→raw pack_frames1 D, with 14.500 ns data delay against 10 ns. The next clk50 path is Bluetooth tx_header0[5]→host_rx generations RAM WRE (−4.442 ns). These are real same-domain paths; private payload preload does not remove all fault/qualification fanout. Complete timing must be fixed in RTL rather than inferred from reduced endpoint counts.

The main hold failure remains original DDR init→wloadn3 at 3.500 ns, slack −3.683 ns. Two additional violations include the 48k reference monitor binary→Gray domain at −0.002 ns. Recovery/removal are positive; neither remaining reference hold nor DDR minimum is waived.

All six frozen physical audit groups completed: native actual VO CLI and 58 tests (44 pass/14 role/mapping skips) with 60 rejected faulty variants; boundary seven tests/69 rejected variants; official six-PLL startup audit/seven negative controls and actual held-v2 gate passed. These subgates do not override STA or complete CDC. PC remains power-up-only.

Dedicated actual VG and routed VO mailbox checks both verify 296 payload freeze, req/ACK synchronization and capture/retirement Boolean relationships, but installed SDC covers only 296 of 9,928 real source-consumer pairs. Missing 9,632 generation qualification paths remain an explicit coverage failure. The exact cache-only 10 ns/held-hold candidate passes complete pair coverage and negative controls; it is not installed or physically timed. Routed review is separately bound in the adjacent JSON. New explicit W policy maintenance cannot upgrade frozen W16 evidence.

Identity `custom138k-workstation-w-demo-v1-18b580e6057ef03d`; integration manifest `efe507f4520166615735dbf8f9200d025a0bdd9acb9656456a85e1b680d5a0d3`; physical manifest `c9ebe3d44fbce14e05354bbe78f477f5d3e6b868524e615730a339c16e3cd4b9`. Bitstream identity and complete source/configuration/tool/command hashes are in the machine report.

Evidence root `/Users/sphenicidition/.cache/gw138k-dual-20261031/w16-default-physical-audits-v1/results/W`; summary SHA `4d1437f6efdce9355630a1738f6d6f953ea57f769a7892766f949e0d114284c9`; audit seal `cf56d8f0279aaef6fb48850e2683036efa3e3e96e7708a9ac6d504aac1d50f41`. Root independently reread 30 physical files, all 1395 frozen tools, 951 prepare snapshots, 645 staged inputs, audit outputs and declared existing absolute dependencies. Exact evidence counts and hashes are recorded.

A separate same-VG/complete-SDC/3.500 ns far variant `D2110119` adds only the two existing DDR opposite-corner CST lines. Its P&R/STA result is not inferred here. No SRAM/Flash operation occurred. W recording remains 16,384 frames / 64 KiB; no new physical HDMI/DAC/25K, phone A2DP/BLE/D/download, long recording or dual-board acceptance exists. Previous board image is retained.
