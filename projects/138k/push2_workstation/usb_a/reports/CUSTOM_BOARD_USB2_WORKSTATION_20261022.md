# 新板 USB2：生产工作站固件与实际 25K MIDI／PL

日期：2026-10-22。起点为已推送的 WIP `7727df770e38349544ed0647e48ce05eec4db4f3`；本轮改动尚未再次提交／推送。开发身份为 `custom138k_usb2_workstation_dev_20261022_r1`，精确输入、工具、日志哈希、ROM／网表身份、验证边界及剩余工作见 [verification.json](custom_board_usb2_workstation_20261022/verification.json)。这不是整机候选、UserCode、位流或部署身份。

[前一 CPU 阶段](CUSTOM_BOARD_USB2_CPU_20261022.md) 的旧输入和证据保持原样；本轮选择实际业务固件，不把旧 probe 通过解释为本轮应用通过。

## 1. 真实应用链路

显式 `--prepare-usb2-soc --usb2-firmware-profile workstation` 将现有生产 `firmware.c`、`gw25k_panel.h`、第一方 Host／CPU port／backend，与锁定 startup／minlibc／USB core 编译成 RV32I／ILP32 ROM；不用测试用 main 或旧 FS `usb_hw.c`。默认仍为 probe，accepted full83／timing85／resource 输入选择均不变。

原生后端保留实际 HS 512／FS 64 的上限、逐端点 IN toggle、重复 DATA 丢弃、ACK／NYET 接受及后续 PING、控制状态阶段提交和换代取消。原生 Push 路径通过现有像素服务软件分包，不再调用旧 FIFO preload；25K 接收临时数组扩大为 512，逻辑 PL reply／CRC／sequence／TILE wire contract 不变。详细限制和复现入口见 [后端合约](../drivers/usb2/WORKSTATION_BACKEND.md)。

真实 VexRiscv 运行生产 main，经第一方总线／MMIO／MAC／PHY、同一 USB3300 物理字节模型，对接实际 `projects/25k/example/MIDI_KEYBOARD/` 的 MIDI USB device、描述符和 `panel_display_endpoint`：

| 模式 | 本轮完成条件 | 模拟完成时间 |
|---|---|---|
| 默认允许 HS | 地址 1／configured／实际 HS；生产固件识别 GW25K mode 7；128 个逐字匹配、有序 NoteOn／Off；PL CAPS 与两块坐标／尺寸正确且收到完成应答的 TILE；CPU fault／协议错误为零 | 503 ms |
| 显式强制 Host FS | 同一实际设备回落 FS，端点 64 字节；相同枚举、事件、PL 与故障检查 | 417 ms |

这里只缩短 attach 去抖到 100 µs；50 ms 根复位、10 ms recovery、SOF、实际 CPU／参考／ULPI 48／50／60 MHz 不加速。bench 不使用 probe 的 `f0/f4/f8/fc` 服务，也不由服务模型伪造 PASS。

**服务边界仍未集成**：外部工作站 MMIO 使用延迟五个 CPU 拍、读零的模型，MIDI 事件在其写入边界检查；LCD 只有 20 个 ULPI 拍后的 tile 完成模型。结果不证明真实参数 owner、事件 FIFO／DSP、LCD 总线、全屏显示、物理 USB 或实板效果；强制 Host FS 也不替代真实 Push 接入验收。

## 2. 本轮 FS 失败的根因

推送检查点中 HS 已通过，强制 FS 在第二次根复位后反复读不到设备描述符。增加 trace 后发现，Host 解除 SE0 时，设备可能仍为 `TermSelect=1 / XcvrSelect=0` 的等待 chirp 状态；旧模型只在 `XcvrSelect=1` 才提供 D+ 上拉，Host 读线态时误见 SE0，退回 attach，持续重复根复位。

USB3300 DS00001783C §6.2.2、Table 6-8（第 34 页）明确 Peripheral Chirp 与 Peripheral FS 均有 D+ 上拉。本轮核对本地同版手册文本并渲染检查表格；手册 SHA-256 为 `33e73e37f5110cb9e3ef66ccf8c7fdd4a16593c7b1afcff0c5df523e41963a9e`。修复 `usb3300_host_model.sv` 的这一建模错误，新增十项独立检查，覆盖 HS／FS termination、chirp、驱动复位及仍在等待 chirp 时释放复位。未修改实际 Host FSM、速度检查、超时、CPU fault 判定或 vendor 来使测试通过。

这是当前实际 25K 控制序列的简化 PHY 模型修复，不是对任意 UTMI 控制组合或模拟电气的 USB 合规验证。

## 3. 固件与实际组件综合

| 配置 | binary 字节 | 静态 RAM 结束 | 完整 64 KiB ROM SHA-256 |
|---|---:|---:|---|
| 业务、允许 HS | 22,176 | 28,024 | `31c4d7d58141ef0ec2b33f826a9c22251b7d4f23771cbaa189427b0f1277d457` |
| 业务、强制 FS | 22,232 | 28,080 | `80a3415b6c89de06f359b268e14b7e826c14f6dd34ea54ddad4739ecf422aa41` |

