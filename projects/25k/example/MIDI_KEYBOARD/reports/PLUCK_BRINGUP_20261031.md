# 25K 弹拨输入与电脑 GUI：2026-10-31

## 范围与实板边界

本页保留2026-10-31的实验与阶段状态；2026-11-01的B2 SRAM部署、当前GUI与剩余噪声/方向验收见[后续报告](PLUCK_NOISE_20261101.md)。B1的频繁MIDI已由用户反馈确认为静止误触，不能作为真实弹拨成功证据。

**当前交付状态：完整键盘FB仍有626条未布通网络；权限已由用户解决。按用户“峰峰值”线索新增临时B1：25 kHz/250点窗口Vpp、200 ms显示保持、可调试验阈值；已通过51个HDL测试台（含额外模式回归）/61个Python测试及原时钟约束下的路由/时序，22:52完成25K SRAM下载/校验及独立读回C12531B1，实际HS 480Mbps、采样约24994 Hz、BUSY超时/overrun均0。GUI已收到实际MIDI，但第2/4路频繁触发，物理操作未知，不能宣称五路灵敏度/误触验收。未写Flash、未操作138K。** 诊断不含完整外围，不解决FB完整键盘问题；不把GUI启动或USB枚举当作ADC/整机验收。

按用户提供的弹拨板网表，把 U5 接口、五路模拟检测、现有触摸键/MIDI 应用及本地 GUI 接成可选开发配置。未修改138K、Android、冻结基线、供应商文件或原始网表。F1–FB阶段未下载SRAM或重载；随后按用户新增授权，A2与B1分别只执行一次SRAM Program and Verify并独立读回，记录分开；全程未写Flash。

授权前JTAG `operation0`只读获得 `GW5A-25A / 0x0001281B / UserCode C12528DA / Status 0x70022020`，输出包含 `Finished.`；不是仅凭工具退出码判断。该读回不等于Flash内容校验或完整功能验收。USB为`fb9a:fb9b / GW25K MIDI Screen / GW25K-MIDI-0001`，sysfs速度480 Mbps；MIDI节点由该USB设备的sysfs子树解析，不硬编码声卡号。

本机ALSA MIDI可只读打开，但USB厂商接口节点无当前用户写权限，libusb无法打开。GUI保留实际MIDI监视并明确显示ADC诊断不可用；未自行安装udev规则、修改权限或索取sudo密码。GUI构造/刷新测试通过，实际MIDI只读打开测试没有录到演奏消息，不能据此认定触摸或弹拨已实测成功。

## 硬件与映射

原始网表、SHA256、U5每针到FPGA球号及ADC通道交叉表见[接口说明](../docs/PLUCK_INTERFACE.md)。U4网表没有器件型号字段；用户随后于2026-10-31明确确认为**AD7606BSTZ**，与已采用的八通道串行接口一致。这是用户型号确认，不是硬件通信验收；排线、电源和发射器电流/常亮能力仍需核对。

CHN1–5分别读取V5/V4/V3/V2/V1，暂映射到触摸逻辑键A–E，即48..52加现有移调；最终音阶和物理顺序未由用户确认。CHN6滑杆仅显示原始值，不抢占触摸条Pitch Bend。Note On100/Off0、通道、移调、USB/BLE分发和会话行为均复用现有应用；同音触摸/弹拨取OR，不产生重复On或提前Off。

新增MK只读`GET_PLUCK=0x03`，采用现有CRC/sequence和厂商端点。word0等待检测处理空闲后锁存一份512位快照，word1..15读取同一快照；不写公共参数、不停止ADC或MIDI。GUI使用系统libusb与ALSA，无PyUSB依赖，不向设备回发演奏消息。

## 资源迭代（均未上板）

| 身份 | 结果 | 处理 |
|---|---|---|
| C12510F1 | 综合23820/23040逻辑，失败 | 不删原有功能，改为五路共享算术 |
| C12510F2 | 综合23315/23040逻辑，失败 | 取消重复诊断锁存、收窄ADC计数器 |
| C12510F3 | 综合23153/23040逻辑，失败 | 把可容许延迟的状态改为同步RAM |
| C12510F4 | 综合22774/23040逻辑；P&R拒绝SP的WRITE_MODE=10 | 读下一通道、写当前通道，明确推断SDPB，避免碰撞依赖 |
| C12510F5 | 综合通过；P&R物理BSRAM58/56，失败 | 不能拿综合等效BSRAM充当物理块；只把基线与持音打包为32位RAM字 |
| C12510F6 | 逻辑22856/23040、物理BSRAM56/56；P&R拒绝B2专用I2C脚 | 仅开发配置启用官方GPIO复用选项，保留JTAG及默认构建 |
| C12510F7 | 综合通过；P&R逻辑22997/23040、CLS11516/11520、物理BSRAM56/56，760条网络未布通 | 资源拥塞，失败；没有可下载位流，不自动部署，不继承DA实体验收 |
| C12510F8 | 完整路由；逻辑22896/23040、CLS11512/11520、物理BSRAM56/56；60个setup端点违例，最差-1.082 ns | 路由完成不等于时序通过；生成文件仅诊断，未发布 |
| C12510F9 | 显式place=2/route=2/replicate=0；逻辑22898/23040、CLS11513/11520、物理BSRAM56/56，556条未布通网络 | 布局策略实验失败，未修改默认策略或时钟约束 |
| C12510FA | 队列等价组合改写；逻辑22969/23040、CLS11514/11520、物理BSRAM56/56，599条未布通网络 | 资源未改善，已撤回该源码实验，保留失败证据和等价测试 |
| C12510FB | 恢复原演奏队列，精简新增逐路诊断缓存；逻辑22581/23040、CLS11464/11520、物理BSRAM56/56，626条未布通网络 | 综合相对F8减少316逻辑、318寄存器，仍无法完成布线，未生成位流 |

