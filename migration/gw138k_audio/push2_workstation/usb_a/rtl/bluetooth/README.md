# RTL8723DS BLE → GW5AST-138K

这是队友的通用 Verilog 驱动在 **GW5AST-LV138PG484AC2/I1、NEO Dock-138K 31005** 上的迁移。原版 0x86 与缓存优化版 0x91 的独立工程均已完成 Gowin 综合、布局布线和位流生成，50 MHz 时序通过；完整工作站集成 0x90 已布通，但存在 BLE/DDR 时序退化，仍是实验候选；138K 上的模组接线、扫描、连接和通知实测待完成。完整验证记录见 `../../reports/RTL8723DS_BLE_MIGRATION_20261007.md`。

原始包逐字节冻结在 `../../vendor/rtl8723ds_ble/`，`inputs.json` 和原始 `MANIFEST.json` 同时校验来源。原包的 `validation/`、`reports/` 是队友原平台的参考证据，不能当作 138K 验收。厂商固件来源与权利说明保留在 `NOTICE.md`；本迁移没有新增许可证。

## 驱动如何工作

```mermaid
flowchart LR
    P[模块复位与启动等待] --> U[115200 UART 8E1]
    U <--> H[H5 / SLIP / ACK与重试]
    H <--> I[HCI ROM版本检查与补丁下载]
    I --> A[LE 广播初始化]
    H <--> G[ATT / GATT FFF0与FFF1]
    G --> N[20字节 BTST 测试通知]
```

核心全部运行在 50 MHz 时钟域，无 CPU 软件、Xilinx PS、VIO、ILA 或 Xilinx I/O 原语。启动时 BT_DIS 低 200 ms、高后等待 2000 ms；随后 H5 建链，要求 RTL8723DS **ROM version=2**，下载 30147 字节补丁及配置（120 片），完成 HCI 和广播初始化。固件及 HCI 波特率设置固定为 115200、8E1，RTS/CTS 流控关闭。

初始化命令顺序为读取本地版本/ROM/地址（`1001`、`FC6D`、`1009`）、设置 UART（`FC17`）、分片下载补丁（`FC20`）、HCI Reset（`0C03`），随后设置 LE Host、发送额度、事件掩码、广播参数/数据和广播使能。初始化器用单步命令与超时控制；下载每片都核对控制器状态与片号。

广播名称 `RTL8723-BLE`，服务 FFF0，可读/通知特征 FFF1，CCCD 为订阅入口，ATT MTU=23；FFF1 的值句柄为 7，CCCD 句柄为 8。订阅后每 500 ms 提交一次 20 字节测试通知：`BTST`、小端序号、小端运行毫秒数、`00 01 02 03 04 05`、CRC16-CCITT。队友版本没有任意业务数据输入、特征写入业务接口、BLE MIDI、蓝牙音频、配对加密或 Wi-Fi 功能；本次保留这些功能边界。

会话保持原版 180 秒上限，到期或失败后释放三根输出。按 BUTTON1 重新启动；工作站集成版的 BUTTON1 同时复位原工作站，不能当作蓝牙专用重启键。`SESSION_MS=0` 会立即到期，不能表示无限运行。停止释放 FPGA 驱动，不发送断开/关闭广播命令。需要长时间常驻或业务数据收发时，应单独修改协议和测试。

## 138K 接线

板子现有无线串口桥是另一类器件，不能替代 RTL8723DS。本工程需要外接队友使用的、兼容 ROM-v2 补丁的 RTL8723DS 模组。下表来自本地 **Tang_Mega_NEO_Dock-138K_31005_Schematics.pdf**，J8 为 PMOD1。注意这个连接器的电源/地位于 1—4 脚，按 31005 原理图核对方向。

| 模组端信号 | 138K 接口 | FPGA 球号 | FPGA 方向 |
|---|---|---|---|
| UART TX | J8 pin 7 / PMOD1_IO4 | AA20 | 输入 |
| UART RX | J8 pin 8 / PMOD1_IO5 | AA21 | 输出，停止时高阻 |
| BT_DIS，低复位、高使能 | J8 pin 5 / PMOD1_IO6 | AA19 | 输出，停止时高阻 |
| WL_DIS，会话中驱动低 | J8 pin 6 / PMOD1_IO7 | AB20 | 输出，停止时高阻 |
| GND | J8 pin 3 或 pin 4 | — | 共地 |
| 集成版 BLE 状态串口 TX | J8 pin 9 / PMOD1_IO2 | AB21 | 输出，115200 8N1 |

