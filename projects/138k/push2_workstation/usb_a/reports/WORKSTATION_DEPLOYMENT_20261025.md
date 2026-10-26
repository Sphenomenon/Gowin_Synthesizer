# 2026-10-25 工作站 SRAM 部署与固化撤回记录

## 当前状态

最新状态：用户确认 D5 HDMI 诊断正常出图，硬件问题已自行修复，并要求恢复之前的完整工作站。2026-10-25 19:55:05（UTC+08:00）已从 `C11025D5` 恢复原 `C1102515` 至 SRAM，独立 op0 身份读回通过。本次没有重综合、P&R 或 Flash 操作；完整工作站功能仍由用户验证，具体证据见末节。

恢复后用户反馈：显示器能够接收信号，但显示黑屏。此反馈只绑定完整工作站，不撤销 D5 正常出图的用户确认，也不表示完整工作站显示验收通过。随后仅开展离线来源核对与两项仿真，未再次访问板卡、下载 SRAM 或操作 Flash；原因尚未确认，见 [整机黑屏排查](WORKSTATION_HDMI_BLACK_20261025.md)。

用户随后授权“抓取吧”：20:56:58–20:57:20（UTC+08:00）仅接收 FTDI B 串口 22.025 秒，接收／发送均为 0 字节，没有有效运行记录。未再次读取 JTAG 身份、复位、综合、下载 SRAM 或操作 Flash；不能据此判定 DDR／CPU 故障。观测通道限制及独立机器证据见上述黑屏记录末节。

此前用户要求：**“算了先不急着固化，我先上板验证，烧sram就好”**。该 SRAM-only 范围继续有效。初次部署随后只重载 SRAM，没有继续写 Flash、恢复旧 Flash 或执行 Flash 启动验证。当时 SRAM UserCode 为 **0xC1102515**，官方下载和独立 op0 身份读取均返回 0；DONE=1，配置错误位 0..3 为 0。状态原值为 `0x00022230`，自动加载失败位仍置位，不能据此宣称 Flash 启动通过。

当前源身份为 `custom138k-native-integration-20261025-a23`，物理候选为 `custom138k-native-physical-C1102515`。实际 FS SHA256：`c5006e8f511fed84ced3cd284dabcb8a47359fadd4f64b4f34fdafc6ec880f68`。源、网表、约束、时钟和位流没有因部署授权发生变化。

最终证据目录：`../out/workstation_deployment_20261025_c1102515/`；机器记录为该目录的 `final_status.json`。最终 SRAM 日志为 `sram_only_final_program.log`、`sram_only_final_codes.log`。没有 SRAM 逐位读回证明。

## 撤回前已启动的 Flash 操作

用户此前要求整机烧录固化，并明确接受本候选的 −0.568 ns 建立时序结果。离线预检重新核对完整来源、真实 STA、CDC、PLL 和原生路由；例外只绑定本候选输入、STA 结果和 FS 哈希，不把 STA 失败改成通过。默认门禁仍拒绝不带授权的失败候选。

撤回后的第一次检查发现先前启动的官方 op54 已进行到 **95%**。尝试定位其子进程以取消时，进程已退出；日志记录 **Program and Verify Flash successfully**，返回 0，耗时 152.81 秒。因此 Flash 确实已被写入，不能描述为“只动过 SRAM”或“Flash 未改动”。随后按最新要求只执行 SRAM 下载和身份读取。

没有继续执行独立 Flash 后读回、分区保留验证、擦除 SRAM 后的 Flash 重载或物理断电启动。不能宣称 Flash 完整验收或整机功能验收完成。此前的授权原文及当时授权内容保存在 `preflight/deployment_preflight.json`；版本化授权文件已标记被最新 SRAM-only 请求取代，预检确认其不再能授权 Flash 部署。

## 备份与回退

