# 功能优先续验（2026-10-19）

本轮实际修复guide编译兼容问题，纠正D测试调用，核对并修正25K基础页字段含义与刷新验证。已fetch确认本地HEAD与`origin/main`均为`9660406207993914abf2e007906815fcb0df42be`，无远程增量需合并；适用目录未发现额外AGENTS规则。原有功能／时序修改和他人的根目录《工程架构报告.md》保留。未提交或推送。

本轮总结果：[verification.json](function_first_20261019/verification.json) 为`passed=true`。这是当前输入的离线功能通过；未执行SYN、P&R、新时序实验、烧录或板测，不代表时序闭合。2026-10-18的[失败报告](function_first_20261018/verification.json)及日志原样保留，不改写历史结果。

## 实际代码修改

| 文件／责任端 | 本轮修改及依据 |
|---|---|
| `rtl/display_data/push2_surface_pixels.sv`，138K Push绘图 | Icarus的旧guide日志明确报告第71行无法绑定`song_pixel`，第74行才声明。把声明放到引用前；未改绘图、PIPELINED选择或接口 |
| `gw25k_panel.h`，138K生产Host基础页 | 现有MMIO的高16位是`synth_gain`，音色是profile，弯音是8bit表索引。VOL改标GAIN、PATCH数字改为音色名称、BEND改标BEND IDX，效果三位标明DCR；A/B/C仍取实际提交mode，保留值显示问号。沿用现有帧快照、tile和传输服务，未增加MMIO或PL字段 |
| `sim/test_gw25k_panel.c` | 补入有效增益／表达、五音色、实际模式、256个弯音索引、8种有效效果、16键held和最近输入释放测试；核对帧中冻结／tile重建／下一帧更新，经真实服务循环逐项改变九类状态，验证完整刷新及静态仅心跳 |
| 独立D验证调用 | 使用`python3 sim/sampler/run.py --test ...`，不再传入不支持的`--out`。本轮没有继续接入D整机或改变其效果语义 |

本轮改动前先核对了生产者：暂存`Prj1/src/ae350/gw138k_controlled_adapter.sv`的`control_state_o={synth_gain,voice_count,profile,route,mode,effect_mask}`；活动`rtl/audio/gw138k_event_workstation.sv`的`synth_gain_o=volume_product[30:15]`、`control_options_o`和弯音`{b,a[6]}`；`rtl/push2_usb_a_control.sv`的0x10／14／1c／20／24。证据中的完整暂存清单与本轮输入哈希均已绑定。

## 基础页字段与刷新边界

| 字段 | 实际来源／数值 |
|---|---|
| NOTE／VEL | 0x24的低7bit音符、随后7bit力度／压力；最近USB受理输入，匹配的Note Off／velocity0使力度归0，不是全部声部或初始化消费ACK |
| GAIN | 0x10[31:16]为CC7与CC11相乘后的Q15有效增益。显示`min(127, gain >> 8)`，32768正确显示127；表达改变后不再等于原始CC7 |
| TONE | 0x10[9:7]，profile0／1／2／3／4为FLUTE／STRINGS／BRASS／MARIMBA／PIANO；对应已定Program73／40／56／12／0，不回显原始Program编号 |
| MODE | 0x10[4:3]，显示音源已提交A／B／C；模式请求等待释放与空闲时，仍显示旧的实际模式 |
| MOD | 0x14[10:4]，CC1颤音深度0–127 |
| BEND IDX | 0x14[25:18]，0–255；即14bit Bend右移6位。中央8192显示128，低6bit不在现有快照中 |
| FX DCR | 0x10[2:0]按Delay／Chorus／Reverb顺序显示实际生效位。000不能区分清空选择和master关闭；初始化CC81=0仍是effect_master=1。此处D不是独立采样器D效果 |
| A–P键格 | 音频域held快照，0x1c bit0=MIDI36，0x20 bit0=MIDI68；当前16格固定48–63，不显示包络尾音，也未取得25K本地transpose |

帧开始读取并冻结一份场景，全部tile与重试保持这份数据；帧中更新在下一帧完整重画。稳定状态只保活。manual／画布丢失／PL恢复的原重画规则保留。仍无脏矩形、整屏缓存、新音源／FFT或新DDR客户端；未测实际USB／SPI刷新率。

