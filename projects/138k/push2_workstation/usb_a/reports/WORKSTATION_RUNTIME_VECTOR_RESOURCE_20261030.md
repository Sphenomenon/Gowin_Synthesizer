# Runtime Vector 共享包络系数与精确除法缩位

日期：2026-10-30。本阶段只修改 `workstation_runtime_scope_vec.sv` 及其
可逆 provenance。与**改前实际双率 native source**逐周期对照通过，旧
48 kHz 矢量回归与组合 render engines 回归也通过。没有修改其他 RTL、
时钟、final runtime、profile 或固件。父级随后完成相同配置的独立综合
A/B；LUT 从 30,926 降至 5,714，寄存器增加 576。尚无物理时序或整机净收益结论。

## 两项源码变化

原逻辑对八个 voice 的 attack／decay／release 各做一次 44.1 kHz 转换，
共 24 组不同输入的 `/147` 运算。decay／release 在源码中重复调用的
相同表达式可能由综合器共享，不能重复当成 40 个除法器。

现在从唯一 `ADSR_FILE` ROM 的当前合法 Note On profile 共享计算三项
44.1 kHz 系数，和 canonical 48 kHz 系数同拍写入所分配的 voice。
每 voice 增加三项 24-bit 派生缓存，额外状态预算为 576 bits；实际综合
可能消除常量位，不能把预算等同测得的 FF 数。canonical A／D／S／R
与 sustain、包络状态、voice 数、事件接受和渲染状态机均保持原义。

采样率在完整 frame 开始时冻结，此后只选择对应缓存。持音切率不重载
voice，也不读取后来改变的 `event_profile_i`。没有新增 ROM 数据权威，
`ADSR_FILE` 参数仍可替换；本阶段没有引入新的 ROM 初始化策略。

相位转换继续先计算完整 unsigned 62-bit 分子：

```text
N = pitch_product × 160 + 77070336
D = 154140672 = 147 × 2^20
floor(N/D) = floor((N >> 20)/147)
```

因此用 `N[61:20]` 的 42-bit `/147` 代替原 62-bit `/154140672`，保留
原 35-bit 结果与越界判断。最大 54-bit product 对应分子为
`2882303761594187616 < 2^62`，没有中间溢出。**先乘、加完整舍入项再
取高位**，没有提前截掉 product 低 20 bits；48 kHz 路径原样保留。

## 来源与可逆性

改前 native SHA256：
`14abaaa4e21a94edc16a4661e3756ecb208066321bd39bb8f548335e2298160e`。

改后 native SHA256：
`7d4e5680200f900c07a1fb708bdfb4b409ca91aeb408a1ec6ce7ca3b97c1a933`。

修改前已把原 source／provenance／静态 parent／默认数据封存在
`/Users/sphenicidition/.cache/gw138k-task-20261030/vector-resource-ab-14abaaa4`。
维护 provenance 追加六组精确可逆锚点，逆向先还原该实际 native hash，
再沿旧 edits 还原未修改的 `scope_vec_engine`，两层均验证字节相同。
编译时不生成 native 实现。

新对照 runner 从该可逆段重建实际双率 native reference，核对以上 hash，
仅对唯一 module 声明改名以同时实例化。可选与初始 cache 再逐 byte
核对；不靠静态 48 kHz reference 冒充双率改前实现，也不修改旧 snapshot。

## 验证

```sh
python3 projects/138k/push2_workstation/usb_a/sim/audio/run_runtime_scope_vec_resource.py \
  --reference-cache /Users/sphenicidition/.cache/gw138k-task-20261030/vector-resource-ab-14abaaa4 \
  --output <新的验证目录>
python3 projects/138k/push2_workstation/usb_a/sim/test_workstation_runtime_scope_vec.py
python3 projects/138k/push2_workstation/usb_a/sim/audio/run_runtime_render_engines.py \
  --project /Users/sphenicidition/.cache/gw138k-task-20261030/f03-scan-window-profile-revision3/workstation/Prj1 \
  --output <新的组合回归目录>
python3 projects/138k/push2_workstation/usb_a/sim/test_current_workstation_sources.py
```

新的 reference-cache 参数可省略，runner 仍通过版本化可逆 provenance
和固定改前 hash 重建相同 reference。

