# 双138K：逐音表情优先选择因子化

日期：2026-10-31。父提交 `47a7ab2`。本阶段仅修改维护振荡器的组合
`expression_select`，不改epoch阶段、note比较、release／allocation、ADSR或任何寄存器更新。
未对改后源码运行整机综合、P&R或板测；物理收益须由新候选独立证明。

## 实际路径

M8完整P&R `m-demo-base-v8-physical-v1/impl/pnr/custom_138k_integration.tr` Path5：
`session/event_o_7_s0` → voice2音高比较 → 最低匹配声部优先归约 →
`oscillator/expression_gain_q8[29]_7_s1/CE`，setup −1.703 ns，13级逻辑。
cell 4.492 ns、route 9.676 ns（66.851%）；起点扇出216，首段路由5.019 ns。
7 bit比较使用ALU链，随后优先归约经过voice2／4／5／12／16／17／22／29的共享LUT。
这与epoch→config→reverb RAM的取消路径是独立锥。

本轮保留原比较器，只收敛优先归约；没有加入事件／PCM流水级。
首段高扇出路由仍是风险，不能从RTL层数预记整机收益。

## 同拍逻辑恒等

32个原样 `expression_matches` 分成8组，每组4位。保留组合的group-any，
再用步长1、2、4的平行prefix合并，`syn_keep`标记这些明确边界。
prefix-1包含本组和前1组；prefix-2包含本组及前3组；prefix-4包含本组及前7组，
下界截为0。因此任意组g之前的 `prefix_4[g-1]` 正好等于前g组的OR。

对于voice v，组前OR与组内较低lane的OR是不相交的区间，并集恰为[0,v−1]。
所以每一位仍精确等于 `matches[v] && !(|matches[v-1:0])`，对任意32 bit
match向量成立；voice0使用空前缀。原匹配中的allocated／RELEASE／IDLE／音高条件全部保留。
所有gain的寄存器条件和127→128映射、NoteOn优先级均未改变。

## 来源及冻结边界

生产仍直接消费维护 `rtl/audio/workstation_runtime_oscillator_engine.sv`，不是生成RTL。

| 对象 | SHA256 |
|---|---|
| 原native | `f78307b44c346a52cc53334b20d3f507684511097c242d9cf1d8aeec866cb2cc` |
| 新native | `99cdad64b9ed09773f5fb93c43e2303fd58c780a32b6bb6b051386511bec74e9` |
| 原 `.provenance.json`，字节不变 | `92d3657f9e16f576181f6894b174fae956ba5ee98b9622e3b485c5c141a1f3c9` |
| 新 `.expression_selection.json` | `58742728c967dc752fa3279dfb9cc13e74b94c6c1e865e7921cd25f26a814674` |

新增 `tools/workstation_oscillator_expression_provenance.py` 的
`restore_native(source, provenance, adaptation)` 先核对三者身份、唯一精确锚点及
双向字节roundtrip，还原原native。`source_bundle(root)`继续反向完整旧链，精确到
prepared `7afb67e8b92828b50e42fbdfa259bf5c5ec0b39d1104bc263c5072e93067859e`。

三旧验证入口只在原native身份检查前调用这个适配；原prepared检查及
`registered_runtime_arithmetic`的final-tail位置、计数、前后哈希全部保留。
runtime_profile的import／DEPENDENCIES／constraints证据hook由其所属代理接入。

## 验证结果

专用whole-oscillator测试通过bridge重建紧邻旧native，只重命名振荡器及私有quantizer。
两边参数完全相同（runtime、pipelined envelope、pipelined rate均1），逐半拍比较
所有公共握手／PCM、32个gain／声部状态／assigned note，以及原release／allocation选择。
另用从低号到高号的独立循环构造最低匹配oracle。

- 6,134,628半拍一致；6612帧，其中6456非零；6,770,688 slot检查。
- 双率、A/B/C及五音色；4980次表情更新，包含0／1／126／127。
- 960次连续重复音高逐音释放，依次选择voice0至31，覆盖RELEASE／IDLE及全部组边界。
- 稀疏重复音高只放voice0、20、29，中间组均不匹配。遗漏最早组的真实RTL mutant被`EXPRESSION_SELECT_ORACLE`拒绝；连续重复音高会掩盖该错误，所以不能单独充当跨组负控。
- 34种PANIC阶段取消和重用继续通过；最长1061 cycles，无新增周期。
- 原振荡器4测试、原ADSR3测试通过；ADSR4096 voice边界、PANIC47 offsets及原时延继续通过。
- 原算术回归及slot／gain tag等负控通过；严格还原的原算术oracle SHA仍为`9950b3cd95dc7224158254bff05bfd2c8658b780a86e4cf4faecd3744a026705`。
- 当前native、bridge、原provenance三种篡改均被拒绝；17项accepted来源边界及diff-check通过。运行输入未漂移。

复现入口：

```sh
python3 projects/138k/push2_workstation/usb_a/sim/audio/run_expression_selection_equivalence.py \
  --output /tmp/dual138k-expression-cycle-v2
python3 projects/138k/push2_workstation/usb_a/sim/test_workstation_runtime_oscillator.py
python3 projects/138k/push2_workstation/usb_a/sim/test_workstation_runtime_adsr_pipeline.py
python3 projects/138k/push2_workstation/usb_a/sim/audio/run_runtime_arithmetic_pipeline.py \
  --oscillator-only --output /tmp/dual138k-expression-old-arithmetic-v2
```

归档：[whole_cycle.json](dual138k_expression_prefix_20261031/whole_cycle.json)、
[arithmetic.json](dual138k_expression_prefix_20261031/arithmetic.json)、
[source_bundle.json](dual138k_expression_prefix_20261031/source_bundle.json)及旧回归日志、负控失败文本。

本阶段不新增候选身份、不烧录，M8原位流及历史物理证据保持不变。
回退以父提交的oscillator源码为界，同时撤销新增bridge／helper／验证入口适配及对应profile hook；
不修改冻结baseline、旧provenance、历史记录或主检出目录的未提交工作。
