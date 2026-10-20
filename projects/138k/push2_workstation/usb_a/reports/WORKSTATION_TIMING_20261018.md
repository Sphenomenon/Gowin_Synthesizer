# 2026-10-18 整机时序修复

p34于23:14:43结束，工具报PR0004：9460条网络未布通，返回码1，没有有效的最终STA，不能采用或沿用旧时序结论。
p34的RTL逐周期、真实Gowin网表四态对照和新18项整机回归均通过；综合BSRAM217，功能资源保留，但不能据此证明可布通。
p27仍是最接近闭合的完整结果：PLL／CDC通过、hold为0，最差setup为-0.018ns。整机时序尚未闭合。
当前无构建在运行。工作区保留p34实验RTL和证据，未切换正式入口；后续需重新调整长路径结构并验证布线可行性。

时钟目标保持50/76.8/48/100/148.5 MHz及原CPU、DDR PHY关系。
最终闭合须同时检查布线Fmax、setup/hold端点TNS、recovery/removal和CDC线路。
综合估算或构建成功不作为闭合依据。

## 改动

- 音频最终量化分6级，保持64位累加、精确三倍增益、舍入、饱和及正负号语义。
  比旧实现增加4个音频时钟周期，不改变48 kHz采样时基。
- 矢量音源保留原音符ROM与32位合法性检查；声部分配／释放直接生成最低下标的一位选择，
  消除优先编码后再解码，保持8声部、同音释放顺序和原事件时序。
- Push曲谱十进制用16步double-dabble；数值稳定后34个USB周期内完成。
  主界面／曲谱像素的字符与背景寄存一级，MMIO已有ready路径多等一拍。
- 138K包装层为两路TF诊断状态补50 MHz两级同步。
- 约束仅补明确同步器首级、握手保持字和Gray指针。Gray飞行时间限10ns，
  不对整个时钟域设false path，接收第二级及业务路径继续检查。
- `--cnn-timing85`只从固定full85快照选择6个CNN时序文件，其余67个CNN目录文件
  逐字采用full83。清单SHA256固定为
  `c5aef03165e18b7f71119e6b563516feb00c88de86a156a2715f32a183ddef2c`。
  活动CNN的Flash改动不覆盖候选；新策略名为`full83_plus_clk50_timing85`；缺少固定快照即停止，不回退活动CNN。

固定快照：`results/song_guide_full85_clk50_20261007_084539_884006_route1/`。
六个基准文件与Git提交`3f762f5ebabf78c28156d91a022d3a6c5547776b`逐字一致，
核对结果为`workstation_timing_20261018/pinned_cnn_git_sources.json`。
六处来源及历史数值验证见[50 MHz修复记录](CLK50_TIMING_FIX_20261007.md)。
本次候选不能沿用该旧位流的时序或板级验收结论。

## 已完成的功能验证

- 最终量化8738个结果，覆盖64位极值、舍入边界、符号、模式及PANIC。
- 完整音源5760个PCM采样与full83旧实现逐位一致。
- 曲谱1536000个像素、主表面1229600个像素与旧图一致。
- MMIO3101次读取覆盖连续地址、跨行、无效列、回退、帧重启和重连。
- 矢量事件2656次、1776帧立体声，全部声部寄存器逐周期与旧版一致。
- 原CNN策略6项、新固定时序来源4项、时序／裁剪门禁7项检查通过。
- 独立Gowin综合网表与旧RTL的四态对照：213522周期、2656次事件、1776帧输出一致。
  使用未改动的厂商仿真模型，不代表完整整机网表或布线时序验证。
- 138K接入初始化、断开作废、PANIC和25K曲谱隔离在当前候选依赖上重新通过。

p4、p5已否决并停止：Gowin没有按行为仿真语义实现由另一ROM派生的
`note_allowed`初始化，矢量音源及其9块BSRAM被裁掉。旧新行为仿真通过仍不能
证明综合实现完整。现已撤回派生表，并在资源审计中增加几何ROM不可被裁掉的门禁。
歌名192字节双读表明确使用分布式RAM，避免像素寄存后被自动改成两块BSRAM。

p6完整布线：`results/timing_p6_vec_cnn85_20261018_031304_461827/`。
SYN BSRAM=216，PNR=260，矢量音源仍占9块。实际Fmax与目标：

