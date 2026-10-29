# C11028E4：D5 HDMI 与 USB2 热插拔组合诊断

日期：2026-10-28。目标是用已经成功显示的 C11028D5 和现有 USB2 热插拔实现组成一个小候选，再用电脑上的 JTAG 窗口判断 138K 是否完成 25K／Push 枚举及设备识别；不带整机声音合成和演奏业务。

## 候选身份与实际实现

| 项目 | 结果 |
| --- | --- |
| 候选 | `custom138k-usb2-hdmi-C11028E4` |
| FPGA UserCode／GAO ID | `C11028E4`／`28E4` |
| 实际顶层 | `workstation_usb2_hdmi_top` |
| 来源策略 | `byte_identical_accepted_D5_display_plus_native_USB2_hotplug` |
| 编译来源 | 71 个；只省略 3 个整文件字节相同的重复模块来源 |
| 最终单次综合＋布局布线 | **341.001369 秒，约 5 分 41 秒** |
| 起止时间 | `2026-10-28T02:17:16.881620+08:00`～`02:22:57.882989+08:00` |
| SRAM／Flash | 用户授权后已下载 E4 到 SRAM；Flash 未访问 |
| 板上只读身份 | 下载后独立读回 `0xC11028E4`，IDCODE `0x0001081B` |

本机输出根目录为 `$HOME/.cache/fpga-usb2-hdmi/20261028-020452-d5-hotplug/`，最终候选在 `candidate-e4/`；日志、数据库和位流均未进入源代码变更。

| 证据 | SHA256 |
| --- | --- |
| 根 `inputs.json` | `68716a40a5398445f83f5c0e8534e438c7b4280b8547e0c6b184f3afd6bdbc21` |
| `integration_audit.json` | `7c6cac09c22fa34cb894a64672fdb38ebd16a87654214a86d133a538867dac03` |
| `integration.gao` | `4fe7f13977657b213b4cce179b52be8c6664e26c7a7b2b0a4adc87a08c82eb75` |
| 原生产工作站固件 ROM | `31c4d7d58141ef0ec2b33f826a9c22251b7d4f23771cbaa189427b0f1277d457` |
| 实际综合 `usb2_hdmi.vg` | `3f2aabb7e74227344262a783689d3c6bda9712eb624aaf3d5020d824dc493ffc` |
| 实际路由后详细时序 HTML | `4cca4b4c98eef28e6cd59530496b58fe11464b8f9db2b8cbfc0e070be3e08e5c` |
| 最终 `impl/pnr/ao_0.fs` | `4234ede9b5d1bd16855e9dc58d21d6e71f25ff7cd70dd1efc32805d4efa9143b` |

根清单记录准备时的配方哈希和所有实际暂存输入。构建完成后增加的缺失输出检查、审计适配及电脑监视器不修改候选清单、编译 RTL、ROM、约束或位流；本报告绑定的是上表中的实际候选，不以当前工作树的配方哈希冒充当时版本。

## D5 与 USB 来源边界

HDMI 子配置重新准备后，每个被选 RTL 以及原 `display.cst`／`display.sdc` 均与接受 D5 的暂存哈希逐字节一致。根组合只增加实例层级与 USB 引脚／约束，没有修改显示扫描窗口、DDR 访问、1080p 输出或 D5 测试画面业务。USB 仍使用已完成的原生 owner、固件、HS／FS Host、会话围栏、注册 Gray 指针事件 FIFO 及诊断观察器；没有另造 USB 协议。

两个子清单原样保留。`video_font_5x7`、`reset_release`、`video_pll_init` 的重复文件只在完整 SHA256 相等时省略，非一致模块冲突直接失败。没有改锁定网表、冻结基线或 vendor 原字节，也没有新增受版本控制的 `.cst`。

HDMI 画面仍由 D5 原来的确定性测试输入生成；USB 事件由电脑窗口观察，未接入声音合成、演奏或 HDMI 业务参数。

## 结构与时序

