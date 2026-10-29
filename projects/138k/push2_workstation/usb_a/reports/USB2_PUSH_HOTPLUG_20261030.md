# Push HS 热插拔：恢复与重试观察

日期：2026-10-30，Asia/Shanghai。继续使用 138K 原生 headless USB Host 探针，Push 接 138K USB-A，JTAG 在 138K；不构建完整音频／HDMI 工作站。前序提交为 `765a476`，前序失败记录见 `USB2_PUSH_RECOVERY_20261029.md`。

## 旧 AC 已能识别实际 Push

00:05:07 读取原 SRAM `C11029AC`，独立身份检查通过。此时端口已为 ACTIVE、`high_speed=1`、Function Control `0x40`；CPU connected=1、generic MIDI=0、GW25K=0、fault=0，收到事件计数为 14559。00:07:26／31 再读仍为 HS，事件增长至 15583／15623，out_errors=0，attempts 始终为 744。原先“未枚举”的快照不能再当作当前状态；同一旧镜像后来自动重试建立了 HS。

原始捕获位于：

```text
~/.cache/fpga-usb2-hdmi/138k-host-c11029ac-20261029_222154/capture-20261030_000504-push-resume/
~/.cache/fpga-usb2-hdmi/138k-host-c11029ac-20261029_222154/capture-20261030_000722-push-stability1/
```

第二个路径的实际窗口时间以目录内 `result.json` 为准；00:07:26 为捕获完成时间，不能把它解释成精确连接时刻。

## 用户拔插一轮

用户按提示拔下 USB、等待约 5 秒后插回；连续 30 个 JTAG 窗口均在原 AC 下采集，未下载程序干预本轮插拔。

| 捕获完成时间 | 端口／枚举 | attempts | received_events | out_errors |
|---|---|---:|---:|---:|
| 00:13:05.253 | ACTIVE，HS，Push 已枚举 | 744 | 18095 | 0 |
| 00:13:09.505 | WAIT_ATTACH，CPU 未连接 | 746 | 18121 | 1 |
| 00:13:13.864 | CHIRP_STREAM，CPU 未连接 | 755 | 18121 | 1 |
| 00:13:18.286 | ACTIVE，HS，Push 已枚举 | 755 | 18197 | 1 |
| 00:14:56.271 | ACTIVE，HS，Push 已枚举 | 755 | 18923 | 1 |

捕获证明断开后重新枚举为 HS，MIDI 计数恢复增长；不是 FS 回退。断开时 out_errors 增加 1，重连后的观察窗口没有继续增加，CPU fault 始终为 0。attempts 增加 11，说明仍有重复启动，不能称为一次协商即恢复。采样间隔约 4.3 秒，尚不能给出插入至枚举的精确延迟。

计数语义补充：`attempts` 统计 PHY ready 上升沿；后端在没有连接时也按 400 ms 启动超时、100 ms 重试间隔重新使能 PHY。因此上述 11 次启动包含拔线期间的空口轮询，不能直接解释成 11 次 Push HS 握手失败。

证据目录：

```text
~/.cache/fpga-usb2-hdmi/138k-host-c11029ac-20261029_222154/push-hotplug-monitor-20261030_001249/
```

每窗均有写前／写后身份、两核 CSV 和 `result.json`；`summary.jsonl` 汇总窗口。两核不是跨域原子快照，SOF／收发 peak 仍是单次尝试的历史峰值，不可当作本轮新会话累计值。

## 三核诊断的时序修正

不改变复位等待、chirp 时长、60 MHz ULPI、IO delay 或任何时序例外，只去除已由异步复位寄存器保证的重复组合门控：

- 初始化 `ready_q` 异步复位为零，只在脚本完成时置位、失败时清零；`ready_o` 保留 fatal 的立即撤销，不再将复位释放网串入数据选择路径。
- 物理组合直接使用初始化器的 ready；数据 OE、STP 和停止时钟的异步故障关闭路径保留。
- `chirp_active_q` 已异步复位为零，chirp valid 不再重复串接 reset；仍受 PHY ready／fatal 限制。
- 独立诊断顶层为 `traffic_enable` 增加 `syn_keep`，防止其别名在综合后丢失，导致 GAO 无法绑定。没有新增端口或改变球位。

`C11030A0` 将前一 AF 的最差 setup −1.283 ns 改善至 −0.212 ns，但仍被门禁拒绝，未下载。移除最后一层冗余 failed 状态译码的 `C11030A1` 在实现开始时因 `traffic_enable` 名称被合并而失败，也未下载。`C11030A2` 加入上述诊断网络保留后重新构建。

### A2 路由通过与 SRAM 部署

`C11030A2` 于 00:15:20–00:17:57 构建并通过全部原有门禁，setup／hold／recovery／removal 为 +0.044／+0.191／+4.829／+0.272 ns，无负路径。候选目录为：

```text
~/.cache/fpga-usb2-hdmi/138k-push-recovery-c11030a2-20261030_001519/
```

