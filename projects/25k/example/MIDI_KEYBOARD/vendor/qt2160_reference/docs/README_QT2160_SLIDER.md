# AT42QT2160 八段滑条与串口连续输出

> 2026-10-15 更新：当前顶层已取消滑条周期串口报告，改为第二颗 QT2160 矩阵按键的检测值输出。
> 滑条读取逻辑仍保留，最新串口功能见 [README_QT2160_KEYPAD.md](README_QT2160_KEYPAD.md)。下文为原滑条功能记录。

在现有 `just_paly.xpr`、`sd_boot_top` 工程中启用 Y0 与 X0～X7 的滑条，使用固定 7 位地址 `0x0D`。
SCL=Y16、SDA=AA14，开漏，不超过 100 kHz；每次 START 前总线连续空闲至少 100 µs。

## 输出

使用原有 UART：FPGA TX=L17、RX=M17，115200、8N1、无流控。
每 200 ms 发送一行，每秒 5 次，十进制位置范围 0～255，固定三位数字：

```text
SLIDER=000,TOUCH=0
SLIDER=128,TOUCH=1
SLIDER=255,TOUCH=1
```

每行结尾为 CRLF。`TOUCH=1` 表示芯片 General Status 的 SDET 位为 1。
`TOUCH=0` 时位置是芯片保留的上次位置，不代表当前手指位置。
初始化、通信或配置校验失败时，发送 `SLIDER=ERR,TOUCH=0`，不会把无效初始化值当作位置。
报告采用固定 200 ms 定时，读取在报告前约 20 ms 发起，发送最近一次完整读取的数据。

原有 LED 指令继续处理；未知命令仍回复 `unknown command`。
滑条报告与命令回复按整行排队，不会逐字节交叉。在未知命令回复正在发送时，报告会等该行完成。

## 芯片配置

上电等待 100 ms，先读取 ID/版本并确认 ID=0x11，再按以下配置初始化。
寄存器地址表使用十进制地址，同时列出十六进制值。

| 寄存器 | 写入值 | 用途 |
|---|---|---|
| 12 / 0x0C | 0x01 | 16 ms 低功耗扫描间隔 |
| 20 / 0x14 | 0x28 | HYST=2，NUM_KEYS=8，Y0 的 X0～X7 |
| 21 / 0x15 | 0x00 | 8 位位置分辨率，0～255 |
| 22～29 / 0x16～0x1D | 各 0x01 | Y0 的八个电极同属 AKS 组 1 |
| 38～45 / 0x26～0x2D | 各 0x0A | 八个电极的负阈值为 10 |
| 54～61 / 0x36～0x3D | 各 0x08 | 八个电极的 burst length 为 8，即 32 个脉冲 |
| 62～69 / 0x3E～0x45 | 各 0x00 | 关闭未用于本滑条的 Y1 八个按键 |
| 10 / 0x0A | 0x01 | 配置读回校验成功后执行校准 |

配置项均通过 I²C 读回比较，再发送校准命令。校准后等待 200 ms，读取地址 2～6 清除上电状态。
运行时每 200 ms 读取地址 2～6，包含 General Status、两字节 Key Status、Slider Position 和 GPIO 状态。
若遇到 NACK、时钟延展超时、总线持续低电平或运行中 RESET 标志，会使数据无效并重新识别、配置和校准。
CHANGE 可以不连接；当前通过定时轮询读取。

上电、重新下载及故障恢复后的校准期间，请保持电极无手指接触。
本配置是八段滑条的初始参数，电极形状、盖板厚度和噪声可能需要后续调整灵敏度；实际手指位置响应要在电极上操作验证。

## 编译、下载与验证

```powershell
Set-Location 'E:/FPGA_Progects/just_paly'
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/test_qt2160_slider.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/test_uart_led.ps1
& 'D:/AAA_Vivado_installation/2025.1/Vivado/bin/vivado.bat' -mode batch -source scripts/build_uart_led.tcl
& 'D:/AAA_Vivado_installation/2025.1/Vitis/bin/xsct.bat' scripts/program_qt2160_jtag.tcl
& 'D:/AAA_Vivado_installation/2025.1/Vivado/bin/vivado.bat' -mode batch -source scripts/capture_qt2160_slider_jtag.tcl
& "$env:USERPROFILE/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe" scripts/verify_qt2160_slider_capture.py
```

JTAG 固定目标为 Digilent JTAG-SMT2 `210251760862`。仅配置当前运行的 FPGA，未烧写启动存储器。
各步骤成功后再继续下一步。下载脚本启动原有 ARM 软件，但不核验 HDMI、摄像头数据流。
现在顶层使用 `qt2160_slider_reader`；旧 `qt2160_id_reader` 及其仿真保留作为历史 ID 调试版本。
旧 ID 采集脚本等待 ID 完成脉冲，该脉冲现在只在初始化识别时出现；运行中的连续采集应使用新的滑条脚本。

JTAG 采集使用 UART 发射器实际接收字节的时刻作为存储条件，1024 个字节可覆盖约 10 秒输出。
验证每行内容与芯片快照相符、行间间隔为 10,000,000 个 50 MHz 周期（200 ms），以及字节发送时序。
这些采样验证 FPGA 内部 UART 发射数据；USB 串口端是否收到数据另行通过串口设备验证。

`slider_result[63:0]`：63:48 采样计数，47:40 错误码，39:32 General Status，31:24 Y0 按键状态，
23:16 Y1 按键状态，15:8 位置，位 7 配置完成、位 6 数据有效、位 1 CHANGE、位 0 SDET。
错误码：1 写地址 NACK、2 指针 NACK、3 读地址 NACK、4 ID 错误、5 写数据 NACK、6 配置读回不匹配、
7 检测到运行中复位、0x40 总线持续低、0x80 延展超时、0xFF 控制器异常。

主要文件：`rtl/qt2160_i2c_master.v`、`rtl/qt2160_slider_reader.v`、`rtl/uart_led_controller.v`。
修改前的固件、源码、探针和记录备份在 `verification/before_qt2160_slider/`。
仿真日志：`uart_debug/slider_simulation.log`；实板结果：`uart_debug/qt2160_slider_jtag_verification.json`。

## 2026-10-13 实测结果（北京时间 20:07）

- 滑条集成仿真通过，包含配置读回错误、16 字节读写、时钟延展、位置 0/128/255、松手、固定报告节拍、UART 引脚解码、命令回复排队、NACK 和运行中复位恢复。
- 原有 UART/LED 命令仿真通过。
- 完整工程编译及最终时序检查通过：WNS=0.355 ns、WHS=0.058 ns，无失败端点。
- 新固件已通过 JTAG 下载；实板 ID=0x11，滑条配置读回校验完成，采样无通信错误。
- JTAG 按 UART 发射器接收字节的事件采集 1024 个样本，解码得到 51 行完整文本。
- 50 个相邻行间隔均为 10,000,000 个时钟周期，即 200 ms，确认每秒 5 次。
- 每行均为 `SLIDER=000,TOUCH=0`；当前采集中未检测到触摸，未验证实际手指滑动时的位置变化。
- 当前电脑仅枚举到蓝牙 COM4/COM5，未枚举到板载 CH340；此次未进行 USB 串口接收端验证。
- 未核验原有 HDMI、摄像头数据流。

构建日志：`uart_debug/build_qt2160_slider_final_console.log`；下载日志：`uart_debug/program_qt2160_slider.log`；
原始采样：`uart_debug/qt2160_slider_uart.csv`；解析日志：`uart_debug/verify_qt2160_slider_console.log`。
