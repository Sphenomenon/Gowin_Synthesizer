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

截至 2026-11-06，最新来源检查点为两板 v15。本阶段只优化 M 手机命令的完整身份比较，保留实际迁至 W 的识别、手机接收/解码及唯一录音对象。W 的全部准备输入与 v14 相同；旧候选和失败结果继续保留，整机时序、完整 CDC 与目标板验收仍未完成。

| 板与阶段 | 来源身份 | 实际证据 |
| --- | --- | --- |
| M v15 当前来源 | `custom138k-workstation-task3-m-paired-checkpoint-v15-1d782f7c4f78fb86`；[配置](push2_workstation/usb_a/boards/custom_138k/workstation_profile_task3_m_paired_checkpoint_v15.json) | 960 项来源锁、287 项编译输入。新综合为 58,417 Register、68,786 LUT、28,044 ALU、212 BSRAM 等效、254 RAM16；完整审计 13/22。无本阶段物理结果或位流。 |
| W v15 当前来源 | `custom138k-workstation-task3-w-paired-checkpoint-v15-7c23d96955b9a2ab`；[配置](push2_workstation/usb_a/boards/custom_138k/workstation_profile_task3_w_paired_checkpoint_v15.json) | 1008 项来源锁、200 项编译输入；全部准备输入、CST/SDC 与 v14 逐字节相同，无新综合或物理运行。v14 实际综合为 49,471 Register、63,891 LUT、16,345 ALU、300 BSRAM 等效、779 RAM16。 |
| W v14 E9 保留物理结果 | `custom138k-resource-physical-D21106E9`；[证据](push2_workstation/usb_a/reports/DUAL138K_TASK3_W_CNN_READY_SDC_20261106.json) | 已独立布通，真实 BSRAM 336/340，完整审计 11/18，时序仍失败。结果不改名归到 v15。 |

[M v15 报告](push2_workstation/usb_a/reports/DUAL138K_TASK3_M_PHONE_IDENTITY_20261106.json)记录了从实际 M v7 综合报告定位的 96 级手机身份比较。新显式策略把全部 boot/session/generation 共 96 位分成 12 组、每组 8 位比较；同拍 ARM/DATA/CANCEL 判断和撤销保持原样，无新增状态或等待拍。精确逆变换必须恢复封存的端点及 board 字节，原有 128 位整对身份检查也继续验证。基础合成、参数应用、D 效果和采样调度均保留。

完整 M 新旧 VG 分别通过全部 `2^192` 个独立 FF-Q 输入赋值的函数证明，各自 96 项漏位故障被拒绝；新比较最长为 7 级 ALU、10 级组合逻辑。原 128 位比较在新整机 VG 中另经全部 `2^256` 个输入赋值和 128 项漏位检查。两个局部 Gowin 探针及原比较工具的兼容性证据也在报告中，逻辑级数均不代表物理延迟。

来源、选择与两板准备/回退检查共 36 项通过，无跳过；直接比较和分组比较各通过端点的 5 个场景、57 项检查及 4 项行为故障。模拟中的独立采样计数不作为真实 DAC 证据。新综合用时 207.36 秒，输入哈希前后一致；相对 M v7 少 12 ALU、多 16 LUT，寄存器、存储和 DSP 数量不变。50 MHz 与 76.8 MHz 域估算仍为 41.463/58.620 MHz，整机频率未改善。最终准备 v3 与实际综合来源 v1 的全部 688 项准备输入逐字节相同，复用收据绑定同一原始 VG；未重复声称一次新综合。

v15 显式保留完整 batch 映射及 MIDI release SDC 门禁。当前 root/publisher 审查只接纳既有 v7 身份来源，因此 v15 完整审计以 `identity root profile/policy mismatch` 拒绝，相关 batch、release 和 CDC/PLL 门禁仍未通过。13/22 不能与旧 v7 的 20/22 当作同一来源的硬件退化或改善；本阶段的两个局部函数证明不替代完整边界验证。旧 CPU consumer 清单未刷新，完整 TF CDC 也未放行。

M 物理比较仍以 v5 为基线：同约束 P2R0 在 699.30 秒后自然失败，剩 362 条未布通网络；Logic 99,067、Register 58,417、CLS 61,314/69,120、BSRAM 253/340。v7 在 645.04 秒后失败，剩 915 条；Logic 99,123、CLS 61,398/69,120，PRIMARY/LW 均为 8/8。v15 尚无新 P&R，不提升为物理更优候选。[终态流水线](push2_workstation/usb_a/reports/DUAL138K_TASK3_M_TERMINAL_PIPELINE_20261106.json)、[128 位比较](push2_workstation/usb_a/reports/DUAL138K_TASK3_M_IDENTITY_GROUPING_20261106.json)、[v7 物理失败](push2_workstation/usb_a/reports/DUAL138K_TASK3_M_IDENTITY_PHYSICAL_20261106.json)及 [v5 对比](push2_workstation/usb_a/reports/DUAL138K_TASK3_M_ROUTE_COMPARISON_20261105.json)保留原证据。