| 时钟 | 目标MHz | p6布线MHz | setup负端点 |
|---|---:|---:|---:|
| clk50 | 50 | 43.376 | 574 |
| audio | 76.8 | 56.597 | 5902 |
| DDR UI | 100 | 73.883 | 955 |
| USB | 48 | 45.718 | 19 |

全局详细报告另发现TF字节FIFO／状态首级的67条异步hold路径，
及USB复位释放直达音频业务寄存器的3条recovery路径。默认摘要hold为0仍不足以判定通过。
失败报告与输入哈希归档于`workstation_timing_20261018/p6_routed_failure.json`。

p7完成SYN，BSRAM=216；P&R前因两处约束引用合并／裁掉的对象而停止，未产生布线结论。
p8（后被p10取代并停止）：`results/timing_p8_release_20261018_045209_948170/`。
逻辑准备目录为`results/workstation_scope83_timing85_20261018_045112_115966/`，
输入600项，加物理参考文件后601项。
针对实际路径继续修改：

- USB生命周期／取消由独立本地状态线传递，普通MIDI RAM数据不再参与生命周期判定；
  完成探测仍须端到端握手。音频业务状态增加本域两级复位释放。
- 32声部Note Off／触后直接一位选择；延音扫描预读下一键的保留位，切断128键动态选择到声部写入的路径。保持原最低下标规则及每周期握手。
- 显示采集仅为PCM、元数据与绝对值加一个源时钟寄存级，保留现有双bank／六极触发。
- Push网格用8组定界比较，替换整数除26／取余及除10／取余；像素逐点一致。
- 暂存TF DMA复用既有写缓冲、字节并行加法、读后计数预备和可用量比较变换。
- 暂存HDMI顶层复用现有8客户端请求槽及注册返回；不增加DDR客户端、地址区或BSRAM。
  原冻结源码和地址图保持原样；**暂存的HDMI包装层已变换**，变换前后哈希独立记录在
  `build_metadata.json.bus_timing`。两份传输模块从现有仓库逐字复制到`rtl/timing`，
  不覆盖73个CNN目录文件，也不接入Flash启动。
- 补TF字节FIFO的Gray飞行10ns／异步hold约束和既有状态首级；继续检查第二级及业务路径。

p7的8738量化结果、5760整音源PCM、全部像素／MMIO、接入回归及18项整机门禁均通过。
新增显示采集逐周期对照30022周期，原始／六极触发分别71／62次发布，RAM和元数据完全一致。
TF完整缓冲拓扑42种变体／背压／零周期响应／在途重启通过；共享DDR三种标签深度、8客户端
命令／掩码内存／返回顺序通过。TF读计数和可用量的65／64位全输入SAT证明通过。
p8新增整条控制链180949周期新旧对照，覆盖1548个释放周期、MIDI0／127、两种音源、
CC64／CC123和释放途中PANIC；逐周期事件／握手／PCM／拒绝计数均一致。
原有正常接入场景仍要求deadline、overflow和drop为0；压力场景的原有限频拒绝按旧版逐项对照。
p8未产生完整布线报告；最终候选仍须用自己的布线时序、资源和线路审计判定；旧p6功能证据保留为历史，不作为p8布线结论。

本次验证目录：

- `results/timing_equivalence_20261018_031349_840368/`：量化、整音源、十进制、像素和MMIO。
- `results/scope_event_ab_20261018_032734_629898/`：逐周期矢量事件对照。
- `results/scope_synth_ab_20261018_032745_192458/`：独立Gowin网表四态对照。
- `results/workstation_scope83_timing85_20261018_031221_737775/current_regression_20261018_031349_813656/`：18项整机回归。

最新scope集成测试最慢1071/1600音频周期，混合运行deadline misses=0。
新增量化流水线4周期为约52.083ns；这是算法延迟，不改变48kHz时基。

## 复现

```sh
python3 build.py --current-workstation --prepare-only --cnn-timing85
python3 tools/build_workstation_timing.py --source results/上一步输出目录 --flow all --label verify
python3 tools/audit_workstation_timing.py results/上一步输出目录 --require-closed
python3 tools/audit_workstation_cdc.py results/上一步输出目录
```

