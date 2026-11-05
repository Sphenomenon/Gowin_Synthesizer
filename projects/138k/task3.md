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

截至 2026-11-06，最新来源检查点为两板 v13。W 的 CNN 复位改为共同异步置位、按各自时钟等待三拍释放；旧 v11 位流及 v12/v13 准备记录保留。v13 正式物理准备因一个失效 SDC 选择器被拒绝，另建 E8 诊断核对实际绑定；诊断不能替代正式生成器修订或整机验收。task2、单板和历史候选均保留。

| 板与阶段 | 来源身份 | 实际证据 |
| --- | --- | --- |
| M v13 当前来源 | `custom138k-workstation-task3-m-paired-checkpoint-v13-4dd0aba0be6244ff`；[配置](push2_workstation/usb_a/boards/custom_138k/workstation_profile_task3_m_paired_checkpoint_v13.json) | 953 项来源锁、287 项编译输入。相对 v11 仅 W CNN/link/task 的未实例化定义改变；M 无本阶段新综合或物理收益结论。实际综合仍参考 v7，物理对比仍用 v5。 |
| W v13 CNN 复位实验 | `custom138k-workstation-task3-w-paired-checkpoint-v13-0753e88e22a7f3b1`；[配置](push2_workstation/usb_a/boards/custom_138k/workstation_profile_task3_w_paired_checkpoint_v13.json) | 1,001 项来源锁、200 项编译输入；综合 49,471 Register、63,891 LUT、16,345 ALU、300 BSRAM 等效、779 RAM16。相对 v11 为 +4 Register、−1,050 LUT、−10 ALU，BSRAM 等效和 RAM16 不变；完整审计 8/17。 |
| W v13 E8 独立物理诊断 | `custom138k-resource-physical-D21106E8`；[证据](push2_workstation/usb_a/reports/DUAL138K_TASK3_W_CNN_DOMAIN_RESET_20261106.json) | 仅将原 2 ns 就绪链约束的失效末级名称重绑定到实存 `backend_sync`；不改变时钟、预算或例外范围。已布通，真实 BSRAM 336/340，时序仍失败；正式生成器尚未同步该变更。 |
| W v11 故障边界回退 | `custom138k-workstation-task3-w-paired-checkpoint-v11-3cbc102ada8e7b2a`；[证据](push2_workstation/usb_a/reports/DUAL138K_TASK3_W_CNN_FAULT_CDC_20261106.json) | 两级故障同步与 native 立即隔离继续保留。旧 P2R0 已布通、BSRAM 336/340，但整机时序失败；不把旧位流或门禁结果归到新候选。 |

v13 的 wrapper 和 task control 各自等待三个控制时钟边沿，native 侧等待三个 DDR 时钟边沿。请求异步撤销时立即清空两域，暂停任一时钟均不能提前释放。只有该 W 策略把 native 排空账本接到 native 末级复位；默认 task 仍保留独立控制/存储复位输入，默认 link 的账本仍跨 memory-only reset 保持原有生命周期。native broker 故障隔离、两级控制故障同步、唯一录音对象和 M 基础采样调度继续保留。

[本阶段报告](push2_workstation/usb_a/reports/DUAL138K_TASK3_W_CNN_DOMAIN_RESET_20261106.json)记录 71 项来源/准备/固件回归和 66 项 provider 负向检查通过，无跳过；其中包含三条完整工作站的干净来源重建。真实 task/broker 配确定性 CNN sink 的 39 项、11 场景检查，以及真实 media/arbiter/raw-store 配 CNN 实例的 22 项检查通过，包括时钟暂停与校准丢失/恢复；它们不证明模型加载、推理质量或完整 HCI 录音。独立 16 KiB AE350 录音 API 回归仍因 ROM 超出 760 字节失败；当前选用的 128 KiB W 手机/录音固件准备通过，两板 USB 固件 ELF、binary、ROM 与 v11 相同。

实际网表中，DDR `memory_release` 到 CNN 范围的控制域 FF 引脚从 10,542 个降到 11 个，仅剩释放链异步清零和状态同步首级 D。到 CNN 核心的直接传播从 7,984 个 FF 引脚、264 个不透明原语端点降为零。三条三级释放链、33 个 native 账本 FF、就绪链和既有故障链的局部证明共拒绝 56 项破坏性变异；该局部证明不覆盖完整 CDC/PLL 或 payload hold。

正式 E7 物理运行在 SDC 第 367 行被 `TA2003` 拒绝，尚未布局或生成位流：综合器保留 `backend_meta→backend_sync`，旧 `model_memory_ready*` 末级名称消失。完整 batch 网表回归 4 项中有 3 项 error：两项被完整四字身份比较的 Boolean 证明阻挡，一项是缺失关联来源文件时的异常类型；未裁掉生成网络、改写历史 consumer 清单或放宽门禁。完整审计还保留 USB FIFO Boolean 映射及失效 SDC 选择器等失败。

