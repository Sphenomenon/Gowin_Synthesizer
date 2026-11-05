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

截至 2026-11-05，最新来源检查点为两板 v4，均已准备但未另跑综合；实际综合参考为 M v3、W v2。M v3 经当前外部审计为 20/22，并完成一次失败的物理诊断。M 保持 2048 音符、256 帧、32 声部和普通/矢量结构，同步存储映射通过。v4 保留 v3 的运行配置、48 kHz 跨板录音和 v3 LCD 协议；可选双采样率后端的 44.1 kHz 尚未接入成对配置。旧配置与冻结候选保留，完整 CDC、路由时序及硬件验收仍待完成。

| 板 | 选定来源与身份 | 验证边界 |
| --- | --- | --- |
| M v3 实际参考 | `custom138k-workstation-task3-m-paired-checkpoint-v3-110816887ce99741`；[配置](push2_workstation/usb_a/boards/custom_138k/workstation_profile_task3_m_paired_checkpoint_v3.json) | 已综合；58,384 Register、69,206 LUT、28,074 ALU、212 BSRAM 等效、254 RAM16。当前外部审计 20/22：原有功能结构、时钟/PLL、USB CDC、batch 映射、CPU48 ROM 及 MIDI release 通过；两个完整 CPU consumer 门禁仍拒绝。物理诊断布局完成，布线失败；无完整 STA、位流及板上验收。 |
| W v2 参考 | `custom138k-workstation-task3-w-paired-checkpoint-v2-c93ee337298bcad6`；[配置](push2_workstation/usb_a/boards/custom_138k/workstation_profile_task3_w_paired_checkpoint_v2.json) | 已综合；49,458 Register、63,986 LUT、16,347 ALU、308 BSRAM 等效、779 RAM16。完整审查 11/18 通过，局部证明硬编码的历史自动网名在新 VG 中已不存在，Boolean driver 查找拒绝；尚不能据此判断电路错误。保留 60 秒单对象；既有 ELF 检查的 ILM 为 50,160 字节、保守栈 896 字节。无物理验收。 |
| M v4 当前来源 | `custom138k-workstation-task3-m-paired-checkpoint-v4-d5a33514ee4deb61`；[配置](push2_workstation/usb_a/boards/custom_138k/workstation_profile_task3_m_paired_checkpoint_v4.json) | 准备及来源校验通过，运行配置和编译文件列表与 M v3 一致；四个封存审计脚本更新，未另跑综合。M v3 的审计和物理结果不改记为 v4 结果。 |
| W v4 当前来源 | `custom138k-workstation-task3-w-paired-checkpoint-v4-752f0d5f38ed41e2`；[配置](push2_workstation/usb_a/boards/custom_138k/workstation_profile_task3_w_paired_checkpoint_v4.json) | 准备及来源校验通过，运行配置和编译文件列表与 W v3 一致；两个共享审计脚本更新，未另跑综合。最新 W 实际资源仍绑定 v2。 |

两板均无本阶段位流 SHA/UserCode、实测控制到声音延迟或硬件通过结论；目标 JTAG/串口身份待接入后绑定。表内资源是各自 XML 综合统计，失败物理报告的用量另列于下文。M 的 50 MHz 综合估算仅 41.597 MHz，76.8 MHz 音频时钟估算 58.651 MHz；W 对应为 48.618/72.254 MHz，均未达到要求。综合估算不能代替 routed STA，也没有据此降低时钟。

最新 [M release 与物理诊断证据](push2_workstation/usb_a/reports/DUAL138K_TASK3_M_RELEASE_AND_PHYSICAL_20261105.json)记录了来源分类修复、MIDI 原始根复位及 528 个最终复位 consumer、PC/APB 局部握手证明。73 项测试通过，97 项故障/来源篡改被拒绝；历史完整 consumer 清单未刷新。M CPU source 的 403 个 FF、两个不透明 IP 终点与旧 batch 清单相同，但不能据此放行其业务行为；destination 清单仍有较大差异。两个完整 consumer 门禁与全部 TF CDC 继续保留。

M v3 原 SDC 在 Gowin 物理阶段出现 17 个 TA2003 对象绑定错误，尚未进入布局。现有物理准备工具新增显式 `--task3-pin-collections` 选项，枚举 15 个实际标量 Q，并为两处 RAM16SDP4 向量端口使用集合查询；逻辑终点集合及其余 SDC 字节保持一致，时钟、预算和例外范围不变。维护入口准备的 E3 与实际 E2 探针的 VG/CST/SDC 逐字节一致；临时探针脚本只作历史证据，不作为后续唯一构建入口。向量时序弧与完整 FIFO 证明仍未通过。

