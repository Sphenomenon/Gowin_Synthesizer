# 项目验证记录

## Fedora兼容修复与138K迁移（2026-09-09，本轮未上板）

本轮完整42项HDL回归通过，259项Python/Tk为258通过＋1项Windows专用跳过。Icarus13两处声明顺序、可重定位工具路径和Tk测试窗管理器干扰已修。新隔离Prj1兼容版setup/hold均0，位流SHA-256为`5b6e447af6c5cf93c26c2a77bf8844b2bf80f95b5aa38cd9e07a70afec59cd7c`；原11:07位流及证据不变。

另有独立48k MIDI＋原三模式/五音色/效果核心＋PT8211＋DDR/HDMI候选，已通过仿真及构建/路由审核，尚未下载。两版本协议和采样率不同，完整输出目录、哈希、限制及日志见[迁移总记录](../../../../migration/MIGRATION_PROGRESS.md)。下面所有历史资源与板测仍只适用于各自版本。

更新日期：2026-09-09。当前新增总体音量、L/R平衡并取消固定除32，详见首节；DDR3/1080p60的已确认板测记录属于历史显示版。**官方PLL初始化对照版（15:06，2ba120fe）手动下载并按S3后，用户确认稳定显示项目画面。** 串口12次完整快照确认DDR=0xCB、像素平均频率约148.5MHz、扫描与渲染约60帧/s、欠载0。用户已确认显示器信息页1920×1080/60Hz，GUI正弦演奏驱动HDMI波形、峰值和声部指示变化，松键后回落。此前的无信号、反复失锁和诊断记录保留在下方，不能混作当前版本结论。

## 总体音量、L/R 平衡与完整幅度混音（2026-09-09 11:07）

当前 [Prj1.fs](../impl/pnr/Prj1.fs) 生成于 **2026-09-09 11:07:09（Asia/Shanghai）**，固定备份 [output_gain_20260909.fs](../build/output_gain_20260909.fs)，SHA-256：`ec6cdfe64e0b1bada68446cc0c8ff10d45c340bf69657e0b0e0b798bb49c81ba`。**本轮未下载、未访问串口、未做耳机或 HDMI 板测。** 下载此版并重启 GUI 后才会启用新的总体音量与平衡控制。

取消按32槽固定衰减，保留40位完整混音，通过总体音量和左右平衡后才饱和。默认总体100%、平衡居中且两路均为单位增益；最长5.24288ms平滑过渡。FFT、结像和波形继续解码最终PT8211串行PCM。行为、协议及过载规则见[输出控制](output_controls.md)。

- **42项 HDL 全量通过**，[摘要](evidence/hdl_summary_output_gain_20260909.txt)、[完整日志](evidence/hdl_output_gain_20260909.log)。包含原FFT/HOLD/DDR/HDMI/串口回归和3项新增输出测试。
- [共享声部独立模型](evidence/hdl_voice_bank_tdm_output_gain_20260909.log)：1329帧逐位比对32个并行参考声部，单音满量程、正负32声部完整相加、饱和、225周期计算和逐声部样本标签均通过。
- [音量级独立80位整数模型](evidence/hdl_audio_output_stage_output_gain_20260909.log)：1336帧，覆盖分数增益、正负宽位输入、左右平衡、平滑反向、帧内目标改变及贡献阈值。
- [真实输出链路](evidence/hdl_output_gain_integration_output_gain_20260909.log)：32声部引擎→音量级→PT8211→观察器，独立解码1613个串行帧；单声部满幅为`7FFF/7FFF`，双满幅声部、总体25%为`4000/4000`，证明没有先削波；全左/全右为`4000/0000`和`0000/4000`。静音、非法命令、PANIC、声音版本及234周期/4.68µs最终样本事件一致，全程零欠载。
- [立体声发送边界](evidence/hdl_pt8211_stereo_output_gain_20260909.log)：独立左右正负字、舍入饱和、帧中到达、装载同拍覆盖完整双槽与标签、有效零样本、欠载补零及热复位。[延迟监视器](evidence/hdl_audio_latency_monitor_output_gain_20260909.log)覆盖新增10/11操作码；记录首次新目标版本，不能当作渐变完成。[尾音换音](evidence/hdl_note_transition_output_gain_20260909.log)保持原物理幅度夹具及原跳变量上限，通过3621个样本、18次复用。
- **259项 Python/Tk 全量通过**（22.746s、无跳过），compileall通过；覆盖协议、CLI、离线模拟、默认与重连同步、旧固件拒绝、ACK确认及滑块与音符的队列顺序。替换未发出的总体控制保留原排队位置，不能移到原本排在其后的NOTE_ON之后；另外覆盖已预留但因限速未发送、已发送不重放、PANIC及断线边界。[完整日志](evidence/python_output_gain_20260909.log)。原生Windows Tk在最小1100×940窗口检查总体音量、平衡、琴键和日志区域均未裁剪；[布局数据](evidence/gui_geometry_output_gain_20260909.json)、[复现脚本](evidence/verify_output_control_geometry_20260909.py.txt)。[测试源码与证据哈希](evidence/verification_inputs_output_gain_20260909.json)。
- Gowin最终 **setup=0、hold=0**，最小报告slack **+0.039ns**，最小脉宽slack **+1.325ns**；114个复位端点及11个PLL_INIT端点审核通过，PLL控制最坏 **7.700ns/10ns**。保留8条既有工具告警。工程输入与构建前快照、构建检查器记录逐项哈希一致。[构建证据](evidence/build_evidence_output_gain_20260909.json)、[输入快照](evidence/build_inputs_output_gain_20260909.json)、[构建日志](evidence/build_output_gain_20260909.log)。

| 整个工程资源 | 上一FFT版 | 本版 |
|---|---:|---:|
| Logic | 14904 | 15667 |
| FF | 13226 | 13733 |
| BSRAM | 94 | 94 / 340 |
| DSP | 13.5 | 17.5 / 298 |

[资源报告哈希](evidence/resources_output_gain_20260909.json)。数字仿真不能代替实际耳机输出与HDMI检查。

## 最终输出 FFT 与立体声结像（2026-09-09 10:13，历史构建）

该历史版生成于 **2026-09-09 10:13:15（Asia/Shanghai）**，固定备份 [fft_image_20260909.fs](../build/fft_image_20260909.fs)，SHA-256：`51afde21a55e76210df712c1533f897ed76e3c34fffe42eeae6977438d68fd89`。**本轮未下载、未访问串口、未做 HDMI 或耳机板测。** 当前左右仍复制同一混音，真实结像应为居中竖线，左右频谱重合；预览中的宽度来自独立立体声测试夹具。

观察器重新解码实际 PT8211 BCK/WS/DIN 双槽 PCM16，覆盖舍入/饱和、启动与欠载补零。FFT 分别计算 L/R 的 1024 点 Hann 变换，约 48 Hz–20 kHz 对数显示；各频带取所有覆盖频点的最高值，避免遗漏高频窄峰。结像来自同一未加窗块的 MID-SIDE 点图，带明确的 X1…X128 自动增益。波形改为最终 PCM 的 M 信号，HOLD 只保持波形。参数、坐标和限制见[输出分析](output_analysis.md)。