实际综合网表和路由后网表审计通过：原 USB bridge CDC、输入 FIFO、复位链、诊断复位别名、USB／音频 PLL 模式及频率；原冻结 DDR 配置／复位检查；视频 PLL 与 TMDS 串行器检查。组合 SDC 的 **253 个内部 selector** 全部解析到实际对象，**9 个功能时钟＋JTAG 时钟**的实现频率和对象均核对通过。

工具将 USB 输入 IBUF 提到组合顶层。审计先在完整网表上证明子模块 `clk_50m_d`／`usb2_ulpi_clk_d` 确实回溯到对应外部时钟，再使用这些实际名称执行原 USB 子树检查。原始综合网表不改写。网表解析器增加明确的拼接位投影，以解析综合器实际产生的 `{produce_w_gry[5],produce_w_gry_0[4:0]}`；位序、常量、宽度及不支持表达式均有回归。

| 实际全局时序 | 最差裕量 |
| --- | ---: |
| setup | +0.175 ns |
| hold | **−0.214 ns** |
| recovery | +2.544 ns |
| removal | +0.253 ns |

`structural_checks_passed=true`，`timing_closed=false`。详细负路径仅为原 HDMI DDR 初始化路径：`ddr_ui100` 域的 `ddr_init_internal_r_s0/Q` → `clk_50m` 域的 `wloadn_3_s0/D`。D5 原同类 hold 为 −0.251 ns；此处保留实际 −0.214 ns，不清除、豁免或记成全时序闭合。没有降低时钟或新增整域 false path。

实现报告主设计 BSRAM 为 **119**，GAO 为 **25**，合计物理 BSRAM **144**；主设计 Register **17430**，GAO **2021**。主设计 LUT **18831**、ALU **3893**，GAO 另用 LUT **861**、ALU **13**。不把主设计资源和含调试核总资源混为一项。

## 电脑监视器与回归

`tools/workstation_usb2_monitor.py` 提供实际 Tkinter 窗口；`tools/capture_workstation_usb2_hdmi.py` 负责身份核对、互斥 JTAG 采样、CSV 解码和证据保存。GAO 只用 USB CPU 48 MHz 时钟，探测 **447 个非恒定物理信号**，重建固定布局中的常量及已验证综合别名；单窗口 1024 拍。设备类型取真实固件配置完成后的 owner 分类，25K、Push 和通用 MIDI 分开显示，不把 PHY ready 记作握手成功。

窗口显示枚举／识别、HS／FS、SOF、输入及生命周期／取消事件、Push 帧／命令、IN／OUT 错误、断连和 CPU 故障。采样在线程中执行，读取失败或过期后撤销绿色成功状态。`--demo` 明确标记为模拟数据，`--once` 可输出单次 JSON。脚本没有 SRAM、Flash 或复位操作。

本轮核心回归 **79 项通过，34.413 秒**，日志 `final-core-regression.log`：

- 新组合准备、真实 owner 字段、CSV、窗口状态与实际 Tk 控件：11 项。
- 网表位投影与结构解析、USB 独立准备／真实 UART、accepted 来源边界、D5 HDMI 及 pinout 电气语义：68 项。
- `--demo --once` 和 `--help` 实际命令通过；窗口控件测试使用明确模拟数据，没有伪造硬件检测结果。
- `git diff --check` 通过。首次上板前只读身份记录为 `preflight-identity-D5.log`，该次检查未下载新程序。

授权下载前，实际运行监视器的只读采样入口时再次读到 D5；因候选要求 E4，入口按预期拒绝继续，未启动 GAO 采样。结果与原始身份日志保存在 `monitor-preflight-D5/`。该项验证身份拦截；后续实际部署与采样见下节。

包含自定义板原生 HS／FS 输入、完整综合及破坏性审计负例的扩展回归已完成：**111 项通过，1327.505 秒**，日志为 `fast-final-regression.log`。该扩展包含完整工作站综合，不是每轮快速迭代的默认回归；没有执行整机布局布线。

较宽的设备级混合热插拔重复运行在不变的完整帧仿真中主动中止，保留 `final-regression.log` 与中止说明，不计为通过。既有设备级验证仍见 [热插拔报告](USB2_HOTPLUG_DIAGNOSTIC_20261028.md) 及其链接证据。本轮组合的硬件检测结果需在新候选获准下载后另外记录。

