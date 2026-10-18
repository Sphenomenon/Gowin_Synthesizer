# USB1 12 Mbps CDC 回环例程

面向 `GW5A-LV25MG121NC1/I0` 的独立 USB Full-Speed CDC 例程，FPGA 直接通过 USB1 的 D+/D− 引脚收发，板载 50 MHz 时钟经 PLL 生成协议核使用的 60 MHz。主机识别为 `FB9A:FB9A / FPGA-USB-Serial`，提供一个原样字节回环串口。

本目录从 `prj/usb1_device` 的实板成功版本整理，包含本地 RTL、PLL、约束、固定上游源码、仿真、GAO、主机工具和已验证位流；原工程保留。2026-10-16，用户补上 D+ 上拉后，原 GAO 镜像已在 Mac 完成 **12 Mbps 枚举及 1848 字节真实二进制回环**。本次整理没有重新下载实板；来源和文件哈希见 [PACKAGED_FROM.json](PACKAGED_FROM.json)。

## 目录

| 路径 | 内容 |
|---|---|
| `rtl/` | 板级顶层、地址过滤桥接、1024 字节回环 FIFO 接口 |
| `clock/` | 50→60 MHz PLL、LOCK 与复位同步、时钟约束 |
| `constraints/` | 本板 USB1、时钟和 LED 引脚 |
| `vendor/fpga_usb_device/` | 固定上游源码、逐文件 SHA256 和 LGPL-2.1 许可 |
| `generate_core.py`、`generated/` | 校验上游并生成带地址过滤的派生核心 |
| `sim/`、`run_sim.sh` | 从物理 D+/D− 端口收发的独立 USB host BFM |
| `debug/` | 50 MHz GAO 观察器、定义、采集与解码工具 |
| `tools/` | 本地安全构建及主机检查支持工具 |
| `builds/20261016_011545_836351/` | 已实板验证的原 GAO 构建产物 |
| `reports/verified_build.json` | 原实板镜像在本目录下的可移植清单 |
| `reports/hardware_20261016/` | 硬件更改后下载、枚举、回环及 GAO 原始证据 |

## 引脚与上拉

| 信号 | FPGA 球号 | 行为 |
|---|---|---|
| `clk_50mhz` | E2 | 50 MHz 输入，PLL 生成 60 MHz |
| `usb1_dp` | L6 | USB1 D+，三态收发 |
| `usb1_dm` | K6 | USB1 D−，三态收发 |
| `led_ready` | E8 | 高有效，PLL 锁定且复位释放后约 0.894 Hz 心跳 |
| `led_done` | D7 | 高有效，收到 CDC OUT 字节后点亮，总线复位清除 |

相关 BANK 使用 3.3 V，USB 引脚为 LVCMOS33，FPGA 内部弱上拉禁用。Full-Speed 设备需要 D+ 经 **1.5 kΩ 接到 3.3 V**。本板用户已确认“补上上拉了”，实际阻值和具体接法未另行报告；实测成功不作为电阻测量记录。

顶层的 `usb_attach_request` 只是内部意图，没有引脚控制外部上拉，也没有软件可控断开功能。协议核在时钟和复位释放后等待约 2 秒再工作，主机检查前需留出启动时间。更换 SRAM 镜像时，Mac 可能保留先前的 MIDI 描述符；本板只靠 USB1 供电时拔线还会使 SRAM 镜像丢失并重启 Flash 内的 MIDI 程序，故重新插线后应先确认运行镜像，再判断枚举结果。

## 构建与仿真

以下命令从本目录执行：

```sh
cd example/USB1_FS
sh build.sh
sh run_sim.sh
python3 clock/sim/run.py
```

`sh build.sh` 默认生成 GAO 镜像；`sh build.sh --normal` 生成不带 GAO 的普通镜像。构建默认使用 macOS `/Applications/GowinIDE.app/Contents/Resources/Gowin_EDA/IDE`，可通过 `GW25K_IDE_DIR` 指定安装位置。入口校验上游哈希，在全新 ASCII 临时目录准备派生源码，使用全局锁并将综合、仅网表 PnR 分进程运行。GAO 使用综合后插入流程，时钟约束合并为单一 SDC，保留调试时为规避 Gowin 崩溃采用的流程。

成功构建写入独立 `builds/<时间戳>/`、`reports/build_<时间戳>.json` 和 `reports/last_build.json`；失败保留之前的成功产物。原实板镜像固定由 `reports/verified_build.json` 指向，新构建不能自动继承原镜像的实板验证结论。

整理后已分别完成 [GAO 构建](reports/build_20261016_214351_988386.json)和[普通构建](reports/build_20261016_214420_844215.json)，两者 setup/hold 违规端点均为 0，并通过下载前离线校验。物理总线 BFM、官方 PLLA 模型仿真及主机工具 16 项离线检查均通过，汇总见 [packaging_verification.json](reports/packaging_verification.json)。这些是本目录的软件整理验证，两个新镜像均未下载实板。

当前 `reports/last_build.json` 指向最后完成的普通镜像。采集新 GAO 构建时应显式指定 `reports/build_20261016_214351_988386.json`，或重新运行默认 `sh build.sh` 并使用其新清单。`reports/hardware_20261016/` 的原始报告保留历史绝对路径，当前操作使用本例可移植清单。

仿真需要 `python3`、Icarus Verilog（`iverilog`、`vvp`）。host BFM 独立实现 NRZI、位填充、CRC5/CRC16，直接连接真实核心的 D+/D− 三态端口，验证描述符、控制传输、地址切换的 ACK 提交时机、外地址隔离、0…255 二进制回环，以及 FIFO 溢出与总线复位清除。仿真只加速内部启动等待，建模外部 D+ 上拉，不代替实际 PLL 和模拟电气检查。

