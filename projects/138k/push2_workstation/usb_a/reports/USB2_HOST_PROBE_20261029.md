# 138K Host ↔ 25K Device：独立探针与 SRAM 实测

日期：2026-10-29，Asia/Shanghai。

## 当前结果

用户已将两板连接，并明确授权编写、综合和下载 138K 探针。本次只下载 138K SRAM；未写任何 Flash，未操作 25K JTAG。

19:05:23 完成 `C11029AB` 的 SRAM Program and Verify，随后用独立 Read Device Codes 确认 `GW5AST-138C / 0x0001081B / 0xC11029AB`。

**138K 已枚举并识别 25K，当前运行在 USB Full-Speed（12 Mbps），不是 High-Speed（480 Mbps）。** 两次独立 GAO 采样均显示 CPU 提交了 `connected=1 / generic_midi=1 / gw25k=1`，CPU fault、端口故障、初始化故障和 OUT 错误均为零。此结论来自当前 SRAM 的实际板间通信，不是仿真或旧镜像计数。

19:05–19:12 的前四次采样中 MIDI 事件数仍为 0。22:05:55，用户安装并操作 25K 触摸板后再次采样，真实 MIDI 接收事件计数已增长到 **1135**，确认输入已到达 138K。该值来自 CPU 侧 MIDI 事件计数，不是 PHY 接收字节。当前结果覆盖枚举握手和 MIDI 输入，不宣称 480 Mbps、音频或 HDMI 验收。

## 候选与来源

候选目录：

```text
~/.cache/fpga-usb2-hdmi/138k-host-c11029ab-20261029_190220/
```

- 入口：`tools/workstation_usb2_host_probe.py`，复用既有 headless hotplug 的原生 USB 控制器、USB CPU、生产枚举／GW25K 固件和输入适配器。
- 顶层：`workstation_usb2_hotplug_top`。没有复制整机工程，没有切换 accepted profile；不含 HDMI、DDR、DSP、CNN 或 BLE。
- 参考／ULPI／CPU／事件域时钟分别为 50／60／48／76.8 MHz；允许 HS 协商及 FS 回退，不使用 `WORKSTATION_USB2_FORCE_FS`。
- ULPI 球位不变：CLK C18，DATA A21/B21/A20/B20/A19/A18/B18/B17，DIR F16，NXT D16，STP E17；旁路使用 LVCMOS33，C18 `PULL_MODE=NONE`。
- 锁定网表 SHA-256：`deff91f6c48be8d66241e32107b88f7eea47ad2bf6c5b607b139c4b85c33a121`；未修改外部网表。
- 原生输入清单 SHA-256：`61a1ca66cbc76d1c0bb341477b01e6683c69883e887a58c088ebba5d7c20a76c`。
- 实际下载位流：`impl/pnr/ao_0.fs`，SHA-256 `a7508a1ea8f3215745e6a15df731a6eb6b2f259baf41cc044b0ae68e4dd3161b`。GAO CRC 与 UserCode 绑定为 `29AB`。
- `host_probe_inputs.json`、原生清单及 `host_probe_audit.json` 保存逐文件来源、配置、输入哈希和检查器身份；下载前再次检查冻结输入与位流哈希。

25K 保持此前记录的 `C12528DA` Flash 固件。本次核对了原记录的清单及位流哈希，但没有通过当前 JTAG 重新读取 25K UserCode。对应位流 SHA-256 为 `61af877c9a7883e28e36fd28bb3fb038d978ee4f7d9b5b01629300388da4778b`。

## 时序修复与离线检查

本次修复落在原生模块，不修改冻结基线或 vendor 文件：

- MAC 预译码发送字面量／负载选择，并注册发送有效状态；同步 BSRAM 读取和 NXT 受理时刻不变。
- 增加内部包尾提示，预先生成注册 STP；不增加普通 USB 数据字节延迟。NOPID chirp 结束最多增加一个 ULPI 周期。
- 端口正常通信／chirp 状态在同一状态迁移中注册，避免组合状态译码直达引脚。
- 参考域 MAC 故障锁存不再直接形成 ULPI 引脚数据路径；保留异步关闭、同步释放保护。汇总故障信号异步置位 STP 输出寄存器，时钟停止时仍能拉高 STP。
- 实际 SDC 包含 USB3300 输入 max/min 5.5/1.5 ns、输出 max/min 5.5/−0.5 ns，与原有时钟、CDC、PLL、复位检查合并。未降低时钟或添加整域 false path。