W v14 的正式就绪 SDC 重绑定保留既有 2 ns 预算，正向/逆向及实际两级映射已验证；E9 自然完成路由与位流生成，Logic 85,355、Register 49,471、CLS 58,819/69,120、BSRAM 336/340。最差 setup/hold/recovery/removal 为 -7.224/-4.350/-7.947/-0.234 ns，setup/hold 违规端点 3,608/75；PR1014、四字身份比较、USB FIFO Boolean 映射及完整 CDC/PLL 仍未关闭。位流 SHA-256 为 `058f909025b8f4db02243d835c3ac9c14e5b46487851970e6a8eed5be8576e60`，UserCode 请求值 `D21106E9`，无板上读回或部署。独立 16 KiB AE350 录音 API 的 760 字节溢出仍保留；选用的 128 KiB W 手机/录音固件已通过准备与实际 ELF 审计。

远程成果已由 `f96df276` 审查后采用：PR #2 的 CPU48 分银行 RAM 已用于 M，CPU48 阶段进一步选入 W；两份实际网表均逐字验证 24 个块、12,288 个 ROM 字，原集成对比为 32→24 块。W 实际物理容量及布线结果进一步证明该选用的收益。PR #3 的独立 USB/HDMI 诊断、复位和状态新鲜度修复也已保留。ADSR/TF ring 仍是实验，退出的重复录音后端未选入。CPU48 来源与物理阶段分别提交并推送为 `1e0ebca6`、`5ec7b183`；此前 git fetch 超时仍保留为失败记录，未将其报告为成功 pull。取舍见 [PR 审查与选用](push2_workstation/usb_a/reports/DUAL138K_TASK3_PR_INTEGRATION_20261103.json)。

后续按以下顺序推进：

1. 先为实际 M v15 VG 绑定完整 root/publisher、batch 和 release 证明，保持旧清单与历史失败；再以 M v5 为物理对比基线复跑布局布线。96 位和 128 位比较均已缩短，但整机估算未改善，须继续检查其余组合路径、拥塞、时钟/复位扇出。完整布通后核对 setup/hold/recovery/removal，不放宽时钟或 false path。
2. 关闭 M 两个完整 CPU release/consumer 边界与完整 TF CDC；W 录音/CNN 故障与 CNN 本域复位的局部旁路已修复；v14 已将就绪末级重绑定移入正式生成器，相关映射与逆变换检查通过。完整 batch 仍被历史生成网名的四字身份比较证明阻挡；缺失来源异常类型已修复。下一步基于实际语义 consumer 重新证明完整身份、live 和请求/回复路径；继续核对 DDR/配置 payload hold、剩余高扇出复位路径和 PR1014。为新网表补齐完整 live/batch 功能证明，保留历史 consumer 清单与失败；局部命令、录音、MIDI 或根状态证明不能替代这些门禁，不放宽时钟或 false path。
3. W CPU48 已完成真实物理容量与布线核查，但时序和完整门禁仍失败。结合仅余 4 块 BSRAM 和 LCD 预算，选择重型效果、FFT/显示分析及扩展合成迁移。W 实际网表已含 32 个 BSRAM 等效的效果链，其中混响占 20 个；优先审查将其复用为受 M 参数控制的有界计算分支，不能直接假定还能叠加一套混响或 FFT。该复用尚未选入整机。已移至 W 的识别、手机解码与唯一录音/下载对象继续保留；旧 TF 客户端、25K 绘制、BLE owner 的数字仍须对应实际编译路径。
4. 正确目标板接入后，先核对两板身份、引脚/电平和 LCD 有效吞吐、往返延迟、拥塞，再验收 M 独立演奏/DAC 延迟、TF→W CNN→Push、手机 D 按放效果与 60 秒录音/下载并发。44.1 kHz 后端仍需兼容的跨板 ARM 及真实来源格式绑定；当前成对配置只接纳 48 kHz 录音。

必要 SRAM 验证沿用本任务授权，须先识别正确目标；Flash 仍需单独授权。每阶段完成相关验证后 commit、push 并更新证据。

历史来源及资源基线见 [priority review](push2_workstation/usb_a/reports/DUAL138K_TASK3_PRIORITY_REVIEW_20261105.json)、[M 同步存储](push2_workstation/usb_a/reports/DUAL138K_TASK3_M_SYNC_STORAGE_20261105.json)、[paired synthesis](push2_workstation/usb_a/reports/DUAL138K_TASK3_PAIRED_SYNTHESIS_20261105.json)、[录音格式](push2_workstation/usb_a/reports/DUAL138K_TASK3_RECORD_FORMATS_20261105.json)、[W consumer 诊断](push2_workstation/usb_a/reports/DUAL138K_TASK3_W_CONSUMER_MUX_SAT_20261105.json)和 [混响子系统](push2_workstation/usb_a/reports/DUAL138K_TASK3_REVERB_SYNTHESIS_20261101.json)。