上述流程只做本机离线构建与审计，不操作板卡；诊断候选不分配发布UserCode。
`--cnn-timing85`为显式选项，默认整机入口仍使用full83全部73个CNN目录文件。
可用`--route-reference results/已完整布线目录`启用物理参考；必须重新SYN，器件、引脚、IP和初始化数据完全一致，旧网表与位流不复用。厂商依据为SUG100-4.4.6E第42页、SUG1220-2.0E第44页。


## Note On／Off与USB本地总线补充

p9停止于综合，已被p10取代；不是通过的布线版本。
p10：`results/timing_p10_note_mmio_20261018_051540_858609/`，
逻辑目录：`results/workstation_scope83_timing85_20261018_051508_944162/`。

- 两种音源的Note Off键号独立进入释放比较；Note On仍从原事件寄存器取键号。
  延音扫描不再经过Note On调音ROM及合法性判断；事件握手、释放顺序及PCM逐周期不变。
- 矢量音源按固定ROM字逐项比较上限，再选择一位结果。直接连续引用原ROM，
  不使用被否决的派生`initial`表。真实Gowin综合网表213522周期／2656事件／1776帧对照通过，资源完整。
- USB CPU／屏幕流与原MMIO控制器之间增加一个未完成事务槽，寄存请求和响应。
  下游真实提交后才回确认，通常多2个USB时钟；背压时保持请求，防止重复提交。
  端点、寄存器地址、消息、重试和会话格式不变。
- 去掉TF清空接收器中50MHz同域首级的不必要false path；仅保留DDR异步首级例外。

新增本地总线2500次读写／背压及256像素／512字节编码块测试通过。
实际MMIO控制器的接入回归通过，180949周期音频旧新对照通过（1550释放周期、一次释放中PANIC）。
p10普通布线已完成，实际剩余问题见下节；旧增量候选停止，未产生完整结论。

p10的18道整机回归和8项量化／音源／像素／MMIO门禁已通过，输入哈希保持不变。已补下游阻塞时复位的旧请求取消测试。

普通路由对照：`results/timing_p10_route0_20261018_062851_181195/`，相同RTL／IP／初始化数据／CST／时钟，路由选项为0，无旧物理参考。Gowin在`run pnr`期间仍重新执行了SYN，最终按实际输出是否逐字复用记录，不能只凭命令名称声称跳过综合。该候选也须实际STA通过后才能使用。

当前TF读计数／可用量SAT已直接绑定p10实际暂存源码，65／64位全部输入证明通过，见`workstation_timing_20261018/tf_read_*_source_bound.json`。

p10实际SYN BSRAM为217／340（p8为216）。矢量音源原9块仍保留，Gowin为Note On／Off分路后的调音／合法性选择另映射1块，子树共10块。8路DDR缓冲变换本身不增加BSRAM。最终物理块数按P&R另报，不能继续套用p6的260。


## p10完整结果与p11修复

p10普通布线完成于2026-10-18 07:45，目录`results/timing_p10_route0_20261018_062851_181195/`。
全局摘要setup／hold TNS均为0；详细报告仍有异步hold，不能据摘要判定闭合。

| 时钟 | 目标MHz | p10布线MHz |
|---|---:|---:|
| clk50 | 50 | 54.110 |
| audio | 76.8 | 76.800 |
| USB | 48 | 48.665 |
| DDR UI | 100 | 210.896 |
| DDR PHY | 400 | 2598.775 |
| video pixel | 148.5 | 169.810 |
| CPU bus | 50 | 69.852 |
| CPU core | 100 | 1244.244 |

SYN BSRAM=217，PNR=262／340。18组Gray指针、5路已有状态同步与scope握手保持字物理审计通过。
失败点：DDR域`u_ddr_command_buffer/full_s1`和`u_ddr16/rsp_valid_o_s0`直达50MHz UART采样，
hold分别为-0.430ns和-0.406ns。独立PLL_INIT检查得到参考PLL RESET完整传播10.964ns，超过10ns门槛。
原始结果见`workstation_timing_20261018/p10_routed_partial_success.json`与`p10_pll_failure.json`。

p11准备目录`results/workstation_scope83_timing85_20261018_075051_477454/`；
布线目录`results/timing_p11_diagnostic_pll_20261018_075101_959182/`。
仅在p10基础上继续两处修复：

- 暂存`basic_pitch_workstation_link.sv`将5个DDR域UART诊断电平先经过50MHz两级寄存器。
  保留10位诊断字段的位置；诊断电平晚2个50MHz周期，不作为事件计数或一致快照。
  只给首级D设异步入口例外，第二级和消费路径继续正常检查。