写入前官方 op51 识别 Flash 为 `0x0B4018`，容量 16 MiB。两次全 Flash 读取均为 16,777,216 字节，逐字节一致，SHA256 均为 `87a15acdd324515b305c5509e06e8cf592dd20a747bc2a8745a588f932808580`；原件为证据目录中的 `flash_before_a.bin` 和 `flash_before_b.bin`，未删除。

原 Flash 的 `0x600000` 模型分区与本候选要求完全一致，52,239 words，CRC32 `AF01A61B`，写配置前另经官方 op66 校验通过，未重写模型。配置 BIN 为 5,283,208 字节，64 KiB 对齐的预期配置擦除范围结束于 `0x510000`，不与模型分区相交；撤回后未再读回验证实际分区保留情况。

如需回退，须另获用户确认，再用保存的原始全 Flash 备份恢复并进行完整读回校验、重新加载与身份核对；此操作会再次写 Flash，当前不执行。原 SRAM 身份 `0x13802401` 不自动等于备份中 Flash 的身份。

## 验证边界

- 建立裕量仍为 −0.568 ns，保持／恢复／移除裕量为 +0.155／+2.981／+0.250 ns。保留失败标记，`release_ready=false`，不替换 accepted 配置。
- 本次新增授权绑定、失效和非建立违规拒绝测试连同原物理准备回归共 15 项通过；accepted 来源 10 项通过，`git diff --check` 通过。
- 被动 UART 检查未收到有效运行记录，无发送控制或上传模型；不能声称 CPU、DDR、音频、HDMI、Push／25K 热插拔或 BLE 实板验收通过。最新安排是交由用户上板验证。
- `scope_change.json` 与 `final_status.json` 分别记录授权撤回时序和最终状态；生成的位流、日志、备份及实现数据库均保留在忽略的输出目录，不作为源码加入。

## HDMI 诊断结束后恢复完整工作站（19:55）

用户明确反馈：“正常出图，是硬件问题我现在搞定了，现在把之前那个完整工作站烧进去”。正常出图的反馈绑定此前运行的 `C11025D5` 诊断，不将其扩展为完整工作站显示、音频、DDR、Push／25K 或 BLE 的实板验收。诊断观测与用户确认见 [JTAG 记录](hdmi_usb3_20261025/JTAG_OBSERVATION.md)。

本次恢复沿用 SRAM-only 授权，直接使用原物理候选 `workstation_physical_20261025_c1102515/impl/pnr/custom_138k_integration.fs`。下载前重新核对七项物理输入、四份审计与原预检的哈希，以及 FS 设备／封装／UserCode 头部和完整 SHA256；均匹配。未修改已接受的原始身份、约束、源码、审计、旧清单或原 Flash 备份，没有因 HDMI 硬件修复重新构建整机。

- FS SHA256 仍为 `c5006e8f511fed84ced3cd284dabcb8a47359fadd4f64b4f34fdafc6ec880f68`。
- 独占 JTAG 后扫描确认唯一 WINUSB 线缆 location 54；下载前 op0 为 ID `0x0001081B`、UserCode `0xC11025D5`、Status `0x00022230`。
- 仅执行 SRAM Program（操作 2），官方下载成功、退出 0，工具报告耗时 7.71 秒；随后独立 Read Device Codes（操作 0）退出 0。
- 下载后为 ID `0x0001081B`、UserCode `0xC1102515`、Status `0x00022230`，配置错误位 0–3 为零。未做 SRAM 逐位读回、Flash 读写或冷启动，不把身份匹配等同于所有整机功能通过。
- 本候选原有 −0.568ns setup 结果及用户对同一位流的接受范围保持原样，不重做时序优化、不放宽门禁，也不改写 `timing_closed=false`、`release_ready=false`。

本次独立授权、前后身份、工具日志及结果在 `../out/workstation_deployment_20261025_c1102515/sram_restore_20261025_01/`，`result.json` SHA256 为 `7cc541467e6766ff755d59b759d3244a6ea91a0dd59d664cf8b5d4fefe3f4b60`。旧 `final_status.json` 保留为 11:21 的历史快照，本次记录不覆盖旧证据。19:55 时工作站留在 SRAM 供用户验证；后续诊断和最新板上身份见下一节。

