# Pitch＋Delay FIFO 实际整机综合（2026-10-31）

固定候选 `18ed947312186187`（源码 `eff1d7d`）实际综合通过，359.108 秒，599 staged 输入、269 enabled、四输出与两工具重哈一致，没有 AG 组合环诊断。VG 为 `c9f88c71…`。最终 fresh prepare 先显式复制至固定综合目录再运行；四份原位 metadata 保持，没有为后续 helper 补写旧 synthesis_copy.json。复制绑定单独记录，不因审计元数据变化回填或重综合。

相比 6b，综合 Logic 106,679→94,582（−12,097）、Register 60,910→60,574（−336）、SSRAM 1,397→309（−1,088）、综合 BSRAM 229→237（+8）。两个 delay FIFO 的层次行各为四 BSRAM／零 SSRAM；完整 payload／Gray／RAM 审计另记。DSP 原语 MULT12X12 3→4、MULT27X36 41→42，MULTALU27X18 保持 37；不据此推导物理打包。

综合默认计算域估算 Fmax 33.445→57.039 MHz，仍低于 76.8 MHz 目标。五条报告路径为显示 drops/sync_value→reader/state（24 级、−7.184 ns），PCM held_reply→serializer/have_next 的 CE（11 级、−6.906 ns），TF launched_epoch→quiesce_sync 首级（12 级、−6.867 ns），以及两条 held_reply→request_sequence（各 11 级、−6.765 ns）。这些只是综合估算；异步路径的契约／约束和真正 routed STA 须分别审查，不能通过过滤路径或放宽时钟授予接受。

只有 pitch 与 owning stereo_effects 两项编译 RTL 改变，另增三个非编译存储策略文件。编译顺序、GPRJ、SDC/CST、配置、固件、feature 和 adaptation 逐项一致；150 条警告去除 stage 前缀后完整 multiset 相同。没有新功能裁剪。

父级实际新 VG clock CLI 及四项／28 负控通过，保留 no-panel 六 PLL 与双参考／DCS 声明。paired-nextq-v2 PCM CLI、18 项／109 负控通过，覆盖声明的 229 源位和 896 selector。两项均不代表完整 CDC/reset、RAM 数据时序、PLL routed、动态 DCS 或板卡接受。

提取器的中间结果保留：原 D-only 断言拒绝新 CE 路径，显式适配后完整保留该路径；旧表格 parser 又因厂商 HTML 缺后续 tr 标签只取首行，v3 改按完整 td 分组并与真实 XML 总数核对。未改厂商报告或 STA 门禁。最初父级封存脚本误用 PCM 负控计数字段，未写 seal／报告即失败，随后按实际 negative_control_count=109 校验；最终权威为 v3。路径、SHA、资源、节点与测试见[机器记录](workstation_task_20261030/runtime_pitch_fifo_synthesis_parent.json)。

下一物理准备须绑定新 CDC、native FIFO、TF/counter 与 helper seals；本阶段尚未生成物理工程、P&R 或位流，无 SRAM／Flash／板卡操作。
