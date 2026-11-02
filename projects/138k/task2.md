# 双 138K 工作站任务清单

决策日期：2026-10-31（Asia/Shanghai）；2026-11-01最新高优先级修订：首批M-DEMO交付可拍视频的基础乐器完整声画，暂不演示TF／CNN；W-DEMO本轮只交付真实手机A2DP／SBC→D实时效果→连续I2S／DAC和USB Host／25K控制及必要反馈，显式W配置从编译与综合网表退出HDMI／图形UI／分析／帧缓存及全部录音下载后端。保留维护源码供后续恢复，不改变M共享行为或冻结候选。两份先独立跑通，再继续LCD通信、最终角色收敛和双板联合验收。手机App提供手机→25K MIDI发送、本机文件播放、选择文件向138K流式输出及真实输出设备确认；目前只有模拟器，真机无线验收后补。2026-11-02用户明确手机MIDI需经25K驱动138K，但25K端转发由用户自行修改，本轮助手不修改25K源码／固件。工作分支：`codex/dual-138k-workstation`。文档起点为已提交源码`01291b571b01349d25e384169f1dea104ed9e0f5`；以下目标和未勾选任务不构成已实现能力声明。

本路线与 [task.md](task.md) 的单板路线并存。该文件“本轮不增加副 FPGA”的约束不适用于本双板分支；不修改其历史记录，也不因此取消主线程正在运行的候选。编写时同时参考主工作区未提交的 task.md；该未提交文件及其他开发改动不随本文件提交。后续从单板主线引入优化时逐提交核对来源和回归，不拷贝完整工程。

## 1. 已确认目标与不可变边界

本节约束最终M／W生产角色。第二块板到货前允许按第5.1节构建M-DEMO／W-DEMO，在同一块板分时运行并临时复用外设；演示镜像与最终角色的差异必须明示，不能把临时外壳固化成另一套产品分工。

**当前阶段优先级：M完整基础声画与W无显示的真实D音频闭环独立推进。** W本轮取消HDMI及录音／手机下载，验收不再等待W声画同步；必须保留真实手机输入、完整D效果目标、连续DAC及25K按下／释放／组合／断连控制，不能用静态测试音或调试命令代替。仅显式W配置收缩功能，M的完整HDMI、新UI、普通／矢量音源、32声部／ADSR和完整效果保持。最终职责表仍是后续双板目标，不能用它冒充本轮实现。

- **主板 M 是可独立演示完整核心功能的 FPGA 工作站。** USB／25K／Push 输入与热插拔、High-Speed链路、唯一参数提交、持音／声部、普通及矢量音源、ADSR、混音、完整效果链、双率时钟、最终I2S／DAC，以及HDMI波形／李萨如／频谱／音效链显示和全部本地分析均留在M。不得以资源压力为由把这些核心移到副板、CPU或回放对端。
- **副板 W 承担蓝牙协议与业务、录音存储／下载、蓝牙媒体解码和端侧 AI。** 副板对外只连接 CAM 与 LCD 板间链路；允许使用本板 DDR、启动 Flash、AE350、片内存储和参考时钟。JTAG 配置／调试属于开发路径，不新增业务接口。显示用FFT／XY属于M；W的音频AI前处理不是其替代实现。
- 最终两板 LCD 连接器复用为板间通信接口，不同时驱动 LCD 面板。不是沿用 RGB 屏扫描协议，也不假定两板直通排线即可安全互接。最终生产W不实例化 USB、HDMI、TF、蓝牙 UART 或 DAC 外设引脚驱动；W-DEMO按第5.1节保留音频／25K交互／蓝牙接口，退出显示与录音。
- **M 不等待 W 发声或显示完整画面。** W不存在／未启动、LCD链路未接、AI忙或后台下载失败时，M仍完成真实USB演奏、音色／效果和HDMI波形／李萨如／频谱／音效链显示；仅副板提供的蓝牙媒体、录音下载和AI扩展不可用。TF文件／播放全链也保留M，不为双板引入跨板扇区请求。
- 全部音频参数只在 M 的既有 `workstation_parameters`／音频执行边界提交。W 缓存带版本的状态，不能成为第二个权威应用点。现有 18-bit 事件及 CC／PANIC 语义保持，链路元数据另作封装，不塞进旧事件。
- 48 kHz／44.1 kHz 及“持音保留、先封存录音／停止 TF 再切换”保持。首入口仍为 M 的 AE350 命令，页面以后复用。W 只确认自己的后台实际终态，不能切换 M 的时钟。
- 先复用现有蓝牙、TF、录音、显示、AI 源码与参考向量。Wi-Fi、本机 LCD／触摸继续暂缓；D 沿用蓝牙流音效上下文方向，不恢复本轮已取消的采样器／音序器集成。
- 最终角色收敛时首批只迁移蓝牙及录音，形成明确主板减负并验证完整单板核心；随后接蓝牙媒体与AI。TF与显示分析不外迁，不等待所有扩展完成才综合主板，也不同时重写所有子系统。当前先执行第5.1节M基础声画与W流式音频DEMO，不以前述最终收敛为演示前置条件。

工程依据：[架构入口](../../docs/architecture/README.md)、[整机接口规划](../../整机接口规划.md)、[原生装配](push2_workstation/usb_a/rtl/workstation/README.md)、[冻结输入规则](push2_workstation/usb_a/baselines/README.md)。USB PL、BLE、A2DP 的外部协议继续使用各自规范，本文件只确定新的内部板间边界。

## 2. 起点与可复用进度

| 项目 | 已有事实／复用内容 | 双板路线不能直接继承的结论 |
|---|---|---|
| 单板 E5／E6／E7 | 已完成完整综合及失败的 P&R；E5 剩 802、E6 剩 788、E7 剩 878 条未布通 | 没有可部署的新整机位流；未布通条数不等于剩余工作量百分比 |
| 单板 E8 | `5eac85f00fa54c84`，综合 Logic 93,321、FF 59,477、BSRAM 250；P&R 已布通，物理 CLS 61,298／69,120、BSRAM 301／340、DSP 120／298 | STA 失败：21,187 setup／297 hold 端点，最差 −13.127 ns；不是可接受部署。物理 Logic 93,808 与综合口径分列；业务替换和后续 RTL 优化净收益不能全归于 AE350 |
| oscillator ROM 实验 E9 | `01291b5`／`c435701f9890c806` 的逐拍回归通过，但完整综合 Logic 99,566，较 E8 +6,245；物理 CLS 61,540、BSRAM 295 | P&R 剩404条未布通。优先复用后续已提交的恢复 E8 oscillator 实现，保留矢量 ROM 和业务迁移；不得仅因 FF／divider 减少就继续沿用该资源回退 |
| 后续时序修复 | `29fbb2beed56f9f6` 综合 Logic 93,029、FF 59,214、BSRAM 250；涵盖 BLE DDR 分 lane、显示 Gray、reverb CE 和 USB 本地域复位／许可修复 | EA 被失效 SDC 别名拒绝；读取时报告仅确认 EB P&R 启动。未确认最终 routed STA／PLL／硬件通过，不能凭后续目录存在推定成功；引入时逐提交核对，不复制主线未提交文件 |
| 主板音频 | 双率、会话／参数、最终物理帧 tap、完整效果、Pitch／Chorus／FIFO／系数优化有现有组件与回归 | 分别通过不等于同一双板主角色已 P&R／上板通过 |
| 蓝牙与录音 | AE350 C owner、H5／HCI／GATT、DDR raw store、CRC／Rice／可靠下载均有维护实现与向量 | 单板 APB 邮箱不是板间协议；独立 25K BLE 通过不等于 W 已接真实 138K PCM |
| TF | SPI／FAT文件owner、WAV直接流式组件及停止排空向量可复用，均保持M归属 | 直接组件尚不能当作当前整机已退出TF DDR中转；本次不引入跨板文件／EOS状态机 |
| 显示 | minor1分析／导出／读取、真实FFT／XY、帧失效与扫描策略已有实现，均保持M归属 | 必须复验完整主角色中的真实波形／李萨如／频谱／音效链，不能退化为基本页或使用W回放替代 |
| AI | 历史 CQT／CNN／Viterbi 与 CAM／YOLO 方向分别盘点 | 当前 no-CNN 主板没有可再扣除的 CNN 占用；YOLO 模型／输入／帧率和共存能力待测 |

资源、候选和验证详情以 [E3—E8 及后续记录](push2_workstation/usb_a/reports/WORKSTATION_AE350_BUSINESS_C21031E3_20261031.md) 为起点。上述 E8 物理结果及 E9／EA／EB 来自2026-10-31读取的主工作区同名报告；该报告较本分支快照更新，本次没有将其未提交内容导入。后续实施先核对主线最新已提交证据及哈希。后续实验日志放 reports；本文件只更新任务状态与证据链接。主线新成果优先复用，但每个固定候选输入保持不变。

### 2.1 主板独立验收清单：副板物理断开也必须通过

这不是只有音频的小探针或测试特供位流。使用同一个完整M生产角色，W物理断开且不注入W回放数据，至少完成下表。W接入、繁忙、复位、断开时再复验同一清单；不能为单板模式另外编入第二套FFT／音源实现。

| 项目 | 必须独立完成 | 必须检查的证据 |
|---|---|---|
| HDMI完整画面 | 实时波形、李萨如（Lissajous／XY）、左右声道频谱、音效链／顺序／开关／参数及实际状态 | 取同一最终实际PCM；真实乐音改变时画面变化，已知频率与声道关系可核对；截图／视频结合数值和最终PCM证据，不接受固定图或伪造频谱 |
| Push／25K热插拔 | 同一USB-A口交替接入、正确设备识别、断开清音／清旧会话、重新枚举及演奏恢复、各自已有显示／反馈 | 设备会话和新增事件计数、实际出声／释放、重连显示／反馈；不是两设备同时连接，也不把旧累计值当新成功 |
| 音源／音色／表情 | 普通A/B/C、矢量、既有音色及多声部／ADSR／力度／延音／滑音／弯音等实际支持项 | 最终I2S／DAC非静音音频、音色变化、声部释放、PANIC，32声部与现有deadline按原目标验证 |
| 效果链 | Pitch及Delay／Chorus／Reverb等原实际支持项、组合／顺序／开关／参数与画面一致 | 对照干声与各效果、左右声道、尾音和切换；主板本地效果历史／DDR不依赖W |
| USB High-Speed | 保留HS Host／ULPI／协商及业务能力；HS设备实际以HS枚举并传输，合法FS设备仍可回落 | 实际端口速度、协商／描述符／包长、MIDI和显示双向有效载荷、热插拔后恢复；60MHz ULPI或“允许HS”不等于480Mbit/s已建立，不要求有效载荷达到理论线速 |
| TF及既有单板功能 | 本地TF选择／播放／停止／拔卡处理；盘点官方单底板已验收功能，逐项列出当前M的来源、配置、现状和补验 | 原有功能不能因副板缺席被静默裁掉；此前明确迁W的蓝牙／录音／AI单列，其他缺项不得用“基本页能亮／能发声”结项 |
| 双率与并发 | 48k／44.1k、持音切率、显示＋热插拔＋音色／效果操作；M不等待W ready | 采样连续性、真实时钟／PCM、切率受控静音、显示正确频轴；W不存在且无远端录音时按实际无事务状态处理，不永久等待远端封存 |

HS／热插拔可复用 [Push实板HS恢复记录](push2_workstation/usb_a/reports/USB2_PUSH_HOTPLUG_20261030.md) 和 [25K HS／FS验证记录](push2_workstation/usb_a/reports/USB2_25K_HS_20261029.md)。前者是独立Host探针而非完整声画整机；后者当次实板未建立新连接、HS／FS成功来自模型闭环。官方底板历史通过、其他载板实测和当前双板主角色验收分列，不能互相转授；缺少历史证据时保留用户陈述并列出待核对项，不编造“已通过”。

## 3. 两板最终职责：每项一个 owner

下表是本分支的最终生产归属；阶段内未迁移功能保持旧实现，必须在候选清单注明，不能在同一个运行系统中同时成为owner。第5.1节的两个分时演示镜像可以包含相同模块／外设适配器；它们不同时运行，不构成两个并行权威，也不改变本表最终分工。

| 子系统／状态 | 主板 M 唯一职责 | 副板 W 唯一职责 | 跨板交付单位 |
|---|---|---|---|
| 演奏与参数 | USB HS Host／VexRiscv、ULPI、Push／25K热插拔与已有反馈、UART MIDI、输入映射、session／PANIC、参数接受及实际提交、实际状态 | 手机／AI 只提出请求；消费 M 已提交状态 | 事件／命令、实际结果、原子快照 |
| 实时音频 | 普通／矢量合成、声部／ADSR／混音、Pitch／Delay／Chorus／Reverb、Delay 本地 DDR、源选择、最终音量／静音、I2S | 不拥有声部、效果历史或最终输出，不远程执行逐样本 DSP | W 输入媒体 PCM；M 输出唯一观测 PCM |
| 蓝牙物理接口 | 真实 UART 字节收发、配置应用、必要 FIFO、已接引脚及实际存在的流控、模块复位执行 | 控制器初始化／补丁／波特率切换策略、H5 序号／ACK／重传、HCI 额度／句柄、GATT、连接与外部业务、后续 BR/EDR／SBC | 有序字节块、配置屏障、真实收发完成及错误 |
| 录音／下载 | 最终物理帧 tap、采集序号／可信度、非阻塞发送；转发用户请求 | 唯一录音对象／ID／格式／任务、DDR 写入与封存、CRC／Rice／下载／ACK／恢复及 Android 业务 | 一份观测 PCM、录音请求、封存终态／状态 |
| TF | 完整SD SPI／初始化／扇区／FAT／目录／曲目／WAV／预取／停止／错误／播放和最终物理EOS | 不参与TF播放，不拥有主板文件游标 | 无常态TF请求／回程PCM；若从TF导入W模型，另作可中断的显式批量任务 |
| 显示 | 最终PCM采集、波形／FFT／频谱／XY计算、原子分析发布、音效链状态、HDMI／DDR framebuffer／扫描／光栅绘制、Push／25K已有显示 | 不提供M画面所需的分析或像素；AI结果只是可选扩展 | 可选AI结果及业务状态；不传显示FFT／XY或整屏帧 |
| AI | 受控接受识别建议、人工／MIDI优先规则、实际应用结果 | CAM、图像预处理、YOLO、音频 CQT／CNN／Viterbi、本地模型／特征／推理队列 | 有上限的检测框／分类／音符结果；模型标识和输入区间 |
| AE350／存储 | 本地控制／启动／状态／TF服务；主板DDR的音频效果、显示及平台仲裁 | 本地蓝牙／SBC媒体／录音／AI服务；副板DDR／模型存储 | 业务消息，不跨板读写APB或DDR |

具体源边界继续复用 `rtl/control/`、`rtl/audio/`、`rtl/services/`、`rtl/bluetooth/`、`rtl/tf_audio/`、`rtl/display_data/` 和 `rtl/memory/`；组合根只负责装配／CDC／ready。两板本地地址分配仍由 `rtl/ddr_address_map.vh` 显式区分角色并核算，链接不暴露对端原生地址。禁止两个独立文件维护互相矛盾的 DDR 分配。

蓝牙迁移复用 [CPU owner](push2_workstation/usb_a/rtl/bluetooth/cpu_owner/CONTRACT.md) 与 [HCI 传输](push2_workstation/usb_a/rtl/bluetooth/hci_owner/NATIVE_TRANSPORT_CONTRACT.md) 的行为，不继续保留 M 的第二套 H5／HCI 信用 owner。M 的串口发送接受不等于字节已发完，更不等于 H5 ACK 或外部业务成功。波特率／复位变更必须排空、确认应用并建立新会话，不能靠定时猜测。

录音迁移完成后，M 的独立 CPU 录音与 BLE raw store 均退出双板主角色；本地命令仍可作为代理操作 W 的同一对象，不再保留另一份 PCM 后备。迁移期若只移动其中一路，须明确列出剩余实例和退休条件，不提前计算整块收益。副板录音与 AI 竞争本地 DDR 时，录音接收／媒体供给有界优先，AI 降帧／暂停，不反压 M 音频。

## 4. 通信契约与明确预算

### 4.1 LCD 链路只传有界消息和连续流

| 类别 | 最小语义 | 故障规则 |
|---|---|---|
| 连接／能力 | 角色、协议版本、双方启动身份、链路代次、功能能力和真实就绪 | 重启／断链撤销旧请求及旧媒体资格；旧 boot／代次的迟到结果丢弃 |
| 控制 | 请求 ID、接受／实际应用／失败分列、截止期限；命令原载荷不擅改 | 满队列拒绝，超时报告未完成；有副作用操作不能盲目重放 |
| M→W 观测 PCM | PCM16 stereo LE、实际 rate、epoch、首帧序号、帧数、可信度／错误；从最终 DAC 完成帧取样 | 不反压采样；缺帧／CRC错／溢出终止录音有效性，分析撤销旧上下文，禁止补旧样本伪装连续 |
| W→M 媒体 PCM | 源／会话、格式、实际 rate、epoch、连续帧号、预填充及尾标记 | M 独立持续采样；欠载使外部源受控静音／失败，旧 PCM 不得恢复播放；不连带停止本地音源 |
| 蓝牙搬运 | 顺序、长度、事务号、可用额度、实际完成与错误 | 原UART时限仍满足；桥接丢字节必须使会话失败，不能继续声称协议连续 |
| AI结果 | 输入rate／epoch／序号区间、结果版本／模型身份、完整提交 | 可丢旧结果，过期结果不应用；不影响M本地完整显示 |

所有包有长度上限、完整性校验与匹配身份；具体字段／CRC／上限只维护于后续唯一内部链路契约和对应常量，不在各子系统复制规范。握手、命令、媒体、分析、模型下载分队列／额度；低优先长传输必须分片并可让路，不建通用远程总线或分布式任务框架。

M 的采样时基是唯一输出权威。W 的参考时钟只用于本地计算／传输，不生成另一套自由运行的“同标称率”DAC 时钟；文件按 M 的消费额度预取。A2DP 的手机时钟频差仍需在 W 的 SRC／时钟恢复处处理，不能靠短 FIFO 永久吸收。板间转发时钟只约束 IO 采样，不等于音频参考。

### 4.2 带宽核算，不传不必要数据

以下为设计预算，均未测量；KB／MB 使用十进制。首版目标为每方向至少 5 MB/s **有效载荷**，实现频率与位宽由真实引脚／电气／时序确定，不能把连接器名称当作带宽保证。

| 载荷 | 48 kHz 上限或计算方法 | 限制 |
|---|---:|---|
| 最终 PCM 观测 M→W | 48,000 × 2 × 2 = 192,000 B/s；44.1k 为 176,400 B/s | W录音／音频AI需要时共用一份流；M的FFT／XY只读本地tap，不额外发送 |
| 蓝牙媒体 PCM W→M | 同上；若实际接口用双通道32位容器则翻倍为 384,000 B/s | 一个A2DP外部媒体流，与M本地TF按既有源选择策略切换，不新增并行效果实例 |
| TF文件及显示分析 | 常态板间传输为0 | FAT／WAV／播放留M；波形／FFT／频谱／XY分析及渲染也留M |
| 蓝牙字节，双向分别算 | 按实际 UART 波特率／帧格式计算；8N1 的字节上界为 baud/10 | 核对实际 H5 转义／ACK及突发，不虚构未接的 RTS／CTS；物理口速率不是蓝牙有效音频吞吐 |
| AI 结果／状态／模型 | 结果数量和刷新率有上限；模型优先 W 本地 Flash／DDR，初次装载另计 | 不传原始 CAM 视频、特征图、逐声部 PCM 或完整 HDMI framebuffer；模型搬运让路实时业务 |

链路验收分别登记两个方向：实测有效带宽、最坏服务间隔、各业务峰值／突发、FIFO水位与溢出策略。必须覆盖观测录音＋蓝牙播放＋音频AI＋蓝牙协议并发；同时M本地完整显示、TF及USB不被拖停。分配不能超过实测服务能力，容量不能只按平均吞吐选择。

首版移植保持既有format 1的48kHz BLE语义，44.1kHz录音沿task.md的兼容扩展独立验收；不修改标签冒充已支持。单个录音固定格式／rate／epoch，READY后不可变。主动切率先完成实际存在的W录音封存及M本地TF停止，再由M切换：从未接入W且没有远端事务时不等待W；已有远端事务而W失联时明确失败，M保持原采样率和持音，不伪造封存成功。链路重启必须让W终止断开的录音，旧对象是否仍可下载按真实完整性判断。

TF完整留M，复用[直接TF契约](push2_workstation/usb_a/rtl/tf_audio/WORKSTATION_TF_DIRECT_NATIVE_V1_CONTRACT.md)并以真实I2S尾帧判断播放完成；不新增跨板扇区或TF EOS。M显示保持[显示契约](push2_workstation/usb_a/rtl/workstation/RUNTIME_DISPLAY.md)的最终PCM关联、原子提交与失效语义；真实FFT／XY、首帧ready和全部图形数据在M闭环，不能等待W或用W回放解锁完整画面。

## 5. 同一块 138K 分别验证两个角色

**M、W 必须能独立 prepare／综合／P&R／启动；每个角色能在同一块兼容的物理 138K 上分时运行，不需要另一块 FPGA 同时在线才得到有效测试结果。** 角色切换只影响本次 SRAM 身份；原 Flash 回退保留。另一块板的实际 pinout／装配仍须独立核对，不能把一块板的电气验收转授给另一块。

分时验证本身不证明通信量低；真正降低通信与联调成本的是完整 owner 留在一端、本地完成中间处理、跨板只交付稳定的块／结果。禁止把本来本地的状态机拆成大量必须对端立即回答的小操作。

复用现有构建入口与来源清单机制，增加显式 M／W 角色和受控测试配置，不复制两个完整工程、不增加长期编号 builder。生产角色与测试角色各有独立身份；fixture／回放适配器不得混入发布候选或替代真实协议 owner。一个可复用的轻量参考对端覆盖各消息种类，不为每项任务再造一套独立平台。

| 层级 | 在同一块板／主机上怎样完成 | 能证明与不能证明 |
|---|---|---|
| S0：离线角色验证 | 真实 M／W 模块分别接参考对端，再在仿真连接真实双端；共享确定性输入与期望输出 | 证明协议／业务和错误路径；不证明引脚、持续物理带宽或板上时序 |
| S1：单板 M | 首先用完整M生产角色、W物理断开且无回放，完成第2.1节全部独立验收。随后才用参考W验证蓝牙PCM／业务请求及断连隔离，不修改本地音源／效果／分析归属 | 证明实际完整主板可单独使用；不能用参考W生成频谱／李萨如或代替真实USB／DAC／HDMI。扩展回放不算手机互通 |
| S2：同板改装载 W | 实际W核心＋参考M数据／字节流，输入非静音PCM、互动H5／GATT对话，读取对象／CRC／响应／AI结果；真实本地DDR，CAM可用时接真实图像 | 证明副板能独立启动和处理；不要求启用W被禁止的其他业务引脚。无实际摄像头时只计CAM fixture，不计真机图像验收 |
| S3：记录与顺序回放 | 先运行 M 保存带源身份／时序／错误／hash 的输入；同板运行 W 消费并保存输出；再运行 M 回放 W 输出。测试向量可分小段重复，不能为测试塞入整段歌曲或重新引入生产大缓存 | 验证真实双方数据兼容及 CRC／结果；顺序回放不能证明实时并发、端到端延迟或无线控制器时限 |
| S4：单板 LCD 电气／压力 | 授权后用经过逐脚核对的回环／测试夹具，测实际 LCD IO、两方向吞吐／错误／队列。对端回放器经同一串行化／CRC／队列边界进入，不只旁路注入成功结果 | 板内回放不算连接器验收；回环不代替两块板之间的独立时钟、接地和布线验收 |
| S5：最后双板联合 | 只集中验证真实电气、独立时钟、持续并发吞吐、真实蓝牙／手机、切率封存／EOS、双方重启／断连与端到端延迟 | 这是双板系统验收，不能删除；基础业务错误不留到这里才首次发现 |

S1扩展测试／S2的参考对端复用生产角色核心文件和接口，记录唯一差异与源码hash；真实DSP、DDR、时钟、协议状态机不能替换成“永远ready／成功”的stub。每个W迁移模块开始前明确输入入口、按真实输出动态回应的有状态对端、结果读回、期望值和失败用例；固定轨迹回放不能替代重传／取消／请求顺序变化。可通过已审核的JTAG／片内观测路径检查结果，不为了测试给W增加永久UART／USB业务接口。需要真实蓝牙的单角色硬件测试可使用经过审核的LCD转接夹具；没有夹具时将真实无线验收明确留给S5，不伪称纯回放已完成。H5／初始化／波特率切换的跨板最长等待和失败恢复须先证明，不能仅以平均带宽达标结项。

### 5.1 过渡交付：M基础声画、W流式音频分别独立跑通

2026-11-02调整为M26-1正式范围（取消M22-1候选，基于M26）：Push Session实体CC51复用已退出TF的入口；每次有效按下按实际已提交率在48／44.1kHz间翻转，松开不触发，Select矢量入口保持。释放稳定5ms去抖、忙时或故障按键消费拒绝且不排队，过期代际请求不得在恢复后补翻转。所有操作进入既有唯一音频时钟服务及完整静音／双晶振DCS／预填充事务；HDMI独立显示实际提交率和切换／故障，不回显请求值。新增真实Push→服务→DCS→DSP／I2S双向回归，含持音、尾音、PANIC、背压、失败恢复和切换期间持续HDMI；进入新身份D2110138全量综合／P&R，不能继承M22的微小时序试装例外。李萨如改为轨迹更连续、浅底深色和有限两快照余迹；仍取真实最终PCM并自动缩放。本轮普通A/B/C采用X=R−L、Y=L+R，先有符号17bit扩位求和／差，再两轴统一除2并反转屏幕Y方向；同相竖线、左单声道╲、右单声道╱，矢量保持既有L／−R直接XY，不冒称亮度渐变余辉。切率、context撤销及PANIC不得残留旧轨迹。此处为范围与验收标准，具体源码／离线／实板完成状态依新报告记录。

