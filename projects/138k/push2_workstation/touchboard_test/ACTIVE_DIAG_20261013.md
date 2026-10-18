# 2026-10-13 主动 RTL 实机诊断

用户授权临时修改 RTL 并自主排查。全部下载只写 SRAM；Flash 未写。原理图、网表、J8针号依据沿用 README 的本地来源。

## 结论与边界

触摸硬件尚未修复。当前证据把问题分成：U2/U3 的实物通信通路，以及 U1 的采样/供电/电极或芯片异常。无法仅凭数字串口唯一确定具体焊点或模拟器件。未把 GUI 静默、单通道零值或一段时间误报减少当作正常触摸通过。

- 扫描全部8个GPIO的56种有序SCL/SDA配对，并扫描0x08–0x77的112个地址，覆盖 **6272/6272**。仅 **J8 SCL10/SDA12、地址0x0D** 应答，读到ID0x11/version0x40。未找到U2或PCA9685，也没有发现移到其他线序/地址的器件。
- 开漏逐脚拉低并释放的自身回读8脚均通过。此测试证明FPGA焊盘驱动/输入可用，不能证明线缆或焊点通到远端芯片。
- 去掉FPGA内部上拉后：J8.9/10/11/12均可回高；J8.5(SDA3)及J8.8(DIN)放低后未在1ms内回高。DIN本就没有保证外部上拉，低电平本身不判故障。SDA3按原理图应有R20上拉，需优先关注该通路/器件拉低。J8.6(CHANGE)回高约110个50MHz时钟，约2.2us；SCL/SDA1/2约7–9周期，约0.14–0.18us，包含同步器和逻辑延迟，不能当作示波器上升时间测量。
- 活动采样与LP=0休眠对照：活动阶段617个原始有效帧有12个带按键位；休眠阶段1464帧按键位均为0，多数通道的signal/reference固定为一组值。休眠读数本身可能已异常且I²C匹配会唤醒器件，不能当作“绝对不会采样”的模拟隔离实验；结果降低UART/显示持续篡改数据的可能性。
- 只启用K0时没有按键位，但该通道几乎全零，因此不合格。
- 发送一次16颗WS2812全黑帧后仍有误报。只证明FPGA发出经仿真验证的全零数据；未得到实物LED熄灭反馈，不把此项当作已证实切除LED负载。
- 连续64字节读取改为逐16位寄存器读取后，仍有零值/跳变和少量按键位；长读取事务不是唯一原因。逐字模式的signal/reference分时读取，不是同时快照。
- 运行中每轮检查寄存器12–69的固定配置。该窗口有效READY/raw帧1442，带按键位22；配置不符错误6没有出现，但有一次地址NACK（25个遥测帧）。不能以配置读回成功排除所有间歇性通信故障。
- 最低通信活动对照：禁用I²C2/3、UART降为5Hz、U1轮询200ms，去掉下载前缓冲帧后共176帧；启动后有效READY/raw帧158，其中全16键帧158。仍异常，因此其他总线访问与50Hz串口通信不是误报的唯一来源。

这些时间窗的无触摸条件沿用用户“当前并未做任何触发”的报告及保持不动的提示；没有独立手指真值记录，不作严格受控统计因果结论。

## 最终监测版

UserCode `0x54420109`。全部16键、burst=1、threshold=10、NDIL=3、BREP=1、LP=1、轮询32ms、I²C参数100kHz、UART50Hz；连续SCL等待上限由2ms延长20ms。启动时发送一次全黑LED帧，校准后等待1秒；使用逐字原始读取、运行中固定配置读回及错误后失效/重新初始化。手册/软件配置没有改变GPIO电气接线。

GUI保留原始按键位，不压制误报。提示“通信/配置通过”，增加全16键/零基准告警；读串口前清空输入缓存，并在离线、重置时清空通道缓存。历史下载前仍可能有FTDI/驱动缓冲帧，因此分析已按最后一次sequence回退截取当前下载会话，文件名为`*_current_session.jsonl`和`*_session_summary.json`。

构建 `build_20261013_022304_248276`；SHA256 `1b574986dc69bf4be1bc1a5aee03878d2d82c4da9152ba0083f391326f662ab3`；setup/hold违例0/0。

## 证据

本目录保存每个诊断版的构建、下载、原始JSONL、UART、仿真与统计。重点：`full_scan_coverage.json`、`pullup_hardware/capture.jsonl`、`sleep_summary.json`、`single_capture_session_summary.json`、`word_capture_session_summary.json`、`audit_config_capture_session_summary.json`、`quiet_capture_session_summary.json`。

仿真包含逐线扫描、故意交换线序、非预期地址0x52、56×112完整覆盖、所有32路原始UART数值/CRC、软复位/校准、身份与读回门控、运行中配置篡改后的失效与恢复、掉线重连、WS2812全零波形。单独静默测试检查其他总线没有边沿。

## 仍需实际硬件能力的部分

U2.23/24的SDA/SCL、U2电源/RST、RN1及U3 SDA3/R20通路，以及U1的VDD/VREF/SMP、Rs/Cs与电极。数字RTL能控制和回读现有GPIO，但没有接入这些模拟节点的电压/波形测量工具，也没有U2的独立硬件RESET控制线。当前证据支持优先排查硬件，不宣称已经找到唯一坏元件。

证据目录：`/home/sphenicidition/Documents/fpga/migration/gw138k_audio/push2_workstation/touchboard_test/results/active_diag_20261013_014257`

最终冻结RTL仿真：`/home/sphenicidition/Documents/fpga/migration/gw138k_audio/push2_workstation/touchboard_test/results/active_diag_20261013_014257/handoff_profile_sim/verification.json`，638个完整UART帧通过；常规RTL回归和Tk/伪终端测试也通过。

最终下载与GUI：2026-10-13T02:29:10.730241+08:00，SRAM独立读回 `0x54420109`；GUI PID 219218。最后600帧：U1 READY 600帧，带按键位600帧；U2 READY 0帧。会话累计CRC错误1、丢帧0；保存的解码帧均通过CRC。详细数据见 `handoff_hardware.json/jsonl`。Flash未写，硬件触摸未验收。


## 03:20 后续引脚监听实测

新增独立SCL/SDA监听，两组共1167个成功事务与主接收器逐字节一致，直接抓到异常原始值及全键状态；GPIO初始化对照未修复，另一次读地址NACK正确报告。已恢复SRAM09和GUI，Flash未写。U3曾回应而恢复后窗口未回应，不再概括为始终无应答。详见 [WIRE_AUDIT_20261013.md](WIRE_AUDIT_20261013.md)。
