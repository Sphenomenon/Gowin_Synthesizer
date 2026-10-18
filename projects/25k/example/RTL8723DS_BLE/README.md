# RTL8723DS BLE 例程

面向 `GW5A-LV25MG121NC1/I0` 与本板 RTL8723DS 模组的独立 BLE 例程，通过 **115200 / 8E1 UART、H5/HCI** 初始化 ROM-v2 控制器、下载固件补丁并提供 GATT 测试服务。广播名为 `RTL8723-BLE`，服务为 `FFF0`，特征为 `FFF1`，支持读取和通知。

本目录从 `prj/ble_bringup` 整理，源码、固件 ROM、约束、构建与测试工具均在本目录内，原工程保留。2026-10-16 原 GAO 镜像已完成本板广播、连接、20 字节读取及 3 个 CRC 有效通知的实测；本目录默认采用**不含 GAO 的普通构建**。整理过程不包含重新下载或新的无线实测，来源和镜像差异见 [PACKAGED_FROM.json](PACKAGED_FROM.json)。

## 文件

| 路径 | 内容 |
|---|---|
| `rtl/` | 板级顶层、SW1 去抖与 USB1 被动监测 |
| `vendor/rtl8723ds_ble/` | 原始驱动、固件、ROM、MANIFEST 和原包测试，保持原样 |
| `prepare_adapted.py`、`prepare_sources.tcl` | 生成 Gowin 存储适配副本与构建用 ROM 路径 |
| `constraints/` | 本板引脚与 50 MHz 时序约束 |
| `build.sh`、`build.tcl`、`tools/gowin_build.py` | 本地安全构建入口 |
| `run_sim.sh`、`tests/` | 原始和存储适配版本的仿真 |
| `program_sram.py` | 普通构建清单检查及 SRAM Program+Verify |
| `tools/ble_check.py`、`tools/requirements-ble.txt` | 电脑 BLE 扫描、读取和通知校验 |
| `reports/hardware_20261016/` | 原实板验证、GAO CSV 与时序核查记录 |
| `debug/` | 历史 GAO CSV 离线解码工具与状态说明 |
| `archive/gao_20261016/` | 原 GAO 镜像、约束和构建脚本历史副本，不作为默认下载入口 |

## 引脚与硬件

| 信号 | FPGA 球号 | 连接和方向 |
|---|---|---|
| `clk_50mhz` | E2 | 核心板 50 MHz 系统时钟输入 |
| `restart_n` | L10 | SW1_KEY，低有效，板上已有上拉 |
| `module_uart_tx` | J8 | U3.42 UART_OUT / BT_TX，模组 TX → FPGA RX |
| `module_uart_rx` | K9 | U3.43 UART_IN / BT_RX，FPGA TX → 模组 RX |
| `module_bt_dis_n` | K8 | U3.34 BT_DIS#，低复位、高运行，板上 R20=10K 上拉 |
| `led_ready` / `led_done` | E8 / D7 | READY / DONE，高电平点亮，配置专用脚复用为 GPIO |
| `usb1_dp` / `usb1_dm` | L6 / K6 | USB1 D+ / D−，仅输入监测，显式关闭内部上下拉 |

I/O 按当前实板采用 LVCMOS33，对应 BANK 供电为 3.3 V。模组需有正常供电、内部时钟及天线，ROM version 必须为 **2**。本例没有驱动 L9 / BT_HOST_WAKE_DEV，也不主动输出 USB1、USB3300 或 LCD 信号。USB1 监测仅记录线态与活动，不发送 USB 数据、不提供枚举上拉，不能据此判断 USB 枚举成功。

Wi-Fi 当前没有可用的 FPGA 数据通路：原理图将 U3.12 WL_DIS# 及 U3.14～19 SDIO 标为 NC。现有 BLE UART 包不提供 Wi-Fi 数据业务；Wi-Fi 需要实际 SDIO/使能连线和独立驱动。

## 启动、按键与 LED

配置后保持约 1024 个系统时钟 POR，随后自动开始一次 **180 秒会话**。BT_DIS# 先拉低 200 ms，再拉高等待 2000 ms；随后执行 H5 握手、HCI 型号和 ROM 检查、**30,147 字节 / 120 分片**补丁下载及广播配置。UART 是 **8E1**，不能作为 8N1 AT 串口使用。

