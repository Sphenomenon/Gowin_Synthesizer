# 双 138K：M7 初始化 hold 物理实验

2026-10-31。实验 `D2103104` 已完成完整 P&R、全布通并生成位流；**全板时序仍失败，未下载 SRAM、未写 Flash**。只处理真实 DDR 初始化保持路径，没有更改厂商 RTL、频率、时序例外或业务功能。

## 来源与精确增量

父候选为 M7 `custom138k-workstation-m-demo-v1-0067ea90a6354485`，父物理目录 `m-demo-base-v7-physical-v1`／`D2103103`。本次直接复用父综合网表 SHA256 `4e77d5b5ae1fe7e591ad9824dfa4c7f8c5962fabf3b5ccf833ad75ae9a980cd6`，没有新综合。独立输出位于 `/Users/sphenicidition/.cache/gw138k-dual-20261031/m-demo-base-v7-physical-hold-v2`。

`workstation_custom_board_implementation.py --ddr-launch-capture-regions` 先验证父物理报告、全部输入及真实 routed VO 的双 DFFCE／共同 reset／CE=VCC／直接 Q→D／DDR CLKDIV4→direct 50 MHz 拓扑，随后只在原 CST 后追加：

```text
INS_LOC "u_memory/u_ddr3/gw3_top/u_ddr_phy_top/wloadn_3_s0" R[40:50]C[70:90];
INS_LOC "u_memory/u_ddr3/gw3_top/u_ddr_phy_top/ddr_init_internal_r_s0" R[70:80]C[150:170];
```

原 SDC 包括精确 `set_min_delay 3.500` 保持逐字节不变；全部已有物理输入的 hash 在 P&R 完成后再次核对。旧 capture-only 与 DQS 模式仍按旧 0.800 ns 策略验证，没有改写历史默认行为。新模式、旧 capture／DQS 和完整 physical prepare 回归共 49 项通过，包括 minimum 漂移、父身份／网表漂移、既有目标位置冲突及混用模式的拒绝。

## 实际结果

| 项目 | D2103104 实测 |
|---|---:|
| Logic／FF | 65,950／46,859 |
| CLS／容量 | 49,982／69,120 |
| 物理 BSRAM／容量 | 235／340 |
| DSP／容量 | 120／298 |
| setup／hold 违例端点 | 3,663／1 |
| 最差 setup／hold | −2.467／−1.799 ns |
| 最差 recovery／removal | −0.424／+0.281 ns |
| audio Fmax（目标 76.8 MHz） | 68.681 MHz |

精确 DDR 路径的 launch 实际位于 `R70C150[0][A]`，capture 位于 `R40C70[0][A]`，均落入要求区域。最小角 CQ 为 0.144 ns、data route 为 2.018 ns、clock skew 为 0.413 ns；arrival 3.559 ns、required 5.358 ns，仍未满足原 3.500 ns 要求。相较父物理 −3.647 ns有所改善，不能把该局部改善写成 hold 闭合。全局建立时序也未通过，−0.424 ns recovery 位于 USB FIFO 队列释放边界。

[完整测量与输入／输出 hash](dual138k_m_demo_v7_hold_v2_physical_20261031.json) 包括精确位置、时钟、前 50 条负 setup 路径及 reset 负路径。位流 SHA256：`78426ed052619ddd1e6592fc5acdb0f003b0b720e46c38d4c26e075037ee13f6`，头部 UserCode 独立核实为 `D2103104`。

本实验保留失败身份，不能当作 M 演示通过或收益归因。后续若试更远位置须使用新的显式模式、目录和 UserCode，保持全部原 SDC，并重新检查全板 setup／hold／recovery／removal。板上回退为保持此前镜像，本实验没有改变板卡状态。

## 远区域复验 D2103106

新显式 `--ddr-launch-capture-far-regions` 使用同一 M7 父综合网表和逐字节相同的完整 SDC，只在原 CST 后追加 capture `R[2:10]C[2:20]`、launch `R[104:110]C[175:181]`。区域依据已有真实布线报告中的普通逻辑位置选取，没有修改厂商 RTL、原严格 `set_min_delay 3.500`、工作频率或时序例外。旧实验与旧模式保持原身份及结果。新增模式和既有 prepare／DDR 回归共 51 项通过。

2026-10-31 完整 P&R 工具退出 0，并完成位流生成；所有输入 hash 在完成后复核一致。目标路径实际 launch `R104C175[0][A]`、capture `R2C2[0][A]`，均在指定区域内，arrival 6.044 ns、required 5.362 ns、原 hold relationship 3.500 ns、clock skew 0.418 ns，目标路径 slack **+0.682 ns**。全部 hold 违例端点 **0**，全局最差 hold +0.143 ns。

全板时序仍不通过：setup 2,114 个违例端点，最差 −2.368 ns；recovery −0.515 ns，removal +0.278 ns；audio Fmax 72.177 MHz，低于 76.8 MHz。负 recovery 仍是 audio 域 `queue_release_5` 到 USB FIFO 生产指针真实 CLEAR，不能用全局 false path 掩盖。实际 Logic 65,952、FF 46,859、CLS 50,060／69,120、物理 BSRAM 235／340、DSP 120／298；这些是本次物理实测，不是预记收益。

[D2103106 完整测量及 hash](dual138k_m_demo_v7_hold_v3_physical_20261031.json)，JSON SHA256 `3f14b4dbc7e25698c28d8203950541c3ba13cb11ab90206907c8c542aa332ce9`；FS SHA256 `8a5de97386e7a7fcc27a887c206125e27fe218e7b89d666035569bb60416c15b`。输出目录 `/Users/sphenicidition/.cache/gw138k-dual-20261031/m-demo-base-v7-physical-hold-v3`，UserCode `D2103106`。没有 SRAM／Flash 下载或硬件验收，板卡仍保持此前镜像。
