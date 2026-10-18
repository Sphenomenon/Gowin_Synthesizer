# USB3300 480 Mbps CDC 回环例程

面向 `GW5A-LV25MG121NC1/I0` 与 USB3300 的独立 High Speed USB CDC 例程。USB3300 负责 USB 物理层，FPGA 通过 60 MHz、8 位 ULPI 实现高速枚举及二进制数据回环。主机识别为 `FB9A:FB9B / GW25K-USB-HS`，Bulk OUT/IN 端点为 `0x01 / 0x82`，最大包为 512 字节。

本目录从已实板验证的 `prj/usb2_device` 高速项目整理，包含本地源码、约束、构建工具、仿真、GAO、主机测试和已验证位流；原项目继续保留。来源、源码哈希及位流哈希见 [PACKAGED_FROM.json](PACKAGED_FROM.json)。

## 目录

| 路径 | 内容 |
|---|---|
| `hs/` | ULPI 启动、CDC 协议核、描述符、2048 字节回环 FIFO 及本地修改说明 |
| `vendor/ultraembedded_usb_hs/` | 固定版本的原始上游源码、哈希和许可证 |
| `constraints/` | 本板引脚及 50/60 MHz 时序约束 |
| `debug/` | GAO 定义、采集和解码工具 |
| `sim/`、`run_hs_*_sim.sh` | 启动、控制传输与 FIFO 仿真 |
| `tools/` | 本地安全构建入口及 macOS 主机检查工具 |
| `builds/20261016_185336_363191/` | 已实板验证的原始构建产物 |
| `reports/verified_build.json` | 上述已验证构建的可移植清单 |
| `reports/hardware_20261016/` | 2026-10-16 的原始实板证据 |

## 构建

以下命令从本目录执行：

```sh
cd example/USB3300_HS
sh build.sh
```

构建使用 macOS 上的 Gowin EDA，默认 IDE 路径为 `/Applications/GowinIDE.app/Contents/Resources/Gowin_EDA/IDE`，可通过 `GW25K_IDE_DIR` 指定。入口会校验上游源文件哈希，在 ASCII 临时目录中生成支持源码，分别启动综合和仅网表 PnR 进程，并使用全局锁阻止并行 Gowin 构建。这保留了调试中为规避 Gowin 崩溃采用的流程。

成功产物保存在独立的 `builds/<时间戳>/`，清单写入 `reports/build_<时间戳>.json` 和 `reports/last_build.json`；失败记录写入 `reports/last_failure.json`，保留之前成功产物。下载前还会检查 setup/hold 均无违规、器件型号、GAO 标识和 SHA256。

整理后的独立目录已实际重新构建通过，清单为 [build_20261016_211949_606050.json](reports/build_20261016_211949_606050.json)，并通过下载前 SHA256、GAO、setup/hold 离线校验。该新构建尚未下载到实板；原实板验证位流仍由 `reports/verified_build.json` 指向。

## 已验证位流与 SRAM 下载

先做离线检查，再下载自带的已验证位流：

```sh
python3 program_sram.py --manifest reports/verified_build.json --check-only
python3 program_sram.py --manifest reports/verified_build.json
```

若要使用本目录刚编译成功的产物，将两条命令的清单均换为 `reports/last_build.json`。下载工具使用 Gowin `programmer_cli`，当前适配 FT2232HL 的 cable 1、channel 0、15 MHz，执行 SRAM Program+Verify 并核对 UserCode 与 Status。只写 SRAM，断电后需重新加载。

已验证位流的 UserCode 为 `6E78`，GAO ID 为 `D2B0`，SHA256 为：

```text
edaa6d5df4630249dc126de835f70e0d31b174a61cc4862fa82c9a4d8dead557
```

## GAO 状态采集

保持下载器连接，使用与当前 SRAM 镜像一致的清单：

```sh
python3 debug/capture_status.py --manifest reports/verified_build.json --location 4273
python3 debug/decode_status.py <生成的采样.csv> --output reports/status_decoded.json
```

`4273` 是原验证环境的 FTDI location；环境变化时可省略或换成实际值。采集工具只读取已加载镜像，清单校验本地文件，不能代替对 FPGA 当前镜像身份的确认。

