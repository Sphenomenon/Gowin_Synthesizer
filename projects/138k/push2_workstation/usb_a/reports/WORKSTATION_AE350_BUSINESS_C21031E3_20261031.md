# AE350 业务替换：整机候选 C21031E3

源码检查点 `f8cf875`；现有 `custom138k-workstation-ae350-business-v1`
生成候选 `39a6b2e5cfbbf595`，614 staged／272 enabled。
保持 1080p60、双率音频、完整效果、TF、HDMI、USB 和两路 DDR 录音，
ILM／DLM 各 64 KiB、启动 ROM 64 KiB；no-CNN／no-local-panel。
本批不选择 A2DP／SBC，相关成本未混入卸载收益。

AE350 的真实启动／后台 pump 调用 C owner，接管八槽任务、三类 ID、
START／STOP／GET／CLEAR、全部 OPEN／READ／ACK／组合读／恢复、
CLOSE／CANCEL 与 30 秒超时。原 `native_bluetooth/ble_recording.v`
及其任务、对象、下载会话状态机退出编译；FPGA 保留采集、CRC、DDR、
封存、Rice、线规和重放缓存等数据通路。本轮增加共享 20 周期 GATT
sample／CRC builder、现有 C350 上的真实 pump 观测，并修正六个共享
release FF 的旧空 CLEAR 选择器；没有新探针或长期 profile。
上述替换已由固件／RV32／APB／实际 RTL 协同仿真覆盖；硬核 AE350 的
实板执行尚未验证，不能作为整机迁移验收完成。

## 完整综合

Gowin 综合退出 0，362.104 秒，登记输入前后保持，无 AG 组合环诊断。
VG SHA256：`8bc03bfcb25a970abafd7aef6d1e2ca448227c21478d35d05680ecef5667df88`。

| 综合资源 | 迁移前 011fdc9c | 前次 business 1a806f23 | 本次 39a6b2e5 | 相对迁移前 |
|---|---:|---:|---:|---:|
| Logic | 94,623 | 97,095 | 96,704 | +2,081 |
| LUT | 75,967 | 78,715 | 78,346 | +2,379 |
| ALU | 16,802 | 16,766 | 16,744 | −58 |
| Register | 60,578 | 62,883 | 62,809 | +2,231 |
| RAM16 | 309 | 269 | 269 | −40 |
| 等效 BSRAM | 245 | 248 | 248 | +3 |

以上是完整同功能配置总量，包含 CPU 存储、邮箱、队列、总线、RTC 和
本次 96 FF 观测寄存器；尚无卸载净资源收益。前次与本次 configuration
完全相同，15 个 staged 文件变化；同时包含已并入主线的 serializer／
boot memory 等维护修改，−369 LUT 不能全部归给 GATT。GATT 本体仅
−11 LUT／−1 ALU／−1 FF；邮箱映射由 3865 降至 3510 LUT。
综合 BSRAM 不代表物理占用，Logic 不代表 CLS。

## 验证与物理进度

C／APB／实际 RTL／DDR 协同仿真通过 1701 checks、136 条消息与旧线规
逐字一致；GATT 两项回归（含背压、快照及两种中断／重连）、真实固件
六项、实际 prepare 业务十一项、accepted 来源十七项通过；profile 七项
通过，十五项外部前置跳过。ILM 30144 B、静态 DLM 656 B，保守调用栈
1376 B／预留 16384 B；ELF SHA256 为
`8b520dda735def4f9ec1bf22719257806d465593a9cf69bdfa5f40ae1cd0b479`。

`C21031E3` 完整 P&R 运行 1327.706 秒后失败：2776 条未布通，物理
CLS 61934/69120、BSRAM 297/340、Logic 97213、Register 62809。
place2／route0／不复制资源，全部输入和工具身份前后保持，没有最终
STA／位流。相对 E1 仅少 71 CLS 和 65 条未布通，仍不可上板。
新 VG 时钟正向门禁通过；PCM CDC 检查发现 serializer
`requested_s0/CE` 和禁用 guard 的差异，未将拒绝计为通过。

外部产物：`~/.cache/gw138k-task-20261030/business-gatt-integrated-candidate-v2`
及 `business-gatt-integrated-physical-C21031E3-v1`。本批未操作板卡、未写
Flash；最近读回的回退身份为 `C11028E5`。只有必要物理门禁通过后执行已授权
SRAM 验证；失败时重载已有 Flash 并独立读回原身份，不改 Flash 内容。

### serializer 最小源码修正

