# W13 D211010A 默认完整物理结果

2026-11-01。W13 全量 P&R exit 0、499.164 s，完整独立 routed 子门通过，但 STA 仍失败：setup 6829 个违例 endpoint、最差 −5.765 ns；hold 3 个、最差 −3.537 ns；recovery +2.468 ns、removal +0.281 ns。不能部署，未上板。

候选 `custom138k-workstation-w-demo-v1-bc065b3de8977725`，物理 UserCode `D211010A`，VG `3c786632…b4a787`。完整原 SDC、DDR 3.500 ns、自动 hold repair 和 place=2／route=0／replicate=false 保持，默认只有既有 ULPI IO type 适配，没有 far／reference-monitor 区域。物理 Logic 71,645、FF 45,092、LUT 55,137、ALU 14,720、CLS 52,540、BSRAM 293／340、SSRAM 298、DSP 66.5；综合 BSRAM equivalent 为 257，分别记录。

最差 setup 是真实 DDR arbiter `read_pointer_0/Q→recording_ble_store/memory_next_index_29/CE`，其后还有 dma_fault 至 reverb RAM CEB 的音频域路径。原 DDR hold 的 arrival 1.891 ns、required 5.428 ns、relationship 3.500 ns、skew 0.476 ns，launch `R87C152[0][A]`、capture `R84C152[0][B]`。PCM／raw 的独立实际 primitive 证明另记，不把 write_address CE 的局部短化推成所有录音 CE 或全局时序收益。

Native VO CLI 与 54 项回归（41 通过／13 跳过）、36 负控通过；DEMO boundary 7 项／61 负控通过；官方 6 PLL、3 shared tuple、7 负控通过，913 份依赖重验。六组分析使用固定 W13 的 1365 文件工具／源码／测试快照，每组前后检查 645 staged 与完整 30 物理文件；当前 TF 及后续 HCI 维护源不混入本候选。[机器记录](dual138k_w13_default_physical_20261101.json)绑定四类 STA、实际路径、资源、输入输出及所有子门，整机接受仍为 false。

同 VG／完整 SDC／DDR 3.500 ns 的新 `D211010B` far 已由实测父证据派生并启动全量 P&R，未预填结果。真实手机 A2DP／BLE／D效果、25K、完整 HDMI／DAC、长录音和双板并发仍待验收；本次没有 SRAM／Flash 或任何板操作。
