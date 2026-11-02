# Task3：最终双138K工作站

修订：2026-11-03，Asia/Shanghai。本文取代原未跟踪规划中“全部效果和可视化计算必须留在M”“先恢复完整M再加TF/CNN”的限制。目标是两板承担实际计算和存储，降低M资源、关键路径与布线压力。阶段状态只按本候选证据更新；源码、子系统综合、整机P&R和实板验收分开。

## 1. 独立工作与回退

- 本轮目录：`/Users/sphenicidition/.codex/worktrees/dual-138k-task3/Gowin_Synthesizer`；分支：`codex/dual-138k-task3`；起点：`cfad079f1640f44602f31d69b18084a3d429d226`。
- 参考目录：`dual-138k-workstation/Gowin_Synthesizer`。其task2、M24正在推进的候选和未提交的W流式Pitch工作继续由原分支维护；本轮不切分支、不搬走脏文件、不改其构建目录。原task3是被忽略的本地文件，已只读备份；本分支将修订稿纳入版本管理。
- 单板主目录仍为`/Users/sphenicidition/Documents/Gowin_Synthesizer`，起点`ba2ba027`；其未提交录音工作保持原地。最终CPU/BLE录音整合不能复制回已退出的第二套后端。
- task2当前M演示和W蓝牙流式D模式继续推进。task3不要求先完成task2全部功能，也不把task2的W临时USB/DAC输出当作最终接线。
- 用户确认：两块目标板默认尚未接电脑；当前连接的138K供另一个分支使用，本轮不操作。LCD排线外观为反序线；用户于2026-11-02进一步确认两板同号网络一一对应（M_n→W_n，例如40→40），不按n→41−n推导。TF在M，蓝牙模块可以接任一板。必要SRAM验证已授权，但仅在目标板到位且身份、电气、候选门禁确认后执行；Flash须另行授权。

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

[FPC4依据](../../example/LCD_RGB/docs/接线核对.md)及`example/LCD_RGB/constraints/lcd.cst`提供单板映射：1/2为+5V，颜色高位多处硬接地；可编程颜色16根、现有显示控制5根，约束为LVCMOS33。用户现已明确确认板间为**同号网络n→n**，例如M40→W40；反序排线外观不再作为倒序映射依据。按此编制互补收发方向，不把两端原LCD输出同时驱动同一线。此确认没有自动验证VCCIO、两板+5V供电关系、空闲电平/上下拉、时钟或链路性能。 旧禁用LCD配置仍把21根线驱动低；新paired角色已改成25个inout和互补所有权，复位默认高阻，供电隔离仍需实物核对。

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

完整框架初版实际CNN输入为48k **stereo16**，净PCM为192,000B/s，上表mono16仍只是后续预算选项。框架内部每PCM事务携带完整身份和index，打包lane为202bit；若逐帧原样发送为1,212,000B/s，按26B对齐为1,248,000B/s，尚未含物理CRC/信用。最终录音tap也携带epoch/sequence。上述是框架初版，后续paired已选择block6/credit8的独立分析/录音流；本轮新的phone-blocks配置将完整PCM1窗口写改为最多5字分块，其他PCM1/clock操作仍为真实远端RPC及应用水位屏障，见[手机分块契约](push2_workstation/usb_a/rtl/workstation/TASK3_PHONE_WINDOW_CONTRACT.md)和8.5。内部宽事务和净PCM不能冒充实际线速。

| 当前显式phone-blocks配置的固定52B外帧预算 | M→W | W→M |
|---|---:|---:|
| 两条48k stereo16分析＋录音，满6帧块 | 832,000B/s | 信用另计 |
| 手机48k、128帧原PCM1槽、每槽26个数据块和完成ACK | 507,000B/s ACK | 507,000B/s数据 |
| 上述合计 | **1,339,000B/s；25,750包/秒** | **507,000B/s；9,750包/秒** |
| 其他 | 原PCM1/clock RPC响应、能力/结果/状态/维护 | 原PCM1/clock RPC请求、信用/维护 |

这不是三流模型或实测预算通过：块间等ACK、实际CPU轮询、信用和仲裁必须另外验证，不能只与理想线峰值相减。离线TF分析可以背压，基础演奏和最终采样不能等待它。

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

本轮已核对维护的`rtl/music/weights/cnn_ddr_blob.mem`：52,239个16-bit word、104,478B，文本SHA256为`b5a98b6458e71cf150da37665305a6f895ba002e9e66b2a5bac9cbc12c6d96bf`，与accepted full83锁定模型逐字节相同；按little-endian word还原的CRC32为`AF01A61B`。真实模型存在；下述W候选已选择真实计算/存储接口并完成当前4Hz维度的2秒任务验证；BSRAM加速另以显式候选验证，整曲、其他维度和实板质量仍待验。原模型和Flash内容不修改。

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

[W CNN BSRAM分担实验](push2_workstation/usb_a/reports/DUAL138K_TASK3_W_CNN_BSRAM_20261102.json)新增两份独立配置，均保持WIN44100/FRAMES8、9 octave、hop22050/4、tile16、真实模型及原算术/时钟。默认仍走DDR；仅显式新W配置把signal或signal＋CQT系数放入W本地BSRAM，front系数和state/plane/weights/features仍在DDR。两候选各991项来源锁、649项暂存、188项编译输入，独立prepare/verify、实际预处理参数链和整机综合已通过；旧14份配置锁保持原字节，回退按原提交及不可变候选，不在当前共享源码上刷新旧锁。

实际综合为：signal-only `…8eead7dd2f05abcb` 使用276/340 BSRAM，signal＋coeff `…5ca0cbd4d7fcfae1` 使用308/340；旧W为228。新增信号RAM实占48 SDPB、两CQT ROM再占32 pROM，不能沿用44/18块的几何估算。两新配置50MHz综合估算均52.907MHz，音频仍63.698MHz/目标76.8MHz；无布线或物理时序通过。小型CQT三模式4完整窗口的全部幅值/抽取/写入序列一致，2项数据破坏负控被拒绝；signal＋coeff已完成两次96,000帧跨配置任务和取消后重跑，75项检查通过；六层hash/写数、完整音符序列与DDR基线一致。单次仿真任务从7.379秒降至3.225秒，accepted DDR16读取减少74.86%、写入减少56.08%，代价为BSRAM228→308。选择该不可变候选继续离线完整框架搭建，保留DDR回退；3.225秒处理2秒内容仍不属于实时推理，且输入未按真实48k节拍送入。signal-only首任务完整且结果一致，第二任务日志在330M时钟截断、进程丢失原因未知，无最终回执，不记为完整通过。官方整机审计入口对这两W身份拒绝`native board preparation policy changed`，完整W门禁接入及CDC/PLL/STA仍待完成。