PMOD 所在 Bank4 的实际电压必须为 **3.3 V**（TP22 核对），模组 UART 电平与之匹配。模组电源按其载板规格供电，不能仅凭芯片名称决定供电电压或电流。PMOD1 同时接到 SDRAM1/DVP_CAM 扩展网络；使用 BLE 的几根线上不能再接其他驱动器。

`clk_50m=V22` 使用当前 138K 工作站同一 50 MHz 板级时钟，`button1_n=AB13`。独立蓝牙工程的状态串口使用 `U15`（现有 BL616 接收通道）；工作站集成版保留原 `U15` 诊断串口，另用 `AB21` 输出 BLE 状态。两类状态串口都为 **115200 8N1**，与模组 **8E1** UART 分开。BT_HOST/RTS/CTS 不由 FPGA 驱动，维持队友验证过的模组载板接法。

## 文件与构建

- `gw138k_ble_link.v`：Gowin 接入层，异步复位或停止时立即撤销输出使能，导出原版状态字。
- `gw138k_ble_board_top.v`：独立 138K 芯片顶层，三态只放在芯片 I/O 边界。
- `gw138k_ble_status_uart.v`：独立只读状态串口，每次锁存全部 24 个状态字，发送期间保持快照一致。
- `constraints/`：板级 CST 与 20 ns SDC。
- `../../tools/rtl8723ds_ble_sources.py`：冻结输入校验与 staging；在副本添加 `syn_romstyle="block_rom"`、同步器 `syn_preserve/syn_keep`，并按选项应用缓存适配，原始导出包保持不变。
- `../../tools/build_rtl8723ds_ble.py`：在全新 `usb_a/results/ble_*` 目录构建；不会编程硬件或更新 `LATEST_WORKSTATION.json`。

从仓库根目录运行：

```sh
python3 migration/gw138k_audio/push2_workstation/usb_a/tools/test_rtl8723ds_ble.py
python3 migration/gw138k_audio/push2_workstation/usb_a/tools/build_rtl8723ds_ble.py --prepare-only
python3 migration/gw138k_audio/push2_workstation/usb_a/tools/build_rtl8723ds_ble.py --synthesis-only
```

完整位流构建必须提供新的、全仓库未使用的八位 UserCode。`00000086` 已分配给本次独立候选，`00000087` 为未布通的集成尝试，`00000088` 用于算法 2 的集成重试，`00000089` 用于 compact HCI 集成候选，`00000090/91` 用于 HCI+H5 优化的集成/独立候选。以下示例使用另外两个值，执行时仍由脚本核对是否被其他构建占用：

```sh
python3 migration/gw138k_audio/push2_workstation/usb_a/tools/build_rtl8723ds_ble.py --full --user-code 00000094
```

工作站集成在已校验的当前 staging 工程上追加 BLE。当前 0x90 实验位流虽然已布通，clk50 Fmax 45.134/50 MHz、DDR UI Fmax 71.563/100 MHz，尚未通过集成时序验收；后续应先修复这些退化再替换当前工作站。默认从 `LATEST_WORKSTATION.json` 选择基线，也可显式传入 `--workstation-base /path/to/Prj1`；基线的父目录必须带有 `workstation_inputs.json`，构建前逐文件核对。新模块留在 50 MHz 域，并使用 J8 独立串口；原工程文件只允许顶层、工程文件、CST、SDC、构建 TCL 五处集成修改。

```sh
python3 migration/gw138k_audio/push2_workstation/usb_a/tools/build_rtl8723ds_ble.py --profile workstation --synthesis-only
python3 migration/gw138k_audio/push2_workstation/usb_a/tools/build_rtl8723ds_ble.py --profile workstation --full --user-code 00000095 --route-option 2
```

