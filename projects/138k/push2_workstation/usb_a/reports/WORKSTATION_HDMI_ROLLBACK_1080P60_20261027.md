# HDMI：取消 720p60，SRAM 回退 1080p60 与 DDR 定位核对

日期：2026-10-27，时间均为 UTC+08:00。接续 [720p60 候选记录](WORKSTATION_HDMI_720P60_20261027.md)和[官方 DDR 对照](WORKSTATION_DDR_OFFICIAL_AB_20261026.md)。本次不新增综合／P&R，不改 RTL，不删除 720p 分支或历史产物，不操作 Flash。

## 授权与取消

用户先明确授权：“允许，之后下载到sram不用询问我”。后续本项目 SRAM 调试下载不再逐次征求确认，但仍核对明确目标、精确位流和下载前后设备身份；该授权不涵盖 Flash，也不把不闭合的时序或未验收的功能改写为通过。

02:29:19–02:29:28 曾按该授权直接下载完整工作站 720p60 BA，独立读回从 `0xC11026B7` 变为 `0xC11027BA`。位流 SHA256 为 `e290835888ff4b087880c089cc95d2b057f3f1089ab473d23db67f8283cdfec9`；其 SRAM 记录位于 `out/workstation_video720p60_20261027_ba/sram_deployment_20261027_01/result.json`，SHA256 `517f3d656c3debaac52265d3639e8eef695a3383f2070300f7f46742cf08af69`。

随后用户反馈 BA“有信号但是黑屏”，明确要求取消本次尝试，回退之前出图的 1080p60，并核对 DDR 三项资源定位。**720p60 BA 的实屏未通过，本次试验已取消，不再继续构建或下载该候选。** 保留其源码、位流及真实证据，不把取消解释为清除工作区修改。

## 实际 SRAM 回退

使用历史上用户确认能出图的完整工作站 **B3／`0xC11026B3`**，不是独立色块或 DDR 测试程序。历史出图仍有闪烁与启动限制，本次只恢复精确旧位流，不提前声称这些问题已消失。

```text
out/official_ddr_ab_20261026_01/c11026b3/impl/pnr/ao_0.fs
SHA256: a901738a4e07eb777cbc32eb571179e93ebae86e8488e573d4b65696e100011c
UserCode: 0xC11026B3
GAOCRC: 26B3
模式: 1920×1080，60 Hz
```

下载前核对 B3 输入／物理／独立核验清单及清单内全部输入哈希。三份清单 SHA256 依次为 `8ed43c158332ea4cbe3aebd703bffc0cc762ba5eb656cbd60421ea88077aeac3`、`28dcbd2829583b3c19d7b93c8c79cc941acd8cb668493bb138a2603123c962b6`、`5d083c29b2d1b67021b5359a3c4f8e27f48fac9486f1ca21943db42632629710`。原 B3 最差 setup 为 −0.394 ns，仍不冒称严格时序闭合。

使用 `/tmp/gw138k_20261025.lock` 排他锁，目标 `GW5AST-138C`、cable-index 5、location 54。命令请求 0.9 MHz；SRAM Program 日志记录工具自动更新为 15 MHz，不将请求频率当作整个写入过程的实际频率。

| 操作 | 时间 | 实测结果 |
|---|---|---|
| operation 0，写前独立读取 | 02:36:37.406–02:36:37.566 | ID `0x0001081B`，UserCode `0xC11027BA` |
| operation 2，仅 SRAM 回退 | 02:36:37.595–02:36:45.472 | 返回 0，完成 100%，日志含 `Finished.` |
| operation 0，写后独立读取 | 02:36:45.473–02:36:45.627 | ID `0x0001081B`，UserCode **`0xC11026B3`** |

实际日志、命令和时间位于 `out/official_ddr_ab_20261026_01/c11026b3/sram_deployment_20261027_rollback_01/`，其中 `result.json` SHA256 为 `95aaf5024e01fe76102138c4d7ff7fa7dd3972d45ffda596774f8ec39171e922`。这是独立设备身份读回，不是 SRAM 位流逐位回读。本轮直接 BA→B3，没有 B2 DDR 预初始化、断电或 Flash 操作。

## DDR 三项定位结论

**720p60 BA 没有再次遗漏这三项定位。** 版本化来源 [boards/custom_138k/ddr.cst](../boards/custom_138k/ddr.cst)、本轮准备目录的 `custom_138k.ddr.cst`、`native_prepared.cst`，以及 B3／BA 实际使用的 `physical.cst` 中，下面三条均精确出现一次：

| 实例 | 专用位置 |
|---|---|
| `u_memory/u_pll/u_pll_0/PLL_inst` | `PLL_L[0]` |
| `u_memory/u_ddr3/gw3_top/u_ddr_phy_top/u_dll` | `DDRDLLM_BL` |
| `u_memory/u_ddr3/gw3_top/u_ddr_phy_top/fclkdiv` | `LEFTSIDE[4]` |

进一步核对的是实际构建输入，而非只查看未参与编译的源文件：

- B3 与 BA 的实际 `physical.cst` **逐字节相同**，SHA256 均为 `40e45c93370e077a0442b79cfc0a084949821c2a0a366dc8b4437d99e11277a5`。
- 两份真实 P&R `cmd.do` 均指向各自该文件并启用 `-cst_error`；日志完成约束解析及位流生成，没有约束错误。
- 两版 routed `.vo` 中均保留上述 PLL、DDRDLL 和 CLKDIV 实例；该检查证明实例存在，不把它冒充坐标逐项读回。
- B3 的 `u_memory/memory_clk_376` 与 BA 的 `u_memory/memory_clk_367` 均使用 **`BANK6_HCLK0 BANK7_HCLK0`**；没有重现早先 E6 快速内存时钟多走 PRIMARY／BANK7_HCLK1 的差异。
- 既有 `wloadn_3_s0` 的 hold 区域约束也保留。它是上述三项之外的独立约束；`native_prepared.cst` 到实际 `physical.cst` 的差异主要在这里，不是再次补回遗漏的三项资源定位。

检查明细 `ddr_location_check.json` 与回退记录位于同一目录，SHA256 `1bf48b99c46994f6844da1bebe9b8403ca32c2a81d08985add506633dda5c12a`。检查绑定了约束、真实工具命令、日志、routed 网表与资源报告的哈希；没有解密受保护的 `.p`／`.pr`，也没有把离线检查称为板上 DDR 校准通过。

## 当前状态与边界

当前最近一次独立读取为 **B3／1080p60／`0xC11026B3`**。BA 已因用户实屏黑屏被取消，不再作为待测试候选；构建时未下载的清单保留为当时快照，实际 SRAM 状态以本次操作记录为准。

本次核对不支持“又遗漏三项定位”这一解释，但**没有证明 720p60 黑屏根因，也不排除 DDR 初始化／就绪或显示取帧问题**。BA 没有 GAO，取消前未取得其板上 DDR 校准抓取。B3 本次是否重新出图仍需用户实屏确认；独立暖启动可靠性、持续欠载及整机声画验收未因此完成。
