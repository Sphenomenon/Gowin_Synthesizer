# task3：双 138K 工作站

M 负责独立实时演奏与最终输出；W 实际承担识别、手机音频接收/解码及录音存储。扩展功能通过 LCD 口的有界通信加入，基础演奏不等待 W，也不等待蓝牙往返。task2、单板工作树和已冻结候选继续保留。

本文只记录分工、接口约束与验收入口，不参与构建或来源锁。版本实验和失败记录保存在 `push2_workstation/usb_a/reports/`，不把历史报告改成新候选的证据。

## 赛题要求与项目目标

依据[赛题原文](../../docs/requests/全国大学生嵌入式芯片与系统设计竞赛'2026FPGA赛道选题指南-高云半导体.pdf)的选题二，PDF 第 15–16 页（正文第 13–14 页）：

| 层级 | 要求与验收 |
| --- | --- |
| 基础 | 至少两个独立可控演奏维度；FPGA HDL 逐声部、逐采样合成；至少四个独立声部同时发声；实时变调、ADSR、混音；经 I2S 和真实 DAC 发声；控制到声音总延迟 ≤10 ms。 |
| 扩展 | ≥32 复音或原文规定的等效并行合成规模；≥3 维表情、≥2 种音色及硬件效果器；≤5 ms 且确定性无抖动延迟；实时可视化、脱机指引及手机联动。 |
| 项目保留 | 32 声部目标及现有普通/矢量音源能力，不降为四声部交付。以同时活跃、可闻的独立声部和实际输出采样率验证，不能仅统计查表次数。 |
| 扩展媒体 | TF 直读、手机流式音频、录音回放属于辅助功能。赛题禁止用预录 PCM、预置推流或整段录音触发代替基础实时合成；基础演奏演示必须独立验证。 |

## 两板分工与实际路径

| 子系统 | M | W | 当前边界 |
| --- | --- | --- | --- |
| 交互、合成与参数 | 最终交互；唯一参数应用点；32 声部普通/矢量合成、变调、ADSR、混音、基础效果与采样调度 | 扩展结果和请求的生产方 | 不新增第二份权威参数；保留既有 18 位事件和生命周期语义。Push 与 25K 交替使用同一 USB-A 口。 |
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

业务准入保持 `link_ready && ALLOW_BUSINESS && budget_validated`；上电默认关闭。已有 200 ms、实际固件负载与理想连线的离线协同仿真，不能据此打开物理音频能力。实测至少覆盖双向有效载荷、往返延迟及尾部抖动、并行流、接收方停顿、停钟、拥塞恢复和丢包/CRC/序号计数。

## 失败、取消与输出约束

| 边界 | 必须保持的行为 |
| --- | --- |
| 断链、重连、取消、PANIC | 撤销当前租约和在途业务；按 boot/session/task/generation 及实际 owner 身份隔离旧结果；重连不能重放旧命令或自动续播。新 ARM 必须满足对象已退出等条件。 |
| 溢出、超时、错误采样帧 | 计数并显式终止对应分支；录音不能悄悄缺帧后仍称成功，识别不能发布部分失败曲谱。 |
| 控制接受与应用 | posted window 本地完成仅表示有界接收；M 的真实 ACK 和 applied barrier 才证明原 PCM1 已完成，缓存回复不能变成参数或输出权威。 |
| 基础音频 | 通信、CNN、显示、TF 操作、BLE 和下载均不能停止采样调度；扩展分支失败不拖住 M 的独立演奏。 |

## 当前候选与下一阶段

截至 2026-11-06，最新已登记来源检查点为两板 v21；另有未选入的 M capture ID 一致性比较实验 F3。v21 将完整 32 位 capture ID 顺序比较分成四组；保留零值、相等值及回绕拒绝，不增加状态或等待周期。W 配置与全部编译字节保持 v20 原样，继续实际承担识别、手机接收/解码及唯一录音对象。完整时序、CDC/PLL 与目标板验收仍未完成。

| 板与阶段 | 来源身份 | 实际证据 |
| --- | --- | --- |
| M v21 实验来源 | `custom138k-workstation-task3-m-paired-checkpoint-v21-cac552dbb92de6d2`；[配置](push2_workstation/usb_a/boards/custom_138k/workstation_profile_task3_m_paired_checkpoint_v21.json) | 979 项来源锁、287 项编译输入、693 项准备文件。完整 M 综合：58408 Register、68670 LUT、28061 ALU、212 BSRAM 等效、254 RAM16；审计 21/23。相对 v20 仅批处理器编译字节改变，LUT −132、ALU +29，寄存器和存储不变。 |
| M v21 F0 物理比较 | `custom138k-resource-physical-D21106F0`；[本轮证据](push2_workstation/usb_a/reports/DUAL138K_TASK3_M_CAPTURE_COMPARISON_20261106.json) | 同约束 P3R0，816.13 秒完成布线与位流生成；Logic 99061、Register 58408、BSRAM 253/340、CLS 61686/69120。setup/hold/recovery/removal 为 -4.468/-3.665/-4.263/-0.141 ns；未通过完整物理门禁，未部署。 |
| M v21 F1 物理预算实验 | `custom138k-resource-physical-D21106F1`；[PLL 路由实验与远程复核](push2_workstation/usb_a/reports/DUAL138K_TASK3_M_PLL_RESET_EXPERIMENT_20261106.json) | 相同综合 VG、CST、P3R0；只追加更严格的 TMDS PLL RESET 6 ns 预算及像素专项报告。831.70 秒完成布线，资源及四项最差裕量与 F0 相同；PLL RESET 仍为 10.870 ns。该实验未改善时序，未选入生产配置。 |
| M v21 F2 输出布局实验 | `custom138k-resource-physical-D21106F2`；[局部布局与完整门禁](push2_workstation/usb_a/reports/DUAL138K_TASK3_M_TMDS_OUTPUT_LOCALITY_20261106.json) | 保持 F0 综合 VG、SDC、P3R0 及全部 IO，仅追加 60 个 TMDS 输出寄存器/反相门的区域约束。688.18 秒完成布线；Logic 99075、Register 58408、BSRAM 253/340、CLS 61705/69120。setup/hold/recovery/removal 为 -4.231/-3.608/-3.953/-0.847 ns；HDMI、clk50、audio Fmax 回退，不选入生产配置，未部署。 |
| M F3 一致性比较实验 | 来源 `custom138k-task3-m-capture-identity-experiment-5f4bc994d089b579`；物理尝试 `custom138k-task3-experiment-physical-D21106F3`；[证据](push2_workstation/usb_a/reports/DUAL138K_TASK3_M_CAPTURE_IDENTITY_EXPERIMENT_20261106.json) | 完整 M 综合 208.25 秒成功：58408 Register、68675 LUT、28057 ALU、212 BSRAM 等效、254 RAM16。P3R0 运行 909.86 秒后 PR0004 退出，日志为“0 unrouted nets”；部分 P&R 报告为 Logic 99060、BSRAM 253/340、CLS 61787/69120。没有 STA、SDF 或位流，不选入生产配置。 |
| M v20 EF 保留对照 | `custom138k-resource-physical-D21106EF`；[证据](push2_workstation/usb_a/reports/DUAL138K_TASK3_M_DEMAND_IDENTITY_20261106.json) | BSRAM 253/340、CLS 61874/69120，setup/hold/recovery/removal 为 -5.106/-3.373/-4.674/0.281 ns。保留原始来源：EF 源于初次 v20，终版 v20 通过编译字节相同比对引用，未改写 EF 身份。 |
| W v21 当前来源 | `custom138k-workstation-task3-w-paired-checkpoint-v21-d8fa5871d2958f19`；[配置](push2_workstation/usb_a/boards/custom_138k/workstation_profile_task3_w_paired_checkpoint_v21.json) | 1027 项来源锁、200 项编译输入、675 项准备文件。配置及全部编译字节与 v20 相同；本阶段没有新 W 综合或物理运行。 |
| W v14 E9 保留物理结果 | `custom138k-resource-physical-D21106E9`；[证据](push2_workstation/usb_a/reports/DUAL138K_TASK3_W_CNN_READY_SDC_20261106.json) | 真实 BSRAM 336/340、CLS 58819/69120；审计 11/18，setup/hold/recovery/removal 为 −7.224/−4.350/−7.947/−0.234 ns。结果保留原身份，未部署。 |

[v21 源码验证](push2_workstation/usb_a/reports/DUAL138K_TASK3_M_CAPTURE_COMPARISON_20261106.json)完成 61 项测试方法，无跳过。新批处理器与精确逆变换得到的完整 v20 参考，在真实异步 APB/PCM owner 测试中逐周期比较 18135 个周期、全部 11 个公开输出；955 项 owner 检查通过，取消、断链、超时及回复背压期间音频采样继续推进。

完整 M 网表中的顺序比较已证明全部 2^64 组操作数赋值等价，拒绝 64 个漏位、严格小于及交换操作数反例，并核查 144 组边界值；最大串联 ALU 为 7 级、组合逻辑为 11 级。证明左侧为 32 位组合响应边界，右侧为 32 个真实 FF-Q；不把它称作 64 个独立 FF 或完整上游/CDC 证明。所用新增 ALU/MUX 模型分别通过 Gowin 官方原语 24/32 行真值表核对。批处理/根状态、手机租约及 TF 尾帧的破坏性回归也通过。

维护 RTL 默认仍用直接无符号比较，只有显式 M v21 选入分组；完整批处理器可精确逆变换回 v20。40 份历史检查点描述符保持原样。终版准备修正了证明器的 MUX 支持，全部 287 项编译输入与本轮实际综合的 v3 准备逐字节相同，复用关系有独立哈希记录；F0 从终版 v4 来源与审计准备，未改名引用旧物理候选。初次来源登记、证明器及测试工具失败均保留在报告中。

F0 与 EF/EE/EC 的物理 CST/SDC 逐字节相同，没有放宽时钟或例外。F0 位流 SHA256 为 `ea00e4c73d9a4a36b470c117f571ae7e94e99fc48775e6f0a11e9f3e0baa4b25`，没有目标板读回。clk50/audio/HDMI 的实际 Fmax 为 43.275/61.993/122.566 MHz，对应要求为 50/76.8/148.5 MHz；详细路径、PR1014、hold 与 PLL 失败以报告原值保留，不由工具成功退出推断时序通过。 相对 EF，Logic 减少 137、CLS 减少 188，BSRAM 仍为 253；setup 和 recovery 改善，但 hold 变差、HDMI 从达标变为不达标，removal 从正裕量变为负裕量。PLL 审计还新增 TMDS PLL RESET 传播 10.870 ns 超过 10 ns 的失败。F0 不替代已有物理对照。

F1 保留全部原 SDC 字节、时钟、例外及最小延迟检查，42 份两板历史检查点描述符未改。F0/EF 的 SDF 逐段核查显示，TMDS PLL RESET 最后一段连线由 3.462 增至 6.052 ns；F1 的 6 ns 端点预算未消除这项失败。完整 PLL 审计仍按原规则拒绝实验 SDC 与来源 SDC 不同，独立且未修改的 video PLL 子检查也失败；两者分别记录。一次诊断导入生成的额外 Python 字节码已单独归档，初次清单失败保留，锁定来源与哈希未修改。

此前全局最差 2000 条 setup 路径没有像素时钟路径。F1 专项 STA 确认 HDMI 最差路径为 lane2 的 `encoder/tmds_8_s0` → `serializer/serializer/D8`，数据延迟 8.003 ns、裕量 −1.425 ns；末段路由占 7.121 ns，编码寄存器/门位于 R56C2，输出串行器位于 IOR58。该路径促成 F2 的输出局部布局实验。F1 位流 SHA256 为 `e821bf7a4d5d0c126df240bf28592183ecfe84a1023b9cbda47e12f7ccddd1f1`，未部署；W 无新综合或物理运行。

F2 在 `R[46:74]C[160:181]` 约束全部 30 个输出寄存器和 30 个反相门，保留原 CST 前缀及全部 42 份检查点描述符。新 VO 核对了全部 30 位的连接顺序与反相关系；实际 SDF 的输出数据段合计范围由 6.617–8.003 ns 降到 1.755–2.748 ns，lane2 bit8 为 1.887 ns，末段连线为 1.171 ns。这些是数据段证据；原 SDC 没有像素专项报告，有限的详细 STA 也没有覆盖这 60 个单元的位置，不能据此声称全部实际位置或完整像素 STA 已验证。

F2 的 clk50/audio/HDMI Fmax 为 41.274/58.111/114.279 MHz，均低于 F0；removal 也回退。完整 PLL 检查首次因未设置官方仿真库路径中止；补上 `GOWIN_SIMLIB` 后按原规则重跑，仍因 startup grant 接收原语、TMDS `ICPSEL[0]` 传播 10.106 ns 超过 10 ns，以及 held-handshake 所选行缺失/重复而失败。环境失败和最终失败分别保留。F2 位流 SHA256 为 `9d52145cd602deaa5000a0568bfe8629437b9d9bab070fadb38992ef0a88bb51`，不替换现有对照；53 项相关测试通过、1 项跳过，未操作目标板。

v21 的顺序比较缩短后，相同 memory fault→reply CE 边界的最长拓扑见证从 47 级变为 50 级，仍含响应与冻结 `capture_id` 的 31 级一致性比较。F3 只将 `LAST_CAPTURE_ID` 的这项完整 32 位比较改为四组 8 位比较；原快照一致性、顺序检查、状态和协议保持原样。通过 27 项测试方法、4290 项真实 RTL 四态比较，以及异步 PCM owner 的 18135 周期/11 个公开输出等价检查。完整 M VG 与失败 P&R 所生成 VO 中的局部比较均证明全部 2^64 组赋值等价，各拒绝 64 个漏位反例，最大串行 ALU 为 7 级、组合逻辑为 9 级。初次 VO 诊断误用了综合层级，修正为实际扁平网名及 FF-Q 后通过；初次失败保留。相同 fault→reply CE 的最长拓扑为 27 级，未证明可敏化，也不是加权 STA。

F3 仍是显式独立实验：287 项原编译输入中只替换一个精确可逆的批处理源，新增一个版本化组合比较模块；693 项父来源文件和 42 份历史描述符未改。完整综合比 v21 增加 5 LUT、减少 4 ALU，寄存器/存储不变，249 个既有层级实例资源不变。物理运行保留 F0 CST 和 SDC 全部字节，仅追加两条像素报告命令；未采用 F2 区域约束。PR0004 的根因尚未确定，“0 unrouted nets”不能覆盖失败退出；生成 VO 的局部证明不能替代缺失的 STA/SDF/位流，完整 PLL 检查也未运行。现有标准配置和 F0/EF/EE/EC 对照均保留。

识别完成信号已确认是保持状态；实际 USB meta→sync 两级存在，源侧首个寄存器边界只有自身保持和 USB meta。任务取消、重新 ARM、完成与曲谱数据的顺序语义仍需证明，本轮未新增例外。

整机的 CPU release/consumer 与 held-handshake 两个门禁仍失败，历史清单未刷新。先前 [403 个源侧 FF 与外部 APB 方程核查](push2_workstation/usb_a/reports/DUAL138K_TASK3_M_P3_SOURCE_REVIEW_20261106.json)仍是局部证据。完整 PLL/startup、完整 TF CDC、真实 32 声部普通/矢量合成、TF→W CNN→Push、手机 D 按放效果及 60 秒录音/下载并发仍需各自验收。局部存储、命令、MIDI 和比较证明不能替代这些门禁。

远程成果已由 `f96df276` 审查后选择性合入：PR #2 的 CPU48 分 bank RAM 已用于 M/W，实际网表逐字验证 24 个块、12288 个 ROM 字，原对照为 32→24 块；W 的 BSRAM 由 344 降到 336/340。PR #3 的独立 USB/HDMI 诊断、目标域复位与状态新鲜度修复也已保留。ADSR/TF ring 仍是实验，重复录音后端未选入。取舍见 [PR 审查与选用](push2_workstation/usb_a/reports/DUAL138K_TASK3_PR_INTEGRATION_20261103.json)。F1 阶段重新核对远程为 `49174d26`，无待合入 PR，且确认该集成提交仍为当前祖先；再次从 M F0 与 W E9 的实际综合 VG 重建全部 24 块、12288 字，CPU 来源及固件与两板最新 v21 制备匹配，未把 W 的旧综合称作新运行。详细记录见 [远程复核与 F1 证据](push2_workstation/usb_a/reports/DUAL138K_TASK3_M_PLL_RESET_EXPERIMENT_20261106.json)。

F2 阶段再次实际 fetch 当前分支：远程与本地均为 `ffc28f8f`，无待合入 PR；`f96df276` 仍为当前祖先。CPU48 的实际网表证据沿用上述明确标识的 F0/E9 复核，本阶段没有新增 W 综合或物理运行。

F3 阶段再次 fetch：远程与本地基点均为 `e9ead733`，无待合入 PR；在线核对 PR #2/#3 已合入原 workstation 分支，当前仍继承审查后的选择性集成。重新从本轮完整 M VG 逐字重建 24 块、12288 字 CPU48 ROM，确认远程优化仍生效；W 沿用明确标识的 E9 证据，没有新综合或物理运行。

后续按以下顺序推进：

1. F3 局部比较证明通过但布线失败，先独立定位 PR0004，再进行有依据的布局/配置比较并取得完整 STA/SDF；不把 27 级拓扑或“0 unrouted”解释为整机改善。F2 证实局部输出线缩短但整机时序回退，仍需覆盖编码器输入、复位和串行器端点的像素专项 STA；F1 的 6 ns PLL RESET 预算和 F2 的 60 单元区域均不直接选入。继续处理 clk50 的 RX payload→TX payload，以及 audio 的 divider valid→配置接受→reverb RAM CE 路径（18 级逻辑，途中门扇出 514），保持采样与配置应用屏障。F2 的 PCM owner staged_physical→written 路径需与原对照分开评估。核查 HCI ready→PCM session release、识别完成→USB 首级及效果故障的运行语义，以及 PANIC/事件队列和复位扇出。保留 F3、F2、F1、F0、EF、EE、EC 对照，不放宽时钟或 false path。
2. 关闭 M 的完整 CPU release/consumer、held-handshake、TF CDC 与 PLL/startup 门禁。将已有局部证明接入新检查点前，补全目的侧和完整握手；不刷新旧清单哈希来取得通过。W 完整 batch 的消费者、身份、live、请求/回复及 DDR/配置 payload hold 仍需独立证明。
3. 结合 W 仅余 4 块物理 BSRAM 和 LCD 实测预算，继续评估重型效果、FFT/显示分析及扩展合成分担。W 已有真实效果链，优先复用，不能假定还能叠加一套混响或 FFT。已有[混响子系统综合](push2_workstation/usb_a/reports/DUAL138K_TASK3_REVERB_SYNTHESIS_20261101.json)尚未选入 paired 整机，其资源减少不能算整机收益。
4. 正确目标板接入后，先核对身份、引脚/电平及 LCD 有效吞吐、往返延迟和拥塞，再验收 M 独立演奏/DAC 延迟、TF/CNN/Push、手机 D 按放效果与长录音/下载并发。44.1 kHz 后端仍需兼容的跨板 ARM 与真实来源格式绑定；当前 paired 配置只接纳 48 kHz 录音。

必要 SRAM 验证沿用本任务授权，须先识别正确目标；Flash 仍需单独授权。每阶段完成相关验证后 commit、push 并更新证据。

历史来源与失败对照保留在 [priority review](push2_workstation/usb_a/reports/DUAL138K_TASK3_PRIORITY_REVIEW_20261105.json)、[M 同步存储](push2_workstation/usb_a/reports/DUAL138K_TASK3_M_SYNC_STORAGE_20261105.json)、[录音格式](push2_workstation/usb_a/reports/DUAL138K_TASK3_RECORD_FORMATS_20261105.json)、[TF 尾帧本域复位](push2_workstation/usb_a/reports/DUAL138K_TASK3_M_TF_TAIL_LOCAL_RESET_20261106.json)、[终态流水线](push2_workstation/usb_a/reports/DUAL138K_TASK3_M_TERMINAL_PIPELINE_20261106.json)、[128 位比较](push2_workstation/usb_a/reports/DUAL138K_TASK3_M_IDENTITY_GROUPING_20261106.json)、[96 位手机比较](push2_workstation/usb_a/reports/DUAL138K_TASK3_M_PHONE_IDENTITY_20261106.json)和 [PLL 局部复核](push2_workstation/usb_a/reports/DUAL138K_TASK3_PAIRED_PHYSICAL_PROFILE_20261106.json)。
