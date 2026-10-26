# 新板工作站蓝牙接入（2026-10-23）

本次把 25K 已有 BLE 业务协议接入新板原生工作站，取代仅有 FFF0 诊断服务的接法。广播名称 `GW138K-MAIN`，业务 UUID、录音格式和下载扩展保持原协议。只选择显式 `--prepare-custom-board` 配置；accepted full83、timing85、原 resource-timing 默认配置不变。

当前源码准备身份为 `custom138k-native-integration-20261023-a16`，本机证据目录为 `/home/sphenicidition/.cache/fpga-validation-20261023/native-ble-v9`。`integration_inputs.json` 记录配置、完整输入哈希、冻结父配置、BLE 源码和网表来源。基础 Git HEAD 为 `f502f28f329c6665e4a6150583e390b2c9611cef` 加当前工作区修改；不能仅用 HEAD 重现本次候选。已有 B6 码流未通过物理门禁，不能用于四接口验收或固化；a16 的实际验证范围单独记录。

## 已接入的路径

- `workstation_bluetooth.sv` 接入原 H5／HCI 补丁初始化、ATT／GATT、命令、录音和下载端点。115200/8E1 启动后切至 921600/8E1；不使用 AT 模组协议。
- 引脚依据核心板 C2400 与自定义 J2 的编号转换以及 FPC 反序连接核对：T14 → 模组 UART_RX，W12 ← UART_TX，AA9 → BT_DIS#，AA13 → WL_DIS#（保持 Wi-Fi 禁用）。对应节点和参考图 SHA 见 `boards/custom_138k/bluetooth.json`；未驱动 PCM／SDIO／HOST_WAKE。
- 音频取自 FPC 串行器实际发出的 48 kHz 立体声帧，包含静音结果。完整 PCM 对和连续帧号通过已有保持字 CDC 进入 50 MHz 域，再写入独立 RAM。录音／下载不会反压音频调度。
- 容量 16,384 帧，即 65,536 字节、约 0.341 秒。容量满封存；断连继续录制。源丢失、帧缺口或切换进入 ERROR，拒绝下载并允许清除。TF 正在播放时拒绝开始录音。参数控制、DDR 长录音未宣告为已支持能力。
- Gowin 工程只启用一份合并后的 `custom_138k.cst`，包含位置、音频、蓝牙和显示标准；四份组成约束保留供审查。显示差分端保留参考设计 LVCMOS33D，避免与 Bank 3 的 3.3 V HPD／CEC 冲突。
- 根据 B6 失败路径修正三处：任务槽位分别登记过期状态，缩短任务编号到分配使能的组合路径，保留完成后一分钟的查询期限；UART 同步器连续采样，仅第二级参与空闲判断；FPC PLL 初始化复位在 50 MHz 域同步释放。源码审计核对两条同步链的直接连接、时钟、使能和第一级唯一消费者。

| 接口 | 已完成的离线范围 | 实物状态 |
| --- | --- | --- |
| 138K ↔ 25K USB／LCD | 原生 Host、实际 CPU 业务固件、MIDI／PL、真实 25K 核 HS／FS 仿真 | USB3300／TXS 电平冲突未修正，不能放行；不保证实物 HS |
| HDMI 屏幕 | 新引脚、四对极性补偿、专用串行器与独立 RGB 解码 | B6 的四串行器启动及视频 PLL 数字传播检查通过；整机门禁未通过，未验收显示器 |
| AUDIO → FPC → 功放 | I2S32、MCLK／BCLK／LRCK、启动静音及实际 PCM 解码 | 待电压／排线／声道和出声验收 |
| 蓝牙 | 现有业务协议、真实 PCM 短录音、CRC／下载、完整 UART 补丁初始化仿真 | 待真实模块初始化、手机连接及录音下载；未支持长录音 |

## 验证与交付状态

前序 a13 完整综合、独立审计及主动破坏输入的审计回归通过（145.019 秒）：56,428 Register、77,064 LUT、15,092 ALU、266 综合 BSRAM、1,459 SSRAM。32 个录音 SDPB 保留完整 14 位读写地址；不是旧 1024 帧循环 ROM。综合有 338 条警告，不能把综合完成视为时序收敛，也不能将综合 BSRAM 当作物理块数。以下 a13／a12 哈希用于绑定 B6 物理实验，不代表修正后的 a15 已完成物理实现。

| 证据 | SHA256 |
| --- | --- |
| a13 `integration_inputs.json` | `a61ad164bd65f0b75561524c60ffeb53647dc6de13d0ea9a774d0c1d4f22a9f2` |
| a13 `audit.json` | `3c67d8d203a83954db365e55364d01fd2c64551ef5e537ca4088307f0bae848e` |
| a13 新综合网表 | `873bf71014dbf8802aae72d3c42a9e4a4e73ce6f2ef22d3f02a11e29953fac5b` |
| 实际物理输入网表（a12） | `d3e122500c1ae380d1605718ec01a7f736433a0c5d7d0512a53f7260cc61fba2` |
| `source-binding-final.json` | `1a6d24849ba6ca08ba6ff9d50fcc9101a7d4e0dad660f403ce646fbed16aee4b` |
| `physical-input-source-audit.json` | `e3621326ae4588228f75788d0b52145a01d15cd9eac46a42469a11f140c4a21c` |
| USB 业务固件 ROM | `31c4d7d58141ef0ec2b33f826a9c22251b7d4f23771cbaa189427b0f1277d457` |

父 SDC SHA256 为 `cf7c8613444693570a531d6edf7c93dbb7f415b0b3ef5cfc026b6b74a2bf4f43`，不符即失败；保留 157 条定向约束。九条旧约束因端口／数据移除或已有独立 FIFO 约束而省略，十条按 input owner／TMDS 层次或失效 MIDI 端点适配，清单进入 manifest。145 组可见选择器非空，第一阶段 D 选择器逐个核对；13 组 DDR 不透明 IP 内部选择器留待实现后确认。准备、旧默认顶层 token 和 accepted 输入边界 12 项回归通过。

物理任务 `native-ble-v5-physical-selector-fix` 使用 a12 已审计网表与 a13 约束，UserCode 为 `C11023B5`，最终退出码 1、PR0004：284 条网络未布通，没有可交付码流。`source-binding-final.json` 逐项复核 229 个编译输入、505 个暂存闭包文件；与 a13 仅有 SDC 和补丁绝对路径头不同，补丁数据相同。实际 SDC 为 a13 原字节加报告查询，CST 逐字节相同；实际物理网表另经 a13 源码审计器检查通过。新综合与物理输入网表哈希不同，未宣称两者已做形式等价证明，未把新网表哈希冒充物理输入身份。

另建 `native-ble-a13-place2-route0` 物理对照，身份 `custom138k-native-physical-20261023-b6`、UserCode `C11023B6`。它保留相同网表和 SDC，选择 place2／route0、关闭资源复制，补回父配置已有的 reference PLL helper 局部布局约束；新板 IO 原字节不变。适配函数 `tools/workstation_timing_constraints.py` SHA256 为 `210f5a801c0883cd60900a8023406fd96752dc18471225d1d31763eb31fa6cd5`，父 CST 必须精确包含该约束块一次。全部输入及额外 CST 原文进入该目录 `inputs.json`；没有借用父工程的通过结论，也未设置其 max_fanout128 综合选项。对照通过后须将所需布局选择归入现有入口并保留门禁；否则仅保留诊断证据，不作为生产输入。

