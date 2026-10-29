# AE350 硬件、存储与软件开发参考

核对日期：2026-10-30。本文汇总 GW5AST-138 内置 Gowin RiscV_AE350_SOC 的官方规格、本仓库接入方式和后续开发入口。官方支持能力、源码实现、离线验证与实际板上运行状态分别说明；本文不改变构建配置、地址分配或部署记录。

## 1. 先区分硬核资源与工程配置

AE350 是 GW5AST-138 内置的硬核处理器子系统，官方架构图标注其处理器为 A25 Core。它与 FPGA fabric 内用于乘加计算的 DSP 模块是不同资源，也与 USB Host 的 VexRiscv 是不同处理器。

| 项目 | 官方能力 | 本仓库可确认的配置／边界 |
|---|---|---|
| 核心时钟 | 最高 800 MHz | 已核对的 CPU PLL 配置为核心 100 MHz、总线 50 MHz；不是 800 MHz 板测记录 |
| 局部存储 | ILM 64 KiB、DLM 64 KiB | 已核对的固件链接脚本未把程序／数据分配到这两个区域 |
| Cache | I-Cache、D-Cache 各 32 KiB | 官方寄存器复位值为关闭；不能仅因硬件支持就认定现有镜像已开启 |
| 外接／自定义存储 | 指令窗口 256 MiB、数据窗口 2 GiB | 已核对工程在 PL 侧实现 16 KiB 启动 ROM、8 KiB 工作 RAM，并桥接两个 DDR UI 页 |
| 运算 | 整数乘除、单／双精度浮点、DSP 扩展 | AE350 固件使用 `rv32im_zicsr/ilp32` 编译；没有据此启用浮点或专用 DSP 扩展 |
| 业务 | 可运行控制、DSP 和 NN 软件 | 当前 AE350 承担 UI／服务／启动自检；逐样本音频和识别计算主要在 RTL 中 |

因此，“现有工程只有 8 KiB 工作 RAM”不等于“AE350 硬核只有 8 KiB RAM”；“官方支持 800 MHz／DSP”也不等于“现有整机已经以该频率运行或完成软件卸载”。

## 2. 官方资料与适用版本

本目录集中保存汇总说明和 7 份已核对的官方原始 PDF：

```text
docs/ae350/
├── README.md          汇总说明与阅读入口
├── manuals/           官方原始 PDF，文件名与字节保持不变
├── manifest.json      文件大小、来源和 SHA256
└── NOTICE.md          来源与版权说明
```

原始资料复制自以下本机目录：

```text
E:\workspace\GW\Mega_138K\Doc\GW官方\AE350
```

上述路径仅记录采集来源，阅读资料无需访问该外部目录；本目录的 PDF 不是构建输入。另一目录 `Mega_138K_60K/07_Datasheet/CN/AE350/` 中保存了较早的 SUG 版本，并混有 AE250 手册；不可把 AE250 或旧版描述直接当作本次 AE350 规格。复查时按文档编号、版本和第 10 节哈希寻找同一份文件。

| 编号／版本 | 用途 | 本文主要依据的位置 |
|---|---|---|
| [MUG1031-1.3.1](manuals/MUG1031-1.3.1_Gowin_RiscV_AE350_SOC硬件设计用户手册.pdf) 硬件设计用户手册 | 架构、内核、存储、时钟、总线及硬件端口 | 正文第 3、5–12 页；PDF 第 11、13–20 页 |
| [MUG1029-1.3](manuals/MUG1029-1.3_Gowin_RiscV_AE350_SOC软件编程用户手册.pdf) 软件编程用户手册 | 内存映射、启动、Cache、外设驱动、内建函数 | 正文第 9–10、14–19 页；PDF 第 42–43、47–52 页 |
| [MUG1032-1.1](manuals/MUG1032-1.1_Gowin_RiscV_AE350_SOC_DSP软件编程用户手册.pdf) DSP 软件编程用户手册 | DSP 函数分类、数据类型、编译和链接 | 正文第 2–4 页；PDF 第 12–14 页，以及第 3 章接口说明 |
| [MUG1181-1.1](manuals/MUG1181-1.1_Gowin_RiscV_AE350_SOC_NN软件编程用户手册.pdf) NN 软件编程用户手册 | NN 函数、DSP 优化和链接选项 | 正文第 2–4 页；PDF 第 13–15 页 |
| [MUG1030-1.3](manuals/MUG1030-1.3_Gowin_RiscV_AE350_SOC快速开发用户手册.pdf) 快速开发用户手册 | IP 配置、FPGA 构建、软件工程和调试流程 | 硬件设计与软件开发章节 |
| [MUG1025-1.3](manuals/MUG1025-1.3_Gowin_RiscV_AE350_SOC_RDS软件用户手册.pdf) RDS 软件用户手册 | RDS 工程、工具链、调试器及示例 | 按所用工具链／调试器选择相关章节 |
| [MUG1026-1.3.1](manuals/MUG1026-1.3.1_Gowin_RiscV_AE350_SOC_RDS软件安装指南.pdf) RDS 软件安装指南 | 安装包、环境及调试器驱动 | 安装和驱动配置章节 |