E2 物理诊断以 900 秒为上限，约 653 秒后自然失败，非超时：布局完成，布线报 1,168 条未布通网络。失败报告用量为 Logic 99,577/138,240、Register 58,384、CLS 61,370/69,120（89%）、BSRAM 253/340；PRIMARY 与 LW 均为 8/8。该物理映射统计与综合的 212 BSRAM 等效不同，不能视作布通或时序通过。生成的 VO 属于失败实现，未生成完整 STA 或位流；请求的 UserCode 为 `D21105E2`，不是板上身份。

本阶段 [M 同步 wrapper 与根复位映射证据](push2_workstation/usb_a/reports/DUAL138K_TASK3_M_SYNC_ROOT_PROOF_20261105.json)绑定新 M v3 VG、完整审计及两板 v3 来源。精确 include 链和真实根 Q 通过验证，35 个根状态位的下一拍方程对全部 `2^35` 个状态赋值成立；请求翻转按真实 D/CE、异步 CLEAR 与 held-word CE 验证有效下一拍行为，未要求综合器沿用旧映射。三份实际 M 网表合计 15 项测试、231 项故障/来源篡改拒绝，加上 32 项来源及 paired 回归，共 47 项测试通过。旧 provider 仍用原证明，完整 executor、APB、consumer 和物理 CDC 未据此放行。

此前的 [v2 成对综合及存储映射证据](push2_workstation/usb_a/reports/DUAL138K_TASK3_PAIRED_SYNTHESIS_20261105.json)保留两板 VG/XML/log 身份、全部失败门禁及回退。工具新增的 `Prj1.gprj.user` 曾使通用 prepare 清单检查拒绝，原始失败保留；本次 M v3 在综合前做通用校验，综合后由生产 paired 校验核对全部封存输入，仅允许该工具输出。静态网表诊断中的 10,138 负载复位网络及 score 身份比较/计数长组合链仍是后续布局/STA 排查入口，不是实际延迟结论。

远程 PR 成果已由 `f96df276` 集成并保留在当前分支：PR #2 的 CPU48 分银行 RAM 与固件/映射 ROM 证明已选入 M；PR #3 的 USB/HDMI 诊断及复位、状态修复已引入。ADSR/TF ring 仍是待物理验证的实验，退出的重复录音后端未选入。此次 fetch 后本分支与 origin 一致；具体取舍见 [PR 审查与选用](push2_workstation/usb_a/reports/DUAL138K_TASK3_PR_INTEGRATION_20261103.json)。

两板 v2 来源锁、完整准备结果及两个冻结 v1 父候选的回退核对通过；42 项定向测试通过，包含 8 项成对元数据和 11 项实际 ELF 记录的篡改拒绝。共享源码快照的 1028 个输入 hash 一致，v3 线协议及业务默认关闭策略保留。最新身份、完整准备差异与复现命令见 [双采样率后端及 v2 检查点](push2_workstation/usb_a/reports/DUAL138K_TASK3_RECORD_FORMATS_20261105.json)。此前的 [v1 成对来源检查点](push2_workstation/usb_a/reports/DUAL138K_TASK3_PAIRED_CHECKPOINT_20261105.json)及其父候选保留。

M 本次 Gowin 网表中，score 为 1 个 SDPB、tap 为 2 个 SDPB，两者均无 RAM16。相对此前冻结的 phone-batch 网表，各移除 256 个 RAM16；整体 RAM16 从 766 降到 254，LUT 从 70,377 降到 69,206，BSRAM 等效从 209 增到 212。该比较不是单变量的物理 A/B，不能证明时序改善。此前的 [通用存储推断预检](push2_workstation/usb_a/reports/DUAL138K_TASK3_M_STORAGE_INFERENCE_20261105.json)另验证原准备输入的 2048×7 位 score 和 256×98 位 tap 同步读端口、12 位本地计数及两个异步模式负控；生命周期和读写冲突回归仍为独立证据。

冻结 W phone-batch 参考候选的独立网表诊断已检查 39 个 consumer 差异：23 个在明确的同名状态对应前提下，复位在内的下一拍函数相等（12 个 BDD、11 个限时 Z3 布尔 miter）；16 个仍待证明。15 项定向测试通过，包含 Gowin ALU 的 80 组及四种 MUX 的 32 组厂商真值核对、实际网表的 8 项突变拒绝，以及 11 份 miter 的独立进程重放。最新范围及复现见 [W MUX/SAT 诊断](push2_workstation/usb_a/reports/DUAL138K_TASK3_W_CONSUMER_MUX_SAT_20261105.json)，此前的 [12 项诊断](push2_workstation/usb_a/reports/DUAL138K_TASK3_W_CONSUMER_NEXTQ_20261105.json)保留。该网表不作为新检查点的映射或 CDC 通过证据。

剩余项为 9 个加密 DDR IP 输出边界、6 个有歧义的同名状态及 1 个缺失状态对应，均未按同名信号直接放行。真实负控还表明：删除某计时器的异步 CLEAR 后，下一拍函数仍可相等；单步诊断因此不能代替异步事件或完整 CDC 证明。完整状态关系、生产门禁、物理时序及硬件验收仍未通过，历史锁和冻结候选均未改变。

