# 双138K v69：完整物理结果，未放行

M/W 两次完整 P2R0 均正常结束并产生位流。完整综合对应 v68 检查点，M/W 综合网表哈希分别为 `bb6dc7cbdc9d004fcd2fa56223c5b9f99d83d38d3e9b8be1d80ed91cd5809658`／`38a722f02d43339936bf35ea97fcb2ec87501afcff8a4535a3c98e1bce7378fc`。功能分工和编译字节未改变；不重复未变输入的有效仿真或综合。

| 项目 | M v21 | W v22 |
| --- | --- | --- |
| 物理身份 | `D21109C7` | `D21109D6` |
| Logic／Register／CLS | 91297／58446／61184 | 80141／46793／56229 |
| 物理 BSRAM | 253/340 | 287/340 |
| setup／hold (ns) | **−4.072／−0.231** | **−1.787／+0.143** |
| recovery／removal (ns) | +2.333／**−2.006** | +1.140／+0.281 |
| 完整 P&R 耗时 | 864.66 s | 985.60 s |
| 放行 | 否 | 否 |

M 位流 SHA-256：`95895de77cc367e401b29f41aefb19c2b0693807319c4f179b7136d4bdf4205d`。

W 位流 SHA-256：`5e3d23b64ec93fcfeec3398d1bc87491cb52745691153c3f220988e2e51a92e2`。

**上述位流均禁止加载。** 原摘要收集器仅看到 M removal +0.278 ns；对全部详细报告独立交叉核对发现 lane2 DQS HOLD 为 −2.006 ns，本文采用更保守值，原始报告和结果均不改写。DDR初始化数据hold为+0.148 ns，不能与DQS removal或邮箱hold混淆。

M 最差 setup 由 delay `peer_fault` 经过效果故障、配置请求和事件提交到普通声部控制；实际走线跨 R21–70、C119–179。另有 TF scope invalidation→M endpoint −4.064 ns。PCM response 和 PANIC epoch 的直接 bundled payload hold 分别 −0.231/−0.203 ns。DQS lane2 的配置 FF/LUT 在 C162–165，HOLD硬块在C0，末段走线7.359 ns。

W 完整DMA/FIFO局部布局将setup从v21的−7.651改善到−1.787 ns，hold保持为正。剩余路径包括raw_store fetch范围算术、tag返回到录音状态、CPU邮箱命令栅栏、效果故障及端点payload。三条CT1094分别涉及write FIFO的`even_memory_0_1`、`odd_memory_0_0`、`odd_memory_0_1`，必须按实际hard site核对后才可推广该布局。

下一步仅针对上述真实负路径选择修复。物理变化可复用相同VG，RTL变化需针对性语义回归及新综合。最终还需有效布局进入维护的prepare入口，并对最终身份完成STA/PLL/CDC/资源门禁；本次未运行板卡、SRAM或Flash操作。task2、单板与所有历史失败／回退完整保留。[结构化结果](DUAL138K_TASK3_PREBOARD_V69_20261109.json)绑定原始输入、位流及详细STA证据。[SRAM清单](DUAL138K_TASK3_SRAM_CHECKLIST_20261108.md)继续只准备步骤。