B6 在 04:34 完成 P&R 并生成码流，退出码为 0，但**验收失败**。物理 BSRAM 为 305/340，CLS 为 63,625/69,120，不能与综合 266 BSRAM 混用。全局最差 setup／hold／recovery／removal 分别为 -16.059／-0.133／-9.684／-0.368 ns；50 MHz 和 76.8 MHz 域 Fmax 分别为 48.539 和 69.202 MHz，另有 DDR UI setup 失败。失败路径包括 USB 复位到 ULPI／参考域、音频 PANIC／事件扇出、DDR 命令地址和蓝牙任务分配。另有 PR1014 提醒 50 MHz 使用普通布线资源。不能通过放慢时钟、批量异步例外或删除功能消除这些失败。

B6 的局部检查有明确范围：12 个时钟周期及像素 60/40 波形保持；原九对 FIFO 的 18 组 Gray 总线和五组电平检查通过；原生 USB 10 个控制位、14 个事件 FIFO 指针位、116 个有效邮箱位，以及 33/64 位 FPC／BLE PCM 保持字传播检查通过；13 组不透明 DDR 选择器全部非空。UART 同步链因级间组合逻辑而失败。视频 PLL helper、四个 OSER10 及 DDR 停钟启动检查通过，且修改时钟字或断开差分缓冲器的负向检查均被拒绝。这些结果不构成全部 CDC／PLL 或外部 IO 时序验收，也不由 a15 自动继承。

B6 的 `inputs.json` SHA256 为 `fce34a2855e540813fa7a9f2504bad926d2ebe6dc2671c41fba5a6a3d242f96c`，所列七项输入复核未变；被拒绝的 `.fs` SHA256 为 `9587ed1ab355a67c733159ce8ee206b75a834632a9080c2e6a14209d2f170fd9`。缓存审计适配器检查原脚本哈希和替换次数，不修改冻结脚本；若以后选择此物理配置，须把原生层次及极性适配归入现有版本化检查器。B5／B6 仅保留诊断证据，不成为生产来源。

前序 `native-ble-v4-physical-full` 缺共享 SDC，已中止；`native-ble-v5-physical-full` 在已移除 MIDI 接收器的失效 D 端点处报 TA2003。两者均不作为交付输入，其原始记录保留。

已经通过的定向验证：真实 PCM 存储／完整下载／CRC／容量／断连／错误及异步启动任务处理；完整 UART 控制器仿真核对全部 30,147 个补丁字节、广播名、GATT 及实际 PCM 对象 CRC；原 25K 默认录音与 GATT 回归；FPC PCM 观察口与独立 I2S 解码一致；accepted 输入边界、时钟和位置规划 39 项回归；实际 25K 核的原生 HS／FS 输入以及 TMDS 专用输出综合和独立 RGB 串行解码。首次 FS 回归因测试文件在运行期间修改而被输入哈希门禁拒绝，冻结后单项重跑通过，不将失败日志当作通过记录。

## 单项上板策略（按用户最新要求）

用户要求多功能协同有问题就回退、逐个功能上板。B5／B6 未上板，无需向板卡写另一旧镜像来回退；保留现有板上镜像，停止部署失败的整机候选。a16 源码修正保留为开发候选，不自动作为整机发布。未回退无关工作区修改。

蓝牙单项诊断为 `custom138k-isolated-ble-20261023-d1`，UserCode `0xC11023D1`，目录 `/home/sphenicidition/.cache/fpga-validation-20261023/ble-isolated-c11023d1`。逐项核对 a15 已冻结暂存的输入哈希，仅取 BLE 业务、初始化、补丁和诊断串口，不复制整机工程。`inputs.json` 记录输入及退出条件，`verification.json` 绑定位流、物理网表、时序和检查器。仅使用 V22 时钟、U15 状态 UART 及 T14／W12／AA9／AA13，不驱动 USB3300。

广播名为 **`GW138K-TEST`**，通过诊断顶层覆盖已有参数；没有修改业务协议。录音源是 48 kHz 左计数／右取反的测试 PCM，容量仍为 16,384 帧；不连接功放、HDMI 或 DDR。下载文件可验证 BLE 业务链，不代表工作站实际音频录音。单项已完成综合和 P&R：物理 BSRAM 67/340、寄存器 10,483，50 MHz Fmax 52.263 MHz，setup／hold 违例端点为零。物理 UART 同步链直接连接、持续采样，第一级仅送第二级；时钟到 Q 加布线为 0.662 ns，小于 2 ns。全部 STA 和身份检查以该目录 `verification.json` 为准，不移用于整机。

功放和 HDMI 分别准备 `audio-isolated-c11023d2`／`display-isolated-c11023d4`，位于相同缓存根目录，UserCode `0xC11023D2`／`0xC11023D4`。前者只通过 138K AUDIO→FPC 输出 48 kHz、左右 1／2 kHz、峰值 1024/32768 的测试方波，后者只输出 1080p60 八色竖条；复用暂存中的实际串行器、PLL 和网表位置约束。功放 STA 通过，PLL 检查器尚需支持已有控制元组寄存器，不把检查器不兼容当作 PLL 已通过。HDMI D4 的 STA、四路 OSER10 停钟启动、视频 PLL 传播及故意破坏时钟字的负向检查通过；前序 D3 因筛选约束时漏掉原有像素复位同步链 CLEAR 例外而被拒绝，D4 仅恢复原有例外的实际端点，未放宽业务路径。这些缓存适配器仅用于诊断，若成为常用配置，须归入现有入口；不作为生产来源。

10:22 用户确认上电后，电脑识别到 `0403:6010`、无序列号的 FTDI 双通道下载器，libusb location 54、D2XX location 13905，出现 ttyUSB0／1。已执行只读 JTAG 识别：0.9 MHz 读全 0，首次 0.1 MHz 读全 F；两种 Gowin 驱动和 openFPGALoader 均未取得有效 FPGA 身份。按用户要求再次检查，截至 10:42，0.9／0.1 MHz 都读回 ID／UserCode／Status 全 0（`board-jtag-latest.log`／`board-jtag-latest-slow.log`，退出码 3），预期器件 ID 为 `0x0001081B`。未下载 SRAM，未写 Flash；当前镜像身份未知，不能声称已回退或部署。

网表中的新底板下载口为 **U13**：1=TCK→J0.4，3=TDO→J0.3，5=TMS→J0.2，9=TDI→J0.5，2／10=GND，4 经 **R4=0Ω** 接 +3V3。下一步按该连接逐项检查排线方向、参考电压、共地及 J0 板对板连接；万用表导通检查在断电时进行，时钟检查使用只读 JTAG 扫描。不能仅因电脑识别下载器就认定 FPGA 供电与 JTAG 已正常。

