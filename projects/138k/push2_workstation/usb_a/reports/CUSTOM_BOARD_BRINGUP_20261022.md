# 自定义 138K 新板与外设 bring-up 清单

日期：2026-10-22。目标是**新板与实际连接外设达到可以上板观察、定位故障和调试的水平**，包括 25K、USB2 High-Speed、功放、蓝牙及底板外设；不是只完成位置约束或离线测试。

本文保留 ULPI 初版的输入哈希与当时范围；随后变更及新的源身份见 [HS／FS Host 端口联调](CUSTOM_BOARD_USB2_HOST_PORT_20261022.md)，不将本文旧哈希解释为当前源码身份，也不改写初版测试记录。

## 1. 本轮状态与源码策略

起点为 `45e7b4870b57372578a967d284c9cf4b09d1bae0`，该引脚准备提交已推送至 `origin/main`。本轮新增的是第一方 ULPI 开发库和仿真，不把它冒充已接入的整机固件，不改变 accepted full83、timing85、资源时序候选或本机实际部署。两份已有未跟踪报告保持原样。

板卡输入仍由 [custom_138k 配置](../boards/custom_138k/README.md) 的原始网表身份约束；位置映射身份 `custom_138k_usb2_20261022_pinout_v2` 不因此变成新固件身份。ULPI 源码标识为 `custom_138k_ulpi_link_dev_20261022`，仅为以下未接入的开发库快照，不复用任何已验收 UserCode。本轮没有 UserCode、位流、SRAM 部署或 Flash 部署。

| `rtl/usb2/` 文件 | SHA256 |
|---|---|
| `workstation_ulpi_link.sv` | `60e4212b91c348bd91406cd6e49487268974b2ccb5f94b83e93fac9651cf9a56` |
| `workstation_ulpi_supervisor.sv` | `9741276485cc6393e7786bb7ca5886d719f120e810839fe9aa2078a723b2a840` |
| `workstation_usb3300_host_init.sv` | `546d0d2ee624dc4ecb2551273c27b9cba5e48c2d81d16dadce13c43e16fc4dbe` |
| `workstation_usb3300_host_link.sv` | `8d4833a57b3f67d3da9ddfbf0a3cd710307f67e99797c1d02327717659ac3097` |

详细时钟、寄存器、自检、背压、错误、取消与恢复契约见 [USB2 模块说明](../rtl/usb2/README.md)。实现基于 USB3300 官方 DS00001783C；本机核对手册 SHA256 为 `33e73e37f5110cb9e3ef66ccf8c7fdd4a16593c7b1afcff0c5df523e41963a9e`。Host 的 Interface Control 使用 `10h`，不是设备端旧诊断的 `00h`，保留 Host AutoResume。没有将设备端代码整工程复制为 Host。

## 2. 全范围交付门禁

| 范围 | 当前可复用／已实现 | 离目标尚缺／验收方法 |
|---|---|---|
| 新板配置／组合根 | 网表身份检查、101 端口／110 球位规划、旧核心位置保留；显式 pinout-only 入口 | 新板原生顶层、复位／时钟／IO_TYPE、电气门禁、明确源码清单及完整构建；不能直接改旧 `p11.cst` 下载 |
| USB2 电气与连接 | USB2 USB-A→USB3300→ULPI 实际端点已映射，Host 与电脑调试口职责分开 | U4／U5 A 侧 1.8 V 与 USB3300 逻辑电平不匹配，须确认实装／修正并测量；不全局改 `VDD_1V8`，不在门禁未解除时上板驱动 |
| USB2 ULPI 物理链路 | 新增 CSR、UTMI 字节收发、RXCMD、NXT 背压、安全换向、失败锁存；已仿真 | 60 MHz 约束／实际 IO 时序与 CDC、读回 USB3300 身份及实测频率；无硬件证据 |
| USB2 启动与可观察性 | 新增独立参考域缺钟／停钟监护、STP 恢复、身份／Scratch／Host 配置读回、失败步骤、显式重启；真实组合已仿真 | 将稳定诊断经正确 CDC 接 UART／GAO；实体断开、缺钟、坏接线和重启定位；ready 仅为 PHY 初态 |
| 真正的 480 Mbps Host | PHY 字节路径具备 NOPID 支持；25K 有独立 HS 设备端参考 | Host attach／reset／chirp K/J 协商、FS 回落与断开、125 µs microframe、HS SIE 时限／CRC／重传、512 字节 FIFO／固件 MPS；枚举并在 HS 与 FS 分别做真实数据与错误恢复验收 |
| 25K 交互连接 | 现有 MIDI／PL 和完整复合设备契约；25K 独立 HS CDC 已有实板证据 | MIDI_KEYBOARD 仍须接入已验证 HS 物理路径及 MIDI／vendor 描述符；不能把 CDC 回环当作 MIDI／PL 完成；须保留 VID/PID、现有 PL 字节契约、18-bit 生命周期，验收演奏／屏幕／拔插／PANIC |
| Push 回退 | 旧 FS Host／业务路径与冻结来源未改 | 新 USB2 PHY 上 FS 实测及 Host 协商回落；与 25K 交替使用同一口，不假设同时连接 |
| DAC／功放 | 音频 BCK／WS／DIN、MCLK D17、PDN C17、滤波／静音脚和检测路径已推导 | U1 具体型号、RN 内部配对及排线脚号确认；按实际格式实现 serializer、MCLK、滤波 strap、安全上电／静音／掉钟。旧 PT8211 不是已兼容证明，`FPGA_DET` 不冒充 `pa_en`；实体测 BCLK/LRCK/MCLK、零输出和有声现象 |
| HDMI | 四组合法差分对、HPD 与 CEC 映射已核对 | 四条串行 lane（含时钟）共同反相以补 PCB P/N；CEC 默认释放而非输出旧 tx_en；实际 HPD／分辨率／画面，另跑物理时序 |
| TF | SPI 四线位置确定，MOSI 修为 W14；既有读卡／播放业务可复用 | 新板原生约束和电源确认、真卡初始化／读文件／播放／拔卡取消；新板未验收，不把蓝牙 SDIO 当 TF SPI |
| 蓝牙 | 138K 已有独立 50 MHz 8E1／H5／HCI／GATT 诊断与仿真；25K 业务协议另有独立验收 | 新板反序排线与剩余球位、模块 disable／UART 方向和电气确认；在138K上做控制器启动／RF／重连，再按现有业务契约接入。FFF0/FFF1 测试服务不是 Android 录音业务后端；实际音频 tap、录音／下载仍须单列，不凭驱动存在宣称完成 |
| DDR／工作站／显示状态 | 旧核心位置和资源时序原生业务边界保留 | 新板同核心假设与实际 DDR 初始化、音频连续调度、最终输出/tap、状态展示；不因新 USB 引入第二份公共参数真值 |
| 调试与部署 | U13 十针外部 JTAG 连接定义；U15/V14 UART 球位已规划 | 实体下载器／电源／接地确认，新的源与位流身份，Gowin 综合／P&R、CDC／PLL／时序／资源检查；之后独立授权的 SRAM 写入与读回／现象验收，最后才可规划 Flash 固化和断电启动 |