**本节最新范围替代此前“两份共同完整HDMI＋W录音下载”的阶段要求。** M、W各自独立prepare／综合／P&R／启动和操作，可在同一块兼容138K分时SRAM验证；不等于双板并发或LCD互通。冻结历史候选及报告不修改，新输入使用新身份。

| 镜像 | 本轮实际交付范围 | 退出与保留 | 后续恢复／最终角色 |
|---|---|---|---|
| M-DEMO基础乐器 | 普通A/B/C、矢量、32声部／ADSR、完整效果、Push／25K、完整HDMI波形／李萨如／双声道频谱／音效链、真实I2S／DAC | 本轮退出TF读卡／FAT／解码／DDR播放、识别配套及其等待／无效入口；保护新浅色HMI和已有效果／音源 | 基础声画通过后显式恢复TF／CNN／Push指导；最终完整M独立验收另补 |
| W-DEMO流式D | 真实手机A2DP→SBC／必要漂移SRC→D实时效果→连续I2S／DAC；USB Host／ULPI、25K触摸／旋钮及必要反馈 | **从编译及综合网表退出HDMI、AE350图形UI、波形、FFT／频谱、XY、显示帧缓存及相关CDC／等待；全部录音／手机下载后端及无用DDR事务退出。** 不重复普通／矢量、声部／ADSR、TF／CNN、Push专属业务 | 保留维护实现，录音／手机下载以后以显式配置恢复；最终媒体经LCD供M效果／输出，演示期本地参数点届时退出 |

每份独立DEMO各有一个本地实际参数提交点，沿用现有事件／USB PL／BLE契约；最终双板仍以M为唯一权威。W可直接进入D上下文，不能为本轮重加采样器或A/B/C。25K按下启效、松开只撤销自身效果，组合操作互不清除，断连清理全部旧会话控制；持续播放期间不停止采样。真实连续PCM Pitch的维护实现及W参数／25K／生命周期离线接入已完成；新整机候选全量EDA与手机／DAC仍未验收，单列跟踪，不用采样器变调或长期SRC漂移补偿冒充。

M画面必须来自实际最终PCM和已生效参数，操作期间声画持续；W本轮没有HDMI验收条件，以真实手机持续播放、25K实际效果控制及连续DAC取证。主机探针只补充定位，不能代替正式无线／音频闭环。Flash写入仍需另行授权。

手机App明确区分本机播放、向138K的蓝牙流式播放、手机→25K的MIDI控制，并提供真实SAF文件选择、播放／暂停／进度和实际输出设备状态。BLE连接不等于A2DP媒体路由；只在模拟器通过的构建／UI不能记为真实无线通过。

### 5.2 两份镜像的具体覆盖矩阵

下表是当前实施与验收分配，不是已通过表。仅维护M-DEMO／W-DEMO两个交付配置；开发候选不暗中变成第三份交付镜像。运行时关闭不算编译／网表退出。

| 功能／真实闭环 | 镜像及必要组成 | 通过条件与证据 |
|---|---|---|
| M完整基础乐器声画 | control／普通与矢量engines／32声部ADSR／完整effects／frame delivery／output router／HDMI | Push或25K真实MIDI→实际DAC；真实波形、XY、双声道频谱、音效链及参数一致；32声部、PANIC、双率／尾音；不依赖W |
| W真实D流式音频 | A2DP／SBC／必要SRC→单套完整D效果目标→连续I2S／DAC | 真实手机持续播放；Pitch独立补齐及验证；Delay／Chorus／Reverb组合和参数有效，断流／欠载受控静音，不停采样、不回放旧PCM |
| W的25K控制 | USB Host／ULPI／25K适配及必要反馈 | 按下启效、释放仅撤自身、组合、旋钮、热插拔／断连清理；持续媒体下效果与实际状态对应，不以AE350调试命令验收 |
| W编译／网表退出 | 显式W配置、固件功能开关、源清单、实际VG／VO检查 | 无HDMI／图形UI／波形／FFT／XY／显示帧缓存及无效CDC；无独立CPU／短录音／BLE raw录音／cue后端或无用DDR请求；维护源码保留，M行为不变 |
| W必要DDR | D效果／延迟线／PCM实际缓存及平台仲裁 | 按`ddr_address_map.vh`核查真正客户端与事务；不盲缩FIFO／HCI信用，不能把删除旧子树算作新物理收益 |
| Android配套 | app→data→ble→protocol既有依赖；本机／138K路由、SAF及手机→25K MIDI | 文件选择／播放／暂停／seek和真实路由反馈；MIDI音符按下／释放、力度与断连清理按已有协议。模拟器构建／UI与真实手机BT／25K链分别记录 |
| 后续TF／CNN、录音下载、CAM／YOLO | 保留维护源码及既有协议，显式恢复时新候选验收 | 不阻塞首批；真实Pitch仍属于W音效缺口，不能随录音延期。CAM／YOLO缺实现／模型据实记录 |

取证顺序：M启动完整画面并演奏／切音色／调效果；W启动手机流式音频并验证25K按下／释放／组合／断连及连续DAC。每段标实际UserCode、接线、源／位流hash和通过范围。独立实拍可剪辑，同板分时不得声称双板并发或未发生的跨板传输。

### 5.3 既有资源盘点与先跑通的实施顺序

M基础范围保持：退出TF读卡、FAT／解码、DDR播放、识别配套及无效等待／入口，维护源码保留；实际旧实例是`workstation_tf_runtime_service`→`tf_workstation_audio_bridge`／FAT及DDR缓存，`workstation_tf_direct_service`并未接入旧镜像，不将直读核说成已部署。普通A/B/C、矢量、32声部／ADSR、完整效果、Push／25K、完整HDMI及I2S／DAC保留。

M浅色工控HMI继续在维护`feedback_dashboard.v`及品牌资产实现，白／浅灰底、深灰文字、蓝灰选中、细线矩形分区。赛事核实为全国大学生嵌入式芯片与系统设计竞赛'2026的FPGA创新设计赛道、高云选题二；logo来自总官网所链赛道官网，10TH／2017—2026是赛道十周年，不推定总赛事届数。口号原文为官方“竞赛原则”，来源／原PNG／许可／转换hash见既有资产报告。画面消费实际owner投影；不宣称与更早分析缓存同采样时刻。

历史E8子树／Classic资源盘点只作定位，不预记新配置收益。此前W20完整显示／录音候选的失败物理结果保留，不继续为已退出的录音链优化阻塞本轮。新W在明确退出后全量综合／P&R，实报Logic／LUT／ALU／FF／RAM16、综合等价BSRAM与物理BSRAM／CLS／DSP、完整STA／CDC／PLL及服务间隔；不放宽时钟／false path，不以退出名义盲缩信用或缓存。

直接执行：①显式W退出第5.4节显示／录音及配套，保留真实D／25K／必要DDR；②M、W分别尽早全量综合／P&R，W新候选预留`D2110131`，M23 `D2110130`按实测STA失败路径另修新候选；③离线门通过后执行已授权SRAM下载、身份读回及实际业务取证；④基础交付后再恢复M TF／CNN、W录音下载，继续LCD和最终双板角色。手机当前只有模拟器，真实无线验收待实机，不能用模拟器或数字探针结项。

### 5.4 W显式配置减负：退出显示与录音，保留D／25K／DAC

以下是最新已授权范围，**源码／编译／网表验证及物理结果尚须逐阶段记录，不能沿用旧W20的已实施结论。** 只通过显式W配置生效，共享维护源码的M行为及冻结M23输入保持。

| W处理项 | 实际退出／保留要求 | 检查点 |
|---|---|---|
| HDMI与图形UI退出 | 不编入HDMI输出、AE350图形UI／renderer、波形、FFT／频谱、XY、framebuffer／绘图／扫描；维护实现保留 | 源清单及实际VG／VO无对应实例／存储／输出驱动，不能只置运行时enable=0 |
| 显示配套退出 | 清理显示邮箱／CDC、帧等待、UI请求／状态及其DDR客户端；平台ready不再依赖不存在的video reset／首帧／ACK | 无显示故障反压采样、无死等待，M仍保留完整原行为 |
| 本轮全部录音后端退出 | 独立CPU录音、旧本地短录音、BLE raw DDR对象／下载、cue及无用配套接口退出；录音／下载请求明确不支持，不报虚假成功 | 无录音存储／事务／封存等待；CPU与BLE不保留第二真实对象。未来恢复时仍只允许共享同一个真实对象 |
| 普通／矢量／TF／CNN／Push专属退出 | 不重复声部／ADSR／普通音色／矢量、TF读卡／识别、Push屏幕／灯光／跟奏 | USB Host／ULPI／枚举／会话及25K必要反馈保留，不能记整个USB子树被删除 |
| D及必要DDR保留 | A2DP／SBC、唯一H5／HCI信用owner、必要SRC、完整D效果目标、延迟线、PCM缓存、时钟和最终连续I2S／DAC | 流式Pitch缺口单列补齐；按下／松开／组合／断连不停止采样；不要用sampler或漂移SRC冒充Pitch |
| 配套固件／App | 关闭无消费者图形／录音命令与任务，避免无效轮询／等待；媒体和25K控制入口完整 | 不修改BLE／USB线规；App基于真实能力显示，不把BLE连接当媒体路由 |

不预记面积／时序收益，不用综合等价RAM推算物理块数，不先开展全量资源重写。退出后的新全量候选仍需完整STA／CDC／PLL及真正手机／25K／DAC验收；W本轮取消声画同步前置条件，M完整声画标准不变。

W的[连续PCM Pitch正式维护接入](push2_workstation/usb_a/reports/DUAL138K_STREAM_PITCH_INTEGRATION_20261101.json)已完成离线阶段：仅D_ONLY实例，实际PCM→Pitch→原crush／drive→完整FX；沿用唯一参数owner及原session／rate／native取消广播，25K G按住结合滑条启效、释放回中，H临时dry并只恢复仍按G，O保留D／C／R，反馈取真实committed index。实际C→MMIO→FIFO／CDC→D／DDR→反馈28716帧／559事件／378检查点／9生命周期／256滑条及完整D29312帧通过，149clock最大服务间隔；两实际输出／history负控拒绝。M／legacy完整服务88191／88223半拍逐位相等，两种非W固件完整预处理相同；组合负控先在legacy失败，另补native-M-only实际输出负控拒绝。主线程重验274文件，336重复输入引用对应123唯一路径／111内容对象，4owner严格inverse等于提交前HEAD；后续runtime_profile变化按原封存object核对，不替换旧测试输入。粒状旁带、峰值偏理想约5.4Hz及pitch-up无抗混叠保持，实际新W revision3／GPRJ／全量综合／P&R与真手机／DAC仍待验，不将retirement独立M FFT fixture说成W保留显示。

M24 `D2110132`的[完整定向物理结果](push2_workstation/usb_a/reports/DUAL138K_M24_DIRECTED_PHYSICAL_20261101.json)已封存：全量P&R551.683秒退出0，物理BSRAM246／DSP116／CLS46554／FF43124／LUT47943／ALU11940／SSRAM99；setup135／最差−.215ns、hold10／最差−.144ns，recovery+2.100／removal+.275ns，DDR原3.500ns保持且指定hold+.631ns。最差glyph地址，audio rate→vector envelope与delay underflow→oscillator expression CE仍负，完整STA失败。原冻结v3审计失败保留，独立v4 native59项45过／14具名skip／61负控、六PLL／7负控，以及boundary7／69、performance17／8通过；HMI通用guard的skip不冒记执行，另补实际routed60live／8常0／61unused、16组合frameCE及8破坏控制全拒，物理CDC接受仍为false。全部物理输入／产物及审计证据逐项重hash，详见报告seal；未上板，M25新身份另测，不修改旧132或预记修复收益。

M25的[完整prepare／新综合与D2110133启动](push2_workstation/usb_a/reports/DUAL138K_M25_PREPARE_SYNTHESIS_20261101.json)已完成阶段验证：真实prepare前dirty原字节900／暂存606／编译262／冻结工具1466及M866锁，身份5f7dce4fde5c4ce0；当时HEAD6e8仅作上下文，不冒称含稍后5b17的Pitch提交。较M24仅event owner／parameters的W分支和brand3编译输入改变，其他259逐字相同，M不编译Pitch实现。完整综合169.821秒、608输入前后不变，FF43272／LUT48124／ALU11406／BSRAM等价206；17来源回归通过。strict v1因缺既有HMI60/M140审计适配拒绝，独立cache v2窄移植后通过；旧native测试API／映射错误保留，独立v3实际60项43过／17具名skip／66负控（含8HMI）通过，维护迁入另记。主线程重hash全部原源／暂存／三套工具及物理输入，133以新VG独立定向P&R，原SDC／DDR3.500ns与128ref要求不放宽；实际routed资源／STA及实板待验，不预记通过。

M25 `D2110133`的[全量P&R及完整物理子门](push2_workstation/usb_a/reports/DUAL138K_M25_DIRECTED_PHYSICAL_20261101.json)已完成：377.508秒、12输入前后不变，物理BSRAM246／DSP116／CLS46606／FF43272／LUT48015／ALU11922／SSRAM99；setup109／最差−.203ns，hold0／最差+.146ns，recovery+3.033／removal+.281ns。DDR原3.500ns且指定hold+.482ns；新brand glyph地址已退出top50，但expected_sequence1→writer req_addr CE、audio rate→vector phase／envelope及read_x→HMI文字仍负。actual VO native60项45过／15具名skip／61负控、boundary7／69、六PLL／7负控、performance17／8及clk50四报告全正；通用HMI guard的skip不冒记执行，另以新VG库存及实际routed来源／16组合frameCE／reset／SDC和8破坏控制补证，60live／8常0／61unused保持。完整STA与物理CDC接受仍false，未上板，M22 v6留板、Flash未写；主线程完整重hash封存见报告，不以局部门覆盖失败。

W22的[显式revision3实际来源／全量综合／134物理启动](push2_workstation/usb_a/reports/DUAL138K_W22_SOURCE_SYNTHESIS_20261101.json)已完成来源阶段：连续Pitch实际加入W GPRJ，M不编译该实现，M配置／features／policy只刷新来源锁；M866／W1113均逐hash核对。新W身份187bb0b3d2cab14f，970原源／610暂存／129编译／1466冻结工具；完整综合113.520秒，612输入前后不变，FF27210／LUT30832／ALU11298／BSRAM等价192（物理另测）。旧112反馈门真实拒绝后，独立strict v3只显式W Pitch接受精确142位，新增30位直接绑定唯一parameters Q，bit36常1；150实际VG负控全拒，source148／dest149统计如实，旧131112位结果不改。17来源／17审计／audio-only4／Pitch8正28负、W131 native60／23skip／64负控与boundary7／69通过，W-only4PLL／3tuple／6grant及47独立负控、M132默认行为逐项保全；645个完全相同GND重复SDF只内存折叠，448非零至.537ns保持，原SDF不改。W131完整P&R真实BSRAM210／DSP57／CLS30822，setup2304／−2.868ns、hold2／−4.376ns失败并保留。134普通CST全量P&R已真实启动，DDR原3.500ns不放宽，不把定向比较先前拒绝改成通过；新资源／STA／手机DAC仍待验。既有PLL单测8处文案断言失败及单独fixture修复后续另记，不冒记全测试通过；本阶段不碰板。

## 6. 分阶段任务与退出条件

**当前状态解释：** 以下按日期保留的W完整HDMI／录音证据属于此前候选；不代表本轮仍需交付这些能力，也不证明最新无显示／无录音配置已通过。当前执行与验收以第5.1—5.4节最新范围为准。

2026-10-31 实施进展：两份显式 DEMO 已修改实际消费的维护 RTL／配置／固件，D／25K、唯一录音、HDMI 实际参数及 App 源码构建的离线阶段已通过。M v5 与 W v3 完整候选均已全量综合，M v5 严格网表门禁通过并启动 P&R；真实资源见[第一阶段来源与证据](push2_workstation/usb_a/reports/DUAL138K_DEMO_SOURCE_20261031.md)。M 基础 revision 暂不含 CNN，W 录音容量仍约0.341秒；P&R、实板声画和真实手机 A2DP／BLE 共存未通过前，T2-D1／D2 保持未勾选。后续 App／虚拟机优化按用户新增授权执行，模拟器不代替无线验收。

手机配套阶段已完成 `0.3.0-demo-d2`：音乐页采用真实 SAF／MediaPlayer／A2DP 路由；W 当前仅公布 `0x68` 录音下载能力时，App 不显示虚构的音色／声部／A/B/C 状态，保留音乐、录音、下载及25K调参说明。73项协议／数据回归和3项独立ARM64 Android模拟器UI测试通过，最终APK已复验文件准备与无A2DP禁止起播；[构建、APK身份和模拟器证据](../../clients/android/docs/DEMO_D1_20261031.md)分别记录。真实手机连接W、流式D处理及持续声画下BLE录音下载仍待同一位流验收，不转授为T2-D1／D2通过。

首轮物理结果已取得：M v5全部布通并生成`D2103101`位流，但8,219个setup／71个hold端点违例，禁止转授为可部署声画镜像。实际物理CLS49,644、BSRAM235、DSP120；与综合BSRAM195分列。已按真实关键路径完成显示导出与reverb局部流水离线验证、修复W SDC层级严格校验；新W v5已准备并启动全量综合。[物理测量与修复记录](push2_workstation/usb_a/reports/DUAL138K_FIRST_PHYSICAL_20261031.md)保留失败身份、hash和后续验收范围。新的资源／时序收益尚未测得，未下载SRAM或写Flash。

后续只合并主线已提交`a4e2804`／`44f804f`的原生CDC及数据路径修复，未导入其未提交reverb／task／报告。合并后raw DDR、录音authority、TF、显示及生产启动真实I2S组合的定向回归通过。W v5已完成全量综合，仍有两项真实会话存储selector闭包待核验，未绕过端点门禁进入P&R；M新候选继续补窄CDC与同步音高关键路径修复，结果另立身份。

M v6完整综合已完成，M v7只修正routed RAM拆分selector、581个非SDC输入与260条编译路径逐项保持；显式复用同一VG并保留独立身份`0067ea90a6354485`。M v7严格综合网表门禁通过，新`D2103103`已启动独立P&R。音高／除法器修复的独立数值与32声部PANIC回归见[音高报告](push2_workstation/usb_a/reports/DUAL138K_PITCH_LOCAL_TIMING_20261031.md)；实际物理收益尚待本次结果。用户确认目前只有模拟器，真实手机A2DP／D处理／BLE共存待实机可用后验收。

M v7已完成独立P&R并生成位流：物理CLS49,996、BSRAM235、DSP120；setup4,069／hold1，audio Fmax67.089 MHz，时序仍失败，未上板。实际VG／VO的4邮箱及98位注册RAM等[局部CDC结构与已装约束验证](push2_workstation/usb_a/reports/DUAL138K_NATIVE_CDC_20261031.md)通过，不转授完整CDC／PLL接受。剩余同步逻辑、TF／PC健康窄CDC和DDR单个hold继续按真实路径纠错。

本批已完成维护HCI能力捕获的[真实综合缺陷修复](push2_workstation/usb_a/reports/DUAL138K_HCI_CAPTURE_20261031.md)、[矢量事件许可等价因子化](push2_workstation/usb_a/reports/DUAL138K_VECTOR_DISPATCH_20261031.md)、[显示分析入口逐拍等价](push2_workstation/usb_a/reports/DUAL138K_DISPLAY_ANALYSIS_EQUIVALENCE_20261031.md)及[TF／PC精确CDC](push2_workstation/usb_a/reports/DUAL138K_NATIVE_CONTROL_CDC_20261031.md)。M v8 `f11f1756db68044a`完整综合及严格门禁通过，`D2103105`完整P&R已完成：物理CLS49,879、BSRAM235、DSP120，setup3,042，最差−1.729 ns；工具hold36由1条DDR data hold及35条reference48 removal组成，另有13条USB reset recovery，仍不可部署。准确细分及位流hash见[M8物理测量](push2_workstation/usb_a/reports/DUAL138K_FIRST_PHYSICAL_20261031.md)。W v6真实HCI会话键恢复；两个无人消费诊断输出的[实际消费者及故障／完成闭包](push2_workstation/usb_a/reports/DUAL138K_W_RECORDING_DIAGNOSTICS_20261031.md)与负控核验后，W v7 `aec83bda901d0042`重新全量综合并通过严格门禁，未复用W v6。W首次完整P&R `D2103102`已布通：物理CLS57,639、BSRAM293／340、DSP68，setup9,178／hold2，最差setup−8.598 ns，实际PCM owner写入控制为首要同步瓶颈；[W7物理证据](push2_workstation/usb_a/reports/DUAL138K_W7_PHYSICAL_20261031.md)保留来源及失败范围，未上板。

DDR保持原3.500 ns约束的M v7远端双region变体`D2103106`已完整P&R，reported hold归零（DDR +0.682 ns、整体最差 +0.143 ns），setup／recovery仍失败；近端变体`D2103104`失败记录保留。[定向布局证据](push2_workstation/usb_a/reports/DUAL138K_DDR_HOLD_20261031.md)不转授整机通过。M7／M8六PLL及serializer的[显式DEMO来源／同步RESET结构门禁](push2_workstation/usb_a/reports/DUAL138K_DEMO_PLL_SOURCE_GATE_20261031.md)已通过，不覆盖失败STA及未完成的完整CDC。后续维护源[取消epoch资格](push2_workstation/usb_a/reports/DUAL138K_EPOCH_MATCH_20261031.md)通过419万种穷举、完整service 48,645帧独立PCM及1.159亿次逐拍检查；[时钟下降沿释放／显示请求寄存](push2_workstation/usb_a/reports/DUAL138K_CLOCK_DISPLAY_CONTROL_20261031.md)通过旧版公共输出逐拍一致、完整display及负控。新物理收益待新身份全量重测，不倒填旧候选。至此仍未下载SRAM或写Flash，T2-D1／D2保持未勾选。

M8的TF DDR同域32位减法反馈已在维护DMA中改为同拍提交的占用计数，原请求／响应／输出时序保持；两容量共800,014次新旧公共输出／内部状态比较、三种真实RTL负控、四种独立byte／ring oracle，以及四配置完整TF/WAV和停钟clear回归通过，见[TF占用计数证据](push2_workstation/usb_a/reports/DUAL138K_TF_OCCUPANCY_20261031.md)。物理收益待新候选，不转授M8时序通过。

后续维护阶段已验证：[USB FIFO生产端本域复位](push2_workstation/usb_a/reports/DUAL138K_USB_FIFO_LOCAL_RESET_20261031.md)保持原audio清空／drain，新增显式配置及真实13FF／packet RAM写准入门禁；[W PCM窗口写资格因子化](push2_workstation/usb_a/reports/DUAL138K_PCM_WINDOW_GATE_20261031.md)通过7,190拍完整owner对照及1,454帧真实DSP／I2S runtime；[M逐音表情平衡前缀](push2_workstation/usb_a/reports/DUAL138K_EXPRESSION_PREFIX_20261031.md)通过613万半拍旧版对照，旧算术／ADSR provenance保持。Delay心跳／APB held response／TF quiesce的[精确CDC v3](push2_workstation/usb_a/reports/DUAL138K_NATIVE_TIMING_CDC_20261031.md)通过M8实际VG／VO和W7 VG及负控，拟安装新SDC未倒填旧STA。W7真实六PLL／serializer门禁也已通过。

M9 `aa7abf5c6454a377`／W8 `d1109d2f36e8e171`已分别完成全量综合及完整严格网表门禁，综合LUT＋ALU为64,588／81,846、BSRAM equivalent为195／257；`D2103107`／`D2103108`的P&R现已完成，完整STA仍失败。[本轮综合证据](push2_workstation/usb_a/reports/DUAL138K_M9_W8_SYNTHESIS_20261031.md)保留首次日志路径错误的终止记录和随后正式重跑结果；[monitor](push2_workstation/usb_a/reports/DUAL138K_MONITOR_CLOCK_AUDIT_20261031.md)及[FIFO](push2_workstation/usb_a/reports/DUAL138K_FIFO_FULL_NETLIST_AUDIT_20261031.md)外部审计修复仅更新验证工具，候选封存输入未改。另有W7真实performance异步释放链的[独立验证与窄SDC提案](push2_workstation/usb_a/reports/DUAL138K_PERFORMANCE_RELEASE_20261031.md)，尚未接入当前候选。至此未下载SRAM或写Flash，T2-D1／D2仍未完成。

M9实测setup6,772、最差−3.643ns，唯一DDR hold−3.506ns，recovery／removal已正；W8 setup8,325、最差−9.674ns，hold2、recovery仍失败，物理BSRAM293／340。M9最差TF晚到增量现改为高位独立预计算及低6位选择，[独立算术／旧版逐拍及完整TF回归](push2_workstation/usb_a/reports/DUAL138K_TF_SMALL_DELTA_20261031.md)通过，无新增周期；实际物理收益待新候选。下一步继续修复M的PANIC高扇出、W的PCM owner资格链及窄复位约束，并独立测量新DDR布局变体，不把旧候选失败或局部修复转授声画通过。

W真实performance三拍释放的[窄约束与50MHz专项报告已接入DEMO构建](push2_workstation/usb_a/reports/DUAL138K_DEMO_TIMING_INTEGRATION_20261031.md)：仅W的六个release CLEAR采用已证明的来源例外，四条后级D仍为2ns；M/W增加四条专项report命令。W8实际VG/VO各12项及8个网表负控通过，没有追改旧候选。M9／W8独立far布局`D2103109`／`D2103110`保持同VG/SDC，实测DDR hold+0.755／+0.633ns，完整STA仍失败，四份真实物理结果及局部门禁见[本轮物理证据](push2_workstation/usb_a/reports/DUAL138K_M9_W8_PHYSICAL_20261031.md)。

