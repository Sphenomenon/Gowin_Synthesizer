# 新板 USB2／USB3300 Host 链路

这是自定义 138K 的显式开发源码，不是已接入整机的 USB High-Speed Host。旧 `--current-workstation`、`--cnn-timing85`、`--resource-rework --resource-timing` 的输入策略均未改变，`--prepare-pinout` 仍只准备位置约束。完整目标见 [bring-up 清单](../../reports/CUSTOM_BOARD_BRINGUP_20261022.md)，后续 Host 端口与 25K 联调的当前证据见 [HS／FS 协商报告](../../reports/CUSTOM_BOARD_USB2_HOST_PORT_20261022.md)。

## 模块与时钟

| 模块 | 职责 |
|---|---|
| `workstation_ulpi_link.sv` | 60 MHz ULPI 总线换向、CSR 读写、UTMI 字节接口、背压、RXCMD、超时与抢占分类 |
| `workstation_usb3300_host_init.sv` | 身份检查、Host 物理配置与逐项读回、Scratch 自检、有界重试及失败步骤 |
| `workstation_ulpi_supervisor.sv` | 独立参考时钟监测 PHY 时钟存活、STP 高电平恢复窗口、停钟复位及显式重启 |
| `workstation_usb3300_host_link.sv` | 以上三者的原生组合，初始化独占 CSR，成功后转交运行期 CSR／UTMI 客户端，失败时禁止 DATA 驱动并拉高 STP |
| `workstation_usb2_host_port.sv` | 初始化后的 PHY 配置唯一拥有者；接入去抖、50 ms 根端口复位、设备 K 过滤、连续 Host K/J、排空后切换 HS、FS 回退、恢复／断开／软件复位 |
| `workstation_usb2_host_phy.sv` | 六模块平台组合，将 CSR 交给端口状态机，按所有权在 chirp 与 MAC 间交接 UTMI，失败时拉高 STP／释放 DATA |

`clk_ref` 预期 50 MHz，`enable_i` 在此域。`clk_ulpi` 为 USB3300 提供的 60 MHz。除了 `clock_running_o`／`clock_present_o`／`clock_failed_o`／`clock_failure_code_o`，组合模块的 CSR、UTMI 和诊断数据均在 ULPI 域。`ready_o` 可因复位／停钟异步撤销；它不是可以直接采入另一个域的多字节状态快照。

参考域 `reset_n` 须来自异步置位、参考域同步释放的复位源。心跳计数器的复位独立同步到 ULPI；ULPI 链路的释放另经两级同步。心跳仅将分频计数器最高位跨域，经两级寄存器同步，不直接采样运行中的多位计数器。这里验证的是时钟存活，不是 60 MHz 频率精度或已完成的整板 CDC／恢复移除时序验收。

默认先保持 STP 高 500 个参考周期（10 µs），再收集 8 次心跳变化，释放链路复位后等待 600 个 ULPI 周期（10 µs）才访问寄存器。停钟门限为 5,000 个参考周期（100 µs，另计同步／状态机延迟）。丢钟后即使没有 ULPI 边沿也可撤销 OE 并置位复位。故障锁存后不会因时钟重新出现而自动重试，须在参考域关闭再开启 `enable_i`，或复位。

这不是 USB3300 硬复位驱动。新网表 U2.9 RESET 接地，不能凭软件需要增加不存在的 FPGA RESET 端口。STP 恢复路径也不替代新板电平转换器电气修正和实体确认；见 [电气预检](../../reports/CUSTOM_BOARD_PREFLIGHT_20261022.md)。

## ULPI／UTMI 契约

- DATA OE 受当前 DIR 立即屏蔽，DIR 下降后的一个换向周期不驱动。复位期间 STP 为高、DATA 高阻，运行空闲 DATA 为 `00`。
- CSR 是单请求／单应答接口，valid／ready 握手。请求受阻时保持地址、数据和读写方向；应答在被消费前保持。空闲时 CSR 优先于新 TX；不抢占已启动的包。读取的换向、数据及释放阶段不计为 USB RX 或 RXCMD。
- 普通 UTMI TX 的第一个字节是完整 PID，链路将其低四位组成 ULPI TX command，并仅在 command 被 NXT 接受时消费这个 PID。后续字节由 NXT 背压。`utmi_tx_nopid_i=1` 则发送 `40h`，不把第一个 payload 当作 PID 消费；它只提供将来 chirp 所需的物理能力，不实现 chirp 时序。
- 发送客户端必须在接受前保持 valid／数据，包内不得出现气泡。最后一个字节握手后撤销 valid，链路在同一结束周期输出 STP 和 `00`，不依赖 NXT 再接受一个零字节。传输中撤回尚未接受的 command 视为致命取消。
- RX 没有可反压 USB PHY 的 ready。RXCMD 单独更新线态、VBUS、ID、RX active／error 和 host-disconnect；NXT 数据逐字节交给客户端。后续 MAC 必须有足够 FIFO，并定义溢出、坏 CRC、取消和包提交／回滚规则。这里不替 MAC 实现 CRC／重传、端点、地址或接收包长度检查。
- 字节计数和 RXCMD 计数饱和，不回绕。普通 TX 计数含消费的 PID；NOPID 不计 command，只计实际 payload；CSR 不计入 RX／TX 字节。514 字节回归说明传输接口可承载该长度，不等于已验证 512 字节 HS USB 事务。

