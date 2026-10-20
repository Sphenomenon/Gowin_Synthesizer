# 2026-10-20 资源候选时序修复

最终状态：**T24 已通过完整离线验收**，BSRAM **234/340**，全局 setup **+0.022 ns**、hold **+0.160 ns**、recovery **+2.762 ns**、removal **+0.273 ns**。全部时钟域零负端点，CDC／PLL／功能绑定均通过。音频余量较小，尚未进行板上验证；五种音色及现有功能均保留。最终位流和证据哈希见 [候选清单](../RESOURCE_TIMING_CANDIDATE.json)。以下保留各轮实际结果和失败记录。

目标是完整工作站在原时钟目标下闭合 setup、hold、recovery、removal，并通过 CDC、PLL 及功能保留检查。4 Hz 音高分析、CNN 频率分块、视频双行 SDP 和完整 32-bit 空间混响继续保留；不通过裁掉功能或放宽时钟/CDC要求来判定成功。尚未达到验收条件时，候选保持离线且不烧录。

## 基准和第一批结构修复

参考为 `results/resource_rework_final_route0_20261020_041042`，输入 617 项哈希核对一致。BSRAM 234/340，最差 setup −1.392 ns。参考源码和报告保留。

本轮第一批候选：`results/resource_timing_20261020_110314_988115`，UserCode `C1102011`。从已完整布线的参考建立独立暂存目录；原验收构建器的 DDR 输入哈希门禁没有放宽。

- 音量/表情乘积先捕获为本帧目标，下一拍执行增益渐变。输入乘法仍使用前次增益；清除到达 SCALE 时也完成原本已提交的增益更新。
- 两个音乐异步 FIFO 的二进制/Gray 候选指针提前计算常量 +1，以读写使能选择是否提交，消除背压信号之后的进位链。
- USB 事件 FIFO 保持二进制预读地址和 reset-to-producer 规则，Gray 候选单独由常量 +1 生成，不改变缓冲输出时序。
- 控制 APB 邮箱在本地请求字捕获后留一个译码周期。状态读出改为寄存的 one-hot 地址选择；普通寄存器状态不再驱动整个返回字的时钟使能。CPU 事件背压保留。
- delay DMA 增加一拍收包状态，先捕获 64-bit 出队值，再写 256-bit 组包缓冲。
- TF DDR 返回资格和 256-bit 数据同拍寄存，下一拍消费已保存的长度/总数。保留重启作废、同拍返回与原 DDR 仲裁所有权。
- 视频诊断将 vblank 脉冲先寄存，再更新完整 32-bit 帧计数；观察值只增加一像素时钟传播延迟。
- Push 性能页将 /120、%120 改为有界比较和常量相减；三个条形长度在帧快照时计算。保持逐像素图像与既有流水延迟。
- 矢量 DECAY 判定使用 25-bit `sustain+decay` 与包络比较，避免先减再比较；饱和边界和声部时序不变。

构建入口：

```sh
python3 tools/build_resource_rework.py --timing-fixes --flow all --route-option 0 --user-code C1102011
```

## 当前证据

第一批功能检查已经通过，整机物理构建仍须审计自己的最终报告。T11 暂存入口漏恢复 CNN link 的 4 Hz 配置与诊断 CDC，已被 `TA2003` 拒绝于布局之前；该轮不计入资源/时序结果。入口已修复并增加实际源码配置门禁，T12 正在构建：`results/resource_timing_20261020_111212_369176`（UserCode `C1102012`）。定向验证的相关模块逐字相同，复用范围和 SHA256 已记录于 `resource_timing_20261020/t12_source_equivalence.json`。

- 音乐 FIFO：15,118 次出队，双时钟、随机背压、满/空、指针环回，与不可变参考逐周期一致。
- USB FIFO：19,830 次出队，含异步复位/重连，与不可变参考逐周期一致。
- 控制服务：3,074 次地址/数据/字节使能检查，包含合法和非法访问、快照、录音及曲谱。
- 完整 APB 路径：1,027 次事务，异步时钟、CPU 事件背压、返回字和错误一致，所有命令恰好提交一次。
- 矢量音源：213,522 周期、2,656 次事件、1,776 帧立体声，全部声部状态和原周期一致。
- 时序数值/像素套件：完整音源、量化、Push 图像和 MMIO 背压对照通过。
- 本次暂存 delay DMA：45,000 个音频样本与原参考一致，含清除、复位、DDR 停顿及预期 underrun。
- 本次暂存 TF DMA：6 种测试通过，覆盖实际 buffered native 仲裁、背压、在途重启、直接返回与同拍返回，以及独立字节/环形地址检查。
- 整机 18 项回归通过。历史回归入口中的 TF 16 项读取基础工作区源码；新增暂存 TF oracle 明确补足本轮变换覆盖。delay 回归入口现可绑定暂存源码，防止误测旧 DMA。