M的[PANIC交付保留窗／render握手／等价增益](push2_workstation/usb_a/reports/DUAL138K_AUDIO_CANCEL_DELIVERY_20261031.md)通过48,691请求全完成、48,645帧独立效果比较及22,532帧真实I2S整链；W的[描述符及许可组合修复](push2_workstation/usb_a/reports/DUAL138K_PCM_DESCRIPTOR_GATE_20261031.md)通过完整owner旧版对照、115,011向量／4负控、长测与1,454帧runtime，交叉审查无阻塞。新M10b `370f528922c4fcb5`／W9b `01aa047a4d25aaf1`均已从各821项来源锁完整prepare并双重校验，实际消费上述维护RTL／时序补充，分别587／644封存输入；已启动两套全量综合。首次prepare的recognition封口顺序拒绝保留，新输出已修正并通过，未预记新的综合／物理收益，仍未上板。

M10b／W9b现已完成[全量综合及严格准备门](push2_workstation/usb_a/reports/DUAL138K_M10_W9_SYNTHESIS_20261031.md)，实测LUT＋ALU64,446／83,097、综合BSRAM195／257，`D2103111`／`D2103112`已启动默认完整P&R，未加旧far布局。W额外原生局部CDC门对APB请求资格新映射的拒绝正核验，不能以综合准备门PASS代替该项或完整物理验收。

W9b的APB请求实际采用唯一INV反馈和精确IDLE／启动CE，维护[外部网表审计](push2_workstation/usb_a/reports/DUAL138K_APB_LAUNCH_NETLIST_AUDIT_20261031.md)现已补齐该合法映射、49位载荷保持／第三同步沿捕获及完整消费者闭包；W9b／W8实际VG和已装SDC通过，分别36／34个破坏负控均拒绝。原候选及其旧审计输入保持封存，新审计器另记hash，不重综合或追改原失败证据。该局部通过不转授完整CDC、P&R或硬件验收。

M10b新实测定位的TF容量宽加法及配置ACCEPT准入链已在维护源修复，[实际旧版对照／完整TF与I2S证据](push2_workstation/usb_a/reports/DUAL138K_LATE_ADMISSION_20261031.md)通过：两容量各400,007次旧状态／输出及245,760容量向量、524,288次实际FSM归纳转换，完整双率I2S22,532帧及12取消边界通过。周期和故障否决保持；首轮wall timeout保留，同binary／输入复跑成功。下一独立候选将重新封存这些来源，未预记新物理收益，仍未上板。

后续[APB routed精确映射审计](push2_workstation/usb_a/reports/DUAL138K_APB_ROUTED_INVERSE_AUDIT_20261031.md)补齐厂商INV→单输入反相LUT及M的唯一LUT2-AND启动拆分，不放行任意门。M10b／W9b真实VG、VO和W8旧VG各54项通过，负控分别45／46、36／38及34；两份far实际VO亦通过基线结构／SDC检查。旧v3证据、所有候选来源及失败日志保持不变，新v4审计器独立封口，完整时序与硬件仍未通过。

M10b／W9b及其各自新far变体现已完成[四套完整物理测量](push2_workstation/usb_a/reports/DUAL138K_M10_W9_PHYSICAL_20261031.md)：M默认setup2,741／hold1，far3,299／hold0；W默认setup9,520／hold2，far9,158／hold1。DDR保持3.500ns，far目标hold为M+0.714／W+0.577ns；六PLL等局部门通过，整机仍不可部署。四条真实50MHz专项报告暴露W的HCI同步长度判定长链，D输入运算仍为W首要同步瓶颈，已按这些实测开展局部修复；未上板，不预记收益。

W的[HCI池长度比较修正](push2_workstation/usb_a/reports/DUAL138K_HCI_POOL_COMPARE_20261031.md)已完成源码验证：先并行比较两个池上限，再选择单比特结果，三处句柄查询保留完整12位匹配。118,730周期完整旧版对照、270,336独立向量、全域符号证明及4个破坏负控通过，完整owner／event与native UART8E1／H5回归通过；不增加延迟或改变信用／错误优先级。新候选尚未综合／P&R，原候选证据保持封存，物理收益及硬件验收仍待实测。

W的[D精确组合运算改写](push2_workstation/usb_a/reports/dual138k_d_process_exact_20261031.md)通过3项全域证明、444,064组实际旧／新函数与独立整数比较及4个破坏负控；2294个完整效果帧保留原PCM／参数采样时刻。新增正式APB／CDC／I2S测试定位并修复[I2S源切换保护窗口](push2_workstation/usb_a/reports/dual138k_i2s_source_hold_20261031.md)：连续零值error槽计入明确source_error，真正缺样仍计underrun，保护期running／prefill不冒脉冲。双率逐bit测试及新旧数值整链均通过，1918个物理模型完成帧、1917个显示快照、12次PANIC一致；通用runtime与默认1028帧启动测试通过。此为离线正式链路验证，仍不等于真实蓝牙／HDMI像素／DAC或硬件验收。

两份DEMO新增[两处接收边界的四条精确约束](push2_workstation/usb_a/reports/DUAL138K_DEMO_BOUNDARY_CDC_20261031.md)，独立元数据固定helper身份；M10b／W9b实际VG／VO各6项测试及60负例通过，完整角色清单保留后级2ns及13个功能写指针的recovery／removal。旧两份与新M11／W10的prepare复验通过，17项来源与15项DEMO回归通过；未豁免同步reference48 hold。新M11／W10均全量综合完成，M11严格门通过并以`D2103115`启动完整P&R；W10严格门在USB packet RAM写许可布尔证明拒绝，失败日志保留，尚未进入物理实现，正在核对实际映射，未放宽门禁或上板。

M11／W10的[新候选来源与完整测量](push2_workstation/usb_a/reports/DUAL138K_M11_W10_CANDIDATES_20261031.md)已固定各822项锁、完整配置及588／645封存输入。M11 `D2103115`默认P&R已完成：物理CLS49,901、BSRAM235、DSP120，setup5,619／−3.762ns、hold1／−3.556ns，仍不可部署；recovery+3.349ns，原生VG／VO、边界VO和PLL子门通过。50MHz真实TF路径另有11条负报告路径，最差−0.766ns；正在分别修复音频配置资格重汇合及TF恢复长链。W10全量综合LUT＋ALU81,314／FF45,073／BSRAM equivalent257，严格门失败仍保持，未P&R或上板。

M11的新[far物理测量](push2_workstation/usb_a/reports/DUAL138K_M11_FAR_PHYSICAL_20261031.md) `D2103117`完整P&R完成：保持VG／SDC及3.500ns DDR要求，目标hold+0.706ns，整机hold0／+0.123ns、recovery+2.190ns、removal+0.278ns；setup仍3,331／−2.343ns，不可部署。六PLL与边界VO子门通过；far额外原生CLI因并行TF维护源码pin变化而拒绝，未冒记通过。原输入和失败日志保留，未上板。

按M11真实路径完成[音频启动许可的组合分解](push2_workstation/usb_a/reports/dual138k_effect_slot_admission_20261031.md)：效果模块提供只读存储空槽位，仅core_ce复用，完整外部ready及即时fault／clear／配置否决保留，不加流水或改变取参周期。全域native／legacy等价证明与4变异通过；115,929,947次边沿比较全部50公共输出和真实core_ce相等，48,691请求完整完成、48,645帧独立效果比较及双率正式I2S回归通过。生产源已冻结进入下一候选，未预记物理收益。

M11真实50MHz路径的[TF即时失败判定等价因子化](push2_workstation/usb_a/reports/DUAL138K_TF_FAILURE_FACTOR_20261031.md)已通过：完整epoch归约和并行失败谓词保留原错误优先级、physical及即时stop／invalidate；过程式默认0保留首个复位沿前的X语义，原连续表达式失败日志保留。99bit全域证明、四组合实际owner共1,069,069边沿／50公共输出／24状态组、4源码负控与完整stop／clear通过，独立四态审查通过。原生审计器仅更新已审TF source pin，M11实际VG／VO各54项回归及45／46负控通过；新源尚未物理验证，不转授旧far CLI或硬件通过。

新只读效果接口的[精确可逆来源适配](push2_workstation/usb_a/reports/DUAL138K_EFFECT_SLOT_LINEAGE_20261031.md)通过7项测试及完整native→prepared链，原D适配／manifest保持逐字节不变。第一次M12 prepare的身份拒绝保留；M12b `0af82c38b1902d92`从新锁prepare及588项复验通过，三项新RTL已核对确为实际编译消费来源，已启动全量综合。该阶段未预记综合／物理收益，未上板。

W10的[USB实际CEA共享组合证明](push2_workstation/usb_a/reports/DUAL138K_USB_SHARED_CEA_20261031.md)已修复旧frontier的NOR重汇合假反例：46真实门／44任意terminal精确BDD与独立SMT一致，19负控全拒绝，原13指针／实际写入增量及旧M／W直接证明保持。新外部完整严格门通过，原失败及VG／SDC输入不改，`D2103116`默认完整P&R已启动。M12b全量综合及严格门亦通过，实际消费新音频／TF源，`D2103118`默认完整P&R同时运行；新物理收益与硬件仍待测。

M12b／W10的[完整默认物理实现](push2_workstation/usb_a/reports/DUAL138K_M12B_W10_DEFAULT_PHYSICAL_20261031.md)均已完成：M12b `D2103118`物理BSRAM235／DSP120，setup3,340／−1.656ns、hold4／−3.457ns；W10 `D2103116`物理BSRAM293／DSP67.5，setup5,750／−5.583ns、hold2／−3.652ns。全部588／645封存输入及物理输入／输出复验，W10原生VG／VO及PLL子门通过；整机仍不可部署。已保持原3.500ns及完整VG／SDC派生各自far变体，另测结果。W录音发布至地址和HCI身份比较、M音频配置和TF DMA为下一轮真实路径修复对象，不预记收益。用户确认只有模拟器，真实手机A2DP／BLE／D模式和下载验收稍后；未上板，不改变T2-D1／D2状态。

针对W10实际50MHz长链的[HCI身份比较修正](push2_workstation/usb_a/reports/DUAL138K_HCI_IDENTITY_20261101.md)已完成：两维护模块使用完整12／16／32bit XOR归约，周期、优先级及信用owner不变。host RX／native旧版对照17,674／6,545周期，后者包括2,608个包RAM元素；全域关系与5新破坏负控、原13＋11业务负控及UART8E1／H5通过。固定W10输入不改，下一候选重新综合／P&R测收益，尚未上板。

M12b／W10的[far完整物理测量](push2_workstation/usb_a/reports/DUAL138K_M12B_W10_FAR_PHYSICAL_20261101.md)已完成，VG／完整SDC保持原字节和DDR3.500ns：M `D210311A` setup1,524／−1.299ns、hold0／+0.143ns；W `D2103119` setup5,532／−5.338ns、hold1／−0.063ns。目标DDR hold分别+0.624／+0.662ns；W剩余为midi_bytes的ack首级路径，尚未豁免或接受。两份M实际VO／SDC／PLL及W far各子门分别通过，整机仍不可部署，未烧录。下一候选继续消费已审源码修复，不把局部门或分时验证升级为声画／双板验收。

W10实际18级D输入控制路径的[PCM命令许可分解](push2_workstation/usb_a/reports/DUAL138K_PCM_CONTROL_ADMISSION_20261101.md)已完成：各操作复用相同校验但直接驱动其状态更新，原周期、采样、ID和末尾撤销优先级保留。7,811周期完整旧owner／512RAM对照、57bit许可证明、4负控和576四态组合通过，独立复核修复了首版未知strobes／ID差异；原8项含双率±2000ppm回归、描述符和正式D→完整效果→I2S／显示／PANIC仿真通过。新物理收益待整机候选测量，未上板。

W10录音同域长链的[已持有事务许可因子化](push2_workstation/usb_a/reports/DUAL138K_RECORDING_OWNED_TRANSFER_20261101.md)只改owner的两个输出门控，保留即时故障、write／response冲突、范围／超时及全部状态。全域证明、16,777,216四态组合、2,547半边沿旧owner对照和11必要负控通过，原raw store与44项DDR队列／桥接回归通过；top分配负控的include cwd缺陷已纠正，原失败保留。未改SDC或预记物理收益。新W11 `bafd43c180d52b1c`已从822项锁prepare、645封存输入复验，四份新维护RTL确被实际编译消费，17项来源／15项DEMO回归通过，正全量综合；未上板。

M12b实际TF占用路径的[晚许可并行运算](push2_workstation/usb_a/reports/DUAL138K_TF_PARALLEL_OCCUPANCY_20261101.md)已修改维护DMA，保留原容量、回绕、周期及restart／hold优先级。两容量各400,008模块检查、有限四态16,384向量及89自由位三项等价关系通过，8类负控拒绝、四组真实ring oracle通过；新源尚待新M候选封存、综合及P&R。这里不预记时序或资源收益，未进行SRAM或Flash操作。

M12b far实际chorus长链的[44.1k精确组合替换](push2_workstation/usb_a/reports/dual138k_chorus_affine44_20261101.md)已完成：双率全部131,072实际函数输入、完整旧新模块3,026,811半周期对照、8项chorus和16项完整效果链回归通过。仅44.1k tap运算改为精确乘加／移位，48k、取样周期及效果行为保持；原来源链可逐字节逆向还原。新源等待M新候选物理测量，W11封存输入不变，无资源收益或硬件通过声明。

W11全量综合与[严格角色门禁修复](push2_workstation/usb_a/reports/DUAL138K_DEMO_BOUNDARY_ROLE_20261101.md)已通过：FF45,091、LUT54,836、ALU14,096、BSRAM equivalent257。首次门禁把663端点DMA映射误判为M，失败保留；现将DMA完整映射和USB完整queue角色分开，原两份完整清单及全部pin／clock／SDC检查不放宽，61负控拒绝，旧W10／M12b兼容复验通过。W11新严格门全通过，默认 `D2110101` 完整P&R正在运行，物理资源／时序未测得，未上板。

M实际配置广播长链的[局部组合简化](push2_workstation/usb_a/reports/DUAL138K_CONFIG_BROADCAST_20261101.md)已通过全域二态证明、81,920有限四态向量、115,929,947半周期完整服务旧新对照及真实APB／I2S／FFT控制仿真。公开ready／采样周期不变，engines／effects共用一个接受广播。两份822来源锁已刷新；M13 `eae1eec8001e068f`已prepare并核实588封存／261启用输入确消费新广播、chorus和TF DMA，正全量综合。默认编译器失败保留，显式同M12b工具链重试通过；尚无新物理或硬件接受结论。

M13综合与完整strict来源／功能／角色／CDC门已通过；三个旧TF网表负控因综合LUT名变化而报错，已[改为真实消费者唯一绑定](push2_workstation/usb_a/reports/DUAL138K_NATIVE_MUTANT_BINDINGS_20261101.md)，原审计oracle不变。M13／M12b／W10／W11各54项回归及全部实际负控通过，旧失败保留；不改变封存编译输入。M13 `D2110103`默认P&R已完成，完整物理证据正在封存，仍不能作为硬件接受。

W11的[默认／far完整物理证据](push2_workstation/usb_a/reports/DUAL138K_W11_PHYSICAL_20261101.md)已封存：`D2110101`物理CLS52,251／BSRAM293／DSP67.5，setup6,423／−5.018ns、hold2／−3.675ns；`D2110102` setup6,394／−4.648ns、hold11／−0.585ns，原DDR3.500ns路径余量+0.673ns。两次实际VO、完整边界和官方PLL子门独立通过，整机时序仍失败。余下参考时钟同域hold未豁免；PCM／HCI分组比较及录音START局部修复正按实际路径推进W12。只读JTAG仍为单块 `C11028E5`，无外部HDMI／线路音频采集，未烧录，未将模拟器或单板计为无线／双板验收。

W11最差PCM路径的[physical epoch四组比较](push2_workstation/usb_a/reports/dual138k_pcm_physical_groups_20261101.md)已实施并验证。实际VG／VO证实原32位XOR仍被映射为NE串行carry；现仅该比较用四组8位 `syn_keep` net，其余许可和位图清理优先级不变。完整64位二态／128符号位四态证明、1,536实际四态向量、完整owner对照及默认双率漂移、正式D APB→I2S回归均通过。新owner `3342a94c…cff837`等待W12实际编译及物理测量，不预记收益。

W11真实50MHz长链的[HCI比较分组](push2_workstation/usb_a/reports/DUAL138K_HCI_KEPT_GROUPS_20261101.md)已完成：仅将先后串行的12位handle和32位generation比较加入8位组保留边界，原last-match、默认值、信用／租约及周期不变。完整host／native旧新模块、原160,228／268业务检查、全部原及新增负控、二态全域关系与4,504次有限四态比较通过，真实UART8E1／H5仿真通过。两份新维护源等待W12实际消费，是否阻止carry重建及真实路由收益仍待综合／P&R检查。

W11参考时钟同域hold的[显式区域派生入口](push2_workstation/usb_a/reports/dual138k_reference_monitor_regions_prepare_20261101.md)已通过39项floorplan回归及5项真实父输入负控。按实际VO固定48／44参考monitor各32位binary＋32位Gray，共128FF，第三selected不改；仅追加区域CST，原VG／完整SDC／IO／DDR远区及3.500ns要求保持。`D2110105`已从完整实测W11far父派生并启动全量P&R，新VO／PLL／时序及收益待测，不升级为硬件接受。

M13的[默认／far完整物理证据](push2_workstation/usb_a/reports/DUAL138K_M13_PHYSICAL_20261101.md)已封存：两次物理BSRAM235／DSP119；默认`D2110103` setup6,958／−3.133ns、hold1／−3.489ns，far`D2110104` setup6,490／−2.943ns、hold0／+0.135ns，原DDR3.500ns余量+0.579ns。完整VG／SDC保持、84份证据及588封存输入复验，各实际VO／边界／六PLL子门通过；相较M12b far的setup回退如实保留，仍不可部署。按新实测控制锥继续局部修复，未上板，不转授硬件或双板通过。

W11真实录音长链的[START宽初始化许可因子化](push2_workstation/usb_a/reports/DUAL138K_RAW_START_20261101.md)已完成：仅在已知memory_quiescent时使用精确fault cofactor，完整故障／超时／隔离和START原周期、四态及CLEAR优先级保持。完整旧新owner661,577边沿、16,777,216四态方程、4,114非法／任意状态单沿及7专项负控通过，raw／owner8／native DDR／正式BLE业务回归均通过。唯一生产raw-store来源pin同步并拒绝漂移；新RTL`214c0a5d…09da1d`已进入W12封存输入，物理收益待测，未上板。

参考monitor单行区域试验`D2110105`的[完整物理结果](push2_workstation/usb_a/reports/dual138k_reference_monitor_regions_physical_20261101.md)已封存：setup7,024／−5.878ns、hold18／−0.487ns，未闭合。44.1k参考hold清零，但48k增至18；同排目标FF仍有1.110ns fabric clock偏斜。保持父VG／SDC及DDR3.500ns（实测+0.679ns），完整VO／边界／PLL子门和前后hash通过；该区域不作为W12默认，不预记收益，未上板。

W12 `13266a0d74cad8e8`已从两份更新后的822项锁完成[prepare／全量综合及严格门](push2_workstation/usb_a/reports/DUAL138K_W12_PREPARE_SYNTHESIS_20261101.md)：951来源快照、645封存／284启用输入复验，实际消费PCM／HCI分组、raw START及M13共享audio。综合FF45,092／LUT55,357／ALU14,093／BSRAM equivalent257，完整strict通过；来源17／DEMO审计15／策略7回归通过，旧非DEMO profile漂移失败如实保留。实际分组网表与新`D2110106`物理实现另验，不继承D105区域、时序或硬件接受，未上板。

M13实际音频控制长链的[事件配置私有cofactor](push2_workstation/usb_a/reports/DUAL138K_EVENT_CONFIG_COFACTOR_20261101.md)及TF读许可／容量的[并行比较分组](push2_workstation/usb_a/reports/dual138k_tf_threshold_groups_20261101.md)已实施并通过完整旧新整模块、正式I2S RTL、全域／四态与负对照验证，实际采样、广播及取消周期保持。两份822来源锁各仅更新四项来源；M14 `0e7a7f996619ed83`已完成[完整来源冻结与prepare](push2_workstation/usb_a/reports/DUAL138K_M14_PREPARE_20261101.md)，875来源快照／588封存／261启用输入逐项核验实际消费新两audio和TF RTL，已开始全量综合。分组是否实际保留、routed资源／时序及硬件另验，不预记收益；基础M仍不含CNN，未上板。

W12的[实际分组与默认完整物理审计](push2_workstation/usb_a/reports/DUAL138K_W12_AUDIT_20261101.md)已封存：16个PCM／HCI分组经真实primitive函数证明全部UNSAT，实际32位串行比较未跨分组重建；raw仅确认122FF／5CE实际映射，不冒称额外完整网表等价。`D2110106`物理BSRAM293／DSP66.5，setup6,428／−4.350ns、hold5／−3.239ns，recovery／removal已正；实际VO／边界及六PLL子门独立通过，整机时序仍失败。保持原VG／完整SDC／DDR3.500ns，仅追加两条DDR远区约束的`D2110107`已启动全量P&R，未预填结果、未上板。

M14已完成[全量综合和严格门](push2_workstation/usb_a/reports/DUAL138K_M14_SYNTHESIS_20261101.md)：综合FF46,932／LUT52,153／ALU12,875／BSRAM equivalent195，native实际VG54项（50通过／4跳过）及45负控、边界7项及61负控通过。实际TF full四组与final函数已保留，但函数内容量只有最低组保留，[完整实际锥审查](push2_workstation/usb_a/reports/dual138k_m14_tf_groups_vg_20261101.md)明确分组目标部分失败，不冒称物理收益。1207工具／源码／测试输入冻结复验，`D2110108`重新严格审计后已启动完整P&R，硬件与CNN仍未验收。

W12 `D2110107`的[完整far物理对照](push2_workstation/usb_a/reports/DUAL138K_W12_FAR_20261101.md)已封存：保持VG／完整SDC／DDR3.500ns，原DDR hold实测+0.672ns，全局hold0违例／+0.085ns；setup却回退至7,373／−5.845ns，整机时序仍失败。物理BSRAM293／DSP66.5／CLS52,488，实际VO54项（41通过／13跳过）及36负控、边界7／61、官方六PLL及7负控通过，32份物理文件与父／来源前后稳定。新PCM key及raw许可修复另属下一候选，不转授本位流接受；未上板。

W12真实长链的[PCM key／COMMIT修复](push2_workstation/usb_a/reports/DUAL138K_PCM_KEY_COMMIT_20261101.md)及[raw START显式case](push2_workstation/usb_a/reports/DUAL138K_RAW_START_CASE_20261101.md)已通过完整旧新owner、全域／四态、正式回归及破坏负控；PCM默认双率漂移共230.4万帧、raw实际fault四态1677万组合通过。两份822来源锁各仅更新三项，W13 `bc065b3de8977725`已完成[完整来源冻结与prepare](push2_workstation/usb_a/reports/DUAL138K_W13_PREPARE_20261101.md)：951原始来源、645封存／284启用输入及1365审计输入逐项核验，来源17／DEMO15／策略7通过，已启动全量综合。真实分组／许可映射及物理收益另验，不继承W12时序结果；未上板，真机无线验收继续待实机。

M14 `D2110108`已完成[默认完整物理审计](push2_workstation/usb_a/reports/DUAL138K_M14_DEFAULT_PHYSICAL_20261101.md)：物理BSRAM235／DSP119／CLS50,306，setup3,764／−1.940ns、hold1／−3.453ns，recovery+1.603／removal+.278ns。native实际VO54项（51通过／3跳过）及46负控、边界7／61、官方六PLL及7负控通过，30份物理文件、588staged及1207冻结审计输入稳定；仍因STA失败不能部署。同VG／完整SDC／DDR3.500ns的`D2110109`远区对照已启动全量P&R，不预填结果；M基础CNN、完整实板声画及双板并发仍未验收。

W13已完成[全量综合与严格门](push2_workstation/usb_a/reports/DUAL138K_W13_SYNTHESIS_20261101.md)：FF45,092／LUT55,249／ALU14,135／BSRAM equivalent257，实际VG native54项（40通过／14跳过）及35负控、边界7／61通过。951原始来源、645staged及1365冻结审计输入复验，默认physical prepare重新完整审计并与CLI深等价，`D211010A`已启动全量P&R；实际PCM／raw映射目标另审，不预记物理收益，未上板。

M14 `D2110109`已完成[far完整物理对照](push2_workstation/usb_a/reports/DUAL138K_M14_FAR_PHYSICAL_20261101.md)：同VG／完整SDC／DDR3.500ns，原DDR hold+0.620ns，全局hold0／+0.135ns；setup却回退至4,251／−2.526ns。物理BSRAM235／DSP119／CLS50,303，实际VO54项（51通过／3跳过）及46负控、边界7／61、官方六PLL及7负控通过，32物理文件、1207冻结审计及588staged输入稳定。仍未闭合、未上板，后续M15独立验证，不转授本位流接受。

TF容量比较已按[精确维护源阶段](push2_workstation/usb_a/reports/dual138k_tf_capacity_module_groups_20261101.md)移至五个模块级kept标量，同一函数原bit0准入、任意两入参和modulo oracle保持；完整occupancy14runs／threshold8runs及native runtime、全部负控通过。两份来源锁各仅更新该DMA一项，M15 `cf9d6319a310d6fe`完成[来源准备](push2_workstation/usb_a/reports/DUAL138K_M15_PREPARE_20261101.md)：875原始来源、588staged／261启用及1365审计输入复验，已启动全量综合。M14分组部分失败保持，新五节点的实际live fanin及物理收益仍须另验，未上板。

W13 `D211010A`的[默认完整物理测量](push2_workstation/usb_a/reports/DUAL138K_W13_DEFAULT_PHYSICAL_20261101.md)已封存：物理BSRAM293／DSP66.5／CLS52,540，setup6,829／−5.765ns、hold3／−3.537ns，recovery+2.468／removal+.281ns。native实际VO54项（41通过／13跳过）及36负控、边界7／61、官方六PLL及7负控通过，30物理文件、645staged与1365冻结审计输入稳定。最差转至raw memory_next_index CE，未将局部映射变化冒充全局收益；同VG／SDC／DDR3.500ns的`D211010B`far已启动P&R，仍未上板。

