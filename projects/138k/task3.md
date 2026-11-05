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

截至 2026-11-06，最新来源检查点为两板 v6；实际综合参考为 M v5、W v2。M v5 已将识别结果终态校验分为两拍，实际整机综合相对 M v3 减少 473 LUT、20 ALU，增加 33 个寄存器，BSRAM/RAM16 数量不变。两板 v6 仅封存后续审计修正，与各自 v5 的编译输入、配置、约束和固件二进制逐字节相同，均未另跑综合。

| 板 | 选定来源与身份 | 验证边界 |
| --- | --- | --- |
| M v5 实际参考 | `custom138k-workstation-task3-m-paired-checkpoint-v5-509346bb5c4bff42`；[配置](push2_workstation/usb_a/boards/custom_138k/workstation_profile_task3_m_paired_checkpoint_v5.json) | 综合完成：58,417 Register、68,733 LUT、28,054 ALU、212 BSRAM 等效、254 RAM16。外部审计 20/22；32 声部、普通/矢量结构、score/tap BSRAM、CPU48 ROM、PLL/USB/MIDI 局部检查通过；两个完整 CPU consumer 门禁仍拒绝。物理诊断结果另列。 |
| W v2 实际参考 | `custom138k-workstation-task3-w-paired-checkpoint-v2-c93ee337298bcad6`；[配置](push2_workstation/usb_a/boards/custom_138k/workstation_profile_task3_w_paired_checkpoint_v2.json) | 已综合：49,458 Register、63,986 LUT、16,347 ALU、308 BSRAM 等效、779 RAM16。完整审查 11/18，优化后的 live/batch 映射仍待证明；不能只替换自动网名。保留 60 秒单对象，真实录音/下载未验收。 |
| M v6 当前来源 | `custom138k-workstation-task3-m-paired-checkpoint-v6-c9e610228d97154d`；[配置](push2_workstation/usb_a/boards/custom_138k/workstation_profile_task3_m_paired_checkpoint_v6.json) | 943 项来源锁、287 项编译输入，准备和校验通过；运行配置等于 v5。新增精确终态流水线复位来源审计，不继承 v5 综合或物理验收。 |
| W v6 当前来源 | `custom138k-workstation-task3-w-paired-checkpoint-v6-b802f5e84c9fc673`；[配置](push2_workstation/usb_a/boards/custom_138k/workstation_profile_task3_w_paired_checkpoint_v6.json) | 991 项来源锁、200 项编译输入，准备和校验通过；运行配置等于 v5。最新实际资源仍绑定 W v2。 |

表内资源来自各自 XML 综合统计，物理 BSRAM 分配另记。M v5 的 50 MHz 与 76.8 MHz 域综合估算为 41.463/58.620 MHz，M v3 为 41.597/58.651 MHz；整体估算仍未达标。W v2 对应为 48.618/72.254 MHz。局部流水线的改善尚未成为整机时序改善，综合估算也不代替 routed STA。

最新 [M 终态流水线与完整验证证据](push2_workstation/usb_a/reports/DUAL138K_TASK3_M_TERMINAL_PIPELINE_20261106.json)记录源码、两板配置、VG/XML/log 哈希及回退。collector 仅增加一个有界终态槽，收下最后音符与终态后，下一拍核验已提交的计数；暂停结果入口一拍，reset、cancel、PANIC 或断链立即撤销有效性。容量仍为 2048 音符，跨板身份和 32 位协议计数保留；复用稳定任务身份，避免再复制 128 位。M 的基础采样、权威参数、HDMI/DAC、W 计算和唯一录音对象均未改动。

独立 Gowin 探针在同一 100 MHz 约束下，collector 的参考/直接/流水线综合估算分别为 75.216/74.616/109.349 MHz，LUT 为 368/367/200，寄存器为 314/314/361，均保留一个真实 SDPB。这是子系统结果。四种 RTL 模式和真实同步映射均完成 9,502 拍检查，覆盖满曲、追加、同拍最后音符/终态、128 位陈旧身份、计数高位、撤销和上游载荷变化；五个语义故障均被拒绝。真实 TF 分析源与 collector 的离线组合也通过，使用确定性 PCM/W 响应，尚非真实卡、CNN 或 LCD 验收。

M v5 的 `terminal_ready` 已含 pending 条件，综合根复位改名为 `reset_n`。审计仅在新配置及两份 RTL 精确哈希匹配时接纳它，并验证其为真实 `u_reset.started/Q` 的唯一正向输出、35 个状态位的全部 `2^35` 个下一拍状态赋值。原始失败审计 14/22 及修正后的 20/22 均保留。37 项来源/配置回归与 16 项新旧 M 网表测试通过，220 项篡改被拒绝；两个完整 CPU consumer 门禁和完整 TF CDC 未据此放行。