证据所在目录包括候选的 `timing_units/`、`tf_dma_timing/`、`staged_delay_test/`、`current_regression_*/`，以及 `results/timing_equivalence_20261020_110337_366152/` 和 `results/scope_event_ab_20261020_110337_607709/`。

完整时序尚未证明闭合，不能以这些功能结果代替布线验收。

变增益的效果链对照也通过：六种顺序、八种 mask、12,589 帧完整立体声及 clip 标志与修复前逐字一致，完整链仍为最多 105/1600 周期。视频帧诊断经 230,010 个像素周期验证，覆盖 76,667 帧和低 16 位进位，完整计数恰好延后一像素周期，Gray 每次最多一位变化。

T13 路由对照为 `results/resource_timing_20261020_111409_509663`，UserCode `C1102013`、route1。实际 FPGA 源码与 T12 完全一致，只有构建 Tcl 的路由与位流标识不同；对照见 `resource_timing_20261020/t12_t13_routing_inputs.json`。T11 的 TA2003 未通过，因此没有沿用其整机资源/时序结论。

新增审计工具 `tools/bind_resource_timing_tests.py` 已核对 T12/T13：相对不可变资源基准改动的 10 个 RTL 文件，均由实际输入哈希一致的定向测试覆盖；18 项集成回归的非构建输入也与两组候选一致。机器证据为 `resource_timing_20261020/t12_functional_binding.json`、`t13_functional_binding.json`。这些检查验证复用范围，不把 T11 的失败物理构建当作有效整机结果。

`tools/collect_resource_timing.py` 会在独立报告中核对全部输入、约束保留、物理叶节点 RAM 数量、全局 setup/hold/recovery/removal 和脉冲宽度。先以原资源基准验证，该工具正确拒绝其 −1.392 ns setup，记录 hold 0.165 ns、recovery 0.964 ns、removal 0.253 ns 及最差脉宽裕量 1.393 ns。

## 第二批结构修复

原关键路径还包括矢量偏移 DSP 的 CE、DDR 域效果卡片动画和 load_state 到事件/FIFO 使能的重复握手。第二批候选为 `results/resource_timing_20261020_113734_360986`（T15，UserCode `C1102015`，route0），与仍在构建中的 T12/T13 各自冻结。

- 矢量最大包络在最后声部处理后已稳定；state15 同时捕获校准和偏移乘积，state16 沿用原数值，不增加帧周期。T14 仅用于该定向验证，源码与 T15 相同：`results/scope_event_ab_20261020_113501_459202/verification.json`，213,522 周期、2,656 事件及 1,776 帧完全一致。
- HDMI 效果动画先并行算出四个固定目标的位置移动，再由效果顺序选择，避免 render_meta 译码后串接完整滑动算术。`results/resource_timing_20261020_113337_961433/dashboard_timing/verification.json` 通过完整 11-bit 位置域、全部 mask/order，1,048,576 配置（各核对三个位置），以及两种分析显示模式的 100,002 个周期像素和状态。
- dispatch 的空闲条件已保证 mode_ready 只剩 allocated==0；接收音符时两种音源均空闲，满声部 Note On 仍按原规则消耗并拒绝。消去重复 ready 反馈，保留表达控制背压。完整工作站旧/新双实例对照 `T15/dispatch_ab/verification.json` 通过 3,892,403 周期，输出、dispatch、事件字、事件握手和 core_ce 逐周期一致，原场景最长 1144/1600 周期。

T15 的完整物理结果和新一轮集成回归仍待完成，上述功能对照不代替整机 STA。

