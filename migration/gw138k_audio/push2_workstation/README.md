# Push 2 → 138K 工作站

**2026-09-11 当前路线：J18 USB-A。** 已验收的 USB-A Push Host 已与完整音频/HDMI/AE350 工程合并为 D50E，并在用户后续授权后 SRAM 下载、回读及数字验证通过，见 [USB-A 当前工程](usb_a/README.md)。最初离线阶段未占用板端；当前板端记录见 `usb_a/BOARD_CURRENT.json`。Flash 未写。USB Host 使用 FPGA 内 VexRiscv 固件，音频保持 RTL。

以下 CH569/HSPI 内容是历史试验记录，不作为当前接线、下载或验收说明。

## CH569 / HSPI 历史

当前为独立迁移候选，目标仍为 **GW5AST-LV138PG484AC2/I1＋NEO Dock 31005**。不修改队友 Dev、原 Xilinx 验证工程或历史位流。实际构建与上板状态以本目录 `results/` 的对应版本记录为准。

链路：Push 2 ⇄ CH569 USB HS Host ⇄ 原生 HSPI16 ⇄ FPGA 工作站。CH569 使用 WCH SDK 固件处理 USB；FPGA 负责 Push 协议、屏幕像素、灯光、MIDI 映射以及逐样本音频运算。电脑只用于配置/诊断，不转发演奏 MIDI。

这是当前用户授权的 CH569 集成路线。它不等于“USB Host 完全纯 RTL”：J18 的纯 RTL USB 路线仍独立保留。

| Push 控件 | 138K 操作 |
|---|---|
| 64 个打击垫 | MIDI 36–99 半音连续排列，保留力度；长按持续发声，松手释放 |
| 左侧触摸条 | 弯音；松手回中；条灯由 Push 跟随位置 |
| 屏幕上排前 3 键 | A / B / C 合成模式 |
| 屏幕上排后 5 键 | 长笛 / 弦乐 / 铜管 / 马林巴 / 钢琴 |
| 屏幕下排前 3 键 | 延迟 / 合唱 / 混响开关，可叠加 |
| 屏幕下排第 4–7 键 | 立体声 / 仅左 / 仅右 / 静音 |
| 屏幕下排末键、Stop | 全部音符关闭 |
| 顶部旋钮 1、Master | 总音量 |
| 顶部旋钮 2 | 颤音深度 |
| 顶部旋钮 3 | 滑音时间 |

其余按键暂不映射。触摸旋钮产生的 note 0–11 不作为演奏音符。只接收 cable 0 / channel 1；初始化会将 Push 切到 Live mode。

Push 的 960×160 屏幕显示实际应用到音频核心的模式、音色、效果、路由、音量、颤音、滑音和弯音，并显示最近音符、力度及 64 垫按下状态。屏幕在帧边界锁存已有 50 MHz 状态快照，目标刷新 10 fps。沿用原 HDMI 三种分析图形和准确 48 kHz 音频路径。

LED 及屏幕传输均等到 USB ACK 才推进；NAK 保留包内容和 DATA toggle 后重试。CH569 在每次请求/响应之间轮询 MIDI IN，MIDI 输入解码独立于屏幕调度器。已仿真验证：屏幕 OUT 返回 STALL 后，音符仍通过异步 FIFO 进入 76.8 MHz 音频域。音频不等待 USB、屏幕、UI 或 DDR。

## 实现来源

- `vendor/`：此前移植的 Push RTL 原件，只读副本；来源及原始 SHA 见 `ORIGINS.json`。
- `rtl/push2_led_tx.sv`：在原件上加入按钮 CC、Live mode 及触摸条配置。
- `rtl/push_hspi_phy.sv`：由底板随附 `EXM_HSPI.sv` 派生，使用其已实现 CRC 的 16 位模式。
- `firmware/`：在已真机接收 Push MIDI 的 CH569 v2 最小程序上加入双向 HSPI 和 USB OUT；WCH/ISP 的固定来源沿用 `ch569_midi_probe`，构建时记录全部输入哈希。
- 完整工程冻结自已恢复的 93D0 工作站：位流 SHA `92c270d7711da7c85b7bcdbef2ea082d665dd1789858695bab4417f72615b787`。