- 视频两组PLL_INIT寄存器到ICPSEL／LPFRES／RESET的数据路径限4ns，给时钟输入传播保留余量。
  独立VO／SDF完整传播检查仍为10ns，不改变板卡引脚或PLL配置。

6个CNN时序基准文件仍来自固定full85；其中link仅再应用上述诊断变换。
`tools/workstation_cnn_cdc.py`要求旧片段唯一匹配，并在`cnn_source_audit.json/local_transforms`
记录变换前后SHA256。另5个与固定full85逐字一致，其余67个仍逐字采用full83；活动CNN未修改。
1338个时钟检查覆盖全部32种诊断电平组合、异步相位、复位及UART位号，测试通过。
p11的18道整机回归已通过；8组功能证据已逐项核对实际源码哈希，归档于`workstation_timing_20261018/p11_functional_verification.json`。仍需实际布线、全部详细时序和PLL_INIT物理审计通过后才能验收。


## p11／p12实际复核与p13／p14

p11完整布线未闭合：audio Fmax为75.751MHz，audio与DDR UI有setup负端点。
新增5路DDR诊断同步的网表结构、全部18组Gray和scope保持字物理检查通过。
PLL独立审计首条失败为10.072ns，完整扫描最大为RESET的10.819ns。
旧4ns `set_max_delay`虽匹配对象，但厂商报告没有PLL控制引脚时序路径，因此不能声称它约束了传播。

p12只将路由选项改为1，逻辑、时钟与CST均与p11相同。
8个Fmax目标与全部详细setup／hold／recovery／removal已通过；
50／audio／USB为52.385／76.832／48.563MHz，DDR UI为243.958MHz。
独立PLL检查仍失败，完整传播最大11.289ns，因此p12也不验收。

p13／p14采用同一新准备目录`results/workstation_scope83_timing85_20261018_101153_780389/`：

- 原参考PLL的官方初始化逻辑局部放置到`R[100:108]C[24:44]`。
  仅追加内部非排他的GROUP／GRP_LOC，复用仓库已有区域选择，不改I/O球位、I/O属性、PLL站点或配置。
- 撤去无实际STA路径的PLL4ns例外。完整VO／SDF传播仍须小于等于10ns。
- audio同域最大延迟限12.5ns，DDR UI同域限9.4ns，给原13.021ns／10ns周期留物理余量。
  所有时钟周期和hold／复位检查保持，新增预算更严格。
- 两者分别用路由选项0／1，均重新SYN。全部业务RTL、固件、ROM和协议与通过功能回归的p11逐字一致。

未改原仓库引脚约束文件；离线暂存CST只追加上述内部放置语句，验收脚本核对其完整前缀。
当前仍须完整物理结果通过，未烧录。


## p13结果与后续候选

p13的参考PLL局部放置通过独立检查，完整最大传播7.704ns；全部18组Gray与5路诊断接收也通过。
但全局更严格的audio／DDR UI `set_max_delay`使该布局常规时序恶化，p13不验收。
p14保留相同严格预算并用另一种路由作对照，最终也失败；PLL最长7.357ns通过，音频74.795MHz、USB46.228MHz未达标。

p15／p16保留有效的参考PLL内部局部放置，撤去两条新增的全域严格预算；
原时钟、原同域setup／hold与10ns PLL传播门槛保持。准备目录：
`results/workstation_scope83_timing85_20261018_104157_394609/`。
布线目录分别为`timing_p15_pll_locality_20261018_104206_412321`与
`timing_p16_pll_locality_route0_20261018_110123_900985`，路由选项分别1／0。
业务源码与已通过的p11完全一致，功能证据8组均已按哈希绑定；没有增加新的功能修改。
完整构建入口现自动生成全局详细报告并执行时序、CDC、scope与PLL物理门禁。


## p15／p16结果与高扇出优化

p15／p16均通过PLL内部传播，常规setup仍有少量负端点，不验收。
p16最差详细slack为-0.081ns，audio／USB Fmax为76.340／47.944MHz。
剩余路径包括sample_tick、事件控制、TF发射使能和视频渲染控制；仍按单周期检查。

