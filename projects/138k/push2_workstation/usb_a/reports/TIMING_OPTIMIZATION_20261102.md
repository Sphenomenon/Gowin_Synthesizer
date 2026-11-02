# 138K 资源候选时序优化与布局布线

## 输入与范围

本轮从已综合的 `custom138k-native-integration-20261102-a27` 开始；源基准为 `4e636f375a35b9bc8e0110e1e69f9d426c4be195` 加资源优化报告中的未提交修改。使用 `a27_checked` 的审计网表，SHA256 为 `743b87eeec59477583db47842cbc8df6d9f4dfc455355b9b53fa2c1393a2d686`，不修改父候选或历史证据。

基线物理候选为 `custom138k-resource-physical-C21102A1`，UserCode `0xC21102A1`。器件 `GW5AST-LV138PG484AC2/I1`、version C；Gowin V1.9.12.03；place 2、route 0、timing driven 与 hold correction 开启，P&R 全局复制关闭。2026-11-02 14:31:31（UTC+08）启动。

## 物理约束来源

用户指定的 F6 目录提供综合逻辑网表及物理约束，不是 PCB 接线文件。本轮只复用其 CST 作为**有来源的离线物理参考**；不导入 F6 RTL 或 SDC，不切换分支。约束来自提交 `73c99cfd`（完整提交 ID 见 [constraint_binding.json](timing_optimization_20261102/constraint_binding.json)），原文件 SHA256：`9604f198c36ea89da98154958c95aa59f188e06b84161de9386a276f80c7b639`。原字节保存在 [reference_F6.cst](timing_optimization_20261102/reference_F6.cst)。

当前顶层 142 个信号位全部有映射，其中差分负端由成对位置隐含绑定。显式位置与版本化 `reports/workstation_integration_20261024/pinout.json`、`boards/custom_138k/model_flash.cst` 一致。只移除 F6 独有且当前顶层不存在的 `clk_16m9344` 的两条 IO 约束；没有移除当前顶层引脚或仍存在的实例约束。加密 DDR 实例的约束仍需在实现后核对解析与实际位置。

SDC 与 a27 综合候选逐字节一致：保留全部时钟、波形、定向 CDC 界限与 DDR 初始化最小延迟。没有降频、扩大 false path 或删减功能。当前没有 PCB 接线文件核对、电气验收或板上验收证据。

## 可复现入口

共享准备入口为 `tools/workstation_custom_board_implementation.py --reference-cst ... --reference-sha256 ... --exclude-reference-port clk_16m9344`。它重新审计父综合网表、核对全部端口、差分配对、引脚冲突与实例位置，并复制原 SDC。普通板级入口行为不变。

若父候选来源是保留的 canonical 源快照，使用 [prepare.py](timing_optimization_20261102/prepare.py)，明确传 `--source-root`、`--source`、新的 `--output` 与新的八位 `--user-code`。它调用同一共享入口；源快照有漂移时失败。不要复用本轮 UserCode 标记不同输入。

路由后审核入口为 `tools/workstation_resource_physical.py <timing|routes|pll|cdc|storage> <physical> --source-root <父候选源快照>`。前四项绑定既有日期审核器的原始 SHA256，适配资源候选的身份与证据字段；新增 storage 项检查 BLE DDR 两个 FIFO 的四组指针及 ready 同步器。旧审核器和所有延迟断言保持原字节。

Gowin 将新 FIFO 的 `RAM16SDP4` 端口与实例结束符写在同一行，旧网表解析器会吞入随后的 LUT／ALU。适配器补充完整实例清单，并要求包含旧解析结果；共享 CDC 的诊断来源遍历补充 ALU。只有精确匹配的 12 个命令 FIFO RAM 才能使用异步读口域证明：write CLK 与四位 WAD 必须来自 50 MHz，四位 RAD 必须来自 DDR 域 read_binary，四组 Gray 同步仍由 storage 门禁独立检查。不能将任意 RAM 输出直接标为目标时钟域。单元测试覆盖内联 RAM 后的原语、清单缺失／重复以及读写时钟错误。DDR hold 区域同时依据实际 CST 检查路由后落点，不依赖历史清单是否存在旧 flag。