四页状态分别包含 PHY VID/PID、UTMI 模式与配置标志、启动阶段与 RX 低 16 位计数、回送消费低 16 位计数与溢出计数。正常配置后应见 `boot_stage=0x12`、`hs_state=5`、`boot_done/hs_active/configured=1`，`boot_error=0`。READY 灯表示 PHY 时钟存活，DONE 灯表示高速配置完成且无启动错误；数据回环由主机报告验证。

## 仿真与主机回环

数字仿真需要 Icarus Verilog：

```sh
sh run_hs_boot_sim.sh
sh run_hs_control_sim.sh
sh run_hs_echo_sim.sh
python3 -m unittest discover -s tools -p test_usb_check.py
```

三组仿真分别覆盖 PHY 初始化及异常退出、UTMI 包级控制传输与 512 字节回环、FIFO 顺序和背压行为。

本目录整理后已重新通过启动 23 场景、控制传输包级 BFM、FIFO 6000 有序字节及背压检查，以及主机工具的 16 项离线检查。

USB2 接电脑后，macOS 枚举检查会严格核验唯一目标、CDC 接口、所属串口和 480 Mbps 速度：

```sh
python3 check_usb.py --output reports/host_enumeration.json
```

真实串口回环还需要当前 Python 环境安装 `pyserial`：

```sh
python3 check_usb.py --loopback --timeout 3 --rounds 8 --output reports/host_loopback.json
```

包装工具默认按 `1,31,64,511,512,513,1024` 字节各 8 轮测试，共 56 块、21,248 字节，覆盖 512 字节包边界；打开串口前重新核验设备身份和链路速度。输出应使用新报告名，保留此前记录。

## 已验证结果

2026-10-16，原构建 `20261016_185336_363191` 已通过 SRAM Program+Verify；50/60 MHz/TCK 的 setup、hold 违规均为 0。Mac 报告 `UsbLinkSpeed=480000000`、`Device Speed=2`，CDC 配置成功；21,248 字节、56 块真实回环逐字节一致，无额外数据。回环后 GAO 的 RX/回送消费计数均为 21,248，overflow 为 0，启动及 UTMI 接收错误标志为 0。综合证据见 [usb2_hs_20261016.json](reports/hardware_20261016/usb2_hs_20261016.json)。

480 Mbps 是协商链路速率，尚未测持续吞吐率。整理目录本身没有新增一次实板测试。`reports/hardware_20261016/` 保留原报告中的历史路径；当前运行应使用本目录脚本及 `reports/verified_build.json` 或新构建清单。

## 引脚与时钟

约束针对当前实板，相关 FPGA BANK 使用 3.3 V、ULPI 为 LVCMOS33。

| 信号 | FPGA 球号 |
|---|---|
| 板载 50 MHz 时钟 | E2 |
| USB3300 CLKOUT，60 MHz 输入 | L4 |
| ULPI DATA[0:7] | L2、L1、K1、K2、J4、K4、G2、G1 |
| ULPI DIR / NXT / STP | J1 / J2 / L3 |
| READY / DONE 灯 | E8 / D7 |

L4 由 USB3300 提供时钟，FPGA 将它作为输入。USB2 的 D+/D− 接 USB3300；本例不使用 USB1。

## 上游许可与范围

上游版本及逐文件哈希见 [UPSTREAM.json](vendor/ultraembedded_usb_hs/UPSTREAM.json)，本地派生修改见 [PATCHES.md](hs/PATCHES.md)。UltraEmbedded CDC 核采用 [LGPL-2.1-or-later](vendor/ultraembedded_usb_hs/cdc/LICENSE)，UTMI→ULPI wrapper 采用 [GPL-2.0-or-later](vendor/ultraembedded_usb_hs/ulpi/LICENSE)，源码及原许可已完整保留，分发和派生使用应遵守各自许可。

本例完成了有限规模的干净链路 bring-up。上游对 IN ACK 丢失后的重传、RX CRC 回滚和 suspend/resume 尚不完善；现有结果未覆盖 USB 合规、长时间可靠性或持续吞吐率测试。