- 原生来源清单 SHA-256：`ee83e42e107aee1ccaa246bde01c8144af2524dc551ca540ddca128ba2535b7e`。
- 实际 `impl/pnr/ao_0.fs` SHA-256：`97aef04dc5a6581fedf739b3472923c247cc1c8c96256e19d3ebd8a0d31a7255`。
- 路由审计 SHA-256：`57e7df637831a94cb74379d6bc0d163c163ddcb4230fb2eee7eeb3e9aa8b1227`。
- 00:19:59–00:20:14 根据既有 SRAM 授权执行 operation 4（Program and Verify）。写前独立读取 `0x0001081B / C11029AC`，写后独立读取 `0x0001081B / C11030A2`，编程器返回 0 并完成校验。
- 写入记录为候选的 `sram-deployment-20261030_001959/deployment.json`，包含原始命令和前／后身份；未写 Flash、未操作 25K。
- 回滚为原 AC，实际位流 SHA-256 `ec8245e6434bd5892fd20f9051bd722733d49802797735450cc852ff6c34030a`；仅在明确需要回滚时重新 SRAM 下载，不自动改写 Flash。

### A2 实物 HS 与用户再次拔插

00:20:56.788，三核捕获独立确认 `C11030A2`：Push 已枚举，ACTIVE／HS／Function Control `0x40`，attempts=1，received_events=396，CPU fault／out_errors 均为 0。恢复观察器为 recovery_count=1、active_count=1、recovery_aborts=0，600000 个 ULPI 周期（10 ms）、80 个 SOF 后进入 ACTIVE，退出前 RXCMD `0x0C`、flags `0xE1`、Function Control `0x40`。这次 SRAM 暖重配置没有重复启动。

用户再次拔线、等待再插回，三核连续窗口记录：

| 捕获完成时间 | 端口／枚举 | attempts | recovery／active／aborts | received_events | out_errors |
|---|---|---:|---|---:|---:|
| 00:22:15.778 | WAIT_ATTACH，CPU 未连接 | 5 | 1／1／0 | 970 | 1 |
| 00:22:20.950 | ACTIVE，HS，Push 已枚举 | 10 | 3／3／0 | 1032 | 1 |
| 00:23:49.176 | ACTIVE，HS，Push 已枚举 | 10 | 3／3／0 | 1686 | 1 |
| 00:26:18.435 | ACTIVE，HS，Push 已枚举 | 10 | 3／3／0 | 2792 | 1 |

重连后事件增长，未新增 CPU fault 或 OUT 错误，未重新启动 PHY；三个 RECOVERY 均成功进入 ACTIVE，没有异常退出。600000 周期／80 SOF 的恢复长度保持不变。空口期间增加的启动数不是失败握手数，recovery／active 的累计次数也不等同于 CPU 完成枚举次数。

24 个连续窗口于 00:24:15.290 完成，最新独立三核复读位于候选的 `capture-20261030_002614-push-final/`。直到 00:26:18 仍维持同一 HS 会话，拔线时的 970 个事件已增长至 2792，attempts／recovery／active 均不再增加。

本轮历史 `state_history=131071` 包含 FULL_SPEED_RESET，不能将其直接解释为 Push 曾以 FS 成功枚举；已连接窗口均明确为 HS。`command_count` 已饱和为 65535，不能用它计算本轮命令增量。实际连接确认仍以当次 CPU connected／device kind 加端口 HS 为准。

原始三核捕获：

```text
~/.cache/fpga-usb2-hdmi/138k-push-recovery-c11030a2-20261030_001519/capture-20261030_002052-push-recovery/
~/.cache/fpga-usb2-hdmi/138k-push-recovery-c11030a2-20261030_001519/push-hotplug-monitor-20261030_002211/
```

## 离线回归

- 最终 ready／chirp 逻辑的 4 项定向回归通过：初始化器 19 场景／5493 检查，物理组合 5 场景／3115 检查，时钟监护 4 场景／223 检查，端口 17 场景／23846 检查。新增异步复位在下一 ULPI 边沿之前关闭 ready／chirp 的断言。
- 来源边界 10/10、Host probe 10/10、恢复观察器 1/1 通过。最终诊断顶层增加的网络保留另有探针用例断言。
- 原生物理协商和真实 25K 控制器 2/2 通过，437.175 秒；包含 FS／HS 协商，以及真实描述符、地址、配置、bulk 和 SOF。运行期间 ready 组合门控进一步等价化，因此这不是 A2 全输入冻结回归；最终 ready 版本的完整物理组合另由上面的 4 项定向回归覆盖。
- 缓存日志：`push-ready-final-tests-20261030.log`、`push-native-regression-retry-20261030.log`。首次命令误写测试类名的失败保留在 `push-native-regression-20261030.log`，不计入代码测试通过数。
- 最终 A2 逻辑另行复跑真实原生控制器 HS／FS：1/1 用例通过（312.376 秒，HS 1146／FS 266 检查），相关 RTL 和测试的前／后 SHA-256 完全一致。证据为缓存 `push-final-native-20261030_002028/` 的 `tests.log`、`inputs-before.sha256`、`inputs-after.sha256`、空的 `input-drift.patch` 和 `exit_code=0`。最终恢复观察器再跑 1/1 通过，日志 `push-final-observer-tests-20261030.log`。

本轮已在 AC 和 A2 各观察到一次实际拔插后的 HS 枚举与 MIDI 恢复。A2 的三核诊断已能区分空口轮询、恢复阶段与 CPU 枚举，没有重现前序 AC 的 RECOVERY 提前退出；不能再将旧快照描述为当前持续失败。下一阶段可继续多轮插拔统计，并将稳定修复带入完整工作站的新候选；此探针不切换任何 accepted 整机 profile。
