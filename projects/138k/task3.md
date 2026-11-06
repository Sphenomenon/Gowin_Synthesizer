# task3：双 138K 工作站

M 负责独立实时演奏与最终输出；W 实际承担识别、手机音频接收/解码及录音存储。扩展功能通过 LCD 口的有界通信加入，基础演奏不等待 W，也不等待蓝牙往返。task2、单板工作树和已冻结候选继续保留。

本文只记录分工、接口约束与验收入口，不参与构建或来源锁。版本实验和失败记录保存在 `push2_workstation/usb_a/reports/`，不把历史报告改成新候选的证据。

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
| 重型效果 | 当前完整候选仍保留本地混响；远程处理必须超时回退且不停止采样 | 已有真实混响计算和历史 RAM 的子系统实现 | 子系统综合证明 M 可移出 20 个 SDPB 和 19 个 MULT27X36；尚未接入完整 paired 候选，不能作为整机资源减少。 |

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

截至 2026-11-06，两板 v21 保留为 paired 来源检查点；本轮另登记 M 独立演奏、W USB 退役和 W 显式 96 KiB 分 bank 配置；两个 W 方案各完成一次综合及一次 P2R0。另有未选入的 M capture ID 一致性比较实验 F3。v21 将完整 32 位 capture ID 顺序比较分成四组；保留零值、相等值及回绕拒绝，不增加状态或等待周期。其中 W v21 的配置与全部编译字节保持 v20 原样，继续实际承担识别、手机接收/解码及唯一录音对象。完整时序、CDC/PLL 与目标板验收仍未完成。

| 板与阶段 | 来源身份 | 实际证据 |
| --- | --- | --- |
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

上表是 E9 对应综合的包含式层级统计，父子项不能相加，也不能当成新配置的物理收益。首轮限定以下三个方案，每个最多一次综合、一次 P&R；先完成各自局部验证再消耗预算，结果未改善且无新诊断依据时停止。

| 顺序与方案 | 验证前预期收益 | 成功条件 |
| --- | --- | --- |
| A：M 独立演奏配置 | 沿用现有 M-demo/provider 与构建入口，把独立交互→普通 32 声部／现有矢量 8 声部合成→DAC 的真实边界固定下来；不预称时序或资源改善。 | 保留两个交互维度、变调、ADSR、混音；验证真实源到串行器和所有声部；完整 CDC/PLL/时序通过后再测目标板控制到声音延迟。 |
| B：paired W 裁掉未转发 USB | 参考子树最多释放 31 BSRAM 等效及 4858 LUT，实际整机收益须测；M 暂不因此减资源。为后续实际迁移留余量。 | HCI/手机代理、CNN、唯一录音对象与固件保持正确；网表不含 USB host/CPU/owner，物理 BSRAM 降低，门禁保留。 |
| C：W 显式 96 KiB 分 bank ROM | 64→48 pROM 的目标；现镜像余量 7888 B。单改数组深度可能仍填充到原块数，不能算收益。 | ELF、启动及运行地址不变、镜像逐字一致；范围/别名与 AHB 时延检查、48 个实际 ROM 块及完整物理门禁通过。 |

[方案 A 阶段证据](push2_workstation/usb_a/reports/DUAL138K_TASK3_M_INDEPENDENT_20261106.json)：新增显式 `custom138k-workstation-task3-m-independent-v1`，复用 M-demo provider 和远程 CPU48 RAM，不修改原描述符及 paired/task2 回退。最终准备身份为 `custom138k-workstation-task3-m-independent-v1-dca520d2406ed45f`；840 个来源锁、612 个冻结文件、267 个编译输入，USB 固件 21380 B，48 KiB RAM。该独立配置验证基础演奏边界，TF、识别、手机与唯一录音对象继续由已有 paired 配置推进。

45 项来源／审计回归通过；实际音频子系统仿真检查 22532 帧，普通 32 声部和矢量 8 声部在 48/44.1 kHz 下共 12 次活跃数量检查、12 种物理串行取消边界通过。Push 入口与禁用 TF 边界回归通过。此证据使用真实 DSP、DDR 模型、DCS、最终 PCM 和 I2S，尚不等同于 USB/CPU 整板仿真或可闻复音及控制到声音延迟实测。

用户完成许可证命令后 Gowin 已进入解析；A 的唯一一次综合在 2.22 秒后因冻结目录缺少 `rtl/ddr_address_map.vh` 失败，无网表、资源或时序结果。已补齐权威头文件依赖并通过重新 prepare、来源校验及 Icarus 预处理；修复后的最终候选未再综合。本轮 A 已用 **1/1 综合、0/1 P&R**，停止该方向的 EDA，不自动重跑；B 已用 **1/1 综合、1/1 P&R**，不追加参数试跑；C 已用 **1/1 综合、1/1 P&R**，首轮三个方案不再追加 EDA。完整 CDC、PLL、布线及硬件门禁均未放宽。

[方案 B 阶段证据](push2_workstation/usb_a/reports/DUAL138K_TASK3_W_USB_RETIREMENT_20261106.json)：显式 `custom138k-workstation-task3-w-paired-no-usb-v1` 只替换 W 的 USB 输入实现，保持数据线高阻、无事件、无 ready；原生顶层、HCI/CNN/录音源码与 AE350 固件同 v21。最终候选有 1030 个来源锁、677 个冻结文件、200 个编译输入；69 份历史描述符保持原哈希。实际综合用初版 `ad50780b1d6923f2`，175.58 秒完成；最终版与其 198 个 HDL 输入、工程和综合选项逐项一致，仅补退役网表中已消失的 USB 遥测约束，明确复用原网表，不再综合。相对 W v14 综合参考，BSRAM 等效 300→269、LUT 63891→58584；该参考不是 v21 的物理结果。