长录音、D 模式及未明确的新产品工作流不因外设搬迁自动视为完成；既有实现的边界继续遵循架构与协议文档。上述硬件缺口不阻止推进 Host、DAC 时序、组合根和回归等有依据的离线工作。

## 3. 本轮离线证据

`sim/test_workstation_ulpi_link.py` 用 Icarus Verilog 13.0 运行四个独立场景组：

| 回归 | 本次结果与范围 |
|---|---|
| ULPI 物理总线 | 10,166 次检查、15 次复位场景；全部 256 种 Scratch 数据与 RX 字节、514 字节发送、NOPID、RXCMD、换向、NXT 背压、抢占／超时／中途复位 |
| USB3300 初始化＋物理模型 | 3,762 次检查、19 场景；全部身份与 Host 配置／Scratch 逐项读回；坏身份／首次及末次配置／Scratch错误、请求或应答受阻、时限、安全／不安全抢占和重试上限 |
| 独立时钟监护 | 223 次检查、4 场景；时钟启动缺失、低电平／高电平停钟、晚到、返回后仍锁存故障、显式重启、无 ULPI 边沿时复位和两级同步释放 |
| 真实四模块组合 | 3,115 次检查、5 场景；初始化阻隔提前到达的运行期请求、CSR 交接与应答背压、同一物理 PHY 不硬复位的 warm 恢复、坏 ID／缺钟隔离、运行期 fatal 取消和安全抢占重试 |

Verilator 5.046 对真实四模块组合执行 `--lint-only -Wall`，零警告；未屏蔽 lint。Yosys 0.67+post 的 `hierarchy -check`／通用 `synth`／`check -assert` 通过。通用映射 cell 不是 Gowin LUT／BSRAM 资源，也不是已带 IO 约束的 Gowin 综合或布局布线。

原构建入口额外回归通过：`test_workstation_pinout.py` 25 项、`test_current_workstation_sources.py` 10 项、`test_stage_usb_firmware.py` 6 项及 `GW138K_VERIFY_CLEAN_PREPARE=1 test_workstation_baselines.py` 23 项。连同本轮 4 项物理／组合回归，共 68 项；三条完整工作站 clean prepare 未因新库漂移到另一种来源策略。这仍不是新板整机实现或硬件证据。

复现命令见模块 README。仿真模型、bench 与 runner 均为第一方版本化源码，不依赖私有暂存或 FPGA。未给仿真通过的链路附加不存在的包级 CRC／重传、HS Host 或实板验收。

## 4. 回退与下一步

- 本轮新模块未选入任何 accepted 配置；停止选用开发库即可保留旧来源，不需要覆写冻结输入或旧镜像。不得把它标成 latest deployment。
- 下一步实现／核对 Host 端口的 HS 协商与 FS 回退、MAC 时序和固件 MPS，再接 25K MIDI／PL；同时按实际 DAC 型号推进串行时钟、格式与安全启动，不用 USB 电气问题代替这些工作。
- 新板完整构建须另有源清单／配置／输入哈希／新 UserCode／位流哈希／资源与时序报告。只有这些和电气门禁闭合后，才进入独立的实体读回与现象验收。
- 当前**没有**完成整机新板候选、Gowin P&R、板测、SRAM 或 Flash；本清单不替代它们，也不缩小总体目标。