E8 使用同一 v13 网表、相同 CST，仅重绑定该条既有 2 ns 约束；实际两级直连、相同复位、无门控 CE、CNN 就绪输入连接及 8 项破坏性检查均通过。它在 318.98 秒自然完成路由与位流生成，输入哈希前后一致。真实资源为 Logic 85,355、Register 49,471、CLS 58,819/69,120、BSRAM 336/340；最差 setup/hold/recovery/removal 分别为 -7.224/-4.350/-7.947/-0.234 ns，setup/hold 违规端点 3,608/75。最差 setup 比 v11 的 −5.679 ns 更差，当前最差路径是 native DDR 仲裁 tag→延迟效果控制；局部修复未证明整机时序改善。完整时序、CDC/PLL 仍未通过；PR1014 仍需处理。位流 SHA-256 为 `e1026e1ba7653d312ab112638651cc7a004a690399498ea8621896911f431d55`，UserCode **请求值** `D21106E8`；无板上读回、SRAM 下载、Flash 写入或硬件功能验收。

[W CPU48 来源与综合证据](push2_workstation/usb_a/reports/DUAL138K_TASK3_W_CPU48_SYNTHESIS_20261106.json)保留 PR #2 的固件容量、栈预算、24 银行及全部 12,288 个 ROM 字证明；两板仍使用该优化，保留真实识别、HCI/SBC 和唯一 60 秒录音对象。v8/v9 的完整物理失败和位流身份保存在对应报告，不改写为新检查点的证据。

M v7 通过显式 `m_identity_compare_policy` 选择 16 组、每组 8 位的完整身份比较。它保留全部 128 位、同拍撤销语义及原有直接比较默认值，不增加寄存器或等待拍；精确反向重建检查保证端点其余字节等于封存的 M v5。完整 M 网表中的该比较从 128 级串行 ALU 缩为最长 8 级 ALU、10 级组合逻辑。两份实际整机 VG 均完成所有 `2^256` 个独立 FF-Q 输入赋值的函数证明，各自 128 个漏位故障均被拒绝。这只证明该组合函数，级数不代表纳秒或整机关键路径。

独立 Gowin 探针的直接/分组比较估算为 152.045/297.354 MHz；两者均为 257 寄存器、128 ALU，分组另用 5 LUT。官方原语仿真核对了所用 NE COUT 的全部 8 行真值。整机 M v7 相对 M v5 增加 37 LUT、2 ALU，寄存器、BSRAM 等效及 RAM16 不变；50 MHz 与 76.8 MHz 域估算仍为 41.463/58.620 MHz，未达标且未改善。综合估算不能替代 routed STA，物理 BSRAM 分配另记。

[身份比较优化与验证证据](push2_workstation/usb_a/reports/DUAL138K_TASK3_M_IDENTITY_GROUPING_20261106.json)记录来源、两板配置、VG/XML/log 哈希及回退。38 项来源/配置回归和新旧 M 网表各 5 项回归通过，无跳过；170 项映射/来源篡改被拒绝。局部与整机比较共拒绝 512 项漏位故障；真实 M 端点/录音 exporter 的确定性回归通过 8 个场景、17 项检查，尚非真实 DAC 或 LCD 验收。

M 的完整审计保持 20/22：`M_paired_release_CDC` 和 `native_held_handshakes` 仍因完整 CPU consumer 清单变化而拒绝；完整 TF CDC 也未据此放行。只读诊断确认 CPU source 最终 release 的 403 个 CLEAR、2 个不透明端点与 M v5 相同；destination 因录音状态映射改变，FF 端点由 9504 变为 9508，尚需逐项功能审查，未刷新历史清单冒充通过。W 的优化映射门禁继续保留。

上一阶段 [M 终态流水线](push2_workstation/usb_a/reports/DUAL138K_TASK3_M_TERMINAL_PIPELINE_20261106.json)仍有效：collector 使用一个有界终态槽，下一拍校验已提交计数，reset、cancel、PANIC 或断链立即撤销；保留 2048 音符容量和完整协议身份。M v5 实际综合比 M v3 减少 473 LUT、20 ALU，增加 33 寄存器；9,502 拍行为检查及五个语义故障验证保存在该报告。

M v7 的 [P2R0 物理诊断](push2_workstation/usb_a/reports/DUAL138K_TASK3_M_IDENTITY_PHYSICAL_20261106.json)以 `D21106E2` 请求值运行，645.04 秒后自然失败，剩余 915 条未布通网络；CST/SDC 与 M v5 逐字节相同。失败物理报告为 Logic 99123/138240（72%）、Register 58417/139095（42%）、CLS 61398/69120（89%）、BSRAM 253/340（75%）、PRIMARY 8/8（100%）、LW 8/8（100%）。本次未布通网络比 M v5 的 362 条多 553 条，物理结果未改善。v7 保留为显式实验来源，不提升为更优物理候选；M v5 继续作为物理对比基线。身份比较链缩短尚不足以解决整机拥塞，没有完整 STA、位流或部署结论。

