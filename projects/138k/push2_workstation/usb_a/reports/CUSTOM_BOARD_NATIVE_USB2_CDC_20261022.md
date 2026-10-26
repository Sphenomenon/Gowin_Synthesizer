# 新板原生 USB2 桥窄范围 CDC 约束验证（2026-10-22）

## 1. 状态与来源

候选身份为 **`custom138k-native-integration-20261022-a5`**。本记录接续 [a4 事务复位验证](CUSTOM_BOARD_NATIVE_RESETS_20261022.md)，不覆盖其历史结果，也不更改 accepted full83、pinned timing85 或 resource-timing 的选源政策。代码基点为已推送的 `f502f28f329c6665e4a6150583e390b2c9611cef`，a4／a5 后续改动尚未提交。本轮没有再次 push，没有访问 JTAG／串口，没有下载 SRAM 或写 Flash。

本阶段完成的是 USB2 桥的明确跨域端点、约束生成、实际综合网表审计和有界行为验证，**不是完整原生板 CDC、P&R、STA、PLL 或硬件验收**。所有部署／release 标志保持 false，没有原生板位流。机器记录见 [`custom_board_native_usb2_cdc_20261022/verification.json`](custom_board_native_usb2_cdc_20261022/verification.json)。

## 2. 约束边界

`boards/custom_138k/usb2_cdc.json` 是本次桥接约束清单；频率继续来自原 `clocks.json`，不另立时钟权威。prepare 将原显式时钟约束与以下 **22 条**约束组合，完整审计逐字核对组合结果及来源哈希：

| 范围 | 数量 | 处理 |
|---|---:|---|
| request／result／reset／reset_ack／high_speed／snapshot／snapshot_ack／reference_fault | 8 组、10 位 | 仅已注册源 Q 到同步器第一级 D 排除异步 setup／hold |
| 同步器第一级 Q 到第二级 D | 同上 | 最大延时 2 ns；保留本域 setup／hold 检查 |
| descriptor／result／snapshot 持有邮箱 | 30／22／64 个实现位 | 源 Q 到对应目的 D 最大延时 16 ns，只排除该跨域邮箱路径的 hold |

不使用整域 `set_clock_groups`、按整片时钟的 false path、同步器第二级 false path 或 RAM／复位宽泛豁免。2 ns／16 ns 是上限，清单可收紧但不可放宽；非法类型、非有限值、未知键、遗漏控制组、错误桥路径及不合法常量位清单均失败。snapshot 原有 80 位中 16 位为综合常量，保留逐位清单，不把不存在的 FF 当作有效命中。

实际完整网表解析出 **38 类选择器、272 个引脚**。检查实际时钟网络、同步器两级直连／同域／共享清零／无条件移位，以及三类邮箱逐位的源到目的依赖。result 目的 D 含原软件清除逻辑，因此检查真实组合依赖，不要求其不存在的直接连线。寄存器匹配排除同名 LUT，遗漏位、重复位或错误时钟失败。

该审计不是完整组合扇入 CDC 分类，也不声称已证明所有其他跨域路径。机器审计中的 `payload_hold_behavior_verified=false` 表示静态网表审计本身不执行握手行为；行为证据单独记录，不把静态结果改写为运行时证明。

## 3. 行为与工具语义

桥接测试在 CPU 半周期 10,417／7,353／25,000 ps 三种比例下检查 descriptor 在提交后保持、result 发布后保持、snapshot 在应答往返期间保持，并要求监视器实际覆盖足够周期。原有 512-byte 数据、取消、复位、超时和 ULPI 停钟场景继续执行。三个故意破坏邮箱保持的临时 RTL 负例分别触发对应监视器失败，不改生产源。

约束语义依据本机安装的 Gowin **SUG940-2.0.4E §5.4.1／§5.4.2**，原 PDF SHA256 为 `b9b31c1a3ff09cd90e1358a566b2e2180d2ee4941c764e98052e7cb5ecbc1a73`。没有假定未记录的 `-datapath_only` 选项。另以同型号器件运行隔离的 4-bit 持有邮箱 P&R／STA 探针，使用生成约束中 request／result 同步链和 descriptor 部分的同形选择器：