预览来自本次生产C渲染器：[renderer.png](function_first_20261019/gw25k_host/renderer.png)，不是实板照片。

## 当前输入的验证结果

最终prepare为`results/workstation_scope83_20261019_002422_673274`；18道门禁输出为其`current_regression_20261019_002509_188265/`。guide和attach显式引用该prepare的`Prj1`；最后生产Host测试使用相同`firmware.c`／`gw25k_panel.h`。本轮再次绑定了每项测试输入，并核对full83原验收594个文件和最终暂存602个文件。CNN只采用验收的73个文件，活动9个修改／11个新增继续排除，没有使用`--cnn-timing85`或修改冻结源、清单及固定哈希。

| 验证 | 结果／证据 |
|---|---|
| CNN来源边界 | 10项通过，[source_boundary.log](function_first_20261019/source_boundary.log)；[CNN审计](function_first_20261019/prepare/cnn_source_audit.json) |
| full83 prepare与裸机固件 | 通过；固件19384 bytes，静态RAM25116 bytes，栈余量40420 bytes；两处64KiB ROM哈希一致。[固件元数据](function_first_20261019/prepare/usb_firmware_metadata.json) |
| full83整机18道门禁 | 全部通过，含8项scope合并、7项Push／曲谱、TF16项、Delay DDR等价及识别／Delay地址隔离；旧地址负例按预期失败，新地址通过。[18项结果](function_first_20261019/full83_18_gates/verification.json) |
| 接入／演奏链 | 通过：6处默认参数边界；Note／CC7／Program／Bend／CC88／89顺序；满队列背压；断开、初始化中断开与快重连作废旧项；PANIC优先／初始化中重启；TF／现场矢量／演示退出；实际C提交后放行；无首帧仍有PCM；Push两次反馈对齐、首次按下／释放／音量及PANIC后演奏。[结果](function_first_20261019/attach/verification.json)、[日志](function_first_20261019/attach.log) |
| guide／generic兼容与25K隔离 | 编译与测试通过，85条音频事件。Push／普通generic原曲谱控制、判定及背压保留；切换GW25K后正确键、错误键及CC110／111／112均不改变活动Push目标。[结果](function_first_20261019/guide/verification.json) |
| 生产25K Host，ASAN／UBSAN | 通过，26帧／6572 tiles／225737次MIDI轮询。包含页面与九类刷新新测试、真实124byte描述符、FS分片、独立DATA toggle／去重、BUSY／NAK／丢ACK、11种响应故障、manual／恢复和静态心跳；不读曲谱MMIO、不发引导MIDI。原generic和Push热插拔固件测试也通过。[结果](function_first_20261019/gw25k_host/verification.json)、[日志](function_first_20261019/gw25k_host.log) |
| D控件 | 通过；CC20／21／22生效、0释放、旧110／111／112不触发，3项momentary FX及快照无撕裂。[结果](function_first_20261019/d_controls/verification.json) |
| D独立模式 | 通过；新CC从模式入口到效果模块生效并释放，5012帧、同采样3起音、jitter0、最大渲染62 clocks。[结果](function_first_20261019/d_mode/verification.json) |

初始化继续由138K执行：先全局PANIC，CC96=0／104=0／90=0，再Bend8192、CC64=0／11=127／1=0／5=0／82=0，最后CC7=127、Program73、CC80=2、CC81=0。所有默认已消费且实际C提交、无待提交模式后放行。PANIC越过普通队列，初始化中PANIC重启默认流程。PL会话恢复只走`gw_recover`，不写USB接入状态；正常恢复不触发音源初始化，USB toggle不确定引起的真正断开重枚举仍按USB重新接入处理。

guide编译仍有Icarus关于FIFO常量位选的已有提示；Verilator编译保留已有绘图等警告，未以关闭检查或改验收快照规避。上述离线门禁也不等于当前CNN卷积完整数值验收、整板综合／布线或物理热插拔闭环。

## 缺少设备源码的边界

`projects/25k/`本次仍只有README。在`/home/sphenicidition`按`panel_display_endpoint.v`和25K工程文件名检索无匹配，未遍历外部挂载盘，详见[检索记录](function_first_20261019/device_source_check.json)。本轮生产Host只连接确定性USB／时间／MMIO mock，没有传入`--endpoint-rtl`，不把测试驱动`sim/tb_gw25k_panel_endpoint.v`当作真实设备工程。

