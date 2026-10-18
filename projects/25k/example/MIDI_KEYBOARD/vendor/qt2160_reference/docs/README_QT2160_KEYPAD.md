# 第二颗 AT42QT2160：2×8 矩阵按键与串口检测值

新增功能日期：2026-10-15。原顶层仍为 `rtl/sd_boot_top.v`。

2026-10-16 已针对无触摸误报和状态/数值错时修订；见 [手册复核与稳定性记录](README_QT2160_KEYPAD_STABILITY.md)。

## 接线与地址

第二颗芯片独立使用 SCL=AA17、SDA=AB17，开漏接口，外部上拉至 3.3 V。
用户确认 A0、A1 均接地，7 位地址固定 0x0D。原滑条芯片在另一组 I²C 线上，同地址不冲突。
新芯片不依赖 CHANGE 通知，通过定时轮询工作；RST 应保持有效高电平，校准时不要触摸电极。
原串口继续使用 FPGA TX=L17、RX=M17，115200、8N1、无流控。

## 按键编号与输出

| 串口 KEY | 矩阵位置 | 芯片键号 |
|---|---|---|
| 01～08 | Y0 与 X0～X7 | Key0～Key7 |
| 09～16 | Y1 与 X0～X7 | Key8～Key15 |

每 200 ms 开始一次完整采集：状态、16 键 SIGNAL/REF、再次读取状态，再按芯片键号顺序分别报告。
仅输出前后状态都为按下且 DELTA 不低于芯片释放门限（当前 8）的键，避免将旧状态与松手后的读数配对。
按住时每秒约更新 5 次，松手后停止该键的报告；空闲时不发送按键文本。
原 `SLIDER=...,TOUCH=...` 周期串口报告已关闭，原滑条读取逻辑仍保留。

示例（每行末尾 CRLF）：

```text
KEY=01,Y=0,X=0,SIGNAL=01234,REF=01300,DELTA=+00066
KEY=16,Y=1,X=7,SIGNAL=01000,REF=01100,DELTA=+00100
```

- SIGNAL：该键的 16 位原始检测信号值，读取十进制寄存器 `100+2×芯片键号`，两字节、低字节在前。
- REF：该键的 16 位基准值，读取十进制寄存器 `132+2×芯片键号`，两字节、低字节在前。
- DELTA：`REF−SIGNAL`，显式输出正负号，范围 −65535～+65535；触摸通常使 SIGNAL 下降、正差值增大。
- 数值使用五位十进制，按键编号两位十进制。发出该行表示状态快照中该键处于触摸检测状态。

状态、SIGNAL、REF 分别通过 I²C 读取，先缓存全部数值，再检查第二次状态并发送；不是芯片锁存的同一瞬间原子快照。
松手或再次触摸发生在一个轮询间隔内时，可能无法单独报告该短暂触摸。
按键判断以芯片 Key Status 位为准，DELTA 供观察灵敏度，不能当作压力数值。
初始灵敏度需根据实际电极、盖板和噪声进一步调整。

## 初始化与故障恢复

上电等待 100 ms，读 ID 并确认 0x11；配置、逐项读回比对后执行校准，等待 500 ms，再清除上电状态。

| 十进制寄存器地址 | 值 | 用途 |
|---|---|---|
| 12 | 0x01 | 16 ms 扫描间隔 |
| 13 | 0x01 | 单次测量，避免增加扫描耗时；两次平均的试验版已撤回 |
| 17 | 0x07 | 检测积分 NDIL，正文 6.14 对应连续 8 次采集 |
| 20 | 0x00 | 禁用新芯片滑条，全部用作独立键 |
| 22～37 | 各 0x00 | 禁用 AKS 分组抑制，允许多键同时检测 |
| 38～53 | 各 0x0A | 16 键负阈值 10 |
| 54～69 | 各 0x04 | 启用全部 16 键，恢复手册默认 burst length 4，即 16 脉冲 |
| 10 | 0x01 | 校准 |

轮询读取状态寄存器 2～6，其中 3、4 的 16 个状态位对应芯片 Key0～Key15。
无论是否触摸，均按每键 SIGNAL 两字节、REF 两字节的短事务读取全部数值，供本帧缓存与 JTAG 原始数据分析。
一帧全部 I²C 读取完成后才发布事件，UART 忙不会拉长同一帧逐键数值读取间隔。
读写沿用已验证的 `qt2160_i2c_master.v`，约 100 kHz，每次 START 前总线连续空闲至少 100 µs，写指针后 STOP 再 START。
NACK、总线/延展超时、配置不一致、运行中 RESET 会撤销有效状态并重试识别、配置和校准。
故障不会生成新的假按键数值；已有完整且已交给 UART 的报告允许正常发完。

## 模块与仲裁