这里的“正文页”是页面印刷页码，“PDF 页”是阅读器从封面开始计算的一基页号。本文是工程参考摘要；原始 PDF 保存在 [manuals/](manuals/)，寄存器和指令细节以原件为准，来源与权利说明见 [NOTICE.md](NOTICE.md)。

## 3. 内核、主频与性能

依据 MUG1031 表 3-1、表 4-1～4-3：

| 项目 | 官方说明 |
|---|---|
| 流水线 | 5 级顺序执行；硬件乘法器、除法器 |
| ISA | RV32I；C 压缩、M 乘除、A 原子、N 用户级中断／异常、F 单精度和 D 双精度浮点扩展；支持 DSP |
| 特权与保护 | Machine／Supervisor／User；SV32 地址转换、物理内存保护、栈保护等 |
| 调试 | 外部四线 JTAG；8 个断点；支持性能监测 |
| 核心时钟 `CORE_CLK` | 最高 800 MHz |
| 数据存储器时钟 `DDR_CLK` | 小于 200 MHz；此端口不是 DDR 颗粒 PHY 时钟 |
| 指令／AHB 时钟 `AHB_CLK` | 小于 200 MHz |
| 外设时钟 `APB_CLK` | 小于 200 MHz；与 AHB 为 1:1 同步时钟 |
| RTC 时钟 | 官方 RTC 使用 32.768 kHz |
| 官方基准性能 | Dhrystone 1.72 DMIPS/MHz；CoreMark 3.224845 CoreMark/MHz；Whetstone 0.783 MWIPS/MHz |

手册要求核心、数据存储器与 AHB/APB 三组时钟按其异步关系处理，不能从频率整数倍推断相位关系。官方 DDR3 配套方案另列颗粒工作时钟不高于 400 MHz、fabric 读写参考时钟不低于颗粒时钟的四分之一、参考输入为 50 MHz；这不是 CPU `DDR_CLK` 的频率上限。

基准分数是官方给出的参考指标，不是本项目实测吞吐、最坏服务间隔或实时音频保证。提高当前 100 MHz 核心配置需要新的 PLL、约束、复位／CDC、时序和板级验证，不能只修改一个频率常量。

## 4. 内存、Cache 与地址空间

### 4.1 内置局部存储与 Cache

| 资源 | 地址／组织 | 容量与用途 |
|---|---|---|
| ILM | `0xA0000000–0xA000FFFF` | 64 KiB 指令局部存储 |
| DLM | `0xA0200000–0xA020FFFF` | 64 KiB 数据局部存储 |
| I-Cache | 4 路、32-byte cache line | 32 KiB 指令缓存 |
| D-Cache | 4 路、32-byte cache line | 32 KiB 数据缓存 |

ILM 与 DLM 均支持单比特纠错、双比特检错；合计 128 KiB，不是一个连续的 128 KiB 地址区。FPGA fabric 还可通过 64-bit Extended AHB Master 接口访问其局部存储，实际可用性取决于 IP 端口配置和互连。

Cache 不作为普通堆／栈容量相加。MUG1029 表 6-3 的 `IC_EN`、`DC_EN` 复位值均为 0；软件必须显式初始化和开启。关于替换策略，硬件手册写 pseudo-LRU，软件手册概述写 LRU，使用时保留这一表述差异，不据此假设严格逐访问的替换顺序。

若启用 D-Cache，CPU 与 FPGA／DMA 共享数据时必须明确内存属性、所有权交接、Cache 清理／失效和内存屏障；`fence` 不能代替脏 Cache 写回。现有 UI 源码按 uncached DDR 使用，不能直接在其共享页上开启缓存后沿用原验收结论。

