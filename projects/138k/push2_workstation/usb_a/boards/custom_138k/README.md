# 自定义 138K 底板引脚配置

本目录维护 USB2 USB-A／USB3300 底板的显式网表级引脚配置，不替代已接受的旧 Dock 整机配置。配置身份为 `custom_138k_usb2_20261022_pinout_v2`；日期化来源和验证见[重定位记录](../../reports/CUSTOM_BOARD_PIN_RELOCATION_20261022.md)及[上板前检查](../../reports/CUSTOM_BOARD_PREFLIGHT_20261022.md)，逐脚来源见[网表候选表](../../reports/CUSTOM_BOARD_PINMAP_20261022.md)。

**已知电气阻断：** 原有工程中 U2 为 USB3300-EZK，U4／U5 为 TXS0108E／TXS0104E；当前网表把 PHY 接在两转换器的 1.8V A 侧，而 USB3300 逻辑输入要求 VIH 至少 2.0V。STP 高电平不满足要求，PHY 返回信号也不在 A 侧推荐输入范围内。生成结果显式报告 `electrical_check.status=blocked`，不是硬件已测结论；不能通过修改 FPGA IO_TYPE 或仅改软件解除，须核对实际装配／供电并审查硬件修正。不得把本位置规划用于新板固化。

## 准备命令

从仓库根目录执行：

```sh
python3 projects/138k/push2_workstation/usb_a/build.py \
  --prepare-pinout custom-138k \
  --netlist-dir "$HOME/Documents/fpga补充文档"
```

入口只读 `pinout.json` 指定的三份网表：底板、功放、蓝牙。文件名和原始字节 SHA256 均须匹配；文件缺失、内容漂移、路径逃逸、连接断开或球位冲突会失败，不尝试历史文件或其他底板配置。网表更新须先审查端点与连接变化，再更新配置和测试，不能只放宽哈希检查。

默认新建被忽略的 `usb_a/results/custom_138k_pinout_<时间>/`，也可用 `--pinout-output <不存在的目录>` 指定位置；拒绝覆盖已有目录或把输出放进网表输入目录。产生：

- `custom_138k.locations.cst`：核心板固定约束和新底板端口的 `IO_LOC`；新外设的电气约束尚未实现。
- `pinout.json`：端口／球位、HDMI 极性、蓝牙排线关系、保留脚、假设、电气阻断及缺口；同时记录输入网表、锁定核心板约束、配置和生成工具哈希。型号与电压要求的来源记录在 `electrical_evidence`，不把网表中 `{Value}` 当成型号，也不把名义电压当作实测。

输出是 **`offline_pinout_only`，`synthesis_allowed=false`** 的位置规划，不生成 `.gprj`、位流或可下载整机，不更新 latest／部署索引。不能与 `--prepare-only`、综合、整机来源或发布选项混用；旧板构建命令保持原义和默认输入。

## 映射边界

- 只从 `accepted_full83` 锁定约束读取同一 30354 核心板的 `clk_50m`、调试 UART 和全部 `ddr_*` 固定约束，保留其 `IO_LOC`／`IO_PORT`；这不表示选择 full83 的整机 RTL。
- 功放按底板 `FPC2.n → FPC1.n`，RN1／RN2 按 `1↔8、2↔7、3↔6、4↔5` 配对推导。两项均是待验证假设，不是实体导通验收。映射从底板实际端点取得，不能照抄功放网名中的旧球位：MCLK 为 **D17**、PDN 为 **C17**，而 **B17 已属于 ULPI DATA7**。
- USB2 解析 8 位 DATA 和 CLK／DIR／NXT／STP 的转换器两侧网络，并检查 VCCA／VCCB／OE 和 RESET 的现有连接；不虚构 FPGA 可控 PHY RESET，也不把旧 D+/D− 软 PHY 接口当成 ULPI。
- TF SPI 的 MOSI 为 **W14**；Y16 与 AB15 是保留的其他数据脚。
- HDMI 保持原生合法差分对顺序；四对均记录串行极性补偿需求，不能用交换 `IO_LOC` 正负球位代替逻辑补偿。K14 是 CEC，不再是旧 `hdmi_tx_en`。
- 蓝牙按底板 `FPC3.n → FPC1.(25−n)` 核对 15 根信号和八个电源／地触点。本位置规划仍只记录线序；原生装配另用 `bluetooth.json` 核对自定义 J2 与核心板 C2400 的编号转换及周边锚点，接入 T14／W12／AA9／AA13 四根 UART／使能信号，并选择 `bluetooth.cst`。PCM／SDIO／HOST_WAKE 未新增驱动。
- 旧 Dock 的 `usb1_dp`／`usb1_dn`、`pa_en`、`hdmi_tx_en`、`button1_n`、`midi_rx_i` 不复制到新板规划；不拿功放检测或 PDN 冒充 `pa_en`，不猜新复位按钮。

## 后续整机适配与回退

原生装配必须同时选择 `ddr.cst` 的 PLL、DDRDLL 和 CLKDIV 专用资源位置，并与其他约束合并为唯一有效 CST。DDR 球位和电气属性相同，不能代替这些资源定位；只复制 `IO_LOC`／`IO_PORT` 会丢失官方 DDR 时钟布局要求。该约束进入原生 `a24` 准备身份，不切换 accepted 整机输入。来源、同板 A/B 和整机验证范围见 [DDR 约束修复记录](../../reports/WORKSTATION_DDR_OFFICIAL_AB_20261026.md)。

三项资源定位不是整机初始化稳健性或稳定显示的验收结论；后续已观察到暖重配置前态依赖及显示欠载，当前范围和证据见 [出图后闪烁排查](../../reports/WORKSTATION_HDMI_FLICKER_20261026.md)。