- `rtl/qt2160_keypad_reader.v`：新芯片初始化、状态和各键检测值读取；事件通过 valid/ready 保持，UART 忙时不会覆盖下一个键。
- `rtl/qt2160_keypad_uart.v`：冻结一个按键的数据，16 周期 BCD 转换后产生 52 字节报告。
- `rtl/uart_led_controller.v`：新增 `ENABLE_KEY_REPORT` 与字节流握手，按整行仲裁原命令回复与按键文本；顶层设该参数为 1、`ENABLE_SLIDER_REPORT=0`。
- `constraints/qt2160_keypad.xdc`：AA17/AB17、LVCMOS33、开漏上拉及时序例外。
- `sim/tb_qt2160_keypad.sv`、`scripts/test_qt2160_keypad.ps1`：模拟真实 I²C 从机并从实际 UART TX 引脚独立解码。

原 UART 四条 LED 命令仍可使用：`LED1+BREATH`、`LED1+STOP`、`LED2+BREATH`、`LED2+STOP`。
未知命令继续回复 `unknown command`。按键报告与命令回复不会逐字节混合。
WS2812 源码与 16 颗灯的原配置未修改。

## 构建和实板检查

在 `E:/FPGA_Progects/just_paly` 下运行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/test_qt2160_keypad.ps1
& 'D:/AAA_Vivado_installation/2025.1/Vivado/bin/vivado.bat' -mode batch -source scripts/build_uart_led.tcl
& 'D:/AAA_Vivado_installation/2025.1/Vitis/bin/xsct.bat' scripts/program_qt2160_jtag.tcl
& 'D:/AAA_Vivado_installation/2025.1/Vivado/bin/vivado.bat' -mode batch -source scripts/capture_qt2160_keypad_jtag.tcl
& "$env:USERPROFILE/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe" scripts/verify_qt2160_keypad_capture.py
```

JTAG 固定为 Digilent JTAG-SMT2 `210251760862` / xc7z020；下载当前易失 FPGA 配置并启动原 ARM 软件，不核验 HDMI/摄像头数据流。

新增 ILA 探针：

- `keypad_result[63:0]`：63:48 状态采样计数，47:40 错误码，39:32 General Status，31:16 Key Status，15 配置有效，14 SCL，13 SDA，12:8 保留，7:0 ID。
- `keypad_done`：识别完成、状态采样完成或错误脉冲。
- `keypad_event_result[63:0]`：35:32 芯片键号，31:16 REF，15:0 SIGNAL，高位补零；`keypad_event` 表示已交给串口格式模块。
- 原 `uart_byte_result` 的 flags 位 2 新增按键文本标记（0x04），位 1 仍为滑条，位 0 仍为命令回复。
- `keypad_scan_result[63:0]`：63:48 帧号、47:44 芯片键号、43 采集前状态、42 采集后状态、41 报告候选、40 配置有效、39:32 General Status、31:16 REF、15:0 SIGNAL。`keypad_scan_done` 在每帧的每个键记录有效时为 1，包含未触摸和被过滤的键。

修改前的源文件、bit 和 ltx 已备份到 `verification/before_qt2160_keypad_20261015/`。

## 验证记录

2026-10-16 23:02 最新复测：已重新 JTAG 下载现有固件；两轮共 2048 条键记录，SIGNAL=120～166，
DELTA=−1～1，无零值、原始按键检测或扫描超限。当前空闲读数明显改善，实际触摸响应仍需单独验证。
详情见 [23 点复测记录](verification/keypad_retest_20261016_2302.md)。以下保留此前历史结果。

2026-10-16 重焊后已重新下载当前短读/整帧缓存版本，并完成两轮原始采集：
ID=0x11、配置正常，未出现原始按键检测；仍有部分通道信号偏低和零值，不能据串口安静判定所有按键恢复。
最新详细结果见 [重焊后测试记录](verification/keypad_after_resolder_20261016.md)；下述 10 月 15 日记录为历史版本。

新增集成仿真已通过：错误 ID、配置读回错误、16 字节传输、100 µs 空闲、时钟延展、两排与全部 16 键、
多键同时触摸、SIGNAL/REF 的 0/65535 边界与正负差值、UART 背压、实际 TX 引脚文本解码、
命令整行仲裁、空闲及滑条报告抑制、数值读取 NACK、运行中 RESET 后重新配置。
原 UART 命令仿真和原滑条集成仿真也均通过。

实板状态采集结果保存在 `uart_debug/qt2160_keypad_jtag_verification.json`；
该检查只表示芯片识别、配置和状态读取，不自动证明实际手指触摸或 USB 串口接收端已通过。

2026-10-15 实板结果：完整编译通过，最终报告 WNS=0.875 ns、WHS=0.020 ns，失败端点为 0，规则检查无错误；已通过 JTAG 下载当前镜像，
22:36 状态采集 ID=0x11，配置完成，错误码 0，Key Status=0x0000（全松开），采样计数 152。
General Status=0x02 为 CC 标志，当前不作为触摸状态；矩阵键判断使用 Key Status。
SCL/SDA 均为高电平。未进行实际手指触摸测试；本机仅枚举蓝牙 COM4/COM5，未验证 USB 串口接收端。
未核验 HDMI/摄像头数据流。