## 黑屏继续排查与再次恢复（2026-10-26）

用户要求“运行，你自己找问题”并连续要求“继续”，据此临时 SRAM 部署整机 GAO 观测 E4，随后 DDR 隔离 E6／E7／E8／EA，均保存独立部署授权、FS／输入哈希及下载前后身份。E5 时序未通过，E9 捕获输出脚失败，均没有下载。此前 E1／E2／E3 超时无位流，也没有下载。隔离工程本身不含 HDMI、音频、USB 或 BLE，不将其临时无信号记为整机回归。完整身份、时序、抓取和范围见 [DDR 训练实测](WORKSTATION_DDR_CALIBRATION_20261026.md)。

整机 E4 实测 DDR PLL 锁定但未校准，显示取数仍在复位；时序闭合的隔离探针进一步观察到 `READ_CALIBRATION` 持续等待、四个 DQS 原语没有给出有效 burst／valid 资格。已确定阻塞边界，尚未证明最底层电气或配置原因，也未修复黑屏。不会绑高校准标志、跳过 BIST、放宽时序或删除功能掩盖问题。本轮只做 SRAM／JTAG，不读写 Flash，不断电重启；10 月 25 日早先 Flash 操作历史保留。

诊断后于 **2026-10-26 01:22:22～01:22:30（UTC+08:00）** 恢复原完整工作站 `C1102515`：

- 下载前原 FS SHA256 仍为 `c5006e8f511fed84ced3cd284dabcb8a47359fadd4f64b4f34fdafc6ec880f68`；原物理清单、七项输入和 stage 父清单均匹配，不重建、不替换已接受身份。
- 下载前为 `C11026EA`，只执行 SRAM 操作 2，退出 0；其后独立操作 0 读回 ID `0x0001081B`、UserCode `0xC1102515`、Status `0x00022230`。
- 当前 SRAM 为完整工作站，不是隔离探针；没有 SRAM 内容逐位比对，不能将身份正确等同于显示／DDR／音频或其他功能验收。
- 原 setup −0.568ns 的同位流用户接受范围不变，`timing_closed=false`、`release_ready=false`，黑屏未修复。没有本轮 Flash 操作或冷启动。

原始日志和结果位于 `../out/workstation_deployment_20261025_c1102515/sram_restore_20261026_01/`，`result.json` SHA256 `81f23d0894693813f2c5ba8690f1b570cec0a4b142ae7077342196231c6eb784`。旧快照与全部失败尝试保留，不以新结果覆盖历史。

## 官方 DDR 对照后部署完整 B3（2026-10-26 上午）

用户授权“试试吧”，先执行官方 DDR 同板 SRAM 对照 B1，再用原 E6 网表只追加官方 PLL/DLL/CLKDIV 三项物理资源定位得到 B2。B1 校准、B2 校准和 8 MiB BIST 均通过；回切原 E6 再次失败、回到 B2 再次通过。完整来源和原始证据见 [官方 DDR A/B](WORKSTATION_DDR_OFFICIAL_AB_20261026.md)。本轮未操作 Flash 或断电。

完整工作站 B3 复用原 a23 业务 VG/SDC、E4 16 位 GAO 和增量实现数据库，仅补上述三项 CST；新身份 `C11026B3`，不是重写 `C1102515` 的旧接受记录，也不是 a24 已重新综合的网表。CDC、PLL/初始化和原生路由通过；setup −0.394ns，严格时序/时钟清单门禁仍失败并保留，仅用于授权的 SRAM 诊断。