M15已完成[全量综合及严格门](push2_workstation/usb_a/reports/DUAL138K_M15_SYNTHESIS_20261101.md)：FF46,932／LUT52,130／ALU12,875／BSRAM equivalent195，native实际VG54项（50通过／4跳过）及45负控、边界7／61通过。875原始来源、588staged及1365冻结审计输入复验，默认physical prepare重新完整审计且与CLI深等价，`D211010C`已启动全量P&R；新TF分组的专项实际消费锥证明另记，不预填routed收益，未上板。

W13的[PCM真实primitive及消费证明](push2_workstation/usb_a/reports/DUAL138K_W13_PCM_MAPPED_20261101.md)已完成：20组8位key、完整160对FF比较、实际rejected COMMIT作用锥和531个真实next-Q（含512bitmap）共37项UNSAT，25项实际网表破坏均给SAT反例。官方primitive二态方程与实际formal/publisher逐位绑定另核；59份证据、951prepare／645staged／1365冻结输入重验。范围仅限所列mapped函数／更新，不升级为全owner形式化、时序、无线或声画实板验收。

M15的[TF容量真实分组与准入锥证明](push2_workstation/usb_a/reports/dual138k_m15_tf_capacity_vg_20261101.md)已通过：五个模块级kept标量全部具备精确独立FF support且真实进入最终capacity／write准入锥，38个任意available／pending FF的原mod32容量式与实际primitive函数UNSAT等价。7项保留旁路节点但破坏真实consumer／INIT的负控全部给SAT反例；实际ALU模型与官方9模式288项核对通过。588staged／1365冻结输入和独立封存重验，M14部分失败记录保持；该专项成功仍不代表routed时序或实板声画通过。

W13的[raw完整实际映射比较](push2_workstation/usb_a/reports/DUAL138K_W13_RAW_MAPPING_20261101.md)已封存：122目标FF／127完整D与CE锥、449实际状态／RAM／DDR边界逐项绑定，在报告明确的配对条件下全部有效next-Q为UNSAT；4项实际网表破坏均给SAT反例，官方LUT4800／ALU1152及RAM模型交叉检查通过。主要write-address CE退出64个timeout叶，其余CE保留；最差memory_next_index的CLEAR完成许可仍经过完整fault链。未证明异步reset／RAM历史／DDR内部或全机四态，不冒称全部初始化已短化、routed收益或实板验收；下一cache提案保持原CLEAR周期与优先级。

W 的[HCI readiness 局部 drift 维护源阶段](push2_workstation/usb_a/reports/DUAL138K_HCI_ACTION_DRIFT_20261101.md)已完成：仅三个已有断开否决的 readiness consumer 使用 action fence，原 full drift、全部顺序逻辑及 X/Z fallback 保持。完整 host 对照17,674周期／33输出／39状态、147,464次有限四态探针、六项二态／四态SMT、原W10及UART8E1／H5回归和全部负控通过；359份最终证据由主线程逐项重验。两份DEMO来源锁尚未刷新，此阶段不混入W13／M15冻结输入；下一完整候选另立身份并检查真实consumer及物理时序，未预记资源收益，未上板。

M15 `D211010C` 的[默认完整物理实现](push2_workstation/usb_a/reports/DUAL138K_M15_DEFAULT_PHYSICAL_20261101.md)已封存：物理BSRAM235／DSP119／CLS50,186，setup3,590／−1.914ns、hold1／−3.478ns，recovery+3.239／removal+.275ns。实际VO54项（51通过／3跳过）及46负控、边界7／61、官方六PLL及7负控均通过；30物理文件、588staged／1365冻结输入及683PLL依赖重验。最差chorus、事件准入与TF容量消费仍须修复，未将源码证明当作时序闭合；同VG／完整SDC／原DDR3.500ns的`D211010D`far已启动P&R，未上板。

W13 `D211010B` 的[far完整物理对照](push2_workstation/usb_a/reports/DUAL138K_W13_FAR_PHYSICAL_20261101.md)已封存：同VG／完整SDC／DDR3.500ns，仅追加两条区域约束，物理BSRAM293／DSP66.5／CLS52,497，setup6,750／−5.562ns、hold0／+.135ns，原DDR路径+.473ns。recovery+2.202／removal+.281ns；真实VO54项（41通过／13跳过）及36负控、边界7／61、官方六PLL及7负控通过；32物理文件、645staged／1365冻结输入及915PLL依赖重验。50MHz端点823／TNS−1515.549ns，仍未闭合；far最差fetch_address CE不在CLEAR赋值块内，后续局部修改不预记其收益。未上板，保持两套原失败证据。

完整显示的[waveform smooth CSA维护阶段](push2_workstation/usb_a/reports/DUAL138K_WAVEFORM_SMOOTH_CSA_20261101.md)已完成：仅替换原平滑函数，无新增状态／周期，保留原33bit舍入溢出。独立二态及X/Z known-mask证明、三个算术破坏负控、两个INPUT_REGISTERED配置各1,067,717实际函数探针／44,000完整capture时钟和六个实际source负控通过；metadata minor0／minor1与真实wave／FFT／XY、owner8 display runtime及三种完整HDMI elaboration通过。205份最终证据逐项重验；M15缺owner8库存的失败尝试原样保留、使用实际含该输入的W13 support后通过。两锁尚未刷新，旧冻结输入不变，未预记资源／时序收益或实板声画验收。

M15 `D211010D` 的[far完整物理对照](push2_workstation/usb_a/reports/DUAL138K_M15_FAR_PHYSICAL_20261101.md)已封存：同VG／完整SDC／DDR3.500ns，原DDR hold+.619ns、全局hold0／+.143ns；setup仍3,081／−1.774ns，recovery+.686／removal+.281ns。物理BSRAM235／DSP119／CLS50,221，实际VO54项（51通过／3跳过）及46负控、边界7／61和官方六PLL／7负控均通过。32物理文件、588staged／1365冻结输入和685PLL依赖复验；chorus、oscillator准入及TF容量仍有真实长链，下一来源候选独立验证，不继承接受，未上板。

原生音频的[采样准入同周期cofactor维护阶段](push2_workstation/usb_a/reports/DUAL138K_AUDIO_SAMPLE_ADMISSION_20261101.md)已完成：仅core_ce组合表达式使用实际dispatch互斥和已有quiescence，保留全部取消／配置／fault／效果栅栏及X/Z原表达式，无状态／周期变化。二态／四态证明及负控、M完整50输出／31内部边界115,929,947半周期、48,691请求与48,645帧独立湿声模型通过；W／legacy和原event／effect门全部通过，warning数量按实记录。89份最终证据重验，另将157项当时输入以内容hash保存到`audio-core-ce-maintained-input-snapshot-v1`（snapshot SHA `28b10a0359f0d4a215ac2cb9104c8e1b88ad9a844c03ac522245693ac76c73eb`），后续chorus演进不改本阶段证据。两锁待统一刷新，未预记实际映射／资源／routed收益或硬件验收。

W的[raw CLEAR完成许可维护阶段](push2_workstation/usb_a/reports/DUAL138K_RAW_CLEAR_CASE_20261101.md)已完成：实际源码`39ae3b91…290b`仅新增组合许可并替换原CLEAR guard，全部NBA位置／右值／顺序及原fault／超时保留。二态UNSAT、16,384四态guard、16,777,216实际fault组合、661,577完整twin边沿、36定向／4096任意四态及4负控通过；旧W11／W12 START门以严格CLEAR逆变换继续全通过，未改旧fixture或16项helper。原raw、BLE完整对象／协议／27负控、authority及来源17项回归通过，唯一生产raw pin同步。54实际输入、331证据和48个内容hash快照blob重验；两锁待统一刷新，CLEAR实际映射／资源／routed收益另验，far最差fetch_address CE不在本赋值块内，未上板。

Chorus的[35bit CSA维护阶段](push2_workstation/usb_a/reports/DUAL138K_CHORUS_AFFINE35_CSA_20261101.md)已完成：仅组合rate_delay函数改为五层CSA和一次末级加法，48k分支、状态／周期／取参及四态传播保持。全16bit实际函数／独立SMT、278,664四态探针与完整双实例通过；原实际延迟131,072穷举、chorus10项／effects16项及全部来源／算术负控通过。150份最终证据和40输入版本／38内容对象由主线程逐项重验。两份DEMO来源锁待统一刷新，M15／W13冻结旧源码不变；下一候选另测实际映射、资源与routed时序，本阶段无板卡操作或收益预记。

M16／W14已完成[完整来源准备及全量综合](push2_workstation/usb_a/reports/DUAL138K_M16_W14_PREPARE_20261101.md)：两锁各822项仅更新10个来源hash，配置／库存不变，来源17／DEMO15／策略7项通过；875／951原始来源、588／645staged及各1374冻结审计输入复制后逐项复验。两综合退出0，LUT＋ALU66,462／71,057、BSRAM equivalent195／257，不能预记物理收益。M16 `5f5ba9978313e96b`严格门通过并以`D2110110`启动全量P&R；W14 `df8c9ba4d32507f1`完整门因watchdog_fault消费者清单漂移拒绝，初次失败保留，核对实际映射前不进入P&R。旧M15／W13来源不变，未上板，声画、CNN、长录音、手机真机及双板验收仍未完成。

TF的[响应选路cofactor维护阶段](push2_workstation/usb_a/reports/DUAL138K_TF_RESPONSE_COFACTOR_20261101.md)已完成：只在最终write_selected处选择两个同周期占用候选，保留原X/Z回退及全部NBA／容量分组。实际源143任意位四项UNSAT／四项SAT负控、1048576四态向量／六新源码负控、旧occupancy14／threshold8及完整service／stop／clear回归通过；229份最终证据由主线程逐项重验，来源17项再过。维护源`3f9eb8af…e7b6`未混入M16／W14冻结输入，两锁保持旧pin待下一候选升级；共享app_rdy仍可能带入上游写许可，不预记真实网表／资源／时序收益，未上板。

M16 `D2110110` 的[默认完整物理结果](push2_workstation/usb_a/reports/DUAL138K_M16_DEFAULT_PHYSICAL_20261101.md)已封存：物理BSRAM235／DSP119／CLS50,976，setup529／−1.222ns、hold1／−3.445ns，recovery+.523／removal+.281ns，仍未闭合。四条clk50实测+2.282／+.181／+.860／−3.445ns；最差为已有握手payload的跨域路径，相关窄CDC正核对，同域残余负路径保持。实际VO54项（50通过／4跳过）及45负控、边界7／61、官方六PLL／7负控通过；30物理文件及2937份证据逐项重验，含1374冻结工具／588staged／875prepare来源。同VG／完整SDC／DDR3.500ns的`D2110111` far已启动P&R，未预记结果，未上板。

W14的[DMA fault精确D／CE映射审计修复](push2_workstation/usb_a/reports/DUAL138K_W14_BOUNDARY_WPTR_MAPPING_20261101.md)已完成：三fault各663端点只有wptr0由D移到CE，完整10个真实FF输入／实际LUT的reset-inclusive next-Q等价，不假设状态可达；新增功能门拒绝保留closure却删故障veto的负控。旧／新八套完整回归通过，其中三套新7项／69负控；原helpers／SDC保持，86实际输入／53内容blob／96证据由主线程逐项重验，M16 VG／VO独立正控通过。原W14 v1失败不改，另立v2完整1374冻结审计输入（仅新helper）后同一VG strict／physical prepare通过；v3仅更新新test，未混入新TF。`D211010E`已完成全量P&R、六组物理审计进行中，资源／STA另记，不预填物理或硬件接受，未上板。

W14 `D211010E` 的[默认完整物理结果](push2_workstation/usb_a/reports/DUAL138K_W14_DEFAULT_PHYSICAL_20261101.md)已封存：物理BSRAM293／DSP66.5／CLS53,327，setup7270／−5.434ns、hold1／−3.538ns，recovery+2.618／removal+.278ns，仍未闭合。最差已到raw memory_failure及completion_generation CE，保留即时owner8 fault和错误优先级；四条clk50报告−4.967／+.180／−4.967／−3.538ns。实际VO54项（40通过／14跳过）及35负控、边界7／69、官方六PLL／7负控通过；30物理文件及3246证据逐项重验，含v3精确两文件外部审计、1374冻结／645staged／951prepare来源。原v1失败及候选输入不改，同VG／完整SDC／DDR3.500ns的`D211010F` far已启动P&R；未上板，仍非合格演示镜像。

M16 `D2110111` 的[far完整物理对照](push2_workstation/usb_a/reports/DUAL138K_M16_FAR_PHYSICAL_20261101.md)已封存：同VG／完整SDC／DDR3.500ns，仅两条远区CST，原DDR hold+.682ns、全局hold0／+.123ns；setup仍583／−1.221ns，recovery+1.745／removal+.278ns。物理BSRAM235／DSP119／CLS51,028；四条clk50+2.223／+.123／+.792／+.123ns。实际VO54项（50通过／4跳过）及45负控、边界7／61、官方六PLL／7负控通过；32物理文件、2939证据（1374冻结／588staged／875prepare／685PLL依赖）逐项重验。仍有真实同域负路径与待核对的握手跨域约束，未闭合、未上板，不转授演示或双板接受。

W14 `D211010F` 的[far完整物理对照](push2_workstation/usb_a/reports/DUAL138K_W14_FAR_PHYSICAL_20261101.md)已封存：同VG／完整SDC／DDR3.500ns，仅两条远区CST，原DDR hold+.667ns、全局hold0／+.106ns；setup仍6909／−5.058ns，recovery+2.469／removal+.278ns。物理BSRAM293／DSP66.5／CLS53,291，四条clk50−4.734／+.140／−4.734／+.140ns；最差到raw memory_generation CE。实际VO54项（40通过／14跳过）及35负控、boundary7／69、官方六PLL／7负控通过；32物理文件与3248证据逐项重验。整机时序未闭合，未上板，仍非合格演示镜像；继续实际RTL控制锥修复，不将模拟器或单板分时升级为无线／双板接受。

TF 的[available响应计算维护阶段](push2_workstation/usb_a/reports/DUAL138K_TF_AVAILABLE_RESPONSE_20261101.md)已完成：仅提前计算delayed／full／partial占用结果，原周期、所有NBA及accepted cofactor保持；未知值回原helper，不假设pending等于32或available。三项48自由位UNSAT、2,097,152四态及三新负控，旧response7／occupancy14／threshold8和真实service／clear／stop、来源17项通过；309产物及四维护文件由主线程逐项重验。新源`1baa7146…25e7`已进入独立M17／W15准备输入，旧M16／W14不改；综合／物理收益待测，未上板。

W 的[global failure末级选择维护阶段](push2_workstation/usb_a/reports/DUAL138K_RAW_GLOBAL_FAILURE_CASE_20261101.md)已完成：仅最后memory_failure同位置NBA使用精确cofactor，保留即时owner8故障、sticky guard、错误优先级及X/Z合并；lower写入、channel／cancel和32bit completion不变。任意prior nextQ证明、1024／262144四态、661577旧新twin、35定向＋4096任意状态及6负控通过；原CLEAR／两START和raw／BLE／DDR／owner／authority／来源回归保持。主线程重验526证据与7维护源，首轮负控构造失败和格式版本区别保留；新raw`b654b55a…3809`及唯一pin已进入W15独立输入，不预记物理收益，未上板。

M／W 的[PC／APB既有握手窄约束维护阶段](push2_workstation/usb_a/reports/DUAL138K_DEMO_HELD_HANDSHAKES_20261101.md)已完成：显式DEMO v2实际SDC增加10行，PC8／APB49bit held请求保持13.020ns有限setup、仅hold豁免，三个toggle仅首级cut及后级2ns；旧APB响应／PC ACK保持。严格综合及物理入口均门检真实closure和全网表selector，16项／100负控及旧v1兼容通过；物理单测2项旧失败已隔离HEAD复现并保留。实际PC仍power-up-only，不把模块reset仿真升级为warm-reset。新M17／W15已实际选择，资源／routed时序另验，未上板。

M17／W15 的[完整来源、综合与VG检查点](push2_workstation/usb_a/reports/DUAL138K_M17_W15_PREPARE_20261101.md)已完成：各822项锁仅更新8条hash，配置／库存保持；875／951原始来源、588／645staged及各1381冻结审计输入逐项复验。综合LUT＋ALU66,380／71,074、BSRAM equivalent195／257；两套严格门／原生CLI通过，原生58项分别53通过5跳过／42通过16跳过及68／57负控，边界各7项／69负控通过。主线程重读4655证据，prepare seal v2仅更正“综合开始时刻”的说明、原v1保留，候选字节不变。`D2110112`／`D2110114`默认完整P&R已启动，资源／routed时序另记；未上板，不转授声画或无线／双板接受。

M17 `D2110112` 的[默认完整物理结果](push2_workstation/usb_a/reports/DUAL138K_M17_DEFAULT_PHYSICAL_20261101.md)已封存：物理BSRAM235／DSP119／CLS50,863，setup3821／−1.945ns、hold1／−3.392ns、recovery+2.571／removal+.278ns，仍不可部署。最差为config_accept_pending同域反馈，TF available→accepted仍−1.824ns；四张clk50报告+.393／+.183／+.393／−3.392ns。原生VO58项55通过3跳过及71负控、边界7／69、官方六PLL／7负控和held-v2物理入口通过；主线程逐30物理／2947证据重验，子门不转授完整时序或硬件。原VG／完整SDC／DDR3.500ns的`D2110113` far另测；未上板，仍待真实声画。

W15 `D2110114` 的[默认完整物理结果](push2_workstation/usb_a/reports/DUAL138K_W15_DEFAULT_PHYSICAL_20261101.md)已封存：物理BSRAM293／DSP66.5／CLS53,325，setup5935／−4.089ns、hold1／−3.454ns、recovery+1.685／removal+.278ns。最差已变为DDR复位反馈至raw failure／return_data及delay欠载至PCM written；四张clk50报告−3.340／+.132／−3.340／−3.454ns。原生VO58项44通过14跳过及60负控、边界7／69、官方六PLL／7负控与held-v2实际入口通过；主线程逐30物理／3253证据重验，整机仍不可部署。原VG／完整SDC／DDR3.500ns的`D2110115` far另测；唯一对象仍64KiB，未上板，声画／无线／双板均未验收。

M17／W15 的[far完整物理对照](push2_workstation/usb_a/reports/DUAL138K_M17_W15_FAR_PHYSICAL_20261101.md)已封存：`D2110113`／`D2110115`保持原VG／完整SDC／DDR3.500ns，仅两远区CST；目标hold+.565／+.679ns，全局hold0／+.134和0／+.151ns。setup仍2614／−1.767ns及6813／−4.798ns；M最差配置反馈／TF read_buf，W最差raw failure／token及PCM written，完整STA未闭合。各58项原生回归及71／60负控、边界7／69、官方六PLL／7负控与held-v2入口通过；主线程分别逐32物理／2949及3255证据重验。W far的setup比默认更差，未预记整体收益；未上板，不转授声画／双板接受。

M 的[公开配置就绪维护阶段](push2_workstation/usb_a/reports/DUAL138K_PUBLIC_CONFIG_READY_20261101.md)已完成：仅明确持有配置请求时采用既有广播cofactor，其他及X/Z回原表达式，状态／周期／事件与采样许可保持。全域二态、M/W各1792四态及5实际负控、原样完整M/W/legacy模块88191／88191／88223半周期和六项旧回归通过；主线程逐121证据／159输入及10源快照重验。新event `b689d16f…c1a6`待下一候选实际消费，旧M17/W15输入不改，不预记资源或时序收益，未上板。

W 的[DDR返回邮箱私有预装维护阶段](push2_workstation/usb_a/reports/DUAL138K_RETURN_MAILBOX_PRELOAD_20261101.md)已完成：299bit私有payload仅在非pending时预装，原完整fault／同拍cancel guard及发布／ACK周期保持，无新增寄存器；未发布私有值可不同。665528完整／定向边沿、5实际负控和raw／BLE对象／nativeDDR／owner／authority及四旧证明通过；主线程复验8维护源、597证据和72输入版本／58blob。首轮测试锚点失败保留，修复未改旧proof函数；raw `d2e39654…c38d`及唯一pin待新候选消费，窄failure／token仍需实测，不预记收益，未上板。

W 的[PCM位图清理维护阶段](push2_workstation/usb_a/reports/DUAL138K_PCM_BITMAP_GATE_20261101.md)已完成：4×128bit written独立唯一写入，原写窗／START／COMMIT／末尾撤销优先级及其余151条NBA保持；默认0过程式保留X/Z。7217整owner周期、1048576有限四态及3＋5实际负控、原8项长漂移／许可／描述符／正式D→完整效果→I2S显示回归通过；旧描述符负控锚点正式修复，原失败保留。主线程复验308证据、5维护源及102输入版本；owner `574c6e26…b71e`待新候选消费，未预记资源或时序收益，未上板。

M 的[TF私有读缓冲预装维护阶段](push2_workstation/usb_a/reports/DUAL138K_TF_PRIVATE_READ_PRELOAD_20261101.md)已完成：仅非valid时预装read_buf，原response发布／指针／周期及其余NBA保持；X/Z回原分支。pending/valid互斥等6项源绑定二态归纳、双容量各737280实际模块四态边沿／4源码负控、旧cofactor→occupancy／threshold及真实service／clear／stop全链通过；有效payload边界明确，旧逆变换门不放宽。主线程重验288维护产物／54输入／10源及3696提案产物，三次历史fixture失败保留；DMA `5fc0fd09…ef3f`已被M18/W16 prepare实际消费，综合与物理另记，不预记收益，未上板。

M18/W16 的[完整prepare／综合及VG检查点](push2_workstation/usb_a/reports/DUAL138K_M18_W16_PREPARE_20261101.md)已完成：各822项锁仅更新6条hash，875／951原始来源、588／645staged及各1395冻结工具逐项复验，实际消费四项维护RTL。综合FF46932／45092、LUT53840／57259、ALU12537／13802、BSRAM equivalent195／257；原生58项分别53／42通过、68／57负控，边界各7／69通过。主线程重读4680证据；M实际VG确认available→256 read_buf CE闭包退出、深度14→2，但CE扇出仍256，routed收益另测。`D2110116`／`D2110118`默认全量P&R已启动；W专门返回邮箱CDC覆盖仍另查，不转授完整CDC／声画或硬件接受，未上板。

W16 的[实际返回邮箱CDC覆盖缺口](push2_workstation/usb_a/reports/DUAL138K_W16_RETURN_MAILBOX_CDC_GAP_20261101.md)已确认：296实际payload CE冻结、pending／ACK／同步链及9项真实布尔关系通过，但原SDC只覆盖296直接D对，漏32×301＝9632资格路径，完整覆盖明确失败。cache精确10ns＋匹配held hold候选覆盖9928／9928、13负控全拒，尚未安装；主线程独立复验。正维护显式W新政策与实际网表门，冻结W16及其P&R仅保留测量身份，不转授CDC／硬件接受，未上板。

W16 `D2110118` 的[默认完整物理结果](push2_workstation/usb_a/reports/DUAL138K_W16_DEFAULT_PHYSICAL_20261101.md)已封存：物理BSRAM293／DSP66.5／CLS53289，setup4489／−4.472ns、hold3／−3.683ns、recovery+1.869／removal+.278ns。最差DDR read_pointer→raw pack_frames及HCI tx_header→generations WRE，另有48k参考hold−.002ns；四张clk50−4.442／+.175／−4.442／−3.683ns。原生VO58项44通过14跳过／60负控、边界7／69、官方六PLL／7负控及held-v2通过；主线程重验30物理／3264证据。专门实际VO也确认缺9632资格约束，整机STA／完整CDC均未接受；同VG／SDC／DDR3.500ns的`D2110119` far已全量P&R，未预记结果，未上板。

M18 `D2110116` 的[默认完整物理结果](push2_workstation/usb_a/reports/DUAL138K_M18_DEFAULT_PHYSICAL_20261101.md)已封存：物理BSRAM235／DSP119／CLS50920，setup1813／−1.652ns、hold1／−3.638ns、recovery+2.933／removal+.278ns。最差TF available_bytes→accepted_used，其后为显示expected_sequence及音频transaction_fault相关路径；四张clk50−1.309／+.137／−1.309／−3.638ns。原生VO58项55通过3跳过／71负控、边界7／69、官方六PLL／7负控及held-v2通过；独立子代理与主线程各重验2966冻结证据，完整STA／物理接受仍失败。同VG／SDC／DDR3.500ns的`D2110117` far继续独立测量；未上板，不改变T2-D1／D2状态。

M18 `D2110117` 的[far完整物理结果](push2_workstation/usb_a/reports/DUAL138K_M18_FAR_PHYSICAL_20261101.md)已封存：物理BSRAM235／DSP119／CLS50884，setup1093／−.866ns、hold3／−.113ns、recovery+2.222／removal+.281ns。原DDR hold要求3.500ns保持，实测+.534ns；三条剩余hold均为48k参考binary→Gray。四张clk50+.487／+.164／+.487／+.164ns；TF available_bytes7→accepted_used30仍为16级／−.864ns。六组审计全过（native58／3跳过／71负控、boundary7／69、六PLL／7负控／held-v2），主线程重验2971证据。完整STA仍失败，未上板；下一维护阶段针对实际TF响应尺寸和其余真实违例，不将定向布局转授整机接受。

W16 `D2110119` 的[far完整物理结果](push2_workstation/usb_a/reports/DUAL138K_W16_FAR_PHYSICAL_20261101.md)已封存：物理BSRAM293／DSP66.5／CLS53333，setup6810／−5.168ns、hold0／+.103ns、recovery+1.966／removal+.278ns。原DDR3.500ns保持、hold+.622ns；四张clk50−4.536／+.138／−4.536／+.138ns。DDR所有权检查至录音即时故障及D效果overflow至PCM资格为当前实测长链，HCI generations至offer_handle CE仍违例。六审计全过（native58／14跳过／60负控、boundary7／69、六PLL／7负控／held-v2），主线程逐项复验3273冻结证据；完整STA和原返回邮箱资格约束缺口仍失败，未上板，T2-D1／D2未完成。