p17只将内部GROUP范围缩到PLL动态输出的RomDreg、state、enable与reset驱动，减少对其他初始化逻辑放置的干扰。
p18／p19在同一准备目录上启用厂商`set_option -replicate_resources 1`，分别用路由1／0。
厂商SUG1220-2.0E第40页说明其复制高扇出资源以改善时序；不修改RTL、固件、ROM或时钟。
工具配置依据为本机IDE的`data/config/rtlplaceoptions.xml`与`rtlrouteoptions.xml`。
准备目录`results/workstation_scope83_timing85_20261018_114818_357495/`；当前等实际STA、CDC与PLL复核，不提前验收。


## p20保留布局参考与p21

p19高扇出复制明显恶化常规时序，排除；p18同选项的另一种路由随后被停止，无完整物理结论。
p20从常规时序已通过的p12读取完整物理参考，逻辑／固件／IP／初始化数据完全一致；
仅允许暂存CST追加精确的PLL动态驱动GROUP后缀，原CST前缀含全部I/O球位逐字不变。
重新综合后做增量物理更新，旧物理结果只提供参考，验收仍检查新VO／SDF与完整STA。
p21采用厂商文档允许的placement algorithm 3、route1，逻辑和约束同p17，无高扇出复制。
p20最终PLL通过、常规STA失败，见下方；p21布局策略3的50MHz、音频、DDR UI也失败，详见`p21_sta.json`。


p22／p23使用`set_option -opt_goal timing`，厂商SUG1220-2.0E第23页定义为时序优先综合；
分别用布局2／4、路由1。器件、I/O、逻辑源码和所有验收门槛不变，SYN BSRAM仍为217且几何子树10块保留。
p18已作为无效复制策略停止，没有完整物理结论。p19失败结果保留。

## p20与校准状态补充

p20目录：`results/timing_p20_retain_closed_layout_20261018_124229_175716/`。
参考p12物理布局没有同时保住常规时序；失败详见`workstation_timing_20261018/p20_sta_failure.json`。
PLL通过记录为`p20_pll_pass.json`，不能据此宣布整机通过。

p24准备目录：`results/workstation_scope83_timing85_20261018_140356_030395/`；
布线目录：`results/timing_p24_calibration_cdc_20261018_140425_210328/`。
CNN link选定SHA256为`6503ada6797a2fb81ce2fae8ecc25615551e02bb4f33f9fcec37018d3a281cbb`。
在p11五路诊断同步之外，新增校准完成状态同步；模型请求的DDR域`memory_calibrated`门控保持原代码。
UART两处校准状态均使用同一个50MHz同步输出，位定义不变、晚两周期。
当前八组功能证据已按p24所有选定文件重新逐项绑定，通过；布线闭合仍待自己的实际报告。

## 当前七路UART诊断候选p25

准备目录：`results/workstation_scope83_timing85_20261018_141031_252897/`。
布线目录：`results/timing_p25_complete_uart_cdc_20261018_141043_879626/`。
CNN link选定SHA256：`0ef34913bdcaf452935b6762d164215a9171ca47926ad23f3bca35c922f935a0`。
DDR复位释放也是DDR域信号，作为状态采样时一并同步；其实际复位用途与DDR控制不变。
其余业务源码与p10／p11已通过功能证据逐字一致，八组输入绑定通过。

p26使用与p25逐字一致的逻辑／约束，采用原默认综合与路由0作对照，目录`results/timing_p26_uart_cdc_route0_20261018_141635_351023/`。14时再次fetch，远程main仍为`abe43c7`，无新增提交。

p27同一七路同步源码采用原默认综合、路由1，目录`results/timing_p27_uart_cdc_route1_20261018_142516_456857/`。
p23布局4导致常规时序明显恶化，且TMDS PLL传播10.418ns超限，排除；详见`p23_sta.json`与`p23_pll.json`。
p22旧五路诊断版本在路由phase0被p25替代并停止，未产生布线结论。

## 定向预算报告块修正与p29

p28准备目录末尾追加的两条预算被实验工具刷新报告块时截去，实际没有应用，已停止；不能将它记为预算优化结果。
工具现在只删除自身精确生成的报告命令块，保留其后的约束；不匹配则失败。
p29完整SYN使用同一七路同步源码与真实保留的定向预算，并以p12提供物理参考；
IP／ROM／器件／原I/O约束逐项相同，新的VO／SDF和STA才用于判定。
布线目录`results/timing_p29_margin_closed_layout_20261018_150934_186864/`，预算两条均已核对存在。
p26完成：PLL和全部CDC通过，异步hold为0；常规setup仍失败，详见`p26_sta.json`，不验收。

