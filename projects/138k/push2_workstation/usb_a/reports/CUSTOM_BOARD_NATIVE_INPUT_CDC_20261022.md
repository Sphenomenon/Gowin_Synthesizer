# 新板原生 USB→音频事件 FIFO CDC 验证（2026-10-22）

## 1. 身份与验证边界

候选 **`custom138k-native-integration-20261022-a6`** 接续 [a5 USB2 桥验证](CUSTOM_BOARD_NATIVE_USB2_CDC_20261022.md)。代码基点仍为已推送的 `f502f28f329c6665e4a6150583e390b2c9611cef`，后续改动未提交、未再次推送。本轮补齐原生装配中 48 MHz USB owner 与 76.8 MHz 音频输入 FIFO 的两组 Gray 指针约束，不改 18-bit 事件、生命周期／PANIC 语义、公共参数权威或音频采样调度。

当前结论是来源绑定、完整综合、选用 FIFO 的行为检查和隔离约束消费通过，**不是整机 CDC、物理时序或上板验收**。没有运行完整新板 P&R，没有原生板位流，没有访问 JTAG／串口，没有下载 SRAM 或写 Flash。机器证据见 [`custom_board_native_input_cdc_20261022/verification.json`](custom_board_native_input_cdc_20261022/verification.json)。

## 2. 选源与实际端点

继续从 `resource_rework_route0` 锁定来源还原事件 FIFO，并经过现有 `workstation_resource_timing.event_fifo` 的检查式适配；不修改冻结来源、原 manifest 或旧 overlay。针对性仿真及隔离综合使用这份选用输入，完整综合测试另外逐字比较原生 staged FIFO，避免只验证未适配组件 FIFO。

实际范围为 `u_native_usb/input_owner/events/fifo/unbuffered`：

| 方向 | 源域 → 目的域 | 已注册源 | 两级接收器 |
|---|---|---|---|
| 写指针 | USB 48 MHz → audio 76.8 MHz | `produce_w_gry[5:0]`，最高位实际别名为 `produce_w_bin[6]` | `produce_cdc/stage0[6:0]` → `stage1[6:0]` |
| 读指针 | audio 76.8 MHz → USB 48 MHz | `consume_r_gry[6:0]` | `consume_cdc/stage0[6:0]` → `stage1[6:0]` |

`input_cdc.json` 固定实际层次、7-bit 指针和最高位别名；时钟频率仍由原 `clocks.json` 单一提供。新增 **6 条** SDC，和 a5 的 22 条桥接约束组合：两条 Gray Q→第一级 D 最大延时 **10 ns**、两条同路径 hold-only 例外、两条第一级 Q→第二级 D 最大延时 **2 ns**。不能放宽预算，不能把整个二进制总线当作 Gray 源，也不对存储数据、完整时钟域或第二级接收器添加 false path。

真实综合网表证明 14 位源→第一级→第二级逐位直接连通、源／目的实际时钟正确、两级无条件采样且清零为常量，解析 **9 类选择器、56 个引脚**。另确认唯一 `SDPX9B` 的写／读时钟分别是 USB／audio。静态审计不将寄存器名称等同于 Gray 算法证明，也不声称双口 RAM 的板级物理时序已经通过。

## 3. 选用 FIFO 行为与约束消费

在 CPU 半周期 10,417／7,353／25,000 ps、audio 半周期 6,510 ps 三种比例下分别通过：

- 逐事件 18-bit 顺序比对、指针多次回绕、满队列背压与不覆盖旧事件。
- 读端停钟后的写侧背压、写端停钟后的读侧排空，不产生重复或幽灵事件。
- 存在未读数据且 audio 停钟时发起清除，恢复时钟并排空无独立复位脚的输出缓存，随后新 epoch 不重放旧数据。
- 两侧已注册 Gray 与二进制指针逐拍对应，正常运行相邻 Gray 值最多改变一位；两种故意改成二进制采样的临时 RTL 负例都被拒绝。