W专属[返回邮箱v3维护阶段](push2_workstation/usb_a/reports/DUAL138K_W_RETURN_V3_MAINTAINED_20261101.md)已完成：仅新W prepare显式选择v3，32×301资格路径添加10.000ns及hold-only，actual VG／VO overlay确认9928／9928覆盖，13原负控＋6补充全拒且mapped项强制校验预期契约原因。早期cache部分VG负控缺driver的范围在报告收窄；来源／旧政策兼容10项、accepted source17项通过，M及旧v1／v2不导入／不偷加新规则。主线程重验7owned／8冻结输入／51证据及6函数AST。尚待新来源锁、新候选和完整物理时序；冻结W16原缺口保留，native-response可达性及整机CDC／硬件未升格，未上板。

M的[TF accepted响应尺寸维护阶段](push2_workstation/usb_a/reports/DUAL138K_TF_ACCEPTED_RESPONSE_20261101.md)已完成：按M18 default／far实测链仅前算full／pending／partial六种accepted算术，未知控制保留generic，read_buf预装与全部NBA／周期不改。实际维护31dcb…07b7通过72自由位两表达式证明、2097152四态／5负控及旧available／response／occupancy／threshold／private-preload全链；严格inverse31→5fc→1baa→3f9→5ac和原fixture保持。主线程重验258产物／25输入／3owned，物理收益需新身份全量重测；未上板，不将旧M18时序转授新RTL。

W-v3的[strict审计来源兼容修正](push2_workstation/usb_a/reports/DUAL138K_W_RETURN_AUDIT_COMPAT_20261101.md)通过16项回归：新helper／bluetooth仅v3封存，起止复用同一来源tuple，M/W旧策略在两新依赖缺失时可继续验证；v3缺任一依赖仍拒绝。修正初始工具无条件读取依赖，未改旧seal或时序门，未启动EDA／硬件。

W实测DDR长链的[owner组合预译码维护阶段](push2_workstation/usb_a/reports/DUAL138K_DDR_OWNER_PREDECODE_20261101.md)已完成：每entry先译invalid再单bit选址，tags仍唯一权威，原owner／返回数据及same-edge empty／invalid故障保持，无新状态／周期。实际e4cd6d…655d通过620880四态／边沿、3新负控、原native27场景＋6fault＋11负控及authority10相位／6负控；主线程重验248证据／2owned。推断存储及路由成本可能变化，需新候选实测，不预记收益，未上板。

W实际overflow至PCM链的[输出context许可维护阶段](push2_workstation/usb_a/reports/DUAL138K_PCM_OUTPUT_CONTEXT_20261101.md)已完成：独立前算非context输出许可，context保留最终同拍静音门；legacy／X/Z／采样及全部NBA、bitmap逻辑保持。实际owner1c575…649b通过源码四态证明／3反例、786432完整模块四态／3负控、全状态／RAM逐拍miter及8 owner测试（含4×576000帧频差）；旧bitmap／descriptor及实际APB／CDC→完整D效果／I2S双率／PANIC回归均通过。主线程重验108包内／238外部产物／93输入／6owned；初始测试锚点失败保留，新物理收益待测，未上板。

W实测HCI长链的[known generation字节组维护阶段](push2_workstation/usb_a/reports/DUAL138K_HCI_KNOWN_GENERATION_GROUPS_20261101.md)已完成：actual VG／VO逐位确认far的32carry对象后，将两处stored/live比较按4×8bit保留边界；无新状态／周期，clocked bytes及credit／lease／fault等保持。654717…fc88通过128位表达式证明、208896实际模块四态／4负控＋2来源负控、完整owner miter及原action／identity／UART8E1-H5 native回归；主线程重验393证据／4owned／1395冻结工具。default上游transport／flow链仍另查，收益待M19/W17实际全量实现，不转授无线／硬件接受。

M19／W17的[来源锁与整机prepare检查点](push2_workstation/usb_a/reports/DUAL138K_M19_W17_PREPARE_20261101.md)已通过：两份各刷新8条已提交维护源码／工具hash，M保持822项锁，W显式新增返回邮箱helper为823项；其余配置／features／references保持。原始来源876／952、staged588／646、enabled261／284及各1403冻结工具在综合前封存；来源17、审计16、政策7项回归通过。主线程独立重验6964路径与精确锁差异，新身份后缀3b42d2cc55cc70d5／518b142532fd5352。M为v2／14行，W显式v3／21行；新实际网表与完整物理门仍待验证，未预记收益或上板，T2-D1／D2保持未完成。

M19／W17的[完整综合与actual VG检查点](push2_workstation/usb_a/reports/DUAL138K_M19_W17_SYNTHESIS_20261101.md)已通过：FF46932／45220、LUT53910／57394、ALU12550／13802、综合BSRAM equivalent195／257；native58项分别53／44通过、5／14不适用，68／59负控全拒，边界各7／69。W新v3实际296payload／301资格端点／9928对10ns及hold覆盖、4专项／19负控通过，native-response完整映射归纳证明和物理CDC未转授。主线程独立复验7039路径；两次外围封存skip解析失败及原始结果均保留，工具／RTL／回归不改。新default D2110120／D2110122各8输入封存后全量P&R已启动；未预记routed资源／时序或上板，T2-D1／D2保持未完成。

M19 `D2110120`的[default完整物理结果](push2_workstation/usb_a/reports/DUAL138K_M19_DEFAULT_PHYSICAL_20261101.md)已封存：物理BSRAM235／DSP119／CLS50976，setup5710／−3.450ns、hold1／−3.617ns，recovery+3.233／removal+.275ns。最差效果transaction_fault→config_state及矢量DSP；DDR原3.500ns要求保持。六审计通过（native58／3不适用／71负控、边界7／69、六PLL／7负控／held-v2），主线程重验30物理／2968证据。TF实际新源已消费，但available→accepted仍13条routed负路径、最差−2.175ns，图结构缩短不记routed收益。相同VG／SDC独立far `D2110121`继续测量；完整STA失败，未上板，T2-D1／D2保持未完成。

M19 `0xD2110121`的[far完整物理结果](push2_workstation/usb_a/reports/DUAL138K_M19_FAR_PHYSICAL_20261101.md)已封存：物理BSRAM235／DSP119／CLS50954，setup3476／-2.302ns、hold10／-0.586ns，recovery+2.428／removal+0.278ns。六审计通过（native58／3不适用／71负控、边界7／69、六PLL／7负控／held-v2），主线程重验30物理／2970证据。最差setup为delay underflow_sticky→config_state CE。DDR原3.500ns要求保持，定向区域实测hold +0.508ns；剩余10个hold负端点属于48k参考计数器binary→Gray／binary，不能放宽CDC或时钟绕过。DDR UI另有505个setup负端点／TNS −319.105ns。报告中仍有TF available_bytes→write_ring_offset／write_total_bytes路径，不能因为有界表未列出accepted_used而宣称TF时序通过。完整STA和整机接受仍失败，未上板，T2-D1／D2未完成。

W17 `0xD2110122`的[default完整物理结果](push2_workstation/usb_a/reports/DUAL138K_W17_DEFAULT_PHYSICAL_20261101.md)已封存：物理BSRAM293／DSP66.5／CLS53457，setup6774／-4.737ns、hold6／-3.683ns，recovery+2.169／removal+0.275ns。六审计通过（native58／11不适用／63负控、边界7／69、六PLL／7负控／held-v3），主线程重验30物理／3275证据。最差setup为delay overflow_sticky→PCM owner written bitmap CE，当前输出context修复没有消除bitmap长链。DDR另有ui_reset_pipe2→memory_failure CE −4.656ns，clk50为tx_header0→host_rx lease_handles CE −3.495ns。原DDR3.500ns要求保持，hold −3.683ns；其余5个hold负端点是44.1k参考计数器binary→Gray／binary，最差−0.406ns。新owner预译码实际把2个RAM16SDP4换为128个DFFRE，新增存储／mux成本如实保留，不以局部结构推断收益。完整STA和整机接受仍失败，未上板，T2-D1／D2未完成。

W17 `D2110123`的[far完整物理结果](push2_workstation/usb_a/reports/DUAL138K_W17_FAR_PHYSICAL_20261101.md)已封存：物理BSRAM293／DSP66.5／CLS53431，setup5696／−5.123ns、hold1／−.232ns，recovery+1.803／removal+0.278ns、pulse+.580ns。DDR原3.500ns保持且实测+.844ns；仍有tags19→raw memory_failure、active_generation→written及host_rx generation→reliable长链。六审计及补充Wreturn19全过（native58／11不适用／63负控、边界7／69、六PLL／7负控／v3），主线程重验32物理／3277标准证据，另复验default／far扩展3307／3322。外围schema／数量断言失败保留，不放宽门禁。完整STA仍失败，未上板，T2-D1／D2未完成。

HCI ACL generation 的[维护源码比较分组](push2_workstation/usb_a/reports/DUAL138K_HCI_ACL_GENERATION_20261101.md)已通过：先并行比较各slot完整32bit，再按原selector选单比特；clocked字节、信用、即时取消与错误优先级不变。两完整owner各91,711周期对照、151,160四态、128自由位组合关系UNSAT及8实际／4来源负控通过，原pool与完整native默认入口（含UART8E1／H5）通过。主线程重验757封存文件及严格inverse，尚未更新profile或进入新综合／P&R，无物理收益主张，未上板。

M19 的[reference区域布局D2110124](push2_workstation/usb_a/reports/DUAL138K_M19_REFERENCE_PHYSICAL_20261101.md)完整P&R及六审计完成，VG／SDC／DDR3.500ns保持，CST仅追加两个64FF bank区域。实测BSRAM235／DSP119／CLS50878，setup5526／−3.417ns、hold11／−0.198ns，recovery+1.807／removal+0.281ns、DDR指定hold+.503ns。reference同域hold仍失败，最差setup转为delay peer_fault→config_state CE；DDR UI另有571 setup负端点／TNS−476.102ns。主线程重验12物理输入／30产物／2972证据；不以局部改善转授整机通过，未上板。

W 的[raw最终故障写使能](push2_workstation/usb_a/reports/DUAL138K_RAW_FINAL_FAILURE_CE_20261101.md)已修改维护源码并通过：私有4bit故障码同沿process保留first-fault／X-Z投影，其他NBA目标／RHS／顺序保持。完整owner两几何356656／304921边沿、4096任意四态＋32定向、524288 CE/value与16384唯一协议向量、5实际／4来源负控通过；原raw、DDR queue／bridge、preload／global及BLE五层入口均通过。工具旧source pin拒绝保留，显式提升后新输出验证；主线程重验552证据与Git严格inverse。尚未更新profile或新综合／P&R，无物理收益主张，未上板。

M 的[TF epoch比较分组](push2_workstation/usb_a/reports/DUAL138K_TF_EPOCH_GROUPS_20261101.md)已落维护源码：针对D2110124实际32级NE链，将全部32bit比较分4×8保留组，无新周期／状态，X-Z与即时取消保持。实际完整模块66560四态、原四配置owner共1069069边沿、stop／clear及17来源门通过，8实际／2来源负控保持；旧实际VG／VO native各58项、68／71变异拒绝，缺失的vendor模型门已明确补跑，余5／3项映射不适用。两独立review无发现，主线程复验104绑定文件及Git严格inverse。尚未更新profile或测量新物理结果，未上板，T2-D1／D2未完成。

W 的[PCM bitmap最终context判定](push2_workstation/usb_a/reports/DUAL138K_PCM_BITMAP_CONTEXT_20261101.md)已落维护：已知context在最终写入选择，X-Z保留原顺序NBA，其他字节不改，不含live_matches新修改。实际模块52224四态、8依赖关系UNSAT／2错误SAT、7217全owner周期、4实际／4来源负控、原owner八项与四种576000帧频差通过；旧window／descriptor／control／output及bitmap来源链保留。正式通用PCM1454重建串行帧、D1918帧／1917显示快照／12PANIC通过，绑定同批回执修复。主线程复验462封存文件／132当前输入及Git严格inverse；未新EDA／上板，不记物理收益。

M／W 的[配置实际接受回执](push2_workstation/usb_a/reports/DUAL138K_CONFIG_ACCEPT_RECEIPT_20261101.md)已修复：runtime CFG_ACCEPT不再因ready独立为1而虚假ACK，直接等待原engine_rate_commit广播回执，故障／valid撤销同拍禁止ACK，无新状态或延迟。完整M／W33280四态、实际FSM及旧ready负控、原config-ready／sample／effect证明和完整service对照通过；M22532帧、生产启动1028帧、48645独立定点模型帧／31边界／115929947 effect对照通过。主线程独立核对十一份变更及797封存文件／220当前输入；未更新profile或新EDA／上板，不记物理收益。

[M20／W18来源锁](push2_workstation/usb_a/reports/DUAL138K_M20_W18_SOURCE_LOCK_20261101.json)已明确刷新：两份各10条已验证源码／工具hash提升，并锁定render回归新import的receipt helper，库存M823／W824；配置、功能、历史references和source_sets保持。两profile严格check、本阶段17来源与16demo审计通过（独立日志无skip；前一回执阶段的26项demo入口另列）。下一全量prepare／综合／P&R分别使用新目录与D2110125／D2110126，旧M19／W17身份和证据不改；当前只完成来源门，不提前记物理或硬件接受。

[M20／W18新整机prepare](push2_workstation/usb_a/reports/DUAL138K_M20_W18_PREPARE_20261101.json)及profile verify通过：M身份`908c9fa1f158b21a`、588 staged／261编译输入；W身份`dee2666eaf545e40`、646 staged／284编译输入。主线程复验全部1234 staged文件与1647来源锁，明确新修复实际暂存身份；模块是否退出仍由综合网表门验证，不以文件在目录中推断实例。M仍为无CNN基础声画、W录音仍16384帧，未修改容量／业务范围。已转入两份全量综合，后续默认P&R使用D2110125／D2110126；当前prepare不代表综合、物理或硬件通过。

M20 的[完整综合及实际VG门](push2_workstation/usb_a/reports/DUAL138K_M20_SYNTHESIS_20261101.json)通过：FF46932／LUT54342／ALU12554／综合BSRAM equivalent195；较M19 LUT+432、ALU+4，不记资源收益。新TF比较已在实际VG形成4条独立8级ALU链；native58项52过／6映射不适用、67负控全拒，APB实际改为unconditional toggle XOR LUT4分支并完整覆盖，未跳过真实边界；boundary7／69通过。主线程重验3753绑定文件。默认D2110125已进入全量P&R，物理BSRAM、完整STA和声画未接受。

W18 的[全量综合与严格门拒绝](push2_workstation/usb_a/reports/DUAL138K_W18_SYNTHESIS_REJECTED_20261101.json)分别记录：FF45180／LUT61247／ALU19772／综合BSRAM equivalent257，LUT／ALU明显增加，未预记收益。actual VG `c016fb99…9327b`的generation闭包仍333／资格301端点，但旧选择器对unpack_active与index0的D／CE各漏一项、多选相反引脚；主线程独立全闭包核对相同。strict门拒绝后未P&R，旧W18固定输入不改，下一独立候选精确修正覆盖；boundary实际正向通过但一项D／CE变异在更早closure门拒绝，原预期归因断言失败也保留。当前只读JTAG仍一块有效138K／C11028E5，未写SRAM／Flash，无专用HDMI采集或线路音频输入；不转授为实板声画接受。

W 的[实际return选择器与负控修复](push2_workstation/usb_a/reports/DUAL138K_W19_SELECTOR_SOURCE_20261101.json)已验证并落维护：只将unpack_active目标改D、index0目标改CE，32源／301资格／9928真实pair、10.000ns与仅hold豁免保持；真实W18 VG的strict held入口、原4项及19负控全通过。boundary D／CE变异先以具体next-Q关系拒绝，再由完整audit拒绝，7项／69负控／0skip通过；不依赖首个异常门归因。主线程复验6511绑定输入／证据，W仅提升一个既有helper hash，M profile及配置不改，两profile来源门、17来源与16demo入口通过。旧W18仍冻结拒绝；因helper本身是non-SDC staged输入，新W19必须完整综合，当前不记新的物理或硬件接受。

M20 的[默认全量P&R与六项实际审计](push2_workstation/usb_a/reports/DUAL138K_M20_DEFAULT_PHYSICAL_20261101.json)已完成：D2110125位流`66059d24…cab6b`，物理BSRAM235／DSP119／CLS51133；setup1936端点、最差−1.170ns，DDR单hold−3.364ns，recovery+2.782／removal+0.290ns。native58项54过／4映射不适用、70负控拒绝，boundary7／69及六PLL／7负控、selected held v2通过；完整STA仍拒绝，不转授上板。主线程重新核对实际物理、工具、暂存及审计全部绑定hash；audio1671与DDR264 setup端点仍须针对实际路径修复。已从同次实际VO派生far D2110127，VG／SDC／DDR3.500ns保持，待独立完整物理重测，不预记通过。

W19 的[新prepare、全量综合与实际VG门](push2_workstation/usb_a/reports/DUAL138K_W19_SYNTHESIS_20261101.json)全部通过：独立身份`2938af5370fd07a0`，952来源／646暂存／284编译输入／824锁，未复用W18综合；实际VG `ff74be96…720f1`。综合FF45180／LUT61247／ALU19772／BSRAM equivalent257，与W18资源相同；strict通过，native58项42过／16具名不适用与57负控、boundary7／69、Wreturn4／19全部通过。主线程复验3064封存文件；默认D2110129开始完整P&R，物理资源、STA和硬件尚未接受。

M20 的[同VG／SDC远端布局D2110127](push2_workstation/usb_a/reports/DUAL138K_M20_FAR_PHYSICAL_20261101.json)完整P&R和六审计完成：物理BSRAM235／DSP119／CLS51269，指定DDR原3.500ns hold已为+0.622ns，但48参考计数器出现5条hold／最差−0.438ns；setup2061／最差−1.348ns，audio1794／DDR266负端点，完整STA继续拒绝。native54过／4映射不适用与70负控、boundary7／69、PLL／7负控与held-v2均通过。位流`a061d50a…44538`及全部来源／物理证据由主线程重验；不启动第三M20布局，转入实际NoteOff长选择链和滑音算术修复，未上板。

M 的[NoteOff最低匹配声部并行前缀](push2_workstation/usb_a/reports/DUAL138K_NOTE_OFF_PREFIX_20261101.json)已修改维护源码：只改变release选择，比较器、allocation／expression与全部clocked字节保持；32自由匹配位关系UNSAT、实际50434四态向量、SEPARATE_OFF_NOTE=0／1各6612帧／6134628半边沿／960重复释放／34PANIC通过，最大1061周期。缺低group的实际负控在符号、四态和整模块均拒绝，原provenance／expression manifest字节不改；新局部严格inverse与必要构建依赖已接入。独立审查无发现，主线程复验58证据与维护／原始来源，不提前记物理收益。

M 的[滑音整数分解](push2_workstation/usb_a/reports/DUAL138K_GLIDE_PARTITION_20261101.json)已落维护：实际n23串行乘法路径改为四个nibble常量商余数与有界并行trial，不增周期，组合块外全部字节保持。实际16777220组合输入／40017事务、294912四态／160000半边沿、280925周期独立模型与旧48k16000周期对照通过；7整数、3四态／来源及2行为负控全部拒绝，两次独立审查无发现。新物理资源、时序与声画均待M21实测。

两份[来源锁提升](push2_workstation/usb_a/reports/DUAL138K_M21_SOURCE_LOCK_20261101.json)只刷新上述4条已有hash并加入2个必需NoteOff依赖，M825／W826；配置、功能与旧候选保持。两profile check、17来源、16demo及7policy通过，下一M21使用新独立prepare及D211012B，必要far预留D211012C；当前W19仍消费原冻结输入，不混维护树新修改。

W19的[默认全量物理结果](push2_workstation/usb_a/reports/DUAL138K_W19_DEFAULT_PHYSICAL_20261101.json)已封存并由主线程重验3374文件：D2110129位流`cdc5c589…dc2ff`，物理BSRAM293／DSP66.5／CLS57746；setup6535／最差−5.870ns，hold2／最差−3.547ns，另有midi_bytes ACK首级−0.060ns。六项实际审计全通过（native44过／14具名不适用、60负控；boundary7／69、Wreturn4／19、六PLL／7负控），完整STA仍失败，未上板，不启动W19 far；下一整合候选同时消费新UI和25K momentary修复。

本轮[M基础TF退出及浅色HDMI维护实现](push2_workstation/usb_a/reports/DUAL138K_M_CORE_HMI_SOURCE_20261101.json)已完成定向离线验证：关闭TF/FAT／DDR播放／识别配套，原始维护实现保留；取消等待不存在TF的stop ACK，拒绝相关原始CC请求，同时隐藏Push的TF／local cue／录音键、失效SCORE／RECORD标签与LED。普通／矢量／32声部／ADSR、完整效果、Push／25K、HDMI及I2S保留。双率实际1078物理帧／1077显示帧的owner投影配对通过；两个浅色页面各2073600像素／21369停顿通过，完整波形／XY／双声道频谱／效果链保留。官方logo来自总官网链接的FPGA赛道站，原文标语为该站“竞赛原则”，来源／原PNG／字体许可及ROM转换身份均入维护资产。参数表是每栅格冻结的实际owner状态，与历史分析缓存不声称采样同一时刻；新／加宽CDC仍须实际VG／VO门。当前只为源码／离线阶段，M22／W20将独立全量综合／P&R（D211012D／D211012E），尚无新资源、位流或板测接受。

W 的[25K真实momentary闭环](push2_workstation/usb_a/reports/DUAL138K_W_TOUCH_MOMENTARY_20261101.json)已落维护固件与唯一参数owner：触摸按下启效、松开只撤自身效果；并按组合、H按住dry／释放恢复仍按住项、G按住全链、P主音量、重复释放及断连PANIC明确处理。真实C→MMIO→FIFO／CDC→D完整DSP／DDR→已提交反馈通过110 checkpoints／2380帧／266USB事件／9生命周期，含44.1k；关效尾音不再混回D，M及默认保留原尾音。默认完整effects18项及9 provenance／262144四态全部通过，原manifest字节保持；这仍是离线闭环，真实25K／手机与新W20物理证据待后续。

[M22／W20新整机prepare及来源冻结](push2_workstation/usb_a/reports/DUAL138K_M22_W20_PREPARE_20261101.json)已完成：M `8624239a297667b1`／891来源／603暂存／262编译／845锁；W `49dc4695ee6881cb`／967来源／661暂存／285编译／846锁，分别冻结1440工具文件。主线程重新核对全部来源／工具及1264暂存文件。两份均由`a33f4115`源码全量新综合，不复用旧VG；此阶段不预记TF退出的资源收益，不代表实际网表／物理或声画接受。

M22的[全量综合及默认物理准备](push2_workstation/usb_a/reports/DUAL138K_M22_SYNTHESIS_20261101.json)已通过：FF43046／LUT48124／ALU11476／综合BSRAM等价203，实际VG `4b3da766…9b0b6`。旧协议库存门先拒绝，独立v2审计快照才按实际display132FF／230接收FF＋98注册RAM位、新参数邮箱60FF及本域queue tail CE→D映射通过，M22源码／VG／SDC未改；失败保留。默认D211012D已启动全量P&R，未派生far。新HMI逐位source origin、常量／alias闭包、后级SDC及破坏负控仍单列pending，不能将基础握手通过转为物理CDC／声画接受。主线程独立复验关键报告、VG／资源XML及两项新审计工具身份；不把综合BSRAM203当物理资源。

M22实测HMI长链的[十进制文字查表修复](push2_workstation/usb_a/reports/DUAL138K_HMI_DECIMAL_LOOKUP_20261101.json)已落实际维护源：完整128值查表替代优先比较／DSP乘法／减法，X/Z默认保留原表达式，无新增状态或流水周期。128二态及16256四态输入逐一等价、2个实际负控拒绝；两完整页面各2073600像素／21369停顿，M／W图像均与v5逐字节相同。独立源码复核通过；同工具孤立函数MULT12X12／ALU由1／7变为0／0，仅为局部结构证据，整机资源／时序待新候选测量。原M22／W20来源、VG和物理结果不改。

M的[performance邮箱释放修正](push2_workstation/usb_a/reports/DUAL138K_M_PERFORMANCE_RELEASE_20261101.json)已落维护构建选择与审计：新显式M-v3仅恢复既有6个异步释放CLEAR目标与4条2ns后级同步界，功能复位与时钟要求保持；旧M-v1／v2及W策略保持。实际M22 VG／VO各17项无skip及各8项变异拒绝通过。双profile只刷新dashboard及3个既有工具，明确加入2个回归依赖后为M847／W848锁；两来源check、17来源／17demo／8policy通过。M22默认STA仍失败，独立同VG的D211012F只追加上述5行并测量DDR／reference定向布局，不能继承默认或未来M23的身份。

W的[流式Pitch源码缺口](push2_workstation/usb_a/reports/DUAL138K_W_STREAM_PITCH_GAP_20261101.json)已据实记录：第5节要求Pitch／Delay／Chorus／Reverb，但实际W20禁合成分支将pitch固定unity，完整stereo链未接PCM变调输入，25K kind4也被拒绝；W19同样如此，属于既有实现缺口。旧sampler_voice是储样本相位／voice引擎，长期输入的SRC漂移补偿也不是流式Pitch，均不能据此打勾。当前25K momentary证据只覆盖实际已实现效果；后续须接入真实流式Pitch及正式操作入口，独立验证持续输入、延迟、声画和共存。

