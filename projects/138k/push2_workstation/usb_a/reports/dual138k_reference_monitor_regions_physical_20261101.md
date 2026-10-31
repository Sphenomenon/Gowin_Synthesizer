# D2110105 参考 monitor 区域整机物理结果

2026-11-01。显式单行区域试验完成整机 P&R，退出 0，耗时 532.23 s，生成 `D2110105` 位流；**未闭合同域 hold，也不能作为下一候选的默认放置**。它沿用 W11far `D2110102` 的同一 VG、完整 SDC、DDR 两端远区及自动 hold repair，只追加前述 128 个源 FF 的区域声明；helper／来源／实际 prepare 与负控见[离线阶段](dual138k_reference_monitor_regions_prepare_20261101.md)。

| 实际物理指标 | W11far D2110102 | 单行区域 D2110105 |
|---|---:|---:|
| setup 违例端点 | 6,394 | 7,024 |
| 最差 setup | −4.648 ns | −5.878 ns |
| hold 违例端点 | 11 | 18 |
| 最差 hold | −0.585 ns | −0.487 ns |
| 48k 参考 hold 端点 | 6 | 18 |
| 44.1k 参考 hold 端点 | 5 | 0 |
| DDR 唯一 3.500 ns 路径余量 | +0.673 ns | +0.679 ns |

新路由实际 Logic 71,155/138,240、LUT 54,725、ALU 14,642、Register 45,091/139,095、CLS 52,152/69,120、物理 BSRAM 293/340、DSP 67.5/298、SSRAM 298；PRIMARY／LW 仍均为 8/8。VG 相同而物理 ALU／CLS 映射有变化，不能将其解释为维护源资源优化收益。recovery／removal 全局最差为 +2.242／+0.287 ns。clk50 四项真实报告中 setup 最差 −4.537 ns、hold 最差 +0.137 ns；单项最多 100 路，不代替完整端点数。

实际 VO 再次通过两个 scope 的完整 128 个 source FF 类型、INIT、CLK／CE／CLEAR／Q 和 IBUF 绑定，第三 selected monitor 没有新增放置声明。详细 TR 能导出 68 个目标 FF 的真实位置，全部命中要求的单行区域；可读产物没有完整导出全部 128 个位置，未将这 68 个冒充全量位置验收。DDR launch/capture 实际仍为 `R104C175[0][A]`／`R2C2[0][A]`，命中原远区。

最差 hold 的 `source_binary[29]` 与 `source_gray[29]` 已在同一行：`R54C67[2][B]`→`R54C71[2][B]`，但实际时钟到达仍为 3.095／4.205 ns，相差 1.110 ns。数据 0.648 ns，hold 要求 0.025 ns，得到 −0.487 ns；紧凑数据放置没有消除直连 IBUF fabric clock 的偏斜。未添加全局缓冲、源 FF 延时、时钟或例外。整机最差 setup 来自录音 DDR `read_pointer[1]`→BLE store completion generation CE；次差为 PCM owner active physical→written CE，分别为 −5.878／−5.876 ns。这些是同一旧源的新物理结果，不与 W12 新源收益混用。

实际 native VO CLI／已安装 SDC 查询通过；native 回归执行 54 项、按角色跳过 13 项，36 项实际负控拒绝；boundary 执行 7 项、61 项实际负控拒绝；PLL 门及 7 项负控通过。物理输入、位流、VO、SDC、TR、SDF 在门检查前后哈希一致。[机器报告](dual138k_reference_monitor_regions_physical_20261101.json) 绑定完整资源／四类 STA、频率、位流身份、实际 FF／位置、原路径及各门结果；详细证据保留在 `~/.cache/gw138k-dual-20261031/w11-monitor-regions-physical-audits-v1/`。

本试验保留为可复现的显式物理配置，后续新候选需自行选择来源和放置。未操作 SRAM／Flash，没有物理 DAC／HDMI／手机／25K 功能验收，不提升发布或硬件状态；回退仍使用完整保留的 W11far 目录及其位流。
