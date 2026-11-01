# Task3：最终双138K工作站

修订：2026-11-02，Asia/Shanghai。本文取代原未跟踪规划中“全部效果和可视化计算必须留在M”“先恢复完整M再加TF/CNN”的限制。目标是两板承担实际计算和存储，降低M资源、关键路径与布线压力。阶段状态只按本候选证据更新；源码、子系统综合、整机P&R和实板验收分开。

## 1. 独立工作与回退

- 本轮目录：`/Users/sphenicidition/.codex/worktrees/dual-138k-task3/Gowin_Synthesizer`；分支：`codex/dual-138k-task3`；起点：`cfad079f1640f44602f31d69b18084a3d429d226`。
- 参考目录：`dual-138k-workstation/Gowin_Synthesizer`。其task2、M24正在推进的候选和未提交的W流式Pitch工作继续由原分支维护；本轮不切分支、不搬走脏文件、不改其构建目录。原task3是被忽略的本地文件，已只读备份；本分支将修订稿纳入版本管理。
- 单板主目录仍为`/Users/sphenicidition/Documents/Gowin_Synthesizer`，起点`ba2ba027`；其未提交录音工作保持原地。最终CPU/BLE录音整合不能复制回已退出的第二套后端。
- task2当前M演示和W蓝牙流式D模式继续推进。task3不要求先完成task2全部功能，也不把task2的W临时USB/DAC输出当作最终接线。
- 用户确认：两块目标板默认尚未接电脑；当前连接的138K供另一个分支使用，本轮不操作。LCD排线为反序线，TF在M，蓝牙模块可以接任一板。必要SRAM验证已授权，但仅在目标板到位且身份、电气、候选门禁确认后执行；Flash须另行授权。

工程遵循[架构](../../docs/architecture/README.md)、[整机接口](../../整机接口规划.md)、[原生组合](push2_workstation/usb_a/rtl/workstation/README.md)及[冻结输入](push2_workstation/usb_a/baselines/README.md)。accepted full83、timing85、resource-timing与DEMO保持各自来源；不改冻结基线、供应商字节或历史报告。

## 2. 赛题基础与项目扩展

