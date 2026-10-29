# USB1 Full-Speed 与 25K 识别组件

这是显式的 USB1 12 Mbit/s 开发配置，**不使用 USB3300/ULPI，也不是把 USB2 强制降速**。138K 目标是独立识别/链路诊断，25K 目标是保留现有演奏、BLE、触摸、灯光、LCD 和 PL 的完整键盘 FS 配置。两者都不自动替换 accepted full83、timing85、resource-timing、新板整机或当前 Flash。

协议与设备侧说明见 `projects/25k/example/MIDI_KEYBOARD/docs/USB1_FS.md`，日期化验证和候选身份见 `../../reports/USB1_FS_25K_20261028.md`。以下命令从仓库根目录运行。

## 模块边界

| 文件 | 职责 |
|---|---|
| `workstation_usb1_phy.sv` | 48 MHz UTMI 与 D+/D−、复位期间三态；复用锁定的 `usb_fs_phy` 原始字节 |
| `workstation_usb1_host.sv` | 原生 RV32I CPU、已验证的 CPU 总线、锁定 FS MAC 和 PHY；向消费者暴露服务总线及会话有效状态 |
| `workstation_usb1_clock.sv` | 138K 的 PLL 48 MHz 与同步复位释放；显式读取锁定的 138K `PLL` cell/helper，不使用 25K 的 `PLLA` |
| `workstation_usb1_diagnostics.sv` | 仅用于诊断的 MMIO 投影、事件握手与计数；没有音频参数权威副本 |
| `workstation_usb1_identify_top.sv` | 独立板级组合，仅有 50 MHz、USB1 D+/D− 和 UART TX |
| `../../usb1_identify.c` | 包含生产 `firmware.c` 的识别、MIDI 和 `gw25k_panel.h`，额外发布诊断状态；不复制枚举/PL 编解码 |

`workstation_usb1_host` 可在后续整机组合中连接现有 owner；本批独立 top **没有音频、DDR、HDMI、CNN 或公共参数提交模块**。MMIO ACK 只代表服务接收，不代表音频应用。不能把此组件综合成功写成 USB1 完整工作站已经集成或板上发声通过。

## 识别和状态

1. FS attach 检测后沿用生产 Host 的等待、根端口复位、地址设置和配置读取。
2. 先按 MIDIStreaming 1.0 描述符寻找合法 Bulk IN；不只比较 VID/PID。
3. 本地实验 `FB9A:FB9B` 同时具备 MIDI OUT 和接口 2 独立 vendor IN/OUT 才进入 25K 分支；缺少屏控条件时仅作为 generic MIDI。
4. 屏控仍使用现有 PL local-v1 HELLO/CAPS，校验画布、格式、tile 和超时能力后才置 PL 就绪。接口、CRC、session、序号、重试均沿用现有契约，不增加私有识别命令。

独立诊断 ABI，**不是整机公共 MMIO 的新分配**：

| 地址 | 含义 |
|---|---|
| `0x00` | 生产 Host 发布的 bit0 connected、bit1 generic MIDI、bit2 25K qualifier；25K 完整端点枚举后为 7 |
| `0x70` | `{PID,VID}`；本地 25K 为 `0xFB9BFB9A` |
| `0x74` | 低位为生产设备模式（25K=3），bit8 connected，bit9 已完成 PL CAPS；`0x103` 与 `0x303` 区分枚举和 PL 就绪 |
| `0x78` | 已交接 MIDI/原始输入服务写的饱和计数，跨重连累计，FPGA 复位清零 |
| `0x7c` | 本次新候选 BUILD_ID |

UART 使用生产设置的名义 115200 baud，打印 build、枚举信息和状态变化。顶层始终接收事件并计数，不发声；显示反馈读值为诊断占位零值，不冒充真实工作站状态。

## 背压、取消与故障

- 普通 MIDI 经生产解码进入既有 18-bit `{kind[3:0],a[6:0],b[6:0]}` 服务写；没有隐含的来源/session/revision 字段。可复用 host 的服务消费者必须保留现有 `workstation_session`/PANIC 边界，不能绕过它直接修改参数。
- 外部消费者 `ready=0` 时，CPU 总线保持该请求。既有总线 10 ms watchdog 超时会撤销请求并置 `fault_o`，不承诺无限排队或静默保留；系统集成必须处理 fault 和生命周期。独立诊断 top 的消费者恒 ready，不存在音频调度等待。
- 连续 SE0 约 1 ms 使 `session_valid_o` 失效，诊断状态立即清除、被背压的旧事件不再 valid，并确认丢弃旧服务写以释放 CPU。短 EOP 不清会话；软件的无回复 50 ms 断开/重枚举机制保持。
- 根端口复位也会使会话失效。新接入不复用旧 PL session 或 USB toggle。诊断计数不是消息可靠交付到音频的证明。
- 25K 的 USB-MIDI 和 vendor 分别使用原有异步 FIFO、端点 buffer、ACK 提交和 NAK 背压；CRC/重复包不向应用重交付，USB reset/deconfigure 清除相应会话。LCD/BLE 不阻塞 USB MIDI 的独立队列。

## 构建和来源

```sh
python3 projects/138k/push2_workstation/usb_a/build.py \
  --usb1-identify --usb1-board 138k \
  --netlist-dir "$HOME/Documents/fpga补充文档" \
  --usb1-output projects/138k/push2_workstation/usb_a/results/usb1_host_C11028F5 \
  --user-code C11028F5 --synthesis-only

python3 projects/138k/push2_workstation/usb_a/build.py \
  --usb1-identify --usb1-board 25k \
  --usb1-output projects/25k/example/MIDI_KEYBOARD/results/usb1_251028F4 \
  --user-code 251028F4 --synthesis-only
```