### 4.2 官方存储窗口

| 区域 | 起始地址 | 结束地址 | 地址窗口 |
|---|---|---|---|
| DDR／SRAM 数据存储 | `0x00000000` | `0x7FFFFFFF` | 2 GiB |
| ROM／Flash 指令存储 | `0x80000000` | `0x8FFFFFFF` | 256 MiB |
| ILM | `0xA0000000` | `0xA000FFFF` | 64 KiB |
| DLM | `0xA0200000` | `0xA020FFFF` | 64 KiB |

前两项是可寻址窗口，不代表芯片内置了 2 GiB RAM 或 256 MiB ROM。指令存储可由 SPI Flash、ITCM 或用户自定义存储提供，数据存储可由 DDR3、DTCM 或用户自定义存储提供。ILM／DLM 与这些外部存储接口选项也不能混为一谈。

### 4.3 官方系统与外设映射

以下是 MUG1029 表 3-1 的地址窗口，不表示当前工程启用了所有外设。外设寄存器偏移继续查官方手册和 BSP，不在 UI 中另造编码。

| 功能 | 起始地址 | 结束地址 |
|---|---|---|
| BMC | `0xC0000000` | `0xC00FFFFF` |
| AHB Decoder | `0xE0000000` | `0xE00FFFFF` |
| PLIC | `0xE4000000` | `0xE5FFFFFF` |
| Machine Timer | `0xE6000000` | `0xE60FFFFF` |
| PLIC-SWINT | `0xE6400000` | `0xE67FFFFF` |
| Debug Module | `0xE6800000` | `0xE68FFFFF` |
| Extended AHB Slave | `0xE8000000` | `0xEFFFFFFF` |
| APB Bridge | `0xF0000000` | `0xF00FFFFF` |
| SMU | `0xF0100000` | `0xF01FFFFF` |
| UART1 | `0xF0200000` | `0xF02FFFFF` |
| UART2 | `0xF0300000` | `0xF03FFFFF` |
| PIT | `0xF0400000` | `0xF04FFFFF` |
| WDT | `0xF0500000` | `0xF05FFFFF` |
| RTC | `0xF0600000` | `0xF06FFFFF` |
| GPIO | `0xF0700000` | `0xF07FFFFF` |
| I2C | `0xF0A00000` | `0xF0AFFFFF` |
| DMA | `0xF0C00000` | `0xF0CFFFFF` |
| SPI | `0xF0F00000` | `0xF0FFFFFF` |
| Extended APB Slave | `0xF8000000` | `0xFBFFFFFF` |

总线扩展接口的命名以 AE350_SOC 边界为准：Extended APB Slave 为 32-bit、64 MiB 扩展外设窗口，Extended AHB Slave 为 32-bit、128 MiB 窗口，CPU 在访问 fabric 外设时为主机；Extended AHB Master 为 64-bit 接口，供 fabric 主机访问 AE350 局部存储，此时 AE350 一侧为从机。

官方外设能力还包括双 UART（兼容 16C550A、64 项收发 FIFO、流控／DMA 握手）、PIT 定时／PWM、WDT、RTC、最多 32 路 GPIO、I2C 主从及 100 kbit/s／400 kbit/s／1 Mbit/s、SPI／Quad I/O 和最多 8 通道 DMA。实际引脚、端口启用和 DMA 连线需以所选 IP 配置核对。

## 5. DSP、浮点与 NN 软件

### 5.1 DSP 能力和库

CPU DSP 指令、DSP 软件函数库、FPGA DSP 乘加硬块分别是指令能力、软件实现和可编程逻辑计算资源。调用 DSP 库不等于自动把运算提交给 FPGA DSP 硬块。

MUG1032 描述的库覆盖基本向量、复数、控制器、滤波、矩阵、统计、变换、工具、SVM、距离与排序等函数。支持 Q7／Q15／Q31／Q63 以及 `float32_t`／`float64_t`；具体函数的数据范围、缩放和饱和行为按各接口说明处理。SIMD 路径要求注意 4-byte 数组对齐，尤其是 Q7／Q15 数组。