[W实际网表CDC预审](push2_workstation/usb_a/reports/DUAL138K_TASK3_W_CDC_PREFLIGHT_20261102.json)发现CNN ready、APB reset合并后失效的选择器，以及两个暂存FIFO Gray最高位合并为binary后漏覆盖。已留精确修正建议与5项拒绝检查，尚未选择新W约束；完整共享reset、继承端点、PLL和布线时序未闭合。保留旧候选，不以平均吞吐或局部CDC替代LCD实测。

## 8. 完整框架优先（2026-11-02）

按本轮补充要求，先搭建可执行的完整业务框架，再集中检验与迭代；不继续把局部资源实验作为接通整机的前置条件。框架入口、实际边界和剩余装配见[逻辑框架](push2_workstation/usb_a/rtl/workstation/TASK3_FRAMEWORK.md)，版本证据见[框架报告](push2_workstation/usb_a/reports/DUAL138K_TASK3_FRAMEWORK_20261102.json)。

- **TF→W CNN→M Push**：新增唯一M SD/FAT/WAV播放/分析路由，分析保留文件游标并自动分成最多96,000帧的片段；有序lane传描述、PCM、末尾CRC。W实际DDR提交及读回CRC后才运行真实模型/CQT/CNN/Viterbi，M收齐全曲后才发布完整谱面，最多2,048音符。明确48k分析和无跨片上下文融合限制，不以短片完成冒充整曲。
- **手机→M最终音频**：完整逻辑audio exchange把W原PCM1/clock两个调用者送至M原PCM owner及统一时钟权威；不再把W演示DAC或已施加最终gain的PCM当最终路径。保留原SRC、D效果、增益及调度边界；真实BLE/H5/SBC及44.1k切率仍需并发检验。
- **M最终tap→W唯一录音对象**：非阻塞256帧采集、远端arm ACK、epoch/sequence核对、失败撤权后接原record_ingress；CPU/BLE继续共用原HCI对象及owner8 DDR存储。没有恢复退出的第二后端。
- **有界通信与失败**：独立FIFO、公平仲裁、背压保持、分析及结果各自严格有序，cancel/PANIC不等待PCM信用。源失败、断链、旧身份、超时、CRC/长度/序号错误和录音溢出均有明确终态，不拖停M基础采样。

现有build.py新增显式框架prepare入口；快照`task3-framework-logical-v1-841ec6407a831645`锁定78文件/54编译输入。独立prepare/verify、22项拒绝负控及暂存后三入口全依赖lint通过；实际展开确认唯一TF/CQT/六层CNN/Viterbi和明确4Hz/BSRAM参数。相关有界/生命周期小验证通过，范围见报告，不代表完整实卡到Push或真实并发验收。

上述初版仅为可展开的双板逻辑组合，不继承物理资源/STA或实板延迟。其后同对板级接入见8.1；原逻辑快照保留。目标板默认未连接，另一分支使用的板卡不操作；原候选和task2继续原分支回退，旧锁不刷新。

### 8.1 同对板级组合已接入，物理验收仍待完成

新增独立 `custom138k-workstation-task3-{m,w}-paired-v1`，复用现有custom-board入口；分工、引脚、冷启动及失败契约见[配对组合说明](push2_workstation/usb_a/rtl/workstation/WORKSTATION_TASK3_PAIRED.md)，两板身份、资源、审计失败和原始回执哈希见[阶段总报告](push2_workstation/usb_a/reports/DUAL138K_TASK3_PAIRED_FRAMEWORK_20261102.json)。维护顶层字节保持，严格可逆stage适配选择实际M/W组件；旧16份配置锁不刷新。

M保留真实32声部普通/矢量、最终PCM1/统一时钟、HDMI与DAC调度。TF卡在M，唯一真实SD/FAT/WAV游标在直读播放与有界分析间互斥；CNN、模型、CQT、Viterbi与长录音存储实际位于W。W的HCI/Classic/SBC/GATT通过有界PCM1/clock代理请求M；M最终完成帧返回W唯一CPU/BLE录音对象。真实REC_START已补自动供流请求、M授权/ACK、终态cancel；四层HCI编译作用域已经实际预处理核对，不以端点单测代替板级选入。

同号LCD采用双向4bit req/ack，本地时钟运行，不把LCD线当FPGA时钟。新增F808页要求CPU写实际非零boot/peer/session与递增generation；probe、预算、business分别启用，默认全关。M演奏PANIC与F808 PANIC在已授权LCD上提供至少50,000个50MHz周期紧急电平，撤销probe后仍保持；未启用probe时演奏PANIC不驱动LCD。保持电平不是已测对端接收。独立CPU复位、断链、预算撤销和重连禁止旧任务复活；自动冷启动nonce分发仍未完成。

离线证据：LCD transport两配置34/42项、四态引脚1,667项；F808配置151/170项；真实APB CDC+公共板级LCD链590/819项；真实M/W业务端点89项（真实单录音引擎捕获/封存4帧）；TF默认真实播放/取消、分析9项/5场景和录音请求17项通过。W新paired固件构建及167个JALR审计通过；原media ELF/BIN/boot与同工具旧版本逐字节一致。范围及失败尝试保留在阶段报告，不当作实卡、无线或实板验收。

v4同对候选已clean prepare并完成实际Gowin整板综合：M `...471dc1f03e7f86d7`、W `...dbd0aa27d30ff935`；M综合BSRAM等效220，W308，均非物理布线计数。真实W CNN、唯一录音引擎/raw存储、两侧端点和32声部M保留；严格审计已实际运行并返回失败：M/W的新LCD/headless组合尚未被旧clock checker完整识别，另有空SDC选择器、M root连接断言及W held/boundary缺口；不代表CDC/PLL/STA通过。远程混响尚未选入这对整板，M仍保留本地效果；先前20SDPB/19MULT子系统减量不能转记成本对整板收益。

最终来源补齐默认资源入口对维护版原生CNN参数的严格选择；三条不依赖私有历史目录的重建路径共23项全部通过。随后v5重新clean prepare并独立verify：M `...6a9647ac5ddae37c`（927锁文件/283编译输入），W `...4d1d6ac48886aaee`（1,023/196）。与实际综合的v4比较，M全部689个stage文件相同；W680个stage文件中仅未被综合调用的Python构建依赖改变，全部硬件输入与综合Tcl相同。v5没有重新运行综合，不转移v4未通过的验收结论。