最终路由：19:02:21–19:04:27，约 126 秒。STA 最差 setup/hold/recovery/removal 为 **+0.081/+0.175/+4.973/+0.250 ns**；无负路径，ULPI Fmax 60.291 MHz。`host_probe_audit.json` 为通过。前面的未闭合或准备失败候选均未下载，部分补丁准备不完整的 `C11029AA` 构建已中止。

离线验证：

- `sim/test_workstation_usb2_host_probe.py`：9/9。
- `sim/test_current_workstation_sources.py`：10/10。
- `sim/test_workstation_usb2_hdmi.py`：16/16，既有 HDMI 构建／来源检查保持通过；不表示本探针包含 HDMI。
- 最新原生 Host + 实际 25K 设备核协议仿真：HS 1146 项、FS 266 项检查通过；包含描述符、地址、配置、512/64 字节 bulk、真实 SOF、故障后恢复和停钟时引脚保护。
- `PhysicalLink` 定向回归：监督器 223 项／4 场景，物理链路 3115 项／5 场景，HS/FS 端口 23830 项／16 场景，全部通过。
- 快速协议仿真证据：`~/.cache/fpga-usb2-hdmi/host-pad-protocol-regression-20261029_190247/validation.json`；源文件执行前后哈希一致。

## SRAM 与双核 GAO 证据

候选内 `sram-deployment/` 保存下载命令、完整编程／校验日志、写前 `C11029D8` 身份、写后独立 `C11029AB` 身份和 `deployment.json`。实际写入操作为 `operation_index 4`，未执行 Flash 命令。

core0 在原生 ULPI 域采样，core1 在 CPU 域采样，各 1024 点；两核不是跨域原子快照。每次 GAO 前后都独立读取当前 FPGA 身份，完整 CSV 和哈希保存在：

```text
capture-20261029_190533/result.json
capture-20261029_190634/result.json
```

两次采样间隔约一分钟：

| 指标 | 首次 | 第二次 |
|---|---:|---:|
| attempts | 1 | 1 |
| port_state | 16（ACTIVE） | 16（ACTIVE） |
| high_speed | 0 | 0 |
| connected / traffic_enabled / phy_ready | 1 / 1 / 1 | 1 / 1 / 1 |
| received_peak | 31,860 | 126,027 |
| transmitted_peak | 2,963,145 | 3,358,895 |
| sof_peak | 11,967 | 72,762 |
| CPU 毫秒 | 12,277 | 73,068 |
| GW25K / generic MIDI | 1 / 1 | 1 / 1 |
| MIDI received_events | 0 | 0 |
| CPU fault / OUT errors | 0 / 0 | 0 / 0 |

峰值计数是自当前 SRAM 全局复位以来**单次尝试的最大值**，不是尝试累计之和；本次 `attempts=1` 且故障历史为零。IN 诊断字 `0x00ff0000` 表示空闲 IN NAK 计数已饱和，duplicate、传输错误和断开计数均为零，不是故障码。

19:10:03 第三次采样 `capture-20261029_191003/result.json`：CPU 毫秒 282,213，仍为同一次连接尝试，FS ACTIVE、GW25K 识别和无故障状态不变；RX/TX/SOF 峰值增长到 450,000／4,720,436／281,922。MIDI 事件仍为 0，等待用户触发输入。

19:11:57 第四次采样 `capture-20261029_191157/result.json`：CPU 毫秒 396,424，连接仍为第一次尝试，无任何新增故障；RX/TX/SOF 为 626,903／5,463,956／396,140，MIDI 事件仍为 0。复核当前冻结输入、实际下载位流与审计哈希、SRAM 编程校验、采样前后 FPGA 身份以及两核 CSV 后，确认本轮“138K Host 与 25K Device 实际 USB 握手通信”目标已在 FS 下成立。候选内 `goal_completion_audit.json` 记录逐项证据；不将其扩展为 MIDI 按键或 480 Mbps 已通过。

## 触摸板 MIDI 输入实测

用户安装并操作 25K 触摸板后，22:05:55 采集 `touchpad-midi-20261029_220555/result.json`。采样前后独立读取 FPGA 身份，均为 `0x0001081B / C11029AB`，没有重新综合或下载。