## 保留尝试、上板与回退

保留 E1～E3 的失败输出：E1 缺少组合根目录所需的 DDR 地址头；E2 为 GAO 常量／综合别名不存在；E3 为 `get_regs` 未加组合层级。最终 E4 补入同字节头文件、精确真实探针及内部寄存器前缀后完成实现。审计适配前的日志与目录另存，不覆盖失败记录。

用户明确回复“ok，帮我烧进去”后，于 **2026-10-28 03:03:08～03:03:16（UTC+8）**仅执行 `operation_index=2` 的 SRAM Program，将上述 E4 位流下载到同一 GW5AST-138C。操作前实际读回已为 `C1102515`，而非上一轮的 D5；首次预检因此停止，未写入。记录这一变化后，再次核对设备、位流哈希和实际前置身份，按用户对 E4 SRAM 下载的授权执行；不推测旧身份变化的原因。

下载返回 0，日志明确为 SRAM Program，随后独立读回 **`0xC11028E4`**。没有访问 Flash。证据在 `sram_deployment_20261028_030308/`，`result.json` SHA256 为 `ab902e79ca5a8843d2340db7fdd130837e0ee112b2fd44e0b2d399db6bf62d6a`。根准备清单、原审计结果和位流保持原样，时序闭合及画面／USB 验收标记不因下载成功而改成 true。

03:03:39～03:03:41 首次真实 JTAG 采样完成，前后身份均为 E4，得到 1024 个样本；`first-live-capture/result.json` SHA256 为 `cebee03420b96899b477a41811d9f5dc948a7cfcad80f78c28c3e07d26f70cf7`。USB／音频 PLL 锁定，CPU 故障字为 0，窗口内观察到 6 个指令地址；PHY ready 为 false、SOF 为 0、owner 未连接，因此**尚未识别到 25K 或 Push**。不把这一读回记成握手成功，也不在缺少插入状态证据时判断原因。

电脑实际监视器已在 `DISPLAY=:0` 打开，非 demo，启动记录为 `monitor-desktop.json`，后续证据在 `monitor-live/`。首次检查已连续成功读取 8 个窗口，均仍为 `phy_initializing`，桌面进程日志无错误。后续依次检查空口、25K、拔出、Push、再次拔出并保存证据；HDMI 画面仍需用户观察确认。

回退使用原 D5 `impl/pnr/ao_0.fs`：`82a2f3aa1cc6a6b4660cc94bb837a56234397f8c6e859e8d06e30962e5c2e8aa`。ULPI 电气状态仍为 `no_voltage_domain_conflict_detected`，实测／完整电气验收标记均为 false；唯一旁路供电待实测项仍是 **USB3300 ULPI IO 是否确由 3V3 供电**。

完整准备、启动与采样命令见 [使用说明](../rtl/workstation/USB2_HDMI_DIAGNOSTIC.md)。

## 用户插入 25K 后的实际观察

用户确认“我现在插入了25k”后，连续读取现有 E4 监视器。03:13:21～03:13:32（UTC+8）的最新三个窗口均为 1024 拍：owner 未连接、未识别设备、SOF／输入事件为 0，USB／音频 PLL 锁定、CPU 故障字为 0。最新记录距读取时约 1 秒，不是拿旧窗口判断本次插入。原始路径、时间、身份及结果哈希保存在输出根的 `25k-insertion-observation-20261028-031333.json`；本次没有重新下载或操作 Flash。

采样到的 CPU 指令地址位于本候选真实 ELF 的 `delay()` 循环附近（`0x000046A4`～`0x000046B8`）；结合未连接状态，与 `connect()` 中 `usbhw_hub_device_detected()` 失败后每 100 ms 重试的路径一致。没有证据表明已进入 25K VID／PID、端点或 MIDI／面板业务识别成功阶段。