T15 集成回归现已全部通过 18 项；`resource_timing_20261020/t15_functional_catalog.json` 明确记录复用的测试来源，`t15_functional_binding.json` 已核对八类定向测试和集成输入，12 个改动 RTL 均覆盖、零差异。完整物理构建仍在运行，未改变离线候选或板上版本指针。

## T12 首轮最终物理结果（未通过）

工具流程及输入冻结检查通过，完整物理时序仍失败。音频 65.354/76.8 MHz（setup 1084 个负端点，TNS −633.677 ns），DDR UI 有 269 个 setup 负端点，像素 147.332/148.5 MHz（2 个端点），USB Fmax 48.883/48 MHz。最差 setup −2.280 ns；不能把 USB Fmax 或每钟 hold 汇总当成全局通过。

新增关键路径包括：PANIC → 生命周期/队列 ready → USB FIFO 二进制预读地址；声部计数串行求和 → APB/遥测状态；65×512 音乐 FIFO 的异步读地址（551 fanout）→ marker 判定 → 读使能，以及同步 Gray → 写使能；TF DMA restart → 宽 write_buf；视频 held_request CE。另有全局跨钟 hold −0.760 ns：新增的条宽 DSP 直接读取 feedback held_data，需让运算使用既有 USB 域快照，避免引入新的未约束 CDC 接收端。

下一批优先考虑：原周期平衡求和树；从 USB 域 cs/op 快照组合计算条宽（消去新异步条宽寄存器）；大 FIFO 按奇偶地址分两银行，双头同步预取并保留完整 512 项容量，读端 valid 仍由两级 Gray 同步保护；写侧 full 改寄存判定（释放只允许保守延后一拍），只针对大 delay FIFO，CNN 小 FIFO 保持原协议；生命周期使用两项弹性队列切断组合 ready 环，保留直接 PANIC 和清除全部待处理旧事件。必须为这些改动补数据序列、满/空、复位、清除及整链对照后才可验收。T15 仍在独立布局中，尚无其最终 STA。

## 第三、四批结构修复与验证

T16：`results/resource_timing_20261020_115445_182901`（C1102016，route0）。平衡 32 声部计数树，Push 条宽使用原 USB 域 cs/op 快照和完整 128-entry 常量查表，大 delay FIFO 用奇偶地址分银行、同步预取相邻队头（保留 512 项）；注册 full 只允许释放保守延迟一拍。CNN 小 FIFO 保持原协议。独立 FIFO 检查完整容量，256/512 项分别 65,839 / 67,373 次传输通过；45,000 样本 delay 对照、12,589 帧完整效果链、389 万周期工作站及数值/像素/MMIO 套件通过。

T17：`results/resource_timing_20261020_115841_334502`（C1102017，route0），继续切断生命周期队列的组合 ready（两项完整事件字，PANIC 直接旁路且原子清除两项旧事件），TF 组包 buffer 的 epoch 清除寄存一拍并保护下次读输入，视频取行请求在前一像素译码、vblank 标记提前预测为原周期寄存值。

- 生命周期原有定向测试通过；新增独立事件账本验证 36,395 次接收、36,235 次正常交付、160 次取消及 404 周期直接 lifecycle，三路输入和随机背压，无丢失或重复。
- TF DMA 六个独立字节/环形地址 oracle 再次通过，包含实际 buffered native 仲裁、在途 restart、短尾、停顿及零延迟返回。
- 实际暂存 video/recorder/score 对照在行为 SDP 与 Gowin 官方 SDPB 两种模型均通过：37,367 包、639 cue、67,200 有色像素、4,208 DDR 请求、10 帧，含故意丢行导致的超时与旧 tag 作废。
- T16/T17 的物理结果尚待最终 STA；T17 新集成回归在运行。

T17 光栅对照通过 7,500,000 像素周期，含中途复位，frame_start/line_start/vblank 以及所有坐标/同步完全一致。全局 STA 审计器现额外要求四类全局报告包含实际路径，并检查脉冲宽度；T12 重新审计仍明确失败（setup −2.280 ns，hold −0.760 ns，recovery 0.165 ns，removal 0.256 ns）。物理 BSRAM 仍 234，CDC 与 PLL 通过，不能代替 timing_closed。

