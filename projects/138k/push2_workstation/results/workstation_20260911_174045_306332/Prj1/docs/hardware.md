# Prj1 板级依据与接口核查

核查日期：2026-09-08；当前源码边界复核：2026-09-09。目标是 **Tang Mega 138K SOM + Tang Mega NEO Dock-138K 31005**，FPGA 工程器件采用 **GW5AST-LV138PG484AC2/I1，GW5AST-138C（C版）**。旧B版和其他封装仅保留资料出处含义。本文把原理图与器件手册能够确认的事实、当前工程选择及仍需实物验证的项目分开记录。文中页码均为 PDF 文件页序，从 1 开始；括号中的页码为印刷页码。

## 1. 资料依据

优先使用本地 `Doc/GW官方` 的器件资料；板上布线以指定版本原理图为准，demo 仅作实现交叉验证。以下路径相对于本项目的 `docs` 目录。

| 标识 | 文件 | 使用位置 |
|---|---|---|
| D1 | [31005 底板原理图](../../../Doc/Mega_138K_60K/02_Schematic/DOCK/Tang_Mega_NEO_Dock-138K_31005_Schematics.pdf) | 第 7 页 SOM_BTB1&2、第 8 页 USB_JTAG、第 9 页 PERIPHERALS、第 10 页 FPGA_AUDIO、第 15 页 FPGA_TMDS、第 18 页 SYS_CLOCK；图纸 Rev 1.3，2024-10-15 |
| D2 | [30354 核心板原理图](../../../Doc/Mega_138K_60K/02_Schematic/SOM/tang_mega_138k_30354_Schematics..pdf) | 第 3 页：两颗 DDR3；第 5 页：固定晶振、JTAG/UART 接口、核心板按键和配置 LED |
| G1 | [UG986-1.2.7 GW5AST-138 Pinout](../../../Doc/GW官方/UG986-1.2.7_GW5AST-138器件Pinout手册.pdf) | **PG484A** 表，第 10、12、13、16 页；同一 PDF 还包含其他封装，不能只按球位搜索后直接套用 |
| G2 | [UG304-1.3.7 GPIO](../../../Doc/GW官方/用户指南/UG304-1.3.7_Arora_V可编程通用管脚(GPIO)用户指南.pdf) | 第 25-26 页（15-16 页）差分输出原语；第 111-112 页（101-102 页）OSER10 |
| G3 | [UG306-1.0.9 时钟资源](../../../Doc/GW官方/用户指南/UG306-1.0.9_Arora_V时钟资源(Clock)用户指南.pdf) | 第 43-45 页（34-36 页）GW5AST-138 的 PLL 和分频公式 |
| G4 | [DS1239-1.0.3 FPGA 数据手册](../../../Doc/GW官方/DS1239-1.0.3_GW5AST系列FPGA产品数据手册.pdf) | 第 52 页（43 页）PLL 电气范围 |
| A1 | [PT8211 V1.6，February 2012，厂商手册的 PJRC 镜像](https://www.pjrc.com/store/pt8211.pdf) | 第 1 页功能、第 3 页引脚、第 4 页协议图和声道映射、第 5 页电气/时序范围；本地资料中未发现该 DAC 手册，故补充此来源 |
| E1 | [audio_i2s demo](../../../Doc/tangMega-138K-example/audio_i2s/eda_proj/src) | `audio.cst`、`audio_drive.v`、`top.v`；引脚可交叉验证，但部分注释和旧板 LED 不能沿用 |
| E2 | [hdmi_svo demo](../../../Doc/tangMega-138K-example/hdmi_svo/eda_proj/src) | `hdmi.cst`、`svo_hdmi.v`；交叉验证差分球位及 OSER10 / ELVDS_OBUF 组合 |
| E3 | [通用 138K 约束表](../../../Doc/Mega_138K_60K/08_Misc/tang_mega_138K_pins.cst) | 交叉验证 UART U15 / V14；其中旧 LED / 按键命名不作为 31005 的最终依据 |

已对 D1 第 7、9、10、15 页、D2 第 5 页及 A1 第 4 页进行 PNG 渲染目视核查。D2 的文本提取存在字体编码问题，因此时钟和核心板按键结论来自图形连线核查。中间图像、提取文本和 A1 下载副本位于被忽略的 `build/hardware_audit/`，不属于交付资料或提交内容。

## 2. 音频、串口和 HDMI 引脚

下表方向均以 FPGA 为参照。球位是 PG484A 封装球位，并非排针序号。本表单端信号采用 3.3 V LVCMOS；DDR Bank 6/7 为独立的 1.5 V SSTL15 域，详见下文。TMDS 使用 demo 对应的 `LVCMOS33D` 和成对约束。

| 顶层端口 / 功能 | FPGA 球位 | 方向 | 原理图网络与核查来源 |
|---|---|---|---|
| `clk_50m` | V22，Bank 4 | 输入 | D2 第 5 页：Y1100 50 MHz 晶振，经 R973 到 `BANK4_V22_EMCCLK_50Mhz`；G1 第 10 页 `IOB104B/EMCCLK` |
| `button1_n` | AB13，Bank 5 | 输入 | D1 第 7/9 页：`EX_KEY.1`，**USER_BUTTON1，S2**；按下接地，需 FPGA 内部上拉 |
| `uart_rx` | V14，Bank 5 | 输入 | D1 第 7/8 页：`FPGA_UART.RX`，来自 BL616 IO28/TX，经 R57 |
| `uart_tx` | U15，Bank 5 | 输出 | D1 第 7/8 页：`FPGA_UART.TX`，到 BL616 IO27/RX，经 R58 |
| `hp_bck` | Y17，Bank 5 | 输出 | D1 第 7/10 页：`I2S_BCLK` → PT8211-S BCK，器件脚 1 |
| `hp_ws` | AB17，Bank 5 | 输出 | D1 第 7/10 页：`I2S_LRCK` → PT8211-S WS，器件脚 2 |
| `hp_din` | AA16，Bank 5 | 输出 | D1 第 7/10 页：`I2S_DIN` → PT8211-S DIN，器件脚 3 |
| `pa_en` | AB16，Bank 5 | 输出 | D1 第 7/10 页：`PA_EN` → R132 → NS4263 `SD`；**0 开，1 关** |
| `hdmi_tx_en` | K14，Bank 3 | 输出 | D1 第 7/15 页：`DVI-A_ALT` → R164 → `DVI_DIR_SEL`；**1=TX，0=RX** |
| TMDS D0 P / N | J14 / H14，Bank 3 | 输出 | D1 第 7/15 页：`DVI-A_D0.P/.N`；E2 一致 |
| TMDS D1 P / N | J15 / H15，Bank 3 | 输出 | D1 第 7/15 页：`DVI-A_D1.P/.N`；E2 一致 |
| TMDS D2 P / N | K17 / J17，Bank 3 | 输出 | D1 第 7/15 页：`DVI-A_D2.P/.N`；E2 一致 |
| TMDS CLK P / N | G15 / G16，Bank 3 | 输出 | D1 第 7/15 页：`DVI-A_CK.P/.N`；E2 一致 |

物理约束在 [tang_mega_138k.cst](../constraints/tang_mega_138k.cst)。D1 第 15 页 TMDS 附近仍有其他封装形式的球位注释；本工程采用第 7 页 BTB 上的 PG484A 网络名，并用 G1 和 E2 交叉验证。

其他有用但首版未接入、可供扩展的引脚（新版已读取HPD）：USER_BUTTON0/S4 为 AA13，USER_BUTTON2/S1 为 Y12；HDMI HPD 为 K13，DDC SCL 为 M13、SDA 为 L13；底板可编程 `USR_CLK_IN` 为 V13。这些端口不能与表内功能互换。

## 3. UART 输入路径

D1 第 8 页的 USB-JTAG/UART 芯片是 **BL616C-50-Q2I-QFN40**。用户控制数据通过板上调试 USB 接口、BL616 桥接固件进入 FPGA UART，无需先加外部串口模块。主机 COM 口枚举、驱动和桥接固件是否提供透传，需要连接实物确认；原理图只能确认连线。

D2 第 5 页另有核心板 8-pin 1.0 mm JTAG 接口 U1201：脚 7 为 FPGA RX/V14，脚 8 为 FPGA TX/U15，脚 6 为 GND，脚 1 为 5 V 电源。UART 信号本身仍为 **3.3 V 逻辑**。外接串口时要共地，并避免外部 TX 与已连接的 BL616 TX 同时驱动 V14。

首版协议与波特率由项目 UART 控制模块和 README 定义；这不是原理图固定参数。旧 `sd_card` demo 的 `txp=R19` 对应其他硬件使用背景，不能作为本板 USB 串口 TX。

## 4. HEADPHONE 输出及 PT8211 格式

**板载 DAC 是 U16 PT8211-S，16 bit 双声道，采用 LSBJ/Japanese 右对齐格式。** 原理图把网络总线称为 `I2S_OUT`，demo 目录称为 `audio_i2s`，但都不能替代芯片的实际时序要求。

由 D1 第 10 页和 A1 第 3/4 页确认：

- 仅有 BCK、WS、DIN 三根数字音频线，无 MCLK，也没有 I²C/SPI 配置或格式选择脚；不需要 codec 初始化寄存器表。
- 输入是 16 bit 二补码、MSB first，DAC 在 **BCK 上升沿**采样 DIN。
- **WS=0 对应右声道，WS=1 对应左声道。** A1 第 4 页正文与 Figure 1 都给出这一映射。
- 一个声道最后的 LSB 在旧 WS 电平下被上升沿采样，随后 BCK 下降沿切换 WS 并输出下一声道的 MSB。每声道恰好 16 个 BCK，不插入标准 Philips I²S 的一位延迟。
- 左右各 16 bit，一帧共 32 个 BCK。这里的物理串行帧宽与工程内部每个音频样本的 32 bit 数据链路不是同一个概念；末端把 Q1.31 量化为 PCM16。

首版使用固定 50 MHz 的整数分频，BCK 每 16 个系统周期翻转，得到 **BCK=1.5625 MHz，Fs=48,828.125 Hz，帧周期=20.48 µs**。这是工程选择，并非晶振误差造成的近似 48 kHz。音高相位增量和包络时长必须按实际 Fs 计算。A1 第 5 页给出 BCK 最大 18.4 MHz、WS 最大 384 kHz，当前数字时钟低于这两个上限；模拟输出质量仍需板测。

模拟通路为：

```text
PT8211-S → LMV321 二阶低通 → NS4263 功放 → 耦合电容 → J25 HEADPHONE
                                           └─────────→ 扬声器接口
```

D1 第 10 页明确标注 **PA_EN=1: PA OFF；PA_EN=0: PA ON**。耳机也经过 NS4263，因此把 PA_EN 永久置 1 会同时关闭耳机通路。插入耳机后，机械检测使 NS4263 `HP-IN=1`，切到 headphone 模式；拔出为 `HP-IN=0`，切到 speaker 模式。该检测由模拟电路完成，首版不需要 FPGA 读取耳机检测。

[pt8211_tx.v](../src/audio/pt8211_tx.v) 在复位及启动等待阶段保持 PA_EN=1，经过 512 帧后拉低使能。当前顶层启用 `STEREO_ENABLE=1`，从40位混音经总体音量/LR平衡产生独立的左右Q1.31，并成对缓存后按“低WS右、高WS左”发送；默认居中时两路相同。量化采用最近舍入、恰好半LSB时远离零，再饱和为PCM16。不得照搬demo中相反的声道注释；左右数字串行仿真不代替耳机物理声道验证。

独立迁移候选保留原准确48kHz音频参数，采用76.8MHz音频时钟与每半BCK 25拍，得到BCK=1.536MHz、Fs=48kHz；这不改变本Prj1的50MHz/48,828.125Hz配置。原Philips I²S端口不能接到PT8211引脚。G1 F12为3.3V/31,250 baud MIDI输出，须为其分配独立、实际可接出的138K输入球位并确认共地，不能并接已由BL616 TX驱动的V14。时钟和后续AE350接口依据见[迁移笔记](../../../../migration/HARDWARE_ADAPTATION_NOTES.md)。

## 5. HDMI 显示和时钟

底板 J29 是 HDMI Type-A 连接器，D1 电路名称为 DVI。本轮输出目标为 **TMDS 视频，1920×1080 / 60.000 Hz**，像素来自 DDR RGB565 双帧缓冲，扫描末端扩展为 RGB888。音频走 HEADPHONE；HDMI 音频包、HDCP、CEC、EDID 读取不属于当前视频通路。

本轮采用 **148.5 MHz 像素时钟**，2200×1125 总时序；串化时钟 **742.5 MHz**，每 TMDS 数据通道 1.485 Gbit/s。50 MHz 经 49.5 MHz 参考级与第二级 PLL 得到精确标称频率，每级 LOCK 持续稳定至少 2 ms 后才释放下级。实际频率继承晶振误差，显示器锁定及信号质量仍需板测。原 25/125 MHz、640×480 / 59.524 Hz 方案仅为已获用户显示反馈的历史版本；详细 PLL 参数、限值和光栅见 [video_1080p_notes.md](video_1080p_notes.md)。

- G2 第 111 页规定 OSER10 顺序为 D0、D1…D9，`FCLK=5×PCLK`，RESET 高有效。E2 同样使用 OSER10。
- G2 第 25/26 页区分 TLVDS_OBUF 与 ELVDS_OBUF；本板实现参考 E2 的 **ELVDS_OBUF** 及成对 `LVCMOS33D` 约束，不能把 P/N 各自用普通逻辑反相后当作差分原语。
- G3 第 43-45 页说明 GW5AST-138 使用 PLL 原语。内部反馈时 `Fpfd=Fin/IDIV`，`Fvco=Fpfd×FBDIV×MDIV`，VCO 路输出为 `Fout=Fvco/ODIV`。时钟参数应满足 G4 第 52 页的 PFD 19-81.25 MHz、VCO 650-1300 MHz 范围，并由 Gowin 工具检查布局和时序。
- D1 第 15 页 `DVI_DIR_SEL` 通过 R165 上拉到 TX 默认值，工程同时显式驱动 K14=1，以使能发送方向及 HDMI 5 V 输出。HPD（K13）已接入只读运行诊断；HPD与DDC不参与视频启动判定。
- D1 第 15 页 TMDS 经 100 nF 串联电容及保护电路到连接器；收发方向相关终端、电压、电缆和显示器锁定都应在上板时验证，仿真不能替代信号完整性核查。

50 MHz 基准来自核心板 Y1100/V22。D1 第 18 页的 **MS5351M + 25 MHz 晶体**属于另一条可编程时钟路径，其 CLK2 到 `USR_CLK_IN`/V13，由 BL616 的 I²C 配置；本轮亦不依赖该芯片的上电配置。

## 6. 核心板 DDR3

D2 第 3 页两颗 H5TQ4G63EFR-RDC 各提供 16-bit DQ，合计 32-bit、1 GiB。DDR 在核心板上，使用 PG484A Bank 6/7 的 1.5 V SSTL15/SSTL15D；不可把其他接口的 3.3 V LVCMOS 约束套到 DDR。实物兼容颗粒仍以丝印和校准结果为准。

本轮采用 `ddr_memory` 的 C 版 138K DDR3 IP，400 MHz CK、800 Mbit/s/DQ，100 MHz × 256-bit 用户口；保留 IP 的 `pll_stop`、PLL_INIT 与专用 PHY 资源。DM 四引脚 AA4/V7/T6/W1 补自 SOM 和交叉示例。完整球位表、C/B 版区别、原生地址单位和资料出处在 [ddr_platform_notes.md](ddr_platform_notes.md)。

显示双帧保留前 8 MiB。启动只对该区做两遍地址模式/反码写读自检，未测试全 1 GiB。DDR 失败保持显示不可用，串口、合成与耳机链路仍独立运行。帧布局、诊断和验收步骤见 [ddr_display.md](ddr_display.md)。

## 7. 原资料差异和不可沿用项

| 容易误用的资料 | 本次核查结果 |
|---|---|
| audio demo 顶层称 PA_EN “高电平有效” | D1 第 10 页低有效；demo 本身赋 0 开启也说明注释不可信 |
| audio demo 称 WS 低为左声道 | A1 第 4 页规定低为右、高为左 |
| 设计草案及 demo 使用“I2S”总称 | PT8211 必须使用其 16-bit LSBJ 格式，不使用 24/32-bit Philips I²S 帧 |
| audio demo `led=W21` | D1 第 7 页 W21 是 `SDRAM1_D12`，不作为 31005 普通 LED 输出 |
| 通用 pin 表列出八个用户 LED | 当前底板 D1 的用户灯是 WS2812，不能按旧八灯约束输出；核心板 LED 主要为电源 / DONE / READY |
| audio demo `rst=F4` | D2 第 5 页 F4 是核心板 `CPU_RESET`，按键接 VCCIO67，为高有效且属不同电压域；本工程选 3.3 V、低有效 AB13 |
| 旧约束的“Key0” | D1 第 9 页：AA13=S4/USER_BUTTON0，AB13=S2/USER_BUTTON1，Y12=S1/USER_BUTTON2 |
| 旧 sd_card demo `txp=R19` | D1 第 7/8 页、D2 第 5 页及 E3 一致给出 USB 桥 TX=U15、RX=V14 |
| E2 自动生成文件头出现 FPG676AES | 当前物理球位及工程器件选择以 PG484A / G1 为准；不能整包复制旧 demo 工程配置 |

提供的设计文档保留全部 41 个模块工作包与后续功能构想。首版硬件输出选择服从用户本次要求：串口输入、HDMI 显示、板载 HEADPHONE。32 bit 模块间链路继续保留，PT8211 输出是末端量化边界。基础工程完成不等于整个长期设计、全部接口、综合时序及上板验收均已完成。

## 8. 必须通过实物验证的项目

以下结论尚不能仅凭原理图或 RTL 仿真登记为通过：

1. 核对实物确为 138K PG484A、SOM 30354 / NEO Dock 31005 或电气等效版本；确认 Bank 3/4/5 实际供电与 3.3 V 约束一致。
2. BL616 固件、主机 COM 口与双向 UART 通信，实际波特率及协议收发；无数据时 RX 应为高。
3. AB13/S2 按下复位、释放重启；V22 实测约 50 MHz；完成 Gowin 综合、布局布线、时序与下载验证。
4. 用逻辑分析仪确认 PT8211 的 BCK=1.5625 MHz、WS=48.828125 kHz、16 bit 右对齐和上升沿采样余量；独立左右声道测试后再登记声道映射通过。
5. 耳机插拔检测、PA_EN 极性、低音量合成音、静音、音高和包络，以及启动噪声和削顶；记录模拟输出幅度和端到端延迟。
6. 本轮 HDMI TX 方向、显示器成功识别 1920×1080 / 60 Hz、颜色/同步正确、拔插与复位恢复，以及 1.485 Gbit/s TMDS 信号质量。
7. DDR 两颗器件与供电、PLL/PHY 校准、前 8 MiB BIST、后台帧推进和扫描欠载、复位/失锁恢复；其余容量与长期压力需要另行覆盖。

截至2026-09-08，用户已确认首版640×480 HDMI“FPGA SYNTH”；COM26（B接口）PING已实际通过，COM25（A接口）曾复现超时。本轮DDR/1080p首版与第四路OSER10版已手动下载，串口支持DDR校准、前8MiB BIST通过及首帧有效；早期版本未稳定显示；15:06官方PLL初始化版已通过本板1080p60基本显示检查，用户确认菜单1920×1080/60Hz及演奏反馈正常，串口约60帧/s且欠载0。实际波特率、长期锁定、热插拔、正弦音质和模拟音频仍待测，详见 [verification.md](verification.md)。