失败输入及完整日志保留在各自忽略的`results/build_20261031_*`和ASCII暂存目录，未覆写成功历史产物。构建统一使用既有`build.sh --pluck --user-code ...`；没有新增编号构建器。F7的GPIO复用选择与本板已有`projects/25k/prj/usb1_bringup/build.tcl`使用的原生选项一致。

## 离线验证

- 完整回归：48个Verilog测试台、58项Python测试通过，包括USB HS/FS、BLE错误ROM拒绝、冻结参考完整性、旧控件/背压/应用及新增弹拨测试。F7对应RTL回归为`results/checks_20261031_190906_833332`；F7仅增加构建器的原生I2C脚复用选项，RTL与该回归一致。
- 用户确认型号后，F8/F9同版RTL通过`results/checks_20261031_195309_330388`完整回归。首次运行`results/checks_20261031_194300_870857`期间补测例导致输入哈希变化，按门禁记为失败；没有将该次运行视为稳定输入验收。
- FA源码最终完整回归为`results/checks_20261031_200437_259404`，48个Verilog测试台与58项Python测试通过，输入哈希全程稳定。
- FB精简统计配置通过`results/checks_20261031_201843_193445`：48个Verilog测试台、58项Python测试，输入哈希全程稳定。检测测试逐周期比较详细/精简模式的校准、frame_valid、sample_ready、门控、触发总数和overrun；MIDI集成测试检查能力位和保留字为零，并贯通五路真实RTL串行输入与共用演奏/USB模块。
- 138K接受输入边界保护回归：`python3 projects/138k/push2_workstation/usb_a/sim/test_current_workstation_sources.py`，10项通过；没有修改138K输入或接受配置。
- `tb_pluck_adc`：双DOUT的完整64时钟、八路有符号字顺序、BUSY未置位/卡高、故障恢复和中帧复位。
- `tb_pluck_detector`：校准、双极性/负满量程、同时触发、定长Off、安静重武装、ADC丢失与处理overrun失败关闭。
- `tb_pluck_diagnostics`：CRC、范围、字节背压、检测处理期间等待、跨请求原子快照、会话复位与只读不产生config_write。
- `tb_pluck_midi`：模拟ADC驱动实际串行控制RTL，贯通五路物理顺序、共用触摸映射、USB On/Off、同音叠加与USB背压；不是实物弹拨测试。
- 默认/USB2观察/USB-only probe/弹拨开发顶层均展开通过；两份CST合计49个唯一球号，覆盖12路弹拨接口信号，无重复分配。
- Tk窗口实际创建/刷新通过：六路ADC表、键盘、MIDI日志和无效数据状态；没有用模拟数据冒充实测波形。

综合、P&R和物理资源必须分别查看。源码/RTL仿真成功不等于路由时序通过，更不等于器件型号、电气、USB数据或弹拨硬件验收。

## 候选身份与回退

仓库基点 `632888acd2c8c7f5b2a7051689e0127e508e8ba3`，工作区包含本轮未提交差异。F7失败配置为`midi_keyboard_top / HOST_PANEL_CONTROLS=1 / pluck_adc=true / use_i2c_as_gpio=1 / GW5A-LV25MG121NC1/I0 / C12510F7`，USB-only probe和USB2观察配置均关闭。

