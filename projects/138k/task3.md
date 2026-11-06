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

截至 2026-11-06，最新实验来源检查点为两板 v19。M 显式启用 TF 尾帧的本域复位释放，完成新综合及 P3R0 布线；局部复位证明通过，但整机时序退步，保留 v17 EC 为较好的物理对照，不能把新位流当作验收版本。W 配置不变，继续实际承担识别、手机接收/解码及唯一录音对象；完整时序、CDC 和目标板验收尚未完成。

| 板与阶段 | 来源身份 | 实际证据 |
| --- | --- | --- |
| M v19 实验来源 | `custom138k-workstation-task3-m-paired-checkpoint-v19-39a8a5b0e54fe1bd`；[配置](push2_workstation/usb_a/boards/custom_138k/workstation_profile_task3_m_paired_checkpoint_v19.json) | 970 项来源锁、287 项编译输入、691 项准备文件。实际新综合：58,408 Register、68,786 LUT、28,044 ALU、212 BSRAM 等效、254 RAM16；审计 21/23。最终准备与初次准备的全部编译字节相同，按证据复用本次原始综合输出。 |
| M v19 EE 物理结果 | `custom138k-resource-physical-D21106EE`；[证据](push2_workstation/usb_a/reports/DUAL138K_TASK3_M_TF_TAIL_LOCAL_RESET_20261106.json) | 同约束 P3R0，471.15 秒后完成布线及位流生成；Logic 99135、Register 58408、BSRAM 253/340、CLS 61932/69120。setup/hold/recovery/removal 为 -9.620/-3.791/-6.381/0.278 ns；较 EC 退步，未部署。 |
| M v17 EC 保留物理对照 | `custom138k-resource-physical-D21106EC`；[证据](push2_workstation/usb_a/reports/DUAL138K_TASK3_M_LEASE_SOURCE_20261106.json) | 已布通；Logic 99155、Register 58418、BSRAM 253/340、CLS 62407/69120。setup/hold/recovery/removal 为 -8.098/-3.612/-5.369/0.281 ns，仍未满足时序，未部署。 |
| W v19 当前来源 | `custom138k-workstation-task3-w-paired-checkpoint-v19-8fa8ad054527db4d`；[配置](push2_workstation/usb_a/boards/custom_138k/workstation_profile_task3_w_paired_checkpoint_v19.json) | 1018 项来源锁、200 项编译输入、675 项准备文件。runtime 源码新增默认关闭的选项，W 的 TF 分支仍关闭；不能声称编译字节未变。本阶段没有新 W 综合或物理运行。 |
| W v14 E9 保留物理结果 | `custom138k-resource-physical-D21106E9`；[证据](push2_workstation/usb_a/reports/DUAL138K_TASK3_W_CNN_READY_SDC_20261106.json) | 已布通，真实 BSRAM 336/340、CLS 58,819/69,120；审计 11/18，setup/hold/recovery/removal 为 -7.224/-4.350/-7.947/-0.234 ns。结果不改名归到 v19。 |

v19 复用 runtime 已有的两级启动采样和三级本域释放链，不新增复位寄存器。公共断言仍异步有效，compute 与 serial 各自等待本域时钟；会话取消或切换时钟不复位在途 mailbox。维护 RTL 提供默认关闭的参数，只有显式 M v19 配置启用；来源可精确逆变换，36 份历史检查点描述符未改，v18 父候选保持可验证。既有 50 MHz 手机租约源寄存级、真实 PCM owner 身份及 32 声部普通/矢量合成继续保留。

[本轮验证](push2_workstation/usb_a/reports/DUAL138K_TASK3_M_TF_TAIL_LOCAL_RESET_20261106.json)完成 45 项测试方法，无跳过；尾帧端点的旧/新配置分别拒绝 7/9 个协议故障，新网表复位检查拒绝 10 个故障，手机租约回归拒绝 14 个故障。覆盖双时钟停转时的短复位、独立释放、取消、排空和重新 ARM。实际网表证明 10 个既有释放寄存器及 1,416 个 TF 尾帧/本地排空寄存器的复位连接，根启动信号不再直达这些状态的 D/CE。该证明不替代完整 TF mailbox、Gray、CDC 或真实 DAC 延迟验收。

EE 与 EC 的物理 CST、SDC 逐字节相同，没有放宽时钟或例外；位流 SHA256 为 `f9ba4a843a0ce1cd29215f4f522111d5e0025d76b3e2b069a0166b0a1e9b959d`，没有目标板读回。clk50/audio 实际 Fmax 为 33.833/44.167 MHz，低于 EC 的 44.261/63.967 MHz；HDMI 像素时钟也未满足要求。新最差 setup 为音频域 `input_owner/panic_seen` 到事件队列，clk50 的会话身份到 TX payload 路径为 -9.556 ns。`compute_release[2]` 扇出 13,792，`reset_n` 扇出 8,786；PR1014 和 DDR hold 失败继续保留。

两个完整 CPU release/consumer 门禁仍失败，旧清单未刷新。新网表只读诊断列出源侧 403 个 ram_clk CLEAR 端点及两个 CPU 黑盒引脚，目的侧有 9,502 个 clk50 寄存器引脚、22 个存储引脚及七个顶层输出；须继续证明实际语义和完整握手。先前 [403 个源侧 FF 与外部 APB 方程核查](push2_workstation/usb_a/reports/DUAL138K_TASK3_M_P3_SOURCE_REVIEW_20261106.json)仍是独立证据，不转作目的侧或正式 CDC 通过。

