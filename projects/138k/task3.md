# task3：双 138K 工作站

M 负责独立实时演奏与最终输出；W 实际承担识别、手机音频接收/解码及录音存储。扩展功能通过 LCD 口的有界通信加入，基础演奏不等待 W，也不等待蓝牙往返。task2、单板工作树和已冻结候选继续保留。

本文只记录分工、接口约束与验收入口，不参与构建或来源锁。版本实验和失败记录保存在 `push2_workstation/usb_a/reports/`，不把历史报告改成新候选的证据。

最新阶段为 [v46 完整综合／消费者证明检查点](push2_workstation/usb_a/reports/DUAL138K_TASK3_PREBOARD_V46_20261108.md)：M `ae6090a0ca3e94c4`、W `a6e2dbc2c10da5fd`，标准综合审计 29/29、26/26 全部通过。已修复 W 转义向量解析及精确 LUT3 映射检查，M 121 个变化消费者状态有条件 next-Q 证明和归纳不变量。两板编译闭包可重复；W 身份仍受诊断报告绝对路径影响，尚需修复。新物理运行 `D21108AF`／`D21108BF` 正在进行，未取得本版时序放行；不得加载。历史 [v43 失败](push2_workstation/usb_a/reports/DUAL138K_TASK3_PREBOARD_V43_20261108.md)、[v38 物理失败](push2_workstation/usb_a/reports/DUAL138K_TASK3_PREBOARD_V38_20261108.md)保留；[SRAM清单](push2_workstation/usb_a/reports/DUAL138K_TASK3_SRAM_CHECKLIST_20261108.md)仅准备步骤。

## 赛题要求与项目目标