W 的[共享存储录音回归](push2_workstation/usb_a/reports/DUAL138K_TASK3_W_SHARED_RECORDING_20261105.json)绑定此前冻结候选的组件字节：生产队列/仲裁器在模拟分析及 delay 流量竞争下完成 288 万帧录制和全部 11.52 MB 下载，CRC 为 `3ddb23ec`；下载断连后旧 ACK 被拒绝，新租约从 73,008 字节恢复同一对象。采样源独立计数，注入第 17,000 帧丢失后，对象 CRC 校验拒绝该结果。此为加速 PCM、行为 DDR 控制器及模拟竞争流量的离线验证，尚不证明新 v2 的全容量并发、实际 CNN/手机并发、硬件 60 秒录音或物理时限。

本阶段的双采样率后端沿用 Android 已有 `REC_FORMATS 0x43 v1`，由同一 C owner 与 DDR 录音引擎处理。开启选项时使用独立物理 ABI，错配在对象分配前被拒绝；44.1 kHz START 必须先获本次 HELLO 授权，再与真实源格式核对。50 MHz 独立采样源在 10 ms 仿真中产生 441 帧，完成 1,764 字节录制、断线续传和 CRC `bc3b03dc` 校验；CPU 与 BLE 交叉操作同一对象。录制中切换采样率使录音失败，保留原对象的 44.1 kHz 描述符，源 PCM 继续运行。282 项行为检查、4 项故障突变和两个方向的 ABI 错配检查通过；同一当前源码的默认 48 kHz 路径通过 1,765 项行为检查、15 项突变拒绝，136 条消息与原参考逐字节一致。该回归使用宿主编译 C、真实解析/APB/CRC/存储 RTL 和行为 DDR 控制器，未执行完整 AE350、LCD、手机或 DAC。

另保留一个通用旧路径失败：`test_stage_ae350_firmware.py` 的 10 项中有 1 项失败，R00 16 KiB ROM 超出 760 字节。精确父版本对照同样溢出，相关目标文件逐字节相同；本阶段未扩大该 ROM、删除功能或跳过测试。此项与已通过的 v2 成对准备及 W 128 KiB ROM 检查分开记录。

接下来按以下顺序推进：

1. M 同步 wrapper 的来源分类、MIDI release、PC/APB 局部证明已完成；接下来证明两个完整 CPU release/consumer 边界及完整 TF CDC。W 需对优化后分散的 live/batch-active 关系建立分层映射证明，不能只替换历史自动网名。保持失败门禁，不能继承旧候选证明。
2. P1 已绑定 M v3 的真实失败实现：SDC 对象表达问题已修复，布线仍有 1,168 条未布通网络。先在相同 VG/CST/SDC 上限时比较另一布线算法，结合 CLS、时钟/复位资源和高扇出网络定位拥塞，再选局部分拍或迁移；完整布通后核对 setup/hold/recovery/removal，不降低时钟或放宽 false path。此前用户提到的两次 M 超时仍未绑定本地可核验日志，与本次自然失败分开保留。
3. 根据新资源决定下一个迁移。优先验证现有存储改动；旧 TF 客户端、25K 绘制和 BLE owner 的数字需先对应实际 compiled owner，避免重复优化已退出路径。混响、FFT/显示分析及扩展合成按链路余量逐项选择，不做全量重写。
4. 正确目标板接入后，先核对两板身份、引脚/电平和 LCD 实测预算，再做 M 独立演奏/DAC 延迟、TF→W CNN→Push、手机 D 按放效果及 60 秒录音/下载并发验收。44.1 kHz 后端格式授权与对象描述符已完成离线验证，仍需补齐兼容的跨板 ARM、M 真实输出/tap 格式与 W ingress 的采样率绑定，再单独验证协议与音频。当前成对配置继续拒绝 44.1 kHz 录音。

每阶段提交并 push 源码、配置和结构化证据，保留失败项与回退入口。必要 SRAM 验证沿用本任务授权，但必须先核对正确目标；Flash 仍需单独授权。

当前资源、优先级和预算复核见 [priority review](push2_workstation/usb_a/reports/DUAL138K_TASK3_PRIORITY_REVIEW_20261105.json)。对应实现证据见 [M 同步存储](push2_workstation/usb_a/reports/DUAL138K_TASK3_M_SYNC_STORAGE_20261105.json)、[paired profiles](push2_workstation/usb_a/reports/DUAL138K_TASK3_PHONE_BATCH_PROFILES_20261103.json)、[phone batch 负载](push2_workstation/usb_a/reports/DUAL138K_TASK3_PHONE_BATCH_20261103.json)、[混响子系统](push2_workstation/usb_a/reports/DUAL138K_TASK3_REVERB_SYNTHESIS_20261101.json)和 [PR 审查与选用](push2_workstation/usb_a/reports/DUAL138K_TASK3_PR_INTEGRATION_20261103.json)。