M v5 已按维护入口以 `D21106E1`、布局 2/布线 0 完成离线诊断：699.30 秒后自然失败，剩余 362 条未布通网络。物理 CST/SDC 与 M v3 同选项参考逐字节一致；旧结果为 1,168 条，此次减少 806 条，但仍不能称布通或时序改善。失败报告资源为 Logic 99,067/138,240、Register 58,417、CLS 61,314/69,120（89%）、BSRAM 253/340，PRIMARY 与 LW 均为 8/8。VO 属于失败实现，无完整 STA 或位流；UserCode 仅为请求值，未操作板卡。

物理回退参考仍为 M v3 `custom138k-workstation-task3-m-paired-checkpoint-v3-110816887ce99741`：算法 0 自然失败，1,168 条未布通网络；同输入算法 1 在 900 秒上限终止。其来源、约束对象修复、失败物理资源及高扇出诊断保存在 [release/physical](push2_workstation/usb_a/reports/DUAL138K_TASK3_M_RELEASE_AND_PHYSICAL_20261105.json)与 [route comparison](push2_workstation/usb_a/reports/DUAL138K_TASK3_M_ROUTE_COMPARISON_20261105.json)。v3/v4/v5 描述符与封存输入均保留，task2、单板分支和原候选未被替换。两板均无本阶段板上身份、实测声音延迟或硬件通过结论。

远程成果已由 `f96df276` 审查后采用：PR #2 的 CPU48 分银行 RAM 用于 M，当前 v5 实际网表逐字验证 24 个块、12,288 个 ROM 字，集成对比为 32→24 块；PR #3 的独立 USB/HDMI 诊断、复位和状态新鲜度修复也已保留。ADSR/TF ring 仍是实验，退出的重复录音后端未选入。2026-11-06 fetch 后 task3 无新增远程提交；取舍见 [PR 审查与选用](push2_workstation/usb_a/reports/DUAL138K_TASK3_PR_INTEGRATION_20261103.json)。

后续按以下顺序推进：

1. 根据 M v5 实际布局/布线结果检查拥塞、时钟/复位扇出和组合路径。部分标量图仍见 `n6538_6` 的 10,137 个复位负载，最长等权链为 147 级、终点为 collector 的 `g_sync_notes.head_valid_s1/D`；宏和缓冲会终止遍历，级数不代表纳秒或物理关键路径。同一部分图的路径追溯从 `configured_identity[0]` 经端点 `new_identity` 的 128 级比较 ALU、Push ready 进入预取；优先评估保持完整身份语义的组合比较重组。继续局部优化，保留异步复位与生命周期，完整布通后核对 setup/hold/recovery/removal，不放宽时钟或 false path。
2. 关闭 M 两个完整 CPU release/consumer 边界与完整 TF CDC；对 W 优化后的 live/batch 关系建立实际网表证明。局部命令、MIDI 或根状态证明不能替代这些门禁；不得刷新历史清单来冒充通过。
3. 结合真实资源与 LCD 余量逐项选择重型效果、FFT/显示分析及扩展合成迁移。已移至 W 的识别、手机解码与唯一录音/下载对象继续保留。旧 TF 客户端、25K 绘制、BLE owner 的资源数字须先对应实际编译路径，不做全量重写。
4. 正确目标板接入后，先核对两板身份、引脚/电平和 LCD 有效吞吐、往返延迟、拥塞，再验收 M 独立演奏/DAC 延迟、TF→W CNN→Push、手机 D 按放效果与 60 秒录音/下载并发。44.1 kHz 后端仍需兼容的跨板 ARM 及真实来源格式绑定；当前成对配置只接纳 48 kHz 录音。

必要 SRAM 验证沿用本任务授权，须先识别正确目标；Flash 仍需单独授权。每阶段完成相关验证后 commit、push 并更新证据。

历史来源及资源基线见 [priority review](push2_workstation/usb_a/reports/DUAL138K_TASK3_PRIORITY_REVIEW_20261105.json)、[M 同步存储](push2_workstation/usb_a/reports/DUAL138K_TASK3_M_SYNC_STORAGE_20261105.json)、[paired synthesis](push2_workstation/usb_a/reports/DUAL138K_TASK3_PAIRED_SYNTHESIS_20261105.json)、[录音格式](push2_workstation/usb_a/reports/DUAL138K_TASK3_RECORD_FORMATS_20261105.json)、[W consumer 诊断](push2_workstation/usb_a/reports/DUAL138K_TASK3_W_CONSUMER_MUX_SAT_20261105.json)和 [混响子系统](push2_workstation/usb_a/reports/DUAL138K_TASK3_REVERB_SYNTHESIS_20261101.json)。