| RDS 工具链 | 普通库 | DSP ISA 优化库 |
|---|---|---|
| Newlib／MCUlib | `-ldsp` | `-ldsp -mext-dsp` |
| Glibc 动态链接 | `-ldsp` | `-ldsp_p` |
| Glibc 静态链接 | `-static -ldsp` | `-static -ldsp_p` |

依赖数学库的接口还需 `-lm`。以上是官方 RDS／Andes 工具链选项，不能直接添加到本仓库现用的通用 RISC-V GCC 并假定可用。软件浮点库函数、F/D 指令支持和浮点 ABI 也需要分别核对；浮点上下文／异常／RTOS 保存恢复必须配套，不能仅修改 `-march`。

### 5.2 NN 软件库

MUG1181 提供激活、基本数学、连接、卷积、全连接、池化、Softmax 和辅助函数，包含纯 C 实现与 DSP ISA 优化版本。

| RDS 工具链 | 普通库 | DSP ISA 优化库 |
|---|---|---|
| Newlib／MCUlib | `-lnn` | `-lnn -mext-dsp` |
| Glibc 动态链接 | `-lnn` | `-lnn_p` |
| Glibc 静态链接 | `-static -lnn` | `-static -lnn_p` |

手册另介绍半精度函数的 `-mzfh` 和 v5f／v5d 工具链要求。这是库的目标配置要求，不能仅凭有 f16 API 就认定当前芯片配置或本工程已开启 Zfh。现有 RTL CNN 不因存在 NN 软件库而自动迁到 AE350，也没有据此获得新的识别性能验收。

## 6. 官方启动方式与开发入口

MUG1029 第 5 章按配置和 SaG／LD 文件区分三类启动：

| 方式 | 内容与运行位置 |
|---|---|
| `BUILD_LOAD` | GDB／eBIOS 把程序装入 ILM 或 DDR／SRAM 后运行 |
| `BUILD_BURN` | 程序保存在 Flash／ROM，启动后搬运到 DDR／SRAM、ILM 或 DLM；可把关键函数与普通代码分开 |
| `BUILD_XIP` | 代码在 Flash／ROM 原位运行；另有数据位于 DLM 的配置 |

官方 `ae350_rpu_ilm_dlm.sag` 对应代码运行于 ILM、数据运行于 DLM；`ae350_rpu_xip.sag` 对应代码在 Flash／ROM、数据在 DLM。这些是官方 BSP 模式，不代表现有自定义 `boot.ld` 已采用相同初始化流程。

开发顺序可从 MUG1026 安装 RDS 和调试驱动，按 MUG1030 核对 IP、存储和时钟，按 MUG1025 建立工具链与调试配置，再按 MUG1029 处理链接、启动、Cache 和外设。官方提供的下载／烧写步骤只是工具使用说明，执行本项目板卡操作仍需明确授权和独立验收记录。

## 7. 本仓库已核对的实现

### 7.1 输入来源和文件入口

| 内容 | 仓库依据 |
|---|---|
| 运行边界与状态语义 | [架构入口](../architecture/README.md)、[整机接口规划](../../整机接口规划.md) |
| accepted／timing85／资源时序的来源政策 | [基线 README](../../projects/138k/push2_workstation/usb_a/baselines/README.md) |
| 已跟踪的冻结 CPU 配置 | [riscv_ae350_config.v](../../projects/138k/push2_workstation/results/workstation_20260911_174045_306332/Prj1/riscv_ae350_config.v) |
| 已核对的 CPU PLL／启动存储 | [PLL](../../projects/138k/push2_workstation/results/workstation_20260911_174045_306332/Prj1/src/ae350/gw138k_cpu_pll_cell.v)、[boot memory](../../projects/138k/push2_workstation/results/workstation_20260911_174045_306332/Prj1/src/ae350/gw138k_boot_memory.sv) |
| 链接与启动代码 | [boot.ld](../../projects/138k/push2_workstation/results/workstation_20260911_174045_306332/Prj1/firmware/boot.ld)、[start.S](../../projects/138k/push2_workstation/results/workstation_20260911_174045_306332/Prj1/firmware/start.S) |
| 开发候选的原生装配 | [workstation README](../../projects/138k/push2_workstation/usb_a/rtl/workstation/README.md)、[组合根](../../projects/138k/push2_workstation/usb_a/rtl/workstation/gw138k_push_workstation_top.v) |
| 构建入口与辅助审计 | [build.py](../../projects/138k/push2_workstation/usb_a/build.py)、[AE350 scripts](../../projects/138k/ae350/scripts) |