- 输入清单SHA256：`fea94db4cc834e9e2906adae675716bc194ba5c67e395bbc72c9d5ee636108af`。
- 结果清单与源快照：`results/build_20261031_191431_194066/`；构建器记录`passed=false`、`hardware_validated=false`、`sram_programmed=false`、`flash_programmed=false`及空产物列表。源码中的空profile header未改写，定义与约束只加入暂存副本。
- 暂存header SHA256：`6fee28b240490066bb001206d7ac8faf079ca5cfef41f994ee0dcba7f11c5058`；合并CST：`8a055cb6fbcfbdfc1c346ece1d3df0076fe0c7ebe4649a4b6ccbea3681891fe0`；合并SDC：`0b8a4032b70dd01963d68003576c74a9aa1ffd090d470d060a9271f9ce046443`。
- P&R日志：`results/build_20261031_191431_194066/build_20261031_191431_194066_pnr.log`，SHA256 `3cd18f71f40993deff42c607a10da4150f2277dfffa5e4cec9a39a921eebe586`。工具报`PR0004: There are total 760 unrouted nets`，不是单纯时序门限失败。
- 物理报告：`/tmp/gw25k-build-s1ogw025/prj/impl/pnr/midi_keyboard.rpt.txt`，SHA256 `7c3bbec935005fbbd38820b9f9695f0c9a682f367f84153e4da47fca06285d2a`。物理BSRAM为39 SDPB加17 pROM，不使用综合等效数量代替。
- 没有生成`.fs`或完整路由时序报告，因此**无位流SHA256、无有效routed setup/hold/Fmax结论、无CDC/PLL硬件验收**。只为三个ADC输入到首级同步器设置专用CDC例外，其余原时钟约束保留；不能由约束文件存在推断时序已过。

后续需先在不删除原有完整键盘功能、不放宽时钟的前提下进一步减少逻辑/布线压力，并以新身份重跑完整回归和P&R。不能将F7当成成功产物，也不能仅通过更换UserCode或GUI安装规则绕过该门禁。

### 型号确认后的优化与证据

F8去掉仅在有效数据到达后才使用的数据寄存器复位/清零路径：ADC移位器必须完整移入64次才发布，检测输入在接受快照时一次覆盖，诊断缓存用独立valid位在会话复位时失效。无效缓存读返回零；增加首读前、等待中复位、全部word和输入提前改变的回归，没有暴露旧会话/未初始化数据。

F8输入清单SHA256为`a9b760534af0ed4167b16d815bd9efca5a6d5fb60288c71e5757898921cb0ea5`，证据目录`results/build_20261031_194350_549775/`，暂存`/tmp/gw25k-build-bp5roxlw`。完整路由时序为：setup -1.082 ns、hold +0.216 ns、recovery -0.923 ns、removal +0.258 ns；50 MHz域Fmax47.434 MHz、ULPI域Fmax65.678 MHz。诊断`.fs` SHA256 `515b30c75ed0720ac2888a36f2400f3aa5a86b7c00d634e8fd8cd7c023ffacd4`，**不是可部署产物**，构建器因时序失败保留空发布列表。时序报告SHA256 `dad3d519991cffb9a0a63110ef29edfab4a37f028ba59a0835edeb2bc911b5ab`。

F9使用相同RTL，输入清单SHA256 `4c9eaa1046c86265a4f5cfd692e6d8996d1cec6fdee98874c063bde4d6b5932f`；证据目录`results/build_20261031_195248_488258/`，暂存`/tmp/gw25k-build-38nnwzsv`。策略只通过既有入口显式传参，没有写入默认配置。未生成位流或完整路由时序报告。

FA在拥有者`gw138k_panel_performance.v`内等价改写原六端口队列的组合入队计算。先按请求排序，入队条件为`rank < free_slots || (pop_control && rank == free_slots)`；写指针与占用量在末尾统一计算，避免把移调/出队判断串入六级宽计数更新。六个写端口、64项容量、周期延迟、满队列丢弃/待发bend、顺序、溢出计数、会话/重调与参数权威均保留；不是另建队列，也不是减少功能。该源改写影响引用此模块的构建，不声称旧DA位流与新源码等同。

以基点提交中的原模块为对照，只在临时验证副本重命名模块：深度8/16/64各20000周期，seed=`760625a1`，逐周期比较所有事件/公共状态、队列读写指针/占用/溢出、每端口地址/负载/目标，全部一致。分别达到1905/2169/3748次接受、14955/14793/13863个满队列周期、224/117/42次回绕。另穷举深度8/16/64/128、所有合法占用/出队/写指针及0..6个请求，共292712种分配情况，旧/新计算完全一致。验证副本、测试源和日志保留于`results/build_20261031_200422_956611/queue_equivalence/`，不作为生产构建输入。

FA虽然功能等价，仍有599条未布通网络，未生成位流；输入清单SHA256为`d518ffb4e8efced504cdc4aba8c04ff42097a2f00a703d8efcf53aa4554c6dab`。该实验已撤回：当前`gw138k_panel_performance.v`与仓库基点逐字一致，SHA256 `5d74b6ac6594d81483758792064710d499568c774433936bf17355a512ff3f16`，不把未改善的队列改写留在交付中。