链路错误码：`0` 成功，`1` 当前事务总时限到达，`2` PHY 抢占，`3` 读取在数据阶段异常撤销。只有 command 尚未接受且 `fatal_error_o=0` 的错误 2 可重试；写数据／结束阶段被抢占、读中止和超时锁存 fatal。已消费 PID 后的 TX 被抢占，输出 `tx_abort_o` 并锁存 fatal，不自行重放包尾。

单链路默认常规事务总时限 60,000 拍（1 ms）。连续 NOPID chirp 另有 `NOPID_TIMEOUT_CYCLES=3,600,000`（60 ms）上限，允许覆盖 50 ms 根端口复位；没有放宽普通包／CSR 的 1 ms 看门狗。初始化步骤总时限 120,000 拍（组合模块默认）；步骤时限包含 CSR 受阻和重试，不因重试刷新。初始化最多重试 3 次安全抢占。所有时限参数须为正整数，`HEARTBEAT_WIDTH`／`QUALIFY_EDGES` 须为正，`MAX_PREEMPT_RETRIES` 支持 0–255；心跳分频须低于参考域可采样的频率。

组合模块发生 fatal、初始化失败或时钟失败时，立即撤销 ready，拉高 STP 并禁止 DATA OE。**ready 撤销／fatal 是运行期事务的显式取消边界**，未完成 CSR 或 TX 不再保证产生成功应答；客户端必须丢弃未完成事务并按显式恢复流程重新开始。运行期 fatal 到初始化失败寄存器有一个 ULPI 周期延迟，不能等待该寄存器才停止驱动。诊断寄存器不是运行期 PHY 配置的权威影子；运行期配置变更后须由所属端口控制器实际读回。

## 初始化步骤与可观察状态

依据 Microchip USB3300 DS00001783C 的寄存器与 Host 章节；初始化从不访问 `30h–3Fh` 保留区，不控制不存在的板上 VBUS 开关。

| stage | 操作／读回要求 |
|---|---|
| 0–3 | `00h–03h` 读回 `24 04 04 00`，即 VID `0424`、PID `0004`；任何错误都在首次写配置前终止 |
| 4–5 | Function Control `04h` 写／读 `49h`：时钟保持、FS、non-driving |
| 6–7 | Interface Control `07h` 写／读 `10h`：ULPI、保留 Host AutoResume，关闭旧串行／carkit 模式 |
| 8–9 | OTG Control `0Ah` 写／读 `06h`：DP／DM 下拉，禁止内部 VBUS 充放电与外部驱动请求 |
| 10–15 | Scratch `16h` 逐组写／读 `55h`、`AAh`、`00h`，最终清零 |
| 16–17 | Function Control 写／读 `41h`，交接到 power-up 初态；完整端口控制器随后写／读 `45h`，才进入正常 FS Host 接入检测 |

初始化失败时固定保留 offending stage、最后读回值／CSR 错误、读到的身份和配置。失败码 `1` 链路 fatal、`2` 步骤时限、`3` 其他 CSR 错误、`4` 身份不符、`5` 配置／Scratch 不符、`6` 重试耗尽、`7` 非法状态。成功后的 stage 固定为 17，CSR 静止并转交运行期客户端。

**host_link 的 ready 只表示物理链路及上述读回完成**，不表示 VBUS／设备接入／枚举／Host 复位／480 Mbps 协商／MIDI／PL 或 Push 已完成。后续 `host_phy` 已接入下述 HS／FS 端口状态机；125 µs microframe 的实际 SOF 包、SIE 的 HS 定时／CRC／重传、512 字节事务及 25K MIDI／PL HS 接入仍须实现，不能把旧 FS Host 的时钟参数改成 60 MHz 就算完成。

## Host 端口与 MAC 交接

`host_phy` 内部的 CSR 唯一拥有者是端口控制器，不向 MAC 公开一条可并行改 PHY 配置的 CSR。初始化读回 `41h` 后，端口写／读 Function `45h`，读取 Debug `15h` 的当前 LineState 作为初值，再消费 `rxcmd_valid_o` 提供的新鲜状态；不以饱和计数器是否变化判定状态是否新鲜。