- 正例中 4 条邮箱 setup 路径的关系为 16 ns，两条同步级间 setup 为 2 ns，两条同步级间 hold 仍为 0 ns；仅预期的异步入口及邮箱 hold 被排除。
- 将邮箱 hold-only 例外改成完整 false path，邮箱 setup 消失，覆盖门禁拒绝。
- 额外屏蔽同步器第二级，相关 setup／hold 消失，覆盖门禁拒绝。

三个探针均确实执行工具并检查报告，不以命令退出码替代约束覆盖检查；负例的工具成功不代表负例通过门禁。**这些是隔离约束消费实验，不是原生整板物理时序结果，不能下载到板上。**

## 4. 实际完整综合与回归

- HS manifest SHA256：`e274665852238145df4635d6ffeba3262ac0eba7d8e660bfff51f4ea0906f7e8`。
- 完整综合网表 SHA256：`3e2af1e4ef97656b79cc03df7afe189f79cc5066af3859709f30b0e98a400021`。
- 原始来源 600 份、staged 文件 486 份、启用工程输入 216 个；HS／FS 的来源快照一致。分别对比 a4 同速准备物，216 个启用条目相同，staged 文件只有 `constraints/custom_138k.sdc` 内容变化，固件 ROM 未变。
- 真实完整综合完成；寄存器 46,750、LUT 58,827、ALU 13,222、综合等效 BSRAM 201/340、SSRAM 1,455；DSP 为 MULTALU27X18 45、MULT12X12 40、MULT27X36 45。与 a4 数量相同不等于物理时序或打包验收。原完整功能层次、四条复位释放链和 16,384-word ROM 核验继续通过。
- 新执行 **107 项不同测试**：原 85 项基础回归、15 项 USB2 准备回归、5 项本次 CDC 测试、1 项三比例桥接行为测试、1 项实际完整综合及破坏性审计。补跑的同名用例不重复累计。
- 实际网表负例覆盖两级断连、CE／时钟错误、descriptor／result／snapshot 逐位依赖缺失及位号错误；原来源、ROM、资源、时钟和复位负例保留。

早先组合命令在综合后的 Python 审计阶段从仓库根目录启动，因模块搜索路径失败；没有重跑或改写原综合产物，随后在 USB-A 工程目录成功审计。首次完整综合测试同样遇到 `test_workstation_pinout` 导入路径错误，已明确设置 `PYTHONPATH=sim:.` 补跑通过；日志及哈希另存，不把入口错误当作硬件或综合结果。

a4 的 HS／FS 输入链路与音频执行共四项仅按**已验证的未变输入复用**，不计入本轮 107 项：逐项核对 30 份完整 profile 输入、全部模型／25K RTL；输入测试文件虽有新的准备断言，其 `run_prepared_input` 方法 AST 与旧执行副本相同。音频另核对 79 份当前来源、87 份 staged 输入、固件及模型未变。仍保留资源 FIFO 与组件 FIFO 的不同来源，以及 DDR 环形模型／显示完成模型／内部 PT8211 参考输出的边界；不把旧执行包装成 a5 新的整板音频验证。

## 5. 剩余门禁与回退

仍待其余整机 CDC／FIFO／复位时序、DDR UI 不透明目标解析、完整原生板 P&R／STA／PLL 和实体连接验收。USB3300 与电平转换器的电气阻断没有解除；未知 DAC 九根信号仍高阻；BLE 新板引脚及实际 138K 业务后端未补齐。不得通过降频、宽泛例外、删功能或复用已接受候选身份隐藏这些缺口。

已插入的调试适配器只读识别为 `0403:6010` FTDI 双通道，尚无 JTAG ID／UART／板上镜像读回；这不是业务 USB HS 已通的证据。调试口插入不等于授权给新候选上板。回退来源为已推送的 `f502f28` 及各历史候选记录；本轮未部署，无需回写板端镜像。完整接受门禁通过前，`timing_constraints_complete`、`timing_closed`、`hardware_tested`、`deployment_allowed` 和 `release_ready` 均保持 false。
