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
`C21031E5` 已直接启动完整 P&R，输入保持新身份；物理／SRAM 结果待收取。
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
E5 冻结输入未改；本改动尚无完整综合或资源收益结论，进入后续新候选。