用户随后实测 U13.4 对 U13.2 为 3.3 V，并明确 CONFIG 指底板 **SW1 四位拨码**，不是核心板 RECONFIG 按键；此前关于“松开 CONFIG”的指引不适用。按底板网表、DS-04R-P-T 符号及核心板原理图第 7 页，SW1 的 1↔8、2↔7、3↔6 三组分别接 U9/MODE2、U10/MODE1、U11/MODE0，对应 J2.35／36／37；4↔5 接 V13 普通 IO。前三路闭合时分别经 R50／51／52=1 kΩ 接 +3V3，另有 R16／47／48=1.5 kΩ 常接地，忽略内部弱上拉时理论分压约 1.98 V，实际电平待测；R15.1 在所给网表中没有网络，不能擅自视作额外上拉。当地安装的高云 UG704-1.0.7 第 6 页明确 JTAG 与 MODE[2:0] 无关、一直生效，101 为仅 JTAG；第 10 页要求 MODE 改动后重新上电或触发 RECONFIG_N。因此不能把拨码状态直接判作读 ID 全 0 的原因，也不能未经实测把 ON 当作可靠高电平。U13 的 3.3 V 只确认下载口参考电压，核心电源、RECONFIG_N／READY 及四根 JTAG 的实物连通性仍待排查。

用户最新确认仅第三位 ON，其余 OFF，实测 **R48 约 2.288 V，R16／R47 约 0 V**，取代前述 R47 约 0.2 V 的测量口述。该拨法意图选择 MODE[2:0]=001（MSPI），但不能据拨位认定 FPGA 实际采样为 001，配置输入的有效高电平门限尚未取得对应器件数据手册确认。0.1 MHz 再次只读扫描仍得到 ID／UserCode／Status 全 0，退出码 3，日志 `board-jtag-mode001-r48-2288mv.log`；未写 SRAM／Flash。用户说明核心板此前固化过程序、当前有明显发热；这不等同于各电源轨或当前旧程序运行状态已实测正常。

下一步先保持拨码，整机断电并断开下载器 USB 后核对底板 U13 到核心板自带 8 针调试座 U1201 的端到端导通：TCK 为 U13.1→U1201.4，TDO 为 U13.3→U1201.3，TMS 为 U13.5→U1201.2，TDI 为 U13.9→U1201.5，GND 为 U13.2／10→U1201.8。核心座 U1201.1 是 5 V，不是底板 U13.4 的 3.3 V 参考电压。对应关系取自核心板原理图第 5 页；这些是待用户实测的目标，尚非已通过证据。导通无误后继续核对 RECONFIG_N、READY 及核心电源轨。

11:45 用户在此前反馈“仅 GND 导通、四路 JTAG 不通”后表示已搞通，并要求重新识别；具体硬件处理方式未说明。下载器重新枚举为 Bus 003 Device 102，libusb location 仍为 54。0.1 MHz 和 0.9 MHz 两次只读识别均成功、退出码 0，均读到 **ID `0x0001081B`、UserCode `0x00000085`、Status `0x00026020`**，确认 GW5AST-138C 的 JTAG 识别已恢复。日志为缓存根目录的 `board-jtag-after-continuity-1145.log` 和 `board-jtag-after-continuity-1145-900khz.log`。UserCode 与历史 0x85 标记一致，不能仅据该数值认定位流逐字相同或整机外设已验收；本轮仍未下载 SRAM、未写 Flash。

1. 调试器恢复后先读器件和 UserCode，记录原镜像及可用回退文件；只给通过各自门禁的单项候选下载 SRAM，精确读回新 UserCode。Flash 保留。每项实际通过后再换下一项，失败保留日志并回到可核实的原镜像；未核实适配新底板的旧位流不盲写。
2. BLE：扫描 `GW138K-TEST`，核对真实模块 ROM=2、补丁 120 片、初始化／连接／订阅，检查查询、短录音、下载 CRC、清除及断连重连。状态 UART 使用 U15、115200/8N1。测试 PCM 不作为实际出声验收。
3. AUDIO FPC：核对排线、MCLK／BICK／LRCK、启动静音、左右测试音；再验证 HDMI 稳定色条。功放只用 138K AUDIO 接口到功放板的 FPC。
4. **USB 单项仍被电气问题阻断。** 用户于 2026-10-23 确认按网表装配、未改动，USB3300 与 TXS A 侧 1.8 V 冲突尚未修正，实际电压未测。不能修改 IO_TYPE 或抬高共享 1.8 V 电源绕过。修正后才验证 25K 枚举、实际协商速率、MIDI 和 LCD；Push 与 25K 交替使用同一 USB-A，不据仿真宣称实物 High-Speed。
5. 单项通过后再处理整机协同，重新完成整机物理门禁。届时 App 连接 `GW138K-MAIN`，最大时长保留 **0（容量上限）**，实际出声后录制并下载核对声道。此版不足一秒，App 可能显示 `00:00`；不能填 1 秒。重配置后删除未完成下载，保留已知 boot_id 重复限制。

上述 11:45 阶段仅执行只读 JTAG 识别。缓存中的 v1／v2／v3 与 `native-ble-exploratory-physical` 是前序或探索结果，不作为部署输入；后续 SRAM 操作见以下记录，不覆盖此前接受配置。

## 蓝牙单项 SRAM 联调续记

11:48 按用户逐项上板授权复核 D1 输入与物理门禁后，执行 SRAM Program，未写 Flash。位流 `ble-isolated-c11023d1/impl/pnr/ble_isolation.fs` SHA256 为 `dd40de7082f8df926ff1b3df30f9879db398a5c9f9a293a5974bc3df7284e6cf`。下载前读到 ID `0x0001081B`／UserCode `0x00000085`／Status `0x00026020`；下载后独立读回相同 ID、UserCode **`0xC11023D1`**、Status `0x00026230`。缓存根目录的 `ble-d1-before-program.log`、`ble-d1-sram-program.log`、`ble-d1-after-program.log` 保留原始输出。程序选择 0.9 MHz，工具在编程阶段自动报告更新为 15 MHz；操作退出码 0，不能据此认定 BLE 外设通过。

11:49 电脑 Intel AX211 蓝牙已开机、未被 rfkill 阻断，使用仓库固定的 bleak 3.0.2 扫描 30 秒，未发现 `GW138K-TEST`；记录为 `ble-d1-advertisement.json`。当前尚无模块初始化、广播、手机连接或录音下载通过证据。用户确认仅接底板 U13 的 JTAG，未接状态 UART，并要求尽量使用 JTAG 调试；后续优先加入只读 GAO 状态采集，不要求额外串口线。

功放 D2 的原控制元组寄存器现已由诊断检查器识别，物理 PLL 检查及破坏寄存器 D／CLK 的负向检查通过，记录为 `audio-d2-routed-check.log` 与 D2 的 `verification.json`；没有修改音频 RTL 或位流，也未上板。用户最新确认 HDMI 已接但无信号、功放暂缓；D1 不含 HDMI 输出，这次无信号不能用来判定 HDMI 驱动失败。按最新优先级集中处理蓝牙。

