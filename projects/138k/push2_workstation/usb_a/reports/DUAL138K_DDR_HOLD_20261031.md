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