## RTL 改动与验证

a28 将 TF ring 的四处 `offset + 32` 复用已有并行进位网络；容量、回绕、数据接口与周期数不变。a29 在 a28 上将共享 ADSR 算术改为四组 6-bit 进位与分组比较，保留 25-bit attack 溢出、24-bit 无符号减法和所有状态的原始饱和条件，不增加流水周期。两者仅作用于显式原生资源候选，accepted/full85 不使用这些新变换。

改动仍由 `tools/workstation_custom_timing.py` 对锁定输入 SHA256 和唯一文本锚点实施，任何漂移必须失败。归位／退出条件：冻结 oscillator 引擎迁移到版本化原生源码后，将算术实现移入其 owner 并退休对应 overlay，不将这个实验变成另一条独立生产构建链。

最终原生时序回归 9 项通过：ADSR 216,384 组全部状态／边界与随机比对；TF ring 803,072 组、四种容量；byte increment 262,464 组；sine 全部 2,048 地址；voice controls 50,000 组；PLL tuple 2,048 组；vector velocity 全部 128 值。TF DMA 的六种原有专项场景在 a28 上通过；a29 的 TF DMA 输入与之逐字节相同。共享物理准备回归 22 项、参考物理与解析器回归 6 项、accepted 来源回归 10 项通过。源文件及回归日志哈希、a27→a28→a29 的暂存输入差异见 [validation.json](timing_optimization_20261102/validation.json)。没有形式化等价证明；这些是离线仿真与工具验证，不是硬件验收。

## 结果

已完成结果绑定到 [verification.json](timing_optimization_20261102/verification.json)，由 [collect.py](timing_optimization_20261102/collect.py) 从未改写的候选清单及实际产物收集 SHA256。综合 BSRAM 233 与路由后物理 BSRAM 278 不可混用。

| 身份 | RTL | place／route | 最差 setup | 最差 hold | 物理 BSRAM | CLS | 结论 |
|---|---|---|---:|---:|---:|---:|---|
| C21102A1 | a27 | 2／0 | −0.883 ns | +0.165 ns | 278/340 | 60,757/69,120 | 路由／PLL／CDC／storage 通过；时序失败 |
| C21102A2 | a28 | 4／0 | −1.848 ns | +0.136 ns | 278/340 | 62,097/69,120 | 路由／PLL／CDC／storage 通过；时序更差，不选为改进结果 |
| C21102A3 | a28 | 2／0 | −0.892 ns | +0.165 ns | 278/340 | 60,619/69,120 | 路由／CDC／storage 通过；时序与 PLL 均失败 |
| C21102A4 | a29 | 2／0 | −1.471 ns | +0.165 ns | 278/340 | 60,808/69,120 | 路由／CDC／storage 通过；时序与 PLL 均失败，算术改写未证明物理收益 |

A1 于 14:31:31–15:05:01 完成；A2 于 15:45:46 完成（均 UTC+08）。A1 的负端点为 50 MHz 17 个、audio 365 个、DDR UI 101 个、pixel 12 个；A2 为 50 MHz 3 个、audio 2,751 个、DDR UI 238 个，pixel 闭合。A2 的局部显示改善不能抵消音频／DDR 的退步。两者 recovery／removal 及脉宽检查为正；`PR1014` 的 `clk_50m_d` generic routing 警告保留。

主要路径类别：ADSR attack RAM 到包络回写、事件／PANIC／online 控制到音频 CE、DDR 分析绘图地址与渲染状态，以及 CNN Viterbi 控制。a28 的 TF ring 加法没有出现在 A1 的主要负路径中，不能仅凭局部算术等价就宣称已经解决这些瓶颈。

