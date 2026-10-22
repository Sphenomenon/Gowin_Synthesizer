# 新板显式时钟树、波形与残留工程隔离

日期：2026-10-22。本轮继续推进上板前准备，**完整目标未完成，不可据此下载或固化**。没有访问板卡、SRAM 或 Flash。仅 CLKDIV 语法探针运行了独立缩比离线 P&R；它不是工作站实现，不用于下载。新板整机仍只完成 prepare／综合，未做整机 P&R。

机器记录：[verification.json](custom_board_native_clocks_20261022/verification.json)。[a2 原生装配记录](CUSTOM_BOARD_NATIVE_INTEGRATION_20261022.md)保留它当时的来源、验证器和结果，不追改成当前快照；新原始来源发生变化后，旧准备物对当前源码的校验失败是正常的漂移拒绝，不应放宽检查。

## 1. 新身份与未变的边界

- 新候选：`custom138k-native-integration-20261022-a3`，仍是 `explicit_native_board_on_resource_timing`、synthesis-only，不复用 accepted 身份。
- 准备 manifest SHA256：`b395cebf73f27dff9d08079756b23199275c28021cb049111566f5b90d693125`；596 份原始来源绑定、486 份 staged 文件、216 个启用工程条目。
- 实际新综合网表 SHA256：`3b2d5d111498f0a32d52c6c1c03149e5ab02b3d8c874825fb24430c04c595188`。本轮改动未提交／推送，Git HEAD 仍为 `91390fb70b8e46a2e504ff7256efe9d7cbef2f48`；机器记录另锁定新增／变更源码。
- 共享 RTL、业务参数应用点、DSP、音频采样计划及既有存储分配不改变。旧 Dock 分支 token 身份与 accepted／timing85／resource 准备边界继续回归。
- 电气阻断、九根 DAC 高阻、CEC 释放、BLE 缺口和全部部署禁止项不解除。新板位流 SHA256 仍为空。

## 2. 从单一时钟计划生成 SDC

`boards/custom_138k/clocks.json` 是显式新板时钟声明来源，SHA256 为 `eac2b14d9f1938fa1370c51f426524a740b656bf7327ed9ae95e4bd30db99838`。`tools/workstation_custom_clocks.py` 验证固定频率、顺序与目标，再生成 `constraints/custom_138k.sdc`；不复制旧板端口例外，不加 false path 或全域异步时钟组。

| 名称 | 频率 | 来源／关系 |
|---|---:|---|
| clk_50m | 50 MHz | 板上参考输入 |
| ulpi_60m | 60 MHz | USB3300 外部并口时钟输入，不假定与 50 MHz 同相 |
| audio_76m8 | 76.8 MHz | 50 MHz × 192/125 |
| usb_48m | 48 MHz | 50 MHz × 24/25，原生 CPU／业务域 |
| ddr_mem400 | 400 MHz | 50 MHz × 8 |
| ddr_ui100 | 100 MHz | DDR IP 内部 /4；实现后的目标解析仍待验证 |
| video_ref49 | 49.5 MHz | 50 MHz × 99/100 |
| video_serial742 | 742.5 MHz | 49.5 MHz × 15 |
| video_pixel148 | 148.5 MHz | 串行时钟 /5，明确 60/40 波形 |
| cpu_ram50 | 50 MHz | AE350 RAM 时钟，仍来自参考 PLL |
| cpu_core100 | 100 MHz | AE350 core 时钟，50 MHz × 2 |

视频像素分频不能用默认对称波形代替。`create_generated_clock ... -edges {1 7 11}` 表示源的第一上升沿、第七边沿为下降沿、第十一边沿为下次上升沿，即 10 个半周期中高电平占 6 个。此前官方 CLKDIV 模型的实际 60/40 检查继续保留；本轮没有修改 PLL 分频参数、降低频率或搜索新的位相。

Gowin 的默认综合频率与实现时 SDC 是不同阶段：安装版 SUG550 §6 的 Clock Summary 说明默认 100 MHz，SUG940 §5.2.2 说明 `-edges` 的定义与互斥参数。本轮没有把综合优化目标改低，也不把综合估算表当 SDC／routed 时序验收。两份安装手册的精确 SHA256 在机器记录中。

## 3. 实际源网表与厂商 STA 证据

新板整机实际综合后，审计解析真实层次和包含转义标识符的实例，检查八个可见派生时钟目标：