三次正例分别比对 **7,841／7,834／7,835** 个事件、观察 **688／692／689** 个满队列周期，各覆盖两次 epoch。这里的复位恢复是 FIFO 单元测试的明确清除／排空流程，不把它等同于整个 owner 的六拍 flush 管线、DSP 或实体音频验收；完整 profile owner 与实际音频链路的旧执行仅按未变输入复用。

另外在同型号器件上对**选用 FIFO 本身**运行三次隔离 P&R／STA：

1. 正例覆盖两侧全部 14 位 Gray 入口 setup（10 ns）、14 条级间 setup（2 ns）及 14 条级间 hold（0 ns）；仅 Gray 入口 hold 被排除。
2. 把 hold-only 改成完整 false path 后，Gray setup 消失，覆盖门禁拒绝。
3. 屏蔽读指针接收器第二级后，其级间 setup／hold 消失，覆盖门禁拒绝。

默认 25 条报告不足以列出全部目标路径，故按本机 Gowin SUG940 §5.5.1 明确增加报告条数，不改变频率或例外；覆盖统计也只匹配 consume／produce，同域复位链不混入指针计数。早期两次报告解析失败及最终完整报告均保留。**这是隔离约束消费实验，不是新板整机 P&R／STA，也不能下载该探针。**

## 4. 完整综合与回归

- HS manifest SHA256：`971101607870c5deae4fe655ca6639a39f13536771aa84d7b36519ce85ca9ebd`。
- 完整综合网表 SHA256：`7cc56914cfffbd7acebe7220867693c63adb40e1158df0be732dcf545e8d2dbb`。
- 原始来源 **602** 份、staged 文件 **486** 份、启用工程条目 **216** 个；HS／FS 的来源快照相同。分别对比 a5 同速准备物，启用清单相同，只有 `constraints/custom_138k.sdc` 内容变化，ROM 不变。
- 实际完整综合及独立审计通过：寄存器 46,750、LUT 58,827、ALU 13,222、综合等效 BSRAM **201/340**、SSRAM 1,455；MULTALU27X18 45、MULT12X12 40、MULT27X36 45。资源数量与 a5 相同不能替代物理打包和时序验收。
- 原功能层次、16,384-word ROM、显式时钟、桥接复位和 a5 桥接 CDC 门禁继续通过；新增实际网表负例检查级间断连、CE／时钟错误、Gray 源断连及双口存储时钟被改错，不能仅凭选择器有命中而接受。
- 本轮最终 **113 项不同测试**通过：112 项完整回归及 1 项实际完整综合／破坏性审计。六项 FIFO 专项的单独补跑不重复累计；a4 的四项输入／音频长执行按来源及方法 AST 未变复用，也不计入本轮执行数。

## 5. 临时存储事故与证据保全

初次完整综合与批量回归遇到 `/tmp` tmpfs 的用户 **12,602 MiB 硬配额**，不能以文件系统仍显示余量判定可继续写入。回归未完成；该次 Gowin 虽返回 0 并写出 finish，资源 XML 却为零字节，独立审计明确拒绝，不能当作综合成功。

随后把已结束的音频验证目录迁移到磁盘缓存，**440 个文件逐项 SHA256 不变**，原 `/tmp` 路径由符号链接保留，不删除历史输入或证据。后续设置磁盘上的 `TMPDIR`，在新的磁盘目录完整重新准备、重新综合和重新执行回归；不补造空 XML、不覆盖失败日志、不复用残缺综合网表。来源、退出状态、原失败产物及迁移记录哈希均见机器证据。

## 6. 未完成门禁与回退

其他整机 CDC／FIFO／复位时序、DDR UI 不透明目标解析、完整 P&R／STA／PLL、电气及实板验收仍未完成；USB3300/TXS 电平连接冲突、真实 DAC 型号及对应驱动、BLE 新板引脚与 138K 业务后端仍需解决。新加指针约束不解除这些条件，也不把调试适配器枚举当作业务 HS 已通。

`timing_constraints_complete`、`timing_closed`、`hardware_tested`、`deployment_allowed`、`release_ready` 均保持 false。回退来源为已推送的 `f502f28` 和 a5 历史记录；本轮未部署，不需要回写板端镜像。完整源码准备、综合、物理实现、实体接受、SRAM 部署与 Flash 固化继续分阶段记录。
