# 138K USB1 Host ↔ 25K USB2 全速回退

日期：2026-10-29，UTC+08:00。状态：**源实现、数字引脚链路、两板综合和路由时序通过；未操作板卡，未做硬件验收。**

## 结论和修正

连接路线为 `138K USB1 FS Host ↔ 25K USB2/USB3300 Device`，最终速率为 FS 12 Mbit/s。25K 保持双速 USB2 配置，不切到自身 USB1，不新增板间线规，继续使用 USB-MIDI、独立 vendor Bulk 和 PL local-v1 HELLO/CAPS。

不能直接把旧 DA 的电脑端 HS 成功当成这条 FS 路线已兼容。此次使用 DA 原始 127 项输入的冻结快照，复现了真实设备核的复位尾段缺陷：

1. 设备未收到主机高速 chirp 响应，约 10 ms 后进入 FULLSPEED。
2. 同一次主机复位仍保持 SE0，之前累积的 `se0_reset` 立即使设备又进入 WAIT_RST。
3. FS Host 的生产驱动保持复位 11 ms；它在第二轮设备 chirp 前结束复位，设备留在 WAIT_RST，随后不响应枚举。

修正位于 `projects/25k/example/MIDI_KEYBOARD/rtl/usb_board/midi_usb_hs_phy.v`：进入 FS 后必须先观察到 J，才允许新的持续 SE0 再开启协商。原复位尾段仍报告 bus reset，地址/配置/toggle/FIFO 清除不取消；HS 协商及 suspend/resume 路径不改。新增测试在 FS 回退后继续保持 SE0，并覆盖第二次复位；旧测试在复位结束后无条件等待已经经过的 chirp 状态，这一测试时序假设也已修正。

138K 识别固件同时改用既有 minlibc 支持的 `%x/%d`，修复 `%08x/%u` 被原样输出、未消耗参数而无法观察真实身份的问题；实际 CPU 仿真检查 UART 中出现正确身份。

## 最终候选

| 对象 | 新身份 | 业务范围 | 物理 BSRAM | Setup / Hold 最差余量 |
|---|---|---|---:|---:|
| 138K | `C11029F7` | 独立 USB1 识别 Host；不是完整音频工作站 | 36/340 | +6.894 / +0.176 ns |
| 25K | `C12529F2` | 默认完整键盘 USB2 双速配置；不带可选 GAO | 54/56 | +0.020 / +0.184 ns |

两者 setup/hold 违例端点均为 0；138K recovery/removal 为 +6.804/+0.349 ns，25K 为 +4.483/+0.967 ns。保持 138K 的 50/48 MHz 与 25K 的 50/60.002 MHz 约束。25K 物理 Logic 21985/23040、CLS 11384/11520，余量较小，不视为后续整合资源充足。

138K 综合 BSRAM 等效数 34，25K 为 40，**不能与上述物理块数混用**。完整输入、综合网表、固件 ROM 和实际产物由 [汇总清单](usb1_mixed_20261029/verification.json)、[138K 输入](usb1_mixed_20261029/host_inputs.json)、[综合审计](usb1_mixed_20261029/host_synthesis.json)、[物理实验](usb1_mixed_20261029/host_implementation.json)、[25K 构建](usb1_mixed_20261029/peer_build.json) 绑定。

位流均保存在忽略的生成目录，没有加入源码：

```text
projects/138k/push2_workstation/usb_a/results/usb1_host_C11029F7/impl/pnr/usb1_candidate.fs
SHA256 6046b4bc84278137d659572defb1429e172a09de4699b760ce62f9c807bbef0d

projects/25k/example/MIDI_KEYBOARD/results/usb2_fs_fallback_C12529F2/impl/pnr/midi_keyboard.fs
SHA256 ebbb572f7541c1e51917e659f41b2adea659ba1648ca420e2a5ea068e6ab0aef
```

## 验证范围

| 验证 | 结果与边界 |
|---|---|
| USB1 定向套件 | 6 项执行通过、1 项外部快照测试默认跳过；另单独选择新 25K 构建快照通过该项 |
| 双速设备 FS 回退 | 402 checks；复位尾段、重新枚举、64B、描述符、CRC/重试、halt、挂起/恢复及会话清除 |
| 原 USB1 FS-only 设备 | 386 checks，保留两板 USB1 的既有路线 |
| 混合数字 D+/D− 链路 | 真实 RV32I/生产枚举和 MIDI/PL 固件 → FS MAC/NRZI/CRC → USB3300 行为模型 → 真实 boot/ULPI wrapper/双速设备核/PL endpoint |
| 链路应用与会话 | 两次接入、256 条 MIDI、HELLO/CAPS、每会话至少两块 tile；背压稳定、拔出取消旧事件、重连无旧身份/ready 复活；25K 拔插时不复位 FPGA |
| 最终冻结输入 | 新 `C12529F2` 全部 136 项原始/快照输入校验，使用其冻结 USB2/PL 源重新执行混合链路；Host 仿真二进制与最终综合 ROM 对应的固件完全一致 |
| 旧 DA 负向复现 | 原 127 项输入完整核对，混合链路停于 WAIT_RST；新复位尾段断言在原设备 RTL 上失败，不修改历史输入 |
| 完整键盘 | 43 个 RTL testbench、100 项检查及其中的 50 个 Python 用例通过，HS/FS、BLE ROM 拒绝、控件、显示与引用完整性保留，输入全程未漂移 |
| 约束/复位 CDC | 5 项通过；首级匹配缺失/歧义拒绝、三级释放结构检查、停钟/异步锁定丢失与三拍恢复 |
| 来源与固件边界 | accepted 来源 10 项、固件 staging 6 项、最终 profile 检查 2 项通过 |