## p27近闭合结果与p30

p27完成：七路DDR状态同步、18组Gray、其余电平同步及PLL传播全部通过。
常规最差setup为-0.018ns；音频76.710MHz／目标76.800MHz，像素148.108MHz／目标148.500MHz；
DDR UI、TF发射使能和显示meta也有极小负路径。详见`p27_sta.json`与`p27_pll.json`，仍未验收。
p30保留p27完整物理参考，业务逻辑／固件／ROM逐字不变；只对已有违例的三个同域路径收紧预算：
audio12.8ns、DDR UI9.7ns、pixel6.4ns，分别严于原周期13.021／10／6.734ns。
所有时钟要求、hold和复位检查保持；严格预算也纳入通过条件。
目录`results/timing_p30_incremental_domain_margin_20261018_154055_382652/`。

## 中断恢复p31

p25／p29／p30均无`tool_result.json`和完整布线STA；状态核对见`workstation_timing_20261018/interrupted_20261018_1554.json`。
p31目录：`results/timing_p31_resume_domain_margin_20261018_155705_399572/`。
沿用p30的audio12.8ns／DDR UI9.7ns／pixel6.4ns严格预算，目标时钟和所有hold／复位检查保持。
命令、PID和脱离会话日志见`workstation_timing_20261018/p31_launch.json`；只在本轮实际STA、CDC、PLL及输入审计全部通过后验收。

p32作为物理参考对照：同一准备目录、同样严格预算、默认综合和路由1，重新综合后采用p12物理提示；IP／ROM／原I/O约束仍逐项相同。
目录`results/timing_p32_domain_margin_reference12_20261018_160005_905146/`。与p31均为独立暂存目录，不互改输入；两者都必须通过自己的完整报告。
恢复后重新核对：CNN来源边界10项、时序／裁剪门禁10项、p31当前选定源码8组功能证据全部通过。日志见`workstation_timing_20261018/resume_checks.json`；这些检查不代表布线闭合。

16:07核对：p31／p32均已完成综合，BSRAM均为217，必须保留的功能资源检查通过，进入布局。
`watch_resumed_candidates.py`只等待这两轮完成，并自动归档各自STA／CDC／PLL；只有全部通过才运行完整输入与功能证据汇总。
该脚本不访问板卡、不切换正式入口、不提交代码。结果写入`resumed_candidate_audits.json`；若完整门禁通过，汇总另写`verification.json`。

恢复命令：

```sh
python3 tools/build_workstation_timing.py --source results/workstation_incremental_margin_20261018_154046_134049 --flow pnr --label p31_resume_domain_margin --route-option 1 --reuse-synthesis-from results/timing_p30_incremental_domain_margin_20261018_154055_382652 --incremental-from results/timing_p27_uart_cdc_route1_20261018_142516_456857
python3 tools/build_workstation_timing.py --source results/workstation_incremental_margin_20261018_154046_134049 --flow all --label p32_domain_margin_reference12 --route-option 1 --route-reference results/timing_p12_diagnostic_pll_route1_20261018_085002_361936
```

## p31／p32完成与p33定向验证

p31结束16:56:39，p32结束17:10:59。两轮SYN／PNR BSRAM均为217／262，输入未变，功能资源保留检查通过；PLL／CDC通过。
常规时序失败，审计见`workstation_timing_20261018/resumed_candidate_audits.json`及`p31_sta.json`／`p32_sta.json`。
两轮额外严格预算下最差setup为-0.402／-0.287ns；这些预算比p27更严，不能直接用数值差比较改善程度。
p32像素155.628MHz达到148.500MHz，但audio76.412MHz低于76.800MHz；且严格DDR／pixel预算仍有负端点，不能验收。