Android 当前可用安装包为 `clients/android/app/build/outputs/apk/debug/app-debug.apk`，版本 0.2.10／versionCode 13；README 的本机 `artifacts/` 归档在此电脑不存在。源码与使用入口仍为 `clients/android/README.md`。App 从“连接设备”扫描业务服务，单项名称为 `GW138K-TEST`；尚未扫描到设备前不能宣称手机实机可用。

### JTAG 只读状态采集与当前阻断

12:05 起按用户优先 JTAG 的要求，下载 `custom138k-isolated-ble-gao-20261023-d5`，UserCode **`0xC11023D5`**。D5 逐项检查 D1 冻结输入，只增加 128 位只读状态寄存器与后综合 `.gao`，不改变 UART、补丁、业务协议或外围输出策略。准备脚本为缓存根目录 `prepare_ble_gao.py`，输出 `ble-isolated-c11023d5`，GAO_ID 为 `1101000100100101`。此配置只用于单项诊断，进入常用构建前须归入现有入口，不能成为新的生产来源。

| D5 身份证据 | SHA256 |
| --- | --- |
| `inputs.json` | `2e83cf4daa25b1166b546728a2d1f78ade25bc7e41fd7253b9812780a62a6da3` |
| `ble_status.gao` | `99fd8a7ab012bcd23552d6a369676f79a7ec320844cb443b5b5bb050e1029ed8` |
| `impl/gwsynthesis/ble_isolation.vg` | `7cb2c4534d6c547e92de0b5bd27fb47b976f1e4b7eaccdbb6a10e8c1859cb58c` |
| `frozen_setup.tcl` | `58024624710a0e5813e67c8b86fb4893dd79a08645822a1a8a1086a729c94232` |
| `impl/pnr/ao_0.fs` | `f4cd384aab2eb8269807e7d9d02aee00e85db1a8c6cbdbcb5981ee8bdb3a888f` |
| `verification.json` | `1140b8d399ded118dd4754b2e11999d80745a248623dc9256f1eb65fc6ffe3b3` |

综合与 P&R 分进程执行，后者确认只有综合网表、未重复综合，并确认后综合 GAO ID 与码流一致。`check_ble_gao.py` 检查全部暂存输入、引脚、128 个保留观察寄存器和实际物理 UART 同步链；采样 RX 使用第二级，第一级仍只送第二级，传播 0.607 ns，小于 2 ns。50 MHz 实际 Fmax 52.172 MHz；工具注入的 TCK 约束为 20 MHz。全局 setup／hold／recovery／removal 最差余量为 0.833／0.201／6.671／0.771 ns，无负向详细路径。物理 BSRAM 67/340、FF 10,616。保留 PR1014 普通时钟布线警告，未放慢业务时钟或增加时序例外；时序通过不等同于 GAO 不透明 IP 的结构 CDC 签核或实际 TCK 频率测量。

D5 仅执行 SRAM Program，首次和启动复采各一次；各次独立读回 ID `0x0001081B`、UserCode `0xC11023D5`、Status `0x00026230`。当前 SRAM 为 D5，Flash 未写。日志为缓存根目录 `ble-d5-before-program.log`、`ble-d5-sram-program.log`、`ble-d5-after-program.log`、`ble-d5-startup-sram-program.log`、`ble-d5-startup-readback.log`、`ble-d5-final-readback.log`。如需撤下 GAO，回退文件为前述已核验 SHA256 的 D1 SRAM 码流；不盲写旧 0x85 新底板配置，不将整机 B6 用作回退。

本机 `gao_sh -cable WINUSB -location 54` 首次调用超时，未取得采集；随后 `programmer_cli --scan-cables` 实际扫描得到 FT2CH 通道 0、location 13921，使用 `-cable FT2CH -location 13921` 成功导出四次 CSV。每次热插拔后须重新扫描位置。GAO 经现有 U13 JTAG 线读取，不使用状态串口。成功命令的形式如下，工具环境与 `/home/sphenicidition/.local/bin/gw_sh` 保持一致：

```sh
gao_sh -gao "$candidate/ble_status.gao" -device GW5AST-138C \
  -cable FT2CH -location "$scanned_location" -out "$unique_capture_prefix"
```

128 位观察字从高到低为：flags 8、GATT／HCI／H5 状态各 8、error／status／opcode 共 32、补丁／HCI 命令／ROM／H5 RX／H5 TX／UART error／H5 retries 各 8、同步 RX／逻辑 TX／逻辑 BT enable／outputs active 各 1、心跳 4。计数只保留低八位，不能把 0 当作从未发生或从低八位差值推算完整错误量。CSV 时间列沿用工具标签，不据此认定真实采样间隔；128 点在名义 50 MHz 下只覆盖 2.56 µs，不能证明两个窗口之间没有 UART 跳变。

12:07 重新下载同一 D5 后复采启动过程，以下时间为 SRAM 命令返回后的捕获调用起止区间，不冒充精确采样时刻。三个窗口均各有 128 点、心跳覆盖全部 16 个值，其余字段在各自窗口中稳定；RX 为经核对的 UART 第二级输出。

| 调用区间（秒） | outputs／BT enable | 同步 RX | H5 TX 低八位 | UART error 低八位 | 错误码 |
| --- | --- | --- | --- | --- | --- |
| 0.33–1.54 | 1／1 | 0 | 0 | 0 | 0 |
| 4.54–5.71 | 1／1 | 0 | 24 | 97 | 0 |
| 10.71–11.82 | 0／0 | 0 | 67 | 70 | 8 |

三次 H5 RX、HCI 命令和补丁片数低八位均为 0，H5 link／initialized 均为 0，ROM 仍为初始 `0xFF`。结合初始化状态和错误 8，可确定停在 **H5 链路建立超时，尚未开始 HCI／补丁初始化**；不能把 ROM 初值当作真实 ROM 版本。发送计数表示传输状态机已完成发送，不等于 FPC 端波形已经实测。初次超时后的单独复采 `ble-d5-capture2_core0_window0.csv` 也得到 RX 低、flags `0x20`、错误 8；记录、解码和调用时间线分别为 `ble-d5-startup[1-3]_core0_window0.csv`、`ble-d5-startup-decoded.json`、`ble-d5-startup-timeline.json`，原始采集保留在缓存中。

电脑另一次 15 秒扫描收到 94 个广播源，但没有目标名称或业务 UUID，记录为 `ble-d1-advertisement-recheck.json`；此扫描发生在 D5 下载之前。不能将未广播归咎于手机 App，也不能仅凭 RX 低认定模组损坏。待用户确认蓝牙 FPC3 接线与电源灯，并测小板 C3.2（VCC）、FPC1.19／U2.42（UART_TX）对地电压；网表将 C3.2 接到 U2.9／22 的 VCC，LED 则接 +5 V，亮灯不能单独证明 VCC 正常。如果模块 TX 为高而 JTAG RX 仍为低，断电核对底板 FPC3.6→蓝牙 FPC1.19 的导通，再核对其到核心球位 W12 的链路；该连线目前仍是网表与排线假设，尚无实体导通证据。

### 接好蓝牙模块并重新上电后的复验