PLL 仿真另用安装的 Gowin `PLLA` 模型检查启动复位、三拍释放、600 个输出周期、占空比，以及失锁后的异步复位和重锁释放；模型验证不能代替物理频率测量。

## SRAM 下载

先离线核验自带的实板成功镜像，再执行下载：

```sh
python3 program_sram.py --manifest reports/verified_build.json --check-only
python3 program_sram.py --manifest reports/verified_build.json
```

使用本目录刚构建成功的镜像时，将清单换为 `reports/last_build.json`。下载工具核对 SHA256、器件、安全位、GAO 身份和 setup/hold 时序，再用 Gowin `programmer_cli` 执行 SRAM Program+Verify。当前适配 FT2232HL cable 1、channel 0、15 MHz，核对 UserCode 与 Status；只写 SRAM，断电后需重新加载。

原实板镜像 UserCode=`4322`、GAO ID=`AA53`、Status=`70022020`，setup/hold 违规端点均为 0。位流 SHA256 为：

```text
bed38e61a1c0b21c738f5ad56d43ea2dc2abe0b1a53ac236fdde674ad4cdc253
```

## 主机枚举与真实回环

USB1 接 Mac、目标镜像已加载并等待启动后，检查唯一目标、CDC 接口、所属串口及 12 Mbps 链路速度：

```sh
python3 check_usb.py --output reports/host_enumeration.json
```

若确认 SRAM 已加载 USB1 镜像，但系统仍保留 Flash 程序的 `Primer 25K MIDI / 1209:0001`，可在保持供电时请求该设备重新枚举。先检查实际 USB location，再运行；以下 `0x01113200` 仅为原测试位置，环境变化时必须替换：

```sh
sh tools/reenumerate_usb.sh --location 0x01113200 --inspect
sh tools/reenumerate_usb.sh --location 0x01113200 --reenumerate
```

工具只允许指定位置上唯一匹配上述旧 MIDI 身份的设备，检查步骤不会修改设备。实际重枚举不切换 USB 供电；成功后再次运行 `check_usb.py` 核对新的 CDC 身份。没有旧 MIDI 匹配时无需运行该步骤。

真实回环需当前 Python 环境安装 `pyserial`：

```sh
python3 check_usb.py --loopback --timeout 3 --rounds 8 --output reports/host_loopback.json
```

工具默认按 `1,7,31,32,33,63,64` 字节各 8 轮，合计 56 块、1848 字节；每块发完并读回后才发下一块。核的 OUT 端点 `0x01` 最大包 32 字节，IN 端点 `0x81` 描述符最大包 64 字节、实际每包最多 32 字节。上游 OUT 接口没有应用层逐字节背压，连续写入且不读取可能使 1024 字节 FIFO 溢出。报告请使用新文件名，保留此前证据。

2026-10-16 的原实板测试确认 `UsbLinkSpeed=12000000`、`Device Speed=1`、configuration=1，CDC control/data 接口类为 2/10。发送、接收各 1848 字节且逐字节一致，无额外数据；payload SHA256=`45366e8626cf4b69da2713d8647ba35567a42bebb583486a7cd7b17387ed033b`。综合证据见 [usb1_postchange_20261016.json](reports/hardware_20261016/usb1_postchange_20261016.json)。12 Mbps 是链路速率，115200 是 CDC line coding 参数，当前结果未测持续吞吐率或长期可靠性。

## GAO 状态采集

保持下载器连接，使用与当前 SRAM 镜像一致的清单：

```sh
python3 debug/capture_status.py --manifest reports/verified_build.json
python3 debug/decode_status.py <生成的_core0_window0.csv> --output reports/status_decoded.json
```

只有实际扫描得到 FTDI location 后才添加 `--location <位置>`，不要套用其他工程的历史位置。GAO 采集只读取已加载镜像，本地清单不能证明 FPGA 当前运行的就是它；采集应与下载记录及工具的 GAO ID 检查配合。

成功回环后的 128 点均为 FS-J，PLL、60 MHz 复位释放、USB 总线复位释放和 received sticky 为 1，overflow 与 SE1 long sticky 为 0。SE0 long sticky=1 是已经发生的总线复位历史，当前连续 SE0 计数为 0。该 GAO 捕获线态和 sticky 标志，**不含字节计数**；1848 字节结论来自主机逐字节回环。完整布局与构建说明见 [debug/GAO.md](debug/GAO.md)。

## 上游与实现范围

固定上游为 [WangXuan95/FPGA-USB-Device](https://github.com/WangXuan95/FPGA-USB-Device/tree/ebf0696f0b1dc604a4ed8eedee4c3eae1643e66f)，提交 `ebf0696f0b1dc604a4ed8eedee4c3eae1643e66f`。本地生成器在不改 vendor 的前提下加入 token 地址过滤，SET_ADDRESS 在状态 IN 的 host ACK 后提交；总线复位恢复地址 0，新 SETUP 取消待提交地址。派生源码保留上游 LGPL-2.1 许可与来源。

现有实现保留上游其余 transaction 与描述符行为，包括 CDC 配置缺少 Header / Call Management functional descriptor、类 IN 请求默认返回零，以及无显式 SET_CONFIGURATION 状态。当前 Mac 已完成列出的有限枚举和回环，结果不表示 USB 合规认证、所有主机兼容性或异常重传覆盖。