`--compact-hci` 可选项将 HCI 命令参数缓存改为单写口异步读 RAM，32 个命令参数逐周期准备，包头保留在 opcode/length 寄存器中；补丁片号与内容、HCI 命令、超时和 GATT 行为不变。原始导出包仍冻结，适配文件为 `adaptations/bt_hci_init.v`。独立综合相较原版减少 1184 LUT、2073 寄存器，BSRAM 仍为 16，完整控制器模型验证通过。此选项主要用于缓解完整工作站布局压力：

```sh
python3 migration/gw138k_audio/push2_workstation/usb_a/tools/test_rtl8723ds_ble.py --compact-hci
python3 migration/gw138k_audio/push2_workstation/usb_a/tools/build_rtl8723ds_ble.py \
  --profile workstation --compact-hci --full --route-option 2 --user-code 00000092
```

`--compact-h5` 将 H5 接收缓存的三个固定探测字节单独锁存，去掉缓存的常量地址读端口，使其推断为单动态读端口 SSRAM。H5 握手、ACK、重试、背压、帧格式保持原协议。与 `--compact-hci` 合用时，独立综合为 8152 LUT、4860 寄存器、140 RAM16、16 BSRAM，较原版少 3257 LUT、4329 寄存器；完整 8 项回归通过。

```sh
python3 migration/gw138k_audio/push2_workstation/usb_a/tools/test_rtl8723ds_ble.py --compact-hci --compact-h5
python3 migration/gw138k_audio/push2_workstation/usb_a/tools/build_rtl8723ds_ble.py \
  --profile workstation --compact-hci --compact-h5 --full --route-option 2 --user-code 00000093
```

Gowin 工具需有 `gw_sh`，仿真需有 Icarus Verilog 的 `iverilog/vvp`，打开状态串口时需 Python `pyserial`。离线状态/通知解析不需要串口或蓝牙设备。原始固件二进制随冻结包保存，完整系统测试从二进制独立重建期望补丁，并在物理 UART 边界逐字节核对，不只比较 DUT 内部 ROM。

## 状态读取与实体验收

独立工程原版 0x86 和联合优化版 0x91 的 `.fs` 位置、SHA256 和 UserCode 记录在迁移报告中。0x91 物理占用 8148 LUT、4860 寄存器、16 BSRAM，Fmax 61.075 MHz，setup/hold 违例 0。先确认供电、电平和接线，再进行单独 SRAM 测试。当前文件不代表已完成 138K 实体测试。

独立工程可从当前板子的 U15/BL616 接收端读取；集成版需将 USB-TTL 的 RX 接 J8 pin 9，并共地：

```sh
python3 migration/gw138k_audio/push2_workstation/usb_a/tools/read_ble_status.py \
  --port /dev/ttyUSB1 --seconds 15 --output /tmp/ble_status.json
```

状态帧为 `BLE1 ` + 24 个八位大写十六进制状态字 + LF；读取脚本检查格式、驱动标识、时钟和波特率，并解码连接、订阅、错误、补丁片数和通知计数。每约 1 秒输出一帧，状态串口只读，不发送控制命令。

蓝牙客户端收到的 FFF1 payload 可保存为每行一条 20 字节十六进制文本，也可使用原包 `{"packets":[{"raw":"..."}]}` JSON 格式。离线检查至少三条 CRC 正确、序号连续、时间递增的通知：

```sh
python3 migration/gw138k_audio/push2_workstation/usb_a/tools/verify_ble_payloads.py \
  --input /tmp/ble_notifications.txt --output /tmp/ble_payload_acceptance.json
```

这个工具不会打开蓝牙设备。原包的 40 条 PC 通知参考数据已通过工具校验，坏 CRC、重复/丢号和数量不足的输入均被拒绝；参考数据来自队友原平台，不能替代本板采集。

实体通过应同时具备：`initialized=true`、ROM version=2、补丁片数=120；手机/电脑实际扫描到 `RTL8723-BLE`；发现 FFF0/FFF1 并成功订阅；收到至少三条序号递增且 CRC 正确的 `BTST` 通知；失败/停止/重启的输出状态正常。完整工作站集成还需重新验证 Push、音频、TF、HDMI 和模型状态，不能由蓝牙独立测试替代。