T18 暂存：`results/resource_timing_20261020_120219_996450`（计划 C1102018）。把共享 DDR 请求槽宽 payload 的采样使能从 request_ready 改为 !full，只有 occupancy/握手保留 reset。invalid payload 可以采样，首次接收时仍同拍覆盖并置 valid；数据不受无效期取值影响。独立八客户 DDR 命令/掩码/返回账本（tag_bits 2/3/5）与实际 buffered TF 六项 oracle 均通过。尚未开始 T18 物理构建。

T18 已开始完整物理构建；18 项最新集成回归也已通过。`t18_functional_binding.json` 核对 17 个变动 RTL，十三类定向验证全部通过并逐项绑定实际输入。共享 DDR 八客户账本另见候选 `shared_ddr_verification.json`，与暂存 queues/core 哈希一致。T17 的旧 dispatch 报告清单包含未实例化的 video/lifecycle 文件，严格复用检查因此拒绝该项；没有放宽门禁，直接重跑 T18 的完整双实例对照并通过。四份约束逐字保留证据见 `t16_t18_constraints.json`。

T13 route1 已由 Gowin 返回 exit1：`PR0004: There are total 0 unrouted nets`，没有生成位流或完整时序报告。保留原始失败信息，不以其文字中的“0”覆盖工具失败状态；该轮无可接受的物理结果，最新结构修复候选继续使用 route0。

T19：`results/resource_timing_20261020_121513_672131`（C1102019，route0），仅在 T18 基础上移除 `read_total_pending` 的 late read_accept 宽 CE：无在途请求时逐拍采样候选计数，受理后保持到已寄存返回消费。六种暂存 TF oracle 已通过；完整物理构建和新的 18 项集成回归在运行。

物理证据采集器还绑定工具成功状态、位流 SHA256、CDC 证据文件哈希以及 PLL 的同一份 SDF/网表。独立的 `offline_acceptance_passed` 要求本轮物理/CDC/PLL 和功能绑定全部通过；它仍不代表板上验证。

## T23：局部写提交与 HDMI 文字路径

T15 的最终物理结果为 234/340 BSRAM，setup −1.232 ns、全局 hold −0.863 ns；音频 70.163 MHz，USB 52.260 MHz，像素 192.017 MHz。CDC/PLL 通过，但仍非时序合格。音频剩余关键链之一为 score_length → 全局 response_error → cpu_event_valid/寄存器 CE，因此下一批把写地址预译码为独立选择，逐地址使用自己的合法性条件和提交脉冲；错误返回保留原逻辑，事件合法性直接判断原 event 格式。

T23 暂存/构建：`results/resource_timing_20261020_122446_658378`，C1102023、route0。新的 services 允许条件通过旧参考全对照；扩充后的测试覆盖完整 256 条 cue、倒序拒绝、满容量、启动/停止/清除/运行中保护、record valid/empty 和快照释放/重取，以及原有全部地址/数据/strobes。完整异步 APB 1,027 次事务继续相同且恰好提交一次。

HDMI 效果标签和 ON/OFF 字符选择移至已有 B 级；A 级不再经过 effect_hit 选择 256-bit text_line。字体行号直接使用固定光栅区域的原始纵坐标，避免 effect_x/read_x 经过整段文字位置选择。随机像素检查捕获了 804..819 行频率标签与右侧 R 标签的不同原点，已补齐 x<1104 条件。另加完整 1920×1080 光栅对照，覆盖正常/分析两种显示模式；当前仍在运行。T20/T21/T22 只作定向测试暂存，没有声称有效物理结果。

T23 物理构建和 18 项最新整机回归已启动；本报告最终验收状态仍为未闭合，等待自己对应的完整报告。

T23 扩充 services 定向测试现通过 4,125 次访问，含 busy guards / record valid 和 empty 分支；完整 APB 仍 1,027 次通过。HDMI 已通过完整 1080p 加随机画面共 2,173,702 周期，正常/分析两模式像素和动画状态相同。T23 工作站双实例对照也通过；物理构建仍在运行。

T23 综合完成并通过约束解析：SYN BSRAM 197，完整功能层级/ROM 几何通过。音频综合估算 80.254 MHz、USB 66.359 MHz、像素 236.558 MHz，均不是最终 STA；`t23_synthesis.json` 保存估算及适用边界。统一入口 prepare 与 T23 非构建输入完全一致，证据 `entry_prepare_verification.json`。


## T24：Gray 写指针最高位名称补齐