网表已足够推进本阶段位置映射，不以取得整份原理图为前提。尚需完成新板原生顶层／复位和电气约束、USB2 ULPI Host 及 48／60 MHz 域交接、DAC 型号对应的格式／MCLK／启动静音、HDMI 极性补偿与 CEC 安全处理，才能进入综合和 P&R。DAC 的具体型号用于协议适配；不能仅换位置就把旧 `pt8211_tx` 认定为兼容。

外设集成的完整交付清单及 ULPI 开发库进展见 [新板 bring-up 清单](../../reports/CUSTOM_BOARD_BRINGUP_20261022.md)。新库尚未选入整机配置，不能把 PHY 自检 ready 当作 USB High-Speed Host、25K MIDI／PL 或上板验收。

后续 [HS／FS 端口联调](../../reports/CUSTOM_BOARD_USB2_HOST_PORT_20261022.md) 已加入 50 ms 根复位、连续 K/J、FS 回退和实际 25K 核的计时回归。它仍缺 Host MAC／固件与整机接入，不改变本配置的 pinout-only／电气阻断状态。

更新的 [Host MAC 包级进展](../../reports/CUSTOM_BOARD_USB2_HOST_MAC_20261022.md) 已补独立事务引擎及真实 25K 枚举／HS 512 字节、FS 64 字节回环。[原生控制器进展](../../reports/CUSTOM_BOARD_USB2_CONTROLLER_20261022.md) 已进一步完成 PHY＋MAC 同链路仿真、故障隔离与 Gowin 组件综合；仍须接入 CPU／固件并组成完整新板配置，不能当成 MIDI／PL 或实板完成。

[CPU MMIO 进展](../../reports/CUSTOM_BOARD_USB2_MMIO_20261022.md) 增加显式双时钟整包邮箱与第一方有界驱动，不会自动替换旧 FS MMIO／固件。寄存器主机到真实 25K 的仿真仍不等于 VexRiscv、MIDI／PL 或新板整机接入。

[CPU 接入开发快照](../../reports/CUSTOM_BOARD_USB2_CPU_CHECKPOINT_20261022.md) 保留推送时的失败证据；后续 [CPU 实际执行记录](../../reports/CUSTOM_BOARD_USB2_CPU_20261022.md) 已修复启动入口，完成真实 RV32I 的 HS／FS 枚举、回环、取消与恢复及组件综合。[显式 SoC 准备入口](../../rtl/usb2/CPU_SOC.md) 默认仍选择 probe，可另行选择业务固件；两者都不是可上板整机候选，也不改变已接受整机配置。

更新的 [工作站应用记录](../../reports/CUSTOM_BOARD_USB2_WORKSTATION_20261022.md) 增加显式生产固件 profile、原生后端、HS／FS 的实际 25K MIDI／PL CPU 仿真和 Push 软件分包验证。显式 [输入 owner／FIFO 组件](../../rtl/workstation/USB2_INPUT.md) 接入原工作站事件边界；[音频组件](../../rtl/workstation/USB2_AUDIO.md) 继续连接原会话、公共参数、DSP、参考串行链与 delay DMA，分别记录来源和模型范围。组件综合本身不解除本配置的 pinout-only／电气门禁，也不能推导可上板。

另有显式 [`--prepare-custom-board` 原生装配入口](../../rtl/workstation/README.md#显式新板装配)，复用现有整机组合并选择新板位置、USB2 和四对 TMDS 极性补偿；其 prepare／离线综合与本目录位置配置是不同验证阶段。原生入口通过 `workstation_fpc_audio` 驱动 AUDIO→FPC→功放链路，并接入蓝牙业务协议和实际音频短录音／下载；本位置配置单独使用时不因此获得驱动。CEC 释放；完整电气、布局布线、时序和实板验收仍需分别完成。音频实现、蓝牙来源与容量限制见原生入口说明。不得把已编译的整机源码组合误报为已经接通的新板。

2026-10-24 原生整合通过 `peripherals.json` 单独锁定远端验证依据：音频实际采用主板 `FPC2.n` → 功放 `FPC1.(25-n)`，不沿用本独立位置配置的同序排线假设；K18 输入 12.288 MHz，功放 MCLK 为 256fs。原生位置生成先按本配置网表推导，再交叉核对远端约束，并加入 LCD。Push CC71／CC79 或 25K 编码器 1 通过同一 CC7 权威控制最终输出音量，不修改功放 vendor 或另写控制协议。原生合并 CST 和独立 pinout-only 输出不能互换使用；详细来源与未完成验收见[本次整合记录](../../reports/WORKSTATION_INTEGRATION_20261024.md)。

之后分别执行时序／CDC／PLL／资源门禁及实体排线、Push／25K、音频、HDMI 验收，另建具有完整来源和位流哈希的新候选。Push 和 25K 在同一个 USB-A 口交替接入，不假定同时连接或 High-Speed。不得凭本阶段通过执行 SRAM 或 Flash 下载。

本入口不改 `p11.cst`、冻结基线、vendor 或整机 RTL；回退即继续原有显式整机配置，不需要恢复网表、重新刷板或删除历史结果。将来接入原生新板装配时，应保留本配置作为位置权威，并以通过端口覆盖、电气检查和完整物理门禁作为结束 `pinout_only` 阶段的条件。

## 针对性验证

无需外部网表和 Gowin 工具的回归：

```sh
python3 projects/138k/push2_workstation/usb_a/sim/test_workstation_pinout.py
python3 projects/138k/push2_workstation/usb_a/sim/test_current_workstation_sources.py
```

前者验证解析、连接、旧标签冲突、HDMI 原生对、排线关系、来源漂移、输出保护和 CLI 隔离；后者验证已接受的整机输入边界。三份实网表的命令运行与其哈希核对是另外一项证据，不由合成测试替代。