13:12 用户确认已重新上电、蓝牙模块已接好，要求重新烧录，并要求后续尽量采用增量综合。本次未修改 RTL、约束或 GAO 配置；核对全部输入及产物哈希后直接复用上述 D5 位流，没有运行综合或 P&R。后续在工具支持、输入边界允许时优先采用增量构建或复用已验证网表，仍保留变更所需的来源、时序和硬件核验，不将不同输入冒充既有通过结果。

下载前只读结果为 ID `0x0001081B`、UserCode `0x00000085`、Status `0x00026020`；再次执行 SRAM Program 后独立读回 ID `0x0001081B`、UserCode **`0xC11023D5`**、Status `0x00026230`。Flash 未写。完整证据在 `/home/sphenicidition/.cache/fpga-validation-20261023/ble-d5-repower-20261023-131246`，其中 `deployment.json` 记录下载与三次捕获调用区间，`decoded.json` 保存解码，`verification.json` 绑定日志和 CSV 哈希。

三次 JTAG 窗口的 RX 均恢复为高，UART error 低八位均为 0；这与此前未确认模块连接时的 RX 低和 UART 错误不同。0.35–1.47 秒窗口 outputs／BT enable 为 1／1，H5 TX 低八位为 0；4.47–5.58 秒仍为 1／1，H5 TX 低八位为 24；10.58–11.75 秒变为 outputs／BT enable 0／0、错误 8，H5 TX 低八位为 65。各窗口心跳均覆盖 16 个值，H5 link／initialized、HCI 命令及补丁片数仍为 0，ROM 仍是初值 `0xFF`。结论仍为 H5 握手超时，尚未进入 HCI／补丁；不能因 RX 高和无 UART 错误就认定链路通过。

13:14 电脑扫描 15 秒收到 105 个广播源，目标名称及业务 UUID 均未发现，见该目录 `advertisement.json`。当前 SRAM 仍为 D5，继续使用 JTAG 调试。下一步请求实物核对：断电测底板 FPC3.5→蓝牙板 FPC1.20（UART_RX）、FPC3.7→FPC1.18（BT_DIS#）导通，上电测 C3.2 对地 VCC；接好模块这一事实已确认，不再重复询问是否接入。尚无手机连接、录音下载或 BLE 硬件验收通过证据。

### 原版独立 BLE 对照：D6／D7

用户补充：FPC 连接正常，同一蓝牙板此前在其他 FPGA 上调通过；要求先检查线序，烧录原版独立蓝牙程序，暂停工作站合并。随后确认此前为 Xilinx 工程，并明确不用追查该工程。本轮不再以既有工作站或业务驱动作为独立对照，也不将用户的模块历史验收转写成本次 138K 通过。

再次逐项核对底板网表、蓝牙板网表以及核心板原理图第 6 页 C2400，四根线的逻辑对应未发现错误。FPC 编号按既有装配对应 `FPC3.n → FPC1.(25-n)`，不是同号直连；以下为文档对应，未新增实体导通测量。

| FPGA 球位 | 核心 C2400 | 底板 J2 | 底板 FPC3 | 蓝牙 FPC1 | 模块信号 |
| --- | --- | --- | --- | --- | --- |
| T14，FPGA 输出 | 90 | 56 | 5 | 20 | U2.43 UART_RX |
| W12，FPGA 输入 | 86 | 58 | 6 | 19 | U2.42 UART_TX |
| AA9，FPGA 输出 | 84 | 59 | 7 | 18 | U2.34 BT_DIS# |
| AA13，FPGA 输出 | 60 | 71 | 19 | 6 | U2.12 WL_DIS# |

新候选 **D6／`0xC11023D6`** 只实例化冻结的 `vendor/rtl8723ds_ble` 原版七个 RTL 文件，使用现有 `rtl8723ds_ble_sources.stage_vendor` 校验来源并应用其既有 Gowin ROM／同步器属性；没有采用 compact HCI/H5、业务协议、PCM、录音或工作站包装。参数保持 50 MHz、115200/8E1、BT_DIS 低 200 ms、高后等待 2000 ms、180 秒会话、30147 字节补丁。预期广播为 **`RTL8723-BLE`，FFF0／FFF1**，不是 Android 工作站业务服务。

板级顶层仅含配置后复位、三根输出使能和 256 位只读 GAO 观察。观察字高 128 位沿用 D5 布局；低 128 位依次为接收字节数 32、同步 RX 跳变数 32、完成发送字节数 32、最后 RX 字节 8、最后提交 TX 字节 8、协议错误低 8、运行毫秒低 8。接收跳变取原版 UART 第二级同步输出；原版同步链在 UART 启用前保持高，因此计数不覆盖模块最初上电至 UART 启用前的引脚活动。32 位接收／跳变计数覆盖后续启动观测区间，避免仅凭短窗口或低八位计数推断无数据。UART 错误为零本身不证明串口已连通。

D6 使用新的小工程综合基线；P&R 单独进程只读综合网表，确认没有重复综合。原版八项回归全部通过，记录为 `results/ble_regression_20261023_132854_497173/result.json`。综合 ROM 的 32768 字节填充镜像逐字节匹配，SHA256 `827718bbda291c2b74ca4ccae3b6892cec6305cbb39d83c0c4c211d21d044bdd`；物理引脚、两级同步链、仅第一级异步输入例外、级间 2 ns 限制和 GAO 仅采第二级均通过核对。D6 全局 setup／hold／recovery／removal 最差余量为 2.042／0.173／6.700／0.911 ns，50 MHz 实际 Fmax 55.686 MHz；GAO TCK 约束仍为 20 MHz。主设计报告为 16 BSRAM，GAO 另报 16 BSRAM，不能把主设计数当作包含 GAO 的总数。仍保留 PR1014 普通时钟布线警告。

13:30 下载前 JTAG 因重新枚举暂时读全 F；用户处理后 13:31 再读恢复 ID `0x0001081B`／UserCode `0x00000085`／Status `0x00026020`。13:34 D6 SRAM 下载成功，并独立读回 **`0xC11023D6`／`0x00026230`**。三个 JTAG 窗口均有 128 点和全部 16 个心跳值；末窗口 RX 字节／跳变计数均为 0、TX 完成字节数为 440、H5 RX 为 0、错误为 8，HCI 命令与补丁仍为 0，ROM 为初值 FF。18 秒电脑扫描未发现目标广播。结论是原版独立驱动仍在 H5 建链阶段超时，未进入补丁下载，不能归为工作站业务栈冲突，也不能据此认定模块损坏。

另做 **D7／`0xC11023D7`** 对照：25K 已验收板将 WL_DIS 标为 NC，而当前独立顶层驱动低；本蓝牙板 R2 又将其上拉。D7 只将该输出在活动期间改为高，BT_DIS 时序和 UART／H5／HCI 均不变。复用经哈希核验的 D6 综合网表，对唯一 `ble_wl_dis_n_s1` TBUF 常量作 GND→VCC 的明确 ECO，配套顶层同步反映该改动；采用 D6 `.p` 作为 `-inc_pnr` 输入，未重新综合。输入哈希、精确单一替换锚点和参考 `.p` 哈希均记录在 D7 清单。这是诊断对照，不是生产源政策。

