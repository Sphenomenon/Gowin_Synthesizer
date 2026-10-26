# 新板原生 DDR UI 时钟核验（2026-10-22）

## 1. 身份与边界

候选 **`custom138k-native-integration-20261022-a7`** 接续 [a6 输入 FIFO CDC](CUSTOM_BOARD_NATIVE_INPUT_CDC_20261022.md)。Git 基点仍为 `f502f28f329c6665e4a6150583e390b2c9611cef`，本轮源码未提交、未再次推送。此次修正真实实现网表的解析边界，补充选用 DDR IP 的隔离 P&R／时钟约束消费验证，不修改冻结／vendor 字节、原时钟计划、整机 RTL 或既有 USB／音频／公共参数契约。

**这不是新板整机 P&R、DDR 数据读写或硬件验收。** 原生候选只执行完整综合；隔离探针另行执行 P&R，并含测试专用 reset／observed 位置，不能当作新板镜像下载。未访问 JTAG／串口，未下载 SRAM，未写 Flash。机器证据见 [`custom_board_native_ddr_clock_20261022/verification.json`](custom_board_native_ddr_clock_20261022/verification.json)。

## 2. 实际确认的时钟

隔离工程逐字使用原生 stage 选用的六份锁定 DDR 输入：`ddr3_platform.v`、`ddr_recovery_guard.v`、DDR 接口和三份 PLL 文件。没有另写简化 DDR 模型替代加密 IP；业务请求保持关闭，因此不能由探针推出 DDR 初始化、训练、容量或读写成功。

真实布局布线网表和工具时钟表共同确认：

| 边界 | 实际值 |
|---|---|
| PLL 输入 | 50 MHz，内部反馈，静态分频／相位 |
| `u_memory/u_pll/u_pll_0/PLL_inst/CLKOUT2` | 400 MHz，周期 2.500 ns |
| `u_memory/u_ddr3/gw3_top/u_ddr_phy_top/fclkdiv/CLKOUT` | `CLKDIV` 除 4，100 MHz，周期 10.000 ns |
| UI 计数器 | 8 个真实寄存器，时钟均来自该 `CLKDIV` 输出 |

生成时钟继续从既有 `clocks.json` 选取，不放宽频率、不加入 false path。工具对计数器的定向 setup／hold 报告分别使用 10 ns／0 ns，均有实际路径且无负余量；完整行、WNS、原始报告与网表 SHA256 记录在机器证据中。此处只验证时钟拓扑和约束消费，不能代替 DDR 数据通路和整机 STA。

## 3. 解析修复与拒绝错误输入

Gowin 路由后网表把层次写入带 `/` 的转义实例名，且转义实例与 `defparam` 的点号之间存在必要空格。解析器原先把名称中的斜杠误当作真实父作用域，也不能正确匹配这种参数写法。现在按实际声明作用域追踪连接，解析带分隔空格的参数和端口方向，并拒绝平铺名称与真实层次的路径碰撞；8 项解析器回归通过。

整机综合网表现可把 DDR UI **输出边界**定位到 `memory_clk`：wrapper 输出 `memory_clk_367`、opaque 端口 `memory_clk_366` 和 3 个 UI reset 同步寄存器的时钟一致。这里的 `source_boundary_verified=true` 只证明可见边界连接；加密内部目标仍在原生综合审计的 deferred 列表中，`verified`、`source_netlist_verified`、`routed_timing_verified` 仍为 false。不能用隔离实现的成功将整机状态改为已闭合。

破坏性检查拒绝：除 4 改除 5、PLL 倍频改错、目标重命名、消费者时钟或分频器输入误接、锁定 IP 字节漂移；完整综合审计还拒绝单个 UI observer 时钟误接和 wrapper 输出伪装成输入，原 ROM、资源、桥接复位与 CDC 负例继续通过。

## 4. 完整候选与回归

- HS manifest SHA256：`1d00251bdab0f3d45df73553e7094841b7f528baa2810e02b1e6dcd76e6dbe68`。
- FS manifest SHA256：`4be27272dbe0274d70d04b0e84f38afbc09334cbb8215e90404587e6af057995`。
- 完整综合网表 SHA256：`86d705256f5c334be51367322c20fd38327e1f17cb018dd6e99544b447640312`。
- 来源快照 602 份、staged 文件 486 份、启用条目 216 个。HS／FS 的来源快照相同；分别对比 a6 同速候选，全部 staged 文件和工程启用清单逐字／逐项不变，ROM 不变；差异在审计工具与验证源码。
- 真实完整综合与独立审计通过：寄存器 46,750、LUT 58,827、ALU 13,222、综合等效 BSRAM **201/340**、SSRAM 1,455，三类乘法资源仍为 45／40／45。综合等效数量不是物理打包结果。
- 本轮 **118 项不同测试**通过：117 项回归及 1 项完整综合／破坏性审计；此前单独的解析器及 DDR 实验不重复累计。回归包含无私有历史输入的三条完整工作站 prepare、固件／来源门禁、既有桥接／FIFO 约束探针及新增真实 DDR 时钟实现。
- a4 的 HS／FS 输入和音频四项长执行仅按选用输入、仿真输入及方法 AST 未变复用，不记为本轮重跑，不推导真实 DAC 或 DDR 通过。

为防未提交工具后续演进后丢失来源，a6 的变更源码按原机器记录哈希精确保存在本机缓存，a7 当前变更与验证源码另存独立 delta，二者与 Git 基点及完整哈希清单绑定；未改历史机器记录，也未向源码仓库添加实现数据库或位流。这是本机证据保全，不能冒充远端已有这些未提交源码。

## 5. 剩余门禁与回退

仍需其他整机 CDC／FIFO／复位约束、原生完整 P&R／STA／PLL、DDR 实际数据通路、电气与实板验收。USB3300／TXS 电平连接冲突、真实 DAC 型号和相应驱动、BLE 新板引脚与 138K 业务后端仍未解决；插入调试线不等于业务 HS 已通，也不解除下载门禁。

`timing_constraints_complete`、`timing_closed`、`electrical_complete`、`hardware_tested`、`deployment_allowed`、`release_ready` 保持 false，`bitstream_sha256` 为空。回退来源仍是已推送的 `f502f28` 和 a6 历史记录；未部署，不需要恢复板端。下一步应在保持这些隔离边界的前提下继续补齐原生整机物理验证与外设资料，不能把专项时钟通过写成“已经可上板”。