当前固定52B帧逐样本传输，每条48k分析或录音流要2,496,000B/s；两者同向合计4,992,000B/s，另加维护/结果/控制。手机仍按PCM1 APB请求/响应往返，不能按192,000B/s净PCM冒充线速需求。本版用于接通框架，未经实测不得启用实时PCM生产配置；下一轮按实测预算实现块传输/上下文压缩和有界专用媒体流。离线分析可背压，基础采样不得等待。目标板尚未连接，无新位流/实测LCD吞吐/控制到声音延迟，也未操作另一分支板卡。

### 8.2 同对综合审计对齐与通信瓶颈（2026-11-02）

新的v6配对候选已分别clean prepare、独立verify并实际重新综合，详见[审计对齐报告](push2_workstation/usb_a/reports/DUAL138K_TASK3_PAIRED_AUDIT_ALIGNMENT_20261102.json)。M为`custom138k-workstation-task3-m-paired-v1-140c00fb4a8b5a6c`，942个配置锁输入/1,005个准备快照文件/283个启用输入；W为`custom138k-workstation-task3-w-paired-v1-3d33fb0c0c41caec`，1,037/1,075/196。两板全部非约束编译输入与冻结v4逐字节一致，唯一启用输入差异为各自SDC；维护顶层、原16份锁及task2候选保留。

| v6实际综合与审计 | M | W |
|---|---:|---:|
| Register / LUT | 55,427 / 65,183 | 46,554 / 59,478 |
| 综合BSRAM等效量；物理计数待布线 | 220 | 308 |
| 综合结构门禁 | 18/19通过，完整TF CDC仍拒绝 | 17/17通过 |
| 50MHz域综合估算 | 39.084MHz，未达标 | 48.889MHz，未达标 |
| 76.8MHz域综合估算 | 58.651MHz，未达标 | 72.616MHz，未达标 |
| 位流 / 布线STA / 实板延迟 | null / 未验 / 未测 | null / 未验 / 未测 |

此次按真实M/W来源补齐PLL/DCS/时钟结构检查、35状态位启动根证明、M四组release合并后的12个CLEAR端点，以及W实际PC8/health32/APB边界和已退出状态的SDC退休证明。LCD每板7个输入pad、20个同步状态位的直接连线/复位/早级唯一扇出已在真实网表及破坏负控中核验。最终PANIC业务扇出、F808 APB、束数据稳定时间、整板CDC和布线检查仍独立待验。M的完整DIRECT TF CDC门禁保持失败，不能由局部receipt/启动/尾部检查通过替代。

三条clean baseline prepare共23项、维护来源17项、约束精确逆向5项通过；报告附各局部检查、破坏负控及实际审计回执哈希。以上是综合结构范围，W通过不表示时序或整机离线验收。两板全源CDC、物理资源、PLL/STA及部署资格均未通过；未生成位流、未接触另一分支板卡。

理想连线双向RTL模型保留默认心跳/探测，在M50MHz、W50MHz或约45.45MHz、独立相位及两种ready占空下，各方向1,024个32B载荷通过。业务速率仅约32,250～34,921包/秒，净载荷1.032～1.118MB/s，不能承载单条48k逐样本流。该数值不是LCD实测或最坏RTT。下一阶段优先保持现有外层帧/PHY，将PCM改为有界分块与共享上下文，并拆分分析/录音接收队列和信用，解决慢CNN占住公共接收槽的问题；基础采样仍不等待远端。

### 8.3 有界PCM分块已接入并重新综合（2026-11-02）

同号LCD接线、PHY、52B外层帧及F808默认关闭策略保持；新的paired板级组合显式选择`BLOCK_PCM=1`，旧端点默认仍为0。实现及来源见[PCM分块阶段报告](push2_workstation/usb_a/reports/DUAL138K_TASK3_PCM_BLOCKS_20261102.json)和[分块契约](push2_workstation/usb_a/rtl/workstation/TASK3_PCM_BLOCK_CONTRACT.md)。完整descriptor/ARM绑定上下文，每包最多6帧PCM；分析/录音各有独立8块接收队列、绝对信用和4槽合并返还。M公平调度两流，W公平调度手机命令、信用和结果；慢CNN不再占住公共接收槽。

双方先核对完整配对身份和媒体能力，旧版DATA及混接不能被当成新媒体能力。匹配故障回报、取消、PANIC和身份变化撤销partial/旧信用；SEAL等待实际PCM展开排空，SEAL后的迟到DATA/重复SEAL失败。录音仍由原最终tap、原W ingress和唯一CPU/BLE对象承担，基础采样没有远端ready。手机PCM1仍逐APB往返，此阶段**没有解决持续手机D传输**。

满6帧时两条48k流的数据预算由96,000降为16,000包/秒，固定外帧由4.992降为0.832MB/s，另计信用、控制和维护。104.2µs只是连续6帧的聚合开销，信用/仲裁/排队另加，不能当作总延迟上界。真实transport/PHY加两对codec的理想连线模型，在M50MHz、W50MHz或约45.45MHz及独立相位下，每流4,099帧/684块、427组控制请求/echo通过。分析停顿3.6/3.96ms并耗尽信用时，录音仍交付174/192帧，控制仍完成18/20次；固定48k源不丢tick，256帧源队列中录音最高2帧，分析最高133/151帧。该模型没有实例化真实CNN/DDR录音对象，不是实测LCD吞吐或RTT。

codec边界/同拍故障110检查，新M/W端点371检查、新旧混接拒绝8检查、原端点/HCI opt-out 89检查通过；来源17项、约束逆向5项和三条clean baseline prepare 23项通过。报告绑定最终源码/日志哈希，早期失败与过期回执保留。

v8已分别重新clean prepare、独立verify并完成实际Gowin整板综合：M `...7458968b00d8a89d`（953锁输入/1,008快照/285启用输入），W `...4412228db9c7893d`（1,048/1,078/198）。两板新codec均实际保留于网表；CST/SDC与v6逐字节一致，没有放宽时钟或例外。维护顶层、旧16锁、v6和task2候选保留。

