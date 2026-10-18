# RTL8723DS 通用 Verilog BLE 驱动

本包为 Verilog-2001 源码，不依赖 Zynq PS、ARM、VIO、ILA、Vivado Block Design 或器件专用 I/O 原语。集成方提供时钟、复位和板级 I/O。核心代码与已通过实板 BLE 测试的版本逐文件一致，新增通用包装层 `rtl8723ds_ble` 和板级三态示例。

这里的“通用”指 FPGA 集成接口可移植；控制器适配固定为 **RTL8723DS、ROM version=2、115200 8E1 H5**。模块仍需要本包中的厂商 RAM 补丁。没有实现通用经典蓝牙协议栈。

## 文件与接入

`sources.f` 列出全部 7 个必需 RTL 文件。将这些文件加入综合工程，并把根目录 `rtl8723ds_patch.mem` 作为 ROM 初始化输入一同加入。默认 `$readmemh` 路径相对仿真/综合运行目录；工作目录不在包根目录时设置 `PATCH_FILE` 为工具可访问的路径。ROM 文件为 32768 行，每行一个 8 位十六进制字节，前 30147 字节有效。

顶层：`rtl/rtl8723ds_ble.v`。无厂商 IP 或运行时软件依赖。`examples/rtl8723ds_ble_board_top.v` 展示芯片顶层三态接法；不要在 FPGA 内部逻辑层使用三态。

| 端口 | 方向/位宽 | 含义 |
| --- | --- | --- |
| clk | 输入 1 | 自由运行时钟，默认 50 MHz |
| resetn | 输入 1 | 低有效复位，包装层实现异步复位、两级同步解除 |
| enable | 输入 1 | 与 clk 同步，1 启动；0 清除状态、释放 outputs_active |
| uart_rx | 输入 1 | 来自模块 UART TX |
| uart_tx | 输出 1 | 接模块 UART RX 的数据值；通过 outputs_active 控制 I/O 输出使能 |
| bt_enable | 输出 1 | 接模块 BT_DIS 的值，低复位、高使能；需同样控制 I/O 输出使能 |
| outputs_active | 输出 1 | UART TX、BT_DIS 及本例 WL_DIS 的共同输出使能 |
| initialized | 输出 1 | 补丁及广播初始化完成 |
| connected / subscribed | 输出各 1 | 已连接 / CCCD 已订阅 |
| failed | 输出 1 | 初始化或传输失败 |
| debug | 输出 768 | 24 个 32 位状态字，可不连接；未连接时综合会裁剪部分计数逻辑 |

停止时 `outputs_active=0`，它本身不是三态。板级顶层负责输出 OE：`pin = outputs_active ? value : 1'bz`。示例在会话期间将 WL_DIS 驱动为低，BT_HOST 由板级保持输入；不要把这个逻辑直接当作其他模组的接法。

| 参数 | 默认值 | 约束 |
| --- | --- | --- |
| CLK_HZ | 50000000 | 必须与实际 clk 一致，建议整数 kHz；其他时钟频率需重新仿真/综合与时序验证 |
| DISABLE_MS | 200 | BT_DIS 低电平时间 |
| STARTUP_MS | 2000 | BT_DIS 高后等待时间 |
| SESSION_MS | 180000 | 最大会话时间，到期释放输出；不是 0 表示无限运行 |
| NOTIFY_MS | 500 | 通知提交周期，受控制器发送额度限制 |
| PATCH_FILE | rtl8723ds_patch.mem | 必须与附带 ROM 对应 |

包装层固定 `BAUD=115200`、`PATCH_BYTES=30147`，因为 HCI 波特率命令及补丁配置固定为 115200。修改核心 BAUD 参数不能单独完成波特率迁移。流控关闭，不使用 RTS/CTS。

从 `enable=1` 开始先低使能 200 ms，再高使能等待 2000 ms，然后 H5 建链、型号/ROM 检查、120 个补丁片下载、HCI/广播初始化。保持 resetn=0 或 enable=0 时所有状态清零。失败或会话到期后，先 enable=0 再 enable=1 重启。停止只释放 FPGA 输出，不发送关闭广播/断开命令，不证明模块射频关闭。