当前 `phy_initializing` 是解码器对全零 PHY 状态快照的呈现，不能据此单独认定 USB3300 初始化失败。该快照通过 ULPI 时钟域发送，而诊断顶层未导出 `destination_valid`；ULPI 时钟未到、快照未送达或 PHY 初始化卡住都可能呈现全零。后续定位需要补充独立时钟存活、快照有效／更新及参考域初始化状态观测，再决定实际修复；不先猜测 25K MIDI 协议或更改球位。

## PHY 定位候选 E5

用户继续授权保持 25K 插入并通过探针定位；随后明确“下载进sram就不用问我了，你自己下载”。这项持续授权仅用于本轮 138K SRAM 诊断，不包含 Flash 或 25K 重刷。

修改解码器前先停止 E4 桌面监视器，等待当次只读采样结束；全部 221 个既有窗口保留，最后窗口仍未识别设备。旧解码器哈希及最后窗口保存于 `monitor-e4-stopped-before-phy-profile.json`，避免旧进程加载旧代码却记录新文件哈希。

E5 使用显式 `--usb2-observer-profile phy` 与新 UserCode `C11028E5`。USB／HDMI 业务 RTL、固件、引脚及约束保持原组合；只扩展 GAO。原 447 个 owner 探针保持原序，追加 ULPI 心跳、参考域时钟监控与使能／复位、初始化／端口状态、快照握手及原始管脚电平。51 位寄存器探针已在实际 E5 综合网表中核对唯一驱动和 ULPI／50 MHz／CPU 时钟归属。

针对性回归 13 项通过（2.362 秒），包含 v1 布局兼容、无快照不得显示成功、参考心跳／快照更新计数、真实 Tk 控件及准备入口隔离。日志 `phy-profile-tests.log`。实现、下载和实际读回另记，不用 E4 的结果代替 E5。

E5 实现于 03:26:56～03:32:51，耗时 **355.175 秒**；位流 SHA256 为 `e723f82f45e5807452125f8a3bb6429ec4955bce91c7770066586fb738c66703`，结构审计通过。全局 setup **−4.661 ns** 的负路径均进入 GAO 原始跨域采样寄存器；原 HDMI DDR hold 仍为 **−0.214 ns**。完整负路径保留，`timing_closed=false`；没有添加 false path 来掩盖调试采样路径。51 位探针实际时钟归属检查通过；把参考心跳探针时钟故意改成 ULPI 时被拒绝。旧 E4 原始 CSV 用新版解码器重放，所有末帧字段一致，记录于 `phy-profile-evidence-tests.json`。另有 accepted 输入边界 10 项及网表解析 9 项通过。

03:34:53～03:35:01 直接下载 E5 SRAM，独立读回 `0xC11028E5`，未访问 Flash。证据 `sram_deployment_e5_20261028_033453/`。首次采样及随后三个确认窗口（03:35:02～03:37:18）均显示：参考域复位已释放，ULPI 心跳／桥接 ULPI 复位释放／快照请求及确认全为 0，DIR=1、NXT=0、STP=1、DATA=0。两组 ULPI 时钟域复位释放寄存器不随 Host 使能清零；这比 E4 的全零快照进一步把问题定位到 FPGA 收不到 ULPI 时钟，而不是 25K VID／PID 或端点识别。

这些立即采样窗口中 Host 使能为 0，还需区分“从未使能”与“短暂使能后因参考时钟故障退出”。因此 E6 仅把 GAO 触发改为原 `clock_failure[0]`，UserCode 改为 `C11028E6`，保留同一 PHY 布局。实际 RTL、ROM、CST／SDC 与 E5 逐项同字节，比较证据 `e5-e6-source-comparison.json`；没有修改运行时初始化或超时。增加触发选择回归后，针对性测试 **14 项通过（2.352 秒）**，日志 `phy-fault-trigger-tests.log`。

E5 的实际 GAO 布局为 **510 个非恒定探针**。主设计仍为 119 个 BSRAM、17430 个 Register、18831 个 LUT、3893 个 ALU；GAO 为 29 个 BSRAM、2273 个 Register、904 个 LUT、13 个 ALU，总物理 BSRAM **148**。E4→E5 实际 RTL 与约束同字节核对保存在 `e4-e5-source-comparison.json`。