- **2026-10-26 10:40:16～10:40:24（UTC+08:00）** 从 B2 下载 B3 SRAM，前后独立读 ID `0x0001081B`，之后 UserCode `0xC11026B3`、Status `0x00022230`。
- FS SHA256 `a901738a4e07eb777cbc32eb571179e93ebae86e8488e573d4b65696e100011c`；部署记录 `../out/official_ddr_ab_20261026_01/c11026b3/sram_deployment_01/result.json` SHA256 `d12491f944967893a5551efda56f4c451adf8d63a07af932e948043bd07385bb`。
- 三次真实 JTAG 抓取均为内存状态 `0xEB`、视频状态 `0x2E`：校准/BIST 成功、前台帧有效、显示取数复位释放、无取数/仲裁/共享加载故障；观察到渲染计数最低位前进。
- 欠载历史标志为 1，尚未区分启动瞬态/持续欠载；用户实屏、声画及交互验收仍未完成。业务 BSRAM 321 加 GAO 1，共 322 块，不把探针算成业务增长。
- 当前完整工作站诊断版 B3 留在 SRAM，未做 SRAM 内容逐位读回，未做 Flash 或冷启动。`hardware_acceptance=false`、`release_ready=false`；旧 Flash 内容未因此更新。

当前证据汇总 `../out/official_ddr_ab_20261026_01/final_status.json` SHA256 `022790c2cfe5a31a7980c7b9a1a988d0bcd6be8be5e7aa5d4a0ac6b39e3f246a`。回退仍使用原 `C1102515`、FS SHA256 `c5006e8f511fed84ced3cd284dabcb8a47359fadd4f64b4f34fdafc6ec880f68`，只做 SRAM，不由此授权 Flash。

## 出图但闪烁后的诊断与最终恢复（2026-10-26 中午）

用户确认完整 B3 有实际画面但快速闪烁，不等于稳定显示验收通过。后续使用同一业务网表、CST 和 SDC 增量生成 B4 计数探针；没有重综合完整工作站或修改业务 RTL，全部暖 SRAM 操作、前后身份及故障尝试见 [闪烁排查](WORKSTATION_HDMI_FLICKER_20261026.md)。

- 11:55 下载 B4 后未校准；11:57 直接恢复同一 B3 也未校准，旧成功不能覆盖这些失败记录。
- 先运行隔离 B2、校准/BIST 通过，再运行相同 B3/B4 均能就绪，观察到暖重配置前态依赖；这不是可接受的整机初始化方案，也不是冷启动验收。
- 校准后的 B4 抓取 04～06 中，欠载计数低八位为 `127→83→112`，后续仍变化；低位回绕和短窗口不能给出精确速率或排除所有窗口外瞬态复位。未宣称闪烁已修复。
- **最终 12:01:49～12:01:57（UTC+08:00）恢复完整 B3**，不是隔离 B2 或 B4。FS SHA256 仍为 `a901738a4e07eb777cbc32eb571179e93ebae86e8488e573d4b65696e100011c`；抓取 09/10 为 `0xEB/0x2E`，最后独立读取设备 `0x0001081B`、UserCode `0xC11026B3`、Status `0x00022230`。
- 最终操作在 `../out/hdmi_flicker_20261026/startup_sequence_02/result.json`，SHA256 `a8cd12e058ef94995c5d53aed540f3f26f30a9784d0de646b479385df0011b3d`。当前状态汇总 `../out/hdmi_flicker_20261026/final_status.json`，SHA256 `5647c73c51147ac9ab3c65b9ce3e29a40b16c23400ea629a42c147f7d4c84616`。

本轮未写 Flash、未主动断电或执行 Flash 重载；SRAM 重配置会重启 FPGA 逻辑，没有逐位 SRAM 内容读回。恢复后的实际屏幕尚待用户重新确认，稳定显示、音频和其他整机功能均不因身份/就绪正确而自动验收，`hardware_acceptance=false`、`release_ready=false`。首选回退/保留身份为已出图的 B3；三项资源定位仍保留，但不把它等同于初始化稳健性修复。