依据[赛题原PDF](../../docs/requests/全国大学生嵌入式芯片与系统设计竞赛'2026FPGA赛道选题指南-高云半导体.pdf)第15–16页（正文13–14页），并对照[汇总](../../docs/requests/赛题2：实时多音色合成电子乐器引擎信息汇总.md)。表格经验答复与指南要求分列，不能用经验答复豁免基础指标。

| 类别 | M必须独立保有或项目必须保留的能力 | 验收 |
|---|---|---|
| 基础 | 至少二维独立演奏交互；FPGA HDL逐音、逐样本实时合成；至少4个独立声部；实时变调、ADSR、混音；I2S→真实DAC | W缺席、链路拥塞、识别/下载繁忙仍能演奏；按实际传感器/USB输入、FPGA执行、I2S和可闻输出分段测量控制到声音≤10ms |
| 既有项目目标 | 32声部、普通A/B/C与矢量音源、已有音色/力度/滑音/颤音、双率及实际参数反馈 | 保留现有实现和32声部目标；基础4声部是赛题下限，不是默认降级配置。任何临时裁剪必须列出原因、候选和恢复条件 |
| 赛题扩展 | ≥32复音或合规并行算子；≥3维表情、≥2音色、FPGA效果、≤5ms、实时可视化、演奏指引、手机联动 | 逐项提供真实音频/显示/交互证据；重型计算可分担到W，仍由FPGA完成相应DSP/可视化计算 |
| 项目扩展 | TF真实选曲/直读、CNN→Push跟奏、手机流式D、长录音/可靠下载 | 不用TF预录PCM或手机推流替代基础实时合成；真实模型、实际对象和完整路径分别验收 |

## 3. 起点证据与第一步迁移

M24当前已退出CNN、TF、录音和蓝牙。因此迁走这四项只能避免恢复时继续压M，不能声称减少M24现有开销。[M23物理证据](push2_workstation/usb_a/reports/DUAL138K_M23_DIRECTED_PHYSICAL_20261101.json)为BSRAM246、DSP116、CLS46460，最差setup −0.556ns、hold无违例，未上板；失败路径涉及效果调度、混响及显示坐标。M24修复另有[固定prepare来源](push2_workstation/usb_a/reports/DUAL138K_M24_PREPARE_20261101.json)，其整机结果由task2继续独立登记，不继承通过。

只读核对M24实际VG，混响子树有20个SDPB、19个MULT27X36；显示分析子树有26个SDPB、1个SDPX9B、5个pROMX9及乘法器。它们是**综合原语清点**，不能直接等同物理BSRAM或整机节省量。

第一步先实施实际混响计算/历史存储的M→W源码拆分，接口见[迁移契约](push2_workstation/usb_a/rtl/audio/REMOTE_REVERB_PARTITION_CONTRACT.md)：M保留有界本地截止时间及原始dry回退，W运行维护的真实双率空间混响。用同源、同工具、同动态输入的完整效果链LOCAL/M及W子系统综合，核对M中混响RAM/DSP确实退出。此阶段不选定生产LCD PCM配方，不上板，不宣称整机时序闭合。链路实测不能满足截止时间时，该实时往返方案不得启用；继续用异步分析/CNN/录音迁移减压，再评估增加有界流水预延迟或其他效果划分。

此拆分已完成[同条件Gowin V1.9.12实际子系统综合](push2_workstation/usb_a/reports/DUAL138K_TASK3_REVERB_SYNTHESIS_20261101.json)，来源`06c55d8a98c277b7ba64fc3854b92ce335d09195`，清单SHA256为`5b7e0c9533d495b003faba50e832b5e06e4fc8b53789aafacadf6c6c6af0a097`：

| 实际综合原语/实例 | LOCAL完整效果链 | M完整链＋远端代理 | W真实混响子系统 |
|---|---:|---:|---:|
| 本地真实混响实例 | 1 | 0 | 1 |
| SDPB | 24 | 4 | 20 |
| SDPX9B | 8 | 8 | 0 |
| MULT27X36 | 28 | 9 | 19 |
| MULTALU27X18 | 1 | 1 | 0 |

M相对LOCAL确实减少20个SDPB、19个MULT27X36，混响运算与历史存储出现在W网表；另有ALU−1815、DFFCE−2412，不能直接折算成整机CLS/物理BSRAM收益。三个对象仅为动态内部接口子系统，没有引脚分配、整机P&R或位流（均`null`）；不能烧录，也没有实测控制到声音/LCD延迟。完整M/W profile仍待原生包装层传播、链路测量后注册，不刷新task2的旧来源锁来冒充兼容。

## 4. 分工与数据权威

| 子系统 | M：本地演奏、提交和最终输出 | W：实际计算和本地存储 |
|---|---|---|
| 交互/参数 | 唯一最终session、PANIC、公共参数接受/实际应用；Push与25K交替接M同一USB口，按实测协商速率验收 | 手机请求适配/代理，只消费M已提交版本；结果不能直接改第二套参数 |
| 基础音频 | 32声部普通/矢量合成、ADSR、实时变调、混音；最终音量/静音、采样调度、I2S/DAC | 不成为基础演奏的必需往返节点；以后扩展合成须保留本地基础路径并单列资源/延迟 |
| 重型效果 | 保留有界调度与dry路径、实际效果状态、输出选择；本地/远端处理按测量选配置 | 第一迁移候选为真实混响及其历史RAM；继续按真实关键路径评估Delay/Chorus、D专有效果；不伪称尚未选入整机的功能已迁移 |
| TF | 卡实际接M：唯一SPI/SD/FAT/目录/文件游标；真实选曲及直读播放；输出/分析PCM分开 | 不直接访问M的TF/USB/DDR；接收明确任务的分析PCM，不伪装成第二个文件owner |
| CNN/指导 | 创建/取消任务、谱面队列、Push屏/灯光/跟奏 | CQT→真实CNN→Viterbi、模型和特征/推理缓存；允许使用一部分BSRAM加速，记录命中/DDR竞争和真实收益 |
| HDMI/分析 | HDMI物理扫描、最终交互/参数页面和已提交图像；W不可用时基础UI仍工作，分析标为不可用/陈旧 | 优先评估把真实FFT、XY/频谱分析及必要绘制迁W；共用最终PCM观测流，按预算返回分析快照或图块，不要求全部计算留M |
| 蓝牙/D | 接收经过验证的媒体PCM/控制；M保留最终输出选择和调度；25K按下启用对应效果、松开结束，组合/断连清理可验证 | **优先W直连蓝牙模块**并独占H5/HCI/GATT/A2DP/SBC，减少M接口/协议压力；若实物只能接M才评估UART桥。W-DEMO的临时独立DAC路径保留为回退，不冒充最终输出 |
| 录音/下载 | 真实最终串行完成帧tap及CPU命令代理；录音/通信不能反压采样 | 唯一真实DDR录音对象、STOP/封存/CRC/下载/ACK/恢复；CPU和BLE操作同一ID/格式/生命周期，清除与下载引用互锁 |

两板只有LCD口这一条已知有线连接；蓝牙仅作实测后的补充。不假设W访问M的USB、TF、DDR、HDMI或DAC。两板各自DDR按[唯一地址图](push2_workstation/usb_a/rtl/ddr_address_map.vh)核算字节/native word和owner，不以退出显示/TF为理由直接重分区。

## 5. LCD、电气与通信预算

[FPC4依据](../../example/LCD_RGB/docs/接线核对.md)及`example/LCD_RGB/constraints/lcd.cst`提供单板映射：1/2为+5V，颜色高位多处硬接地；可编程颜色16根、现有显示控制5根，约束为LVCMOS33。反序排线的接触面方向不能证明座间编号映射。**若实测为n→41−n，同型座的+5V会落到对端40/39，且部分信号落地；不能直接用现有LCD位流互连。** 当前禁用LCD配置仍把21根线驱动低，必须在新角色约束中明确输入/输出/高阻与供电隔离。

先断电核对两端pin1、地、电源隔离、线序、实际VCCIO、驱动方向和时钟；随后以保守源同步/异步实现逐级测速。逐方向测有效载荷、双向并发、RTT的min/p50/p95/p99/max、最大服务间隔、水位、CRC、拥塞/溢出、停钟、独立重启和重连。**5MB/s/方向只是待验证目标，不是已测吞吐。** 未完成此项前不冻结生产位宽/时钟/跨板PCM往返延迟。

| 流 | 48k预算 | 44.1k预算 | 说明 |
|---|---:|---:|---|
| W→M手机解码PCM16 stereo | 192,000 B/s | 176,400 B/s | 时钟频差/SRC与欠载策略独立验收 |
| M→W最终输出PCM16 stereo | 192,000 | 176,400 | 录音与FFT/分析共用，不重复发送 |
| M→W TF分析mono16 | 96,000 | 88,200 | stereo则翻倍；最终模型格式另锁定，可背压后台读取 |
| 重型效果全精度stereo32输入/返回 | 每方向384,000 | 每方向352,800 | 混响第一源码候选；另计每帧上下文、包头、CRC、信用，不截成PCM16冒充等价 |
| 显示完整快照示例 | 约11,264B/帧＋元数据 | 同左 | 512×32bit波形、65536bit XY、512×双8bit频谱；30Hz约337,920B/s，实际帧率/压缩/分片待选 |
| CNN结果/控制/对象状态 | 按最大包长/突发单列 | 同左 | 分片让路，不以平均带宽代替截止时间 |

W直连蓝牙时，M→W的最终观测＋mono分析＋效果输入净PCM为672,000B/s，W→M媒体＋效果返回为576,000B/s，另加结果/显示快照/协议开销。这是候选并发预算，不代表全部流必须同时开启。基础演奏不等待W。

第一混响源码接口还携带每帧身份/状态：请求163bit、响应164bit，各至少21B；48k下每方向1,008,000B/s，若按24B对齐为1,152,000B/s，尚未含外层包头/CRC。按21B预算，并发M→W为1,296,000B/s、W→M为1,200,000B/s（未含显示快照）。尤其是5MB/s下仅请求＋响应串行化已需8.4µs，大于试验512/76.8MHz=6.667µs期限；**不能凭5MB/s平均目标就启用此实时往返方案**。须测更高吞吐/最坏RTT，或明确压缩上下文、改变有界流水与效果拓扑后重验。

蓝牙UART现有921600、**8E1=11bit/字节**，名义每方向83,781.8B/s，50MHz DIV54线速约84,175.1B/s，均需扣H5帧头/转义/ACK/间隙；不能沿用baud/10。未经压缩的48k stereo16已超过该UART预算。SBC/A2DP与BLE同时运行的真实吞吐、抖动和延迟须测；蓝牙承载音频还是仅控制由实测决定，不能把BLE下载当实时音频。

## 6. 有界事务与失效语义

内部跨板信封另定义版本、长度、CRC、非零boot/session、generation、sequence、rate和用途；不改18-bit事件、USB PL或BLE wire契约。请求接受、参数实际应用、存储完成、串行输出完成和业务成功分别反馈。

- **基础采样**：永不等待通信ready。跨板效果候选在固定本地截止时间交付本帧；无有效结果即dry并计数/报告远端不可用，不把故障标成“效果已成功应用”。连续性和总延迟需要整机测量。
- **队列**：实时PCM、后台分析、控制、结果/显示、下载分别有界；明确深度、最大包长、服务期限和信用。高水位限制后台；不会用无界队列掩盖永久带宽不足。
- **断链/溢出**：媒体PCM欠载受控静音，禁止重复旧帧冒充连续；效果用本地dry；录音缺帧/CRC/写溢出使该对象ERROR、禁止伪READY；CNN输入不完整则终止/标注不完整，显示不得发布破碎快照。
- **重连/取消**：重新握手能力与boot，旧session/generation请求、PCM和结果全部作废。TF切曲/拔卡、识别取消、W重启不能复活迟到结果；有副作用请求不盲目重放。
- **PANIC**：M立即执行现有本地释放/静音语义，同时撤销远端音频历史及队列。PANIC不依赖普通满队列；新会话之前不接收旧尾音。远端清理确认不能阻塞本地采样。
- **切率**：M保留唯一实际切率权威；本地输出和待封存录音按已有屏障完成，W未确认则明确失败/保持原率。效果源码探针的本地配置ACK只表示本地上下文清空，不伪称W已同步。

## 7. TF、CNN、D和录音恢复条件

TF复用维护的[native直读](push2_workstation/usb_a/rtl/tf_audio/WORKSTATION_TF_DIRECT_NATIVE_V1_CONTRACT.md)、[ingress](push2_workstation/usb_a/rtl/tf_audio/WORKSTATION_TF_DIRECT_INGRESS_V1_CONTRACT.md)和[真实尾帧](push2_workstation/usb_a/rtl/tf_audio/WORKSTATION_TF_PHYSICAL_TAIL_V1_CONTRACT.md)。恢复Push真实文件名浏览/确认/播放/暂停/停止/重播，以及HDMI实际曲目/错误反馈；CNN缺席仍能选曲播放。只有一个SD/FAT owner，实际profile/网表/请求trace证明播放无DDR双bank中转；真实卡连续供给、碎片/FAT间隙、预填充、拔卡和物理EOS需独立验证。

当前M原生直读链为真实SD/FAT/WAV→v2帧桥→唯一router/DSP→PCM桥→I2S/观察/物理尾帧，owner4 TF DDR请求固定为零；arming、pause及post-LAST仍执行实际DSP采样。独立TF菜单不依赖本地CNN，保留真实曲名/选择/确认/播放控制。历史菜单DDR检查点、v11/v13直读和双率冷启动16场景分别保存在[菜单证据](push2_workstation/usb_a/reports/DUAL138K_TASK3_TF_MENU_20261101.json)、[运行证据](push2_workstation/usb_a/reports/DUAL138K_TASK3_TF_DIRECT_RUNTIME_20261101.json)和[旧候选证据](push2_workstation/usb_a/reports/DUAL138K_TASK3_TF_DIRECT_PREPARE_20261102.json)，不把旧divider2测试转授为FAST12或真实卡验收。

[新M CRC/cache整机候选](push2_workstation/usb_a/reports/DUAL138K_TASK3_TF_CRC_CACHE_PROFILE_20261102.json)为`custom138k-workstation-task3-m-direct-tf-v1-68efbb0415ea234e`：898项来源锁、269个编译输入，显式CRC1/cache1/r3，prepare、独立verify及真实Gowin综合通过。网表有唯一CRC checker和FAT cache，32声部envelope/state/expression、普通/矢量、实际效果、HDMI及I2S均保留。综合等效FF48,494、LUT56,082（含INV）、ALU13,857、BSRAM216、SSRAM218；比旧v13增加1个BSRAM、109FF、165LUT等效和67ALU。均不是布线物理占用；50MHz/76.8MHz的综合估算仅44.254/62.444MHz，不能宣称时序收敛。无P&R、位流、实体DAC或控制到声音延迟。

[FAST12诊断](push2_workstation/usb_a/reports/DUAL138K_TASK3_TF_SUPPLY_20261102.json)定位旧链每簇重读完整FAT扇区，稳态115,463B/s并复现7790帧欠载；[独立512B FAT缓存](push2_workstation/usb_a/reports/DUAL138K_TF_FAT_CACHE_20261102.md)现已修复该布局的重复读取。完整顺序512字节及真实CRC/CS释放成功后才发布，STOP/新任务/错误/复位撤销有效位与迟到填充资格。7个真实SPI模型场景及3负控通过，主线程复跑双率长片段、坏CRC和lookup取消4场景；48k/44.1k各完成11,000+97帧，实际87次数据读取、2次FAT读取、85次命中，有限片段供给225,671.9B/s。SPI divider12、3072帧预填及既有FIFO均不变。任意碎片可cache thrash，真实卡抖动、最大累计赤字和公共remount恢复未验；音频payload仍可能在最终CRC判定前被消费，validated-data-sector原子发布尚未实现。

[CRC组件](push2_workstation/usb_a/reports/DUAL138K_TF_SD_CRC16_LOCAL_20261102.md)与缓存默认参数保持关闭，只有新DIRECT显式启用，旧vendor/manifest及其他13个profile锁不改。历史[局部CDC证据](push2_workstation/usb_a/reports/DUAL138K_TASK3_TF_CDC_LOCAL_20261102.json)保留；新M实际网表10套局部检查有效合并为35项、2项skip、实际执行33项，387项不同负控全部拒绝，3项可选RAM边界缺口检出另计。首次FRAME/TAIL测试硬编码旧r2缺口而失败的证据保留；只修订测试按显式r3核对已安装边界后复跑这两套，未改生产审计器、SDC或候选输入。官方ROOT原语模型另有1项独立复跑，不抹去原skip。完整profile审计越过clock门禁后仍被完整TF CDC强拒绝。FIFO算术与所有权、RAM物理timing arc、串行context及compute回复业务语义、完整复位和STA继续是独立门禁，不能将局部检查或非空选择器当整机通过。

CNN首工作流为M选TF→明确分析PCM任务→W CQT/真实模型/CNN/Viterbi→完整谱面返回→M Push指导。先允许离线分析完再练习；不能称零延迟扒谱。模型权重/CRC、CQT、输入率/window/hop、量化、Viterbi和音符映射单独锁定；历史[full83验收](push2_workstation/usb_a/reports/CNN_83_ACCEPTANCE_20261006.json)不能转授新W。缺模型/loader/实现据实列缺口；允许W用部分BSRAM缓存加速，须测真实资源、推理最坏时间和录音/蓝牙共存。播放扇出不把两个ready相与：分析不足就降实际cadence或失败，不拖停播放。

本轮已核对维护的`rtl/music/weights/cnn_ddr_blob.mem`：52,239个16-bit word、104,478B，文本SHA256为`b5a98b6458e71cf150da37665305a6f895ba002e9e66b2a5bac9cbc12c6d96bf`，与accepted full83锁定模型逐字节相同；按little-endian word还原的CRC32为`AF01A61B`。真实模型存在；下述W候选已选择真实计算/存储接口并完成当前4Hz维度的2秒任务验证，整曲、其他维度、BSRAM加速配置和实板质量仍待验。原模型和Flash内容不修改。

W真实识别所需的任务取消边界已在维护`basic_pitch_workstation_link.sv`内显式可选实现（`DRAIN_RESTART_ENABLE=1`）；实际FIFO/DDR读返回与写接受排空后才重启推理，超时/内存复位/校准丢失隔离。真实模型、小窗口/2帧回归覆盖7种生命周期场景，取消后六层hash/写数/score与全新默认实例相同，跳过排空的负控失败，见[CNN任务证据](push2_workstation/usb_a/reports/DUAL138K_TASK3_CNN_RESTART_20261101.json)。默认保持旧行为；W21未因此接回CNN，完整W装配/loader/质量与实板仍待验。

[W真实CNN任务组件](push2_workstation/usb_a/reports/DUAL138K_TASK3_W_CNN_TASK_20261102.json)已贯通完整只读SPI模型加载、payload及DDR读回CRC、独立PCM对象写入/读回CRC、实际CQT/六层CNN/Viterbi及取消排空。PCM池为`0x31100000..0x311fffff`，首档只接受48k stereo16、最多96,000帧（2秒）；不借用唯一录音对象。owner5 broker仅以真实native接受回执确认写入，不能把本地入队当存储完成。57项实际任务检查使用受校验的2048/2测试维度、每任务4096输入帧；两次完整推理的六层hash、正写数及完整一音符谱面相同。生产43844/172维度保持，尚未用生产维度/2秒上限或整曲验收；owner6/8竞争来自native探针，不是同时运行真实Delay和60秒录音。新增有限EOF补零仅在该任务启用，旧默认与既有推理hash/7种生命周期结果相同；broker51项、3突变及地址图4突变通过，主线程复跑相同。**该组件验证当时未选入W整机；后续显式W候选见下。物理时序、LCD、Push完整指导及识别质量仍未验收。** 故障隔离需service/FIFO/client/controller共同复位，不能仅ACK终态后重新接单。

[统一录音审计](push2_workstation/usb_a/reports/DUAL138K_TASK3_RECORDING_AUDIT_20261101.json)已确认可复用现有`ble_business_owner`与真实CRC/rawDDR后端：CPU本地代理与BLE可操作同一对象。既有联调1765检查/136条历史报文及15负控、rawDDR188004检查/5负控通过；该审计时为16384帧（约0.341s），后续W角色已显式选择60秒容量。W21明确退出该后端；后续新增W媒体角色，不恢复R00独立对象。60秒需要同时扩大对象容量、物理engine/策略与DDR分配，不能只放宽一个常量；LCD突发PCM还须有界解包/节拍后喂给现有CRC录音端。

[60秒容量组件](push2_workstation/usb_a/reports/DUAL138K_TASK3_LONG_RECORDING_20261101.json)已完成：C的GET/外部START/CPU START共用显式容量，非默认配置须核对真实physical容量；engine/service/rawDDR同时支持2,880,000帧。独立W地址池为`0x30600000..0x310fffff`，真实对象只到`0x310fc7ff`，不把池尾14,336B填充区提供给下载。真实C/APB/解析器/CRC/nativeDDR联调采满2,880,000帧并逐字节下载11,520,000B，CRC `3ddb23ec`，1421块；主线程完整复跑相同。第二对象由BLE START、CPU STOP，在native写暂停时保持WAIT，排空后封存13帧并下载52B。默认136条wire golden与15负控保留，另验容量不匹配、地址/尾BL8和上限拒绝。**这是加速仿真的60秒容量证明；后续W候选已选择该容量，没有实测60秒录音或手机验收，44.1k和长对象重连仍待验。** 长对象重连试验的OPEN失败未隔离，未用保持会话的容量结果覆盖该缺口。

[W媒体内存组合](push2_workstation/usb_a/reports/DUAL138K_TASK3_W_MEDIA_MEMORY_20261101.json)已建立真实BIST及owner5 CNN、owner6 Delay、owner8唯一录音通路；其余owner关闭，旧audio-only组合和仲裁器未改。三种时钟相位共84,569检查、3项突变拒绝，主线程独立复跑相同；覆盖实际native提交、写掩码、返回归属、停顿、停钟校准丢失、共同复位和迟包同沿隔离。真实单槽组合在1024周期持续请求中Delay/录音各完成170次；绕过单槽的裸仲裁负控中持续Delay使录音256周期零服务，因此没有据此宣称录音期限或改公平性。**该内存层回归未选择W整机、未运行实际CNN/录音负载；安全恢复仍要求controller/client共同清除旧native事务，任意旧响应与新读重叠不能靠无epoch总线识别。**

[W媒体原生装配、固件与录音入口](push2_workstation/usb_a/reports/DUAL138K_TASK3_W_MEDIA_NATIVE_20261102.json)已把实际BIST、CNN任务和唯一raw store组合起来：完整52,239-word真实SPI模型启动/DDR CRC与24帧录取、排空、逐样本下载/清除通过；native owner5/6/8分别实际接受104,478/42,082/6条命令，owner6仍是竞争探针。新增headless-media固件保留真实Classic/HCI/SBC/GATT及唯一C/BLE owner，退出图形UI；每个TU按同一DDR图编译2,880,000帧容量。新ELF审计167处实际JALR、4张真实回调表、896B保守栈峰值，4负控拒绝。独立256帧有界录音入口按至少5个50MHz时钟送一帧，真实engine完成16帧/CRC；111项/15场景及3突变通过，涵盖溢出、断链、4ms lease、取消/PANIC与高generation重arm。主线程复跑原生组合和入口相同。**此原生装配阶段当时未选择W整机；没有连接HCI radio或LCD/M实际tap，也未并发运行整段CNN/真实Delay/60秒录音。** 不复用会退出业务录音的W21 audio-only选择，不以W本地最终PCM冒充M最终输出；真实手机解码出口、M最终tap录音入口和TF分析入口保持独立有界边界。

D保留真实手机A2DP/SBC连续流及按下启效、松开结束；BitCrush/Drive/Delay Send和Pitch/Delay/Chorus/Reverb逐项标实现/缺口。持续PCM Pitch不等于采样器变播放相位或近unity SRC。最终路径明确为手机→W蓝牙/解码→有界链路→经验证的M/W效果→M最终音量/调度→DAC；W演示DAC仅为回退，最终不能让手机音量标签冒充M实际输出。

长录音优先W本地DDR。首档至少60秒：48k stereo16需11,520,000B，44.1k需10,584,000B。显式W角色已选择一个CPU/BLE共同操作的权威对象，物理封存/下载仍须验收。先真实48k format1，再实现44.1k能力；ID/rate/epoch/帧数/CRC封存后不可变，STOP等待真实写入终态。CPU与BLE共同操作这一对象；Android保持app→data→ble→protocol，实手机录制/下载/CRC/WAV试听不可用fixture代替。

[显式W媒体整机候选](push2_workstation/usb_a/reports/DUAL138K_TASK3_W_MEDIA_PROFILE_20261102.json)现已通过prepare、独立来源验证和真实Gowin综合：`custom138k-workstation-task3-w-media-v1-01a09c94f065b7ba`，188个编译输入。真实CNN、owner5/6/8、唯一60秒raw对象和完整Classic/HCI/SBC/GATT已选入，退出W图形/TF/本地合成；旧W21不改。F807任务/PCM入口使CNN描述符实际可达，目前只有诊断调用，固件尚无自动TF/LCD任务生产器；软件M-final-tap录音入口默认关闭，LCD-ready固定0；不把软件开门当实际LCD/M tap。新APB→真实模型装载/native读回CRC 112项、APB→真实录音engine 161项均由主线程复跑通过，坏帧组合环和APB读strobe问题已修复；仍无实体手机/D/跨板链路验收。

该W候选实际选择既有资源配置`WIN_LEN=44100/FRAME_LIMIT=8/FEATURE_TILE_COLS=16/COARSE_GUIDANCE=1`（4Hz），不转授默认43844/172组件的维度证据。综合等效FF46,342、LUT65,490、ALU19,515、BSRAM228、SSRAM678；实际CNN子树22BSRAM，唯一raw store子树8BSRAM，证明计算/缓存及存储接口保留在W网表，不是M恢复同一后端。均不是物理占用、完整CDC/PLL/时序或位流验收；`bitstream=null`。官方干净重建23项通过，包含accepted/full83、timing85、resource-timing三条prepare和损坏输入拒绝；旧live profile锁因既有firmware/hash漂移仍拒绝，未为通过而刷新。M的CRC/cache候选见上；继续推进完整CDC/P&R、整曲识别与实际跨板链路。

[W选中配置的真实推理](push2_workstation/usb_a/reports/DUAL138K_TASK3_W_SELECTED_CNN_20261102.json)直接使用不可变W v13的全部相关源码与完整SPI模型，不缩小维度或覆盖RTL。96,000帧/2秒任务及取消后重跑完成74项检查，六层写数分别为16,896/2,112/22,528/704/22,528/704，六层hash及完整4音符结果一致。单次任务约368,947,028个50MHz时钟（仿真7.379秒）；4Hz是特征cadence，不能据此称实时推理吞吐。输入为确定性LFSR，只证明计算/存储/生命周期，不证明识别质量；owner6/8仍为竞争探针，尚未运行真实Delay和长录音并发。

[W实际网表CDC预审](push2_workstation/usb_a/reports/DUAL138K_TASK3_W_CDC_PREFLIGHT_20261102.json)发现CNN ready、APB reset合并后失效的选择器，以及两个暂存FIFO Gray最高位合并为binary后漏覆盖。已留精确修正建议与5项拒绝检查，尚未选择新W约束；完整共享reset、继承端点、PLL和布线时序未闭合。保留旧候选，不以平均吞吐或局部CDC替代LCD实测。

## 8. 阶段、提交与证据

每阶段完成针对性验证后commit、push并回写本节。输出固定目录、配置和来源；两板分别列源提交/输入hash、固件/模型、UserCode、位流SHA、物理资源、setup/hold/recovery/removal、PLL/CDC、LCD及控制到声音延迟、功能范围与回退。没有位流时明确`bitstream=null`，不复用已接受身份。

| 阶段 | 当前状态/退出条件 |
|---|---|
| T3-01 分支/原文/分工/预算 | 已完成，见[来源/硬件边界核对](push2_workstation/usb_a/reports/DUAL138K_TASK3_PLAN_20261101.json)；硬件吞吐均待测。原始规划备份在`~/.cache/gw138k-task3-20261101/task3-original-ignored.md` |
| T3-02a 第一计算迁移源码 | 已完成[源码/仿真证据](push2_workstation/usb_a/reports/DUAL138K_TASK3_REVERB_SOURCE_20261101.json)：M真实链退出本地混响的显式分支，W真实混响/历史RAM；端点15,076帧、18故障场景，整链37,312帧、全部效果顺序/mask/双率及3次有尾音普通屏障通过，整链最大538计算时钟。默认19项、来源17项、候选清单11项通过；生产DEMO宏关闭且原层次不变 |
| T3-02b 同条件资源差值 | 已完成[真实综合/清单/网表证据](push2_workstation/usb_a/reports/DUAL138K_TASK3_REVERB_SYNTHESIS_20261101.json)：M退出20SDPB/19MULT27X36，W实际承担；来源`06c55d8a`。候选工具12项来源/篡改测试通过，首轮不支持的工具宏选项失败保留，改为校验provider后新目录完整通过。仅子系统综合，整机profile传播、LCD/CDC和完整P&R另验，不把仿真538时钟当物理控制延迟 |
| T3-03 LCD可用线与实测 | 待目标板：反序线逐脚/电气/方向/时钟；双向有效吞吐/最坏RTT/拥塞/重连；先据此决定实时往返效果与其他PCM通路 |
| T3-04 M本地基础/TF前端 | 新DIRECT候选…68efbb0415ea234e，CRC1/cache1/r3、269输入prepare/独立verify/实际综合通过，32声部及普通矢量保留；综合BSRAM216。FAST12双率11,000+97帧无欠载，CRC/FAT来源和失效负控通过；完整TF CDC仍拒绝，综合时钟估算未达标。音频CRC原子发布、任意碎片/真实卡/remount、完整P&R及实体延迟待验 |
| T3-05 W CNN/分析/长录音 | 显式W媒体角色…01a09c94f065b7ba实际综合BSRAM228，CNN/raw/HCI保留；当前4Hz/96,000帧真实任务和取消后重跑74检查通过，仿真单次约7.379秒。CPU/BLE同一60秒对象及下载组件通过，APB112/161检查保留。整曲/质量、长对象重连、44.1k、真实并发和完整CDC/P&R未验；软件tap默认关、LCD固定down |
| T3-06 同对候选集成 | TF→W CNN→Push、真实手机D→M DAC、CPU/BLE同一长录音、下载/重连/取消/PANIC；分别测两板并发资源/时序/吞吐/延迟 |
| T3-07 硬件收敛 | 目标板到位并确认身份后必要SRAM验证；完整32声部/向量/效果/HDMI/TF/识别/录音证据和回退；Flash另授权 |

禁止用全量资源重写、放宽时钟/false path、删特性或报告字段代替门禁。子系统收益必须再经整机同条件P&R确认。新扩展配置进入现有`build.py`/显式profile；本轮子系统综合工具只用于分工验证，整机集成后收敛或退役，不成为新编号生产构建器。