| v8实际证据 | M | W |
|---|---:|---:|
| Register / LUT | 56,252 / 67,035 | 47,713 / 60,491 |
| 综合BSRAM等效量；物理计数待布线 | 217 | 308 |
| 综合结构门禁 | 17/19；两项release/held清单证明拒绝 | 16/17；shared PLL/control release清单证明拒绝 |
| 50MHz / 76.8MHz域综合估算 | 41.537 / 60.809MHz，未达标 | 45.854 / 65.028MHz，未达标 |
| 位流 / 完整源CDC / 布线STA / 实板延迟 | null / 未通过 / 未验 / 未测 | null / 未通过 / 未验 / 未测 |

新增媒体逻辑改变了真实复位释放端点集合，因此v6封存的完整consumer清单不能直接用于v8；严格审计按预期拒绝继承证明，未简单刷新hash使其通过。M的held检查在此更早的清单门禁处停止，完整DIRECT TF CDC仍待完成。分块增加部分Register/LUT，也不代表整板时序改善。下一步逐项补齐新端点的源/CDC证明，再推进有界手机PCM专用流及真实TF/CNN/Push、长录音/下载并发；电气、实际吞吐、抖动和控制到声音延迟仍须目标板到位后验收。本阶段未操作任何板卡，SRAM/Flash均未写入。


### 8.4 队友 PR 审查、选择性合入与 M CPU48（2026-11-03）