- CPU `received_events=1135`，相对此前的 0 已增长；`enumeration_verified=true`，`application_communication_verified=true`。
- `connected=1 / generic_midi=1 / gw25k=1`，CPU fault、OUT errors、端口故障和初始化故障均为 0。
- `attempts=1`，仍是本次 SRAM 启动后的同一次连接；CPU 毫秒为 10,834,200。
- `high_speed=0`，仍为 FS。RX/TX/SOF 峰值为 17,254,623／78,394,703／10,834,643。
- IN 诊断字仍为 `0x00ff0000`：空闲 NAK 已饱和，传输错误、duplicate 和断开计数为 0。
- 本次采样保存事件总数，未捕获逐条音符／力度／CC 内容，不据此推断具体 MIDI 消息类型。

## 为什么当前回落为 FS：HS 热复位计时复现

22:11–22:17 检查当前候选和 25K 已部署 DA 的冻结输入。138K 准备清单 `high_speed_allowed=true`，backend 初始化 `allow_high_speed=1`，不是构建时强制 FS。板上历史包含 CHIRP_START／STREAM／DRAIN／HIGH_SPEED_TAIL 和 FULL_SPEED_RESET，最终 Function Control 为 `0x45`、`high_speed=0`。历史位图不提供状态先后时间戳，不能单凭它认定完整的两板复位波形。

发现并用 DA 原始 PHY 源码复现一个确定的热复位窗口冲突：

1. 138K 原生端口启用时已经执行复位／速度协商；生产 `firmware.c:311` 在 `connect()` 检测到设备后仍会再次调用 `usbhw_reset()`。
2. DA 设备在 HS 无活动约 3 ms 后进入 HS_SUSPEND，恢复 FS 终端并等待约 125 us；随后进入 WAIT_RST 时又将 `usb_rst_time_q` 清零，重新等待 3 ms 才发设备 K chirp，持续约 1.1 ms。
3. 当前 138K 端口的 DEVICE_CHIRP 窗口为 7 ms，必须在这个窗口内完成 K 的资格检查并看到其返回 SE0；超时进入 FULL_SPEED_RESET。

独立 Verilator 定时复现使用已部署 DA 清单绑定的 `midi_usb_hs_phy.v`，SHA-256 `00ac7e281990c0fe18e4b2b4d5c590fa6cbaa5b6896c56fe8bfdec0df94e0445`，不是当前已发生修改的活动文件。当前 138K 候选内的端口源码也与活动源码做了哈希比对。

| 从该次总线复位开始计时 | 设备 K 开始 | 设备 K 结束 | 对 138K 7 ms 窗口 |
|---|---:|---:|---|
| 冷启动复位 | 2,999.888 us | 4,099.844 us | 及时 |
| 已在 HS 后热复位 | 6,124.797 us | 7,224.753 us | 结束晚约 225 us |

证据目录 `~/.cache/fpga-usb2-hdmi/hs-reset-timing-20261029/` 保存 bench、编译日志、运行日志与 `verification.json`。该实验复现的是实际 DA 设备状态机的定时冲突，并与当前 Host 源码窗口核对；本轮没有重新下载，不把它冒充新采集的两板同步复位时序。

修复方向是使原生 Host 初次连接不重复执行已经完成的端口复位，并修正 25K HS 热复位重复计时，使今后的真正热复位也能重新协商 HS。仅取消 FS 回退或把状态标志硬置为 HS 都不是修复。现有 138K SRAM 和 25K Flash 保持不变。

## 后续与回滚

1. 触摸板触发后的真实 MIDI 输入已验证；若需要进一步区分音符、力度和 CC，可增加逐条事件观测。
2. HS 480 Mbps 尚未在当前连接上成立，需另按 chirp／速度切换证据调试，不能将当前成功的 FS 枚举等同于 HS 验收。
3. 后续 HDMI／整机集成使用新候选和独立路由／板测，不把探针冒充完整工作站。

本次 SRAM 下载前的 `C11029D8` 回滚位流：

```text
~/.cache/fpga-usb2-hdmi/138k-device-c11029d8-20261029_155037/impl/pnr/ao_0.fs
SHA-256 a5c95b7a91ab17dbf4cfafe37469bbe502fc0455a1f12dd06f14ad64f74b848a
```

138K 原有 Flash `C11028E5` 没有改写；断电后仍按 Flash 启动，不会保留本次 SRAM 探针。