冻结配置启用了 `AE350_EXT_I_MEM_EN`、`AE350_EXT_D_MEM_EN`、`AE350_EXT_APB_SLAVE_EN`、`AE350_APB_SMU_EN`。这些宏描述已选接口，不是完整 ISA 或 Cache 开启状态查询。

生产准备流程按锁定清单重建输入，不能把任意活动文件或历史脚本视为所有 profile 的实际编译来源。最终必须从所选构建的 manifest、生成 `.gprj`、ROM 与固件身份复核；冻结目录仅作为可追溯参考，不直接修改。

### 7.2 时钟、启动与存储

已核对的 PLL 以 50 MHz 输入、24 倍频，再分别除以 24／12，得到总线 50 MHz、核心 100 MHz。原生组合根将 `CORE_CLK` 接核心时钟，`DDR_CLK`、`AHB_CLK`、`APB_CLK` 接总线时钟。其 `RTC_CLK` 接 `clk_50m`，不符合官方 RTC 标准输入的 32.768 kHz，不能据此宣称当前 RTC 已正确计时；现有固件未提供对应验收。

| CPU 可见区域 | 地址／大小 | 已核对实现 |
|---|---|---|
| 启动 ROM | `0x80000000–0x80003FFF`，16 KiB | `4096 × 32-bit`，由 `firmware/boot.mem` 初始化；位流携带的 ROM 内容不等于外部 Flash XIP 固件 |
| PL 工作 RAM | `0x00000000–0x00001FFF`，8 KiB | `1024 × 64-bit`，字节写使能 |
| 链接器 RAM 区 | `0x00000200–0x00001FFF`，7.5 KiB | `.data`／`.bss` 从 `0x200` 开始；低 512 bytes 未分配给普通数据段，启动自检使用 `0x100` 一带 |
| 栈 | 初始 `sp=0x2000`，向低地址增长 | 链接断言 `__bss_end <= 0x1000`，为栈保留至少 4 KiB；这是静态布局检查，不是运行时防溢出证明 |
| UI page 0 | `0x10000000–0x103FFFFF`，4 MiB | 桥接至物理 DDR UI 页 0 |
| UI page 1 | `0x10400000–0x107FFFFF`，4 MiB | 桥接至物理 DDR UI 页 1 |

`start.S` 设置异常入口，执行 RAM 字节通道／读回自检，将 `.data` 初值从 ROM 复制到 RAM，清零 `.bss`，再进入服务程序。已核对源文件没有把数据／栈链接到 DLM，也没有把函数放入 ILM；未见显式 Cache 开启代码。对其他 profile 和板上镜像仍应检查其实际输入，而不是扩大这份参考脚本的结论。

DDR 分配唯一依据仍是 [ddr_address_map.vh](../../projects/138k/push2_workstation/usb_a/rtl/ddr_address_map.vh)。它记录物理 DDR 总容量 1 GiB，以及 CPU UI 两页到物理字节区 `0x01000000–0x017FFFFF` 的映射。这里的 CPU `0x10000000` 与物理 DDR 同值地址不是一回事。原生 `app_addr` 以 32-bit 字计数，一次 BL8 为 32 bytes、步进 8；其余客户和预留空间直接查该权威表，不在本文再分配一套地址。

已核对的 [AHB→DDR 桥](../../projects/138k/push2_workstation/results/workstation_20260911_174045_306332/Prj1/src/ae350/gw138k_ahb_ddr.sv) 仅支持一个 outstanding 事务，检查 UI 地址窗口和访问对齐，通过跨域请求／响应握手完成；不支持的窗口或对齐返回错误。不能将官方 2 GiB 数据窗口解释为当前 CPU 可直接访问全部物理 DDR。

### 7.3 服务、工具链与业务边界

已核对的固件使用 `0xF8000000` 诊断、`0xF8010000` 音频服务、`0xF8020000` UI 服务，均处于 Extended APB 窗口。详细字段查已有 [audio_services.h](../../projects/138k/push2_workstation/results/workstation_20260911_174045_306332/Prj1/firmware/audio_services.h) 和各服务 RTL，不把这些自定义基址误认作 AE350 固定硬件寄存器。