FB保留原演奏队列，只精简本轮新增的详细ADC调试缓存：`DIAGNOSTIC_DETAILS=0`不存逐路幅值/计数，仍保留六路16位ADC原值、五路检测门控、32位触发总数、阈值、采样/故障信息和真实MIDI。word1 bit5表示详细统计能力，关闭时相关word全零保留，GUI明确显示“—”而非假零值；不降低采样率、ADC位宽或检测精度，不删原有外设。Tk两种能力模式刷新通过，使用隐藏窗口与构造输入，只证明界面行为，未冒充ADC实测。

FB配置为`midi_keyboard_top / HOST_PANEL_CONTROLS=1 / complete_keyboard=true / pluck_adc=true / diagnostic_details=false / use_i2c_as_gpio=1`，使用原默认布局布线策略。输入清单SHA256 `b87240f881ac54179b4abdb672ebd0b5c61b74f494b4c0eb248f38892374f3a2`；结果目录`results/build_20261031_201832_749826/`，暂存`/tmp/gw25k-build-s1aa0tbt`。暂存header/CST/SDC哈希与F7相同；源码快照记录精简统计与用户型号确认。该清单和最终回归的输入哈希均与当前源码一致。

FB物理报告SHA256 `9440102164dd4dbc2f055f07e041bea019a97596f9038045600be0488c798f51`；P&R日志SHA256 `a75106578c073af487ed04054ccec06efe7983c0560c240d69683fc498065cf8`。工具在2026-10-31 20:30:28报告`PR0004: There are total 626 unrouted nets`。逻辑98%而CLS约99.5%、物理BSRAM100%，不能用综合总量尚未超限掩盖拥塞。未生成`.fs`或完整routed timing报告，无位流哈希、无routed setup/hold合格结论；`passed/hardware_validated/sram_programmed/flash_programmed`均为false。

最终只读JTAG复查仍为`C12528DA / Status 0x70022020`，含精确器件ID与`Finished.`；日志SHA256 `05c5c76981cf5ebb5645e47af2a96b8bf62e13442dbced892c4cd93f463929ee`。HS仍枚举为480 Mbps。FB物理报告和该只读日志另存于其结果目录的`diagnostic_evidence/`；没有读取或声称校验Flash内容。

若下一步改用临时弹拨/USB诊断配置分阶段验证ADC与阈值，须先由用户确认诊断范围并明确授权SRAM操作，且不得把裁剪诊断配置冒充完整键盘的时序或功能验收。该路径不改变本页完整候选失败结论，也不得自动替代默认构建；完成硬件输入验证后仍需回到完整配置解决资源/时序，或明确撤销实验。当前尚未实施该诊断配置。

已核对历史完整DA回退文件：`~/.cache/fpga-usb2-hdmi/25k-midi-debug-c12528da-20261028_175332/acceptance_20261028_182213/ao_0.fs`，SHA256 `61af877c9a7883e28e36fd28bb3fb038d978ee4f7d9b5b01629300388da4778b`。本轮未演练回退。任何未来SRAM下载须重新核对连接、原身份和此文件哈希，并取得用户授权；不需要因此写Flash，不能由旧部署记录推断此刻Flash内容。

剩余门禁：USB权限由用户安装限定设备规则；确认排线/发射电流；候选物理资源与路由时序通过；另行授权25K SRAM及精确身份读回；五路独立弹拨、快速重复/误触/Off/触摸叠加、滑杆原始值和断开故障；最后再接138K验证真实FS MIDI。U4型号已由用户确认，但不替代上述实板检查。Flash与冷启动另行验收，不在本轮范围。

## 21:16起：用户同意的临时弹拨＋USB诊断

以上F1–FB为完整键盘的历史失败证据；其“当前/最终/未下载”描述截至用户本次同意之前。用户随后明确回复“同意”，确认临时诊断范围，并条件授权电气/离线检查通过后只下载25K SRAM、不写Flash。该授权不包含138K、Flash或生产默认配置替换。

采用现有`build.sh`/`gowin_build.py`的独立`--pluck-probe`选项，顶层`midi_pluck_probe_top`原生组合现有USB2、MK端点、ADC/检测器、原演奏映射模块和USB MIDI编码器，不复制USB栈或演奏策略。该配置**明确不含触摸板、编码器、LCD、PCA灯、BLE及138K PL屏幕业务**；`complete_keyboard=false`，完整键盘资源/路由问题没有因此解决。

发射灯原网表未标型号。核对五支路3.3V、120Ω、S8050低侧结构后，选择安全初始态：五个驱动低、WS2812线低，工具不自动点灯，ADC继续采样。未测量实物电压/电流，未确认LED连续额定值，不把网表检查当电气实测。临时配置另有仅诊断启用的MK `0x04`灯使能：默认禁能，USB会话/掉线/ADC离线立即关灯，2秒硬件租约；GUI只在操作者通过电气确认对话后每0.5秒续租，重连不自动开启。完整配置拒绝此命令，读取`0x03`仍无写副作用。关灯时检测器不校准、不发Note；开启后重新校准64帧。