依据[赛题原文](../../docs/requests/全国大学生嵌入式芯片与系统设计竞赛'2026FPGA赛道选题指南-高云半导体.pdf)的选题二，PDF 第 15–16 页（正文第 13–14 页）：

| 层级 | 要求与验收 |
| --- | --- |
| 基础 | 至少两个独立可控演奏维度；FPGA HDL 逐声部、逐采样合成；至少四个独立声部同时发声；实时变调、ADSR、混音；经 I2S 和真实 DAC 发声；控制到声音总延迟 ≤10 ms。 |
| 扩展 | ≥32 复音或原文规定的等效并行合成规模；≥3 维表情、≥2 种音色及硬件效果器；≤5 ms 且确定性无抖动延迟；实时可视化、脱机指引及手机联动。 |
| 项目保留 | 保留普通 32 声部、现有矢量 8 声部及项目 32 声部目标，不降为四声部交付。矢量当前实现没有 32 声部证据；以同时活跃、可闻的独立声部和实际输出采样率验证，不能仅统计查表次数。 |
| 扩展媒体 | TF 直读、手机流式音频、录音回放属于辅助功能。赛题禁止用预录 PCM、预置推流或整段录音触发代替基础实时合成；基础演奏演示必须独立验证。 |

## 两板分工与实际路径

| 子系统 | M | W | 当前边界 |
| --- | --- | --- | --- |
| 交互、合成与参数 | 最终交互；唯一参数应用点；普通 32 声部、现有矢量 8 声部合成、变调、ADSR、混音、基础效果与采样调度 | 扩展结果和请求的生产方 | 不新增第二份权威参数；保留既有 18 位事件和生命周期语义。Push 与 25K 交替使用同一 USB-A 口。 |
| TF 与选曲 | TF 实际接在 M；真实选曲、SD/FAT/CRC 检查、直读播放；另一路有界分析源 | 接收分析 PCM，存入 W 自己的 DDR 任务区 | W 不直接访问 M 的 TF 或 DDR；分析背压不得阻塞基础音频。 |
| 识别与 Push 指导 | 收集结果，完整成功后发布指导；最多 2048 音符 | 实际 CQT/CNN/Viterbi、模型与工作存储；允许用部分 BSRAM 加速 | 保留模型、任务身份和错误状态；有真实模型离线证据，目标板加载、质量及完整歌曲链路仍待验证。 |
| 手机与 D 模式 | 原 PCM1 接收、最终源选择、DSP 与 DAC 输出 | 蓝牙模块优先放 W；HCI/Classic/SBC/GATT 及手机流式接收/解码 | 路径为手机→W→LCD→M PCM1→DSP→I2S/DAC；持续音频能力 CAP3 尚未开放。 |
| 录音与下载 | 最终物理输出 tap；256 帧有界缓存；W 的真实源需求经 M 同意后 ARM | 唯一 CPU/BLE 录音对象、W 本地 DDR、封口、读取及下载 | 已选 2,880,000 帧、48 kHz stereo16，容量 60 秒；44.1/48 kHz 后端已通过离线回归，跨板 ARM 仍仅接纳 48 kHz。真实 60 秒录音和下载未验收。 |
| 可视化 | HDMI 物理输出及统一显示状态；现有 Push 绘制 | 后续可迁移 FFT/频谱等分析，回传有界快照 | 按实际资源、关键路径和通信余量选择，尚未选入整机的迁移不能算收益。 |
| 重型效果 | 当前完整候选仍保留本地混响；远程处理必须超时回退且不停止采样 | 单个真实混响、完整本地效果链与 DDR 栅栏的独占租约组合已通过源码仿真 | 子系统综合证明 M 可移出 20 个 SDPB 和 19 个 MULT27X36；新租约尚未接入完整 paired 候选，不能作为整机资源减少。 |

D 模式需逐键验证“按下启用对应效果，松开结束”，包括重复按键、PANIC、断链和源切换。当前完整候选的 D 效果在 M，跨板部分是 W 接收/解码后的 PCM；后续迁移效果时必须重新记录处理位置、回退与最终输出路径。

## LCD 连接与通信预算

用户确认网络按 `M.FPC4.n → W.FPC4.n` 一一对应，不按排线外观做 `n → 41−n` 反转。副板与主板之间仅有 LCD 有线连接；各板只访问本板外设。两块目标板默认未接电脑，当前电脑上的 138K 属于其他分支。

引脚、互补方向及保留脚见 [pinplan](push2_workstation/usb_a/boards/custom_138k/task3_lcd_probe_pinplan.json)。接口采用两个独立的四相 req/ack、4 位 bundled-data 通道，状态机使用本板 50 MHz 时钟，LCD 线不作为 FPGA 时钟。名义 I/O 为 3.3 V；实际 VCCIO、接触、电源拓扑和方向仍需检查，尤其 FPC4 的 1/2 脚连接 +5 V，不能靠 RTL 隔离。

沿用维护中的 [LCD framing](push2_workstation/usb_a/rtl/workstation/workstation_task3_lcd_transport.sv) 与 [typed channels](push2_workstation/usb_a/rtl/workstation/task3_paired_channels.vh)，不替换 USB PL/BLE 业务协议。每个线帧固定 52 字节（18 字节头、32 字节 payload、2 字节 CRC16）。PCM 按 stereo16、每采样帧 4 字节计算：

| 流量 | 48 kHz 预算 | 说明 |
| --- | --- | --- |
| 一路原始 PCM | 192,000 B/s 净数据 | 不含身份、确认及物理握手。 |
| M→W 分析或录音 block6 | 每路 416,000 B/s 线帧字节 | 6 帧/包、8,000 包/s；不足 6 帧的包和信用包另计。 |
| W→M 手机 window5 | 理想满包下限 499,200 B/s；当前 128 帧块按 26 包计算为 507,000 B/s | M→W 还需等量窗口 ACK；不能只看净 PCM 速率。 |
| 手机数据及最少 snapshot/COMMIT | 每方向至少 546,000 B/s | 每个 128 帧块再计两次请求/回复；更多轮询另计。 |
| 分析＋录音＋手机同时运行 | M→W 至少 1,378,000 B/s；W→M 至少 546,000 B/s | 仍不含 block credit、额外轮询、初始化、状态、heartbeat/probe、服务间隙和拥塞。 |

44.1 kHz 净 PCM 为 176,400 B/s，满 block6 为 382,200 B/s；这是算术预算，44.1 kHz 录音后端的离线通过也不代表跨板业务已支持该采样率。现有识别/跨板录音仅接纳 48 kHz。双向通道分别核算，不能把两个方向带宽合并使用。

block RX 为每流 8 包、每包最多 6 帧，满包仅覆盖 1 ms@48 kHz；M 录音 tap 的 256 帧覆盖约 5.33 ms。队列不能消除持续带宽不足。蓝牙 UART/HCI 吞吐也不等于手机端到端音频吞吐，音频或控制用途须由实测吞吐、抖动和延迟决定。

新增[理想 LCD 回显与混响预算验证](push2_workstation/usb_a/reports/DUAL138K_TASK3_LCD_REVERB_BUDGET_20261106.json)：使用现有 channel-0 framing 和实际 transport/PHY RTL，在两个 W 时钟频率、三个相位下共取得 24 次有序回显，耗时 57.96–62.12 μs，CRC/序号/溢出计数均为零，业务始终关闭。它不含 W 效果计算、媒体队列和真实线延迟，不能作为物理最坏延迟；但所有观察均超过未选入远程混响接口的 512@76.8 MHz 周期（6.67 μs）期限。不能直接接入或仅延长期限；需异步 wet 流、明确附加延迟和有界队列，并复用 W 现有效果资源。

业务准入保持 `link_ready && ALLOW_BUSINESS && budget_validated`；上电默认关闭。已有 200 ms、实际固件负载与理想连线的离线协同仿真，不能据此打开物理音频能力。实测至少覆盖双向有效载荷、往返延迟及尾部抖动、并行流、接收方停顿、停钟、拥塞恢复和丢包/CRC/序号计数。

## 失败、取消与输出约束

| 边界 | 必须保持的行为 |
| --- | --- |
| 断链、重连、取消、PANIC | 撤销当前租约和在途业务；按 boot/session/task/generation 及实际 owner 身份隔离旧结果；重连不能重放旧命令或自动续播。新 ARM 必须满足对象已退出等条件。 |
| 溢出、超时、错误采样帧 | 计数并显式终止对应分支；录音不能悄悄缺帧后仍称成功，识别不能发布部分失败曲谱。 |
| 控制接受与应用 | posted window 本地完成仅表示有界接收；M 的真实 ACK 和 applied barrier 才证明原 PCM1 已完成，缓存回复不能变成参数或输出权威。 |
| 基础音频 | 通信、CNN、显示、TF 操作、BLE 和下载均不能停止采样调度；扩展分支失败不拖住 M 的独立演奏。 |

## 当前候选与下一阶段

2026-11-08 最新源码／综合检查点为[v46](push2_workstation/usb_a/reports/DUAL138K_TASK3_PREBOARD_V46_20261108.md)，配置、严格综合复用收据、两板资源、完整审计、状态对应范围和复现缺口均有独立证据。v15 物理运行结果待收齐；已完成的旧物理结果仍为[v38](push2_workstation/usb_a/reports/DUAL138K_TASK3_PREBOARD_V38_20261108.md)，属于 v37 来源，不继承给 v46。task2、单板及历史回退保留，本轮未上板。

2026-11-08 上板前收尾仍在进行，最新范围、修复、失败记录和验证入口见[本轮报告](push2_workstation/usb_a/reports/DUAL138K_TASK3_PREBOARD_20261108.md)，步骤见[SRAM 清单](push2_workstation/usb_a/reports/DUAL138K_TASK3_SRAM_CHECKLIST_20261108.md)。本轮止于离线候选，不执行 SRAM 或 Flash 操作；真实 LCD 吞吐、DAC 延迟和整机演示留到正确目标板的下一阶段。

### 2026-11-06 保留的检查点与失败证据

截至 2026-11-06，两板 v21 保留为 paired 来源检查点；本轮另登记 M 独立演奏、W USB 退役和 W 显式 96 KiB 分 bank 配置。M 经授权修复 DDR 头文件封装后完成综合；显示邮箱的旧审计清单已补齐并通过完整标准综合审计，唯一一次 P2R0 已完成；PLL/启动子门禁通过，音频 setup 与 DDR hold 仍失败；两个 W 方案各完成一次综合及一次 P2R0。另有未选入的 M capture ID 一致性比较实验 F3。v21 将完整 32 位 capture ID 顺序比较分成四组；保留零值、相等值及回绕拒绝，不增加状态或等待周期。其中 W v21 的配置与全部编译字节保持 v20 原样，继续实际承担识别、手机接收/解码及唯一录音对象。完整时序、CDC/PLL 与目标板验收仍未完成。

[本轮收敛核查](push2_workstation/usb_a/reports/DUAL138K_TASK3_CONVERGENCE_20261106.json)逐项复核了最新 goal：A 固定 M 独立演奏配置；B/C 将 W 实际 BSRAM 从 E9 的 336 降至 287，保留真实 CNN、手机解码和唯一录音对象；异步混响与单引擎租约完成局部验证，但完整并发超过现有 LCD 容量，因此保持 M 本地效果。三个方案的首轮综合／P&R 已结束；A 的两次解析失败重建按用户授权单列，不增加布局试跑。本轮架构取舍已明确，最终双板工作站尚未验收。

新增[采样边沿验证](push2_workstation/usb_a/sim/audio/run_pitch_capture_boundary.py)直接使用与 F7 冻结输入相同的音高、普通及矢量引擎。注册参数在采样前一／两拍更新，38 帧完成 76 次实际捕获检查，其中 36 帧保持普通 32／矢量 8 声部活跃；37 次采样间隔检查通过，覆盖 48→44.1→48 kHz 与 PANIC 后重新演奏。独立模型拒绝输入滑音加寄存器、输出音高加寄存器两个反例，且两类消费者均捕获到错误值；不选用这种直接加拍方案。既有 17 项来源、8 项演示和 95,714 个音高模型采样点回归通过。本轮只有诊断与文档变更，没有新综合、P&R 或位流。

再次核对 M 的 614／W 的 684 个冻结文件、完整清单及位流哈希，均保持原样；从当前源码根重验旧候选时，分别因 5／7 个后续构建或审计工具变化而拒绝，未刷新历史来源锁。后续先处理 W `n737_9` 的完整消费者证明及 M 参数应用／采样边沿契约，再按真实路径推进时序诊断；完整 CDC、时序、LCD 实测与目标板验收仍各自保留。未接触当前供其他分支使用的板卡。

| 板与阶段 | 来源身份 | 实际证据 |
| --- | --- | --- |
| M 独立演奏 A，DDR 解析修复 | `custom138k-workstation-task3-m-independent-ddr-map-v1-8cf0f8e10a9efb34`；[证据](push2_workstation/usb_a/reports/DUAL138K_TASK3_M_DDR_ALIAS_REPAIR_20261106.json) | 854 个来源锁、614 个冻结文件、267 个编译输入。130.22 秒完成综合：43158 Register、48137 LUT、11422 ALU、198 BSRAM 等效、99 RAM16。普通 32 声部存储、矢量子树及 CPU48 全部 ROM 字核对通过；修订外部审计后完整标准综合审计通过，保留初次 17/18 失败记录。[F7 物理证据](push2_workstation/usb_a/reports/DUAL138K_TASK3_M_INDEPENDENT_PHYSICAL_20261106.json)：P2R0 在 512.18 秒完成，Logic 60564、Register 43158、BSRAM 238/340。音频 Fmax 73.696/76.8 MHz，setup/hold 为 -0.548/-3.535 ns；PLL/启动子门禁通过，整体仍未放行。 |
| M v21 实验来源 | `custom138k-workstation-task3-m-paired-checkpoint-v21-cac552dbb92de6d2`；[配置](push2_workstation/usb_a/boards/custom_138k/workstation_profile_task3_m_paired_checkpoint_v21.json) | 979 项来源锁、287 项编译输入、693 项准备文件。完整 M 综合：58408 Register、68670 LUT、28061 ALU、212 BSRAM 等效、254 RAM16；审计 21/23。相对 v20 仅批处理器编译字节改变，LUT −132、ALU +29，寄存器和存储不变。 |
| M v21 F0 物理比较 | `custom138k-resource-physical-D21106F0`；[本轮证据](push2_workstation/usb_a/reports/DUAL138K_TASK3_M_CAPTURE_COMPARISON_20261106.json) | 同约束 P3R0，816.13 秒完成布线与位流生成；Logic 99061、Register 58408、BSRAM 253/340、CLS 61686/69120。setup/hold/recovery/removal 为 -4.468/-3.665/-4.263/-0.141 ns；未通过完整物理门禁，未部署。 |
| M v21 F1 物理预算实验 | `custom138k-resource-physical-D21106F1`；[PLL 路由实验与远程复核](push2_workstation/usb_a/reports/DUAL138K_TASK3_M_PLL_RESET_EXPERIMENT_20261106.json) | 相同综合 VG、CST、P3R0；只追加更严格的 TMDS PLL RESET 6 ns 预算及像素专项报告。831.70 秒完成布线，资源及四项最差裕量与 F0 相同；PLL RESET 仍为 10.870 ns。该实验未改善时序，未选入生产配置。 |
| M v21 F2 输出布局实验 | `custom138k-resource-physical-D21106F2`；[局部布局与完整门禁](push2_workstation/usb_a/reports/DUAL138K_TASK3_M_TMDS_OUTPUT_LOCALITY_20261106.json) | 保持 F0 综合 VG、SDC、P3R0 及全部 IO，仅追加 60 个 TMDS 输出寄存器/反相门的区域约束。688.18 秒完成布线；Logic 99075、Register 58408、BSRAM 253/340、CLS 61705/69120。setup/hold/recovery/removal 为 -4.231/-3.608/-3.953/-0.847 ns；HDMI、clk50、audio Fmax 回退，不选入生产配置，未部署。 |
| M F3 一致性比较实验 | 来源 `custom138k-task3-m-capture-identity-experiment-5f4bc994d089b579`；物理尝试 `custom138k-task3-experiment-physical-D21106F3`；[证据](push2_workstation/usb_a/reports/DUAL138K_TASK3_M_CAPTURE_IDENTITY_EXPERIMENT_20261106.json) | 完整 M 综合 208.25 秒成功：58408 Register、68675 LUT、28057 ALU、212 BSRAM 等效、254 RAM16。P3R0 运行 909.86 秒后 PR0004 退出，日志为“0 unrouted nets”；部分 P&R 报告为 Logic 99060、BSRAM 253/340、CLS 61787/69120。没有 STA、SDF 或位流，不选入生产配置。 |
| M v20 EF 保留对照 | `custom138k-resource-physical-D21106EF`；[证据](push2_workstation/usb_a/reports/DUAL138K_TASK3_M_DEMAND_IDENTITY_20261106.json) | BSRAM 253/340、CLS 61874/69120，setup/hold/recovery/removal 为 -5.106/-3.373/-4.674/0.281 ns。保留原始来源：EF 源于初次 v20，终版 v20 通过编译字节相同比对引用，未改写 EF 身份。 |
| W v21 保留 paired 来源 | `custom138k-workstation-task3-w-paired-checkpoint-v21-d8fa5871d2958f19`；[配置](push2_workstation/usb_a/boards/custom_138k/workstation_profile_task3_w_paired_checkpoint_v21.json) | 1027 项来源锁、200 项编译输入、675 项准备文件。配置及全部编译字节与 v20 相同；本阶段没有新 W 综合或物理运行。 |
| W v14 E9 保留物理结果 | `custom138k-resource-physical-D21106E9`；[证据](push2_workstation/usb_a/reports/DUAL138K_TASK3_W_CNN_READY_SDC_20261106.json) | 真实 BSRAM 336/340、CLS 58819/69120；审计 11/18，setup/hold/recovery/removal 为 −7.224/−4.350/−7.947/−0.234 ns。结果保留原身份，未部署。 |
| W USB 退役 F5 | 来源 `custom138k-workstation-task3-w-paired-no-usb-v1-366eee69d13d8733`；物理 `custom138k-resource-physical-D21106F5`；[证据](push2_workstation/usb_a/reports/DUAL138K_TASK3_W_USB_RETIREMENT_20261106.json) | 实际物理 BSRAM 303/340，比 E9 少 33 块；Logic 79556、CLS 56313/69120。317.30 秒完成布线和位流生成，setup/hold/recovery/removal 为 −2.520/−4.194/−7.381/−0.424 ns；审计 17/20，PR1014 仍在，未通过完整门禁，未部署。 |
| W 分 bank ROM F6 | 来源 `custom138k-workstation-task3-w-paired-banked96-v1-c5aa7e9c87dd9908`；物理 `custom138k-resource-physical-D21106F6`；[证据](push2_workstation/usb_a/reports/DUAL138K_TASK3_W_BANKED96_20261106.json) | 物理 BSRAM 287/340，比 F5 少 16 块、比 E9 少 49 块；48 pROM＋8 scratch SDPB 及全部 24576 个初始化字核对通过。403.42 秒完成 P2R0，setup/hold/recovery/removal 为 −2.542/−4.334/−6.654/−0.609 ns；审计 18/21，PR1014 仍在，未通过完整门禁，未部署。 |

[v21 源码验证](push2_workstation/usb_a/reports/DUAL138K_TASK3_M_CAPTURE_COMPARISON_20261106.json)完成 61 项测试方法，无跳过。新批处理器与精确逆变换得到的完整 v20 参考，在真实异步 APB/PCM owner 测试中逐周期比较 18135 个周期、全部 11 个公开输出；955 项 owner 检查通过，取消、断链、超时及回复背压期间音频采样继续推进。维护 RTL 默认仍用直接无符号比较，只有显式 M v21 选入分组；局部比较与完整消费者/CDC 验证分别记录。

[F3 一致性比较实验](push2_workstation/usb_a/reports/DUAL138K_TASK3_M_CAPTURE_IDENTITY_EXPERIMENT_20261106.json)另通过 27 项测试方法、4290 项真实 RTL 四态比较及完整异步 owner 等价检查。实际综合 VG 与失败 P&R 的 VO 均证明局部比较全部 2^64 组赋值等价，拒绝漏位反例；相同 memory fault→reply CE 的最长无权拓扑由 50 降至 27 级。这不是可敏化或 STA 证明。287 项父编译输入中仅一个可逆替换，另新增一个组合模块；693 项父准备文件、42 份历史描述符和标准配置保持原样。PR0004 根因未确定，缺失的 STA/SDF/位流不能由“0 unrouted”或局部证明替代。

物理候选均未通过完整门禁。表中的 F0/F1/F2、EF 与 W E9 保留各自来源和哈希；F1 严格 RESET 预算和 F2 输出区域约束未选入。F2 虽缩短输出数据段，整机 Fmax 和 removal 仍回退。像素专项 STA、PLL/startup、hold、完整 CPU release/consumer、held-handshake 与 TF CDC 的失败以各报告为准。所有初次环境、工具和审计失败均保留，未刷新历史哈希或放宽时钟/例外。

新增[保留物理网表的 startup 清单](push2_workstation/usb_a/reports/DUAL138K_TASK3_LCD_REVERB_BUDGET_20261106.json)发现，旧审计固定要求 DFFRE→DFFCE 且第二级 CLEAR 为低；M F0 实际为七组 DFFCE→DFFCE，直读 TF 下另外两组不存在；W E9 为四组 DFFCE→DFFCE、两组 DFFRE→DFFCE。已发现的首级 Q 均只连第二级 D。此清单仅用于定位审计契约不匹配，尚未证明来源绑定、复位根和完整运行语义；审计未修改。后续须按精确配置与真实 reset-root 建立契约及破坏性测试，不能全局放行任意原语或忽略缺项。

识别完成信号已确认是保持状态，实际 USB meta→sync 两级存在；任务取消、重新 ARM、完成与曲谱数据的顺序仍需完整证明。真实 32 声部普通/矢量合成、TF→W CNN→Push、手机 D 按放效果及 60 秒录音/下载并发也仍需各自验收，不能由子系统离线通过替代。

远程成果由 `f96df276` 审查后选择性合入，且仍为当前祖先：PR #2 的 CPU48 分 bank RAM 已用于 M/W，实际网表逐字验证 24 块、12288 个 ROM 字，原对照为 32→24 块；W 的物理 BSRAM 从 344 降至 336/340。PR #3 的独立 USB/HDMI 诊断、目标域复位与状态新鲜度修复也已保留，该诊断不作为完整工作站的真实声部证明。ADSR/TF ring 仍是实验，重复录音后端未选入，详见[PR 取舍](push2_workstation/usb_a/reports/DUAL138K_TASK3_PR_INTEGRATION_20261103.json)。架构审查时再次 fetch，本地与远程当时均为 `f84fa3c7`，没有新增提交。F3 的完整 M 网表重建仍确认 CPU48 优化生效。

按最新 goal，先完成[有界架构审查](push2_workstation/usb_a/reports/DUAL138K_TASK3_ARCHITECTURE_REVIEW_20261106.json)，暂停重复比较器、局部布局及路由参数试跑。架构审查阶段没有新综合或 P&R；后续 A/B/C 实验另行记录。W E9 继续保留原身份：v14 与 v21 配置相同，但一个编译文件的字节不同，差异位于 W 未启用的 TF direct 分支；不能称 E9 为 v21 的新物理结果。

| W 实际资源用途 | 核查与处置 |
| --- | --- |
| USB：2570 Register、4858 LUT、31 BSRAM 等效 | 事件只到 W 本地 `u_managed`，没有板间 USB 事件通道。手机 PCM/时钟 APB 已转发 M，USB CPU 与 AE350 解码 CPU 分离。优先在显式 paired-W 配置裁掉 USB；保留 W-demo/25K 回退。 |
| 启动存储：64 pROM＋8 SDPB | 真实固件镜像 90416 B；其中 24880 B 为运行时仍执行的 ROM 代码。实际 32768 个初始化字已逐字核对，不能删除 ROM。可评估三 bank、96 KiB ROM，预计少 16 pROM；保留 scratch、ILM/DLM、地址和 16 KiB 栈。原配置的 linker/验证器只接纳 128 KiB；方案 C 使用独立物理容量校验，保留原 linker 地址。 |
| 本地效果：4326 Register、4122 LUT、32 BSRAM 等效 | paired W 无本地手机 PCM，且输出强制静音；本地 USB 参数、效果、时钟/串行器和 delay DDR 客户端仍在。混响本身占 20 BSRAM 等效及 19 MULT27X36，优先复用。裁剪需一起处理私有参数、DDR 请求与 readiness，不能直接接常量掩盖依赖。 |
| 识别、解码与录音 | 保留实际 CNN/CQT/Viterbi、HCI/SBC/Classic，以及来自 M 最终输出 tap 的唯一 C/BLE DDR 录音对象。 |

上表是 E9 对应综合的包含式层级统计，父子项不能相加，也不能当成新配置的物理收益。首轮限定以下三个方案，每个最多一次综合、一次 P&R；先完成各自局部验证再消耗预算，结果未改善且无新诊断依据时停止。用户另行允许修复输入封装、解析等低级错误后重建；这些调用单列记录，不扩展布局或路由参数试跑预算。

| 顺序与方案 | 验证前预期收益 | 成功条件 |
| --- | --- | --- |
| A：M 独立演奏配置 | 沿用现有 M-demo/provider 与构建入口，把独立交互→普通 32 声部／现有矢量 8 声部合成→DAC 的真实边界固定下来；不预称时序或资源改善。 | 保留两个交互维度、变调、ADSR、混音；验证真实源到串行器和所有声部；完整 CDC/PLL/时序通过后再测目标板控制到声音延迟。 |
| B：paired W 裁掉未转发 USB | 参考子树最多释放 31 BSRAM 等效及 4858 LUT，实际整机收益须测；M 暂不因此减资源。为后续实际迁移留余量。 | HCI/手机代理、CNN、唯一录音对象与固件保持正确；网表不含 USB host/CPU/owner，物理 BSRAM 降低，门禁保留。 |
| C：W 显式 96 KiB 分 bank ROM | 64→48 pROM 的目标；现镜像余量 7888 B。单改数组深度可能仍填充到原块数，不能算收益。 | ELF、启动及运行地址不变、镜像逐字一致；范围/别名与 AHB 时延检查、48 个实际 ROM 块及完整物理门禁通过。 |

[方案 A 阶段证据](push2_workstation/usb_a/reports/DUAL138K_TASK3_M_INDEPENDENT_20261106.json)：新增显式 `custom138k-workstation-task3-m-independent-v1`，复用 M-demo provider 和远程 CPU48 RAM，不修改原描述符及 paired/task2 回退。最终准备身份为 `custom138k-workstation-task3-m-independent-v1-dca520d2406ed45f`；840 个来源锁、612 个冻结文件、267 个编译输入，USB 固件 21380 B，48 KiB RAM。该独立配置验证基础演奏边界，TF、识别、手机与唯一录音对象继续由已有 paired 配置推进。

45 项来源／审计回归通过；实际音频子系统仿真检查 22532 帧，普通 32 声部和矢量 8 声部在 48/44.1 kHz 下共 12 次活跃数量检查、12 种物理串行取消边界通过。Push 入口与禁用 TF 边界回归通过。此证据使用真实 DSP、DDR 模型、DCS、最终 PCM 和 I2S，尚不等同于 USB/CPU 整板仿真或可闻复音及控制到声音延迟实测。

用户完成许可证命令后 Gowin 已进入解析；A 首次调用在 2.22 秒后因冻结目录缺少 `rtl/ddr_address_map.vh` 失败。[经授权的解析修复](push2_workstation/usb_a/reports/DUAL138K_TASK3_M_DDR_ALIAS_REPAIR_20261106.json)保留全部失败：补齐头文件后的第二次调用在 1.26 秒失败，原因是旧 `src/memory/ddr_address_map.vh` 先设置同名 include guard，屏蔽了当前 CNN 容量宏；单文件预处理未覆盖该顺序。新显式配置让两个 include 路径使用同一份维护权威映射，保留全部 69 个旧宏值。第三次调用 130.22 秒综合成功。A 实际为 **3 次综合调用（2 次解析失败、1 次成功）、1/1 P&R**；两次额外调用均有用户授权。B、C 各仍为 **1/1 综合、1/1 P&R**，未追加布局或路由参数试跑。

新候选 `8cf0f8e10a9efb34` 的 40 项针对性回归通过，264 个 HDL 文件按实际完整顺序预处理无警告；相对原 A，全部已启用 HDL、固件、工程、CST/SDC 不变，仅旧 DDR include 别名改用维护权威字节。71 份历史描述符、原 A/B/C 报告与基线均未修改。来源在独立缓存根中按锁重建，包含将一份历史编译 CRLF 文件还原为其声明的原始字节，原历史目录不动；重建过程、缺失供应商清单的准备失败和最终哈希均在报告中。

解析修复阶段完整标准审计曾报 `u_managed/display/held_data` 寄存器清单变化，未放行；独立分项检查为 17/18，覆盖实际普通 32 声部存储、保留矢量子树、CPU48 的 24 块及全部 12288 字、时钟/PLL 拓扑与多项 CDC。矢量 8 声部的功能依据仍是维护源码和前述真实子系统仿真，不冒充新的目标板复音验收。综合资源为 43158 Register、48137 LUT、198 BSRAM 等效；这不是物理 BSRAM，也不能把独立配置未启用的扩展功能算成 paired M 的优化收益。音频 76.8 MHz 域的综合估计仅 72.852 MHz；当时尚无布线 STA、位流或控制到声音实测，后续显示审计修订与唯一一次 P&R 见下文。完整 CDC、PLL、布线及硬件门禁继续保留。

[显示邮箱审计修订](push2_workstation/usb_a/reports/DUAL138K_TASK3_M_DISPLAY_AUDIT_20261106.json)对同一冻结候选重新核对：实际显示邮箱为 132 个保持 FF 加 98 个注册 RAM 输出，共 230 位；另有 60 位已应用参数邮箱，合计 5 个邮箱。旧 `m-demo-core` 只预期 73 个保持 FF，新显式 `m-task3-independent` 证明实际时钟、位映射、忙时保持、ACK/第三请求级和 RAM 注册输出，并核对既有 SDC 的 28 行本地约束。RTL、SDC、候选身份与 71 份历史描述符均不变；未刷新来源锁。完整标准综合审计通过仍不等于完整 CDC 或时序闭合，相关接受状态保持 false。9 项新测试拒绝全部 61 个破坏性反例，34 项当前源码/演示、10 项真实复位、2 项厂商 RAM 测试通过；PLL 回归 22 项通过、1 项缺显式夹具而跳过。两项旧 W 来源锁失败在提交前审计器中亦可复现，单独保留。A 首次且唯一的 P2R0 使用 `D21106F7`、原冻结 VG/CST/SDC 和 900 秒期限；完成结果见下文，未操作目标板。

[方案 A 的唯一物理实现](push2_workstation/usb_a/reports/DUAL138K_TASK3_M_INDEPENDENT_PHYSICAL_20261106.json)在 512.18 秒内完成 P2R0，实际 BSRAM 为 238/340（136 SDPB、50 SDPX9B、45 pROM、7 pROMX9），Logic 60564、Register 43158、CLS 46641/69120。音频 Fmax 73.696 MHz，低于 76.8 MHz；全局 setup/hold/recovery/removal 为 **-0.548/-3.535/+2.943/+0.275 ns**。最差 setup 为 `glide_step_o_6`→`pitch/glide_ratio_2`，近邻还包括效果增益、效果 valid 扇出和 HDMI 字形 RAM 地址；最差 hold 为 DDR 初始化 `ddr_init_internal_r`→`wloadn_3`。F7 位流 SHA-256 为 `598300de7ae12e8c1382f8369471a6ee0e817a60598445d6607ea19ba940a0ed`，仅保存证据，未部署。

物理审计对同一份 VO/SDF 补齐显式 TF-disabled M 启动配置，要求 TF 网表和 TF 约束查询确实为空；原 M 默认仍检查 9 条，独立 M 检查保留的 6 条，实际最差 CLK-Q＋route＋setup 为 0.904 ns，保留 2 ns 上限。6 个 PLL、3 组共享控制、DDR/视频启动、AE350/RTC 与显示 held-handshake 子门禁通过，7 项物理反例均被拒绝；34 项启动/PLL 回归为 33 项通过、1 项缺显式夹具而跳过。原失败审计保留，不改 RTL、SDC、位流或历史锁；完整 CDC、时序及硬件验收仍为 false。诊断时误生成的两个 Python 缓存文件已移出保存，614 个冻结文件及清单全部复核原样。本轮 A/B/C 均已消耗各自一次 P&R，不追加重复布局或路由参数试跑；后续先围绕上述真实路径做局部验证，并完成 W 现有效果的有界异步调度。

[方案 B 阶段证据](push2_workstation/usb_a/reports/DUAL138K_TASK3_W_USB_RETIREMENT_20261106.json)：显式 `custom138k-workstation-task3-w-paired-no-usb-v1` 只替换 W 的 USB 输入实现，保持数据线高阻、无事件、无 ready；原生顶层、HCI/CNN/录音源码与 AE350 固件同 v21。最终候选有 1030 个来源锁、677 个冻结文件、200 个编译输入；69 份历史描述符保持原哈希。实际综合用初版 `ad50780b1d6923f2`，175.58 秒完成；最终版与其 198 个 HDL 输入、工程和综合选项逐项一致，仅补退役网表中已消失的 USB 遥测约束，明确复用原网表，不再综合。相对 W v14 综合参考，BSRAM 等效 300→269、LUT 63891→58584；该参考不是 v21 的物理结果。

8 项新来源/真实 RTL/网表测试、17 项当前源码检查、12 项 paired 审计测试通过，原 W 默认边界审计在旧网表上的结果与冻结版完全一致。新配置的 USB、常量遥测、真实 CNN 与唯一录音对象均有网表证明；完整综合审计为 17/20，3 项根复位/批处理消费者证明仍报 `u_task3_bus_endpoint/n737_9` Boolean driver 缺失或歧义。F5 位流 SHA-256 为 `edb72b630defca10617989991668914147964489b0c949a6e3b195e2141d9807`，只用于本轮物理证据，未写入目标板。W 已释放实际容量，M 资源尚未因此减少；下一步评估方案 C，并按有界异步合同复用 W 现有效果资源，不能直接宣称迁移完成。

[方案 C 阶段证据](push2_workstation/usb_a/reports/DUAL138K_TASK3_W_BANKED96_20261106.json)：新增显式 `custom138k-workstation-task3-w-paired-banked96-v1`，从方案 B 派生三个独立同步读 32 KiB bank。保持 ELF/BIN 字节（BIN 为 90416 B）、全部运行地址、8 KiB scratch、64 KiB ILM/DLM 与 16 KiB 栈；物理 ROM 上界严格为 `0x80018000`，余量 7888 B。新增独立的 paired 固件参考，不修改旧 ROM96 参考或 70 份历史描述符。原生顶层、CNN/HCI/唯一录音对象及 SDC 均保持原值，M 本阶段没有减少资源。

36 项针对性测试通过：7 项实际准备/RTL/启动/网表测试，以及 17 项当前源码和 12 项 paired 审计回归。实际 RV32 启动、冷区 Classic/安全函数、缓存拒绝、范围/别名、scratch 转发和坏字/位宽/缺块均有验证；完整 CPU 顶层及目标板尚未验证。唯一综合用初版 `add5905aeb551ab5`，181.17 秒完成；终版仅补齐审计分派及来源锁，198 个 HDL、工程、选项、约束及 ROM 与初版相同，明确复用网表。综合 BSRAM 等效 269→253、LUT 58584→58588；实际物理 BSRAM 303→287。三项消费者/PLL 门禁仍报 `n737_9`，setup、hold、removal 较 F5 略回退，所有时序裕量仍为负；保留 F5 回退，不把本次资源收益当作时序闭合。两组历史回归分别被已有 `recording_service.c` 和 `build.py` 来源锁挡住，未刷新旧参考。F6 位流 SHA-256 为 `0fe24010d862b787518ba0f27453c5f936c97433da840db255dd25195429c3e4`，未写板。

跨板混响已完成[异步调度的源码阶段验证](push2_workstation/usb_a/reports/DUAL138K_TASK3_ASYNC_EFFECT_STREAM_20261106.json)，不作为第四个综合或 P&R 试跑。新 M 边界保持 stereo32，使用 64 帧固定 dry 对齐窗口和 16 帧发送队列；有匹配结果便采用，否则按原节拍输出对应 dry，松键立即选择 dry。取消、丢链、W 引擎租约丢失或仅切换速率后，必须用新身份恢复远程工作，序号不回卷。W 包装器没有另建混响引擎，真实现有引擎的独占复用仍需接入；[完整契约](push2_workstation/usb_a/rtl/audio/REMOTE_EFFECT_STREAM.md)列出队列、超时、重连与 PANIC 边界。

真实维护混响加双时钟 FIFO 仿真覆盖 48/44.1 kHz、W 25/50 MHz，共 17080 帧；413 次边界断言通过，7 个破坏版本全部被拒绝。现有来源与演示策略的 25 项回归通过，556 个旧文件及 72 份配置描述符与父提交一致。附加窗口为 1.333/1.451 ms，尚无真实声音延迟测量；两板候选、原资源／时序失败和回退均保留，没有新增位流或写板。

通信仍未准入：全部 15 个类型通道已占用。仅 PCM 加 8 字节 token/index 的下限为双向各 832000 B/s@48 kHz；若另留两字节容纳计数／标志，每包只能放两组 stereo32，预算升至双向各 1248000 B/s。叠加原手机、录音、分析最低负载后，为 M→W 2626000、W→M 1794000 B/s，信用、状态、下载及拥塞余量另计。这只是包预算假设，尚未选择新线协议；须完成 W 所有权调度、维护协议的显式协商扩展及实测并发预算后再决定整机集成，不能沿用 stereo16 的 416000 B/s 估计。

[W 混响独占租约源码验证](push2_workstation/usb_a/reports/DUAL138K_TASK3_SHARED_REVERB_LEASE_20261106.json)把真实维护混响、完整本地效果链、实际 delay DMA 和远程有界队列组合起来，展开层级确认只有一个混响实例。请求租约后立即停止接收新的本地样本／配置，完成已接收样本，再等待全链 history 事务及实际 DDR 有序栅栏返回；静音或单独的 delay quiet 都不构成释放证明。4096 周期内无法排空则拒绝，同一持续请求不自动重试；本地抢占、取消或 PANIC 立即撤销远程路径，真实清理并确认恢复原本地速率后才重新接收本地工作。512 周期恢复失败后锁定故障，PANIC 不能解除。

8 组仿真覆盖 W 25/50 MHz、本地 48/44.1 kHz 与相反的远程速率，以及恢复 ready 或 ACK 丢失。共完成 488 个本地样本、18416 个远程结果；每组另有一个在途远程请求被抢占取消，没有旧结果泄漏。8 个可编译的破坏版本全部被行为断言拒绝；25 项既有来源／演示回归通过。提交前另复现并修复新租约接口在复位期间仍暴露本地 ready 的问题，加入复位关闭断言和反例。首轮计分器边沿、测试 DDR watchdog 与反例预期修正及其失败日志均保留，既有生产 DSP、超时、时钟和约束没有改动。556 个历史文件、72 份配置描述符保持原哈希，远程已审查优化提交仍是当前分支祖先。

本阶段使用可逆、检查完整输入哈希的效果链接口投影，正式配置未选择它；没有新综合、P&R、位流或写板。M F7／W F6 的真实资源和时序失败继续沿用原证据。下一步先确定维护 LCD 协议中的显式协商扩展及准入调度，再做版本化原生组合接入；完整 CDC、物理时序与实测链路预算通过前，不开放跨板效果业务。

[持续容量复核与接入决定](push2_workstation/usb_a/reports/DUAL138K_TASK3_EFFECT_CAPACITY_DECISION_20261106.json)复用维护中的真实 transport/PHY 吞吐测试，4 组双向时钟／轻度终端背压场景共传递 8192 个业务线帧。两端 50 MHz 的有限窗口测量约为每方向 1.816 MB/s 线帧字节；W 45.45 MHz 的独立时钟压力场景，M→W 为 1.677、W→M 为 1.713 MB/s。它使用通用传输负载和理想连线，没有运行媒体消费者，不能作为真实引脚或应用吞吐验收。

完整并发加含标志的 stereo32 混响需要 M→W 至少 2.626、W→M 至少 1.794 MB/s；W 另按每 4 个满 block 最多一次信用更新预留 0.208 MB/s，预算共 2.002 MB/s。延后的信用可合并，故信用预留与严格下限分别记录。即使采用省略逐样本标志的 PCM-only 三帧包假设，M→W 仍需 2.210 MB/s；当前 50 MHz PHY 的保守状态驻留推导上界仅 2.174 MB/s，尚未扣 CRC 构建、包间隙和维护流量。现有传输无法支撑这组完整并发，扩大队列不能消除持续缺口。20% 余量仅用于离线规划，并非实测抖动保证；手机＋混响两路在有利模型中也只剩约 1.2%，不构成接入依据。

因此本轮明确**不把远程混响接入未改动的 paired-v3 传输**，保留 M 本地效果和所有回退；W 识别、手机接收／解码与唯一录音对象继续按原配置推进。9 组预算组合和 5 个坏证据反例通过；来源、时间、方向和 payload／线帧单位均核对原始日志。后续如继续迁移，先在维护协议内评估批量确认或更长有效载荷等方案，并以新的完整并发预算证明可行；不自动抢占手机／录音，也不静默丢弃分析。两板物理准入、完整 CDC／时序与目标板验收仍关闭，本轮没有追加综合或 P&R。

[F4 route1](push2_workstation/usb_a/reports/DUAL138K_TASK3_M_CAPTURE_ROUTE1_20261106.json)已在 1800 秒监督期限被终止，没有完整资源、STA、SDF 或位流，不再自动重跑。此前[效果配置分拍实验](push2_workstation/usb_a/reports/DUAL138K_TASK3_M_EFFECTS_DISPATCH_EXPERIMENT_20261106.json)保留未选入状态：4 项局部测试及 10 项真实效果/DDR 回归通过，完整 M 综合成功但 LUT +392；映射拓扑检查在旧参考的向量别名处失败，尚未证明切断关键路径，没有 P&R，不作为整机改善。

完整 M CPU release/consumer、held-handshake、TF CDC、W batch 消费者及 DDR/配置 payload hold 门禁继续保留。正确目标板接入后，先核对身份、引脚/电平及 LCD 有效吞吐、往返延迟和拥塞，再验收独立演奏、TF/CNN/Push、手机 D 按放效果与长录音/下载并发。44.1 kHz 后端仍需兼容的跨板 ARM 与真实来源格式绑定。

本次 2026-11-08 goal 止于上板前，先完成两板离线候选及 SRAM 验证清单，不执行板卡连接、加载或 Flash 操作。每阶段完成相关验证后 commit、push 并更新证据。

历史来源与失败对照保留在 [priority review](push2_workstation/usb_a/reports/DUAL138K_TASK3_PRIORITY_REVIEW_20261105.json)、[M 同步存储](push2_workstation/usb_a/reports/DUAL138K_TASK3_M_SYNC_STORAGE_20261105.json)、[录音格式](push2_workstation/usb_a/reports/DUAL138K_TASK3_RECORD_FORMATS_20261105.json)、[TF 尾帧本域复位](push2_workstation/usb_a/reports/DUAL138K_TASK3_M_TF_TAIL_LOCAL_RESET_20261106.json)、[终态流水线](push2_workstation/usb_a/reports/DUAL138K_TASK3_M_TERMINAL_PIPELINE_20261106.json)、[128 位比较](push2_workstation/usb_a/reports/DUAL138K_TASK3_M_IDENTITY_GROUPING_20261106.json)、[96 位手机比较](push2_workstation/usb_a/reports/DUAL138K_TASK3_M_PHONE_IDENTITY_20261106.json)和 [PLL 局部复核](push2_workstation/usb_a/reports/DUAL138K_TASK3_PAIRED_PHYSICAL_PROFILE_20261106.json)。