M22的[默认全量物理结果](push2_workstation/usb_a/reports/DUAL138K_M22_DEFAULT_PHYSICAL_20261101.json)已封存：D211012D，物理BSRAM243／DSP118／CLS46587，setup242／最差−0.435ns、hold4／−3.419ns、recovery−5.021ns、removal+0.278ns。六项选定审计通过（native44过／15具名不适用、60负控；boundary7／69；六PLL／7负控），另有TF退出grant的10项负控；旧库存／fixture失败保留。完整STA仍拒绝，新的HMI逐位语义审查另列，不上板。M23已由新维护源独立全量综合；D211012F的同VG实验与M23新VG不混同。

W20的[默认全量物理结果](push2_workstation/usb_a/reports/DUAL138K_W20_DEFAULT_PHYSICAL_20261101.json)已封存：D211012E，物理BSRAM306／DSP68.5／CLS57944，setup7640／最差−6.130ns、hold2／−3.392ns，recovery+2.867／removal+0.278ns。六审计及Wreturn4／19通过（native47过／12具名不适用、63负控；boundary7／69；六PLL／7负控），完整STA仍失败。主线程独立复核W的4917封存文件与M实际资源、位流／工具／source／stage绑定；没有SRAM／Flash操作。下一步修复实测tags→pack_frames、compute_release→written路径；不宣称流式Pitch或真实手机声画验收通过。

W实测返回故障长链的[owner-veto分层选择](push2_workstation/usb_a/reports/DUAL138K_W_OWNER_VETO_TREE_20261101.json)已落维护RTL：实时tags先译码，经4:1有界组合树选择，奇数末层2:1；不增状态／周期，不增加影子tags，不延迟同拍故障。TAG_BITS2—8实际四态检查通过，当前8位347136例及4负控拒绝；原生DDR27配置／6故障／11负控和两模式严格lint通过，独立源码复核无阻塞。双profile仅刷新arbiter并明确加入原回归依赖，M848／W849锁；新映射／完整资源时序尚待W21全量实现，不提前记收益，M23与W20冻结输入保持。

[新HMI实际来源语义审查](push2_workstation/usb_a/reports/DUAL138K_HMI_ACTUAL_SOURCE_REVIEW_20261101.json)已收口M22／W20的实际VG与默认VO：129位端口分别为M60有效／8已用零常量／61未用，W36有效／35已用零常量／58未用；W上游255明确为Q20 unity位20。逐位串联唯一owner→旧display→新邮箱→renderer，16组合frame接受CE、3级reset alias和6条精确SDC选择通过；M新增8负控、W70 VG／63 VO负控均拒绝，旧RAM98与握手门保持。主线程复验28绑定证据。此项关闭来源／映射语义，不将历史分析缓存与实时参数称为同一采样时刻，也不覆盖完整STA或实板验收；M23新网表须再次验证。

M22的[定向布局D211012F](push2_workstation/usb_a/reports/DUAL138K_M22_DIRECTED_PHYSICAL_20261101.json)完整P&R及六审计＋performance专项完成：同VG，精确增加5条释放约束，DDR原3.500ns与所有功能保持；物理BSRAM243／DSP118／CLS46583。setup仍8端点／最差−0.007ns，hold0／最小+0.144ns，recovery+2.514／removal+0.278ns，指定DDR hold+0.514ns。原native／boundary／PLL负控、performance17项／8负控及override10负控通过；主线程复验1510绑定文件。微小负slack仍严格拒绝，不四舍五入成通过，不上板。

M23的[新全量综合与定向物理准备](push2_workstation/usb_a/reports/DUAL138K_M23_SYNTHESIS_20261101.json)已通过：来源commit2b26f7a6、身份56a8bb5120ee3116，847锁／891来源／603暂存／262编译／1441工具；真实VG afe0228f…7b4ded，FF43096／LUT48033／ALU11423／综合BSRAM等价206／SSRAM99。当前完整综合含新十进制查表及正常M-v3 SDC，未复用M22网表；真正strict报告38s且非空，通过后直接采用已测有效的DDR／reference定向配方启动D2110130全量P&R。主线程复验4404文件，正常stage SDC与physical字节相同，无12F实验override。初次误用无CLI模块的空输出明确排除；物理资源／时序和声画尚未预记。

[PCM逐槽清理许可](push2_workstation/usb_a/reports/DUAL138K_PCM_BITMAP_SLOTS_20261101.json)已落维护源码：实际完整owner7217拍／6000随机命令、52224四态及3负控通过，旧context严格inverse后4负控与8项PCM suite通过（双率±2000ppm／jitter／stereo各576000帧）。主线程重验67文件与Git逐字节inverse；无新增状态或周期，不预记物理收益。W无显示／无录音新候选将显式消费，M23冻结输入不变；已中断的raw录音proof另保留且不宣称完整通过。

M23的[完整物理D2110130](push2_workstation/usb_a/reports/DUAL138K_M23_DIRECTED_PHYSICAL_20261101.json)已封存：全量P&R623.863s，物理BSRAM246／DSP116／CLS46460；setup599／最差−0.556ns（audio477、DDR UI122），hold0／+0.143ns，recovery+2.462／removal+0.275ns，DDR原3.500ns保持且指定hold+0.453ns。native45过／14具名不适用／61负控、boundary7／69、六PLL／7负控、performance17／8负控，以及新VG／VO实际HMI来源60有效／8消费常量／61未用及各8负控均通过；完整STA仍严格失败，不下载。主线程重新核验4475冻结文件；新M最小修复另用D2110132，W无显示配置独立推进。

手机App新版[0.3.1-demo-d3](../../clients/android/docs/DEMO_D3_20261101.md)已实现真实SAF文件选择、本机／具体A2DP设备选择与实际routedDevice核对、播放／暂停／seek，及独立标准BLE MIDI手机→25K单事件发送／16键／力度／通道／NoteOff／PANIC／会话清理。83项单测零失败（2原硬件项跳过）、lint零错误／7依赖提示，隔离模拟器5项UI全过及最终同APK真实文件选择通过；主线程复验102来源／APK／证据文件，APK SHA c19645ec…9c5be。当前25K维护固件只将手机MIDI用于remote LED，无BLE→USB→138K发声转发；App明确显示，真手机无线／25K反馈／W DAC及断连实测均待验，不能据此勾选T2-D1／D2。

W的[显式无图形／无录音AE350固件](push2_workstation/usb_a/reports/DUAL138K_W_AUDIO_ONLY_FIRMWARE_20261101.json)已完成真实RV32链接：24编译单元仅维护startup／libc／Classic／HCI／SBC／PCM／clock，ui_main／ui_render及录音／business C未编译且ELF无其符号；源实现保留。保守栈896／16384、93实际JALR闭包及4回调负控，实际loader后断连／坏ID两场景持续pump且零UI／录音／DDR访问；8组成／误标负控、默认分支预处理等价、原11SBC双版本／15runtime＋9PCM负控和17来源测试通过。独立review发现的证据角色误标漏洞已修，v5 ELF与v4逐字一致；FPGA实际编译／VG／物理退出仍由新W21另验，不把固件通过当整机／手机／DAC通过。

M24的[同拍dispatch与HDMI既有级坐标修复](push2_workstation/usb_a/reports/DUAL138K_M24_DISPATCH_HDMI_MAINTENANCE_20261101.json)已落维护RTL：只读stored slot经原引擎owner组合，保留公开ready、同拍mode／事件互斥及未知态fallback，不增加音频状态／周期；27个坐标谓词前移至既有Stage A，颜色优先级、四级像素延迟、reset／enable停顿保持。M／W／legacy完整service／engine／effects／DMA miter、3项无假设二态证明、147456四态、3可观察负控及4配置整屏＋65536额外输入通过；旧fixture对封存M23已拒绝、fallback移除在观测锥无差异，均据实保留而未冒记负控。主线程重验164绑定／119文件，4份完整inverse逐字节等于Git HEAD；17来源测试通过。新D2110132将独立全量综合／P&R，不预记资源或时序收益，未上板。

M24的[实际生产来源逆链](push2_workstation/usb_a/reports/DUAL138K_M24_DISPATCH_PRODUCTION_PROVENANCE_20261101.json)已接入：同一tools helper唯一维护3源完整inverse，verification薄导入；只有精确新oscillator可逆回原release／expression链，旧3份manifest逐字节不变，混合新旧owner与越界修改严格拒绝。7来源正例／18负控、绑定新helper的147456四态＋3实际负控和M／W／legacy完整miter通过；主线程重验106绑定／94文件并重跑来源与17入口测试。仅解除新源码构建来源门，不把来源通过当综合、物理或硬件接受。

W21的[显式无显示／无录音源码及双方来源锁](push2_workstation/usb_a/reports/DUAL138K_W21_AUDIO_ONLY_SOURCE_20261101.json)已落实际provider：W revision2退出HDMI／图形UI／FFT／XY／framebuffer、录音下载及配套CDC／等待，保留USB Host／25K必要反馈、真实H5／HCI／SBC／PCM与D效果；复用原生BIST／队列／owner6延迟DDR，退出CPU／显示／录音事务。默认M角色／配置／feature／baseline不改，macro-off默认预处理逐字节保全；维护源码及旧W revision1证据保留。M857／W1106锁经主线程逐项load／hash核对，W3定向、17来源／17审计、clock2项（1具名skip）通过；真实memory 64 BIST＋256 D事务、停顿BL8／有序返回／故障隔离通过。新131／132各自全量prepare／综合／P&R另记，退出VG与真实手机／DAC未预记通过；unfinished raw8未提交、不消费、不冒记验证，真正流式Pitch另补。

M24的[整机prepare及来源封存](push2_workstation/usb_a/reports/DUAL138K_M24_PREPARE_20261101.json)已完成：9e88d1fb来源、身份b4a481778b7043c8，857锁／898原来源／604暂存／262编译及1460冻结工具逐项复验；M独立全量新综合已启动，132物理另验。prepare结束后W修复改动的2工具＋W profile严格从同提交blob恢复到原SHA后封存，原metadata／暂存输入不改；7项unfinished raw均非copied／非enabled，仅库存，未转授验收。主线程重hash2974封存文件；此阶段不预记综合资源、routed时序或声画通过。

M24的[完整新综合与D2110132物理启动](push2_workstation/usb_a/reports/DUAL138K_M24_SYNTHESIS_20261101.json)已完成：新VG deca9e69…c7d9e7，完整综合168.40秒，严格v4通过后启动全量P&R；正常M-v3 SDC原字节，DDR原3.500ns与128ref定向布局要求保持。新M queue tail出现另一完整D／CE映射，63个真实叶／1137 BDD节点的无假设next-Q等价通过，仅窄接纳第二M140 census，原139端点及opaque／clock门保持；错误的release低tail必零假设已被真实BDD拒绝、未采用。DDR根cells／params仅3个精确clock alias重命名后与参考相等，128ref D变化明确保留，不冒称整VG相同；主线程重验4457封存文件，旧失败与cache审计适配逐项记录。真实资源／STA／PLL／CDC／HMI及实板仍待物理结果，不据综合放行下载。

W的[连续PCM Pitch维护单元](push2_workstation/usb_a/reports/DUAL138K_STREAM_PITCH_UNIT_20261101.json)已通过离线阶段：同采样率一入一出、双读头交叉淡化，32bit stereo／2048帧history、64frame启停ramp、每帧含接收41clock；不是sampler或SRC调速。实际维护模块在行为RAM及真实8×SDPB各87496请求与独立定点模型逐帧相等，4执行负控拒绝；独立补测两mode各57946请求，补齐接收后1—40全部取消边沿及clamp／极值／ramp反转。主线程核对全部来源及65份证据文件。当前仅单元入维护，正式W参数／25K／PCM生命周期接入、新整机EDA与手机DAC仍待验；粒状旁带、约4.4Hz dominant-peak偏差和pitch-up无抗混叠滤波如实保留，不冒称高保真或完成Pitch整机交付。

用户本轮明确要求的[M22 SRAM功能试装](push2_workstation/usb_a/reports/DUAL138K_M22_SRAM_TRIAL_20261101.json)已执行，采用微小时序违例的定向版本D211012F（8 setup／最差−0.007ns、0 hold，原失败标记保持）；FS c4a8f68b…27feea495未改。两次op4逐位Verify均返回18／Verify Failed，含一次显式0.9MHz重试，工具实际加载频率仍自动切换；随后op2 SRAM Program退出0，独立op0及op74确认0001081B／D211012F／00022230。当前留此M22给用户现场看功能，未执行Flash写入或重载。用户随后断电并要求重烧：写前独立读回C11028E5／00022020，再用同一FS执行op2退出0，写后op0／74确认D211012F／00022230；本次不重复宣称逐位Verify通过。用户再要求重烧的v5同样使用原FS，op2退出0，独立op0／74再确认D211012F／00022230（记录SHA8da8e678…4e3b43f88），未写Flash。再一次明确要求重烧的v6仍为同FS／op2退出0，独立op0／74确认相同身份和状态（记录SHA77dc51fc…6c088cafb），未进行新逐位校验或Flash操作。下载命令及身份已确认，**逐位校验未通过，声画功能未验收**，不将用户本次试装授权改记为正常时序放行；M24／W新镜像开发继续。

W21-j的[无显示／无录音完整新综合与严格VG门](push2_workstation/usb_a/reports/DUAL138K_W21_J_SYNTHESIS_20261101.json)已通过：身份343123757bea9052、1750冻结来源／工具、608暂存／128编译输入；综合101.768秒，FF26186／LUT29149／ALU10737／BSRAM等价184（不是物理数）。1553可见selector完整解析；只精确退休已从VG消失的32 serializer sequence CE，其余混合query活项保持，112反馈、HCI8条、USB／reset／native／held／boundary／ROM及功能退出门通过。i实际VG36破坏控制与j实际strict分列；实际xPack ELF已在RV32执行断连／错HCI身份，8heartbeat且0退休MMIO／DDR／trap。a—i失败均保留；未通过的raw优化实际7份完整封存后精确恢复原HEAD，不冒记通过。主线程重hash2397绑定文件；131全量P&R及真实资源／STA另记，尚无W SRAM／手机／DAC接受。

此前M23已验证但只在封存工具中的[HMI／M-core审计修复](push2_workstation/usb_a/reports/DUAL138K_HMI_CORE_AUDIT_MAINTENANCE_20261101.json)已按原SHA落维护3文件：5邮箱及实际门名负控、显式M-core的TF全部cells／selector缺席证明、由封存profile选择grant角色。M24实际VO原v3测试／PLL先拒绝并保留；新独立v4封存后59项native（45通过／14具名skip）、六PLL及7负控均通过。routed HMI帧级guard的skip不转授8项专门破坏控制，这些另跑；未改原VG／CST／SDC／候选，完整STA仍失败。主线程重hash1476文件；后续W-only无HDMI PLL分支独立推进。

M24最差实测glyph地址路径的[最小维护修复](push2_workstation/usb_a/reports/DUAL138K_BRAND_ADDRESS_TIMING_20261101.json)已完成：只把既有layout函数在elaboration组合成绝对8pixel块查表、glyph×24按行组分解；ROM／官方素材／时序状态／enable／单周期brand及4周期dashboard不改。全部4194304坐标／34560文字地址与37117停顿、4配置各2073600像素＋65536额外向量，以及实际1080p和720p缩放renderer均逐位相等；错地址负控在(402,24)出现真实RGB差异被拒。root完整inverse等于Git HEAD并核对31绑定输入。真实同器件leaf综合逻辑级15→8、估计91.333→164.690MHz，仅为小单元估计；新M25/D2110133须完整新综合／P&R，不预记整机收益，旧132不改。

除起点事实和T2-D0的文档分配外，下面完整工程任务仍未结项。每项只在对应来源、回归和要求的实测证据齐全后勾选；任务记录链接到 reports，不在此堆积工具日志。

| 完成 | ID | 工作与明确退出条件 |
|---|---|---|
| [ ] | T2-00 | 固定M／W功能矩阵与来源；逐项登记官方单底板及后续独立探针已有功能／证据，形成第2.1节保全矩阵，不把历史或用户陈述冒充当前整机通过。列出保留／退出／迁移模块；保全单板未提交改动／固定候选，实际prepare不回退私有staging。 |
| [ ] | T2-01 | 完成双方 LCD／CAM 引脚、电压／方向、供电与地、线序／线长、可用转发时钟／复位的逐脚表；检查 M 原 LCD tie-off 与新链路无多驱动。不能未经证据认定21根信号全部可复用。 |
| [ ] | T2-02 | 固定一个内部链路契约、常量和参考对端；实现有界消息／流、能力／会话、CRC／信用／优先级；覆盖满队列、损坏／重复／迟到、双方复位及版本不兼容。 |
| [ ] | T2-03 | M／W 独立prepare和单板fixture可复现；先完成链路小候选综合／P&R，静态确认W仅CAM／LCD业务IO、M保留完整音源／效果、fixture不进入生产。完整角色物理验收放T2-12及T2-40，不等待未减负的旧M先布通才开始迁移。 |
| [ ] | T2-04 | 复用既有声画／USB回归，建立第2.1节完整M无W测试：真实波形／李萨如／频谱／音效链、Push／25K交替热插拔、HS／FS、非静音音色／32声部／效果／I2S、TF、双率／PANIC。先离线验证，单板实测随T2-12候选完成；不得用W回放解锁核心，不阻塞T2-10源码迁移。 |
| [x] | T2-D0 | 最新分配已确认：M基础完整声画；W真实手机流式D＋25K＋连续DAC，显式配置退出显示和全部录音／下载。M不回退，App补手机→25K MIDI／本机与138K流式文件入口。仅范围确认，不代表工程／物理／实机通过。 |
| [ ] | T2-D1 | 按第5.1—5.4节完成实际配置／RTL／固件与App；核查W显示／录音实例和配套等待／DDR事务退出，M完整HDMI／音源／效果保全；分别全量综合／P&R。W真实流式Pitch独立补齐，不以sampler／SRC代替。离线通过后SRAM验证M基础声画和W手机持续播放／25K按下释放组合／断连／DAC连续性。 |
| [ ] | T2-D2 | 实拍对应实际镜像／UserCode／来源／位流／接线与通过范围：M完整声画贯穿演奏；W真实手机D音频／25K／DAC持续有效，不要求W HDMI或录音下载。App真机BT／MIDI与模拟器检查分列；同板分时不等于双板互通／并发。 |
| [ ] | T2-10 | 整体迁移 H5／HCI／GATT及录音下载业务到 W；M只保留字节桥和物理口，完成波特率／复位屏障、信用与初始化回放。原UUID／CRC／MTU／重放／外部错误码向量保持。 |
| [ ] | T2-11 | 实际最终PCM单流→W DDR录音／CRC／封存／可靠下载。先48k，容量满、缺帧、链路满／断开、W CPU慢／复位不影响M发声；STOP须等真实连续前缀提交。 |
| [ ] | T2-12 | 首批完整主板减负检查：退出M的蓝牙协议栈、录音后端及其CPU接口／存储；音源／效果／TF／FFT／XY／完整绘图／USB HS保留。扣除新增链路／FIFO／CDC，报告两板综合／物理资源及裕量；同一M候选在W断开且无回放下实测第2.1节，不能只测小探针。若仍不布通，先查残留／拥塞，不以继续换算法或裁核心替代迁移核对。 |
| [ ] | T2-13 | S1—S4覆盖首批真实业务；完整M单板清单通过后冻结双端角色，首次S5完成真实手机录音下载、CRC／WAV试听及并发演奏。双板扩展验收不能替代M独立验收。 |
| [ ] | T2-20 | 保全M本地完整TF：SPI／FAT／目录／WAV／播放／停止／拔卡／换曲及最终物理EOS单板验证。复用现有直接流式成果时另测资源／时序，不为双板重写文件栈或引入跨板扇区。 |
| [ ] | T2-21 | 保全M本地完整显示：真实波形／FFT／频谱／XY及音效链状态、minor1原子发布／读取／HDMI绘制均在M；W断开时完整工作，参数／频轴／画面与实际最终PCM及效果一致。不得以只显示基本页或副板回放结项。 |
| [ ] | T2-22 | W接标准A2DP／SBC流，复用现有源码／向量，不把GATT当A2DP。按块供给M现有效果入口，验证SRC／长期频差／欠载／断连／格式；与BLE录音共存的HCI信用只有一个owner。 |
| [ ] | T2-23 | 双率录音按原协议兼容扩展验收；切率时M保持持音，先等W封存／TF实际停止，再切时钟并发布新epoch；W不可达／迟到结果不导致旧对象、旧PCM或旧图复活。 |
| [ ] | T2-30 | W恢复音频CQT／CNN／Viterbi：固定实际模型、输入源／率／窗口、识别指标与预算；结果通过M受控入口，不直接驱动第二音源或篡改参数。 |
| [ ] | T2-31 | W实现CAM→预处理→YOLO→有界结果；固定摄像头／模型／量化／输入分辨率／内存／帧率及精度证据。先单板跑通，再并发；不把能装下模型当作吞吐达标。 |
| [ ] | T2-32 | 副板资源及调度矩阵：录音、媒体、分析、CNN／YOLO分别测量，再测共存；AI超预算先降帧／拒绝任务，音频／下载不被饿死。未经实测不宣称两模型与全部业务可同时满速。 |
| [ ] | T2-40 | 冻结M／W兼容版本、位流／固件／模型／约束hash、工具和回滚身份，分别通过真实routed时序／CDC／PLL／资源及功能检查；同一生产M再完成第2.1节无W验收，不能靠放宽时钟／false path或测试特供核心掩盖失败。 |
| [ ] | T2-41 | 完成最终S5：双向最大允许并发、真实手机／CAM、双方独立重启、拔线／恢复、模型装载、EOS／封存、长时间频差，测实际音频延迟／欠载、显示和链路错误；W忙／复位／断连时重复第2.1节完整主板清单。 |
| [ ] | T2-42 | 授权后分别SRAM部署／读回／人工声画，保留已知Flash回退；Flash写入及冷启动另行授权／验收。提交演示材料只声明实际完成范围。 |

近期先推进 **T2-00＋T2-D1—D2：M基础完整声画、W无显示／无录音的手机流式D与25K音频闭环→独立演示交付**。随后恢复M TF／CNN、W唯一对象录音下载，再推进LCD通信、最终角色收敛与双板联合验收；T2-10之后的长期目标继续保留。每批验证后commit／push并更新本文件，失败冻结候选只补证据、不改输入。

## 7. 最终完成判据与交付记录

1. M和W各有独立、可复现、可在同一块兼容138K分时运行的角色镜像；S0—S4的输入／输出与失败范围可检查。单板验证不冒充真实双板互通。
2. 同一完整M生产角色在W物理断开、无W回放时通过第2.1节：完整HDMI波形／李萨如／频谱／音效链、Push／25K热插拔、HS、真实发声／音色／效果／TF等保全项；W繁忙／故障不使核心退化。移出的蓝牙／录音模块确实退出M网表，资源包含两板新增接口成本，综合BSRAM与物理BSRAM分列。
3. 观测PCM只在W需要时上送一份，内部DDR不跨板；摄像头／AI模型／特征留W，TF／显示分析及HDMI整屏留M。带宽和最长等待实测满足已声明并发，失败可观察、可恢复且不会停止采样或本地完整显示。
4. 所有参数只有M一个实际提交点；外部协议保持兼容，录音／媒体／分析按实际rate／epoch／序号关联。AI结果、普通命令、实时流和显示快照不混为一个“成功”状态。
5. 发布记录至少包含：双方commit／配置／来源hash，M／W位流和固件身份、协议兼容性、模型身份，各自综合／routed资源／时序／CDC／PLL，S0—S5证据，SRAM／Flash状态和回滚方式。只完成首批时，明确TF／分析／A2DP／AI的剩余范围。
6. 本轮两份独立镜像按第5.1—5.4节验收：M基础乐器完整HDMI（波形／XY／双声道频谱／音效链）及真实演奏／DAC；W真实手机蓝牙流式D、25K按下／释放／组合／断连控制及连续I2S／DAC，显示和全部录音／下载从编译／网表退出。M TF／CNN、W唯一对象录音下载后续显式恢复，流式Pitch缺口单列补齐。退出检查、实际来源、资源／时序、位流及实测对应记录；独立／分时运行不等于最终角色、LCD互通或双板并发通过。

本文件记录开发计划与验收划分，不构成新板卡操作授权。编写本文件不执行综合、烧录、Flash写入或板间接线；后续硬件操作使用当前会话明确授权和实际连接证据，不继承单板历史部署授权。


按用户再次要求，已将同一 M22／`D211012F` [重新写入 SRAM（v7）](push2_workstation/usb_a/reports/DUAL138K_M22_SRAM_TRIAL_20261101.json)：原 FS SHA `c4a8f68b…7feea495` 及完整物理输入逐项核验，operation2 exit0，独立 operation0／74 读回 `0001081B／D211012F／00022230`。此次记录 SHA `62f15acb…93e2fc7`，此前 v1–v6 证据完整保留；未写 Flash，未声称逐位 Verify 或现场声画验收通过。板上继续保留 M22，后续 M／W 候选离线推进。


[HMI60／M140与PLL测试维护收敛](push2_workstation/usb_a/reports/DUAL138K_MAINTAINED_HMI_PLL_AUDIT_20261101.json)已完成：正式维护审计精确覆盖 M 显示132FF＋98RAM、HMI60位和完整 M140 tail-D 闭包，保留原M tail-CE／W139 tail-D规则；实际HMI八破坏控制修正至现有API与已映射3／4位。PLL仅修正一行异常文案断言，原八组身份变异保持。两显式profile各仅提升四条来源锁，1979项全匹配；主线程独立复核2615文件及四源严格inverse，并重跑来源17项和PLL完整23项（1既有actual环境skip）。M25实际VG native60项／66负控、M boundary7／69、W134实际CLI与61负控结果通过；通用历史profile入口的旧固件锁漂移失败如实保留，未改历史配置。本阶段不改RTL／SDC，不重写冻结候选，不增加时序豁免，也不记物理收益；板上仍为M22。