`C12531A1`于21:16:43完成路由/时序，位流SHA256 `0a8e577d7ec16efa139bf390f6eb0f79c84b153b62946656dfdd7e6fca6bb738`，输入清单SHA256 `c1dbdaa5a306d58a4e4b77ba0b4a52b7a0ae502169e1f6857b26e749695d76f6`，结果`results/build_20261031_211614_630531/`。对应`results/checks_20261031_211623_625140/validation.json`通过49个HDL测试台、59个Python测试，输入未漂移，清单SHA256 `c9ae93c71b70a47c9180851d649f64ea9e27388efb9684f1e59e865bdef658de`。A1未下载；随后纠正诊断顶层GET_STATUS，使USB/BLE/错误/active/panic位沿用原有位置，并将ADC离线纳入灯硬件禁能、GUI停止续租。以新身份A2重新构建，不复用A1身份冒充变更输入。

`C12531A2`构建结果：

- 结果：`results/build_20261031_212244_352827/build.json`，暂存`/tmp/gw25k-build-3i4qev92/`，git基点`632888acd2c8c7f5b2a7051689e0127e508e8ba3`。
- 输入清单SHA256：`34839bdcdb68d7948592cd75716f8b86665075a315a6b010d9975f7b1decd605`；逐文件哈希、源快照、暂存header/CST/SDC转换与GPIO选项均在构建清单中。
- 位流：`results/build_20261031_212244_352827/impl/pnr/midi_keyboard.fs`，SHA256 `4b12008fe17ebbb3df09e83df511f4fe758d3cc36979146f05bf54f490fbd06e`；文件头UserCode为`C12531A2`。
- 原50MHz/60.002MHz时钟，setup/hold违例端点均0；最差setup `+0.559ns`、hold `+0.222ns`、recovery `+6.025ns`、removal `+0.253ns`；实际Fmax `72.275/62.086MHz`。无降频、无放宽CDC或时序例外。
- 物理资源：Logic `4023/23040`、Register `2743/23280`、CLS `3210/11520`、BSRAM `10/56`，27个I/O。未实例化BLE固件ROM为该临时配置的预期，非删除完整构建的ROM校验。
- 原演奏模块仍逐字等于基点，SHA256 `5d74b6ac6594d81483758792064710d499568c774433936bf17355a512ff3f16`；未重试FA改写或缩减原队列。

新增安全测试覆盖默认关闭、续租/到期、USB/复位立即禁能、重连不自动开启、非法参数/CRC无写副作用、完整配置拒绝诊断控制。串行ADC→五路映射→MIDI测试另跑安全诊断变体，验证未开启前有ADC采样但无校准/Note、开启后正常映射、关闭后禁能。隐藏Tk窗口测试明确使用构造输入：验证无能力/数据过期禁用按钮、对话否不入队、确认后才入队、默认不发任何硬件写；不当作实板数据。

退出/回退条件：完成五路原值/触发和阈值实板确认后，回到完整键盘解决资源和routed timing，并单独做触摸叠加及138K业务验收；否则撤销该实验。历史完整DA回退文件及哈希见上一节，实际回退若发生须另记下载/校验/读回，不能通过此诊断构建推断Flash内容。后续最终验证、SRAM读回及GUI权限状态单独记在下节。

## 21:30–21:34：A2 SRAM部署，ADC实测受权限阻塞