## HSPI 边界

FPGA 发起单个请求 → CH569 处理可选 USB OUT、轮询一次 MIDI IN → 返回固定 544 字节响应 → FPGA 消费完 MIDI、并等待至少 200 个 50 MHz 周期（4 μs）的方向切换间隔后才发下一请求。FPGA TX 为 50 MHz；CH569 TX 为 120 MHz。数据线共用，发送方向分时。CH569 每次切换方向都重新初始化 HSPI DMA/FIFO，并保留原生序号；仅翻转方向位的旧方案在真机返回全零数据，已替换。TX RAM 必须同步读，原生 CRC 覆盖实际传输，序号随成功的原生帧推进。

请求 `P2Q1`：16 字节头＋至多 512 字节 USB 数据。头包含 ticket、opcode（0 轮询/1 OUT/2 启用/3 禁用）、端点、DATA toggle、地址、长度、版本、首次会话标志和原生序号。首次会话用于 FPGA SRAM 重载后对齐 CH569 序号并关闭 USB。

响应 `P2R1`：32 字节头＋512 字节区。头含 ticket、真实 USB OUT 结果、Host 状态、VID/PID、速度、三个端点的元数据、MIDI 字节数和错误计数。只有 CRC、序号、ticket 和格式符合预期才接收。当前仅接受已抓取的 Push 2 2982:1967 高速端点组合：显示 OUT 1、MIDI OUT 2、MIDI IN 82，MPS 均 512。

物理引脚全部见 `integration/push.cst`。`integration/push.sdc` 明确约束返回时钟、I/O 和握手/Gray CDC，不以整组时钟假路径掩盖数据路径。转发时钟的 1–8 ns 源延迟也是工程预算：当前 SDF 没有输出时钟 OBUF 的完整延迟弧，不能称为全温压实证。I/O 的 2.5 ns 发送延迟预算、2 ns 接收建立和 0.5 ns 保持仍属于工程预算；FPGA STA 通过不能代替 CH569 全温压时序认证。

## 构建和验证入口

- `python3 build_firmware.py` → 独立固件、ISP 工具及输入/输出哈希。
- `python3 build_full.py` → 新时间戳工程副本，先校验原 93D0 全部输入，完整综合/布局/布线。
- `python3 scripts/audit.py results/workstation_...` → 原音频/DDR/HDMI/AE350/J18 审核＋新增 HSPI 引脚和 CDC 核查。
- `sim/tb_controls.sv` → 64 垫、力度、长按、映射、背压、断开 panic。
- `sim/tb_hspi_link.sv` → 双向原生 HSPI CRC/序号、512 字节 OUT、真实结果回传、完整 512 字节 MIDI IN（128 事件）、背压、截短但 CRC 有效的回复拒收/恢复，以及方向切换间隔。
- `sim/tb_host_gate.sv` → 原工程 UART 接口的 50 MHz / 115200 接收及启停 SysEx。
- `sim/tb_visual.sv` → 327696 字节完整屏幕传输、84 个初始化/灯光命令、独立端点 toggle、NAK 重试。
- `sim/tb_surface_fault.sv` → 注入屏幕 OUT STALL 后仍能接收音符并写音频 FIFO。
- `python3 scripts/test_parser.py RESULT_DIR` → 使用实抓描述符和畸形输入测试实际 C 解析器。
- `python3 scripts/control.py --seconds 10` → CRC 校验的 A138/C350/K138/E138/U138/P138 串口记录。

## 上板顺序

CH569 旧 v2 通过 PA6（FPGA G18）发送 UART。必须先更新为新 HSPI 固件，再下载会驱动 G18 的 FPGA 候选，否则两个输出会冲突。

1. 保持 FPGA 93D0；CH569 P1 从 Push 换到电脑，BOOT＋RST 进入 ISP。准备好的 `scripts/program_when_ready.py BUILD` 会核对芯片 UID、启动引脚和配置后烧录并校验。
2. 确认固件验证成功，再给 FPGA 下载审计通过的 SRAM 候选；FPGA Flash 不写。
3. P1 仍接电脑时，只验证 HSPI 响应，USB Host 保持关闭。
4. 人工确认 P1 已换回 Push、原装电源接好，才执行 `scripts/control.py --host enable --seconds 20`。
5. 验证 P138 枚举/错误/灯光及帧计数，再验证实际按垫、触摸条、模式/效果键、耳机音效和 Push 画面。

