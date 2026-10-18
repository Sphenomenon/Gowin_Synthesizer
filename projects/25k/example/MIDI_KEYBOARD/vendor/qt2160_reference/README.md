# QT2160：16 键矩阵与八段滑杆源码包

打包日期：2026-10-16。源工程：`E:/FPGA_Progects/just_paly/just_paly.xpr`。
本包保存当前工程的源代码原件，含最新矩阵触摸稳定性修订。
适合阅读、复用和迁移到高云 FPGA；不含 bit、ltx、网表、IP 生成物、Vivado 工程缓存或编译输出。

## 文件入口

| 文件 | 功能 |
| --- | --- |
| `rtl/qt2160_keypad_reader.v` | 第二颗 QT2160，Y0/Y1 × X0～X7 的 16 键初始化、配置校验、校准和轮询 |
| `rtl/qt2160_keypad_uart.v` | 键号、坐标、SIGNAL/REF/DELTA 的串口文本格式化 |
| `rtl/qt2160_slider_reader.v` | 第一颗 QT2160，Y0 + X0～X7 滑杆，位置 0～255，每秒采集 5 次 |
| `rtl/qt2160_i2c_master.v` | 两个 reader 各自实例化的共用 I²C 主机模块，地址固定 0x0D |
| `rtl/uart_led_controller.v` | UART 整行仲裁、滑杆报告、键盘报告及原 LED 命令处理 |
| `rtl/uart_rx.v`、`rtl/uart_tx.v` | UART 收发，默认 115200/8N1 |
| `rtl/led_breath_channel.v` | `uart_led_controller` 使用的依赖模块 |
| `reference/sd_boot_top.v` | 当前完整工程的原始顶层，仅供查看现有实例化和接线 |
| `constraints/` | 原 Xilinx 平台触摸、UART、时钟和 LED 引脚约束 |
| `sim/`、`scripts/` | 两个功能各自的现有集成仿真源码和运行脚本 |
| `docs/` | 原功能说明、手册复核过程及最新空闲测试记录 |
| `MANIFEST_SHA256.txt` | 包内文件的 SHA-256 校验清单（不含清单自身） |

`rtl/` 已包含这两个功能及串口模块所需的全部子模块。该目录为可复用模块集合，没有独立板级顶层。
`reference/sd_boot_top.v` 还包含原 HDMI、摄像头、Zynq PS 等实例，相关模块不在本包，
因此请参考其中触摸部分接线，在目标工程顶层实例化 `rtl/` 中的模块；不要将该参考顶层直接作为独立工程综合。

## 当前接线和功能

默认系统时钟为 50 MHz；两颗芯片各使用独立 I²C 总线，A0/A1 均接地，7 位地址均为 0x0D。

| 功能 | 信号 | 原板引脚 |
| --- | --- | --- |
| 八段滑杆 | SCL / SDA / CHANGE | Y16 / AA14 / V15 |
| 16 键矩阵 | SCL / SDA | AA17 / AB17 |
| 串口 | FPGA TX / FPGA RX | L17 / M17 |
| 50 MHz 时钟 | clk | M19 |
| 串口模块附带 LED | led1 / led2 | P20 / P21 |

矩阵 KEY01～KEY08 对应 Y0/X0～X7，KEY09～KEY16 对应 Y1/X0～X7。
有效按键的串口输出示例（CRLF 结尾）：

```text
KEY=01,Y=0,X=0,SIGNAL=00120,REF=00140,DELTA=+00020
```

矩阵默认 NTHR=10、BL=4、BREP=1、NDIL=7、校准等待 500 ms，每 200 ms 轮询。
先读取触摸状态，再缓存 16 键数值，最后复核状态；前后均检测到且 DELTA≥8 时形成报告候选。
滑杆文件保持当前原件，其默认校准等待仍为 200 ms，未随矩阵模块改为 500 ms。

## 如何启用滑杆串口输出

当前原工程使用以下配置，滑杆持续读取，但只输出矩阵按键报告：

```verilog
uart_led_controller #(
    .ENABLE_SLIDER_REPORT(0),
    .ENABLE_KEY_REPORT(1)
) u_uart_led (...);
```

在你的顶层实例化时，根据需求设置：

| 串口输出需求 | ENABLE_SLIDER_REPORT | ENABLE_KEY_REPORT |
| --- | ---: | ---: |
| 仅矩阵按键（当前配置） | 0 | 1 |
| 仅滑杆 | 1 | 0 |
| 两者同时输出 | 1 | 1 |

滑杆报告格式为 `SLIDER=128,TOUCH=1`，无效数据为 `SLIDER=ERR,TOUCH=0`。
两者同时启用时共享串口，采用整行仲裁；多键报告会使滑杆文本发送存在排队延迟。
只使用其中一种功能时，未使用的 UART 数据输入应接确定的常量或有效信号，不要悬空。

## 迁移到高云时的接线要点

触摸 reader 的 `scl_low`、`sda_low` 为 1 时表示拉低总线，为 0 时表示释放总线。
应在目标 FPGA 顶层实现开漏三态，并把实际引脚电平反馈给 `scl_in`、`sda_in`：

```verilog
assign touch_scl = touch_scl_low ? 1'b0 : 1'bz;
assign touch_sda = touch_sda_low ? 1'b0 : 1'bz;
assign touch_scl_i = touch_scl;
assign touch_sda_i = touch_sda;
```

矩阵总线使用相同接法。也可以使用高云对应的双向 I/O 原语；原顶层中的 Xilinx `IOBUF` 需要替换。
SCL/SDA 保留外部上拉，不能主动推挽输出高电平。两颗同址芯片必须继续使用各自的总线。
滑杆的 CHANGE 仅用于状态诊断，读取采用轮询；目标板不接该输入时，可在逻辑侧接 `1'b1`。

原 XDC 中的球位和约束语法只适用于原 xc7z020 板。迁移时应建立目标器件的引脚、3.3 V 电平与时钟约束，
保留模块使用的寄存器上电初值语义，并检查 I²C 异步输入约束及同步器。
若目标时钟不是 50 MHz，需要同时调整 reader、UART 的 `CLK_HZ` 和 I²C `HALF_CYCLES`、
`BUS_FREE_CYCLES`、`TIMEOUT_CYCLES`，使 I²C 不高于约 100 kHz、STOP→START 空闲不少于 50 µs（当前为 100 µs）。
上述低层时序参数是周期数，不会全部随 `CLK_HZ` 自动换算。

## 仿真与实测范围

`scripts/test_qt2160_keypad.ps1`、`scripts/test_qt2160_slider.ps1` 是原集成仿真脚本。
运行前修改脚本中的 Vivado 安装路径；从包根目录执行，首次运行需先建立日志目录：

```powershell
New-Item -ItemType Directory -Path uart_debug -Force
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/test_qt2160_keypad.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/test_qt2160_slider.ps1
```

原功能文档中的全工程构建、JTAG 和历史日志路径仍指向源工程，并非独立包内流程。
本包没有可直接烧录的镜像，需要在目标工程完成顶层集成和约束后重新编译。

最新 23 点空闲复测：两轮共 2048 条记录，ID=0x11、SIGNAL=120～166、DELTA=−1～1，
无零值、原始按键检测或扫描超限。此前异常分布本次未复现；实际触摸对应关系和长期稳定性尚未据此确认。
详见 `docs/keypad_retest_20261016_2302.md`。本次打包不修改硬件中的程序。