| 检查 | 结果 |
|---|---|
| native lint、新 TB＋actual native reference | 零 warning |
| 默认与 stress 两份 ADSR_FILE | 各 241,512 clocks 全部输出、调度、相位、canonical 包络状态逐周期 bit exact |
| 每份输入的双率帧 | 48k 969、44.1k 985 |
| 五 profile／八 voice | 每个 rate×profile 都含 72 帧八声部，voice 满拒绝保持 |
| 派生缓存核对 | 每份 5,796,288 项，与改前转换函数及 canonical 值逐项一致 |
| held 双向切率 | 每份 20 次，idle 切率不改变 phase／envelope；frame 中输入 rate 变化不影响当前 frame |
| overflow／频率拒绝与恢复 | 每份 16 帧，显式静音且保留 held state，降低 pitch 后恢复 |
| 在途 PANIC | 每份两率各一次，旧 render 不迟到泄漏 |
| stress 表 | zero、24-bit 饱和边界和快速全生命周期，五个 ADSR 状态全部覆盖 |
| 相位缩位 | unsigned54 边界及一万伪随机 product，之后各周期持续核对两式与实际 effective step |
| 最大 vector render | 115 clocks，与原调度一致 |
| 旧 targeted vector | 480 帧／56,809 clocks 48k 精确对照；440 Hz 双率／回切、piano attack 577／530 帧、44k 控制 slew 118 帧均通过 |
| 组合 render engines | 3,718 帧、50 切率、1,327 busy 拒绝、48 PANIC，最大 1,039 clocks，三组 PCM 频率核对通过 |
| accepted source boundary | 10／10 通过 |

组合回归保留 12 条既有 package／pitch／oscillator／静态 reference 警告：
TIMESCALEMOD 1、WIDTHEXPAND 6、WIDTHTRUNC 1、UNSIGNED 4；均不来自
本次 vector 修改，无 UNOPTFLAT。本阶段新 native／reference／TB 的 lint
与编译均为零 warning，没有隐藏这些组合警告。

默认真实 ADSR 表在该有限时长内主要覆盖 attack／release；完整状态
生命周期由显式可替换 stress 表覆盖，未以短测试冒称自然衰减全时长。
这也不是全输入形式等价或物理时序／音频接受证明。

## A/B 准备与剩余门禁

A/B 缓存子目录为 `synthesis-before` 与 `synthesis-after`，各有固定
manifest、工具 hash、SDC、Tcl 和独占非阻塞共享锁 runner。均使用相同
`vector_resource_synthesis` wrapper、`SEPARATE_OFF_NOTE=1`、八声部、
完整 geometry／默认 ADSR、器件 C、sysv2017、真实 76.8 MHz；两清单
**只有 native source 一个文件的 hash 不同**。未复制完整工程或改变
voice／effects／时钟门限。两个 `--verify-only` 均通过，没有尝试 EDA 锁。

后续由主代理明确冻结并串行运行：

```sh
python3 /Users/sphenicidition/.cache/gw138k-task-20261030/vector-resource-ab-14abaaa4/synthesis-before/run_synthesis.py --run-synthesis
python3 /Users/sphenicidition/.cache/gw138k-task-20261030/vector-resource-ab-14abaaa4/synthesis-after/run_synthesis.py --run-synthesis
```

父级在相同固定输入、工具与共享锁下串行执行两次综合，均退出 0，全部输入
哈希保持。synthesis report 的 LUT 为 30,926 → 5,714、Register 为
1,775 → 2,351、MULTALU27X18 为 38 → 17；MULT27X36 均为 12，
综合 BSRAM 均为 10。过程清单、日志和 VG 哈希纳入机器证据；没有位流。
父级另以 `vector-resource-parent-final` 重跑默认及边界表逐周期对照，两组全过。

集成 profile 的资源与 P&R／CDC／时序、全系统硬件仍待完成；这些独立综合
数字不能推断物理净收益。回退可逆最后六组 resource edits，精确恢复改前
native hash；旧基线、旧 snapshot 与 accepted provider 不变。

机器证据：`reports/workstation_task_20261030/runtime_vector_resource.json`。
离线身份 `runtime-vector-resource-offline-v1-2ae6a6d912818a9c`，source-set
`2ae6a6d912818a9c10fd5cab61e21065876ad892b1811d7042c85c70e5a86f4e`。