构建代码使用 `-march=rv32im_zicsr -mabi=ilp32`，按裸机方式链接自定义启动代码，检查固件大小不超过 16384 bytes，再形成 `boot.mem`。这证明所选固件的指令和 ABI 策略，不是 CPU 全部能力列表，也不证明已经链接官方 DSP／NN 库。`ae350/scripts` 中的早期脚本还保留历史本机依赖，不是默认生产入口。

AE350 的当前职责是 UI、命令／服务和启动自检；USB Host／MIDI 传输继续由相应 USB CPU／适配器承担，音频采样、合成、效果与识别数据通路继续由各 RTL 子系统负责。公共参数必须在现有权威应用点提交，不能在 CPU 软件中建立并行真值。连续采样不等待 CPU、显示、文件或 BLE。

## 8. 后续利用内置资源时需要补齐的证据

本次只整理资料，没有改变链接、Cache、CPU 时钟或硬件配置。后续实现可按以下边界逐项推进：

1. 从实际准备后的固件、IP 配置与映射文件核对 ILM／DLM、Cache、FPU／DSP 和编译器支持情况；必要时读取对应 CSR／状态，但板卡操作单独授权。
2. 若迁移到 ILM／DLM，明确代码／只读数据／全局变量／堆／栈容量，补齐复制、清零、异常入口及固件装载方式；不能只改链接地址。
3. 若开启 Cache 或共享局部存储，明确 CPU 与 fabric 的所有权、内存属性、屏障、Cache 维护及复位行为，再验证数据一致性。
4. 若将 BLE 非实时业务迁到 AE350，复用现有 APB，定义有界包交接、满队列背压／溢出、取消与错误行为，测最长服务间隔和 ROM／栈预算；连续 PCM 采样和公共参数应用点仍保持各自归属。
5. 软件卸载、独立仿真、综合资源、整机 P&R、实体功能和 SRAM／Flash 部署分别记录。内置 RAM／DSP 能力不等于已经释放了相同数量的 fabric BSRAM／CLS。

此前 BLE 资源优化与软件卸载预算见 [AE350 分工报告](../../projects/138k/push2_workstation/usb_a/reports/AE350_RESOURCE_OPTIMIZATION_20261027.md)。该报告包含已实施的 RTL 缓存优化及尚未实施的 CPU 业务卸载，不应混成已完成的迁移。

## 9. 查阅顺序

- 硬核是什么、主频／RAM／浮点／DSP：先看本文第 3～5 节，再查 MUG1031。
- 完整内存映射、启动和 Cache：查 MUG1029 第 3、5、6 章。
- DSP／NN API 的参数、缩放和链接：查 MUG1032／MUG1181；以目标工具链和硬件扩展匹配为前提。
- 本项目实际用了什么：从本文第 7 节进入源码，再核对所选 profile 的生成输入。
- 板上现在是什么、哪些功能被验收：查[架构入口](../architecture/README.md)链接的日期化候选／部署证据，不从官方规格或历史文件名推断。

## 10. 本次核对的官方 PDF 身份

以下 SHA256 对应本目录 `manuals/` 中的原始 PDF，复制后与第 2 节采集来源逐字节一致。机器可读清单见 [manifest.json](manifest.json)，不将 PDF 作为构建依赖。文件名中的中文标题与第 2 节对应。

| 文件编号／版本 | PDF 总页数 | SHA256 |
|---|---:|---|
| MUG1031-1.3.1 | 66 | `0f357e21c8341a23a399a32a54bc706de953767235826ed39886924549756dc3` |
| MUG1029-1.3 | 363 | `3b8c45bdb4612fcafce82626d202ecf640351290a9be4b58571b6d20674f72ee` |
| MUG1032-1.1 | 216 | `f31766acbb61016966918c766a3e05d27aa70d52705efa2135cec3fb67cd6266` |
| MUG1181-1.1 | 178 | `223eb0f50f95c8c3c941aec21989c46fa49681e041e07e748cf2ac0ab8c33920` |
| MUG1030-1.3 | 41 | `66945fb66d6ee2eefa6e83f28fdefd1a07b64796bd6526db1f496101ffd9b3a3` |
| MUG1025-1.3 | 159 | `a9de3dcc5d1f400281cd0b636b902a4ee8cabfad38f36fa9a92bdb546a5b3399` |
| MUG1026-1.3.1 | 25 | `0c6599ca52d916219ffd3cac6e1e153ea3b5891ab26f269af1de0a849f2a4ce6` |