- 最终离线清单：`results/checks_20261031_212303_493826/validation.json`，`passed=true`，49个HDL测试台、59个Python测试，含USB HS/FS、BLE错误ROM拒绝、参考文件完整性与全部顶层展开；`inputs_changed_during_run=[]`。清单SHA256 `56f7c6da32b41ea142081524e0b310d2fdc0382d65ee6c9744a3fb6fa73e26b1`。138K当前工作站来源回归另跑10项通过。
- 下载前逐一核对当前源码/回归/构建输入哈希一致、暂存header/CST/SDC哈希、27个球号无冲突、AD7606引脚表、候选位流头/哈希、DA回退位流哈希、JTAG序列号`210357A7D00E`和原`C12528DA`。实物电源/排线/LED电流仍未测量；因此只允许默认关灯采样，未发送开启命令。预检在`results/build_20261031_212244_352827/hardware/preflight.json`。
- 仅对WINUSB location850、器件`GW5A-25A / 0x0001281B`执行一次operation4（SRAM Program and Verify），完整读回进度100%、报告`C12531A2 / 0x70022020 / Finished.`。请求2.5MHz，原生工具在operation4中自行报告切换到15MHz；后续独立operation0使用2.5MHz。没有operation1重载或任何Flash操作。
- 首个辅助脚本在工具已完成后，因误要求输出包含`success`单词而报断言；原生CLI实际没有该单词。没有重复下载。保留原日志，核对操作类型、完整SRAM读取、候选UserCode/Status/Finished、无具体错误，再**独立**operation0读回`0x0001281B / C12531A2 / 0x70022020`。CLI连help与正常只读也打印通用`ERROR FOUND`前缀，不把该前缀或退出码单独作结论；解析修正原因在`hardware/deployment.json`。
- USB重新枚举到`003:083`，sysfs仍为`3-5.3`、`480`Mbps；ALSA实际MIDI节点可以只读打开。`/dev/bus/usb/003/083`为root:root0664，无当前用户写权限，实际`--probe`退出2，返回`pluck_verified=false`。没有ADC快照、采样计数、滑杆响应或真实弹拨MIDI可验收，不能用模拟数据填充。
- 已启动实际Tk GUI，进程PID3497598，默认只读/关灯，界面显示480Mbps、MIDI可读、ADC权限不可用，六路“—”、开灯按钮禁用、实际MIDI消息0。`hardware/gui_actual_permission_blocked.png`最终由直接读取本程序X窗口获得并检查；不是桌面遮挡截图或构造ADC输入。GUI日志无未处理异常，权限放行后会自行重试连接。

构建清单的`hardware_validated/sram_programmed/flash_programmed=false`仅描述**构建阶段**，没有事后篡改。部署状态单独存`hardware/deployment.json`：`sram_programmed=true`、原生operation4校验及独立身份读回为true、`hardware_validated=false`、`flash_programmed=false`、`emitters_enabled_by_agent=false`。本轮未演练DA回退，当前SRAM保留A2临时诊断，不是完整键盘；当前Flash内容未读取，不根据旧DA身份推断。

下一步必须由用户在本机终端安装`tools/60-gw25k-midi.rules`并reload/trigger（完整命令见接口说明）。无需以root运行GUI、拔线或重刷。先验证ADC样本持续增长、BUSY超时/overrun和CHN6滑杆响应；确认发射灯连续电流、供电/排线后，才可由操作者通过GUI确认开启，测试五路原值/门控和48..52真实On/Off。若实物不符，停止开启、保存失败数据并回退/修正；不得把权限放行或HS枚举替代物理弹拨验收。完整键盘/触摸叠加、138K链路与Flash冷启动仍独立未验收。

## A2权限解除与用户观察更正

此前权限阻塞段保留为21:30–21:34的历史记录，不再代表当前状态。用户安装了限定VID/PID的udev规则，22:45复核USB `3-5.3`、`003/083`当前用户可读写，JTAG `003/078`亦可访问。直接读取实际GUI窗口保存于B1的`hardware/before_vpp_actual_gui.png`：采样计数18,056,900、4000 Hz、BUSY超时0、检测overrun0、CHN6=8983；操作者此前已手动启灯，五路基线差值约2–3，阈值1024/512，触发/MIDI计数仍0。这证明旧采样在运行，不能证明模拟峰值被GUI捕获或检测阈值合适。

用户最终更正为“示波器检测发现五路ADC信号都很灵敏”，**不存在已成功的Xilinx板或参考工程**。峰峰值是用户给出的检测线索，不是仓库中另一个已验收FPGA实现。此前对带通网表推断“必须加PWM载波”不成立，已收回；不改发射极性、DC方式或猜测载波频率。`results/pluck_ir_analysis_20261031_221102/filter_model.json`保留为早期理想元件分析，未验证实装值，其结论不得当成必需载波或硬件故障的证据。

## B1窗口峰峰值候选

