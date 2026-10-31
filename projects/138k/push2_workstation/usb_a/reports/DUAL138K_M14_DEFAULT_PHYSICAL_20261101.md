# M14 D2110108 默认全量物理审计

M14 默认候选完成全量 P&R 和独立 routed 子门禁，但**时序仍失败**：setup 最差 −1.940 ns、3764 个违例 endpoint；hold −3.453 ns、1 个违例 endpoint。物理 BSRAM 实测 235／340。Native VO、DEMO boundary VO、官方 PLL／serializer startup 及各自负控均通过，不能覆盖失败 STA，也不是实板声画、25K／Push、SRAM、Flash 或双板并发验收。完整资源、四类 STA、路径和封存身份见[机器证据](dual138k_m14_default_physical_20261101.json)。

## 封闭来源与物理身份

候选 `m-demo-base-v14`，身份 `custom138k-workstation-m-demo-v1-0e7a7f996619ed83`；integration manifest SHA256 `9bab7f4300868ed32fc61f9b140552d63d47e7f296e86eee15ba71d34f1007b2`，588 staged／261 enabled inputs、875 source snapshot entries。综合 BSRAM equivalent 为 195，不与最终物理 235 混淆。

本次全部分析使用独立 `m14-audits-v1/source-tools` 的 1207 文件快照，其 seal SHA256 为 `876d48677aac865cba4453ac6e1fb18191ee331ef42ecba6c72f3e0bf74bc2ad`。588 个实际 staged 文件与 1207 文件快照在每次审计前后及交付时逐项核验。当前 worktree 后续 PCM key-commit／raw START case 源码没有作为 M14 来源；不能给 M14 加上后续代码或测试的已实现身份。

物理身份 `custom138k-native-physical-D2110108`，UserCode `0xD2110108`，manifest SHA256 `07a0273bae202d8a893038262ac0da687b236da54e3f2e26af4f6f301a94d22f`。VG SHA256 `414081bc2a6a233cdae0f7b4988ed126d44fb2f8ed5be93eefcdd7d6aba6db78`，SDC `6fa398b1bf7418d052e6cdc0c98c90512d506cc75931fa952b974f7b7db1562c`，CST `3410fdce9ae4525e5667d75697db6a7f782f3c1fc2540e671fe1af97c8c2d6cb`。默认只保留既有 ULPI IO type 适配，无 DDR far 或 reference-monitor placement；原 DDR minimum 3.500 ns 保持。place=2、route=0、replicate=false，原自动 hold repair 和时钟／例外检查保留。

主线程全量 P&R exit 0、755.257 s，位流 FS SHA256 `31514409cbc2cc55ca0d97d67c98f965a50d7cfcbfcd25db589da22ecc7088cc`。此为本次失败候选身份，不是硬件接受或部署记录。

## 真实资源和时序

| 最终实际资源 | 使用／容量 |
|---|---:|
| Logic | 66303／138240 |
| LUT／ALU | 52031／13426 |
| Register | 46932／139095 |
| CLS | 50306／69120 |
| 物理 BSRAM | 235／340 |
| SSRAM | 141 |
| DSP | 119／298 |

四类 STA 最差分别为 setup −1.940 ns、hold −3.453 ns、recovery +1.603 ns、removal +0.278 ns。最差 setup 为音频域 delay `underflow_sticky_s1/Q→oscillator/envelope_state[26]_0_s1/CE`；随后有 oscillator pitch divider valid→chorus `lfo_remainder` CE 等路径。没有放宽 audio clock、删除业务、加入 false path 或预记资源收益。

唯一 hold 违例是原 DDR `ddr_init_internal_r_s0→wloadn_3_s0` 的 3.500 ns 关系：arrival 2.002 ns、required 5.455 ns、skew 0.482 ns、slack −3.453 ns，launch `R75C8[0][A]`、capture `R75C4[0][A]`。

四份 clk50 实际表单独记录。same-domain／to-clk50 setup 均为 −1.330 ns，报告负路径分别 36／37；same-domain hold +0.183 ns，to-clk50 hold 包含 DDR −3.453 ns。每份有 100-path 上限，不将报告中的负路径数当作完整违例总数。最差 same-domain setup 为 audio clock transaction `state_0_s0/Q→state_0_s0/D`。

## 独立子门禁与执行边界

- Native VO CLI 通过；54 项测试执行 51／跳过 3，46 个 actual-netlist mutants 全部拒绝。
- DEMO boundary VO 7 项测试通过，61 个 mutants 全部拒绝；其 physical CDC 接受字段仍为 false。
- 官方 PLL／serializer startup 完整子门禁通过，6 个 PLL、3 个 shared tuple、7 个负控；DDR source／configuration proof 重新执行。它仍是 PLL／startup 子门禁，不是全 STA／CDC／电气或实板接受。

六组执行全部经过既有 `m14-audit-job-v1.py` 的实际来源／快照校验，并额外在每组执行前后核验整个物理目录。资源／STA 测量包装器仅把 import ROOT 从 live worktree 改为 frozen source-tools，原测量算法与阈值保持，派生文件身份单独封存；没有 monkeypatch 或注入成功结果。

物理目录共 30 文件，其完整 seal SHA256 为 `bbcfce87ae3ce161ff3d78d1ce6754af1966569b0ba76c11aa0961c4c8c99472`。全部物理输入／输出、官方子门禁依赖与来源均保持前后身份。未执行任何板操作，原板镜像保持；不能用本 FS 作为已验收回退版本。

主线程独立负责同 VG／SDC／3.500 ns 的 `D2110109` far 派生与 P&R，本报告不预填其资源、时序或结果。M14 默认仍须关闭 STA 和完成正式功能、CDC、电气及声画实板验收；后续 key-commit 或 raw 源改动需要新的候选身份和完整实现验证。