- 默认连续 J 接入去抖 100 ms；接入抖动重计时。LS 显式报告 `unsupported_low_speed_o`，不冒充 HS／FS，也不执行 HS 协商。
- 写／读 `50h`（XCVR=HS、TERM=0、OpMode=raw）开始至少 50 ms 根端口复位，DP／DM 下拉与 VBUS 控制保持初始化配置。设备 K 连续至少 2.5 µs 才有效；设备 chirp 必须在 T0+7 ms 内结束。没看到有效 K、或本轮复位开始时禁止 HS，均保持 SE0 后回到 `45h`，不假报 HS。
- 有效设备 K 结束后，发送一个连续 NOPID train，`00h` 为 K、`FFh` 为 J，每段 50 µs，至少 KJ KJ KJ，直到根复位结束前 100–500 µs 才停止；不会在各段之间插 STP／Idle。开始发送受阻超过 90 µs、或已经开始的 raw train 出现 NXT 背压，都显式失败，不伸长 chirp 掩盖时序问题。
- 停止 train 后必须收到新的 SE0 RXCMD，才写／读 `40h` 切换正常 HS；排空等待上限 90 µs。复位总时长到达后才放开 SOF。普通事务还要再等 10 ms recovery；这 10 ms 内 MAC 必须实际发送 SOF，不能把 `sof_enable_o` 当作已经发了 SOF 包。
- HS 断开取 PHY host-disconnect；FS 断开过滤至少 2.5 µs 连续 SE0，避免把 EOP 当拔线。断开与开始复位输出 `session_reset_o`，待 Host 固件／会话适配消费；没有改动 18-bit 事件布局，也没有凭空加入 session 元数据。
- 软件复位请求先关闭新 SOF／事务的调度许可，保留 MAC 对已开始包的拥有权，等 `mac_idle_i` 后再改 PHY；等待超过 1 ms 失败。上层 MAC 必须将调度许可与在途包 valid 分开，不能在一个包中途撤销 valid。

`mac_reset_n_o` 在复位协商期间保持低，进入 recovery 后释放，以允许先发 SOF；`traffic_enable_o` 再晚 10 ms 放开。HS 已选定但 recovery 尚未完成时，`high_speed_o` 也不代表可以开始枚举或 MIDI／PL。所有 MAC 接口在 60 MHz 域，旧 Host MMIO／CPU 的时钟与复位桥仍待显式适配。

端口状态可由 `state_o` 定位；错误码 `1` PHY fatal／TX abort，`2` CSR 错误或重试耗尽，`3` CSR 总时限，`4` Function 读回不符，`5` chirp 开始超时，`6` raw train 背压，`7` drain 状态超时，`9` 非法状态，`10` MAC 无法静止。最多重试 3 次安全 CSR 抢占，不因重试刷新时限。`failed_o` 必须用于 DATA OE／STP 安全隔离，完整 `host_phy` 已落实该连接；独立使用端口模块时不能漏接。

## 复现与集成边界

在仓库根目录执行：

```sh
python3 projects/138k/push2_workstation/usb_a/sim/test_workstation_ulpi_link.py
verilator --lint-only -Wall --top-module workstation_usb2_host_phy projects/138k/push2_workstation/usb_a/rtl/usb2/*.sv
source_root="$PWD/projects/138k/push2_workstation/usb_a/rtl/usb2"
validation_dir="$(mktemp -d)"
(cd "$validation_dir" && yosys -Q -T -p "read_verilog -sv $source_root/*.sv; hierarchy -check -top workstation_usb2_host_phy; synth -top workstation_usb2_host_phy; check -assert; stat")
```

物理总线模型独立观察 DATA/OE/DIR/NXT/STP，不强制 DUT 内部状态。覆盖 256 种 Scratch 数据、256 种 RX 字节、RXCMD、514 字节 TX、NOPID 独立超时、NXT 背压、换向、读写抢占／时限、初始化逐项读回、坏 ID／配置／Scratch、步骤受阻、显式重启、缺失／停止时钟及真实组合交接。端口快速故障矩阵缩放计时；另有真实 60 MHz／50 ms 根复位／10 ms recovery 的六模块组合，与仓库 25K CDC 设备核实际协商 HS／FS，不能以快速矩阵替代真实计时。

25K 第一方 CDC 适配增加 HS 3 ms 空闲判定及复位后 100 µs FS 检查窗口，修复上游短 SE0 计数器误伤合法 100–500 µs chirp 尾段的问题。对应控制回归还验证地址／配置跨 500 µs HS 空闲保持、512 字节真实 SIE 事务、3 ms HS 热复位及重新读描述符。vendor 字节与原始清单不改，测试也核验其锁定哈希。

协商联调中的电气连线／差分线态与 SOF 保活活动由独立模型抽象，不是模拟信号完整性或 Host 发包／枚举证明。设备侧控制测试使用真实 token／PID／CRC／ACK 路径，但不能反向证明 138K Host SIE 已完成。完整 suspend／resume、LPM、USB 电气合规也没有因此通过。

集成时只能在显式新板配置中选入这四个第一方模块。60 MHz CSR／UTMI 不得直接接原 48 MHz Host；须使用明确的时钟迁移或异步桥，并验证超时、取消、FIFO 深度和复位。不得更改 vendor、冻结基线或旧部署身份。完整时序、原生新板组合根、I/O 电气约束、Gowin 综合／P&R、USB 协议和实体调试均是后续门禁，不被上述通用综合或仿真替代。