新路由的完整 PLL/startup 审计仍因 grant receiver 原语要求和 held-handshake 约束选择失败，未删除检查。首次调用未发现 macOS 仿真库，显式指定已安装的 `GOWIN_SIMLIB` 后重跑得到上述实际失败；两次日志均保留。[v18 来源封存和 PLL 局部复核](push2_workstation/usb_a/reports/DUAL138K_TASK3_PAIRED_PHYSICAL_PROFILE_20261106.json)保留各自原始证据，不改称本轮结果。

历史 M [终态流水线](push2_workstation/usb_a/reports/DUAL138K_TASK3_M_TERMINAL_PIPELINE_20261106.json)、[128 位身份比较](push2_workstation/usb_a/reports/DUAL138K_TASK3_M_IDENTITY_GROUPING_20261106.json)、[96 位手机身份比较](push2_workstation/usb_a/reports/DUAL138K_TASK3_M_PHONE_IDENTITY_20261106.json)和 [P2R0 失败比较](push2_workstation/usb_a/reports/DUAL138K_TASK3_M_PHONE_ROOT_PHYSICAL_20261106.json)保留各自原始资源、来源、时序与失败结果。W 的独立 16 KiB 录音 API 溢出也保留为失败；选用的 128 KiB 手机/录音固件具有独立准备及 ELF 审计证据。

远程成果已由 `f96df276` 审查后采用：PR #2 的 CPU48 分银行 RAM 已用于 M，CPU48 阶段进一步选入 W；两份实际网表均逐字验证 24 个块、12,288 个 ROM 字，原集成对比为 32→24 块。W 实际物理容量及布线结果进一步证明该选用的收益。PR #3 的独立 USB/HDMI 诊断、复位和状态新鲜度修复也已保留。ADSR/TF ring 仍是实验，退出的重复录音后端未选入。CPU48 来源与物理阶段分别提交并推送为 `1e0ebca6`、`5ec7b183`；此前 git fetch 超时仍保留为失败记录，未将其报告为成功 pull。取舍见 [PR 审查与选用](push2_workstation/usb_a/reports/DUAL138K_TASK3_PR_INTEGRATION_20261103.json)。

后续按以下顺序推进：

1. 以 v19 EE 和 v17 EC 的同约束结果定位复位扇出、布局和路径变化，保留 v16 EB 及 P2R0 对照。TF 尾部复位修改通过局部检查但未改善整机时序；下一步优先处理 PANIC/事件队列、会话身份到 TX payload 的宽组合路径及本域复位扇出，再检查 reply CE、混响和滑音。不放宽时钟、时序预算或 false path。
2. 关闭 M 两个完整 CPU release/consumer 边界与完整 TF CDC；将已通过的 403 个源侧 FF 和外部 APB 方程核查接入新显式检查点前，继续证明目的侧和完整握手，不刷新旧哈希。W 录音/CNN 故障与 CNN 本域复位的局部旁路已修复；v14 的正式就绪 SDC 绑定已验证。完整 batch 仍被历史生成网名的四字身份比较证明阻挡；下一步按实际语义 consumer 证明完整身份、live 和请求/回复路径，核对 DDR/配置 payload hold、剩余高扇出复位、PR1014 及完整 PLL 门禁。局部命令、录音、MIDI 或根状态证明不能替代这些门禁。
3. W CPU48 已完成真实物理容量与布线核查，但时序和完整门禁仍失败。结合仅余 4 块 BSRAM 和 LCD 预算，选择重型效果、FFT/显示分析及扩展合成迁移。W 实际网表已含 32 个 BSRAM 等效的效果链，其中混响占 20 个；优先审查将其复用为受 M 参数控制的有界计算分支，不能直接假定还能叠加一套混响或 FFT。该复用尚未选入整机。已移至 W 的识别、手机解码与唯一录音/下载对象继续保留；旧 TF 客户端、25K 绘制、BLE owner 的数字仍须对应实际编译路径。
4. 正确目标板接入后，先核对两板身份、引脚/电平和 LCD 有效吞吐、往返延迟、拥塞，再验收 M 独立演奏/DAC 延迟、TF→W CNN→Push、手机 D 按放效果与 60 秒录音/下载并发。44.1 kHz 后端仍需兼容的跨板 ARM 及真实来源格式绑定；当前成对配置只接纳 48 kHz 录音。

必要 SRAM 验证沿用本任务授权，须先识别正确目标；Flash 仍需单独授权。每阶段完成相关验证后 commit、push 并更新证据。

历史来源及资源基线见 [priority review](push2_workstation/usb_a/reports/DUAL138K_TASK3_PRIORITY_REVIEW_20261105.json)、[M 同步存储](push2_workstation/usb_a/reports/DUAL138K_TASK3_M_SYNC_STORAGE_20261105.json)、[paired synthesis](push2_workstation/usb_a/reports/DUAL138K_TASK3_PAIRED_SYNTHESIS_20261105.json)、[录音格式](push2_workstation/usb_a/reports/DUAL138K_TASK3_RECORD_FORMATS_20261105.json)、[W consumer 诊断](push2_workstation/usb_a/reports/DUAL138K_TASK3_W_CONSUMER_MUX_SAT_20261105.json)和 [混响子系统](push2_workstation/usb_a/reports/DUAL138K_TASK3_REVERB_SYNTHESIS_20261101.json)。