PCM 反例定位到禁用 SOURCE_HOLD 时仍保留两个 guard FF 的反馈。
维护源码现已显式消除禁用 guard，并将 `requested` 收敛为唯一逐拍赋值，
未修改 checker 或扩大 CDC 例外。原／新 RTL 在 ENABLE、sample error、
双率的八种组合下共 400 万配对周期全部输出／内部状态一致；启用 hold
两项、默认双率 I2S、actual prepare 十一项、accepted 十七项通过。
新候选 `42cdecbb2e9b8c7d` 沿用同一 profile／功能，源码 `0192fae`，
完整综合退出 0，359.777 秒，614 项输入保持，无 AG 诊断。新 VG 为
`9be1d177f213999e686c81278ea0160af45e928e5014a402667861d845e9e257`。

| 综合资源 | E4 | 相对迁移前 011fdc9c |
|---|---:|---:|
| Logic | 96935 | +2312 |
| LUT | 78580 | +2613 |
| ALU | 16741 | −61 |
| Register | 62810 | +2232 |
| RAM16 | 269 | −40 |
| 等效 BSRAM | 248 | +3 |

修正不计为净资源收益。原版 PCM `paired-nextq-v2` checker 未改，实际
229 个源位／896 个 selector、reply 闭包／header／next-Q／已安装约束
全部通过；六个共享 release 及 455+175 个消费者的实际连接检查通过。
`C21031E4` 的 place0／route1 P&R 已失败：2611.896 秒、退出 1，
PR0004 报 28051 条未布通；物理 CLS 62431/69120、BSRAM 297/340、
Logic 97432、Register 62810。全部输入和工具身份前后保持，未改变时钟
或数据路径例外；没有最终 STA／位流，新 SRAM／Flash 操作仍为零。

E3 所有输入保持不变；E4 没有继承其综合／物理接受。E4 外部目录为
`business-serializer-integrated-candidate-v1`、
`business-serializer-integrated-physical-C21031E4-v1` 和
`business-serializer-integrated-necessary-gates-v1`，均在上述 cache 根目录。

### 邮箱 RAM 实际替换

源码 `cb405af` 将 mailbox staging/result 两份 512 bit 寄存器和 parser
的 512 bit 副本删除，生产实例直接使用两块 `workstation_sdp` 16×32 RAM
及同步 byte 口；没有禁用的新接口或第二套业务 owner。现有 APB CDC
按真实 ready 背压 COMPLETE 18 个控制周期，保留部分 staging、旧结果、
原 consume 时刻及取消优先级，CPU 的地址 ABI／固件／BLE 线规保持。
固定源码协同仿真通过 1701 checks、136 条消息完全一致、15 个 C 突变
均被拒绝；主树 mailbox 三项、GATT 两项、actual prepare 十一项、
accepted 十七项通过。新候选为 `33e2b72a7bac6501`，沿用同一 business
profile。新增两块 RAM、拷贝／读取／仲裁逻辑的成本必须纳入完整综合；
当前尚不宣称净收益。该候选尚未运行 EDA；其等待队列已由下面同批
完整候选替换，原 prepare 输入保留，E4 输入不变。

源码 `df3856e` 进一步将 data service 的 12 个结果读字及 4 个 staging
写字改为固定选择，删除宽向量动态切片，保持地址／错误／快照 ABI。
原／新 RTL 各 672 项检查通过；实际 prepare 业务十二项和 accepted
来源十七项通过，源码及共享输入已 push 至 `9bb9086`。与 RAM 改动合并
后的同一候选为 `3484de847173bbfa`，614 staged／272 enabled，功能配置
与 E4 完全相同。E4 失败后已立即开始全量综合；结果将同时计入 RAM、
同步拷贝、字节握手和仲裁成本，再以新 UserCode `C21031E5` 做 place1／
route0 完整 P&R。没有为这些改动新增长期 profile 或构建器。

完整综合已通过：341.612 秒、退出 0、614 项输入保持、无 AG 诊断。
VG SHA256：`32dd16e15b63424e255f1dffc98474cb6fdcc9a6502e284109bbb04a7b78d191`。

| 综合资源 | E5（3484de84） | 相对 E4 | 相对迁移前 011fdc9c |
|---|---:|---:|---:|
| Logic | 95317 | −1618 | +694 |
| LUT | 76947 | −1633 | +980 |
| ALU | 16756 | +15 | −46 |
| Register | 61306 | −1504 | +728 |
| RAM16 | 269 | 0 | −40 |
| 等效 BSRAM | 250 | +2 | +5 |