D7 同样通过 ROM、引脚、接收 CDC 与全部物理时序检查；Fmax 56.448 MHz，最差 setup／hold／recovery／removal 为 2.285／0.175／12.691／0.911 ns。13:38 SRAM 下载后独立读回 **`0xC11023D7`／`0x00026230`**。末窗口 RX 字节和跳变仍为 0、TX 完成字节数 416、错误 8、HCI／补丁为 0；18 秒扫描同样无目标。该对照没有恢复通信，不保留为默认输出策略。

| 输入／产物 | D6 SHA256 | D7 SHA256 |
| --- | --- | --- |
| `inputs.json` | `374ef6f271940ccdcb1edee414aa5b0e493ee3522f2d543d1b4263d468eb1756` | `40b3f4f687fa84e8b778a9a890b7473a764fcf43647deea83821555421c3927a` |
| `impl/pnr/ao_0.fs` | `a5cfe00a4ac4ce7658b1dbb26c6714b6e7f42f42c8385ed55447618fa6c2a52c` | `de26846bb1a59b73862ec7b3fd604c1e6bd9366e3217ad368f46035272015944` |

本轮准备、检查与下载脚本，以及 `.vg`／`.gao`／时序报告／输入清单均保留在 `/home/sphenicidition/.cache/fpga-validation-20261023`：`prepare_ble_original.py`、`check_ble_original.py`、`run_ble_original.py`、`prepare_ble_wlan_compare.py`，候选目录为 `ble-original-c11023d6`／`ble-original-c11023d7`。实体原始日志、JTAG CSV 和 `decoded.json` 分别在 `ble-original-deployment-20261023-133402`／`ble-original-deployment-20261023-133802`；`deployment.json` 记录精确调用区间、身份读回与捕获哈希。调试器 FT2CH 新位置为 13937，后续热插拔仍须重扫。两次均只写 SRAM，Flash 未写。

13:40 已撤下 D7，直接复用 D6 已核验位流恢复原版独立基线，没有重复综合或 P&R。独立读回 ID `0x0001081B`、UserCode **`0xC11023D6`**、Status `0x00026230`；日志与部署清单在 `ble-original-restore-d6-20261023-133956`。当前 SRAM 为 D6，Flash 仍未写。若需要恢复本轮前的 GAO 配置，使用前文已核验的 D5 位流；不自动重载未核实适配新底板的 Flash 0x85。

退出条件：先解决独立原版驱动的 UART／H5 回包，再考虑工作站合并；若该诊断配置需要长期使用，应归入现有 `build_rtl8723ds_ble.py` 的显式板卡配置，不能将缓存脚本变成新的生产入口。下一步应聚焦模块使能／启动方式与端到端 UART 通路，具体最小观测点为模块 U2.43／FPC1.20 的 UART_RX，确认收到实际 115200/8E1 握手，再看 U2.42／FPC1.19 的 UART_TX 是否回应。现有发送计数只证明 FPGA 内部 UART 完成发送，JTAG 不能直接证明 FPC 另一端收到电气波形；目前没有广播、连接、通知或手机验收通过证据，也没有充分证据认定模块损坏。

### D8 完整 SYNC 捕获与规格核对

