# 显示请求流水实际综合父级复验（2026-10-31）

固定候选 `222fb761448fb6c0`（准备源码 `9bc8fc5`）实际综合通过，377.719 秒。599 staged／269 enabled、四份 runner 输出、两工具及原 644 份准备副本重新逐项核验一致；VG 为 `f621fcbe…`、process 为 `2b9a71d6…`，没有 AG 组合环诊断。四份原位 metadata 保持，没有补写历史 `synthesis_copy.json`。后来主线未选择的 TF 组件不在这份固定输入中。

相对固定 18ed，唯一 staged／编译变化是 `workstation_display_runtime.sv`；GPRJ／编译顺序、SDC／CST 字节、业务配置、features、固件和 adaptations 保持。综合 Logic 94,582→94,749（+167）、Register 60,574→60,576（+2）、SSRAM 309、综合等价 BSRAM 237 不变；它们不是新物理打包结果。150 条完整规范化警告 multiset 无增减。

旧显示路径不再出现在本次工具仅报告的五条最差路径中，不据此声称所有显示时序已消失。实际前五条为 held_reply→serializer/have_next 的 **CE**（−6.906 ns、11 级）、TF launched_epoch→quiesce_sync 的 D（−6.867 ns、12 级），以及 held_reply→request_sequence[2/4/5] 的 D（各 −6.765 ns、11 级）。独立审查按真实 VG 闭合 403 个 pin row／201 条 tNET 邻接，90 个断 pin 故障控制全被拒绝，父级完整重放通过；没有把 CE 当 D，也没有过滤异步路径。默认计算域综合估算仍为 57.039 MHz，低于 76.8 MHz，未获得时序接受。

父级对新实际 VG 重新执行时钟公开 CLI 及四项／28 负控、PCM 公开 CLI 及 18 项／109 负控；paired-nextq-v2 的 229 源位／896 selector 均通过。它们仅接受所声明的静态时钟和 PCM/context 结构，不代表完整 FIFO/RAM/reset、动态 DCS、工具约束解析或物理 CDC。其余 shared／TF-counter／native FIFO 审查使用新的独立 scope 继续进行，18ed 接受不转移。

独立复核同时重算 canonical 身份、完整 654-file 候选库存与七项 impl 输出，并对比 HTML/XML 资源。作者 `b70115d` 的源码交付与主线 `9bc8fc5` 的四 profile 来源分别核对：主线保留先前八个 CDC helper 锁，仅增加 owning 显示 SHA，不能把作者旧 profile seal 当作新候选的全部来源。父级封存 14 份维护审计来源快照，各与准备 commit Git blob 相同，未来 root 更新不会改变本次记录。最终父 seal 为 `65214de4…`，30 文件／4,058 输入，见[机器记录](workstation_task_20261030/runtime_display_load_synthesis_parent.json)。

本阶段没有准备或运行新物理候选、生成位流或操作板卡。C2103101 使用旧显示源码且路由失败，不与本候选合并验收。完整 CDC／reset／PLL／routed STA／功能与硬件仍未通过，没有 SRAM／Flash 部署；下一物理实验须另行绑定这份新 VG 和精确审计输入。