8 项新来源/真实 RTL/网表测试、17 项当前源码检查、12 项 paired 审计测试通过，原 W 默认边界审计在旧网表上的结果与冻结版完全一致。新配置的 USB、常量遥测、真实 CNN 与唯一录音对象均有网表证明；完整综合审计为 17/20，3 项根复位/批处理消费者证明仍报 `u_task3_bus_endpoint/n737_9` Boolean driver 缺失或歧义。F5 位流 SHA-256 为 `edb72b630defca10617989991668914147964489b0c949a6e3b195e2141d9807`，只用于本轮物理证据，未写入目标板。W 已释放实际容量，M 资源尚未因此减少；下一步评估方案 C，并按有界异步合同复用 W 现有效果资源，不能直接宣称迁移完成。

[方案 C 阶段证据](push2_workstation/usb_a/reports/DUAL138K_TASK3_W_BANKED96_20261106.json)：新增显式 `custom138k-workstation-task3-w-paired-banked96-v1`，从方案 B 派生三个独立同步读 32 KiB bank。保持 ELF/BIN 字节（BIN 为 90416 B）、全部运行地址、8 KiB scratch、64 KiB ILM/DLM 与 16 KiB 栈；物理 ROM 上界严格为 `0x80018000`，余量 7888 B。新增独立的 paired 固件参考，不修改旧 ROM96 参考或 70 份历史描述符。原生顶层、CNN/HCI/唯一录音对象及 SDC 均保持原值，M 本阶段没有减少资源。

36 项针对性测试通过：7 项实际准备/RTL/启动/网表测试，以及 17 项当前源码和 12 项 paired 审计回归。实际 RV32 启动、冷区 Classic/安全函数、缓存拒绝、范围/别名、scratch 转发和坏字/位宽/缺块均有验证；完整 CPU 顶层及目标板尚未验证。唯一综合用初版 `add5905aeb551ab5`，181.17 秒完成；终版仅补齐审计分派及来源锁，198 个 HDL、工程、选项、约束及 ROM 与初版相同，明确复用网表。综合 BSRAM 等效 269→253、LUT 58584→58588；实际物理 BSRAM 303→287。三项消费者/PLL 门禁仍报 `n737_9`，setup、hold、removal 较 F5 略回退，所有时序裕量仍为负；保留 F5 回退，不把本次资源收益当作时序闭合。两组历史回归分别被已有 `recording_service.c` 和 `build.py` 来源锁挡住，未刷新旧参考。F6 位流 SHA-256 为 `0fe24010d862b787518ba0f27453c5f936c97433da840db255dd25195429c3e4`，未写板。

跨板混响暂不作为第四个 EDA 试跑。先定义有界异步 dry-send/wet-result 队列、完整身份/序号和期限、附加延迟及 dry/wet 对齐；丢链、松键、取消及 PANIC 丢弃旧 wet 结果并有界退回本地 dry。若沿用 stereo16 block6，额外发送/返回各至少 416000 B/s@48 kHz，信用/状态及手机、录音、分析并发另计；实测前业务仍关闭。

[F4 route1](push2_workstation/usb_a/reports/DUAL138K_TASK3_M_CAPTURE_ROUTE1_20261106.json)已在 1800 秒监督期限被终止，没有完整资源、STA、SDF 或位流，不再自动重跑。此前[效果配置分拍实验](push2_workstation/usb_a/reports/DUAL138K_TASK3_M_EFFECTS_DISPATCH_EXPERIMENT_20261106.json)保留未选入状态：4 项局部测试及 10 项真实效果/DDR 回归通过，完整 M 综合成功但 LUT +392；映射拓扑检查在旧参考的向量别名处失败，尚未证明切断关键路径，没有 P&R，不作为整机改善。

完整 M CPU release/consumer、held-handshake、TF CDC、W batch 消费者及 DDR/配置 payload hold 门禁继续保留。正确目标板接入后，先核对身份、引脚/电平及 LCD 有效吞吐、往返延迟和拥塞，再验收独立演奏、TF/CNN/Push、手机 D 按放效果与长录音/下载并发。44.1 kHz 后端仍需兼容的跨板 ARM 与真实来源格式绑定。

必要 SRAM 验证沿用本任务授权，须先识别正确目标；Flash 仍需单独授权。每阶段完成相关验证后 commit、push 并更新证据。

历史来源与失败对照保留在 [priority review](push2_workstation/usb_a/reports/DUAL138K_TASK3_PRIORITY_REVIEW_20261105.json)、[M 同步存储](push2_workstation/usb_a/reports/DUAL138K_TASK3_M_SYNC_STORAGE_20261105.json)、[录音格式](push2_workstation/usb_a/reports/DUAL138K_TASK3_RECORD_FORMATS_20261105.json)、[TF 尾帧本域复位](push2_workstation/usb_a/reports/DUAL138K_TASK3_M_TF_TAIL_LOCAL_RESET_20261106.json)、[终态流水线](push2_workstation/usb_a/reports/DUAL138K_TASK3_M_TERMINAL_PIPELINE_20261106.json)、[128 位比较](push2_workstation/usb_a/reports/DUAL138K_TASK3_M_IDENTITY_GROUPING_20261106.json)、[96 位手机比较](push2_workstation/usb_a/reports/DUAL138K_TASK3_M_PHONE_IDENTITY_20261106.json)和 [PLL 局部复核](push2_workstation/usb_a/reports/DUAL138K_TASK3_PAIRED_PHYSICAL_PROFILE_20261106.json)。
