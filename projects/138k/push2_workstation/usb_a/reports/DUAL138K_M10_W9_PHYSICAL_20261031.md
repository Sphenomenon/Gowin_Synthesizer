# M10b／W9b 完整物理测量

2026-10-31。两套默认候选及各自独立 DDR 远置变体均已完整 P&R、生成各自身份位流，**四份整机时序仍失败，均未下载 SRAM 或写 Flash**。M10b 来源为 `370f528922c4fcb5`，W9b 为 `01aa047a4d25aaf1`，完整综合来源见[综合证据](DUAL138K_M10_W9_SYNTHESIS_20261031.md)。

| 物理身份 | Logic | FF | CLS | 物理BSRAM | DSP | setup端点／最差ns | hold端点／最差ns | recovery／removal ns |
|---|---:|---:|---:|---:|---:|---|---|---|
| M10b 默认 D2103111 | 65,722 | 46,930 | 49,927 | 235/340 | 120 | 2,741 / −2.701 | 1 / −3.498 | −0.483 / +0.275 |
| M10b far D2103113 | 65,729 | 46,930 | 49,970 | 235/340 | 120 | 3,299 / −2.163 | 0 / +0.139 | −0.995 / +0.275 |
| W9b 默认 D2103112 | 85,464 | 45,072 | 58,033 | 293/340 | 68 | 9,520 / −11.524 | 2 / −3.683 | +0.742 / +0.278 |
| W9b far D2103114 | 85,464 | 45,072 | 58,034 | 293/340 | 68 | 9,158 / −11.685 | 1 / −0.081 | +0.249 / +0.284 |

综合 BSRAM equivalent 仍为 M195／W257，不能与上表物理块数互换。所有时钟仍维持原要求；W 默认 video Fmax141.482 MHz 低于148.5 MHz，far 为167.238 MHz，不能只报告后者来接受默认镜像。

两份 far 均从各自新默认物理结果及 hash 绑定 VO 独立派生，VG／完整 SDC 逐字相同，仅 CST 新增 capture `R[2:10]C[2:20]`、launch `R[104:110]C[175:181]` 和新 UserCode。没有直接套用旧 M9／W8 的物理证据。实际 launch／capture 均为 R104C175／R2C2，原 DDR 3.500 ns hold 要求保持；目标 hold 实测 M+0.714 ns、W+0.577 ns。W far 剩余 −0.081 ns 是 MIDI ACK 同步首级路径，未把同步 reference48 hold 豁免或称为已通过。

四条新增 50 MHz 专项报告实际均非空、每份100 paths。M 默认／far 同域 setup 最差为 +1.009／+0.765 ns、同域 hold +0.185／+0.164 ns；all→50 hold 分别含默认 DDR 负路径与 far 全正结果。W 默认／far 同域 setup 的100条均负，最差 −5.967／−4.080 ns，不能被全局音频 top2000 隐藏；同域 hold 全正，all→50 hold 各自保留 DDR／MIDI 实际结果。这些是有限报告中的路径数，不冒充完整违例端点总数。

M 默认最差为 DMA 三个 sticky fault 的跨域首级接收，另有 TF 容量准入及配置状态到 DSP 的真实同步长链；USB producer 本地 reset 的两个接收 CLEAR 仍 recovery 失败。W 新窄 performance release 约束已消除旧 recovery 违例，但 D 输入许可→drive乘法→饱和／crush→effects BREG 仍为首要同步瓶颈；50 MHz 长链为 HCI handle／pool 选择后再作长度比较。针对性维护源修复和接收边界证明分别记录，不将其收益追记到本批位流。

四份实际六 PLL／DDR 时钟／serializer 启动／AE350／RTC 门均通过；M10b 与 W9b 的实际 VG／VO、两份 far VO 的[局部原生／APB结构门](DUAL138K_APB_ROUTED_INVERSE_AUDIT_20261031.md)通过，负控及外部审计器身份独立封口。这些不等于完整 CDC 或 STA 接受。

[机器证据](dual138k_m10_w9_physical_20261031.json)固定四份来源、全部输入及 FS／VO／STA／资源 hash、UserCode、默认与 far 派生证据，并在汇总时再次逐项重核全部原始输入／输出。没有板操作，原 SRAM／Flash 回退内容未改；T2-D1／D2 继续未勾选。