完整总量包含新增两块 SDP 实例及全部接口／同步拷贝／仲裁逻辑；RAM 化
及固定字选择已降低当前候选资源，但相对迁移前仍无净收益。独占映射
明细为 mailbox 1247 FF／586 ALU／2527 LUT、parser 1260 FF／380 ALU／
1876 LUT、data service 853 FF／32 ALU／37 LUT；后者由 300 LUT 降至
37 LUT。旧 `recording` owner 从 2381 FF／4048 LUT 降至 843 FF／1848
LUT，该减少量没有与新增接口成本分开计算净收益。A2DP／SBC 仍未选择。
`C21031E5` 完整 place1／route0 P&R 运行 1020.870 秒后失败，802 条
未布通网络；物理 CLS 61525/69120、BSRAM 301/340、Logic 95819、
Register 61306。输入及工具身份前后保持，没有最终 STA／位流，未执行
SRAM。物理 BSRAM 相对 E4 增加 4，不能以综合增加 2 代替实际打包成本。
新 VG 的原版 PCM `--installed --constraint-revision paired-nextq-v2`
检查通过，229 位源载荷／selector／next-Q／已安装约束闭合；六个实际
shared release、455 个 CPU CDC 和 175 个 business 消费者连接通过。
检查器与 E4 字节一致，未跑新的负控大套或改门槛；结果位于 cache 下
`business-ram-datawords-integrated-necessary-gates-v1`，不代替物理 CDC／STA。

既有 UART smoke 增加显式 `--recognition-disabled`：当前配置不会发送
B138，选中时要求全程无该报文／模型状态；CPU／DDR／CRC／音频节拍、
控制／复音门禁保留，不产生 CNN 模型验收。现有定向测试十四项通过。
这是 SRAM 后保留功能测试的配置适配，未访问板卡。

### GATT 发现响应固定槽

维护 GATT 的 Find Information 响应改为五个固定写槽，消除依赖递推
`used` 的变量写地址，保留原 MTU 23／247 下五条上限及同一 PARSE 拍。
新旧源以同一外部请求矩阵双跑：400 对请求、800 条响应和 400 次完整
64-byte 双 bank 快照逐字一致，覆盖边界／非法长度、credit／TX 背压、
满队列和未写尾部；现有 GATT 三项、业务九项、accepted 十七项通过。
E5 冻结输入未改。源码已 push 至 `2b9597f`；同功能完整候选
`67dbd4df45737a6c` 通过 actual prepare 业务十二项，E5 失败后立即开始
全量综合。完整综合退出 0，334.813 秒，614 项输入保持，无 AG 诊断，
VG 为 `d470c1b250d07f2a589e26416ce6ebb62cf96b87048f10616c62e1894588162d`。

| 综合资源 | E6（67dbd4df） | 相对 E5 | 相对迁移前 011fdc9c |
|---|---:|---:|---:|
| Logic | 94964 | −353 | +341 |
| LUT | 76574 | −373 | +607 |
| ALU | 16776 | +20 | −26 |
| Register | 61303 | −3 | +725 |
| RAM16 | 269 | 0 | −40 |
| 等效 BSRAM | 250 | 0 | +5 |

GATT 独占映射从 6230 降至 6005 LUT；全表包含其余网表映射变化，
不把全部 −373 LUT 归给该分支。当前仍无相对迁移前的净资源收益。
原版 PCM／实际 reset6 必要正向门禁通过。`C21031E6` 的同一 place1／
route0 P&R 运行 871.908 秒后失败，788 条未布通；物理 CLS 61926/69120、
BSRAM 301/340、Logic 95476、Register 61303，全部输入及工具身份保持。
虽然综合 LUT 减少，物理 CLS 反而增加 401；没有最终 STA／位流或 SRAM。

维护源码进一步将 `0x06`／`0x08`／`0x10` 的服务／声明响应改为固定一／二／
三槽，删除其余递推 `used` 写地址；同一 PARSE 拍、类型及长度错误、
尾部和队列保持。新旧完整入口矩阵的 12692 条响应与 6346 次双 bank
快照逐字一致，含六次满队列拒绝；没有扩大配置或改变 E6 输入。
完整候选 `ba876207401f8441` 全量综合通过：343.831 秒，614 项输入保持，
无 AG 诊断，VG 为
`5e69f354b1e0b79b0c7d84019b0316dca0a56a5abec6817fc044aced99c4b69d`。
整机 Logic 94978、LUT 76592、ALU 16772、Register 61306、DSP 84、
等效 BSRAM 250／RAM16 269；相对 E6 为 +18 LUT／+3 FF／+1 DSP，
未取得整机净资源收益。GATT 独占 LUT 从 6005 降至 5940，不能代替总量。
新增 DSP 来自服务计数长度乘法，未混入 A2DP／SBC 成本；维护源已将其
改成固定长度选择，新旧完整矩阵再次通过，等待下一批完整综合。
`C21031E7` 的 place3／route0 完整 P&R 运行 724.961 秒后失败，878 条
未布通；物理 CLS 61830/69120、BSRAM 301/340、Logic 95494、Register
61306，输入及工具身份保持。原版 PCM 和实际 reset6 正向门禁通过；
仍无最终 STA／位流，未执行 SRAM。


### 同功能矢量系数 ROM