T16/T17/T18/T19 最终均为 234/340 BSRAM，但不满足时序验收。T17 全局 −6.181 ns setup、−1.828 ns hold 源于两个 512-word 延迟 FIFO 的 write_gray[9] 被综合为等值 write_binary[9]，原 write_gray 通配符未命中该寄存器。现仅附加这两个源位到各自 write_gray_meta[9] 的 10 ns max_delay 与原有 hold 例外；所有原始 SDC/CST 内容、时钟周期、其他 CDC 约束均逐字保留。路由 CDC 审计继续核验来源寄存器、完整两级同步和真实飞行时间，附加约束仅允许已证明的最高位。

T24 `results/resource_timing_20261020_124632_064482`（C1102024）与 T23 的全部 RTL/ROM 数据相同，仅 build Tcl 和上述 SDC 附加块不同。曾复制相同综合网表并记录 SHA256；实际 Gowin `run pnr` 仍重新触发综合，不能声称节省了综合时间。功能绑定复用 T23 的相同 RTL 验证，明确记录精确的 SDC 单独变化，不放行任何其他输入差异。

T23 最终结果已有：音频 76.928/76.8 MHz、USB 55.488/48 MHz、像素 220.590/148.5 MHz，**所有时钟域的 setup/hold 端点均为零**。全局 setup −6.915 ns / hold −1.945 ns 仅列出上述两个漏匹配的 Gray MSB，因此 T23 仍不算验收通过。T24 的完整重新构建继续验证。

## T25/T26：附加等价优化（尚未纳入合格候选）

T25 `results/resource_timing_20261020_124905_665114` 把普通振荡器包络的 decay 减法比较改为扩展 25 位 sustain+decay 阈值；图像增益对应的移位量在 GAIN 时提前计算，坐标饱和先比较有符号偏移量，再做 8 位偏移。图像地址对照实际旧/新 RTL，已穷举全部 17 位带符号输入与 8 档增益的 1,048,576 组坐标，全部一致。完整事件工作站双实例再次通过 3,892,403 周期对照。数值/像素及整机回归各自保存新输入哈希。T25 全流程综合布线已启动，不能用这些功能通过代替 STA。

T26 `results/resource_timing_20261020_125241_653624` 仅为 APB 返回采样的进一步定向暂存：request pending 期间持续采样 response_held，接受当拍仍捕获相同返回值、ACK 后冻结，避免 command_ready 控制整条 33 位返回总线 CE。异步 APB 1,027 次事务、回压、相同 words/errors、恰好一次提交已通过；尚未启动物理构建。


T25 的 18 项整机回归、8 项数值/像素对照、3,892,403 周期工作站对照均已通过，14 项定向证据覆盖全部 18 个变更 RTL；绑定文件为 `resource_timing_20261020/t25_functional_binding.json`。T26 的 4 项 units 也通过，但仅是定向暂存，不作为合格物理候选。

另以 T23 原 `.pr` 路由生成 T27 `results/resource_timing_incremental_20261020_125601_885721`（C1102027）。本机官方 SUG100-4.4.6E 第 4.3 节明确支持 Arora V 的 Incremental Placement and Routing；Tcl 使用 `set_option -inc_pnr` 指向复制的 `.pr`，原始路由 SHA256 随输入冻结保存。T27 RTL 与 T23 相同、SDC 与 T24 相同，功能复用只允许该精确约束差异，绑定通过全部 13 项、17 个改动 RTL、完整 18 项整机回归。仍需等工具确认实际增量过程和最终完整 STA，不把工具选项等同于成功。

T23 完整 CDC 证据中只有上述两个 write_binary[9] 别名，所有其他写 Gray 源仍为原名称。18 个 Gray bus 的最大真实传播为 2.630 ns（预算 10 ns）。PLL_INIT 最大传播为 7.858 ns（预算 10 ns）。这些结果绑定该轮原 SDF/网表，不移用于新候选的物理验收。


T23 的物理资源（相对 234 块资源优化初版）：Logic 80,940/138,240（+773）、Register 46,120/139,095（+621）、CLS 56,713/69,120（+438）、DSP 155/298（−0.5）、BSRAM 234/340（不变）。增加流水和独立局部提交，未通过扩充 BSRAM 换取同域时序闭合。精确物理报告和资源分组见 `resource_timing_20261020/t23_physical_checks.json`。