p33准备目录`results/timing_p33_measured_paths_20261018_173136_545041/`，实际构建`results/timing_p33_measured_paths_20261018_173136_739962/`。
复用p27完整物理参考，重新综合；业务逻辑／固件／ROM逐字不变，原周期和所有hold／复位检查保留。
只对TF发射、视频帧计数／meta／背景、音频读FIFO／gain到slot、矢量包络、delay指针这8组实际违例路径增加较严max_delay。
这是离线物理实现实验，不能写成已修复；各组对象必须在工具实际输入中生效，并以本轮STA／CDC／PLL判定。
`watch_p33.py`等待本轮结束并归档审计到`p33_audits.json`，全部通过才运行完整来源和功能证据汇总；不操作板卡。

## p33结束与p34结构修复

p33结束18:36:02。SYN／PNR BSRAM为217／262；PLL完整传播最大8.058ns（门槛10ns），CDC通过，hold为0。
50MHz／audio／USB为49.460／75.186／47.354MHz，目标50／76.8／48MHz；像素155.096MHz达到148.5MHz。
常规setup失败，严格预算下最差-0.308ns，147个setup负端点；详见`p33_audits.json`／`p33_sta.json`，不验收。

p34准备目录：`results/workstation_scope83_timing85_20261018_214242_333215/`。
唯一源码变化为`rtl/audio/scope_vec/scope_vec_engine.sv`：每声部本地计算包络，再由声部索引选择写入；消除索引先选读整个包络字、经过算术逻辑后再选写的组合路径。
不增加状态、不改变事件／采样时序、ROM、8声部数量及Note On／Off规则。原时钟／CDC／PLL检查保持，不加入p33额外预算。
与p27逐周期比较已过：213522周期、2656事件、1776立体声帧及全部声部状态一致；实际Gowin综合网表四态对照尚待完成。
此时尚无p34整机布线结论，不能将结构改动记为时序已修复。

21:45更新：真实Gowin网表四态对照通过，输出周期与p27完全一致；网表SHA256为`f23d878049c690144d932c7882cfec7e48b3dee5e9d0b7e76180ef1d026172f0`。
RTL逐周期与综合网表证据分别位于`results/scope_event_ab_20261018_214306_268939/`、`results/scope_synth_ab_20261018_214306_270701/`。
p34完整构建`results/timing_p34_vector_local_envelope_20261018_214554_355618/`已启动，使用p27物理提示、重新综合，不复用旧网表作为逻辑。
来源边界10项与时序门禁10项通过；省略新增的等价证据标志时，旧汇总器仍拒绝这个RTL差异，反例检查通过。
`tools/workstation_vector_timing.py`固定唯一变换及参考哈希；汇总器逐字验证p34只有这一处源码变化，要求真实等价证据，最终验收另要求新准备目录的18项回归通过。
当前18项回归独立运行，尚未完成；后台`watch_p34.py`会在整机工具结束后归档自己的STA／CDC／PLL，全部门禁通过才写最终汇总。不烧录、不切换正式入口。

22:03核对：p34完整综合完成，BSRAM为217，功能资源保留门禁通过；布线Phase1完成，尚无最终STA。
当前准备目录的18项整机回归全部通过，含8项scope／TF合并、TF16项、Delay DDR与识别隔离；最大工作站周期1071／预算1600，共存deadline miss为0。
新回归目录`results/workstation_scope83_timing85_20261018_214242_333215/current_regression_20261018_215740_243690/`。
8组功能证据已重新绑定新回归和p34源码，`current_functional_verification.json`明确记录`fresh_18_gate_regression_passed=true`；未生成最终时序验收文件。

## 23:20汇总：p34布线失败

p34在23:14:43结束，`tool_result.json`返回码1，所有输入哈希保持；厂商错误`PR0004`明确为9460条网络未布通。
虽然工具生成了资源／引脚报告和部分VO，但未产生有效的完整布线STA／SDF，不能用于时序或PLL验收。`p34_audits.json`记录`build failed; no acceptance`，没有最终`verification.json`。
资源报告Logic77280／138240、Register43450／139095、CLS54688／69120（80%）、BSRAM262／340；资源未满不能证明布线可行，也尚不能仅据此确定根因。
已通过的功能等价与18项回归保留；p34每声部本地包络计算仍为待处理实验改动，不作为整机可用版本。
当前无工具构建在运行；最佳完整结果仍为p27，setup最差-0.018ns。下一步须调整组合路径结构与布线负载，再重新验证，不能继续沿用“布线运行中”状态。
本轮没有烧录、板测、I/O引脚改动、提交或推送。状态快照见`workstation_timing_20261018/status_20261018_2320.json`。