## 当前 BLE 功能

固定广播名 `RTL8723-BLE`，服务 FFF0、可读/通知特征 FFF1、CCCD，ATT MTU=23。支持服务、特征、描述符发现、读取、订阅和错误响应。ACL 采用单信用保守发送及两个 ATT 回复队列槽。

订阅后默认每 500 ms 提交 20 字节测试通知：`BTST`、小端 uint32 序号、小端 uint32 GATT 运行毫秒数、`00 01 02 03 04 05`、前 18 字节的 CRC16-CCITT（初值 FFFF，小端保存）。**当前没有任意用户数据输入端口**；定制业务 payload 需扩展 bt_gatt 的通知生成逻辑及相应测试。

不包含配对/加密、ATT 长包、ACL 分片、通用经典蓝牙栈，也没有实现 Wi-Fi 驱动。H5 数据 CRC 关闭，应用通知单独带 CRC。

## 可移植性与综合

`ASYNC_REG` 和 `rom_style` 为综合属性，其他 FPGA 工具可能忽略；移植时确认两级 UART 同步器保留，并确认 `$readmemh` 推断上电初始化 ROM。可改用目标器件 ROM IP，但须保留同步读延迟及内容。时序约束只对 UART 外部输入到第一级同步器作 false-path，保留第一级到第二级的时序。引脚、电平标准、IO BANK、时钟/PLL和模块电源由板级工程配置，本包不含硬编码球号。

`constraints/vivado_example.xdc` 是 50 MHz 板级示例约束，无球号，其他频率/顶层需调整。默认资源数字来自原实板已布线设计，不是本包的独立综合结果：

| 范围（XC7Z020） | LUT | FF | BRAM36 等效 | DSP |
| --- | --- | --- | --- | --- |
| 蓝牙核心，含状态计数器 | 7925（14.90%） | 12525（11.77%） | 8（5.71%） | 0 |
| 原完整测试工程，含 VIO/ILA/debug hub | 11714（22.02%） | 19048（17.90%） | 10.5（7.50%） | 0 |

核心的 8 个 BRAM36 用于 32 KiB 补丁 ROM，内部包缓冲当前使用 FF/LUT。本包参数改变、debug 悬空及工具优化会改变综合资源。详细报告在 `reports/`。

## 验证和来源

`validation/` 保存原板测试：Windows 实收 40 包、800 字节，序号 0–39，内容与独立 CRC 全部正确；两个 ARM 核停止。该实板测试使用原板级包装层。导出包装层另由包内完整 UART 控制器模型验证补丁、初始化、GATT 和通知，并验证错误 ROM 拒绝。仿真按时间比例加速，实际硬件参数仍是 50 MHz/115200。

在包根目录运行：

```powershell
python scripts/verify_package.py
.\scripts\simulate.ps1 -ToolsRoot 'C:\AMDDesignTools\2026.1'
```

测试脚本运行 H5、GATT、包装层整机、错误 ROM 四项，以及板级示例编译/展开。无需原 workspace 或硬件。输出日志在 `sim_output/`。Vivado/XSim 仅用于示例验证流程，RTL 可交给其他兼容工具。

当前导出包装层验证 **4/4 PASS**，板级示例编译及展开通过。已保存的结果、对应源文件 SHA256 和四项日志见 `validation/portable/`。

`firmware/` 原始二进制供独立仿真重建补丁，不需加入综合。固件来源为 Armbian firmware 的 rtl_bt 目录，哈希、ROM 选择和有效配置见 `firmware_manifest.json`。`NOTICE.md` 记录来源；没有为第三方固件授予新许可。

`MANIFEST.json` 记录每个导出文件的长度和 SHA256，`scripts/verify_package.py` 校验完整性。`rtl/` 核心 6 个文件与原工程相同，仅顶层包装层新增。原工程的 bitstream/ELF、PS/VIO/ILA及 J25 球号不在必需源文件中。