已审查 [PR #2](https://github.com/Sphenomenon/Gowin_Synthesizer/pull/2)（`07e91936`）和 [PR #3](https://github.com/Sphenomenon/Gowin_Synthesizer/pull/3)（`e417b604`），适用改动经冲突处理后进入本 task3 分支；未把包含无关 Android/25K 历史的整个分支合入，也未操作远端主分支的合并按钮。原 PR 保持打开，本地修正不表示其原提交已无缺陷。来源、选入/未选入、失败和回退详见[整合证据](push2_workstation/usb_a/reports/DUAL138K_TASK3_PR_INTEGRATION_20261103.json)。

| 分工/优化 | 本轮实际选择 |
|---|---|
| M USB CPU | 新显式 `custom138k-workstation-task3-m-paired-cpu48-v1`：3×16KiB RAM，配套 linker、栈顶和三组 ROM；保留原 32 普通/矢量声部、TF、DSP、HDMI 和最终输出权威 |
| W CNN/长录音 | 保留冻结 v8（`...4412228db9c7893d`）与唯一 CPU/BLE 录音对象；没有恢复第二套短录音后端，未重综合 W |
| BLE DDR/重放/GATT | PR2 旧后端改写与当前独立 owner 不同，未选入；其 `0x30100000` 与 Basic Pitch 历史区冲突，备选短存储改别名到既有 `0x30510000` / native `0x0c144000` 并通过正反例。完整资源开关明确拒绝 |
| TF ring/ADSR 算术 | 数值回归保留；原 PR 的实际布线未证明时序改善，本轮不选入双板配置 |
| HDMI USB/声部状态 | 仅显式组合诊断；修复显示域复位释放、上游 ULPI 停钟后的过期状态及独立顶层多出 10 个无约束引脚。声部条仍为 D5 演示快照，尚未接真实 DSP |

M v3 已实际 Gowin 整板综合，最终 v4 为审计来源收敛后的 `...4fbaadf81abc4c5f`，配置 SHA `85b232bd83fe9af7ab0cd7aee2a342118e66d032cf1d729427855f5446cd490a`。v3/v4 的全部 702 个 staged 文件、285 个启用输入、工程/Tcl/ROM 逐字节一致；仅来源清单和两个未编译审计器改变，故显式绑定复用刚生成的 v3 网表，**不称为 v4 第二次独立综合**。955 个锁源输入与完整来源验证通过。CPU 固件 21,380B，静态末端 27,228，48KiB 静态栈余量 21,924B；未测实际栈峰值。

| 实际证据 | 原 M v8 | 新 M CPU48 | W 冻结 v8 |
|---|---:|---:|---:|
| Register / LUT | 56,252 / 67,035 | 56,255 / 67,052 | 47,713 / 60,491 |
| 综合 BSRAM 等效量 | 217 | **209** | 308 |
| USB CPU RAM SDPB | 32 | **24；12,288 初始化字逐字核验** | 32 |
| 综合结构门禁 | 17/19 | 17/19 | 16/17；本轮未重审 |
| 50MHz / 音频域估算 | 41.537 / 60.809MHz | 40.334 / 60.809MHz；仍未达标 | 45.854 / 65.028MHz；仍未达标 |
| 位流/物理 BSRAM/布线 STA/实体延迟 | 未验 | null / 未验 / 未验 / 未测 | 未验 |

这是综合存储减量，未证明物理时序改善。M 的 CST、SDC 和实际双板顶层与 v8 逐字节相同，没有调整时钟或例外。容量配置与 24 个真实 RAM 原语/全 ROM 共同证明功能存储保留；原来固定 64KiB 下限的检查仅对显式 CPU48 配置分支，旧配置原下限不变。两项 release/held 完整消费者清单仍拒绝继承，完整 DIRECT TF CDC 仍待完成，部署门禁保持关闭。

针对性验证：CPU48 边界与破坏负控 7 项，实际 RV32I FS64B/HS512B 探针回环/枚举/复位恢复通过；显示 3 项、组合诊断 15 项（Tk 1 项跳过）、资源组件 10 项（退出的旧后端 2 项明确跳过）、BLE 8 项通过。真实 C/APB/CRC/raw DDR 的 60 秒容量录音与全量下载再次通过 2,880,000 帧/11,520,000B/1,421 块/38,475 检查，输入未漂移；不是无线或实时时长验收。来源 17 项、三条 clean baseline prepare 23 项、原/配对审计回归及精确逆向通过。SoC 原有 lint 仍失败：HEAD 与当前完全相同的 35 条警告，原测试要求 1 条，未放宽门禁。旧 18 份配置锁、common FIFO、五份 generic BLE 源码及原 task2/双板候选保留。

LCD 的同号映射、PCM block6/credit8、0.832MB/s 加控制/信用的格式预算保持；没有新的物理吞吐、RTT、抖动或控制到声音延迟证据。手机 PCM1 逐命令瓶颈仍在。目标板未接入，本轮未发现/操作设备，SRAM/Flash 均未写入；Flash 仍须另行授权。

### 8.5 手机 PCM 窗口分块与真实 owner 屏障（2026-11-03）

新增显式 `custom138k-workstation-task3-{m,w}-paired-phone-blocks-v1`，见[阶段证据](push2_workstation/usb_a/reports/DUAL138K_TASK3_PHONE_WINDOW_20261103.json)。M 继承 CPU48，保留 32 普通/矢量声部、TF、原 DSP、参数/采样权威及 HDMI/DAC；W 承担真实 CNN/CQT/Viterbi、HCI/SBC 与唯一 CPU/BLE DDR 录音对象。新 W 同时纳入此前审查的 CPU 默认 RAM generate、DDR BIST/装载器及 USB 状态来源，不能把它相对冻结 v8 的全部差异称为“只加手机分块”。旧 19 份配置锁、task2、M CPU48 与 W v8 候选均保留。

W 将原 PCM1 窗口完整字写合并为最多 5 字，最多一个 building 块加一个在途块；M 逐字经原 held APB CDC 写入原 PCM1 owner。W 本地写 ACK 仅表示有界接纳，M 完成 ACK 才是实际 RAM 写水位；其余 PCM1/clock 操作须等该水位后走原 RPC，COMMIT/SELECT、槽与 bitmap 检查仍属原 owner。新配置需 version2/features `0x80080601` 的完整身份协商；新旧混接拒绝 ARM。重叠命令、超时、断链、取消/PANIC 与身份变化撤销手机分支及旧历史，基础采样不等待它。默认旧端点仍不启用此策略，详见[分块契约](push2_workstation/usb_a/rtl/workstation/TASK3_PHONE_WINDOW_CONTRACT.md)。

针对性验证通过：分块/屏障 363 检查和 4 个破坏负控，重叠仲裁 75 检查/6 场景和 2 个负控；真实 M/W 端点＋锁定实际 APB CDC＋原 PCM1 owner 为 603 检查、512 字/104 块、160 个精确非零立体声输出，另通过新旧能力拒绝、STOP/PANIC 和 generation/重连清理。该验证未包含 LCD PHY、实际固件轮询、RF/SBC、D 效果、I2S/DAC；不能据此宣称持续手机流或实体声音已验收。早期失败、最终 v7 回执和原端点回归均保留。

| 本轮实际整板综合 | M | W |
|---|---:|---:|
| Register / LUT / ALU | 56,599 / 68,233 / 27,700 | 48,475 / 61,605 / 16,077 |
| 综合 BSRAM 等效量 / SSRAM | 209 / 766 | 308 / 779 |
| 新手机缓冲 Register / LUT / BSRAM | 344 / 489 / 0 | 696 / 736 / 0 |
| 50MHz / 76.8MHz 综合估算 | 42.644 / 59.634MHz，未达标 | 43.888 / 65.193MHz，未达标 |
| 位流 / 物理资源 / 布线 STA / 实体延迟 | null / 未验 / 未验 / 未测 | null / 未验 / 未验 / 未测 |

两板 v2 已实际 Gowin 综合，最终 v5 为 M `...a8c56437ef9af94e`、W `...86b7bda71d161a30`，分别锁定 967/1,061 项来源并另行 clean prepare/独立 verify；仅未编译审计器改变，全部硬件输入、GPRJ、Tcl、ROM 和约束逐字节一致后，显式绑定复用 v2 网表，不称为第二次独立综合。新 provider 的精确来源、共同/角色逆向及实际 35 位 root 状态证明补齐，5 项回归/85 个破坏负控通过；W 默认 64KiB 的 32 个 SDPB、16,384 个 ROM 字逐字核验，修复 `g_ram64` 名称引发的误拒绝。端口审计改从实际 GPRJ 唯一选 provider，覆盖全部旧/新配对配置。完整输出清单保留各 LCD 位及别名，旧 M 的两个总线标签恢复为 7 个真实输出位；**历史完整消费者闭包仍拒绝，未刷新旧 hash**，完整 DIRECT TF CDC/物理门禁继续关闭。最终 M 为 17/19：`cpu-source` 完整消费者清单及 held payload 的 CE/提交条件证明拒绝；W 为 16/17：共享 PLL/control 释放清单拒绝。held 拒绝已定位为 request 的 CE 被综合为常高、提交条件并入 D；performance/CPU 两处的独立 reset-inclusive BDD 各覆盖 19 输入，局部转移与 `request XOR payload_CE` 吻合，尚未并入整项握手证明。不得将这些失败统称为已补齐的 root/ROM 登记问题。最终候选身份、逐门结果和工具哈希见阶段报告。

按原 128 帧 PCM1 槽计算，手机数据及反向实际完成 ACK 各 507,000B/s；加双 block6 分析/录音，M→W 为 1,339,000B/s、25,750 包/秒，信用/控制/维护另计。真实三流 LCD 模型、实际固件轮询和最坏等待尚未通过，持续能力及总延迟有效位保持关闭。目标板继续按未接入处理，本阶段未发现或操作设备，SRAM/Flash 均未写入。下一步补齐完整消费者/TF CDC，再验证三流、真实手机 D→M 最终输出与长录音/下载并发，按实板资源和关键路径决定进一步效果/FFT 分担。

### 8.6 held 局部提交证明与真实固件 LCD 负载（2026-11-03）

本阶段补验证框架和局部审计，见[held／LCD 固件负载证据](push2_workstation/usb_a/reports/DUAL138K_TASK3_HELD_LCD_WORKLOAD_20261103.json)。没有修改生产 RTL、固件、配置、约束或既有候选，没有重新综合或生成位流。M／W 仍分别引用 8.5 的 `...a8c56437ef9af94e`／`...86b7bda71d161a30`；综合等效 BSRAM209／308 为原证据，物理资源、布线 STA、实体延迟仍未验。原19份配置锁及新增两份 phone 配置保持，task2 和其他分支不受影响。

M 的 performance380／CPU224 位 held 数据具有相同的本地提交使能，但其 request FF 的 CE 被综合为常高、条件移入 D。审计新增精确、复位优先的 `next-Q = CLEAR ? 0 : request_Q XOR payload_CE` 证明，并核对 held 仅驱动对应 destination D 的完整消费者集合。两组各覆盖19个真实Q输入的524,288种赋值；旧 CE 映射兼容、7项回归及66个破坏检查通过。这只证明本地提交耦合，未证明入口业务、完整握手或物理 CDC。完整 peripheral 审计现到达并拒绝 `config_cdc/p_release_2_s0` 的历史 CPU source 消费者封印，未更新旧 hash 放行；v5 整体严格失败状态继续保留。

另对旧／新真实网表完成只读差异诊断。M 的403个 CLEAR 消费 pin 和2个 AE350端口保持，只有两个 request 实例映射变化，独立旧／新 next-Q 等价证明通过。W 的真正旧封印来自 v6：14,361个FF消费 pin，v8为14,419，phone v5为14,481；245个 primitive pin及3个蓝牙输出逐项一致。新增手机包 owner 和 HCI／录音映射变化须逐项证明；完整 CE 锥在真实 `controller_rvalid` 黑盒边界及既有120输入限制处未能完成证明，不能归为单纯重命名。以上消费 pin 数不是物理寄存器或 BSRAM 计数。

新增[真实固件工作量适配器](push2_workstation/usb_a/sim/audio/run_task3_phone_firmware_workload.py)直接调用未修改的 `runtime_pass` 四次／pump及 `pcm_media`。每128帧包含8次 poll／submit、100次读取和137次写入，其中128次是窗口字；SELECT另加3读6写。Native和ASan／UBSan各4,364检查通过，覆盖100ms pending超时、不确定COMMIT不重放及默认能力关闭时零写入。构建前后绑定第一方、vendor及adapted decoder，真实篡改外部缓存的负控拒绝。预建立的Classic／security、已解码PCM和idle HCI均是显式测试输入，未替代真实RF／SBC验收。

[LCD 联合模型](push2_workstation/usb_a/sim/workstation/run_task3_phone_lcd_cosim.py)实例化两端真实endpoint、默认维护流的LCD transport／PHY、锁定APB CDC和原PCM1 owner；M50MHz、W50MHz或约45.45MHz／3ns独立相位、音频平均76.8MHz，使用理想零延迟连线。原生产CAPS仍为 `0x67`、持续能力位关闭，两组正常用例均零手机写入。另有四组**仅测试读包装**把C观察值改为`0x6f`，用于暴露尚未放行路径的负载，生产字节不变。

| 仅测试注入的观察结果 | W50MHz | W约45.45MHz |
|---|---:|---:|
| 只有手机：相邻128帧COMMIT的pump后观察间隔 | 8.303ms | 8.724ms |
| 手机＋双48k分析／录音：同一观察间隔 | 9.500ms | 11.847ms |
| 四组实际PCM1结果 | 两块提交后欠载，`F_UNDERRUN=4` | 两块提交后欠载，`F_UNDERRUN=4` |

128帧在48k下仅覆盖2.667ms。四组各取得255个精确非零立体声owner输出后进入欠载／固件fence；其中三组有一个在途窗口被已失败owner拒绝，该错误真实回传，未改成成功。上述时间是在四次pump返回后的观察值，最多包含一个pump的观测滞后，不是物理延迟或最坏界限。即使本地C计算除MMIO外按零耗时处理，现策略仍不能持续补充音频；仅按PCM字节计算的8.5预算漏掉了大量状态查询往返。

三流两组的分析和录音各交付1,962帧；分析暂停3.96ms期间录音各推进192帧，实际TF source队列最高161／256，最终tap导出队列最高4／256。手机失败后两路继续推进；CRC／序列／传输溢出保持零，手机错误局限于手机分支。测试台外生`sample_take`节拍及取消后的节拍继续，不能据此宣称真实DSP／I2S／DAC调度验收。模型没有真实CNN计算、DDR录音对象／下载、TF卡、D效果或射频，不能把有限窗口并发升级为整机持续能力。最终v6与全部源码／APB输入哈希绑定，前五次诊断及测试台修正保留；Verilator只保留原record ingress三条精确宽度警告，任何新增警告仍拒绝。来源17项回归通过；未提供显式候选参数的两条旧审计测试跳过，未计为通过。

下一实施重点是减少W真实固件的LCD状态／MMIO往返：以有界原子owner快照和批量数据交接保留完整epoch／generation／stream／physical上下文、实际应用水位及取消门禁，重新验证补充速率。不能靠增大预填充、开放CAP3或忽略欠载宣称持续手机D成功。M／W完整消费者／TF CDC、物理资源与时序门禁继续关闭。目标板仍未接入；本阶段未发现或操作设备，SRAM／Flash均未写入。

### 8.7 原子快照与批量手机控制（2026-11-03）

已实现默认关闭的 `PHONE_BATCH` RTL、显式 paired C 适配器及两端联合模型，见[本阶段证据](push2_workstation/usb_a/reports/DUAL138K_TASK3_PHONE_BATCH_20261103.json)与[唯一批量契约](push2_workstation/usb_a/rtl/workstation/TASK3_PHONE_BATCH_CONTRACT.md)。本阶段尚未选入生产 profile，未生成新 AE350 ELF、整板网表或位流。两板继续保留8.5的封存回退：M `...a8c56437ef9af94e`／W `...86b7bda71d161a30`，原综合等效 BSRAM209／308不能转授给新源码；新资源、关键路径、物理CDC／STA和延迟均未测。旧锁和review不刷新，旧身份须使用其原提交和闭包重建，不能让当前活动源码冒用。

M仍由原PCM1 owner拥有槽、bitmap、SRC、完整key、历史屏障和最终采样应用。新增20字原子快照只观察同一计算边沿，capture ID跨CPU observer reset保留且拒绝回绕；批量执行器经原APB CDC重放完整key／命令，核对真实command ID后返回单包快照。accepted `command_id` 与实际源／历史／采样 `applied_id` 保持分离。W新增虚拟页，不截取原 `0x020..03c`；每笔控制先flush窗口并等实际M ACK水位，再交换一个请求／回复。同一128帧内最多复用7次快照，等待槽、历史变化、块结束或状态变化须刷新；不确定命令不重放。协议需双端显式version3／features `0xc0080601`，普通旧模式默认关闭新路径。

修复了初始化lease首拍可能吞包的入口缺口，并禁止batch期间普通命令抢占；故障立即撤销输出／命令权限，同时保留错误ACK排空。原APB CDC在撤销后可能停于COMPLETE，新lease必须先排空或重置observer bridge；联合模型明确只重置该bridge，不清原owner寿命、retired key或capture计数。生产组合还须按此绑定并重新证明复位消费者。

验证包括M真实异步CDC／owner的955检查与默认关闭逐拍对照27,855周期；W 610检查、40异常场景和12变异；M端点57检查与4变异。新C Native及ASan／UBSan各9,387检查，旧C开关宏四组各4,364检查。不开 `A138_TASK3_PHONE_BATCH` 时，与`6ebb5e41`的默认预处理和host对象逐字相同、结构仍96B；开启后160B，真实AE350 ROM／栈尚未测。默认端点／窗口／owner兼容回归75／89／363／603检查和来源17项通过。空闲槽字段明确是四位bitmap（15／14／0），不是数量。

真实C＋两端endpoint＋LCD transport／PHY＋锁定APB＋owner模型延长至每组200ms；仍按理想零延迟连线、非MMIO C零耗时、已建立会话／已解码恒定PCM运行。原CAPS实际保持 `0x67`，两组生产用例有查询但零窗口写、零源命令。仅测试读包装注入CAP3的四组结果如下：

| 200ms测试注入结果 | W50MHz | W约45.45MHz |
|---|---:|---:|
| 手机单流：接受128帧块／精确非零立体声owner输出 | 75／9,386 | 75／9,372 |
| 手机＋双48k分析／录音：同一计数 | 75／9,368 | 75／9,354 |
| 三流：最大相邻COMMIT的pump后观察间隔 | 3.583ms | 3.665ms |
| 三流：分析／录音交付帧 | 9,666／9,666 | 9,660／9,660 |

四组均无owner／固件／media故障，外生供给积压最多1块；取消后原owner回到legacy、队列归零且采样节拍继续。三流分析停3.96ms时录音各推进192帧，TF source最高161／256、录音导出最高4／256。每128帧实际26个窗口包，按52B外帧计手机数据＋实际ACK每方向507,000B/s；至少再计snapshot与COMMIT两对包，手机下限每方向546,000B/s，加双block6分析／录音后M→W下限1,378,000B/s。额外空闲轮询、信用、维护和状态须另计，不能将该下限当实测链路能力。旧模式40ms六组重新验证，四组注入仍复现两块后欠载／255个输出。

最大观察间隔仍超过128／48k的2.667ms；原256帧预填充没有加大，有限窗口靠既有缓冲完成，尚未得到最坏补充期限。恒定PCM也不证明不同块顺序或真实D效果。因此持续能力和物理预算继续关闭。下一阶段接入独立M／W batch profiles：显式传递M snapshot参数和observer复位，给W新增严格固件来源review／全TU编译宏／paired初始化，完成真实ELF、ROM、间接调用与栈审计，再clean prepare和整板综合。RF／SBC、真实TF／CNN／Push、长录音下载并发、D按住／松开至M DAC，以及目标板LCD吞吐／RTT／延迟仍待验。本阶段未操作板卡，SRAM／Flash均未写入。

### 8.8 显式 batch 配置、真实固件与整板综合（2026-11-03）

已将8.7的实现接入两份独立 `custom138k-workstation-task3-{m,w}-paired-phone-batch-v1` 配置，完成真实固件构建、clean prepare、独立闭包复核和两板整板综合，见[来源与综合证据](push2_workstation/usb_a/reports/DUAL138K_TASK3_PHONE_BATCH_PROFILES_20261103.json)。新增配置分别锁定980／1,074份来源；24份旧配置、review及冻结参考逐字未变，旧配置继续拒绝当前源码漂移。task2、其他工作树与旧候选保持原身份；没有生成位流或操作板卡。

M显式将snapshot参数传到原PCM1 owner；phone lease撤销只复位远端observer APB，原owner根复位、retired key和capture寿命保持。普通／矢量32声部、TF直读及菜单、HDMI和最终输出调度保留。W的27个真实编译单元均显式启用 `A138_TASK3_PHONE_BATCH`，实际调用paired初始化；CNN的signal＋CQT BSRAM及CPU／BLE同一60秒录音对象保留。TF来源检查只为这个已知包装文件核对完整包含链hash后读取原phone-window宏，不新增通用绕过规则。

| 本轮实际产物 | M | W |
|---|---|---|
| candidate后缀 | `3bb41077d21baadc` | `cda40ccde09fd1ee` |
| 配置SHA256 | `4818e7bbf0e511e1b92ddea2fbdeccc55ea3c22766ebd58e3c15c0dd36b458ac` | `c2f919997690990ce2caf3aede6ec8e2016901d6e8cf433b7a7015b1071e6fef` |
| 编译输入／综合等效BSRAM | 287／209 | 200／308 |
| 严格综合审计 | 12／19，未通过 | 11／17，未通过 |
| 50MHz／76.8MHz综合估算 | 41.281／58.651MHz | 48.732／75.574MHz |
| 位流／UserCode／物理资源／布线STA／实体延迟 | 均未生成或未验 | 均未生成或未验 |

BSRAM等效数与旧phone-window候选相同，不代表物理BSRAM或时序通过。新provider的生产root审计仍登记未审阅的 `alias=None`，因此严格拒绝并阻断其下游时钟／CDC检查；不能把本轮未执行到的完整消费者封印和TF CDC算作通过。独立只读VG诊断确认实际根Q为M `terminal_ready`／W `reset_n`，两板各35位启动状态的全部 `2^35` 赋值方程及4项破坏控制通过，但未自动提升生产注册。M批量执行器保留1,357 FF及640位执行器快照，原owner快照保留414 FF；W保留969个批量FF及238位请求载荷。独立named FF清单不证明被合并／常量字段的读mux语义，也不替代功能或物理CDC验收。

W真实ELF审计覆盖141个可达JALR，保守栈上界896B；热代码49,952B（增加3,632B），静态DLM 7,664B（增加64B），ROM仍128KiB，BIN仍90,416B。关闭新宏后，27个真实对象及ELF／BIN／ROM与冻结`6ebb5e41`逐字相同。M真实board／runtime／APB／owner定向检查43＋35项及6个变异通过；该fixture裁掉无关DSP／PLL／显示子模块，不冒充整机演奏。W来源3项、固件5项和审计7项回归及对应破坏检查通过；来源17项及三条干净检出prepare的23项通过，277份基线文件未变。旧16KiB AE350 recording API仍超容量760B，相关套件9／10，保留失败而不扩容放行。

生产CAP3、实测延迟有效位及LCD probe／budget／business默认仍关闭，8.7有限理想线模型不能转授为真实固件持续期限或实体链路能力。下一阶段把新VG的root／batch结构证明纳入严格审计，继续逐项解决消费者与完整TF CDC，再做完整物理实现和最坏补充期限验证。目标板到位后才测LCD电气、吞吐／RTT／拥塞，以及真实手机D按下／松开至M DAC、TF／CNN／Push、长录音／下载并发和控制到声音延迟；当前连接板继续留给其他分支，SRAM／Flash均未写入。

## 9. 阶段、提交与证据

每阶段完成针对性验证后commit、push并回写本节。输出固定目录、配置和来源；两板分别列源提交/输入hash、固件/模型、UserCode、位流SHA、物理资源、setup/hold/recovery/removal、PLL/CDC、LCD及控制到声音延迟、功能范围与回退。没有位流时明确`bitstream=null`，不复用已接受身份。

| 阶段 | 当前状态/退出条件 |
|---|---|
| T3-01 分支/原文/分工/预算 | 已完成，见[来源/硬件边界核对](push2_workstation/usb_a/reports/DUAL138K_TASK3_PLAN_20261101.json)；硬件吞吐均待测。原始规划备份在`~/.cache/gw138k-task3-20261101/task3-original-ignored.md` |
| T3-02a 第一计算迁移源码 | 已完成[源码/仿真证据](push2_workstation/usb_a/reports/DUAL138K_TASK3_REVERB_SOURCE_20261101.json)：M真实链退出本地混响的显式分支，W真实混响/历史RAM；端点15,076帧、18故障场景，整链37,312帧、全部效果顺序/mask/双率及3次有尾音普通屏障通过，整链最大538计算时钟。默认19项、来源17项、候选清单11项通过；生产DEMO宏关闭且原层次不变 |
| T3-02b 同条件资源差值 | 已完成[真实综合/清单/网表证据](push2_workstation/usb_a/reports/DUAL138K_TASK3_REVERB_SYNTHESIS_20261101.json)：M退出20SDPB/19MULT27X36，W实际承担；来源`06c55d8a`。候选工具12项来源/篡改测试通过，首轮不支持的工具宏选项失败保留，改为校验provider后新目录完整通过。仅子系统综合，整机profile传播、LCD/CDC和完整P&R另验，不把仿真538时钟当物理控制延迟 |
| T3-03 LCD可用线与实测 | 用户确认同号网络n→n；按此实施互补收发/默认高阻。待目标板电气/供电/方向/时钟核对；双向有效吞吐/最坏RTT/拥塞/重连；先据此决定实时往返效果与其他PCM通路 |
| T3-04 M本地基础/TF前端 | 新DIRECT候选…68efbb0415ea234e，CRC1/cache1/r3、269输入prepare/独立verify/实际综合通过，32声部及普通矢量保留；综合BSRAM216。FAST12双率11,000+97帧无欠载，CRC/FAT来源和失效负控通过；完整TF CDC仍拒绝，综合时钟估算未达标。音频CRC原子发布、任意碎片/真实卡/remount、完整P&R及实体延迟待验 |
| T3-05 W CNN/分析/长录音 | 显式W媒体角色…01a09c94f065b7ba实际综合BSRAM228，CNN/raw/HCI保留；DDR配置4Hz/96,000帧真实任务和取消后重跑75检查通过，仿真单次约7.379秒；另选signal＋CQT本地…5ca0cbd4d7fcfae1（308BSRAM）继续框架，等价两任务75检查/约3.225秒，signal-only第二任务未完成。CPU/BLE同一60秒对象及下载组件通过，APB112/161检查保留。整曲/质量、长对象重连、44.1k、真实并发和完整CDC/P&R未验；旧候选软件tap默认关、LCD固定down；新paired实际接入见8.1 |
| T3-06a 完整逻辑框架 | 真实TF/CNN流、原子谱面、手机PCM1/clock代理、M最终tap→W原对象入口、有界队列已装配；默认旧行为及旧锁保留。见框架报告；不继承旧候选物理/功能验收 |
| T3-06b 同对板级集成 | 新paired profiles已实际接入真实M/W owner、HCI单对象、LCD/F808与控制门控，clean prepare及整板综合完成；严格离线审计和物理门禁仍有失败/未验项。手机D→M DAC、全曲/Push、长录音/下载及实测并发/时序/吞吐/延迟仍待验，见8.1 |
| T3-06c 同对综合审计对齐 | v6实际综合M18/19、W17/17结构门禁；M完整TF CDC仍拒绝，两板综合时钟估算未达标，完整源CDC/物理STA未验。LCD理想线模型确认逐采样封包不足，转入有界PCM分块/独立流队列迭代，见8.2 |
| T3-06d PCM分块与流隔离 | 分块/独立队列/信用/能力与故障协议已接入，110＋371＋8＋89检查及实际LCD理想线双48k模型通过；v8两板实际综合完成，新增端点使封存release清单证明拒绝（M17/19、W16/17），源CDC/物理门禁仍关闭，见8.3 |
| T3-06e PR 审查与 CPU48 | PR2/3 适用改动已合入本分支；新 M CPU48 实际综合等效 BSRAM217→209、全 ROM 核验，严格17/19，W v8/唯一对象与18旧锁保留。未证明物理时序改善，见8.4 |
| T3-06f 手机有界分块 | 新显式 phone-blocks 配置与原 M owner 接通，真实端点/CDC/owner 603 检查及两板实际综合完成；等效 BSRAM M209/W308，原19锁保留。root/ROM/provider 证明补齐；严格 M17/19、W16/17，消费者/held CE/TF CDC、时序、三流及物理门禁仍未通过，见8.5 |
| T3-06g held／真实固件LCD负载 | M局部提交耦合7项／66破坏控制通过，历史消费者封印保留；真实固件＋LCD＋原owner的6组模型完成。生产能力继续关闭；4组测试注入均复现欠载，三流录音／分析继续，真实固件状态往返成为下一优化重点。没有新综合／位流／板测，见8.6 |
| T3-06h 原子快照／批量控制 | 默认关闭的新RTL／C与真实LCD模型完成；200ms四组注入各75块、无欠载，生产CAP3仍关闭，取消后原owner归零；旧模式负例保留。新profile／真实ELF／整板资源时序和实板未验，见8.7 |
| T3-06i batch生产来源配置 | 新显式M／W配置、真实W ELF、两板clean prepare与整板综合完成，等效BSRAM209／308；严格12／19、11／17，新的root生产注册及下游完整门禁未闭合。旧配置与回退保留，持续能力与实体链路仍关闭，见8.8 |
| T3-07 硬件收敛 | 目标板到位并确认身份后必要SRAM验证；完整32声部/向量/效果/HDMI/TF/识别/录音证据和回退；Flash另授权 |

禁止用全量资源重写、放宽时钟/false path、删特性或报告字段代替门禁。子系统收益必须再经整机同条件P&R确认。新扩展配置进入现有`build.py`/显式profile；本轮子系统综合工具只用于分工验证，整机集成后收敛或退役，不成为新编号生产构建器。