- **39 项 HDL 全量通过**，[摘要](evidence/hdl_summary_fft_image_20260909.txt)、[完整日志](evidence/hdl_fft_image_20260909.log)。原32声部、尾音换音平滑、UART、延迟、DAC、DDR、HDMI 和 HOLD 回归保留。本轮未改主机工具，未重复执行 Python/Tk 套件；下节233项属于历史主机更新。
- [串行观察器](evidence/hdl_pt8211_observer_20260909.log)：15个真实发送帧、舍入/饱和/半值、启动/欠载、同帧参考，另有8组独立左右串行字及复位。[真实输出到分析](evidence/hdl_final_output_analysis_20260909.log)：PT8211→观察器→异步捕获→双FFT/结像，观察1583个实际串行帧，单声道左右频谱相同且结像只在中轴。
- [分析测试](evidence/hdl_output_audio_analysis_20260909.log)：9组输入覆盖独立频率与幅度、同相/反相/左右单独/静音、PCM16满幅、低电平X128、结果保持和复位。bin417（约19.88kHz）位于最后两个对数端点414/419之间，仍保留左右正确峰高。计算约143254个100MHz周期/**1.433ms**，不含约20.97ms采集和后续显示等待。
- [独立浮点 DFT](evidence/fft_dft_comparison_20260909.json)：左右全部2048个复数bin，整数/分数频点混合与确定性噪声；理想周期Hann直接求和，不复用RTL蝶形调度。复数误差最大L **6.479976**、R **6.090570** 个保护位单位，限值64，RMS约1.330499/1.318185。ROM再生成检查通过。
- [完整光栅](evidence/hdl_analysis_renderer_20260909.log)：1920×1080全帧，逐点检查229376个频谱像素及262144个结像像素；独立频带区间最大值模型、69137拍随机背压、并行下一块捕获及末拍释放。[字形测试](evidence/hdl_feedback_dashboard_20260909.log)另以独立形状断言补充减号和小数点，检查32格与字体流水。
- [正常预览](images/feedback_analysis.png)、[HOLD预览](images/feedback_analysis_hold.png)由实际RTL完整光栅生成并目视检查；HOLD还逐字检查512点波形不变，左右峰值和结像更新到新直流块。它们不证明板上立体声或模拟输出。源码、夹具、像素及日志[哈希绑定](evidence/verification_inputs_fft_image_20260909.json)。
- Gowin最终 **setup=0、hold=0**，报告最小slack **+0.021ns**，最小脉宽slack **+1.325ns**。114个复位端点与11个PLL_INIT端点独立审核通过，PLL控制最坏 **7.869ns/10ns**。一轮中间布线的PLL复位路径10.070ns未通过；PLL RESET不形成工具普通时序路径，因此移除无有效路径的试验性约束，改用显式时序优先布局算法2后重新布局布线；独立10ns审核门限保留。所有SDC约束生效且每个最大延迟约束都有实际路径。保留8条既有工具告警（起音监测指针1、官方PLL计数4、字体优化2、时钟通用路由1），未新增FFT告警。[构建证据](evidence/build_evidence_fft_image_20260909.json)、[输入哈希](evidence/build_inputs_fft_image_20260909.json)、[日志](evidence/build_fft_image_20260909.log)。

| 整个工程资源 | 本版用量 |
|---|---:|
| Logic | 14904 |
| FF | 13226 |
| BSRAM | 94 / 340 |
| DSP | 13.5 / 298 |

[资源报告哈希](evidence/resources_fft_image_20260909.json)。下载上述哈希到SRAM后检查正弦峰位、左右重合/居中、和弦HOLD时分析更新、松键清空、DDR欠载和复位恢复。屏幕反映DAC数字输入，功放静音和模拟耳机响应不在采样范围内。

## 主机低延迟与有界异步收发（2026-09-08）

本轮只更新 Python 主机工具；233 项 Python/Tk 测试通过，包括 31 项传输计时/异步/故障用例、27 项 worker 对抗用例、原音色/GUI/0E/0F 回归。检查覆盖每包独立时间、批量 ACK、参数拒绝不提前起音、松键与 PANIC、被替换预加载不复活、发送恢复不越过松键、诊断取消与故障清音。[完整日志](evidence/python_host_latency_20260908.log)、[输入与证据哈希](evidence/verification_inputs_host_latency_20260908.json)。

同一 COM26、115200 baud 的实物测试仅发送 PING；没有测试音或新参数，串口会话均关闭。原同步 RTT 的 QPC 中位数约 17 ms；D2XX 设置并回读 1 ms 无稳定改善。Windows VCP 注册表仍为 16，用户 `-Apply` 因窗口未提升权限而未修改。GUI 修正使用普通 VCP，不依赖管理员更改。

| 路径与测量端点 | 成功 ACK | 中位数 | P95 | 最大值 |
| --- | ---: | ---: | ---: | ---: |
| 生产异步传输 API，4 ms 计划 PING 事件→写串口 | 1000/1000 | 0.721 ms | 1.446 ms | 1.683 ms |
| 生产 GUI worker，合成 PING 提交→写串口 | 200/200 | 0.526 ms | 1.152 ms | 1.639 ms |

完整包按至少 1.5 ms 节奏发送，另有 1024/1024 PING 压力试验；单次合并多包 write 曾出现缺 ACK，因此没有采用该方法。真实 115200 RTL 临时仿真连续 8/12/64 包通过；包内额外 400 μs 停顿可触发原解析超时并复现丢一个包。实物方向和桥固件聚合机制尚未完全定位。本轮没有改生产 RTL、ACK 帧或 RX 超时。

位流文件仍为 `4e4981fc864ed9a195f6fd7670c15b7933e84c72a284c7bee9161729079ab376`，没有重新构建或下载。下面 21:14 节的 HDL、STA 与资源是该次构建证据。本轮 PING/GUI 截图不能证明板上具体位流哈希；数字或模拟端到端 ≤10 ms 尚未验证，不能用上述主机排队数字代替。使用与原始逐笔数据见[主机延迟说明](host_latency.md)。

## 32声部独立起音延迟检测（2026-09-08 21:14，历史构建）

该历史构建生成于21:14:16，固定备份[voice_onset_20260908.fs](../build/voice_onset_20260908.fs)，SHA-256为`4e4981fc864ed9a195f6fd7670c15b7933e84c72a284c7bee9161729079ab376`。**本版尚未下载或进行实际耳机延迟测量；本轮工具没有访问COM口。**

新增`0F VOICE_ONSET_STATUS`，为32槽各自保留最新NOTE_ON记录。计数起点为FPGA帧边界提交，两个端点为目标声部首次有效PCM贡献、首个目标贡献DAC双槽帧发送完成。其他声部/参数不覆盖记录，完成后松键或PANIC仍保留；只有同槽下一次NOTE_ON替换。已生成样本在途时松键仍等待DAC完成；首次贡献前松键则标记测量取消。重触发、功放静音、过期和观测器溢出有独立标志，缺失值不冒充零。规则及32字节布局见[声部起音说明](voice_onset.md)。

- **35项HDL全量通过**，[摘要](evidence/hdl_summary_voice_onset_20260908.txt)、[完整日志](evidence/hdl_voice_onset_20260908.log)。32声部数值参考、UART、DAC、DDR/1080p与HOLD回归均保留；旧未知opcode测试移到仍未分配的`10`，`0F`已用于新诊断。
- 独立监测器测试含60次原子查询，覆盖32槽、初始化期查询、参数推进、重触发、同拍样本/释放优先级、取消/完成/过期保持、24位revision和32位时间回绕、零周期有效端点。48个1024周期帧中每次样本/DAC均使用全32位掩码，DAC事件与下一命令只隔16周期；所有记录正确且无溢出。人为高频事件突发会显式置溢出位并禁止后续伪完成。该用例最长查询等待592周期，等待不计入检测时长。[监测器日志](evidence/hdl_voice_onset_monitor_20260908.log)。
- 真实32声部引擎→PT8211→观测器集成，从`hp_bck/hp_ws/hp_din`独立解码148个立体声PCM帧，零欠载。快速Attack脉冲音色的空闲slot31：提交→PCM为2274周期/**45.48µs**，提交→DAC末位为4079周期/**81.58µs**；活动声部重触发分别为1250周期/**25.00µs**和3055周期/**61.10µs**。旧在途帧2031周期的末位被排除。以上是指定音色的RTL仿真数字时间，不是PC键盘到耳机的实测，也不代表所有音色。测试同时检查启动功放静音、读0后同槽重触发仍保持余下31字节原子、松键后完成记录保留和其他静音槽独立取消。[独立引脚解码日志](evidence/hdl_voice_onset_integration_20260908.log)。
- 查询握手单测分别用7周期和1400周期RAM响应，验证等待超过合成一帧也不暂停音频，检查非法输入、快照voice绑定、ACK背压与旧0E快照隔离。[协议日志](evidence/hdl_voice_onset_protocol_20260908.log)。
- **139项Python/Tk测试通过**，compileall通过。涵盖32字节读取、None/有效零值、断线/旧固件/离线、切换声部取消半快照、演奏命令逐字节抢占、32行缓存与旧0E主机代次关联。910×900实际Tk窗口用模拟数据生成并目视核对无底部裁剪；[界面预览](images/voice_onset_gui_preview.png)明确标记模拟数据，未访问串口。[主机日志](evidence/python_voice_onset_20260908.log)、[验证源码/日志哈希](evidence/verification_inputs_voice_onset_20260908.json)。
- Gowin最终**setup=0、hold=0**，详细最小slack **+0.083ns**，最小脉宽slack **+1.325ns**；114个复位端点、11个PLL_INIT端点审核通过，PLL控制最坏9.245ns/10ns。46个工程输入在构建前后SHA-256一致。[构建证据](evidence/build_evidence_voice_onset_20260908.json)、[输入快照](evidence/build_inputs_voice_onset_20260908.json)、[日志](evidence/build_voice_onset_20260908.log)。8条工具告警中7条为既有告警；新增1条为4深FIFO指针增量的宽度截断，指针3显式回0，合法0…3范围不会丢有效位，已核对队列回绕和满队列行为。

| 整个工程资源 | 原全链路版 | 加入逐声部起音后 | 增量 |
| --- | ---: | ---: | ---: |
| Logic | 11357 | 13361 | +2004 |
| 普通FF | 11792 | 12669 | +877 |
| BSRAM | 73 | 75 | +2 |
| DSP | 4.5 | 4.5 | 0 |

新观测模块本体为988 LUT、252 ALU、664 FF、65个RAM16SDP4事件FIFO和2块16位SDPB。256×32记录在综合网表是一个32位SDPB宏，布线时拆成2块BSRAM；时间差/revision差共用运算链，无32套计时算术或额外DSP。[资源证据](evidence/resources_voice_onset_20260908.json)。合成器仍每1024周期计算一帧，32声部计算226周期。

上板：将上述哈希文件下载到SRAM并按S3，重新连接GUI，打开“延迟检测”的“声部起音”页并选择正在使用的槽。分别检查普通按键后松键、尾音重触发、零力度取消以及不同声部交替演奏。32行是各槽最近查询缓存，只有当前选择槽低频更新；可用`python tools/instrument_cli.py --port COM26 voice-onset 0 --json`单独查询。记录端点为数字串行完成，不能代替模拟耳机测量。

## 音频链路延迟检测（2026-09-08 20:19，历史构建）

本节历史位流[latency_20260908.fs](../build/latency_20260908.fs)，SHA-256：`477a1cd093f41646d729b9ad9f84de1b52fcbca469c65ca3a8be575a0debdfed`。**本版尚未下载或进行实际键盘/串口/耳机延迟测量。** GUI本地计时和FPGA计数需在下载后演奏时读取，不能把以下仿真结果当作PC到耳机的实测延迟。

新增64字节`0E LATENCY_STATUS`原子快照，使用同一50MHz时间基准记录UART起点/CRC、合法命令提交、首个新状态样本、NOTE_ON目标声部经PCM16量化后的首次非零贡献、相应PT8211双槽末位及ACK就绪/完整结束。只观察事件，不修改数值或调度。GUI有独立延迟窗口，显示主机排队/往返/总时间，只有同连接同事务匹配时才给数字输出单程区间。64字节查询逐事务让出演奏命令，旧位流明确提示不支持；说明、字段和测量边界见[latency.md](latency.md)。

- **32项HDL测试通过**：31项整套回归加新的真实UART→32声部→DAC→监视器→串口快照集成。原有1061帧共享/并行逐位比对、32声部满载、尾音平滑、DDR/HDMI和HOLD检查继续通过。[摘要](evidence/hdl_summary_latency_20260908.txt)、[整套日志](evidence/hdl_latency_20260908.log)。
- UART埋点独立检查重复A5、假start、帧错、CRC/超时恢复、接收背压、上一ACK末字节尚未结束时下一回复到达和计数回绕。[UART时间测试](evidence/hdl_uart_latency_20260908.log)。
- 音频标签检查提交当帧旧状态、下一帧新revision、NOTE_ON零包络阶段、slot31、PCM16的32767/32768阈值、同拍DAC消费、有效零样本、欠载不冒用旧标签和最后左槽BCK上升沿。[音频标签测试](evidence/hdl_audio_latency_tags_20260908.log)。
- 监视器检查各阶段差值、零周期有效标志、首事件不被覆盖、模2^32回绕、2^31周期后过期、目标声部隔离、查询不重置记录及未完成记录覆盖计数。[监视器测试](evidence/hdl_audio_latency_monitor_20260908.log)。
- 端到端用例从实际`hp_bck/hp_ws/hp_din`独立解码826个PCM帧，零欠载。目标slot31首非零立体声末位距提交**4079周期/81.58µs**，与0E返回计数逐字一致；首新状态样本1250周期，首次非零贡献样本2274周期，计算226周期，音频周期1024。64字节快照读0之后发送PANIC，后续1…63仍保持旧快照；非法参数、坏CRC和诊断不覆盖声音记录。**UART使用16周期/bit加速仿真**，收包及请求总时间不代表115200baud板测；音频保持真实50MHz/1024周期节拍。[独立引脚解码日志](evidence/hdl_uart_audio_latency_20260908.log)。
- **121项Python/Tk全量测试通过**，compileall通过。覆盖实际写串口时间戳、提交起点/批处理/合并/优先级、64字节schema及阶段有效位、查询逐字节让路、旧位流/模拟拒绝、单程区间与连接/序号回绕代次匹配。完整延迟窗口Tk实测自然需求575×784，窗口910×830，无裁剪。[Python/Tk日志](evidence/python_latency_20260908.log)。验证源码/日志哈希见[验证输入](evidence/verification_inputs_latency_20260908.json)。
- 最终Gowin构建**setup=0、hold=0**，最小报告slack **+0.138ns**，最小脉宽slack **+1.359ns**；114个复位端点和11个PLL_INIT控制端点审核通过，PLL控制最坏7.582ns/10ns。保留7条既有工具告警。[构建证据](evidence/build_evidence_latency_20260908.json)、[日志](evidence/build_latency_20260908.log)。全部工程输入在综合前后哈希一致，[输入快照](evidence/build_inputs_latency_20260908.json)。

| 整个工程资源 | 加入检测前 | 加入检测后 |
| --- | ---: | ---: |
| Logic | 10142 | 11357 |
| 普通FF | 10211 | 11792 |
| BSRAM | 73 | 73 |
| DSP | 4.5 | 4.5 |

上板流程：下载本版到SRAM、按S3、重新连接GUI，打开“延迟检测”，按键并保持片刻。应看到计算226拍/4.52µs、音频周期1024拍/20.48µs及与实际演奏关联的阶段；分别检查NOTE_ON/OFF、slot31、PANIC和连续按键让路。新状态样本可能为零，独立声部贡献也可能在混音中相消。终点是数字双槽传输，不包含DAC/功放/耳机或声学延迟。

## 32声部分时复用（2026-09-08 18:33，历史构建）

本节历史位流为[tdm32_20260908.fs](../build/tdm32_20260908.fs)，SHA-256：`0f787ca29ef77c21e9cb501ab68944b4f5a3a3fdbebfd5b05a57d6bcad03b918`。此版已完成综合、布线和仿真，**尚未下载到开发板，也未进行32复音耳机实测**。下方15:06稳定HDMI及17:36换音修复记录分别属于历史版本。

32个独立声部共用振荡器/ADSR运算、一个完整32位增益乘法器和一张正弦表；262×32位状态存储在同步RAM。最终布线确认共享声部核心只有2个MULT27X36（4 DSP）、16个SDPX9B状态RAM、2个pROM正弦ROM。宽状态RAM的物理容量大于8384bit有效状态数据，当前用块RAM换取低FF占用；未声称状态存储只有一块BSRAM。

| 整个工程资源 | 旧4声部并行版 | 新32声部共享版 |
| --- | ---: | ---: |
| Logic | 12898 | 10142 |
| 普通FF | 10929 | 10211 |
| DSP | 32.5 | 4.5 |
| BSRAM | 63 | 73 |

新版占器件DSP容量1.51%，比旧四声部整工程减少86.15%；新增声部状态占用块RAM，所以BSRAM有所增加。完整资源及网表原语归属见[资源证据](evidence/resources_tdm32_20260908.json)。混音固定除32，单音比旧版低18.06dB；这是预留32声部满幅余量的增益策略。实现说明见[tdm32.md](tdm32.md)。

- 28项HDL测试通过：27项整套回归加新增32声部DAC集成测试。共享核心1061帧与旧并行实现的混音及全部声部状态逐位一致；集成检查254次响应、276个精确226拍输出、275帧独立串行PCM解码，实际1024拍节奏下零欠载。包括首tick早于RAM初始化完成、全32满幅、跨字节声部寻址、0D原子快照、ACK背压、暖复位。原换音连续性、DDR、HDMI、匹配/HOLD回归继续通过。[总摘要](evidence/hdl_summary_tdm32_20260908.txt)、[整套日志](evidence/hdl_tdm32_20260908.log)、[32声部集成](evidence/hdl_synth_32voices_20260908.log)、[逐位比较](evidence/hdl_voice_bank_tdm_20260908.log)。
- 96项Python/Tk测试通过（81项instrument、15项video diagnostics），以及compileall。涵盖32位状态、旧固件降级、32参数组、旧预设扩展、实际Tk离线32音/释放31号/PANIC、尾音空槽优先分配及失败回滚。[日志](evidence/python_tdm32_20260908.log)。
- 最终Gowin构建setup=0、hold=0，最小报告slack **+0.138ns**、最小脉宽slack **+1.325ns**；114个复位端点与11个PLL_INIT控制端点审核通过，PLL控制最坏 **8.185ns/10ns**。保留7条既有供应商PLL截位/优化/全局布线告警，无新音源告警。[构建证据](evidence/build_evidence_tdm32_20260908.json)、[构建日志](evidence/build_tdm32_20260908.log)。
- 最终构建前后核对全部工程输入SHA-256一致，避免将综合开始后的修改混入证据。[输入快照](evidence/build_inputs_tdm32_20260908.json)。测试/日志关联哈希见[验证输入](evidence/verification_inputs_tdm32_20260908.json)。
- HDMI改为2×16个01–32声部指示及完整32位ACTIVE MASK；逐格、字形、高位CDC、随机背压和快照保持回归通过。[实际RTL预览](images/feedback_32voices.png)、[HOLD预览](images/feedback_32voices_hold.png)均为仿真夹具，不是开发板照片。

上板复核：下载上述位流到SRAM后按S3；GUI应识别32声部，新`voice-status`返回8位十六进制掩码。检查声部31（界面第32格）的起音/释放、多个声部叠加与清音、HDMI1080p60稳定和HOLD反馈；使用HEADPHONE试听。当前UART仍逐条提交NOTE_ON，不支持32音同一帧原子起音。

## 同声部换音爆音修复（17:36，历史构建）

用户报告“不同音高在同一个声部切换时会有爆音”，要求先提交再修改，并确认操作是“松开一个琴键后按另一个琴键”。已先完成提交 **`4cc4f6c`**（`feat: checkpoint instrument GUI and stable DDR waveform display`），提交后才新增回归和修改合成器。本轮修改尚未另行提交。

GUI松键后释放主机槽，FPGA声部仍可能处于RELEASE尾音；下一颗键复用该槽并发送NOTE_ON。旧RTL无条件清零相位和包络，导致正在发声的样本突然归零。新增 `tb_note_transition` 在提交基线上复现失败：换音点混音样本从 **363199008 跳到 0**，超过测试的相邻样本变化上界134217728。保留 [修复前失败日志](evidence/hdl_note_transition_before_fix_20260908.log) 和 [样本](evidence/note_transition_before_samples_20260908.txt)。此记录来自真实RTL整数样本，不是耳机录音。

修复只改 `synth_voice` 的活动声部重触发：包络非零时延续DDS相位正常推进，保持当前电平，更新音高并从当前电平重新ATTACK；不再截断尾音。仅本次重触发的A/D有效步长最多为 `0x01000000`（每样本满量程1/128），零步长也使用该值，满量程变化约2.62144ms；正常较慢包络仍按配置运行，到SUSTAIN时结束保护。未发声时仍从零相位/零包络开始，NOTE_OFF可打断重触发，PITCH维持连续相位，PANIC继续立即清音，5周期混音延迟及协议格式不变。详见 [串口数值规则](uart_protocol.md)。

- 新回归通过 **18次释放尾音复用、3621个实际混音样本**，覆盖不同松键间隔、反复换音、正负相位、零时间A/D、连续PITCH、脉冲相位/电平保持、其他声部独立、重触发中松键、静音起音、PANIC和复位。检查区间相邻样本最大变化 **62496151**，低于134217728上界；此量包含正常振荡器的采样变化，不能当作爆音分贝测量。脉冲本身有固有跳沿，独立检查其换音相位/包络连续性。见 [通过日志](evidence/hdl_note_transition_20260908.log)、[修复后样本](evidence/note_transition_after_samples_20260908.txt) 和 [源码/日志哈希](evidence/hdl_note_transition_inputs_20260908.json)。
- 完整 **26项HDL回归通过**，包括四声部独立正弦模型、UART→PT8211串行PCM、和弦整段匹配/HOLD、换音重捕获、DDR/HDMI；见 [回归摘要](evidence/hdl_summary_note_transition_20260908.txt)。主机GUI命令路径无需修改。
- Gowin综合/布局布线及检查通过，**setup=0、hold=0**，最小报告slack **+0.016ns**（既有像素复位至TMDS路径），最小脉宽slack **+1.325ns**。114个复位端点、11个PLL_INIT控制端点审核通过，PLL控制最坏9.398ns/10ns。Logic **12898**、寄存器 **10929**、锁存器 **0**、BSRAM **63**、DSP **32.5**，保留既有7条工具告警。见 [构建证据](evidence/build_evidence_note_transition_20260908.json) 和 [日志](evidence/build_note_transition_20260908.log)。

本节历史位流生成于 **2026-09-08 17:36:54（UTC+08:00）**，另存 `build/note_transition_20260908.fs`，两份SHA-256一致：**`2e22e6f0e471543c2a10ce6b83e862e3fbd3af02c4fc87ac83ede105f21a00d1`**。修改前17:08位流保存在 `build/pre_note_transition_20260908.fs`。

**本版尚未下载或耳机实测。** 下载后按S3，以原先的音色/释放时间交替松开和按下不同琴键，复查尾音被同一声部复用时的听感，并核对和弦/HOLD显示。此修复不改变实时力度/音色/sustain突变、零时间首次起音/释放和PANIC的行为；它们尚无通用去爆音处理。

## 和弦整段匹配 / HOLD（17:08，历史构建）

用户明确确认已下载16:20版 `3f23e665…`，不同音高和弦仍抖动，随后选择“整段匹配时更新，未匹配时保持并显示 HOLD；换音后重新捕获”。单个DDS周期只能锁住参考声部，不能约束所有其他音的相对相位。真实合成器的持续 C4/E4/G4/C5 仿真记录了45000个混音样本和55个旧DDS触发快照，相邻帧RMS像素变化均值50.562、最大138.949；软件窗口对齐但不拒绝失配仍有明显变化。此历史实验是仿真，源码哈希随 [基线量化记录](evidence/wave_stability_dds_baseline_20260908.json) 保存，不能当作本版匹配器或板测结果。

本版采集1024点，比较全部513个512点窗口的全部样本，以显示高度的平均绝对差≤4像素作为接受条件。最佳窗口的原始Q1.31数据逐字复制；失配时512点显示RAM全部保留，画面显示 **HOLD / WAITING FOR MATCH**。声音命令版本随真实混音样本传递，换音、松键、变调、力度、音色、ADSR参数或PANIC后重新捕获；未完成旧块取消，已发布银行保持不可变。PING/诊断不重捕获，完整全零块自动显示平线。峰值/声部/状态随最新1024点块刷新，HOLD时其时间与保留曲线不同。接口和更新率见 [反馈说明](feedback_notes.md)。

本节历史位流于 **2026-09-08 17:08** 构建完成，保存在 `build/pattern_trigger_20260908.fs`，SHA-256：**`bbb954c5437284d4e39a2466fcb2e7a51a9580f06b6e76cabb8da58664851989`**。16:20旧位流另存 `build/pre_pattern_trigger_20260908.fs`。

- 完整 **25项HDL回归通过**，见 [回归摘要](evidence/hdl_summary_pattern_trigger_20260908.txt)。真实合成器→1024点capture→匹配器→renderer联合用例完成7帧，其中1个HOLD帧逐字不变，6个新模板来自对应声音版本的连续真实混音窗口。测试使用真实的每1024源时钟一次采样节奏；光栅缩为128×800以限制运行时间。此用例的6个接受帧均为首帧或版本重捕获，不把日志中的同版本误差0误读为持续和弦每帧都能匹配。
- 独立匹配用例覆盖偏移184的最佳窗口、原始低位保持、4像素接受/5像素拒绝、稀疏点之外的误差、HOLD不可变、换音、全零、正负满幅及小于530000周期的搜索上界。真实多声部参考用例通过9012个样本、9个快照、5次参考切换，84次混音过零全部被忽略。详见 [匹配日志](evidence/hdl_wave_align_pattern_trigger_20260908.log)、[联合显示日志](evidence/hdl_stable_display_pattern_trigger_20260908.log) 和 [输入/日志哈希](evidence/hdl_pattern_trigger_inputs_20260908.json)。
- 完整1920×1080 RTL预览先渲染真实测试曲线，再输入无关的+0.5常量块；确认HOLD、最新PEAK=`40000000`及1,036,800个完整双像素beat。已目视检查 [HOLD预览](images/feedback_dashboard_hold.png)，该图为仿真测试夹具，不是板测照片。
- Gowin综合/布局布线和构建检查通过，**setup=0、hold=0**，全设计详细最小slack **+0.001 ns**（既有DDR欠载解码至帧元数据路径，余量较小），最小脉宽slack **+1.325 ns**；新增匹配相关报告路径最小setup余量 **+1.306 ns**。114个复位端点和11个PLL_INIT控制端点审计通过，PLL控制最坏传播9.497ns/10ns。Logic **12303**、寄存器 **10925**、锁存器 **0**、BSRAM **63**、DSP **32.5**，保留既有7条工具告警。见 [构建证据](evidence/build_evidence_pattern_trigger_20260908.json) 和 [日志](evidence/build_pattern_trigger_20260908.log)。

HDMI光栅保持60Hz；1024点采集需20.97152ms，持续新画面上限约47.7帧/s，实际受触发、匹配及DDR交接影响。HOLD可以持续较长时间，但峰值/状态和帧计数继续更新。历史15:06版约60个新画面/s实测不能迁移到本版。

**本版没有下载或板测，尚不能确认实际屏幕问题已解决。** 本轮COM26只读查询被拒绝访问，未取得新板测数据。下载上述哈希文件后按S3，保持原先容易抖动的和弦，核对失配时曲线不动并显示HOLD、换音后出现新曲线、清音后回平线，同时检查峰值/声部、FRAME推进和UNDERRUNS。旧版板测与本版仿真分别保留。

## 和弦相位参考修复（16:20，已下载仍抖动，历史版本）

用户进一步确认问题发生在**不同音高的和弦**。15:47版按混音过零触发，和弦的多个上升过零点会令窗口跳到不同参考相位。现从真实合成声部只读取得DDS相位，选择最低音且包络/力度非零的声部作为参考；在原始波形采样时锁存选择，下一拍比较周期回绕，标记总延迟保持5个系统周期，与实际混音输出对齐。参考经top/HDMI/renderer送入capture，有有效参考时不使用混音过零；显示仍是连续512个原始混音样本。变调、静音、释放和重新发音会自动更新参考，不改变任何发声相位或音频时序。

本节历史位流于 **2026-09-08 16:20:42（UTC+08:00）** 完成构建，保存在 `build/polyphonic_trigger_20260908.fs`。SHA-256：**`3f23e6650a580edd7b1b923e0272b87710589f07978314b1e5d8986ef6449d09`**。Gowin完整构建和检查通过，setup=0、hold=0；全设计详细最小slack **+0.054 ns**（既有DDR欠载诊断路径），最小脉宽slack **+1.325 ns**。新增触发路径经两级选择/比较流水后最小报告setup余量 **+0.469 ns**。114个复位端点及11个PLL_INIT控制端点审计通过，PLL控制最坏传播7.951 ns，预算10 ns。资源为Logic **12125**、寄存器 **10544**、锁存器 **0**、BSRAM **61**、DSP **32.5**，保留既有7条工具告警。详见 [构建证据](evidence/build_evidence_polyphonic_trigger_20260908.json) 和 [构建日志](evidence/build_polyphonic_trigger_20260908.log)。

完整 **23项HDL回归通过**。新增真实四声部→异步capture联合测试检查 **9012个样本、10个512点快照、5次参考切换**；84次混音过零均不会误作DDS周期起点。测试覆盖错开发音的C4/E4/G4/C5、变调、正弦/三角/脉冲叠加、静音、释放、重触发、PANIC和复位。原有独立正弦混音参考、UART到PT8211及背压测试继续通过；renderer新增检查确保外部参考连接生效。完整1080p RTL预览成功生成。

同一和弦用例使用 `vvp build/sim/tb_feedback_polyphonic.vvp +LEGACY` 恢复混音过零触发，首个快照即失败：`chord snapshot 0 jumped away from its reference phase`。保留 [完整回归摘要](evidence/hdl_summary_polyphonic_trigger_20260908.txt)、[和弦测试日志](evidence/hdl_polyphonic_trigger_20260908.log)、[renderer日志](evidence/hdl_polyphonic_renderer_20260908.log) 与 [输入和日志哈希](evidence/hdl_polyphonic_trigger_inputs_20260908.json)。

该版本交付时未下载，**随后用户明确确认已下载16:20版，和弦显示问题依旧**。最低音参考没有满足用户对稳定曲线的要求；当前改为用户选择的整段匹配/HOLD，见上方最新记录。本节23项测试及构建数据仅适用于此历史版本。

## 波形过零触发修复（15:47，历史版本）

用户反馈波形未锁相、显示抖动。根因是 `feedback_capture` 自由运行截取512点，窗口起点随显示缓冲释放而变化。现改为负阈值武装后的上升过零触发，触发点作为第0点并原样保存后续511点；加入静音快速刷新和8192个有效样本的自动触发超时。忙碌期间发生的过零会被消费，缓冲恢复后等待新边沿。采样、合成和HDMI时钟不变，双bank所有权和无音频背压接口不变。采样精度、多声部及低音更新率边界见 [反馈说明](feedback_notes.md)。

过零触发修复位流生成于 **2026-09-08 15:47:08（UTC+08:00）**，保存在 `build/wave_trigger_20260908.fs`。SHA-256：**`3dee6506fe4807370f8caece39b5c9308c797a3a0fb50a2382ca16c5ad87a33b`**。构建前位流保存在 `build/pre_wave_trigger_20260908.fs`。该轮交付时未执行下载；后续用户反馈不同音高和弦仍抖动，上方记录了进一步修复。15:06版的既有板测结果不能迁移为本轮触发修复的验收结果。

- 新增 `tb_feedback_trigger` 在旧RTL上复现“尚未发生上升触发便发布快照”的失败；修复后18帧非整数周期正弦/三角/脉冲逐点比对通过，并覆盖滞回、无效输入、静音/直流、超时边界、缓冲忙碌和复位。
- 完整 **22项HDL回归通过**；完整1080p渲染预览通过并目视检查。保留 [回归摘要](evidence/hdl_summary_wave_trigger_20260908.txt)、[触发测试日志](evidence/hdl_wave_trigger_20260908.log)、[渲染测试日志](evidence/hdl_wave_trigger_renderer_20260908.log) 和 [测试输入哈希](evidence/hdl_wave_trigger_inputs_20260908.json)。
- Gowin完整综合/布局布线和构建检查通过：setup=0、hold=0，详细最小slack **+0.138 ns**，最小脉宽slack **+1.325 ns**。114个复位端点和11个PLL_INIT控制端点审计通过；后者最坏传播8.265 ns，预算10 ns。保留既有7条工具告警，触发逻辑没有新增告警。
- 资源：Logic **11940**、寄存器 **10464**、锁存器 **0**、BSRAM **61**。完整 [构建证据](evidence/build_evidence_wave_trigger_20260908.json) 和 [构建日志](evidence/build_wave_trigger_20260908.log) 已归档。

下载本节位流后，以单声部持续正弦/三角/脉冲观察起点是否保持上升沿；变调后应重新对齐，清音后回到平线，并检查DDR欠载及帧推进。该显示触发没有亚采样插值，仍有一个采样间隔（约两水平像素）的量化位移，多声部拍频和包络变化会真实改变波形。

## DDR/1080p 本轮状态（15:06版板测基线）

| 项目 | 本轮范围与当前结果 |
|---|---|
| DDR 平台 | 核心板32-bit / 1GiB DDR3，C版IP、400MHz CK、100MHz用户口已接入 |
| 启动自检 | 前8MiB两遍地址模式/反码写读逻辑；`tb_ddr3_bist` 独立测试通过，不覆盖整个1GiB |
| 反馈 | capture/dashboard/renderer三项独立RTL测试通过；完整1920×1080逐像素预览已生成、目视检查 |
| 视频时钟/时序 | 148.5/742.5MHz精确标称方案、LOCK过滤、完整2200×1125光栅独立测试通过 |
| 帧缓存集成 | RGB565、末笔写握手、双行标签、晚请求恢复与背压联合测试通过；故障后256帧epoch回绕全黑及复位恢复通过 |
| 完整回归 | DDR基础20项HDL通过；诊断增量4项相关HDL及完整77项Python/Tk通过；新增DDR失锁完整重校准保护测试，含亚周期脉冲/校准边界；TMDS检查全部字节、5632随机字和流水中复位 |
| 1080p吞吐模型 | 真100/148.5MHz、2200×1125光栅，连续3帧6220800像素正确、零欠载；含刷新/命令阻塞，最慢后台帧14.273910ms，余量2.392757ms |
| Gowin / STA | PLL初始化版2026-09-08 15:06:19，V1.9.12.03、C2/I1；setup=0、hold=0，详细最小 slack +0.138 ns、最小脉宽 slack +1.325 ns；114个复位端点独立审计通过 |
| 板测 | 15:06修复版下载并按S3后，用户确认稳定画面；12次诊断均DDR=0xCB、像素约148.5MHz、扫描/渲染约60帧/s、欠载0 |

预览：[1080p RTL 仿真图](images/feedback_1080p.png)。该图使用合成测试向量及DDR诊断夹具，不能作为板测照片。复现 `python3 scripts/render_feedback_preview.py`；专属测试为 `tb_feedback_capture`、`tb_feedback_dashboard`、`tb_feedback_renderer`、`tb_ddr3_bist`、`tb_ddr_framebuffer`、`tb_video_timing_1080p`、`tb_video_clock_1080p`。

Icarus回归排除加密DDR PHY，由用户口内存模型检查请求、反压、数据和错误路径；模拟PHY校准与PCB电气只能在Gowin模型/工具适用范围及真实硬件中核查。60Hz扫描时序、每秒60个新完成帧、DDR自检通过是三个不同的验证结论。

本轮可复现记录：[20项HDL摘要](evidence/hdl_summary_ddr_1080p_20260908.txt)、[HDL输出及吞吐假设](evidence/hdl_ddr_1080p_20260908.log)、[62项Python/Tk日志](evidence/python_ddr_tests_20260908.log)。吞吐测试使用有序用户口模型，每4周期阻塞1次命令、写另每8周期阻塞1次、每780周期暂停26周期刷新，返回资格延迟12–15周期。该结果不是DDR PHY或板级带宽实测。

2026-09-08 13:36（UTC+08:00）完整 `unittest discover` 通过62项：共享后端19项、CLI 12项、GUI/预设/主机分槽31项。新增4项回归覆盖 `memory-status`（0x0B）的 ACK 语义：结构化事件不再把 DDR flags 当作 `active_mask`，该字段为 `None`；`memory_flags` 仅在真实、成功的查询回复中有效。GUI 保留已确认声部状态，后续普通 ACK 仍能正常更新和清零；拒绝回复与离线模拟不会伪造 DDR 状态。这些主机测试使用假串口及离线 worker，不访问开发板。

上板按 [DDR显示说明](ddr_display.md) 和 [硬件清单](hardware.md#8-必须通过实物验证的项目) 记录新位流哈希、校准/BIST状态、屏幕识别、欠载/帧推进和复位恢复。音频/串口独立于DDR的复位与访存，显示初始化不应影响主演奏链路。

### 官方PLL初始化修复版（已稳定显示）

根据14:49诊断版平均频率及帧推进正常、显示器反复失锁的实测，视频两级PLL接入当前官方初始化helper。保留24.75/15倍率、1080p光栅、ELVDS与四路OSER10，两个helper使用50MHz初始化时钟。新构建15:06:19已通过原有完整检查：setup=0、hold=0、最小slack +0.138ns、114个复位端点预算通过；独立审核也已通过：11个动态控制端点、两个helper共79个50MHz寄存器；最坏完整传播8.069ns（含输入缓冲、源时钟布线、C2Q、组合逻辑和端口布线），低于10ns预算。该检查约束20ns状态窗内的数字传播，不模拟PLL抖动或模拟锁定过程。

新增 [初始化顺序测试](evidence/video_pll_init_sequence_20260908.log) / [源码及模型哈希](evidence/video_pll_init_sequence_20260908.json) 通过4个启动/失锁/复位场景、24/24.75表等价与绕过初始化的负例；真实PLL/CLKDIV在该测试中为静止stub，只验证控制顺序。原有 `tb_video_clock_1080p` 和 [9场景TMDS原语测试](evidence/tmds_pll_init_20260908.log) 再次通过。新增4条EX3791来自官方helper的有限位宽计数回绕，另保留字体ROM两条NL0002和50MHz普通布线PR1014，详见第三方说明。

当前下载候选 `impl/pnr/Prj1.fs` 的SHA-256为 **`2ba120fe5d3d636859eb8ba593d7eea28b2a7e34aeb4c1c3ce0d69a62594d58d`**，构建时间 **15:06:19**，详见 [PLL初始化构建证据](evidence/build_evidence_video_pll_init_20260908.json)。[独立审核自测](evidence/video_pll_init_audit_selftest_20260908.json) 中6个负例均被拒绝：动态ICP被关闭、错误ROM位来源、设置线延迟超限、RESET组合单元延迟超限、helper时钟改变、动态设置被替换成常量。构建检查器已强制调用此审核；用户已确认下载并按S3后稳定显示项目画面。随后12次完整视频快照均HPD=1、窗口有效、两域复位释放，DDR flags=0xCB，欠载0。像素块数1450/1451，符合148.5MHz量化范围；首末间隔8.625000s、扫描和渲染各推进517帧，均约59.942帧/s。原始ACK和采集边界见 [PLL初始化版板测](evidence/com26_video_pll_init_20260908.json)。用户进一步确认显示器菜单可以打开，信息页为1920×1080/60Hz；GUI正弦演奏时波形、峰值和声部指示随输入变化，松键后回落。此结果支持当前板/线/显示器组合下的短时稳定运行；不等于全1GiB或长期压力、信号眼图、模拟音频质量验收。

### 视频运行诊断版（已下载，接收器反复失锁）

新增 `video_runtime_diagnostics` 与 `0x0C` 串口快照命令，读取HPD、像素时钟每10ms的1024周期块数、vblank帧数、完成渲染帧数及欠载计数。只有index0在采样边界锁存整组128位，后续字节读取相同快照；诊断不改变声部或清除计数。CLI为 `python tools/instrument_cli.py --port COM26 video-status`，完整布局见 [串口协议](uart_protocol.md)。

本次相关 [4项HDL测试](evidence/hdl_video_diagnostics_20260908.log) 覆盖合成器快照/非法参数/背压/相位连续、UART实际字节CRC及诊断回复、四声部正弦参考、诊断Gray跨域/停钟/计数进位/复位与短失锁恢复；[完整77项Python/Tk测试](evidence/python_video_diagnostics_20260908.log) 通过，包含新增15项诊断解码与传输测试。此前DDR/TMDS完整回归证据仍单独保留。

首次诊断构建发现64个像素计数复位恢复违例，最小slack -6.712ns，已被检查器拒绝，未下载。原因是全局50MHz复位与已有像素域复位重新组合；模块已改为直接使用调用方包含全局复位的像素/UI域同步释放复位，测试也使用真实域复位管线。没有给计数器CLEAR添加时序例外。修复后已重构建通过。

视频运行诊断版（备份 `build/video_diagnostics_20260908.fs`）的SHA-256为 **`7fbf05f48b6822b843bc47291cb61ae4c024b495a4de495bd9b02a6509438ef9`**，完成时间 **2026-09-08 14:49:32（UTC+08:00）**。完整构建检查通过：setup=0、hold=0，详细最小slack **+0.153ns**，最小脉宽余量 **+1.325ns**；114个初始化复位端点审计通过，四组新增Gray跨域最大延迟约束均有实际报告路径。资源为Logic **11554**（9175 LUT、2379 ALU）、寄存器 **10370**、BSRAM **61**、DSP **32.5**、PLL **3**、OSER10 **4**。保留两条字体ROM优化NL0002和一条50MHz普通布线PR1014告警。证据见 [诊断版构建记录](evidence/build_evidence_video_diagnostics_20260908.json)。

用户确认下载软件成功；首次PING/0B/0C均未收到字节，见 [无回复记录](evidence/com26_video_diagnostics_no_reply_20260908.json)。按S3后串口恢复，启动无回复的根因尚未确定。此后12次完整快照均为HPD=1、视频就绪及两个像素复位释放、串化器不在复位、窗口有效；DDR flags均0xCB、欠载0。10ms块数1450或1451，测得148.4800或148.5824MHz，符合148.5MHz及±0.1024MHz量化。首末间隔8.610000s，vblank与rendered均增加517帧，约60.046帧/s，原始16字节快照、每个ACK及时间见 [诊断版板测](evidence/com26_video_diagnostics_20260908.json)。

用户最初描述复位后有信号但黑画面，随后明确指示灯不断从有信号跳到无信号、显示器无法进入菜单，因此登记为**接收器反复失锁**。显示器、线材和接口与旧640×480成功显示时相同。上述数据支持FPGA内扫描/DDR渲染持续推进，不能证明显示器稳定接收，也不能测量PLL抖动或TMDS眼图。下一步采用当前官方PLL_INIT做单变量对照，见 [HDMI无信号调查](hdmi_no_signal_investigation.md)。

### HDMI 转发时钟修复版（上板仍无信号）

时钟修复版（备份 `build/hdmi_clock_fix_20260908.fs`）的 SHA-256 为 **`7fc6c77eeb5a5e410b9f45dccf747f387a4bab7b552289f634536171f5842b46`**，Gowin 报告生成时间 **2026-09-08 14:20:38（UTC+08:00）**。时钟通道新增第四个 OSER10，按同板官方 `cam_dvi` 的方式发送 `1111100000`；三路数据和时钟共用 FCLK/PCLK/RESET，ELVDS 输出保持对应差分球位。

完整布局布线和检查器通过，setup/hold违例均为零，最小报告余量 **+0.138 ns**、最小脉宽余量 **+1.325 ns**。114个复位端点的最坏分发加恢复时间为 **8.441 ns**，低于40ns预算。资源为 Logic **11011**（8702 LUT、2309 ALU）、寄存器 **9603**、锁存器 **0**、BSRAM **61**、DSP **32.5**、PLL **3**、OSER10 **4**；仍保留两条字体ROM优化NL0002和一条50MHz输入普通布线PR1014告警。证据见 [修复版构建记录](evidence/build_evidence_hdmi_clock_fix_20260908.json)。

修复后 [20项HDL回归](evidence/hdl_hdmi_clock_fix_20260908.log) 通过，另用本机 Gowin 官方 CLKDIV、OSER10 和 ELVDS_OBUF 模型运行真实 `dvi_tx_top`。新增 [原语测试日志](evidence/tmds_clock_primitive_20260908.log) 和 [模型/源码哈希](evidence/tmds_clock_primitive_20260908.json) 覆盖3个PCLK传输延迟×初启/失锁/外部复位，共9场景、3240个三色数据字：在同一转发时钟下降沿按固定流水延迟解码，核对独立TMDS参考、四种蓝通道同步控制及红绿00控制，没有逐通道搜索相位。测试确认原始 `/5` 高6UI低4UI，修复输出高低各5UI、周期10UI。恢复旧的直接转发时钟或整体反相时钟字，测试均会失败；时钟常量错误、绕过串化器、差分P/N反接也被网表审计拒绝。

复现新增测试：`wsl -d Ubuntu-22.04 --cd /mnt/e/workspace_cloud/Mega_138K/Dev/Prj1 -- python3 scripts/check_tmds_clock.py`。脚本通过 `--simlib` 或 `GOWIN_SIMLIB` 指定本机官方库，仅在忽略的build目录提取所需原语。这些数字模型不证明真实PLL、PCB或接收器已经正常。用户确认重新下载 **7fc6c77e…** 后显示器仍提示“无信号”。随后 COM26 连续10次查询仍为0xCB，原始ACK见 [时钟修复版板测](evidence/com26_hdmi_clock_fix_20260908.json)。该改动尚未解决接收器无法锁定；下一版增加实际像素计频、vblank/渲染帧/欠载计数和HPD读取。

### 首次 DDR 上板结果

用户确认手动下载后 HDMI 无显示，并进一步确认显示器提示“无信号”或进入待机。2026-09-08 **14:11:44–14:11:59（UTC+08:00）**，COM26 以 115200 baud 连续 30 次查询均返回 `memory_flags=0xCB`，原始带 CRC 的 ACK 和每次解码结果见 [首次 DDR 板测记录](evidence/com26_ddr_first_board_20260908.json)。对应下载候选是下节的 `e1166ee5…` 位流；下载由用户执行，没有 JTAG 读回哈希。

该结果支持 DDR PHY 校准及保留区前 **8 MiB** 两遍地址模式/反码写读自检通过。`front_valid=1` 还需要像素域至少发生一次垂直消隐请求，因此不只是 DDR 端画完第一帧。30 次查询中没有读超时或欠载标志；这仍不能证明像素时钟持续运行、准确频率、每秒60个新帧、其余DDR容量或 HDMI 接收器同步。

排查确认 HDMI 方向、使能和球位与已显示的 640×480 版本一致。发现首个1080p版本直接转发 `CLKDIV /5` 的像素时钟，官方模型的占空比为60%/40%，且转发路径没有数据通道的 OSER10 延迟。已参照同板 `cam_dvi` 完成上文的第四路串化器修复并重新构建，接收器复测仍无信号，不能把模型通过登记为已经解决。

### 首个 DDR/1080p 构建

该历史位流的 SHA-256 为 `e1166ee52eeb46cf07b2c24572340b0c37dc7a14721247ff7819c5b54d807d66`，另存于忽略的 `build/ddr_first_board_20260908.fs`。生成报告时刻为 **2026-09-08 13:45:44（UTC+08:00）**。当时的构建检查核对位流/报告/SDF/路由网表晚于全部工程输入、所有 SDC 约束激活，并要求每个最大延迟约束都有真实报告路径。当前 `impl/pnr/Prj1.fs` 已更新为上文的视频运行诊断版。

最终 [构建输入、位流/报告哈希、时序与告警证据](evidence/build_evidence_ddr_1080p_20260908.json) 和 [检查器通过日志](evidence/build_check_ddr_1080p_20260908.log) 已保存。独立 VO/SDF 审计覆盖 **113 个初始化复位端点**：3 个 OSER10、1 个像素 CLKDIV、101 个 DDR IO 原语及 8 个负沿校准寄存器；SDC 选择集合没有额外端点或遗漏。最坏复位分发加恢复时间为 **8.556 ns**，小于 40 ns 预算，距 80 ns 启钟窗口保留 71.444 ns。八位 DLL STEP 的实际源、采样使能和流水也已核对，最坏原语弧/布线/setup 合计 4.099 ns。9 个网表/SDF 故障注入及 5 个 STA 报告负例均被检查器拒绝；这些检查不代替模拟 PHY 和板上测量。

六路时钟为 50、400、100、49.5、742.5、148.5 MHz。1920×1080 有效区、2200×1125 总光栅对应标称 60 Hz；实际频率继承晶振误差。工具报告的 Fmax 不代表板上提高频率或实际显示器验收。

资源为 Logic **10965/138240**（8647 LUT、2318 ALU）、寄存器 **9603**、锁存器 **0**、BSRAM **61/340**、DSP **32.5/298**、PLL **3/12**、OSER10 **3**。保留三条告警：两条 NL0002 是两个像素路径的字体函数被吸收为同步字形 ROM，已核对路由网表的 128 字符初始化值；一条 PR1014 是板载 50 MHz 输入的普通布线段，沿用 V22 原理图脚位并保留实际时序分析。TMDS 外部电气、DDR 信号质量和耳机模拟输出仍须板测。

首次下载准备中的界面操作曾被 Esc 中止，随后用户手动下载，实测结果已登记在上方。复测当前修复版时，关闭占用 COM26 的 GUI 后运行 `python tools/instrument_cli.py --port COM26 memory-status`；正常稳态且从未欠载时预期 `memory_flags=0xCB`。同时核对显示器信息页的 1920×1080 / 60 Hz、波形/峰值随演奏变化、FRAME 持续推进和 UNDERRUNS 保持零。串口 flags 不能代替显示器识别、完整帧率或音频模拟测量。

2026-09-08 **13:52:48（UTC+08:00）** 再次读取 COM26：`memory-status` 收到有效 ACK `a5 5a 00 01 00 0b 9b 02`，sequence=0、opcode=0x0B、status=1（unknown opcode）。这说明串口仍能双向通信，但板上响应程序不支持新增 DDR 诊断命令；不能把该拒绝解释为 DDR 校准失败，也不能据此识别板上位流的准确哈希。此次只读查询未发出发声、清音或下载操作，原始证据见 [下载前 COM26 状态](evidence/com26_ddr_pre_download_20260908.json)。需要下载经过时序检查的新版后继续板测。

## GUI/正弦版本历史记录

更新日期：2026-09-08。GUI/正弦版本覆盖 Python 图形串口控制台、预设 JSON、共享串口后端和 FPGA 正弦 DDS。**10 项 HDL、52 项 Python/Tk 回归通过，Gowin 完整构建通过，setup/hold 违例均为 0。含正弦的新位流尚未下载；耳机声音、模拟质量和端到端延迟尚未验收。**

### GUI/正弦版本可复现结果

| 项目 | 环境 / 结果 |
|---|---|
| RTL 回归 | WSL Ubuntu-22.04，Icarus Verilog 11.0/vvp；**10 项通过**，含新增正弦 ROM 和四声部正弦参考测试 |
| 主机回归 | Python unittest + Tkinter；**52 项通过**，其中 GUI/预设/主机分槽 30 项，共享后端 16 项，原 CLI 6 项 |
| GUI 检查 | 实际 Tk 窗口检查完整布局；[截图](images/instrument_gui.png) 为离线正弦双声部预览，不是 FPGA 音频测量 |
| 工程清单 | `python scripts/update_project.py --check` 通过 |
| Gowin 全流程 | V1.9.12.03 x64，GW5AST-LV138PG484AC2/I1，C 版；综合、布局布线、位流生成通过 |
| GUI/正弦位流检查 | `python scripts/check_build.py` 通过；位流晚于源码，CDC 约束激活 |
| STA | setup 违例端点 **0**；hold 违例端点 **0**；详细 setup/hold/recovery/removal 报告最小 slack **0.247 ns** |
| 时钟 | 检查 50 MHz、25 MHz、125 MHz；系统域报告 Fmax **81.537 MHz**，像素域 **65.714 MHz** |
| 板上串口后端 | COM26 实测连接 PING → PANIC → connected → 关闭清音 → disconnected 通过；ACK RTT 约 15–16 ms |
| 新版板测 | **未执行新版下载**；不能将首版位流的串口 / HDMI 反馈视为GUI/正弦版本正弦音频通过 |

GUI/正弦版本 Gowin 报告生成时刻为 **2026-09-08 11:34:35**（本机 UTC+08:00）。Fmax 仅是特定路径和工具模型下的报告值，不是提高工作频率的承诺。125 MHz 串化采用专用 OSER10，工具未给出该时钟的通用寄存器路径 Fmax，不记为“无限余量”。

证据已另存，首版快照继续保留：

- [GUI/正弦版本 HDL 摘要](evidence/hdl_summary_gui_sine_20260908.txt)
- [GUI/正弦版本 52 项 Python/Tk 日志](evidence/python_gui_tests_20260908.log)
- [GUI/正弦版本构建输入、位流哈希和工具告警](evidence/build_evidence_gui_sine_20260908.json)
- [COM26 后端握手与关闭实测](evidence/com26_backend_smoke_20260908.json)

完整可再生报告位于 `build/sim/`、`build/python_gui_tests.log`、`impl/gwsynthesis/` 和 `impl/pnr/`，复现命令见 [README](../README.md)。测试日志验证相应代码行为，不替代真实串口拔插或音频测量。

### 板上已确认的事实

- 用户已确认首版 `Prj1.fs` 下载后 HDMI 显示 **“FPGA SYNTH”**。这是用户反馈，尚无热插拔、长期锁定或显示器覆盖测试。
- 本机同一 USB 桥枚举 COM25（A）和 COM26（B），VID:PID 均为 `0403:6010`。此前 COM25 `ping` 复现超时；COM26 `ping` 返回 **`seq=0 OK active=0x00`**、退出码 0，已定位为接口选择问题。
- GUI/正弦版本约 11:43 再次执行 COM26 CLI PING，返回 **`seq=0 OK active=0x01`**。这验证重构后的 CLI 与板上已有位流仍能往返通信；掩码 1 只表示当时一个 ADSR 状态非 IDLE，不能推出已测到声音。
- 随后实际使用共享后端连接 COM26：先 PING、PANIC，成功后发布连接事件；关闭时再次 PANIC 后断开。清音 ACK 的 `active_mask=0`，往返时间约 15–16 ms，见实测 JSON。此次没有发送新发声命令。
- PING/PANIC 验证请求、CRC、帧边界提交、清音状态及回复链路。不能由此推出 PT8211 时序、模拟幅度、正弦波形或端到端延迟通过。

GUI/正弦版本增加的 `waveform=2` 需下载新版位流后验证。当前首版位流仍可用于默认三角波和脉冲波控制；选择不支持的波形值会返回错误，工具明确提示新版位流要求。

### 仿真与主机测试覆盖

| 测试 | 核对内容 |
|---|---|
| `tb_pt8211_tx` | 实际分频 BCK/WS、两个 16-bit 串行槽、满幅/舍入、欠载静音、功放启动/复位 |
| `tb_synth_engine` | 四声部独立状态、采样边界提交、连续相位变调、ADSR/力度、非法值拒绝、混音满幅、ACK 背压 |
| `tb_sine_rom` | 全部 1024 点相对独立正弦参考的误差、象限端点、对称性、相位桶截断误差上界 |
| `tb_sine_voices` | 四个正弦声部逐样本参考比较、独立相位、变调相位连续、新波形枚举拒绝范围、原流水线延迟、PANIC |
| `tb_uart_control` | UART → CRC/残包恢复 → 合成 → PT8211；独立解码左右 PCM16 并比较参考量化值、非零发声、独立变调、ACK CRC、PANIC、无欠载 |
| `tb_video_timing` | 完整 800×525 帧、640×480 有效区、同步宽度/极性与回卷 |
| `tb_video_monitor` | 异步相位观测压力、三条 32-bit 快照原子性、允许丢弃、复位恢复 |
| `tb_video_peak_meter` | 最小有符号数的绝对值、帧边界与样本同时有效、峰值与衰减归零 |
| `tb_video_tmds` | 全部 256 字节、4 控制码、1024 随机字节，与独立 TMDS 模型比较 |
| `tb_video_dashboard` | 电平刻度、四声部图块、消隐，实际 RTL 生成 [HDMI 预览](dashboard_preview.png) |
| `test_instrument_cli.py` | 原协议、CRC/包布局、音高误差、增益/包络边界、demo 失败清音和原错保留 |
| `test_instrument_backend.py` | 假串口 ACK 重同步/Sequence+Opcode 匹配、超时不重试、A/B 描述、离线标记、单线程所有权、参数合并、NoteOff/PANIC 优先、队列满、握手失败、关闭清音与错误保留 |
| `test_instrument_ui.py` | 独立四声部 JSON、非法文件/数值、四槽分配、旧按键释放、Tk 键盘重复/修饰键、编辑框隔离、参数缓存 ACK 边界、ADSR 图示、焦点清音、状态尾音、真实离线 worker 连接与关闭 |

UART 联合测试使用加速分频，验证功能与帧归属，不用于板级延迟结论；PT8211 独立测试另核对实际 50 MHz/1024 周期。视频仿真未建模厂商 PLL/OSER10 的物理特性，这部分仍依赖 Gowin 分析和板测。

GUI 离线测试不打开硬件串口，不输出声音；它只模拟 ACK 和开关状态。曲线是 ADSR 参数示意，活动掩码表示非 IDLE，ACK RTT 是往返通信时间，这三者都不是音频电平或键盘到耳机的延迟测量。

### 资源、约束与保留告警

GUI/正弦版本 Gowin 资源：Logic **5535/138240**（3689 LUT、1846 ALU），寄存器 **2454**，锁存器 **0**，BSRAM **8/340**（pROM），DSP **32.5/298**，PLL **1**，OSER10 **3**。这些数据仅适用于当前固定四声部与正弦查表，不代表 32 复音或自由图容量通过。

SDC 保留根时钟与 PLL 派生关系。UART RX 和按键经同步适配器进入系统。显示邮箱用握手保持源数据：请求经过同步和额外等待后，至少约 120 ns 才锁存，总线设置 **80 ns 最大延迟**；只对此稳定总线移除同沿 hold 假设，并对 req_meta/ack_meta 首级 D 输入设置例外，其余路径照常分析。工具确认约束激活。

PT8211 外部走线与 DAC setup/hold、TMDS 眼图尚未建立外部 I/O 延迟预算。STA 通过范围是已建模的 FPGA 内部路径，不能写成全部板级时序验收通过。

GUI/正弦版本保留与首版相同的 **7 条工具告警**：

- 六条 **EX3791** 来自第三方 TMDS 编码器的无尺寸常数缩位。对应逻辑通过独立全字节和随机序列参考比较，告警仍可见。
- 一条 **PR1014**：`clk_50m_d` 含普通布线段。V22 在 UG986 PG484A 表中标为 IOB104B/EMCCLK，未标专用 PLL/GCLK 输入；报告确认系统主干使用 PRIMARY PBR1/PBR2/PBR3。UG984 允许 GCLK 源经普通布线，但板级延迟、偏斜及 PLL 锁定仍需关注。文本报告尚不能将告警精确归属到某个入口或 PLL 支路，保持原理图脚位与可见告警，并将稳定性留给板测。

### 首版历史快照

下面是 **2026-09-08 05:17:28** 的首次工具交付记录，不是GUI/正弦版本正弦位流的资源或版本标识。当时未下载；后续用户 HDMI 与 COM26 反馈已单独登记在上方。

| 项目 | 首版快照 |
|---|---|
| 回归 | 8 项 HDL、6 项 Python 通过 |
| 构建 / STA | 完整 Gowin 通过；setup=0、hold=0；最小 slack=0.247 ns |
| Fmax | 系统域 87.658 MHz；像素域 65.601 MHz |
| 资源 | Logic 4875（3152 LUT、1723 ALU）、寄存器 2183、锁存器 0、DSP 32.5、PLL 1、OSER10 3 |
| 首版位流 SHA-256 | `0b32416e36b252ba14a1006f640df6797095eefc3b8f143763f23f6b486a72b8` |

原始 [首版 HDL 摘要](evidence/hdl_summary.txt) 与 [首版构建证据](evidence/build_evidence.json) 未被GUI/正弦版本覆盖。首次交付、随后板上连通性、GUI/正弦版本新功能构建分别适用于对应版本。

### GUI/正弦位流与下一步验收

GUI/正弦版本位流：`impl/pnr/Prj1.fs`，不提交生成的二进制文件。

SHA-256：`ab0ed3617138641baf4be1be1f0d8c6b241b94859823346c33ba49e19a50de40`。

下一步下载该位流，按 [硬件板测清单](hardware.md#8-必须通过实物验证的项目) 验证复位、实际采样率、PT8211 16-bit 格式、正弦/三角/脉冲的耳机声音、模拟幅度与噪声、HDMI 锁定及端到端延迟。GUI/正弦版本 GUI 没有增加音频采样回传、FFT、录音/编码、蓝牙、效果或通用图；主机四槽分配也不等同于板内标准事件分配器。原设计 41 工作包与比赛全量验收继续保留。
