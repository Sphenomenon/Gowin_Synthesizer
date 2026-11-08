# 双 138K v27 综合与物理修复续记

本阶段完整综合及审计通过，**尚未放行上板**。M A10／W B11 已从 v27 生成新物理输入并开始 P&R；资源、四类 routed STA、最终物理 CDC／PLL 待新结果。未识别、连接或操作板卡，未写 SRAM／Flash。v22、task2、单板及历史失败证据保留；机器可读身份、资源、逐项证据哈希见[续记清单](DUAL138K_TASK3_PREBOARD_FOLLOWUP_20261108.json)。

| 板 | v27 候选后缀 | 配置 SHA-256 | 综合门禁 | 实际新物理运行 |
| --- | --- | --- | --- | --- |
| M | `bbeed2f1f0c9a797` | `74b70cf198c9f6634b83080e540bb06880b0a402762c2091c59aa23f9fbf1882` | 26/26 | A10／`D21108AA`，待结果 |
| W | `12ff9f44e63f71e1` | `d92f1af85009eb41a64eeef28c6de662b4b7c4d03250a341459aecdddfd9994e` | 25/25 | B11／`D21108BB`，待结果 |

M 继续拥有交互、统一参数、普通 32／矢量 8 声部、基础音频、本地混响与最终输出；W 实际承担 CNN、手机接收／解码和唯一录音对象。既有 TF、识别／Push、手机 D 模式、录音下载路径和失败隔离保留。CAP3 持续手机吞吐准入仍关闭，须上板实测；理想模型不能代替持续 RF/SBC/LCD/DAC 验收。

## 本次实际修复与证据

- W B9 的工具退出 −9 已由内核日志定位为约束解析内存耗尽：`gw_sh` 占用 126007 MB 后被终止，并非超时或时序结果。对相同 9,130 个实际可放置原语及五个区域，改用精确 GROUP／GRP_LOC，保持 280 个 held FF 的独立映射。B10 又因多行 GROUP 语法失败，失败输入保留。安装版手册及同器件小工程确认单行 GROUP；B11 才验证完整网表。运行监督器只限制本次工具进程树，记录 RSS／输入哈希，达到 16 GiB 或 1800 秒即停止。
- M telemetry 的 16 位 USB divider 原由异步原始条件释放；现在使用既有两级 `usb_ready[1]`。保存完整父源与可逆单点修改证明，仅显式 M preboard profile 选择。停钟、两拍释放、暖复位及原始坏源反例通过。协议与音频路径不变。
- M PCM bitmap 的同值撤销条件并行化保持逐拍语义，但 v23 网表显示深度未改善，因此另按真实八级 command-ID 饱和归约链拆成四个保留字节谓词。v26 相同算法测得 command-ID→bitmap 最大组合级数 **17→14**；四个实际字节 AND 的 BDD 及四个 INIT 破坏反例通过。物理改善仍须新 route 证明。完整 owner 对比覆盖 7,190 周期、61 个状态／输出、512 RAM 字和四个 bitmap；262,144 组四态标量组合、352 个实际 command-ID 四态模式及 7,543 周期继续对比通过，丢失 revoke 的坏源被拒绝。
- M owner-live、idle、PCM ACK、输出安全、USB source-release、两条立即置位／本域解除 hold 链及 score FIFO Gray 都按实际 next-Q、PRESET／CLEAR 和首级完整消费者证明。异步例外仅命中隔离首级或释放级；后级 2 ns、Gray flight 10 ns，功能 reset 与 payload 保留时序。HCI session 只新增四个 release/live CLEAR，epoch／generation 功能捕获 reset 继续计时。
- M 五类 F808／PANIC／PCM held payload 保留 max 10 ns、min 1.8 ns 和 hold 检查，按清单分置 348 个真实数据 FF；W 为 164 个 F808 FF。DDR 初始化保留原始有限 min 0.8 ns、功能 reset max 7.5 ns、异角区域及原生 clock-skew/hold 检查；不改加密 IP 字节，不以例外宣称初始化 hold 已解决。
- M CPU release destination v6 清单逐项审阅 8,360 个端点。相对 v5 有 56 个新增、67 个移除的端点名／D/CE 打包项，但逐位状态身份、时钟、RAM 和顶层输出完全相同；保留 v1–v5，不按计数或通配符准入。实际网表破坏反例通过。v25 M 的两个旧清单失败门禁保留。

## 验证与复现

v26 两板分别重新完整综合，输入哈希保持不变。v27 只更新审计清单／锁，全部暂存编译字节、启用顺序、工程、脚本、固件、ROM 和 IP 与 v26 相同后，严格复用七项综合产物；新候选完整审计重跑，M 26/26、W 25/25 通过。

实际 v26 网表定向检查：消费者 3 项、物理边界 2 项、route-repair 7 项（其中一项需要另选 routed W 的检查跳过）；含额外消费者、错误时钟／INIT、损坏 Gray、重复约束等破坏反例。当前 17 项 accepted-source 检查通过。未变的 TF／PCM／滑音／效果回归沿用[前阶段证据](DUAL138K_TASK3_PREBOARD_20261108.md)，不把未重跑的旧结果写成新运行。

v27 在第二目录再次准备，M 709 项暂存／288 项启用输入、W 697／201 全部逐字节相同且顺序相同。M 候选编号相同；W 固件诊断包含输出路径，候选编号不同而实际编译输入完全一致。该证据不证明重复 P&R 位流逐位一致。

复现入口仍为 `build.py --prepare-custom-board --workstation-profile custom138k-workstation-task3-{m,w}-preboard-v1`，外部 Gowin 网表与 RISC-V 工具链、完整候选／物理目录及证据哈希见续记清单。正确目标板、串行 JTAG、身份独立读回、回退与功能步骤见[简短 SRAM 清单](DUAL138K_TASK3_SRAM_CHECKLIST_20261108.md)。真实 LCD 吞吐、DAC 延迟及整机演示继续留在上板阶段。