A3 使用 a28、place 2／route 0，作为相同算法对照，16:08:24–16:57:00 完成。其 50 MHz／audio／DDR UI 负端点为 43／634／142；pixel 闭合。最慢为 TF DMA write_total_bytes→read_pending CE，−0.892 ns；ADSR attack→包络回写仍为 −0.859 ns，事件到矢量引擎 CE 为 −0.867 ns。视频 reference PLL 的 RESET 全传播 **10.838 ns > 10.000 ns**，因此 PLL 审核失败，不能因工具 exit 0 或 hold 为正而忽略。具体来源为 `u_video/u_clock/g_hardware.u_pll/u_reference/PLL_inst/RESET`。

a29 综合于 16:22:47–16:36:09 完成，来源／ROM／功能／CDC／时钟及网表审计通过；综合 LUT 74,398、ALU 15,380、Register 54,428、BSRAM equivalent 233、SSRAM 479。新网表 SHA256 为 `7373a847da2eef4e6a175962aea5e0b1597239e943e31bd0c3597507441f06cf`。其物理候选 `C21102A4` 使用 place 2／route 0，16:40:18–17:27:49 完成，用时 47 分 32 秒。物理 Logic 93,166、Register 54,428、DSP 156.5/298。

A4 的 50 MHz／audio／USB48／DDR UI／pixel 负端点为 **17／868／12／98／31**。最慢路径为 DDR `cs_memsync_2` 到 lane 1 `DQS/RLOADN`，−1.471 ns；ADSR attack→包络回写最差 −1.145 ns，比 A3 的 −0.859 ns 更差。音频 Fmax 为 70.590 MHz，低于 76.8 MHz；USB 47.118 MHz 低于 48 MHz；pixel 135.641 MHz 低于 148.5 MHz。视频 reference PLL RESET 的全传播为 **10.651 ns > 10.000 ns**，PLL 审核也失败。

因此，本轮两项算术试验和放置选项搜索**没有证明整体物理收益**。最好的已完成物理对照仍是 a27／A1，setup −0.883 ns，且仍未闭合。a28／a29 保留为有来源、可重现的开发实验，不提升为 accepted、release 或部署候选；当前显式原生开发准备身份是 a29，不能把它称为最佳物理结果。现有工作区和独立候选没有被相互覆盖。

本机工作区的部分历史输入受 `core.autocrlf=true` 影响，故各次综合使用独立 canonical 源快照：未修改的历史输入保持 Git 中的规范字节，覆盖本轮活动修改，准备时仍严格核对锁定哈希；未覆盖任何旧候选源树。a28 位于 `results/timing_opt_20261102/source/`，a29 位于 `results/timing_opt_20261102/source_a29/`。这些是本次可审计实验的来源快照，不是新的长期生产来源；稳定源码仍来自版本化 RTL／构建工具及 `baselines/`。复现时须在保持规范字节的 checkout 使用本轮修改，不能通过修改冻结输入或跳过哈希来适配换行。

没有操作实体板、编程 SRAM 或写入 Flash；当前候选不改变已部署身份。回退保持 a27 的完整来源及其资源优化报告中的回退信息，不把 F6 位流与 a27 输入混用。

## 剩余时序工作

现有组合算术改写不足以解决 RAM 读口→共享算术→32 声部回写的完整路径。下一次 RTL 候选应优先评估 ADSR 算术结果的独立寄存级，同时延伸 write index／state／valid、忙条件和 PANIC 清理；音频 sample_ce 的既定周期不能暂停。事件到矢量／效果控制的高扇出也需在拥有者内部拆分，保留事件接受、应用和反馈的原子关系。

DDR 分析绘图地址、dashboard 几何计算和 TF DMA 控制比较是独立瓶颈，需分别准备真实功能回归后再改变流水。视频 PLL RESET 超过 10 ns 需要针对真实 source FF→PLL 路径的位置／组合深度修正；DDR RLOADN 必须保留官方模型、配置和 setup／hold 审核。不能用更松的频率、例外或 PLL 传播上限代替这些修正。单看 Fmax 摘要也不充分：A1 的 DDR Fmax 虽高于目标，详细报告仍有 101 个负端点。

全部实现已结束；本报告没有把尚未完成的流水重整、外部 IO 时序、电气核对或硬件验收算作完成。