待真实25K工程接入：已定16键／滑条／编码器消息、本地音量与音色同步、持音移调以及现有USB／SPI／触摸驱动的集成。还缺源码来源／版本／许可、板型／时钟、屏控制器／尺寸／连线和实际电极键序。没有创建占位模块或重写设备驱动。

待产品决定仍为移调入口／范围／越界行为、25K专有功能和效果选择入口、D整机模式／DDR／UI及每次切入是否清零、未来HighSpeed物理接口。未自行分配菜单或编码器长按。本轮只完成138K可落实部分，D仍为独立模块，当前时序未闭合。

根规划、首批实施记录、25K接入说明，以及本机Obsidian《接口确认记录》《25K MIDI指令表》《现有规范兼容性对照》《待确认》已同步本轮实现和边界，保留原历史记录。旧路径只用于兼容；本轮新引用使用`projects/138k`和`projects/25k`。

## 复现

在`projects/138k/push2_workstation/usb_a`下执行；已逐一检查入口的`--help`。新输出应使用新目录，以下prepare值是本次实际输入：

```sh
python3 sim/test_current_workstation_sources.py
python3 tools/build_current_workstation.py --prepare-only
PREPARE=results/workstation_scope83_20261019_002422_673274
python3 sim/scope_vec/run_current.py "$PREPARE"
python3 sim/run_workstation_attach.py --baseline "$PREPARE/Prj1" --out results/function_first_rerun/attach
python3 sim/run_pl_guide.py --baseline "$PREPARE/Prj1" --out results/function_first_rerun/guide
python3 sim/run_gw25k_panel.py --output results/function_first_rerun/gw25k_host
python3 sim/sampler/run.py --test tb_sampler_controls
python3 sim/sampler/run.py --test tb_sampler_mode_d
```

重跑时将PREPARE换成该次prepare输出，将`function_first_rerun`换为新的目录名。sampler脚本只支持`--test`，自身将对象与可执行文件放在忽略的`out/sampler_*`；其余本轮生成物都在`results/`。本报告目录只归档JSON、文本日志和预览PNG，不包含Verilator对象、可执行文件或预编译头。


## 同日后续：25K专有方向明确

用户随后明确25K借鉴EP-133的4×4演奏与组合效果逻辑，并要求在题目允许范围多借鉴。新增独立D组合回归，测试文件已有新输入；本页和本页JSON仍保留本次原输入／5012帧结果。后续5022帧／8种组合的独立证据及产品范围另见[现场演奏核对](GW25K_PERFORMANCE_SCOPE_20261019.md)，没有改写本页历史验证或生产RTL／固件。

## 2026-10-19赛题口径与独立续验

题目全文及随后用户对D／TF PCM的补充解释已保存，按“保留采样／TF路径，禁止直接播放预处理音乐冒充实时合成”继续推进，原素材审核和回录边界保持。补充的32实时声部串行重建／FFT验证通过；完整采样器9个RTL测试、5个导入工具测试、5个模块lint通过，D播放中8种组合继续通过。详见[赛题验收对照](CONTEST_REQUIREMENTS_20261019.md)。生产RTL／固件与原功能回归输入一致，没有重跑18道整机门禁，也未改写本记录原JSON／哈希；未板测、未烧录、未SYN／P&R、未新增时序实验，时序未闭合。

## 同轮后续远程25K工程与设备控件

新远程`5a4bd71`已导入完整25K工程和硬件资料，检查唯一README重叠并保存本地全文后快进接入，其他138K未提交输入保留。真实25K顶层现默认使用已确认控制映射，持音移调顺序、快重连不补播、物理每档一步、长按未分配及远端页控件可用已落地；旧独立行为保留在构建兼容分支。完整设备最终回归38测试台、25个Python协议测试、88项检查通过，152项输入稳定；真实138K Host／设备PL端点闭环1019请求、2帧通过。新证据见[设备控件落地报告](GW25K_CONTROLS_20261019.md)。旧“缺完整25K源码”仅描述导入前状态，原JSON／哈希未改写。25K专有效果上下文／16键表、整机D及专有页面仍未完成；未板测、未烧录、未SYN／P&R或新增时序实验，时序未闭合。