## 最终采用 T24：完整离线验收通过

最终构建 `results/resource_timing_20261020_124632_064482`，route0，位流 UserCode **0xC1102024**。T24 自身完成综合、布局布线、位流生成；SYN 197，PNR 234/340，物理网表叶节点与资源表一致。BSRAM 对旧 P27 净省 28 块，剩余 106 块。最终 Logic 80,940、Register 46,120、CLS 56,713、DSP 155，所有原时钟目标保持。

| 时钟 | 目标 MHz | 最终 Fmax MHz | setup 负端点 | hold 负端点 |
|---|---:|---:|---:|---:|
| clk_50m | 50 | 53.916 | 0 | 0 |
| audio_76m8 | 76.8 | 76.928 | 0 | 0 |
| usb_48m | 48 | 55.488 | 0 | 0 |
| ddr_mem400 | 400 | 2598.775 | 0 | 0 |
| ddr_ui100 | 100 | 195.000 | 0 | 0 |
| video_pixel148 | 148.5 | 220.590 | 0 | 0 |
| cpu_bus50 | 50 | 67.873 | 0 | 0 |
| cpu_core100 | 100 | 1461.988 | 0 | 0 |

全局 setup/hold/recovery/removal 分别为 **+0.022/+0.160/+2.762/+0.273 ns**，每类均读取 100 条详细路径，pulse-width 最差 +1.393 ns。video_ref49 / video_serial742 等派生域的 setup/hold 摘要同样零负端点。最终 CDC 与 PLL 证据均绑定 T24 自身的 SDF、VO 和约束哈希；两个 Gray MSB 别名由路由网表明确证明，预算继续为 10 ns。原始 CST/SDC 全部保留，唯一 SDC 内容变化为精确追加的两个最高位别名约束。

功能绑定重算通过：13 项定向证据覆盖全部 17 个变更 RTL，完整 18 项整机回归输入与最终 T24 全部非构建 RTL 相同；T23 与 T24 的差异仅为 build Tcl 和严格限定的 SDC 别名块。通过的对照含 4,125 次 services 访问、1,027 次异步 APB、3,892,403 周期工作站、完整 1080p 与随机画面的 2,173,702 周期像素对照、完整效果链、FIFO、TF/DDR/生命周期和 SDP 存储检查。4 Hz CNN 与空间混响的既有真实权重/独立定点证明继续适用，未修改其算术与音频精度。 TF 历史 16 项子套件仍使用活动工作区源码；对实际暂存 TF DMA 与仲裁/队列改动另有 6 个独立定向用例及共享 DDR 检查，未把历史子套件视为新暂存路径的直接验证。

统一入口已收敛到最终 T24 变换，再次 `--prepare-only` 后，所有非 build Tcl 输入与已闭合候选逐字节一致，见 `resource_timing_20261020/final_entry_prepare_verification.json`。T25/T26 的附加数学和 APB 实验未纳入最终入口；在 T24 已通过全部验收后，主动停止仍运行的 T25/T27 可选构建，原因记录于各自 `trial_stop.json`。不把这些主动停止当作成功或路由失败。

位流 SHA256：`0cc7ae6263bcf92d96cf9fb9df46d6ab257d5ec5e46f86eb826886d5668092af`。文件头 UserCode 与 metadata 一致。验收证据为 [物理检查](resource_timing_20261020/t24_physical_checks.json)、[功能绑定](resource_timing_20261020/t24_functional_binding.json) 和 [最终候选清单](../RESOURCE_TIMING_CANDIDATE.json)。原资源候选指针、LATEST/板上记录均未切换，也未烧录。

```sh
python3 build.py --resource-rework --resource-timing --user-code C1102024
python3 build.py --resource-rework --resource-timing --prepare-only
```

离线时序闭合不替代板上听感、显示/USB 持续运行和 DDR 负载验证。音频 setup 仅 0.022 ns，仍需关注实际板测。4 Hz 是音乐时间轴上的分析密度；已有测例约 3.6 秒完成 2 秒音乐的计算，尚未证明实时 4 次/秒推理或识别准确率不变。本轮未迁移 TASLP 音源，现有五种音色、A/B/C、chorus、delay、录放、曲谱/指引和示波器/HDMI 均保留，USB CPU RAM 仍为 64 KiB。