- 身份`C12531B1`，独立临时`--pluck-probe`。构建目录`results/build_20261031_224457_202688/`，隔离输入`/tmp/gw25k-build-ls78grq4/prj`，Git基点`632888acd2c8c7f5b2a7051689e0127e508e8ba3`，输入清单SHA256 `a8141bb1bb455a4c4c78bbbc86fbc8c328c03175491a6fa1084f179bb5fd9f98`。位流`impl/pnr/midi_keyboard.fs` SHA256 `21365e6cbf82ccb6a0bc38a243ae6ff202556cd47cc5d8f4f2220c829d60a0c0`，不是复用A2的接受身份。
- 原50/60.002 MHz约束和CDC门禁不变；setup/hold/recovery/removal最差裕量分别`+0.295/+0.220/+6.751/+0.256 ns`，违例端点0，Fmax `71.630/61.083 MHz`。物理资源：Logic4650/23040、Register2846/23280、CLS3544/11520、**物理BSRAM8/56**、IO27/86；不是用综合等效6块冒充物理8块。
- 采样4 kHz改25 kHz，SCLK仍2.5 MHz、CONVST高仍2 µs；12帧50 MHz/4 µs BUSY模型测试确认40 µs调度、64串行时钟、无跳帧。250点不重叠窗口计算有符号max-min；16窗口校准、50 ms门控、10 ms安静重武装。显示Vpp保持200 ms，检测不使用显示保持。64/32仅为可调试验初值，USB会话复位恢复初值，未宣称适配五路硬件噪声。
- 新MK `0x05`仅临时Vpp配置接受，OFF:ON打包、OFF<ON、保留参数0、CRC有效才产生配置写入；完整配置拒绝。应用释放当前门控并重新校准，不清触发历史，不改变公共参数权威/现有MIDI映射。ABI沿用PLK1，新增bit13能力及word15高16位窗口长度；旧配置相关字段0。
- 针对性通过：窗口首尾/跨窗DC不误计、负值/全量程65535、五路同时触发累计、逐路饱和/总数回绕、显示保持不阻止静默重武装、关灯仍测Vpp但不发Note、重校准/ADC故障/reset；真实串行模型到原共享performance再到USB MIDI的五路48–52 On/Off、叠加去重及背压。Python新增Vpp/阈值往返及有界原子遥测测试通过；138K当前源边界10项测试通过（`138k_current_sources.log`）。完整回归另记，不用针对性测试代替。
- GUI自适应绘图改用Vpp保持值（旧配置仍原值），明确单位/窗口/显示非全速录制，支持手动调整阈值与单份最新JSON遥测，不另抢USB、不伪造MIDI。25 kHz对超过12.5 kHz或窄于40 µs的模拟信号存在采样限制，实测Vpp不保证等于示波器Vpp。
- 发射器驱动保持不变，加载后默认关灯；不继承A2操作者的开启状态。回退优先使用本轮已校验A2 `results/build_20261031_212244_352827/impl/pnr/midi_keyboard.fs`、SHA256 `4b12008fe17ebbb3df09e83df511f4fe758d3cc36979146f05bf54f490fbd06e`；另保留DA完整键盘回退（见A2段），两者回退动作均未在B1实验中执行。

### B1离线回归与SRAM部署（22:52）

完整回归`results/checks_20261031_224411_971819/validation.json`通过：51个HDL测试台、额外HS/FS与旧差值/安全诊断/Vpp诊断模式、61个Python测试；`failed_checks=[]`、`inputs_changed_during_run=[]`，验证清单SHA256 `b5f20289eef2d2b7e9844c590bce7092683c978cdf3d60bf306dbe97c461c2e7`。源码身份/输入再次核对无变化，原`gw138k_panel_performance.v`保持SHA256 `5d74b6ac6594d81483758792064710d499568c774433936bf17355a512ff3f16`。未通过缩减既有队列或修改原performance换取通过。

关闭旧GUI并停止灯租约，等待超过2秒；即时operation0确认A2/器件`0x0001281B`。22:52:00–22:52:04只运行一次原生operation4 `SRAM Program and Verify`，完成写入/读回，随后独立operation0读到`C12531B1`、Status `0x70022020`。命令请求2.5 MHz，原生写入过程自行报告15 MHz；独立读回仍2.5 MHz。通用`ERROR FOUND`启动横幅在help/成功读码也出现，不单独作为失败或成功依据；保存完整进度、操作类型、完成标记、UserCode及独立状态。`hardware/deployment.json`与各日志记录此部署；构建清单的阶段标志不追改。未执行Flash、138K操作、重载或回退。

### B1实际USB与GUI观察（未等于五路验收）

加载后、GUI启动前，由单一只读客户端取得四份原子快照（`hardware/usb_vpp_probe.json`）：HS480Mbps、实际计数估算24993.986 Hz、25 kHz/250点能力回读正确、阈值64/32、BUSY超时/overrun0；确认发射灯OFF、校准未完成、门控/触发0。代理未发过灯使能或阈值写命令。

新GUI PID3507959已启动并持续写`hardware/latest_telemetry.json`；实际程序X窗口截图`hardware/gui_actual_vpp.png`、`hardware/gui_actual_vpp_active.png`经检查可见Vpp曲线/阈值/实际MIDI。初始遥测为关灯、未触发；之后操作者会话中灯已ON，出现实际On/Off，代理不替操作者点击确认或自动恢复发射。

`hardware/passive_vpp_observation.json`从GUI最新JSON被动观察5.995秒（116份，无第二个USB客户端）：五路累计触发从`31,227,5,697,2`变为`31,245,5,750,2`，实际MIDI增加144条；显示保持Vpp最小`12,36,27,31,27`，最大`25,79,41,138,59`，阈值仍64/32、超时/overrun0。五路历史计数非零不等于逐路实物验收；当时是否在拨动/遮挡未被观察，尤其第2/4路频繁触发，不能分辨真实演奏与静止误触，不能直接把64/32定为最终值。需要操作者提供不弹拨时和逐路弹拨时的对照，再决定阈值/窗口调整。