E6 实现耗时 **357.553 秒**，结构审计通过，实际时序与 E5 相同；位流 SHA256 为 `0ea31dcd2c229989b477326a075b06e621b0fc23422827851e6976f034eb54e3`。03:49:37～03:49:45 下载到 SRAM并独立读回 E6。两次采样的故障位均为 0，因此**没有取得有效的故障触发窗口**，不据此声称已观察到 Host 启动、故障码 1 或重试过程。原始 CSV／身份／结果保留在 `e6-clock-fault-capture-{1,2}/`，后续严格重放均拒绝，分类记录 `e6-trigger-validation.json`。这也暴露了“导出 CSV 不等于命中触发”的主机采样检查缺口，解码器已补上触发位验真。

03:49:51～03:49:59 恢复同一已审计 E5 位流，独立读回 **`0xC11028E5`**，记录 `sram_e5_monitor_restore_20261028_034951/`，结果 SHA256 为 `cc8032046990d3e2c49815aedbc09335c55ff0238db6f65eb5d38f34d7576ef4`。所有本轮下载均仅 SRAM，未访问 Flash，也未重刷 25K。

## 定位结论与当前监视器

**25K 枚举的当前阻断点是 FPGA 端未收到 USB3300 的 ULPI 时钟。** 不是把零快照直接解释为 PHY 初始化失败：实际 E5 综合网表证明，桥接 `ulpi_release_q` 和监控 `heartbeat_release_q` 两组释放寄存器的 CE 都接常量 1，CLK 都接外部 `usb2_ulpi_clk`；CLEAR 分别只由已读到 1 的 `usb_release[3]`／`reference_release_q[1]` 取反驱动，不随 Host 使能清零。时钟若到达，两组释放链会在两个 ULPI 边沿后置 1。实际反复采样中它们持续为 0，心跳与快照请求／确认也持续不动。复位反相器的实际网表证明保存在 `e5-ulpi-reset-netlist-proof.json`。

03:57:23～03:57:26 的新版本解码器再次真实采样，1024 拍全部为 `ulpi_clock_not_observed`，CPU 无故障，参考／CPU 域已释放，ULPI 两组释放链仍为 0。`final-e5-live-capture/result.json` SHA256 为 `7c5730ba9bcd70e2304283adde375820580cc2341d521b1ee35f79509bd1c53f`。实际桌面监视器使用 E5 非 demo 配置持续读取，最新启动信息由输出根 `current-monitor` 指向，数据在 `monitor-e5-final-live/`；当前部署由 `current-deployment` 指向。没有把同一 FPGA 的时钟输入问题归因到 25K MIDI／端点代码。

下一步物理检查沿既定连接定位：**U2.14 CLKOUT → U5.2／U5.13 旁路 → J1.92 → FPGA C18**。U2.14 有 60 MHz 而 C18 没有，就查时钟旁路／连接；U2.14 本身没有，则查 USB3300 的供电、24 MHz 晶体与启动。没有改锁定网表、球位、其它端口或 retired_ports。既有 pinout 电气审计唯一供电待实测项仍为“USB3300 ULPI IO 是否确由 3V3 供电”，电气验收标志保持 false。

最终针对性回归 **34 项通过**：组合／解码／真实 Tk 控件 15 项、accepted 输入边界 10 项、网表解析 9 项；另有真实 E4 CSV 兼容重放、E5 错时钟负例和 E6 未命中触发拒收检查。日志 `phy-final-*.log`，未重跑整机 P&R。两个小候选实现分别只需约六分钟。完整工具版本哈希及当前身份、采样／部署索引另存于 `final-tools-source-identity.json`。

## 后续 Flash 固化

用户随后明确授权固化当前 E5 以进行硬件检查。2026-10-28 14:30 已完成配置 Flash 写入、独立复验、保留分区前后字节核对及 Flash 重载 E5 读码；未补下 SRAM，未改写 25K。此前“未访问 Flash”描述仅对应各段原 SRAM 实验。当前部署、全量备份、回退材料及启动后 ULPI 读数见 [E5 Flash 固化记录](USB2_HDMI_FLASH_20261028.md)。