W22／D2110134 的[完整P&R与实际VO审计](push2_workstation/usb_a/reports/DUAL138K_W22_PHYSICAL_20261101.json)已完成：普通template、原DDR3.500ns保持，328.265s／exit0且9输入前后不变，FS `b6582caa…56163ec`。真实资源为BSRAM218／DSP59／CLS32346／FF27210／LUT30740／ALU11660／SSRAM187；完整STA仍setup1／−2.595ns、hold2／−4.357ns，recovery+2.214／removal+.278ns。唯一setup为普通MIDI request→req_meta第一同步级，另hold为ACK返回−1.010ns及DDR init→wloadn−4.357ns；未增加false path。实际VO native60项37过／23具名映射skip、64负控，boundary7／69及四PLL／三shared tuple／六grant／六main负控通过；原始SDF保持，仅折叠649组逐字相同GND弧。主线程复核3286来源／编译／物理／证据文件；v1摘要误计0grant由v2按真实six-grant字段更正并保留原记录。完整STA拒绝、反馈实际VO专项另列待验，未上板；独立D2110135只做DDR定向新布局，不改134身份。


W22的[独立定向布局D2110135](push2_workstation/usb_a/reports/DUAL138K_W22_DIRECTED_PHYSICAL_20261101.json)已完成：同134完整VG与新实际VO witness，CST仅追加130条精确INS_LOC（DDR2＋reference128），完整原CST与SDC／DDR3.500ns保持；229.091s／exit0，12输入与33产物重新核验。实测BSRAM218／DSP59／CLS32576／LUT30740／ALU11653／SSRAM187；setup1／−2.572ns、hold2／−1.004ns，recovery+1.089／removal+.278ns。指定DDR hold由−4.357变为−.181ns，仍不通过；launch／capture确在请求区域，不以局部改善授予放行。主线程独立核41证据及128完整FF连接／参数、全部130追加字节；新135实际VO子门未跑，不继承134通过。未上板，原134冻结输入不改；下一W使用新源码与新身份退出无用MIDI链。


W的[普通合成MIDI遗留链退出](push2_workstation/usb_a/reports/DUAL138K_W_SYNTH_MIDI_RETIREMENT_20261101.json)已落实际维护源码：显式W revision4／`disabled_unused_synth_uart_v1`通过专用wrapper退出midi_uart／midi_bytes／midi_drops三实例、零绑字节／valid／drop／framing；PC UART、真实USB25K与CPU-session／PANIC独立路径保留，默认M预处理文本／实例层次一致。实际W134 VO确认UART valid恒0、payload/valid已sweep而空握手及drop诊断仍在；142bit唯一参数反馈专项通过。仅移除两条已退休Gray约束，旧W1/2/3合同及三memory特征严格保持，39独立负控拒绝。实际Wwrapper经生产C／MMIO／USB FIFO／CDC／生命周期／唯一参数／完整D与DDR／反馈通过28716帧、559事件、378点与9生命周期，来源17／demo18／audio-only5入口通过；主线程重验1201文件和88执行输入、11项源前后快照及严格patch逆向。两profile只提升M5／W8既有来源项，M显示两owner未提交改动与其旧HEAD锁保留。新prepare待M显示单独验证／刷新锁，未预记新VG、资源／时序或硬件收益；M22继续留板。


M的[实际显示组合路径平衡](push2_workstation/usb_a/reports/DUAL138K_M_DISPLAY_BALANCE_20261101.json)已落维护源码：producer把32bit epoch／sequence比较改为2bit XOR pair＋两级OR，原source_valid／context_break和同周期撤销保持；dashboard将文字word从坐标优先链拆为互斥并行选择＋平衡OR，保留if-X跳过、HMI最终优先级、metadata／hex／effect覆盖、四级使能与几何。完整producer21输出／5645819边沿与真实FFT／XY／wave publication对照通过；源抽取四态9472及漏bit负控通过。冻结M25整dashboard四配置×4194304完整11bit坐标、65536固定seed合法参数、48282 stalls及18354 X/Z向量逐像素／word／77bit metadata等价，两个执行负控拒绝，来源17项通过。主线程复核1156文件及严格before／after／patch逆向，两profile只更新两owner并新增定向回归锁，M867／W1114的1981来源全匹配且实际load通过；保留刚提交W revision4功能与全部source locks。此阶段不记物理收益、不操作板；新M137／W136后续各自全量综合及P&R，M22留板。


[M26／W24新整机来源准备](push2_workstation/usb_a/reports/DUAL138K_M26_W24_PREPARE_20261101.json)已通过：两者均从已提交69670c1d及prepare前原字节／工具快照取源，M身份`6e4fadc51e5a2888`、900原源／606暂存／262编译／1467工具，W身份`32ebb8aa64afa5e2`、970原源／610暂存／129编译／1467工具；分别使用M867／W1114锁与新物理编号D2110137／D2110136。主线程独立重验6030文件；M的259其余编译输入与M25同字节，W新配置实际采用专用无MIDI wrapper，三实例退出继续由新VG验证。两份全量综合已转入独立运行，物理资源／时序／板测随后实测记录，M22留板。M显示独立审查也已收口：65项hash、全11bit坐标域区域互斥、冻结旧像素oracle、四级CE suffix与producer撤销／状态字节均通过，无具体问题；相应证据已补入显示报告。


M26／D2110137的[全量物理结果与路由后门禁](push2_workstation/usb_a/reports/DUAL138K_M26_PHYSICAL_20261102.json)已完成：原DDR3.500ns与独立新VG保持，394.835s／exit0；物理BSRAM246／DSP116／CLS46694／FF43243／LUT48025／ALU11839／SSRAM99，setup0／最差+.007ns、hold0／+.143ns，recovery+2.843／removal+.275ns，指定DDR hold+.624ns。实际VO native60项45通过／15具名skip、boundary7项、performance17项、六PLL与七main负控、HMI八破坏控制单独通过；四张clk50表均非负，主线程重验完整冻结工具／物理／门禁证据。FS `97ee9868…36419f75`；仅离线通过，微小setup余量如实保留，未下载／未做声画硬件验收。板上仍为M22；M22-1新入口不复用此位流身份，另行全量综合／P&R。

M26／D2110137已按持续SRAM授权[下载并独立读回身份／状态](push2_workstation/usb_a/reports/DUAL138K_M26_SRAM_20261102.json)：原FS `97ee9868…36419f75`，写前M22／D211012F，op2成功后两次独立op0均为D2110137，op74状态00022230。没有Flash操作、逐位Verify或现场声画／Push／25K功能接受；板上现在是M26。原v1仅在收尾错误要求op74含UserCode，下载和独立读回均成功，v2保留原失败并只读复核，未重复下载。M26-1使用新身份D2110138并重新全量实现。

M26-1的[Session切率维护实现与定向离线回归](push2_workstation/usb_a/reports/DUAL138K_M26_1_PUSH_RATE_SOURCE_20261102.json)已完成：原始USB MMIO CC51独立于音频FIFO／停钟接入既有唯一服务，5ms释放去抖、忙／故障／过期代际消费拒绝且不排队，Select保持；实际已提交率及busy／fault以独立frame-frozen状态栏更新。真实USB→DCS→DSP／I2S双向1495帧（998@48k／497@44.1k）、1494显示PCM配对、6提交／1真实晶振故障与既有APB恢复、持音／尾音／PANIC／满FIFO和周期／静音／预填充检查通过，两执行负控拒绝；默认USB118182输出检查及原APB九次回归保持。状态栏215597像素及两负控通过；两个旧TF/BLE full-runtime fixture因冻结support接口过时编译阻断，未算通过。M876／W1123来源锁、17来源／18demo通过；这里只接受源码与离线范围，李萨如及新全量EDA／实际CDC／板测仍待完成，不继承M26位流。

W24／D2110136的[全量P&R与实际路由门禁](push2_workstation/usb_a/reports/DUAL138K_W24_PHYSICAL_REJECTED_20261102.json)已完成但完整STA拒绝：274.120s／exit0，物理BSRAM218／DSP59／CLS32139／FF27030／LUT30508／ALU11614／SSRAM177，setup31／最差−2.655ns、hold1／−.282ns，recovery+.754／removal+.281ns。31项setup全部来自BLE boot ID归一化到PCM session epoch，下一显式W将复用既有published_epoch寄存器；DDR原3.500ns保持，独立hold缺口继续实测。native60项／23具名skip、boundary7、PLL及142位反馈／110负控和无用MIDI三scope退出门通过，不转授完整STA或硬件接受。FS `c70e30f6…251d9ca`与全部33原始物理文件重验，未下载；下一W新身份D2110139。

M26-1连续XY与W25会话时序修复的[维护源码阶段](push2_workstation/usb_a/reports/DUAL138K_M26_1_XY_W25_EPOCH_SOURCE_20261102.json)已通过定向验证：M新trace叶子两态／四态各11帧／6247点／720896像素及四反例，保持L／−R、真实2048点、自动gain、原1bit ABI，仅当前与上一raw快照二值余迹，第三退出；PANIC真实tuple接收／丢失撤销74项及三反例通过，完整analysis on/off回归另跑不冒记。W新显式registered_controller_epoch复用原published_epoch，默认／旧W1-4与M保持；真实HCI/session默认三相位四反例、新三相位与high32 fallback五反例、268 native检查／11反例、110反馈反例及旧字典保持通过，synthetic重绑审查仅为离线证据。两profile M884／W1131锁、17来源／18审计／6HCI／8policy通过，M revision3／W revision5，分别D2110138／D2110139全量新实现；新实际网表／物理资源／完整STA与实板均待测，板上M26保持。

M26-1的[完整XY分析／runtime离线门及prepare来源修复](push2_workstation/usb_a/reports/DUAL138K_M26_1_XY_COMPLETE_PREPARE_FIX_20261102.json)已完成：7份真实2048双声道快照，5075874默认off周期与M26一致，786432像素／6144双声道频谱栏／192停读及两反例通过；实际完整runtime参数均为1，PANIC被接收或因停memory clock被丢失，两路均换代并清真实history，10发布／15commit／229070 tuple／69drop及原取消／双率／复位检查通过。最初M／W prepare被旧顶层storage-reference锁严格拒绝，原失败保留；只增加已知Session顶层四锚点的严格逆向／往返来源桥，旧hash与manifest不改，7测试／29负控及原完整source_bundle对照通过。M888／W1135来源门、17来源检查及旧M26 VG native60项／16具名skip通过；换新prepare目录继续，不把prepare或离线门当综合／板测。

W25已由664e2506完成新prepare（身份ff53a5420e3db5ed／975原源／613暂存／129编译），进入全量新综合。M26-1第二次prepare则因新增Push SDC在recognition适配之后、demo retirement之前追加而被旧recognition hash拒绝；新验证先严格恢复demo、再唯一精确去除新增Push后缀后验证原recognition，不改实际SDC或任何时钟。17来源／18审计及M来源门通过；失败目录保持，M使用新prepare目录，不复用不完整输出。

[M26-1／W25新整机prepare与冻结](push2_workstation/usb_a/reports/DUAL138K_M26_1_W25_PREPARE_20261102.json)已成功并由主线程重验全部原源／暂存／工具：M来自f2cbce53，身份3dbbf0577da87328／608暂存／263编译；W来自664e2506，身份ff53a5420e3db5ed／613暂存／129编译，各1488审计工具在prepare前捕获。两份已独立全量新综合，预留D2110138／D2110139；新增三条Push控制CDC、10位PANIC实际来源及W32Q仍须新实际VG／VO门，未预记资源／时序或硬件接受，板上M26不变。

M26-1的[全量新综合与物理启动](push2_workstation/usb_a/reports/DUAL138K_M26_1_SYNTHESIS_20261102.json)已完成：182.929s／exit0，610运行输入保持；新VG `e39eccbe…4c7b91e`，FF43627／LUT48834／ALU11484／综合BSRAM等价211／SSRAM99。strict通过，native60项43过／17具名skip及65负控、boundary7项／69负控、performance17项／8负控均通过。native旧库存断言先拒绝，独立v2只在显式connected_xy下按实际142FF＋98RAM＝240payload修正，HMI60及旧规则保持；10位PANIC来源／trust语义与新Push三CDC另验，不以库存替代。主线程重验3011文件；D2110138用新VG／原3.500ns DDR及M26仅定位配方独立全量P&R，128ref控制与DDR完整alias闭包明确核对，未继承旧route接受。新物理资源／完整STA／VO门和实板尚待结果，不下载，板上仍M26。

M26-1／D2110138的[首次完整P&R结果](push2_workstation/usb_a/reports/DUAL138K_M26_1_PHYSICAL_REJECTED_20261102.json)已封存并拒绝部署：669.482s／exit0，物理BSRAM251／DSP116／CLS47130；setup975／最差−1.178ns、hold3／−.114ns、recovery−4.037ns、removal+.275ns，指定DDR hold+.672ns且原3.500ns保持。实际路径明确指向新XY初始error、状态栏跨域复位释放及既有音频／显示控制；下一维护修复按实际路径推进，不放宽时钟或继承M22试装例外。32份物理文件由主线程重hash，原候选不改、未下载，M26／D2110137继续留板。

W25／D2110139的[完整新综合／P&R与路由门禁](push2_workstation/usb_a/reports/DUAL138K_W25_PHYSICAL_REJECTED_20261102.json)已封存：综合BSRAM等价192，物理BSRAM218／DSP59／CLS32197；P&R416.862s，setup0／最差+.001ns，hold仅DDR1项／−.310ns，recovery+.885／removal+.281ns。真实32Q路径及33负控、142位反馈及110负控、native60项／23具名skip／64负控、boundary7／69、四PLL及6负控均通过，普通合成MIDI三scope退出；主线程独立重验3138文件。已消除旧31项epoch setup，但未满足完整STA，不下载；同VG／CST／SDC的独立D2110140只测route_option1，不预记成功，DDR原3.500ns不变。

M26-1的[实测路径最小维护修复](push2_workstation/usb_a/reports/DUAL138K_M26_1_ROUTED_REPAIRS_SOURCE_20261102.json)已完成：状态栏业务寄存器复用既有pixel释放，零新增时钟／复位状态；XY仅增加本域准备拍分开绝对差与初始error，准备期间不写两类RAM、不步进，不影响采样；writer将快照身份比较改为并行4bit XOR归约，原同拍撤销／DDR节拍保持。状态栏215597像素／1138释放／728帧冻结及5负控、XY两仿真器与完整analysis（7帧／5082314默认off周期／786432像素／6144FFT栏）及7负控、writer106528四态谓词／615641旧周期／minor1完整传输及2负控通过；M890／W1137锁、17来源／18审计及双profile检查通过，主线程重验3391文件。旧D2110138的三Push CDC实际VG／VO及292＋41负控、PANIC／XY实际语义及20＋2负控亦完成，仍不覆盖旧STA拒绝。下一M以新来源重新全量实现D211013A，旧音频／显示setup和ref hold仍由实测收口，不预记收益或板测。

修复后的M26-1已完成[第二轮正式prepare及来源冻结](push2_workstation/usb_a/reports/DUAL138K_M26_1_R2_PREPARE_20261102.json)：来源c9bdae9d，身份`1ab654241de6eb73`，608暂存／263编译／1490冻结工具，主线程逐项复验。预留D211013A，已启动完整新综合；后续源码修改不进入本冻结闭包，原D2110138失败证据及M26留板身份均保持，未预记新资源／时序或硬件接受。

第二轮M26-1的[完整新综合与D211013A物理启动](push2_workstation/usb_a/reports/DUAL138K_M26_1_R2_SYNTHESIS_20261102.json)已完成：193.222s／exit0，610封存输入保持；新VG `9dad96de…47aa6f45`，FF43629／LUT48595／ALU11461／综合BSRAM等价211／SSRAM99，strict通过。实际native60项44过／16具名skip、66执行负控全部拒绝；仅显式connected_xy库存断言窄适配，原门不放宽。新VG／SDC经完整DDR及128ref来源闭包复核后全量P&R；此阶段尚无新routed资源／完整STA／硬件接受，不下载，M26留板。

W25的[独立布线／时钟定位试验](push2_workstation/usb_a/reports/DUAL138K_W25_ROUTE_CLOCK_TRIALS_20261102.json)已冻结139／140／141失败：140仅route1，setup0／+.012ns，DDR hold仍−.453ns；141的LOCAL_CLOCK被CT1018拒绝、实际未应用，STA与139相同，VO仅唯一CreatedTime行变化，不能算作新语义／资源结果。逐pin对照显示M/W该数据路径基本相同，W捕获clk50使用PRIMARY、延迟比M的LW多.988ns；已核对vendor文档LOCAL非LW同义词。主线程重验物理及证据输入，下一独立142只追加显式BUFG8选线并按实际分布／全STA判断，原VG／SDC及DDR3.500ns保持，不预记收益、不下载。

W25／D2110142的[完整物理及选定门禁](push2_workstation/usb_a/reports/DUAL138K_W25_PHYSICAL_20261102.json)已通过离线范围：434.069s／exit0，实际clk50为LW、44.1参考改为PRIMARY，setup0／+.013ns、hold0／+.140ns、recovery+2.376／removal+.281ns，DDR hold+.626ns且原3.500ns不变；物理BSRAM218／DSP59／CLS32197。142实际全STA／各时钟零TNS／脉宽和PLL及6负控重验，完整VO仅精确CreatedTime头与139不同，主线程独立证明该唯一逆变换并复验1536文件，复用139语义门而不冒称重跑。FS `0d5b7659…ce1c078`／CheckSum3575；等待现有授权的SRAM试装及真实手机／25K／DAC业务验收，仍不宣称全IO／电气／CDC或最终发布接受，无HDMI／录音范围保持。

M26-1第二轮STA已闭合，期间预备的[Delay私有数据路径化简实验](push2_workstation/usb_a/reports/DUAL138K_DELAY_COFACTOR_EXPERIMENT_RETAINED_20261102.json)未进入r2；完整补丁、3修改／5新增源码及3523032边沿／四态／映射FIFO验证已封存cache。只撤回逐字节核对后的本实验改动，使正式维护源保持已过物理的冻结来源，不记资源或时序收益；无用户未提交文件被撤回。


M26-1／D211013A的[第二轮完整物理与路由后门禁](push2_workstation/usb_a/reports/DUAL138K_M26_1_R2_PHYSICAL_20261102.json)已完成：596.598s／exit0，物理BSRAM251／DSP116／CLS47008／FF43629／LUT48476／ALU12036／SSRAM99；setup0／报告最小0.000ns（不记正余量）、hold0／+.126ns、recovery+.240／removal+.275ns，指定DDR hold+.605ns且原3.500ns不变。boundary7／69负控、performance17／8、HMI8、四张clk50实际表、六PLL／七负控通过；native原60项44过／15具名skip／1个fixture ROOT读源错误完整保留，只修临时wrapper ROOT后重跑该项通过，合计45过／15skip，59＋2负控拒绝，不冒称原整跑exit0。新实际VG／VO三条69bit Push控制mailbox、17个状态栏业务复位、10位PANIC及4history／8image RAM prepare门闭包均通过，26＋25综合控制、10＋7＋2新增路由控制拒绝，不冒称同核控制全部重跑。主线程独立重验冻结工具／物理／门禁文件；FS `414bd240…c09bc6f7`／CheckSum8096。这里只接受离线范围，完整IO／电气／CDC及现场声画／Push切率仍待验；将按已有SRAM授权试装，不写Flash、不把身份读回当功能验收。


W25／D2110142已按持续授权完成[短暂SRAM试装及独立身份／状态核对](push2_workstation/usb_a/reports/DUAL138K_W25_SRAM_20261102.json)：写前M26／D2110137，op2 SRAM Program成功，随后独立op0读回D2110142，op74为00022230；原FS／程序／日志身份一致，主线程复核1545文件。21201串口115200被动观察12秒0字节，没有取得CPU／HCI就绪遥测，不由此判定无线链路成功或失败；没有手机A2DP、25K启效／释放、DAC连续输出的实体验收，也无逐位Verify或Flash写入。这次仅为同一块138K的分时试装，之后已由M26-1新候选替换，不能算双板并发验收。


M26-1／D211013A现已按持续授权[SRAM下载并留板](push2_workstation/usb_a/reports/DUAL138K_M26_1_R2_SRAM_20261102.json)：写前W25／D2110142，原FS `414bd240…c09bc6f7`／CheckSum8096，op2成功后独立op0读回D211013A，op74状态00022230；程序／物理输入产物／日志重新核hash，没有逐位Verify或Flash写入。包含Session CC51按下切实际48／44.1k、唯一切率服务与实际状态栏、Select矢量，以及用户确认的浅底深色连续XY／自动缩放／当前上一raw二值余迹，M26音源与完整HDMI／效果保持。21201被动12秒0字节，没有CPU／DDR／音频就绪遥测；本机无HDMI采集或线路音频输入，现场新李萨如、持音／尾音／PANIC切率、HDMI不断画和DAC连续性仍未验收。当前最后一次读回的留板镜像为M26-1；掉电会丢SRAM，不据此推断Flash或冷启动。两角色本轮各有完整新P&R及SRAM身份记录，但真实业务／双板并发仍待，任务保持进行中。


W26的[A2DP真实能力声明修复](push2_workstation/usb_a/reports/DUAL138K_W26_DELAY_CAPABILITY_SOURCE_20261102.json)已落维护源码：冻结W25的pcm_media没有delay_valid事实，却在GetAllCapabilities公布08/00，手机选择时会以08/31拒绝；新代码仅A138_WORKER_AUDIO_ONLY退出这项无真实provider的可选能力，未经广告选择返回08/17，不造延迟值、不改D音频Delay效果。真实ACL相同请求对照旧947／新941×2检查及3执行负控通过；默认DelayReporting11199×2／18负控、Classic49640×2／15负控与真实SBC向量保持。实际W固件编译宏核实、ROM398f9677…d253ae3、ELFa15642d9…2396bf、栈上界896bytes；主线程用真实RV32编译器独立证明非W默认完整35552字节object相同（原raw预处理常数guard比较差异保留）。两profile仅精确刷新2来源并新增3测试锁，M893／W1140全匹配，17来源／18审计／8policy通过。预留新D2110143重新全量实现，未继承W142位流身份或时序／手机验收，M26-1仍留板；25K手机转发由用户自行完成，本轮不改25K。

W／M被动UART零字节的来源核对另已收口：实际debug_uart_tx确接U15上的PL runtime_serial，50MHz下每秒独立发送115200遥测，CPU／HCI／DDR／音频ready均只是payload而非发送门；因此零字节不是预期活跃遥测。现有硬件盘点只将21201识别为FT2232接口1候选，旧引脚核对要求确认核心板调试口／外接3.3V串口路径；未实测21201→U15连接或时钟／复位，不能凭本次空capture判断业务成败，也不因此篡改冻结候选。


W26的[正式生产prepare与预先来源冻结](push2_workstation/usb_a/reports/DUAL138K_W26_PREPARE_20261102.json)已完成：来源c7818498，身份`0a6b1eb610b17895`，975原源／613暂存／129编译／1492冻结工具，M893／W1140锁。实际生产指定xPack15.2、安装ROM `9f15d539…6ae487ea`／ELF `5c8c422f…d149e6b9`；先前源验证默认Homebrew的398f ROM另列，不混成同一构建。与冻结W25相比仅boot.mem及未启用HDMI源码两暂存项变化，129个启用RTL的路径／顺序／字节均保持；ROM仍是实际readmem输入，必须重新综合和全量P&R。新综合已启动，预留D2110143，不预记资源／时序／业务通过，不改M26-1留板。


手机配套的[当前可安装交付复核](push2_workstation/usb_a/reports/DUAL138K_ANDROID_CURRENT_DELIVERY_20261102.json)已完成：保留0.3.1-demo-d3／versionCode16和App业务源码／依赖，强制重跑83项单测（81过／2原实体skip／零失败）、35实际Gradle任务、构建／lint及API35独立模拟器5项instrumentation通过。正式App另经真实系统SAF选8秒静音文件，未选输出禁播、选本地扬声器后实际设备ID路由确认、播放／暂停均实测，静音夹具只验证手机文件／路由，不充当W音频闭环。主线程复验145来源／证据文件并查看截图；已将同一APK `c19645ec…139c5be`归档至本机ignored的`clients/android/artifacts/gowin-control-0.3.1-demo-d3-current-debug.apk`，README首入口从旧0.2.10历史说明改为当前安装入口。复用本机API35镜像创建cache隔离无窗口AVD，没有下载／改其他虚拟机。真实手机A2DP／BLE MIDI及W的D／25K／DAC仍待，25K→138K转发由用户实现，本轮不改25K。


M26-1的[普通立体声李萨如维护修改与正式增量核实](push2_workstation/usb_a/reports/DUAL138K_M26_1_STEREO_XY_SOURCE_20261102.json)已完成本次要求的首阶段：普通A/B/C使用17bit有符号R−L／L+R、两轴统一算术除2和既有gain／clamp，屏幕Y反向；同相竖线、仅左╲、仅右╱，矢量原直接L／−R保持。仅新M revision4显式开启；已提交scope_status[8]随真实PCM进入205bit held tuple，模式变更撤销完整／半帧窗口与raw余迹，默认204bit及旧M1–3保持。21份真实2048点快照、23492306旧矢量／默认逐周期、6815744像素、39936 FFT栏、全部8gain／负满幅／奇数／连续线／二值余迹通过；实际runtime5691 tuple／65模式撤销／6416点及7执行负控通过，主线程独立重验158测试证据。旧default-off完整analysis另跑7帧、PANIC74项／3反例及17来源／18审计／8policy通过；M897／W1144锁，W只精确刷新共享源与测试hash，音频配置不变。首次旧fixture漏接新可选端口的warning失败及context缺include失败均保留，没有改门限。

本轮未启动任何M综合、增量／全量P&R或烧录，未产生新位流，不继承D211013A的时序通过。正式安装文档确认Arora V支持`set_option -inc_pnr <旧.pr>`，当前工具非运行查询接受并保存该设置，M26-1原.pr及原FS逐hash保留；这只确认能力和检查点，尚未证明新网表实际复用。未找到公开支持的增量综合入口，本次算术逻辑也不是ROM初值更新，因此后续仍需新综合网表后再显式引用旧.pr做正式增量P&R；不得悄悄回退全量P&R或预记余量。板卡未操作，最后记录的SRAM仍D211013A，新增坐标尚未上板；主目录原9个未提交项与25K由用户自行修改的职责均保持。