原生矢量引擎的五个 ADSR profile 固定来自 `ADSR_FILE`，现在同一
`$readmemh` 初始化后以原 `envelope_step` 函数预计算 44.1 kHz 系数 ROM，
退出 attack／decay／release 三个 WIDTH32 div147 流水。phase divider
保留；原系数前寄存器和十四级 valid／profile／voice tag 延迟保持，
没有改变音符接受、PANIC、reset、quiet 或持音切率周期。默认与边界
ADSR 表在 Verilator／Icarus 的新旧逐拍比较均通过，每表 217152 周期、
530 系数结果、546 accepted notes、708 帧、40 PANIC、12 reset、10 次
并发事件及 10 次持音切率；既有双率矢量回归及零警告 lint 通过。
九个现有原生 profile 仅刷新已消费源码哈希，功能配置不变。
accepted 来源十七项、业务九项及 profile 七项通过（外部输入相关
十五项跳过）。尚无本次全量资源结果；ROM 初始化的 Gowin 综合及真实
净收益由紧接着的完整候选确认，不把理论除法器规模记作收益。


同功能完整候选 `5eac85f00fa54c84`（源码 `8582380`）全量综合通过，
328.149 秒、退出 0、614 项输入保持、无 AG 诊断；configuration 与 E7
逐项相同。Gowin 成功提取派生 ROM，三个 `g_rate_pipeline` 系数 divider
已退出网表，phase divider 保留。VG SHA256：
`53bde60e7fe8545dfa397df595ea1d3bafc4ea5b8a3f70ea342769cdcf11efea`。

| 综合资源 | E8（5eac85f0） | 相对 E7 | 相对迁移前 011fdc9c |
|---|---:|---:|---:|
| Logic | 93321 | −1657 | −1302 |
| LUT | 74932 | −1660 | −1035 |
| ALU | 16775 | +3 | −27 |
| Register | 59477 | −1829 | −1101 |
| DSP | 80 | −4 | −3 |
| RAM16 | 269 | 0 | −40 |
| 等效 BSRAM | 250 | 0 | +5 |

整机总量包含新增 CPU 存储／邮箱／队列／总线及拷贝逻辑，未扣漏接口
成本；新增 A2DP／SBC 未选中。相对迁移前的下降是业务替换与后续原生
RTL 优化的合计，不能单独归因于 CPU 卸载。矢量引擎本体由 2849 FF／
3922 LUT／26 DSP 降至 2438 FF／3821 LUT／23 DSP，原三个 divider
另有 1415 FF／1238 LUT，均为独占映射；其和不替代整机总量。
actual prepare 业务十二项通过。`C21031E8` 已开始 place1／route0 完整
P&R，未改变时钟／例外／冻结 E7 输入；最终物理 CLS／BSRAM／时序和
SRAM 仍待本次实际结果。

E8 的原版 PCM 229-bit／paired-nextq-v2 已安装约束检查、六级实际 reset
release（455 CPU＋175 business 消费者）通过；同一实际 VG 中 19 个
ROM LUT3 的 INIT 对五个有效 profile 均与 staged ADSR 文件计算一致，
160 个系数状态 D pin 逐项匹配，确认初始化没有被综合成错误常量。
以上均为必要正向门禁，614 项输入前后保持；完整 routed CDC／STA／PLL
仍待本次 P&R，不以这些局部通过替代整机验收。


### 合成器系数同功能缩减

原生 oscillator 的 ADSR 同样仅由 NoteOn 锁存的五个 profile 决定，现将
三个 WIDTH32 系数 divider 改为 canonical／44.1k ROM，保留原前寄存器、
十四级 valid 和十三级圆环 tag RAM。先应用原 RATE_SCALE／ffffc0 饱和，
再做 44.1k round／saturate；reset 未写声部仍为零，非法 profile 保留
原越界 X 语义，PANIC 不改已锁存 profile。接口及非 PIPELINED_RATE 分支
不变，仍由硬件计算实时包络与 PCM，没有将 DSP 移给 CPU。
默认及边界 ADSR 表在 Verilator／Icarus 的旧 E7 流水逐拍比较和既有
prepipeline oracle 均通过：每表约 443216 周期、23012 个系数、680 帧、
696320 slot 比较、34 PANIC、26 reset、6 非法 profile 和 10 次加载提交
同拍 PANIC，最坏 1061 cycles，原 deadline 1599。Icarus 仅在外部 staging
对已有声明排序及 parameter string 类型作兼容适配，Verilator 直接运行
未改生产源。PIPELINED_RATE 0／1 lint 通过；accepted 来源十七项、业务
九项通过，九个现有 profile 仅刷新两个已消费源码哈希。该源码将进入
下一独立候选，E8 冻结输入保持，资源收益待完整综合。