M v5 的同约束 P2R0 诊断以 `D21106E1` 请求值运行，699.30 秒后自然失败，剩余 362 条未布通网络；失败物理报告为 Logic 99,067、Register 58,417、CLS 61,314/69,120（89%）、BSRAM 253/340，PRIMARY 与 LW 均为 8/8。M v3 同选项为 1,168 条，另一次算法 1 在 900 秒上限终止。失败 VO、局部链缩短或更少未布通网络均不构成完整 STA、位流或部署许可。历史 [release/physical](push2_workstation/usb_a/reports/DUAL138K_TASK3_M_RELEASE_AND_PHYSICAL_20261105.json)与 [route comparison](push2_workstation/usb_a/reports/DUAL138K_TASK3_M_ROUTE_COMPARISON_20261105.json)保留。两板均无本阶段板上身份、实测声音延迟或硬件通过结论。

远程成果已由 `f96df276` 审查后采用：PR #2 的 CPU48 分银行 RAM 已用于 M，CPU48 阶段进一步选入 W；两份实际网表均逐字验证 24 个块、12,288 个 ROM 字，原集成对比为 32→24 块。W 实际物理容量及布线结果进一步证明该选用的收益。PR #3 的独立 USB/HDMI 诊断、复位和状态新鲜度修复也已保留。ADSR/TF ring 仍是实验，退出的重复录音后端未选入。CPU48 来源与物理阶段分别提交并推送为 `1e0ebca6`、`5ec7b183`；此前 git fetch 超时仍保留为失败记录，未将其报告为成功 pull。取舍见 [PR 审查与选用](push2_workstation/usb_a/reports/DUAL138K_TASK3_PR_INTEGRATION_20261103.json)。

后续按以下顺序推进：

1. 以 M v5 为物理对比基线，结合 M v7 的失败结果检查拥塞、时钟/复位扇出和剩余组合路径。身份比较已在实际整机网表中缩短，但整机综合估算未改善；继续定位真实限制，保留异步复位与生命周期，完整布通后核对 setup/hold/recovery/removal，不放宽时钟或 false path。
2. 关闭 M 两个完整 CPU release/consumer 边界与完整 TF CDC；W 录音/CNN 故障与 CNN 本域复位的局部旁路已修复；先把实测就绪末级的选择器重绑定移入正式生成器，补正向、旧选择器拒绝及精确逆变换回归，准备新身份。完整 batch 仍被四字身份比较证明和缺失来源异常类型阻挡；继续核对 DDR/配置 payload hold、剩余高扇出复位路径和 PR1014。为新网表补齐完整 live/batch 功能证明，保留历史 consumer 清单与失败；局部命令、录音、MIDI 或根状态证明不能替代这些门禁，不放宽时钟或 false path。
3. W CPU48 已完成真实物理容量与布线核查，但时序和完整门禁仍失败。结合仅余 4 块 BSRAM 和 LCD 预算，选择重型效果、FFT/显示分析及扩展合成迁移。W 实际网表已含 32 个 BSRAM 等效的效果链，其中混响占 20 个；优先审查将其复用为受 M 参数控制的有界计算分支，不能直接假定还能叠加一套混响或 FFT。该复用尚未选入整机。已移至 W 的识别、手机解码与唯一录音/下载对象继续保留；旧 TF 客户端、25K 绘制、BLE owner 的数字仍须对应实际编译路径。
4. 正确目标板接入后，先核对两板身份、引脚/电平和 LCD 有效吞吐、往返延迟、拥塞，再验收 M 独立演奏/DAC 延迟、TF→W CNN→Push、手机 D 按放效果与 60 秒录音/下载并发。44.1 kHz 后端仍需兼容的跨板 ARM 及真实来源格式绑定；当前成对配置只接纳 48 kHz 录音。

必要 SRAM 验证沿用本任务授权，须先识别正确目标；Flash 仍需单独授权。每阶段完成相关验证后 commit、push 并更新证据。

历史来源及资源基线见 [priority review](push2_workstation/usb_a/reports/DUAL138K_TASK3_PRIORITY_REVIEW_20261105.json)、[M 同步存储](push2_workstation/usb_a/reports/DUAL138K_TASK3_M_SYNC_STORAGE_20261105.json)、[paired synthesis](push2_workstation/usb_a/reports/DUAL138K_TASK3_PAIRED_SYNTHESIS_20261105.json)、[录音格式](push2_workstation/usb_a/reports/DUAL138K_TASK3_RECORD_FORMATS_20261105.json)、[W consumer 诊断](push2_workstation/usb_a/reports/DUAL138K_TASK3_W_CONSUMER_MUX_SAT_20261105.json)和 [混响子系统](push2_workstation/usb_a/reports/DUAL138K_TASK3_REVERB_SYNTHESIS_20261101.json)。