细项：[混合链路](usb1_mixed_20261029/mixed_pair.json)、[冻结候选链路](usb1_mixed_20261029/frozen_peer_pair.json)、[原 FS-only 链路](usb1_mixed_20261029/fs_pair.json)、[旧 DA 负向证据](usb1_mixed_20261029/old_DA_negative.json)、[完整键盘](usb1_mixed_20261029/keyboard_regression.json)。

USB3300 为定向行为模型，支持本测试需要的寄存器、DIR/NXT/STP、FS 包和线态；设备 chirp 的模拟电流/电压及 HS 波形没有模拟。48/60/50 MHz 时钟独立，FS 两端约 96 ppm 相对偏差。LCD tile 完成由模型确认；不是真实屏幕、触摸、音频或无线并发验收。

## 构建和时序边界

138K 复用现有 `build.py --usb1-identify --usb1-board 138k --synthesis-only` 和锁定 PLL/vendor 输入。综合网表审计现要求三个输入首级 DFF 各自唯一命中约束，适配实际 `phy_0` 实例名；没有把输入例外扩大到第二级采样。三级 `release_q` 的异步 CLEAR 具有专用、仅限三个端点的异步控制例外；PLL 辅助状态及 power-ready 的异步解除允许在链内吸收，不把它伪装成同步输入。审计核对三级初始化、常数一、共时钟/共 CLEAR 和串联，停钟复位测试验证其契约；后级数据与复位输出时序继续检查，无异步时钟组。

138K P&R 是**非默认的独立识别实验**：从已封存 synthesis Tcl 原样选取器件/options，以实际综合网表和原 CST/SDC 单独运行 P&R，不重新综合。精确 Tcl、命令及哈希保存在物理实验 JSON；标准 CLI 仍只提供 prepare/synthesis。它不成为 sole production 输入；若要正式可部署 USB1 profile，需将同等门禁迁入现有入口的显式 flow，或在完整原生工作站 USB1 集成后退休本实验。

25K 使用原 `tools/gowin_build.py build.tcl --user-code C12529F2` 和默认完整业务，不选择 `MIDI_USB1_FS`。首轮可选 GAO 观察版 `C12529F1` 因 6 条未布通网络被拒绝，未当作通过；最终 F2 不带可选 GAO，但 BLE、LCD、触摸、灯光、MIDI/PL 保持。未为通过而放松时钟或删业务。

138K F1/F2 是中间综合候选；F2 的初次 P&R 发现未命中的首级约束，F3–F6 继续识别复位同步器的异步控制边界，均未当作路由时序验收。最终 F7 使用新身份和完整审计。厂商/普通时钟路由 warning 保存在清单，不把它们或未执行的物理 PLL/电气门禁改为通过。早期键盘/USB1 回归还暴露了上述旧测试等待假设；最终稳定输入完整重跑通过，失败记录保留。

复现入口见 [USB1 README](../rtl/usb1/README.md)、[25K FS 回退说明](../../../../25k/example/MIDI_KEYBOARD/docs/USB2_FS_FALLBACK.md)。重跑构建使用新输出目录及新 UserCode，不覆盖本轮证据或复用已接受身份。

## 上板前置与回退

- 138K 使用新底板 USB1，D+ H13、D− G13；不是尚未调通的 USB2/USB3300。25K 继续使用 USB2/USB3300 的实际数据口。
- 138K USB1 锁定网表的 CC1/CC2 为 5.1kΩ Rd，VBUS 经 F1 连 +5V；Host 角色、CC、供电及防反灌仍必须核查，不能直接假定 C-C 接线成立，也不授权改电阻/供电。
- 25K USB2 的上拉/端接由 USB3300 控制，不套用 25K USB1 软 PHY 的外加 D+ 1.5kΩ 要求。其 USB3300 供电及 60 MHz CLKOUT 启动仍是独立门禁，协议修正不能修复失钟。
- **本轮没有访问 JTAG、UART 实物端口、USB 实物设备，也没有 SRAM 下载、Flash 写入或配置重载。** 不把历史 DA/E5 记录当成本轮板上身份读回；所有硬件/部署许可字段保持 false。
- 本轮没有改变 accepted full83/timing85/resource-timing、部署指针或板上配置，无需板卡回退。后续若授权 SRAM 实验，应先独立读回身份并保留原镜像；不得把这个不含音频/DDR/HDMI/CNN 的 138K 独立识别顶层当成完整工作站发布。

下一阶段是确认电气/接线后，单独授权并验证实际 FS 枚举、PL ready、双向 MIDI、连续传输、拔插及冷启动；完整 138K 音频/公共参数 owner 接入和 Flash 发布仍是另外的集成/验收阶段。
