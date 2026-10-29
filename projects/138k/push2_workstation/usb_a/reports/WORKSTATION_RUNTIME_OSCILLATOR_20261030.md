# 主振荡器原生迁出与运行时 48／44.1 kHz 组件

日期：2026-10-30。新增独立 [workstation_runtime_oscillator_engine.sv](../rtl/audio/workstation_runtime_oscillator_engine.sv)，从 F02 rev2 **实际 prepared engine** 精确迁出，保留 48 kHz 周期行为，增加主 DDS／ADSR 的 44.1 kHz 运行时适配。四项局部仿真通过；未改 profile、build 或 top，当前完整工作站仍未接入运行时双率。

机器记录：[runtime_oscillator.json](workstation_task_20261030/runtime_oscillator.json)。本组件未做 Gowin 综合／P&R／板测；固定旧候选的失败时序见 [F02 P&R 报告](WORKSTATION_F02_PHYSICAL_20261030.md)，不能继承为新组件结论。

## 来源与迁出边界

来源为固定 commit `3d4b3175d0f20d0b787b61b43e4543739b26bca1`、profile 身份 `custom138k-workstation-v1-f5b723250388add5` 的 `legacy/rtl/audio/unified_oscillator_engine.sv`，SHA256 `7afb67e8b92828b50e42fbdfa259bf5c5ec0b39d1104bc263c5072e93067859e`。新源码 SHA256 `d5e58e866abd33177d79629a1dcebb2a4fab3d29981bb693424482fcd7129629`。

[相邻 provenance](../rtl/audio/workstation_runtime_oscillator_engine.provenance.json) 记录每个唯一改动锚点、次数与精确来源；测试按相反顺序还原后重验来源 SHA256。这是对独立原生源码的审计，不是生成生产实现的构建 overlay。冻结 baseline、原 engine、原 quantizer 和原选择策略均未修改；新 quantizer 独立命名，允许新旧模块在同一仿真中并存。

完整比较显示 prepared 与活动 `rtl/audio/unified_oscillator_engine.sv` 的差别是 voice-control 结构：prepared 使用并行 one-hot 优先分配、分布式 expression 寄存器与树形 active count；活动副本使用优先循环、共享寄存过程和串行 count。ADSR／slot／mix／quantizer 的流水相同。本次保留实际 prepared 结构，未直接用活动副本替换。

仿真依赖通过现有 baseline 解析器重建受跟踪的四个 ROM／插值模块和五张数据表。Sine next-address 的 native 位映射仅在测试暂存目录按精确锚点恢复，结果哈希与实际 prepared 输入一致；不读取私有历史目录。

## 组件接口与算术

独立模块保留原端口，新增 `rate_commit_i`、`rate_44100_i`、`rate_ready_o`、`applied_rate_44100_o`、`quiescent_o`。`RUNTIME_RATE_ENABLE` 默认 0，旧调用可以省略新输入；运行时启用必须设 `SAMPLE_RATE_HZ=48000`，把现有表及 voice slot step 保留为 canonical 48 kHz。

`rate_commit_i` 是 `rate_ready_o` 为真时的一拍提交，不能同时提交 sample／event／expression／mode／PANIC，也不是可长时间保持的背压请求。非法忙时提交在仿真中失败。组件的 applied bit 是配置确认，公共 requested／applied 的权威仍由整机统一控制，不能把它变成另一套业务参数来源。

在 accepted sample 边界冻结本帧 rate。44.1 kHz 的相位增量按 `round(canonical_step × pitch_ratio_q20 × 160 / (147 × 2^20))` 一次舍入；48 kHz 使用原表达式，输出与周期保持一致。中间乘积 62-bit、最终有效 step 35-bit，保留高位后再判断 `0.45×2^32` 防混叠阈值，不先截成 32-bit。禁用 pitch expression 时运行时分支使用 unity pitch，同样进行 rate 适配。

达到截止阈值只清当帧 gain pipe，不写零 canonical slot gain／step。NoteOn 在 44.1 kHz 下仍载入 canonical 48 kHz 值；持音切回后可恢复原来的有效高分音。声部、相位、包络 level／state、力度、压力、音色和已缓存参数都不重新触发。

ADSR 存储仍为当前 canonical 48 kHz 的 step；44.1 kHz 每帧用 nearest `step×160/147` 并按原最大值饱和。当前五张表的最小非零 step=408；15 个 attack／decay／release 值的最大相对增量误差为 0.04%，连续时长误差约 0.040016%，另有至多一帧边界量化。组件没有任意外部 ADSR step=1 的接口，未改五音色表；完整逐项数值在 JSON 中。LFO／glide、矢量及效果由各自模块适配，本组件不兼任其参数权威。

精确常量除法目前保留原计算周期。虽然 RTL 可综合，**其资源、物理时序与完整工作站 deadline 尚未验证**。后续可在行为对照下单独流水化，不能因失败改表、降时钟或放宽门禁。

## PANIC 与真实排空

原 engine 的 PANIC 清 issue／mix 状态，但 sine 插值与部分 tags 仍有自然尾流。新组件保留该取消行为；不把 `sample_ready` 或 `mix_busy=0` 当作排空。

`quiescent_o` 包含 load／MIDI／partial／gain ROM、issue／slot／pitch、ADSR lane、sine 四级内部 valid 的独立镜像及其输出、gain／envelope／finalize、独立 quantizer 全部 valid 与最终输出。sine 镜像跨 PANIC 继续移位，和实际子模块逐级 valid 在测试中对照。消费者必须作废取消帧，并等待 quiescent 才提交 rate；本组件不擅自修改原 PANIC 尾流语义。

## 局部验证

运行：

```sh
python3 projects/138k/push2_workstation/usb_a/sim/test_workstation_runtime_oscillator.py
```

Verilator 5.052，4 项全部通过：

- 48 kHz 116,883 clocks／275 帧逐拍对照实际 prepared reference：A/B/C、五音色、32 声部、弯音、压力、NoteOff、ADSR 分支及饱和边界；同时覆盖 expression 开／关及默认关闭 runtime 的旧调用。
- 同一组件 48→44.1→48 持音切换，38 帧；对 32 个混合音色声部核对精确相位／ADSR delta。提交拍逐项比较全部 1024 个 slot words 和 32 个 voice states，切换不重触发。无 commit 的 pending rate 输入在帧内变化不影响本帧。
- note75／flute／partial31 的 canonical step=1781707008、gain=1，44.1 kHz 下观测 9 次截止静音，反切及后续 48 kHz 下 16 次恢复有效；canonical 字节保持。
- PANIC 在 12 个 pipeline offset 注入，逐级检查实际 valid 阻止 quiescent；达到 quiescent 后 24 clocks 不再产生新输出。非法忙时 commit 是负向测试，确实被拒绝。

观测到的主 engine 最大 frame latency 为 1039 clocks，测试上限 1600。该数值只属于本组件的已采样用例，不包含效果、最终串行／CDC、整机压力或 routed STA，不能当作完整 44.1 kHz 工作站验收。编译只余 2 条刻意省略 runtime 输入的兼容性 PINMISSING 与 4 条继承来源的 unsigned 优先逻辑提示；新增宽度警告已修正，出现其他 warning class 会使测试失败。

后续仍需接入 runtime coordinator、矢量／效果历史／分析 generation、真实输出节拍和串行桥，并做完整 offline／hardware 验收。当前未改候选选择，未综合本组件，未烧录 SRAM 或 Flash。