| 状态 | READY | DONE |
|---|---|---|
| 初始化中 | 约 1 Hz 心跳 | 灭 |
| 初始化完成、可扫描 | 约 1 Hz 心跳 | 常亮 |
| 已连接、未订阅 | 约 1 Hz 心跳 | 约 1 Hz 闪烁 |
| 已订阅 | 约 1 Hz 心跳 | 约 3.9 Hz 快闪 |
| 初始化或传输失败 | 约 3.9 Hz 快闪 | 灭 |
| 会话正常到期 | 常亮 | 灭 |
| SW1 按住并完成去抖 | 灭 | 灭 |

会话计时包含启动和补丁下载，失败后不会自动反复复位模组。按住 SW1 至少约 **20 ms**，再释放至少约 **20 ms**，即可重开完整会话。故障闪灯使用同一会话毫秒计数，到 180 秒后会冻结。原图 READY/DONE 串联电阻为 10K，实际亮度可能较低。

复位、失败及到期时，FPGA 的 UART_TX 与 BT_DIS# 输出置为高阻。R20 仍将 BT_DIS# 上拉，**高阻不等于关闭射频**；停止时未发送关闭广播或断连指令。原包在模组自行重启或 H5 重新握手后不会自动重新执行完整固件/HCI 初始化，此时应使用 SW1 重开会话；单独看到 H5 link_up 不能证明初始化完成。

## 独立构建与仿真

从仓库根目录进入本目录，后续命令均在本目录执行：

```sh
cd example/RTL8723DS_BLE
sh build.sh
sh run_sim.sh
```

构建需要 Python 3 和 macOS Gowin EDA，默认 IDE 路径为 `/Applications/GowinIDE.app/Contents/Resources/Gowin_EDA/IDE`，可用 `GW25K_IDE_DIR` 指定其他路径。入口先按 vendor MANIFEST 校验完整原包，再在全新 ASCII 临时目录中构建；综合和仅网表 PnR 分进程运行，并使用全局锁避免并行 Gowin 构建。此流程保留了调试时规避 Gowin 崩溃的措施。

`prepare_adapted.py` 根据已核验的原文件生成两个存储适配副本：H5 的 280 字节 pending payload RAM 改为无数组复位的同步读写 block RAM；固定 MTU=23 的 GATT 保留两个回复槽和一个活动槽，将各槽收紧到 32 字节，最大实际出包仍为 31 字节。协议状态机、槽数及完整补丁不变。`prepare_sources.tcl` 为 Gowin `$readmemh` 暂存未改动的 ROM 到 ASCII 路径，仅在生成顶层中替换 `PATCH_FILE`。每次构建重新生成，vendor 文件不被修改。

成功产物保存在独立 `builds/<时间戳>/`，清单为 `reports/build_<时间戳>.json` 和 `reports/last_build.json`，失败保留此前成功产物。普通构建保留 JTAG、复用 READY/DONE 为 GPIO、关闭读回保护，并检查 setup / hold 均无违规。

整理后的普通例程已实际重新构建通过，原始清单为 [build_20261016_212742_017482.json](reports/build_20261016_212742_017482.json)，50 MHz 约束下 Fmax=54.486 MHz、setup / hold 违规端点均为 0，且已通过下载前离线检查。可移植清单为 [ready_build.json](reports/ready_build.json)，整理验证记录见 [packaging_verification.json](reports/packaging_verification.json)。它们代表构建与离线检查通过，尚未进行一次新的实板验证。新镜像 UserCode=`03D1`，SHA256 为：

```text
4a83570933221b472cf8eecae6818cea1919ab93db555f2cf18833ef6ff6c117
```

仿真需要 PATH 中可用的 Icarus Verilog（`iverilog`、`vvp`）。`run_sim.sh` 先完成 MANIFEST 40/40 校验，再分别运行原始版本和存储适配版本的 5 项测试：

- 板级 POR、BT_DIS# 时序、输出使能、SW1 去抖、会话到期和重启，以及 USB1 被动 SE0 监测。
- H5 握手、全双工 8E1、ACK、重复包、重传、SLIP、长度限制、背压、校验和奇偶错误。
- GATT 发现、ATT 错误、CCCD、控制器信用、回复队列、通知序号与 CRC。
- 整机模型逐字节核对 30,147 字节和 120 个补丁分片，完成 HCI、ATT、CCCD 及 3 个有效通知。
- 错误 ROM 在补丁下载前被拒绝。