`--prepare-only` 可替代 `--synthesis-only`。本轮目录已存在时拒绝覆盖；重跑用新目录，输入变化用新 UserCode。入口拒绝与整机、ULPI、HDMI、资源候选等 profile 混用，既不写 latest 指针，也不调用 programmer。

`tools/workstation_usb1.py` 选择版本化原生源、现有 25K 源和锁定 vendor，记录原始/暂存 SHA256、Git HEAD、UserCode、固件 ROM 和引脚依据。138K PLL 支持输入从 `resource_rework_route0` 按哈希取出；不依赖私有旧 staging。25K 的官方 `PLL_INIT` 来自既有 USB1 工程，校验固定 SHA256 并保持原字节。没有修改冻结基线、vendor 或原始清单。

Gowin 此版本的 Tcl 不提供所尝试的 Verilog define/HDL 参数选项，故生成独立 `usb1_profile.vh` **仅声明编译期端口选择和 BUILD_ID 常量**；原生 RTL、协议、会话和业务实现均不由文本生成。默认工程的同名空 header 保持 USB2。header、CST、SDC、Tcl 和所有暂存输入都受哈希检查；已有综合证据拒绝覆盖，工具 ERROR 即使伴随零退出码也拒绝通过。后续若统一编译配置机制，迁移这些常量并保留相同输入/展开回归，再退休此配置 header。

综合审计校验实际顶层、PLL/PLLA 类型与 50×24/25=48 MHz、FS PHY 与保留功能、资源报告/网表一致性；138K 还从 32 个 RAM bit plane 重建并逐字节核对 64 KiB CPU ROM。BSRAM 数是**综合等效数**，不是布局布线物理块数。

## 引脚和物理边界

138K USB1 也可连接 25K USB2/USB3300，由设备回退到 FS；不是把 25K 保持在 HS。该路线使用修正复位尾段的新双速设备核，不选择 25K 的 `MIDI_USB1_FS`，详见 [混合链路](../../../../../25k/example/MIDI_KEYBOARD/docs/USB2_FS_FALLBACK.md)。25K USB2 的端接/上拉由 USB3300 控制，下文关于 25K 外部 1.5 kΩ 上拉的要求仅针对其 USB1 软 PHY。

- 锁定新底板网表 USB1 是 Type-C：D+ 经 R33 到 H13，D− 经 R34 到 G13；USB2 才是 USB3300，`USB3` 在该网表中是 HDMI。
- R35/R36 标为 15 kΩ 数据线下拉，R37(NC) 是可选 D+ 1.5 kΩ 上拉；Host 角色不能装该上拉。代码不以 FPGA GPIO 高电平或弱上拉替代 USB 电阻。
- **网表 R1/R2 为 CC1/CC2 到地的 5.1 kΩ（Rd），不是已验证的 Type-C Host Rp。** VBUS1 经 F1 直接接板上 +5V，没有可控 VBUS 开关。须核实实际装配、角色/线缆、5V 与防反灌；不能仅接 C-C 线就假定 Host 角色成立，也不授权改阻值或板卡供电。
- 25K USB1 为 L6/K6，需要既有 USB1 工程记录的物理 D+ 1.5 kΩ 上拉与正确供电。没有该电阻时综合/仿真成功也不会自动枚举。
- 标准 `--usb1-identify` 入口仍只到综合。2026-10-29 的显式混合链路另有独立 P&R 实验，见 [候选和门禁](../../reports/USB1_HOST_USB2_25K_FS_20261029.md)；不据此推断完整工作站、模拟电气、板上 PLL、SRAM 或 Flash 验收。后续板卡操作需另行明确授权。

## 仿真

```sh
python3 projects/138k/push2_workstation/usb_a/sim/test_workstation_usb1.py
python3 projects/138k/push2_workstation/usb_a/sim/test_workstation_usb1_constraints.py
```

定向回归包括 FS-only 描述符/STALL、64 字节端点、重复/丢 ACK/CRC、halt、suspend/resume，以及真实 RV32I 固件→FS MAC/NRZI D+/D−→25K 真实桥接与 PL endpoint。两端 USB 时钟有独立相位和约 96 ppm 相对偏差，应用域为 50 MHz；验证两次接入的 256 条 MIDI、CAPS、tile、背压稳定和拔出取消旧事件。LCD tile 完成使用模型，电阻使用数字强度解析，不等于板上波形、真实 LCD 或音频验收。

综合网表审计还要求三个 USB 首级采样 DFF 各自唯一命中对应输入例外，允许工具将内部 PHY 实例改名为 `phy_0`，但不扩大到第二级采样。138K 仅对三个 `release_q` 同步释放寄存器的异步 CLEAR 声明异步控制例外：PLL 辅助状态和 power-ready 共同形成异步复位，不把该解除边沿当作同步 recovery/removal；三级链负责吸收这个异步边沿。后续数据路径、三级移位释放、复位输出的 recovery/removal 与 50/48 MHz 时钟继续检查。审计核对三级初始化/常数一/串联/共时钟/共 CLEAR，定向仿真覆盖停钟及锁定丢失时无时钟边沿的复位断言和三拍恢复；不是异步时钟组或整域 false path。