启用 SysEx：`F0 7D 50 55 53 48 01 F7`；禁用末值改为 `00`。FPGA 复位后需重新启用。本阶段的显式启用避免测试时 CH569 仍接电脑却自动进入 Host 模式。

仿真通过、完整构建通过、数字上板验证、实际声光验收分别记录，不能相互替代。

## 当前实测进度

版本绑定见 `CURRENT.json`。完整候选 3BE2 已通过原工作站与新增 HSPI 路径审计，setup/hold 为 0，已 SRAM 下载。AE350、原音频/HDMI 启动和控制回读已通过；Push 输入累计映射 1111 个控制事件，实际核心回读见 note 44 与活动声部。耳机听感仍需用户确认。灯光/屏幕首个 USB OUT 被 CH569 拒收，v5/v6 均抓到 CRC/序号正常而长度不一致，1 μs 等待未解决；v7 候选改为先清 R_DONE 后读长度，并记录两个 DMA 长度寄存器。尚未完成声光验收。

CH569 方向切换修正后，独立 MIDI 诊断阶段有超过 100 万个有效回复、FPGA 链路/USB IN 错误为 0 的记录。当前完整候选加入峰值绝对值寄存，不增加分析状态机周期；九组 PCM、4096 复数频点及 589824 次双缓冲读出比较已通过。原生产位流和工程保持原文件。

v5 诊断扩展：reply byte22 最高位为 1 时，其低 7 位依次表示 CRC、序号、FIFO、物理长度范围、magic、协议版本、头声明长度错误；reply24..27 此时改为 `{实际接收字节数16, 头声明USB字节数16}`，不再解释为 USB IN 错误数。`scripts/control.py` 显式解码此标记，避免把诊断值当成 USB 错误累计。

v7 诊断扩展：reply byte22 为 F8–FD 时，reply24..27 分别轮换显示：当前接收长度/头 USB 长度、清 R_DONE 前 LEN0/LEN1、清后 1 μs LEN0/LEN1、再等 10 μs LEN0/LEN1、清前状态、延迟后状态。长度两个字段各 16 位；状态从高到低为 RX_SC、CFG、RTX_STATUS、INT_FLAG 各 8 位。脚本按类型标记原始寄存器，不当作 USB 错误计数。所有数据长度和 CRC 校验仍强制执行。


### 2026-09-11 晚间 HSPI 长度问题

- v7 真机记录 `results/capture_20260911_190227_133877`：当前 USB 数据 12 字节，原生请求应为 28 字节；LEN0=32，LEN1=28。清中断前、后 1 μs、后 10 μs 均相同，CRC/序号/FIFO 状态为 0。否定了单纯等待不足的解释。
- v8 显式启用 RX 槽位切换并按 RX_TOG 选择完成长度。隔离压力测试仍失败，不能称修复通过。方向切换只保存 SC 的低四位、首次握手也清掉槽位位，v9 候选同时保留包序号和 bit4，并在 UP/DOWN 都保留 RX 槽位配置。v9 是否有效以对应真机记录为准。
- 临时 `probe/length_build.py` 从生产 HSPI 源生成独立变体，允许 Host 关闭时发送 OUT 形状请求。CH569 必须在任何 USB 事务前返回“Host 未配置”结果 3；五种原生请求长度为 16/20/28/32/528 字节，收到 21 次结果后只发轮询。该测试暂停音频/HDMI，完成后恢复 3BE2。
- `results/length_bounded_sim_20260911_191744_205843` 通过 21 个按序变长请求、确定性数据、CRC/序号及后续 6 个空轮询。临时 5337 位流构建 setup/hold 为 0；v8 真机仍失败。这两种结论明确分开。
- `results/gate_wire_monitor_20260911_185529_927993` 从门级引脚独立采样 14 个包，以反射多项式 A001、初值 FFFF、残值 B001 重新验证 CRC，同时核对原生序号及物理包长。全部通过，仅为无 SDF 的门级功能仿真。