- PLL／CLKDIV 目标存在、来源连接经模块端口／输入缓冲正确连接，不仅比较 FCLKIN 字符串。
- 每个 PLL 的输入声明、反馈模式、分数分频、输出使能、静态相位与动态相位／分频开关符合计划；分数频率以有理数计算。
- 像素 CLKDIV 保持 /5 和显式 60/40 边沿；修改 PLL 输入频率、倍频、相位或视频分频的负例必须失败。

DDR UI 时钟在 `~GW_DDR3_PHY_MC.DDR3_Memory_Interface_Top` 不透明 IP 内部。审计确认该边界存在，但不把内部 `fclkdiv/CLKOUT` 冒充成源网表已解析；结果保留唯一 deferred target，`source_netlist_verified=false`、`routed_timing_verified=false`、`constraints_complete=false`。后续需从真正整机实现数据库及 STA 再核对内部 UI 时钟、所有 CDC 和复位路径。

另建仅含 CLKDIV 和一个触发器的缩比探针，50 MHz 输入／10 MHz 输出，在相同器件上实际执行 Gowin P&R／STA：

| 探针 SDC | STA 周期 | 上升／下降 | 对原生目标波形的判定 |
|---|---:|---|---|
| 从当前原生声明提取 `{1 7 11}` | 100 ns | 0／60 ns | 符合 60/40 |
| 反例 `{1 6 11}` | 100 ns | 0／50 ns | 不符合原生目标 |

两次工具均正常结束，STA 报告明确保留源、master、divider/CLKOUT 和不同下降沿，证明不是 Tcl 空桩或工具自动忽略了边沿选项。缩比探针只验证选项消费／波形；**不是 148.5 MHz 新板时序通过，不是整机布局布线**。探针临时目录中的自动输出也不是工作站位流，不纳入源码或部署。

## 4. 固件准备失败后的残留工程

父资源工程返回后，立即把通用 `scripts/build.tcl` 换成明确报错的隔离入口，并先写 `integration_prepare_incomplete`／禁止 P&R／禁止部署元数据，然后再做原生源选择和固件准备。以前若固件准备阶段失败，可能留下父工程的普通构建入口；现在该故障不会残留可被误当成原生成功工程的发布元数据。

新负例在父工程成功返回后注入固件准备失败，验证：通用构建入口仍报错、元数据保持 incomplete 和所有禁止项、没有 `integration_inputs.json` 完成清单。它不宣称替代所有历史 builder 内部的失败审计。

## 5. 本轮最终执行

完整新板实际综合退出码为 0，资源仍为 **201/340 综合等效 BSRAM、1,455 SSRAM、46,750 寄存器、58,868 LUT**；DSP 与全部原功能层次保留。32 个 CPU ROM bit-plane 重建 16,384 word 逐字一致。没有物理 BSRAM／整机 STA／板测结论。

HS／FS 分别从新 a3 完整 prepare 选择实际 29 份前端源码及 ROM，复跑 RV32I、Host 和真实 25K 核；两条链均通过，源／拷贝／所选输入哈希前后不变。音频下游仍为带背压事件检查器，不是整板 DSP／功放；不能把窄仿真与完整综合相乘为硬件验收。

| 本轮最终回归 | 独立 Python 测试数 |
|---|---:|
| clean baseline／accepted 来源／固件 staging／原生组合 | 45 |
| 位置来源／覆盖／负例 | 25 |
| 默认 USB2 prepare 与实际组件综合 | 15 |
| 原生新板快速检查，含固件失败隔离和 TMDS 模型／专用输出 | 7 |
| 显式时钟与实际缩比厂商 STA | 4 |
| a3 实际输入 HS／FS CPU 执行 | 2 |
| 完整新板实际综合／来源／资源／ROM／时钟篡改审计 | 1 |

合计 **99 个独立 Python 测试，无 skip**；不累加 a2 的 94 个测试或重复执行。命令、日志、验证器与准备输入哈希见机器记录；缩比探针和相位子场景不另计测试数。

## 6. 下一道门禁

仍需解决 USB3300／TXS 实物电气条件、明确功放 U1 型号并实现真正 DAC 驱动、补齐 138K BLE 引脚及业务后端。软件侧继续补外部 IO 时序、原生 48／60 MHz 邮箱与跨域 FIFO／复位的有界约束和实现后检查，不能用一条全域 false path 隐藏问题。完整新板 P&R、routed STA／CDC／PLL、外设实体和冷启动验收均未完成。

回退依旧使用原有显式整机配置，不选择新板入口；不修改任何历史部署记录或当前板内容。本轮目标保持进行中，不把“时钟声明齐了”重新定义为整个新板完成。