`hardware/validation_summary.json`明确离线通过、SRAM已部署、实际MIDI已观察，但`hardware_validated=false`、五路灵敏度/误触验收false。`hardware/evidence_sha256.json`固定证据哈希，排除仍在更新的`latest_telemetry.json`与`gui.log`。GUI保留操作者当前会话，未自动关闭其已确认的灯；掉线/退出租约仍失败关闭。完整键盘、触摸叠加实物、138K及Flash冷启动仍未验收。

## B2逐路静态噪声校准

### 用户反馈与实现边界

用户进一步确认：双手全部放在板上时没有触发，静止时第2/4路持续抖动，怀疑逻辑方向与灵敏度。由此B1频繁On/Off应按静态误触处理，不能作为真实弹拨通过证据。双手是否完全遮光、覆盖/移开瞬间的原始波形与峰值尚未分别标记；Vpp对原值取反不变，保持遮挡后不补发也不等于极性反转。因此B2不改变发射极性/DC方式，不擅自改成Vpp下降或持续遮挡触发。

B2只改临时`--pluck-probe`：开灯/手动校准后，要求操作者移开双手、保持无遮挡静止约1秒；以各路100个10 ms窗口的Vpp最大值建立独立静态参考，冻结到下一次校准。有效ON/OFF为该路参考加64/32试验余量。演奏不自动抬参考，避免强动作被吸收；校准中不发Note，掉线/ADC故障/关灯清参考并释放门控。加法用17位检查，噪声+ON超65535则禁止该路触发，不回绕为低敏阈值。50 ms门控不变，重武装改为结束后连续3个安静窗口（30 ms）；短回落打断重武装，保留单窗口短脉冲识别。历史逐路/总计数仍按原规则饱和/回绕、故障与手动校准不清历史。

PLK1 bit14表示此能力，word10现为ON/OFF噪声余量；旧B1 bit14=0仍按绝对阈值解码。新增只读MK `0x06`，`PNO1`独立原子512位快照提供五路噪声上限、有效ON/OFF、当前未保持Vpp、有效掩码和校准进度。与0x03的锁存各自独立，交叉查询不破坏另一份；未读word0、重置/取消捕获、CRC/保留参数/越界均有测试。其他配置拒绝0x06，不产生config_write，不改公共参数或18位事件/MIDI映射。GUI增加噪声/有效阈值列、无遮挡校准确认和当前窗口Vpp提示，按能力兼容B1及旧配置，不自动写余量或开启灯。

### 候选来源与离线验证

- 新身份`C12531B2`；构建`results/build_20261031_232804_784162/`，隔离输入`/tmp/gw25k-build-8egq_ge7/prj`，Git基点`632888acd2c8c7f5b2a7051689e0127e508e8ba3`。输入清单SHA256 `a28bb51b1ce992fe345a003b0d3df9df653ae50b90ab87bdf2cd46d311979aea`，位流SHA256 `26a78913817f16cc31866c867f79de89e856841d61699218772471c8f758d7b6`。
- 原50/60.002 MHz时钟/CDC约束未改；setup/hold/recovery/removal最差裕量`+0.608/+0.247/+6.250/+0.343 ns`，违例端点0，Fmax `66.449/62.273 MHz`。物理Logic5249/23040、Register3387/23280、CLS4236/11520、BSRAM8/56、IO27/86。未缩减旧外围/队列或修改冻结/vendor内容换取通过；临时诊断原有缺失外围仍缺失。
- 新针对性测试通过：独立五路校准峰值含最后窗口，重复第2/4路越过旧绝对64的静态扰动不触发；真正超过本路噪声+余量的单窗口脉冲可触发，持续高幅不补发，少于3窗口静默不重武装；余量修改重校准、关灯保留测量、溢出禁用、ADC故障恢复；另验证噪声快照CRC/原子性/独立锁存/重置，以及校准前后保持原五路48–52 USB MIDI On/Off、同音去重与背压。
- 138K当前源边界10项通过（`138k_current_sources.log`）。完整回归另记；本节不以针对性仿真替代完整回归或实板验收。回退优先为已核验B1位流SHA256 `21365e6cbf82ccb6a0bc38a243ae6ff202556cd47cc5d8f4f2220c829d60a0c0`，保留先前A2/DA证据，不修改历史接受身份。

以上候选段截至2026-10-31；完整回归、2026-11-01 SRAM更新/独立读回和新GUI实际状态已另记于[后续报告](PLUCK_NOISE_20261101.md)。尤其“是否应该在遮挡瞬间触发”仍需物理对照；噪声校准不等于已修复或证明极性问题。