本次整理已通过原始版本 5/5、存储适配版本 5/5，MANIFEST 40/40 校验通过。结果写入 [simulation_results.json](reports/simulation_results.json)、[adapted_simulation_results.json](reports/adapted_simulation_results.json) 及同目录日志。

## SRAM 下载

先检查自带普通构建，再按需下载：

```sh
python3 program_sram.py --manifest reports/ready_build.json --check-only
python3 program_sram.py --manifest reports/ready_build.json
```

使用刚编译成功的产物时，将清单换为 `reports/last_build.json`。脚本将位流限制在本目录的 `builds/`，核验 SHA256、器件、安全位和 setup / hold 违规数；明确拒绝 GAO 镜像。下载使用 Gowin `programmer_cli`，适配 FT2232HL cable 1、channel 0、15 MHz，执行 **SRAM Program+Verify** 并核对 UserCode / Status。只写 SRAM，断电后需重新加载。

普通构建没有 GAO，LED 和真实 BLE 收发用于运行检查。历史 GAO 镜像存在未签核的跨时钟 hold 违例，作为调试证据归档，不通过本下载入口加载，详见 [archive/gao_20261016/README.md](archive/gao_20261016/README.md)。

## 手机或电脑检查

手机可使用 nRF Connect：等待 DONE 常亮后扫描 `RTL8723-BLE`，连接并发现 `FFF0` / `FFF1`；对 FFF1 执行 Read，随后订阅通知（CCCD=`01 00`）。应读到 20 字节数据，每约 500 ms 收到一包通知，此时 DONE 快闪。若已过 180 秒，先用 SW1 重开会话。

电脑自动检查需要系统蓝牙及相应权限。可在本目录创建环境并安装固定依赖：

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r tools/requirements-ble.txt
.venv/bin/python tools/ble_check.py --output reports/ble_hardware_new.json
```

依赖固定为 `bleak==3.0.2`。工具按广播名称选择设备，连接后读取 FFF1，再订阅至少 3 个通知，检查数据内容、CRC 和序号递增。输出使用新文件名以保留此前证据；执行检查时应确保附近目标名称唯一。本次整理没有执行新的扫描或连接。

| 字节 | 测试内容 |
|---|---|
| 0～3 | ASCII `BTST`，即 `42 54 53 54` |
| 4～7 | uint32 小端通知序号 |
| 8～11 | uint32 小端毫秒计数 |
| 12～17 | `00 01 02 03 04 05` |
| 18～19 | 前 18 字节 CRC16-CCITT，初值 FFFF，小端 |

## 已验证记录与来源

2026-10-16 的原实板报告 [ble_hardware_20261016.json](reports/hardware_20261016/ble_hardware_20261016.json) 记录：扫描和连接成功、FFF1 读取 20 字节有效、通知序号 0 / 1 / 2 均有效，毫秒计数 18522 / 19022 / 19522，间隔均为 500 ms。对应原 GAO 镜像 SRAM Program+Verify 成功，UserCode=`EEDB`、Status=`70022020`。这些是原镜像证据，不将其当作新普通构建的实板验证。

历史 GAO 的 128 个样本均显示 initialized=1、connected=1、subscribed=0、failed=0、ROM=2、补丁片数=120。单次快照仅反映采样时刻；GAO 内部跨独立 JTAG 时钟仍有 -0.606 ns、1 个 hold 违规端点，未添加时序例外，未宣称其 CDC 签核通过。离线解码方法及完整状态表见 [debug/README.md](debug/README.md)。

原包 UART/H5/HCI/ATT/GATT 源码未附加新的开源许可证；Realtek 控制器补丁与配置是第三方厂商二进制。来源、哈希和许可说明保留在 [NOTICE.md](vendor/rtl8723ds_ble/NOTICE.md)、[firmware_manifest.json](vendor/rtl8723ds_ble/firmware_manifest.json) 与 [MANIFEST.json](vendor/rtl8723ds_ble/MANIFEST.json)。