第一方业务代码以 `-Wall -Wextra -Werror` 编译，vendor 保留原 `-Wall` 策略；60,000 字节静态门禁未放宽。静态余量不等于运行期栈峰值或 warm CPU reset 的可变 `.data` 恢复证明。

对允许 HS 的业务 ROM 执行明确 14 项 RTL 的 GowinSynthesis V1.9.12.03、目标 `GW5AST-LV138PG484AC2/I1` 组件综合：38 SDPB、1,922 寄存器；从网表 INIT 重建全部 16,384 个 ROM word 并逐字核对。五条综合警告均为未修改 vendor；独立 SoC lint 继续只允许已记录的第一方 CPU 本地复位 `SYNCASYNCNET`，不屏蔽其他第一方警告。

本机工程 `/tmp/workstation-usb2-workstation-synthesis-20261022`；输入 manifest SHA-256 `91b18dec20d8b8af21dcf2997312aabd8c9d44dd6c43e950d2eba231c0bb5987`，网表 SHA-256 `f12de6003cfc64502253d63b42ede8e418d4efe3bb83e382ca70a96721a56f19`。这不是 P&R、整板物理 BSRAM 数、时序／CDC／PLL 门禁或新位流。

## 4. 本轮验证与复现

| 本轮执行 | 独立 Python 测试数 | 结果 |
|---|---:|---|
| 实际应用＋PHY 模型＋Push 帧＋backend ASan／UBSan | 4 | 全通过，93.707 s |
| 准备／来源／混用拒绝／实际 probe ROM 综合 | 15 | 全通过，30.391 s |
| CPU 总线／lint／实际 probe HS／FS | 3 | 全通过，43.067 s |
| MMIO／邮箱／取消／缺钟／HS／FS／Gowin RAM | 7 | 全通过，362.865 s |
| accepted 来源 10＋固件 staging 6＋引脚 25＋clean baseline 23 | 64 | 全通过，6.922 s |

共 **93 个独立 Python 测试，无 skip**；速度／时钟子场景、重复执行及单测内部 C 子程序不重复计数。另按既有 `sim/run_generic_midi.py` 的编译策略执行两项 legacy 生产 C ASan／UBSan 回归，均通过。额外加 `-Wextra -Werror` 检查旧 `test_hotplug.c` 会遇到其未改动第 107 行缩进警告；没有为此修改无关测试或隐藏警告，也不宣称 legacy 测试已通过该额外严格策略。

默认宏关闭的旧业务固件重新编译后，与 native 修改前保存的实际 binary 逐字节一致：19,788 字节，SHA-256 `1634ace36de82f169654caca844b579f96553b6cd2f6e2c4893964b4458d09be`，静态 RAM 结束 25,548。三条 clean prepare 未改用新原生 profile。

```sh
GW138K_USB2_APPLICATION_EVIDENCE=/tmp/usb2_application_evidence \
  python3 projects/138k/push2_workstation/usb_a/sim/test_workstation_usb2_application.py -v
python3 -m unittest discover -s projects/138k/push2_workstation/usb_a/sim \
  -p 'test_workstation_usb2_*.py' -v
GW138K_VERIFY_CLEAN_PREPARE=1 PYTHONPATH=projects/138k/push2_workstation/usb_a/sim \
  python3 -m unittest test_current_workstation_sources test_stage_usb_firmware \
  test_workstation_pinout test_workstation_baselines -v
```

指定证据目录须不存在。本轮保留 `/tmp/workstation-usb2-application-evidence-20261022/hs_0` 与 `hs_1`：来源复制前后及执行后核对，包含实际 peer include、ROM、工具、编译和执行日志。版本化源码及本轮 JSON 中的身份是权威，不能把 `/tmp` 当作唯一生产输入。

## 5. 整体目标、回退与下一步

下一步是将此真实生产 C／原生 Host 组合接到现有工作站输入控制 owner，验证事件 FIFO、lifecycle／PANIC、公共参数应用及真实音频调度／显示快照；不能让服务 ACK 模型成为产品实现。随后形成显式新板组合根、约束和实际可观察诊断，分别执行完整综合、P&R、时序／CDC／PLL／资源门禁。

全范围仍按 [新板 bring-up 清单](CUSTOM_BOARD_BRINGUP_20261022.md)：USB3300 电平转换器实装确认／修正、功放具体型号及 DAC／MCLK／启动静音、HDMI 极性／CEC、TF 真卡、138K BLE 剩余引脚及真实业务／音频路径、实际 Push／25K／音频／显示验收均未由本轮代替。业务使用 bulk 后的运行期 SET_INTERFACE 也仍明确拒绝，不冒充支持任意 alt 切换。

回退是继续已有显式 accepted／resource profile，不选择新原生组件；无需改回 vendor／冻结基线或操作硬件。两份无关用户报告原样保留。没有新板位流、UserCode、硬件验收、SRAM 下载或 Flash 写入；本轮未自动再次提交／推送，整体“可上板观察调试”的目标仍未完成。