此前冻结W26／D2110143的[全量新综合、独立P&R及实际门禁](push2_workstation/usb_a/reports/DUAL138K_W26_PHYSICAL_20261102.json)已完成：来源c7818498、身份0a6b1eb610b17895和原W1140锁，生产xPack ROM9f15d539…6ae487ea；综合113.562s／615输入不变，VG39401fc4…26ced6a6；新P&R437.429s，物理BSRAM218／DSP59／CLS32197／FF27030／LUT30655／ALU11607／SSRAM177，setup0／+.013ns、hold0／+.140ns、recovery+2.376／removal+.281ns，13时钟TNS／端点均0、最差pulse+2.851ns。实际DDR保持原3.500ns关系、hold+.626ns；只复用W142的CST定位配方，未复用旧时序或语义接受。新VG和实际VO的epoch32Q／33负控、142bit反馈／110负控、boundary7／69负控、PLL及6负控均新跑通过；native主矩阵60项实际36过／24条件skip，另补vendor注册RAM单项通过，64负控拒绝，不把skip算通过。初次strict省略INIT0表示及PLL缺显式simlib的工具失败保留，分别只在cache做精确vendor模型适配及补安装模型路径，未改冻结工具原本／RTL／时钟。

W26新VG与实际VO各64颗pROM全部32768word重建等于实际生产ROM，未误用源阶段Homebrew398f镜像；FS `4b76a2c5…e30b755af`／UserCodeD2110143／CheckSum3575，独立重核4827文件（含4825份完整输入／工具／物理证据）。本轮后台W全量实现与M坐标修改独立：未对M启动综合／P&R、未操作板卡，新M revision4／1cf5bf83未混入冻结W26。W仍显式无HDMI／录音的D音频候选；真实手机A2DP、25K组合按下／释放／断连、连续DAC和完整IO／电气／CDC及双板并发尚未验收，release_ready=false；最后记录的SRAM仍M26-1／D211013A。


M26-1新普通立体声XY的[正式prepare与原检查点增量输入准备](push2_workstation/usb_a/reports/DUAL138K_M26_1_STEREO_PREPARE_20261102.json)已完成：来源ada8cf9e（含1cf5bf83坐标维护修改），新M revision4／897锁，身份cf7678174e8941a7，905原源／608暂存／263编译／1496审计工具在prepare前冻结，主线程重核3009文件。相对M13A只有四个编译输入、include的HDMI provider及显示契约共六份暂存文件变化，其余RTL、两套固件及全部SDC逐字节相同。第一阶段仿真和正式增量能力核实已先完成；本次逻辑不能仅改ROM／旧位流，安装工具未暴露增量综合，因此现在生成新的正式VG，再仅允许显式`-inc_pnr`引用原M13A .pr的增量P&R，预留新身份D2110144。旧.pr／FS及原CST／SDC保留；增量失败即封存停止，不自动全量P&R，不继承旧余量或硬件接受；板卡未操作。


M26-1新普通立体声XY的[完整新综合与严格网表检查](push2_workstation/usb_a/reports/DUAL138K_M26_1_STEREO_SYNTHESIS_20261102.json)已完成：170.488s／exit0，610封存输入前后保持；新VG `eaac0fa2…76a16f7`，FF43632／LUT48626／ALU11495／综合BSRAM等价211／SSRAM99，非物理资源。原strict因新增observation bit204库存拒绝的失败保持，独立v2仅对显式M revision4／精确axes policy增加同tuple位检查，默认／旧M／W不放宽；1496原工具不改，临时3文件完整精确patch和退出计划入报告。strict原有角色／32声部／完整效果／HDMI／时钟／CDC／SDC门通过，主线程独立重验4512来源及工具／网表／证据文件；新bit204实际来源和算术消费、完整native等附加门另验。正式增量输出仅允许引用原D211013A .pr，检测匹配不足或自动default/full即终止；尚无新P&R／位流／时序结果，本阶段未操作板卡，不继承旧余量。


新M26-1的[实际VG语义／完整附加门与首次增量停止记录](push2_workstation/usb_a/reports/DUAL138K_M26_1_STEREO_VG_INCREMENTAL_STOP_20261102.json)已封存：新增bit204从权威矢量提交点经同PCM held tuple进入模式／context；33bit输入全部2^33算术赋值、8gain归一化／clamp／真实屏幕Y消费、模式撤销及history/front复位闭包通过，16真实cell＋11配置＋25原PANIC/history负控拒绝，独立审计复跑通过。native60项44过／16具名skip及66负控；boundary7／69、performance17／8、新VG三Push mailbox共69bit及17业务复位／308＋26负控通过。早期fixture库存失败及精确修正保留，主线程重验3727文件。

首次正式`inc_pnr`调用虽在实际cmd.do携带原.pr，但未取得CT2074或matching/reuse正证，工具进入placement及部分routing后已人工SIGTERM（578.224s／child−15），无新FS／VO／TR／PR，不构成新时序或增量成功。监控器`\bRunning placement`被工具实际`$数字`前缀粘连绕过的缺陷如实保留；独立v2以真实日志／碎片／无换行／CR等18实际子进程回归通过，未改原runner或重跑EDA。3653封存输入及原BASE32文件集合／字节全同，原回退位流和板上记录不变。未证明工具自动full回退，也未调度额外full；继续核实安装版后端正式增量接口，不自动全量P&R，不借密文checkpoint差异推断布局复用。


用户本次明确授权“先帮我把M26固化进138k”，已完成[原版M26配置Flash固化、独立校验及重载](push2_workstation/usb_a/reports/DUAL138K_M26_FLASH_20261102.json)：使用原冻结D2110137／身份6e4fadc51e5a2888／FS `97ee9868…6419f75`／CheckSumDDB9，不包含M26-1的Session切率与新XY修改。写前独立读回M26-1 D211013A；当前138K／Flash0B4018核实后，op54从0x000000写至工具报告0x0506A00并Program and Verify成功（102.927s），独立op66再Verify成功（31.409s）。随后op24擦SRAM、op1从Flash重载，独立op0读回D2110137／00022020，op74再次确认00022020；全流程无SRAM Program，54份原物理／来源证据及位流前后hash保持。op54最初结果匹配器漏识别安装工具的成功文字而标false，原log／事件保留，单独精确适配后op66结果为true；不是硬件失败或重写。当前板上及配置Flash均为原版M26；仅软件重载已验证，未进行物理断电或新的HDMI／DAC／Push功能验收。主目录9个未提交项及本工作区其他审计／profile未提交工作均保留，M26-1维护源码和已停止增量证据不撤回。


[W26 SRAM deployment for user hardware acceptance](push2_workstation/usb_a/reports/DUAL138K_W26_SRAM_20261102.json) completed under the latest explicit user request. Frozen candidate 0a6b1eb610b17895 / D2110143 uses FS SHA256 4b76a2c5b991cbd268b2e72f2cc9f8538e7ad8ea23fbac677b82372e30b755af / CheckSum3575. All 19 programming inputs and physical evidence files remained unchanged. Before programming: M26 D2110137 / 00022020. SRAM Program (op2) exited 0; independent op0 then read D2110143 / 00022230, and op74 confirmed the same status. All 20 independent review checks passed. W26 is now left in SRAM for real phone streaming D, 25K combined press/release and disconnect cleanup, and continuous DAC acceptance; HDMI, recording and downloads remain absent. Identity readback does not establish those functions or bitwise SRAM verification. No Flash write was performed; the previously programmed original M26 configuration Flash remains, so a power cycle or explicit Flash reload returns to M26. No fresh Flash-byte readback or physical power cycle was performed. M26-1 source, other uncommitted work and the primary checkout remain protected; sequential testing on one board is not two-board concurrent acceptance.


### 2026-11-02：接续其他会话 W B5 与独立 BLE 录音分线

用户最新授权两线并行、JTAG串行及通过门禁后的SRAM复测，本轮不写Flash。真实vivo Y77/Android12已ADB授权，现装0.3.3-ble-lifecycle/code18，不再仅有模拟器。W音频线继续显式无HDMI／录音下载配置；独立BLE候选复用A25D/C1协议、真实最终PCM与16384帧短录音RAM，必须新身份及全量实现后验证连接／状态／非静音录音／完整CRC下载。A25D ROM数据、C1历史全零PCM均不作为真实乐音验收；25K转发仍由用户自行修改。

已只读参考“执行最新 task.md 任务”的codex/w26-phone-audio工作树，精确迁入SSP请求策略／事件顺序修复及已有ACL诊断，不合并其M/显示差异。当前分支重新通过来源17项、security原生及sanitizer各17904检查、W session各3284检查及32变异；runtime 11个SBC用例原生及sanitizer各3759检查、15+9变异均通过。独立的既有M stereo审计维护13项／资格负控通过，未重新实现M位流。

[W B5来源、物理门禁与SRAM证据](push2_workstation/usb_a/reports/DUAL138K_W_PHONE_B5_REUSE_20261102.json)：复用c83a2639会话已完成全量综合／P&R的候选dc79a470bb3e8135，物理D21102B5，FS SHA256 dfbcd2d458d47345d8853e2a4a9983db2158bd372589beaa238fcd28417c5a19。14域setup/hold端点均零，最差setup/hold/recovery/removal +.013/+.092/+2.376/+.281ns，PLL及四项实际routed CDC通过。功能LUT30655／FF27030／BSRAM218／DSP59，GAO另占BSRAM9；这不是本工作树新跑第二次P&R。重新逐hash验证封存输入及门禁后，已从D21102B4串行SRAM下载并独立读回D21102B5／00022230；当前板上身份以此替代前条W26记录。手机配对／A2DP及D／25K／连续DAC尚未验收，BLE录音线尚未上板。Flash未写，主目录与其他工作树保持。

### 2026-11-02：Android 生命周期迁入与短录音时长显示

精确迁入 origin/main f1839911 的 v18 生命周期修复，保留 app→data→ble→protocol、本分支原 DELIVERY_CHECK 文档、原 UUID 和录音下载协议。新候选 0.3.4-recording-duration/code19 补真实采样率下的毫秒时长显示：4800/48000 显示 00:00.100，16384/48000 显示 00:00.341，避免短录音显示为零秒。工作站和25K MIDI连接独立，本地音乐和选文件流式入口保留；25K转发由用户自行修改。

[源码和离线验证](../../clients/android/reports/RECORDING_DURATION_20261102.md)：31项定向通过，完整111项中109通过、2项既有无线项跳过；APK和测试APK编译通过，lint零错误。真手机导出的现装v18 APK SHA256实测 d3160a8e539cb357bd25bfe75c7a8defc84f84c84cf1b656299a2631008bf0af，实际证书6aedebb7…；本机新debug包证书be0b935e…不匹配。v19先归档，不卸载、清数据或降级手机；现装v18继续实测。本阶段未声明v19实机或非静音BLE录音通过。


### 2026-11-02：独立 BLE 真实短录音候选源码阶段

新增显式 custom138k-workstation-ble-demo-v1/revision1，复用维护 M 基础乐器及最终串行 PCM，以原 C1 的 EXTERNAL_PCM=1 RAM 路径接通独占 UART/H5/HCI/GATT 与16384帧短录音对象。保留原 A25D/C1 的 UUID、状态、CRC和可靠下载协议；不修改25K，不启用已退出的CPU录音后端、cue、TF或CNN。W音频配置不增加业务GATT或录音，M/W默认配置和冻结输入不变，共享工具仅追加显式BLE选择。该候选仅为短录音验证，不代替最终唯一DDR长录音后端目标。

[来源、配置与回归](push2_workstation/usb_a/reports/DUAL138K_BLE_DEMO_SOURCE_20261102.json)：来源锁899项逐hash核对；新配置及保留策略5项、原UART/H5/GATT／真实立体PCM CRC及下载8项、既有DEMO策略8项、DEMO审计18项、performance7项及当前来源17项通过。独立只读复核无重大问题。既有stereo VG仅用于资格检查，不冒称新BLE综合网表。新候选仍需全量综合、P&R、PLL／时序／真实CDC与资源门，预留物理身份D21102C1；连接／状态／非零乐音录音／CRC下载均待实板。SRAM由root串行，不写Flash。


### 2026-11-02：BLE 独立候选全量综合与实际网表门通过

[新全量综合证据](push2_workstation/usb_a/reports/DUAL138K_BLE_DEMO_SYNTHESIS_20261102.json)：源HEAD4b964e0d，候选e06ff364b0467886，正规prepare封存608项staged、263项compiled和1499项工具；新全量综合299.856s／exit0，所有封存输入保持。实际综合FF50329／LUT63860／ALU13590／BSRAM等价274／SSRAM151，非物理BSRAM计数，未预记资源收益。新VG严格门核32声部、完整HDMI／效果、7个唯一BLE owner、16384帧真实PCM RAM36、98bit实际源D／目标D／heldQ及两侧时钟、native held与实际SDC选择器；未使用旧VG冒称新实现。

首次检查器因Gowin映射端口拆名而拒绝，错误保留；v3仅按实际PCM源／目标逐位D/Q及原时钟关系补精确mapped审计，新增8个实际VG反例全部拒绝，6项新回归和18项原审计通过，新checker独立封存。独立DDR加密模块与128参考FF控制复核只允许复用定位配方，不能继承M26的路由／时序。新PnR随后独立运行；PLL、完整STA、实际routed CDC、实板录音及下载均待通过。W B6开始后的改动未混入该封存候选。


### 2026-11-02：W B6 实际控制器身份与扫描状态源码

手机清理仅RTK旧绑定、蓝牙重开及B5同位流SRAM重载后，fresh inquiry可见通用RTK名，但本次手机HCI显示CreateConnection返回0x04 page timeout，无ACL，不能冒称SSP或A2DP通过。B5实际H5失链sticky fault为0；初始化controller epoch来自LE_Rand，重载后变化不能误报成重复复位。原ReadBDADDR结果因debug未被消费而在B5网表裁剪，当前手机目标地址尚不能证明就是本板。

[W B6源码与回归](push2_workstation/usb_a/reports/DUAL138K_W_B6_IDENTITY_SOURCE_20261102.json)：session-only服务通过唯一CPU/HCI owner在既有WriteScanEnable3后读取真实BD_ADDR并回读ScanEnable3，两项成功后才ready；默认durable顺序保持。PL仅在显式SESSION_ONLY_PAIRING允许无参数1009/0c19，物理命令信用、私有副本、epoch和原owner2完成不变。既有48bit诊断在首ACL前显示实读地址，故障明确输出FC各层原因，保留首close／ACL，不再用永久CPU1掩盖runtime fault。

Security default原生／sanitizer各52747检查，W session各37736检查、32变异拒绝；runtime 11用例各4209检查、15+9变异拒绝；原生HCI268检查和11变异、两策略各1315实际包／信用检查和7变异、来源17项通过。独立源码复审无重大问题；对象增量据实记录，尚无整机链接／新全量综合／P&R／实板结论。新物理身份预留D21102B6，保留冻结B5及BLE C1候选，随后独立全量实现；本轮Flash不写。


### 2026-11-02：W B6 新全量综合与严格网表门

[W B6全量综合证据](push2_workstation/usb_a/reports/DUAL138K_W_B6_SYNTHESIS_20261102.json)：来源9bcb938b，新候选0d623a4cb68e2b0d，正规build.py显式W配置；613暂存／129编译／977来源及1499工具封存。新全量综合113.688s、exit0，615输入前后不变；实际VG4be691f0…5015e10，严格W音频／完整效果与流式Pitch／USB Host反馈／HCI epoch及源CDC门通过，HDMI与录音仍退出。综合FF27030／LUT30943／ALU11254／BSRAM等价192／SSRAM177，非物理资源，不预记收益。实际AE350 ROM3eeae0aa…b59984，ILM正文29856＋常量976＝30832字节，DLM静态7024字节，原16384字节栈未扩容；ROM与ILM分开统计。

B5定位配方已用新VG完整DDR模块、app_cmd完整cell及128参考FF逐一核实，只允许复用CST／SDC定位，不继承route／时序。新物理身份D21102B6随后独立全量P&R及门禁，仍需读回真实本板蓝牙地址、手机A2DP与D／25K／连续DAC实测；本综合阶段未操作板卡、未写Flash，冻结B5及BLE C1输入保持。


### 2026-11-02：BLE C1 全量物理实现完成，完整 STA 拒绝部署

[新全量物理证据](push2_workstation/usb_a/reports/DUAL138K_BLE_DEMO_PHYSICAL_REJECTED_20261102.json)：冻结源 HEAD `4b964e0d`、候选 `e06ff364b0467886`，物理 `D21102C1`，新 VG／SDC 全量实现 694.926s／exit0并生成位流；这仅表示工具执行完成。真实物理 Logic78900／CLS57042／FF50329／BSRAM314／DSP116／LUT63734／ALU14260／SSRAM151，综合 BSRAM 等价274单列，未预记收益。完整 STA 有 setup1567端点、最差−1.209ns，hold0／最差+.143ns，recovery+2.129／removal+.275ns；audio1361、DDR UI121、video pixel44、50MHz15端点违例，因此拒绝时序及部署准入。原 DDR3.500ns关系与far／128 reference放置配方保持，指定DDR hold+.743ns。

FS SHA256 `c5136b47854046b634fe5c8ef3fefb581be1d36f6a20fba9ccc4ff8af8de6d92`，全部32物理文件及16项measurement绑定复验。独立实际路由检查98+98个PCM CDC FF的D／Q／CLK／CE／CLEAR逐bit保持，绑定真实完成串行PCM／sequence／epoch／error／rate；7个owner类型唯一性来自实际VG，扁平VO只确认叶scope，不伪称重证层级。PLL子门因维护DDR configuration path审计exit1未通过，原失败日志保留，完整CDC亦未准入。C1未下载SRAM或写Flash，连接／状态／非静音录音／完整CRC下载均未验；下一轮仅为BLE显式选项修复实测glide与XY路径，默认M/W保持，其他多域违例仍需新全量P&R，不能预称两处修复即可闭合。


### 2026-11-02：W B6 全量 P&R 与本次实际门禁通过

[W B6新物理证据](push2_workstation/usb_a/reports/DUAL138K_W_B6_PHYSICAL_20261102.json)：新候选0d623a4cb68e2b0d／D21102B6独立全量P&R313.956s、exit0，全部输入保持；FS6105a594…7de29fd。实际功能FF27030／LUT30851／ALU11611／CLS32561／BSRAM218／DSP59／SSRAM177；GAO另9 BSRAM，合计227/340，综合等价192单列。14域setup／hold端点均0，最差setup+.004／hold+.092／recovery+1.901／removal+.301ns，pulse-width门通过；未放宽时钟／例外。原DDR3.500ns关系及实际定位保持，本次指定hold路径单列于报告。PLL／启动及6执行负控、四项实际VO／SDC正向CDC门全部通过，CDC旧负控未冒称本轮重跑。

实际AE350新VG和VO各64颗pROM全部32768word重建等于生产ROM3eeae0aa…b59984，非USB固件校验替代。160bit既有GAO仅精确修正5个新别名并核唯一FF／consumer；48bit CPU源于ram_clk、其余112bit源于clk50，诊断抓取不宣称原子快照。cache准备的错误同域假设、PLL调用缺import路径和非GAO测量器旧FS文件名三次前置失败保留，分别精确修正，没有改电路／约束／门限。新位流随后按已授权流程串行SRAM；本阶段尚未部署、不继承手机A2DP或D／25K／DAC硬件接受，Flash未写。


### 2026-11-02：W B6 已授权 SRAM 下载与真实手机首轮

[W B6 SRAM与首轮手机证据](push2_workstation/usb_a/reports/DUAL138K_W_B6_SRAM_20261102.json)：原D21102B5核实后，使用新FS6105a594…7de29fd执行op2，随后独立op0读回D21102B6／00022230，op74再次确认；全部输入保持，未进行逐bit SRAM读回。当前138K SRAM以B6为准，Flash未写，原M26 D2110137固化镜像及B5 SRAM回退文件保留。

既有正式HCI服务已真实读出本板BD_ADDR34:20:03:3D:8A:62，回读ScanEnable3并完成0c19/0，现有诊断所有观察到的owner fault为0。真实vivo手机向此地址首轮配对仍返回ConnectionComplete status0x04/page timeout，未建立ACL；板端地址诊断保持，无首ACL／close。不把静态名称、旧手机环或身份读回当作SSP/A2DP通过。继续核对fresh inquiry与空口接入前原因；D实时效果、25K按下／释放／断连及持续DAC均待真实流式输入后验收。


### 2026-11-02：近距离手机复核与 C1 PLL 补充

[本次补充证据](push2_workstation/usb_a/reports/DUAL138K_B6_NEAR_PHONE_C1_PLL_ADDENDUM_20261102.json)：用户已将手机靠近并确认天线连接，且只有138K蓝牙模块供电。BT重开后的真实fresh inquiry含本板地址，近距记录RSSI约−76…−74dBm；再次配对仍page timeout0x04／无ACL，B6正式地址／Scan3诊断保持，未观察到owner fault。不将无第二模块与无软件fault推断为空口或射频正常；开始显式W正式startup的无用LE广播退出及唯一Classic名称受控对照，不先认定因果，默认M／durable及独立BLE保持。

C1首次PLL子门错误已独立定位为macOS未自动找到官方gw5a模型；显式GOWIN_SIMLIB后在新workspace复跑原完整门通过，6 PLL／7负控／held门均通过，708项独立依赖与输出hash复核，原失败日志和已提交报告历史不改。C1完整STA仍1567 setup／−1.209ns，仍拒绝部署、未烧录。此补充不产生新位流，不写Flash；当前SRAM仍B6。

### 2026-11-02：Android 演示页面与实际计时《小星星》录音

按用户临时优先级，本轮仅完成 App：蓝牙／MIDI／录音页面去除开发者说明与冗长免责声明，原本地入口显示为“扫描并接入 138K”；真实 BLE 扫描保留。点击录音后按实际时间增长，停止或录满才封存《小星星》短旋律，再经原协议下载与 WAV 保存后试听，内部保留来源元数据。[阶段报告](../../clients/android/reports/PRESENTATION_20261102.md)记录 v20／0.3.5-presentation 身份、源码 hash、APK、日志与边界；[Push 演奏顺序](../../clients/android/docs/TWINKLE_PUSH.md)已核对冻结 M26 实际映射。114 单测中112通过／2既有无线跳过，9项模拟器完整界面回归通过，lint零错误／警告。vivo实机独立包安装成功，原v18与数据保留；6.037秒录音WAV、前11个完整音符与本应用MediaPlayer实际启动／结束已核对。此为本地演示验收，不转授为138K无线或DDR录音完成；本轮未操作板卡、EDA、SRAM或Flash，M/W及其他未提交工作保留。

### 2026-11-02: Independent CNN-DEMO historical trace and custom carrier

[Trace and targeted evidence](push2_workstation/usb_a/reports/DUAL138K_CNN_DEMO_TRACE_20261102.json): source 8bc80e9 and the full83 user acceptance record were verified. TRAVLER, WAV 48 kHz, model E / CRC32 AF01A61B remain the target; historical static_timing_closed=false is preserved. The local and remote acceptance tag is absent; the recorded acceptance JSON and complete source commit remain available. The custom carrier Netlist_my_138k_2026-10-21.tel and amplifier/Bluetooth netlists were recovered from the local locked archive and hash checked. No official-carrier bitstream is used. Current source boundary 17 tests, Push guidance/lights 2 tests, TF DMA, and candidate full83 Viterbi 172 frames x 89 states / 28 notes passed; the old map negative control failed as expected. The new explicit build.py --cnn-demo is undergoing actual compilation, retaining historical CQT/CNN BSRAM caches and original score/Push rules plus native USB and FPC audio. Model startup still requires manual BPN1 UART loading into DDR and CRC readback status E. New synthesis/P&R/PLL/STA/CDC and real Push/TF/CNN/DAC acceptance remain pending. No board action or Flash write was performed. Existing dirty M/W/BLE work and frozen candidates remain protected.


### 2026-11-02: CNN-DEMO explicit source, real inference regression and first physical measurement

[Source and validation evidence](push2_workstation/usb_a/reports/DUAL138K_CNN_DEMO_SOURCE_20261102.json) and [operation/source policy](push2_workstation/usb_a/rtl/workstation/CNN_DEMO.md): added the independent build.py --cnn-demo configuration on the locked custom carrier. It retains actual TF/WAV, original full83 model E / AF01A61B, the explicitly pinned six timing85 fixes, CQT/CNN/BSRAM/Viterbi, original Push selection/guidance, dry basic instrument and native DAC. HDMI/LCD, AE350 graphics, framebuffer, visual FFT, full effects/vector/BLE/recording/rate-switching paths are absent from the measured synthesis hierarchy; other profiles and frozen sources remain available. UART model upload is manual and ready only after DDR CRC status E.

Selected-source offline checks passed: source boundary 17, original Push/lights 2, uninterrupted 1340 sample ticks with actual serialized nonzero DAC PCM and PANIC/detach, and full 172-frame Viterbi oracle with 28 notes. The joined WAV->CQT->six CNN layers->Viterbi->original guide test decoded 95625 PCM samples, made 4407158 actual model reads, emitted one computed target, blocked the wrong key, advanced the correct key, and cleared old guidance on restart. Its generated audio and behavioural model preload are explicitly simulation-only; they do not establish physical TF/TRAVLER or UART acceptance.

The first new full P&R D21102D2 completed with 42031 logic / 145 physical BSRAM, but failed STA (setup -3.137 ns, hold -4.548 ns); it was not deployed. Measured follow-up fixes isolate the model UART from performance events, buffer basic-instrument event fanout, synchronize diagnostic/error levels, restore actual Push model/TF failure status, and use the locked timing85 changes. Candidate-v8 ad205f0df5065543 is undergoing fresh synthesis/P&R/PLL/STA/CDC; no gate is inherited or waived. User confirms Push/TF are present but the board is not connected to the computer. No JTAG/SRAM/Flash action occurred; current W SRAM and M Flash remain the rollback pending actual identity readback.