用户要求优先检查握手及软件，参考 RTL8723 规格书，必要时采用独立处理器验证，暂不追查此前 Xilinx 工程。取得 Realtek `RTL8723DS-CG` Rev.0.92（2017-07-24）原厂内容的 33 页数据表，来源为 [LCSC 数据表附件](https://atta.szlcsc.com/upload/public/pdf/source/20240905/58802A97879605D6EBE218F35C750A08.pdf)。7.5 节明确支持 H4 与 H5、默认波特率 115200；这不能确定本块模组熔丝选择的启动协议。文档描述的是裸芯片，不能将其 48 脚编号代入本板 44 脚模组网表。

同时对照 [Linux v6.12 `hci_h5.c`](https://github.com/torvalds/linux/blob/v6.12/drivers/bluetooth/hci_h5.c)：Realtek 启动设置为 115200、偶校验、关闭流控；SYNC 为 `01 7E`，响应为 `02 7D`。其使能与唤醒序列同时拉低再拉高。本板额外的 HOST_WAKE_DEV 对应 AB13→C2400.62→J2.70→FPC3.18→FPC1.7→U2.6。原先未显式驱动该脚，但模块 R3 已有 10K 上拉，Gowin 未用脚默认亦为弱上拉；因此不能将“此前没有驱动”直接宣布为根因。

新候选 **D8／`0xC11023D8`** 完全复用经核验的 D6 综合网表，只调整 GAO 为 65536 点、4 根观察线（同步 RX、内部 TX、BT enable、输出使能），采用 D6 `.p` 增量布局，未重复综合。完整物理检查通过，clk50 Fmax 55.686 MHz，setup／hold／recovery／removal 最差余量为 2.042／0.173／6.490／0.738 ns。输入清单 SHA256 `882d94a39f1ade3dcc8ea033fa73caa13be75894897612c8da51b840bc0ecc38`，位流 `impl/pnr/ao_0.fs` SHA256 `e8d7f2e4658fe186ac530c8c7495caf4aad415502ad0c2384256c719f828431c`。

13:50 SRAM 下载后独立读回 `0xC11023D8`／`0x00026230`，Flash 未写。证据目录为缓存 `ble-original-deployment-20261023-135023`。首个完整窗口输出使能为 1，独立按 434 个名义 50 MHz 周期逐位解码得到 **`C0 00 2F 00 D0 01 7E C0`**，全部偶校验及停止位正确；SYNC 头校验和也正确，RX 在该窗口保持高。后两个窗口输出已关闭，只可称为内部逻辑 TX，不能声称仍在 FPC 发包。原始 CSV 和 `uart_wire_decoded.json` 保留。这确认了 FPGA 内部发送的 SYNC 格式，仍未取得模块响应，也不等于在模组焊盘实测波形。

13:50 的 D8 SRAM 部署取代了前述 13:40 D6 状态。后续独立软核探测将分别测试 H5／8E1 与 H4／8N1，并显式控制复位、HOST_WAKE_DEV；只发送建链与读取本地版本所需命令，暂不带入工作站、业务协议或补丁下载。其仿真、综合、P&R、SRAM 与实体接收证据分阶段记录，不能用处理器启动或离线通过替代链路通过。

### D9 独立 VexRiscv 验证及 CTS 待确认项

**D9／`0xC11023D9`** 使用既有、经清单校验的 `usb_host_fs_8fc3` VexRiscv 与 simpleuart，以及 `workstation_usb2_cpu_bus.sv` 的 CPU RAM／MMIO／计时功能；没有实例化 USB 控制器、PHY、工作站业务、音频或蓝牙补丁。总线唯一暂存适配为为 64 KiB RAM 添加 block RAM 属性。独立 1584 字节 RV32I 裸机固件直接控制蓝牙使能、WL_DIS、HOST_WAKE_DEV 和 UART。先用原版 115200／8E1 UART 执行 H5 SYNC、CONFIG 与 HCI Read Local Version；6 秒未成功则重新复位，换独立 simpleuart 的 115200／8N1，直接发送 H4 `01 01 10 00`。每次 BT_DIS 低 250 ms，随后高并等待 2000 ms；WL_DIS 保持低，HOST_WAKE_DEV 随 BT_DIS 同时拉低再拉高。

CPU 执行真实固件的线级仿真覆盖 H5 成功、H4 回退成功、无响应超时三种情况，全部通过；对端模型独立检查字节、奇偶、停止位、SLIP、H5 头和 HCI 命令。仿真缩短毫秒计时器以加速运行，UART 位宽仍为 434 个时钟；虚拟 HCI 版本只用于测试，不是实物读回。测试台修正了全双工应答期间漏采主机起始位、复位中断旧 UART 字符应丢弃两项测试台行为，未因此改写冻结 UART 源码。

本候选建立新的小型 CPU 综合网表；后续约束调整只重复 P&R，明确使用单一综合网表、未重复综合。Gowin 将顶层初始化为高的同步寄存器保留为两套不同 INIT 的单元；按最终连线，实际第一级为 `input_sync_0_s2`，只驱动两个第二级 `input_sync_1_s1`／`input_sync_1_s2`。两套外部输入端点均仅在第一级作异步例外，实际级间路径均保留 2 ns 约束；没有切断第二级时序。物理 6 个引脚、384 位 GAO 寄存器及完整 65536 字节 CPU RAM INIT 逐字节核验通过，RAM 镜像 SHA256 `8febe969970677d60a36ed1d69da175dad2e27dacb31ba022329dbc90b4502b3`。Fmax 65.057 MHz，全局 setup／hold／recovery／removal 最差余量为 4.629／0.220／6.767／1.101 ns。主设计 36 BSRAM（其中 CPU 主存 32），GAO 另报 22 BSRAM；PR1014 警告仍保留。

| D9 输入／产物 | SHA256 |
| --- | --- |
| `inputs.json` | `0fd08660ffb2ca6e37b5ac1bfc6d6b839c7552bc6e4f44c172d7b81c72a745b9` |
| `firmware.bin` | `6052660c18ca2f20b6da8802eb04901885bc26feab0290a21e07a76274aa0cb5` |
| `impl/pnr/ao_0.fs` | `4f5786aa0c2e366d716ce9f84b5f10bcb0ade07c82daed87f82d3b05cd8b57d0` |

14:17 SRAM 下载后独立读回 ID `0x0001081B`、UserCode **`0xC11023D9`**、Status `0x00026230`。证据在缓存 `ble-cpu-deployment-20261023-141753`，五次 JTAG 捕获的心跳均覆盖 16 值，CPU 总线故障均为 0。H5 阶段收到 0 字节，发送累计 328 字节；换 H4 后共发送 332 字节，最终 phase=`EE`，仅收到单字节 `FF`。RX 跳变累计为 4，并非完全没有电平活动；29 次 8E1 错误集中于首次启动，后续不再增长。该探针在 BT_DIS 拉高时即启用 UART，可能把模块 UART 就绪前的电平变化解成错误／`FF`，不能把该字节称为 HCI 回包。H4 探针也未清除启动杂字节，因此即使后续出现完整事件，当前按首字节匹配的解析仍可能漏报；本次 RX 总共只有一个 `FF`，没有完整事件可供解析。复测前应先清除启动缓存并按 H4 包头重同步。

软核验证没有恢复通信，未收到 SYNC_RSP 或有效 HCI 事件，未取得芯片／ROM 版本、广播、连接或手机验收。不能宣称原版 H5 状态机已被证明是根因，也不能据此认定模组损坏。当前 SRAM 为 D9，Flash 未写；回退可直接复用上文 D6 的已核验位流，不运行历史 Flash 0x85。缓存 `ble-original-current-board.txt` 已更新为本次 D9 部署。准备、测试、检查、下载脚本为 `prepare_ble_cpu.py`、`tb_ble_cpu_probe.sv`、`check_ble_cpu.py`、`run_ble_cpu.py`，候选为 `ble-cpu-c11023d9`；诊断固件不作为生产输入。

随后取得 FN-Link 原厂编写的 [6223A-SRD V1.4（2022-05-25）模组手册](https://github.com/noniepark/RTL8723DS-BreakOut/blob/main/Datasheet/Fn-Link_6223A-SRD_datasheet_V1.4_20220525.pdf)，缓存 PDF SHA256 `566d1a4c66b7303300d7d84e46c4f575c6a4e573e1f655dbce28bda3ca8f8529`。其 12×12 mm、44 个侧边触点的 6／9／12／22／34／41／42／43 脚定义与现有网表相符，但网表没有厂商型号，尚未确认实物就是该型号，不能将相符当作型号证明。

该手册第 12 页列 **44 脚为 UART_CTS 输入**；第 16 页“Host 不支持硬件流程控制的接法”明确画出 **模组 CTS 接地**，UART_OUT→主机 RXD、主机 TXD→UART_IN，RTS 不接。41 脚表中注明模组侧为接地，因此现网表将 41 脚接地不能误报成把普通 RTS 输出短接。现有 `蓝牙.tel` 完全没有 U2.44 的连接，该脚也未引到 FPC；FPGA 软件关闭自身流控无法给悬空的模组 CTS 输入提供低电平。这是比继续重写 H5 更具体的待验证项，尚非已确认根因。

下一步先取得实物完整模组型号；若符合该手册，再测 U2.44 对地电平，并按模组手册验证无流控接法。未确认型号及实体 CTS 状态前，不指示短接未知触点、不盲目交换 UART、不继续将失败诊断固化。用户确认所需状态后，清除探针启动缓存／完善 H4 重同步，再复用 CPU 综合网表更新固件或复用 D6 重新验证；先以有效 H5／HCI 回包为成功条件，再恢复 BLE 初始化和广播。

### DA 修正探针启动接收后复验

为避免 D9 的启动杂字节影响下一次诊断，已完成上述软件修正，不等待实物信息：BT_DIS 拉高后先保持 UART 禁用 2000 ms，再开启 UART；H4 命令前清空旧接收缓存，并对非 `04 0E` 包头字节重新同步。新 1688 字节固件与测试台在缓存 `ble-cpu-firmware-r1`，没有修改原始 D9 输入或冻结 vendor。真实 CPU 固件的 H5 成功、H4 前插入 `FF 80` 杂字节仍成功、无响应超时三项仿真全部通过；H4 测试接收 9 字节、phase=`44`，确认能够越过这两个杂字节。

新候选 **DA／`0xC11023DA`** 复用经核验的 D9 综合网表，仅更新 32 个 CPU RAM 单元的 `INIT_RAM` 参数。先删除 INIT 参数比较整个网表，确认除 RAM 初始化外逐字相同；新 65536 字节 RAM 镜像再次逐字节核验，SHA256 `4f4aefde413f607668bcc634ea46ab045e0bc32416b2aa014bfa9eefdb1776a0`。使用 D9 `.p` 执行 `set_option -inc_place`，重跑布局布线，日志确认跳过综合。所有引脚、CDC、完整物理 setup／hold／recovery／removal 检查再次通过，Fmax 与最差余量均与上述 D9 相同；没有放宽时钟或时序例外。

| DA 输入／产物 | SHA256 |
| --- | --- |
| `inputs.json` | `eafc617104eaecba02355cfebd2fd274027892659bc6b0faab3c4f49e0715a2a` |
| `firmware.bin` | `b96762f38e4d77782f078bae0a78fb94326e2780a1da2d5996f3975e3fe223a8` |
| `impl/pnr/ao_0.fs` | `0da186b9846e508ee84bd4df9fe561ee6bc16f84ef69b09ae77f92e3f8399b80` |

14:27 SRAM 下载后独立读回 ID `0x0001081B`、UserCode **`0xC11023DA`**、Status `0x00026230`。证据在缓存 `ble-cpu-deployment-20261023-142722`，候选目录 `ble-cpu-c11023da`，额外准备脚本为 `prepare_ble_cpu_da.py`。五次 JTAG 捕获的 CPU 故障与 UART 误码均为 **0**，H5／H4 的接收字节数均为 **0**，累计 TX 332 字节、RX 跳变 4；最终 phase=`EE`、result=0。D9 的 29 次误码与 `FF` 已消除，仍没有 SYNC_RSP 或 HCI 事件，故启动杂字节是探针自身的问题，不能宣称它就是原版蓝牙不通信的根因。

**当前 SRAM 为 DA，Flash 未写，链路仍未验收通过。** 本轮没有合并工作站或改写生产蓝牙协议；不再为尚未确认的 CTS 状态反复改写协议。等待模组完整型号，以及型号匹配时的 U2.44 对地电平，以核对手册中的硬件流控前置条件。确认后可重新加载 DA 作 H5／H4 诊断，或按已核验身份恢复 D6 验证完整原版 BLE 初始化及广播。

### DA 重载后的实体电压检查

用户反馈 CTS 接近 0 V，当前没有实测依据支持“CTS 被拉高阻止发送”。随后首次核对板上身份时读到历史 Flash UserCode `0x00000085`，此前 UART 电压不能直接对应 DA 的输出预期。15:35 重新加载既有 DA，15:43 按用户要求再次加载同一已核验位流；没有重新综合或写入 Flash。部署证据分别在缓存 `ble-cpu-deployment-20261023-153538`、`ble-cpu-deployment-20261023-154316`，均独立读回 `0xC11023DA`。

15:43 重载后，用户再次测得模组外圈 **43 脚 UART_IN 为 0 V、42 脚 UART_OUT 为 3.3 V**，随后报告 **34 脚 BT_DIS# 为 3.3 V**。34 脚已有 R1 上拉，其高电平表示模块解除 BT_DIS#，不能单独证明 FPGA 至模组的连通性。只读 JTAG 采样保存在 `ble-voltage-check-20261023-154731`：phase=`EE`、TX 累计 332、RX 字节 0、RX 跳变 4、UART 错误及 CPU 故障均为 0，心跳正常；之后再次读回 UserCode 仍为 DA。该 GAO 总线没有直接观察 TX 焊盘或当前输出使能，不能用软件空闲预期替代实体电压。

固件结束后按现有 RTL 应保持 UART TX 空闲高电平。最终物理报告将 TX 映射为 T14／Bank 5、LVCMOS33、8 mA；TBUF 的低有效 OEN 由复位释放与 `control[3]` 的 NAND 产生，与 RTL 一致。下一测点为底板 **J2.56／FPC3.5**，用于区分 FPGA 输出侧与 FPC 后端的电平差异。网表路径为 T14 → 核心板 C2400.90 → 底板 J2.56 → FPC3.5 → 模组板 FPC1.20 → U2.43；其中跨 FPC 的反序关系仍待实体连通测量确认。当前先沿该路径定位，不依据现有数据认定模组损坏或协议根因。

### DB 直接观察 UART 输出数据与使能

用户已在 PCB 中重新确认 **FPC3.5＝BANK5_T14＝J2.56**，撤回此前 FPC3.6 的编号判断。16:05、16:28、16:32 均按用户要求重载同一 DA；最近一次证据为 `ble-cpu-deployment-20261023-163205`。随后用户反馈底板 FPC3.5 与模组 U2.43 **均为 0 V**，因此需要直接核对 FPGA 输出逻辑，不能只归因于 FPC 两端电压差。

新观察候选 **DB／`0xC11023DB`** 完全复用 DA 的综合网表、固件、引脚及约束，只在原 384 位 GAO 之外增加 16 位输出／使能／控制观测。综合网表 SHA256 仍为 `4038a31e1d90ee541bcdd6bfad41f7daad10ba90e817b781c04744a49502bc22`，CPU RAM 全 65536 字节核验通过，沿用 DA 的三项固件仿真记录。采用 DA `.p` 增量布局，日志确认跳过综合；完整物理引脚、CDC、setup／hold／recovery／removal 检查通过，clk50 Fmax 65.057 MHz，四项最差余量为 4.629／0.210／6.638／1.101 ns。设计 36 BSRAM，GAO 单列 24 BSRAM；PR1014 警告保留。

| DB 输入／产物 | SHA256 |
| --- | --- |
| `inputs.json` | `5eb19124998b0bdd63b26a7c33a9e176e47015fc2595be1b27a34e6875923099` |
| `impl/pnr/ao_0.fs` | `6f90efdf068398ff157f4dcdb9a1235154a6d587bad9dc00cdbfb6cee4562015` |

16:40 SRAM 下载后独立读回 **`0xC11023DB`**，Flash 未写，证据为 `ble-cpu-deployment-20261023-164028`。首次采集本身成功，GAO 将新增 16 位与原 384 位导出为两列；修正解码器的列解析后，继续只读采样，未为解析问题重新综合或重烧。启动等待及结束后的三次稳定采样均显示 **TX TBUF.I (`n469_4`)=1、TBUF.OEN (`ble_uart_tx_o_7`)=0、复位已释放**；结束时 `control[5:0]=0x3D`、H4 TX=1、phase=`EE`、CPU 故障为 0。该证据确认逻辑侧请求驱动高电平，仍不能直接证明焊盘的电压或实体连通性。接收仍为 0 字节，未取得蓝牙链路验收。

候选、准备和检查证据在缓存 `ble-cpu-c11023db`，额外准备脚本为 `prepare_ble_cpu_io.py`；它只用于观察，回退复用上文 DA 的已核验位流，不改变生产输入选择。下一步按用户确认的断电操作移除蓝牙 FPC，再上电并重载 DB，测底板 FPC3.5 空载电压，以区分 FPGA 输出侧与外接链路的影响。

用户已确认完成断电、拔下蓝牙 FPC、重新上电。16:45 重载同一 DB 并独立读回 `0xC11023DB`，证据为 `ble-cpu-deployment-20261023-164519`；部署记录明确注明 FPC 断开。结束后的两次采样仍为 TBUF.I=1、OEN=0、复位已释放、CPU 故障为 0，RX 跳变为 0。当前 SRAM 为 DB，Flash 未写，等待底板 FPC3.5 的空载实体电压；断开模组时的无接收不作为蓝牙故障或验收结论。
