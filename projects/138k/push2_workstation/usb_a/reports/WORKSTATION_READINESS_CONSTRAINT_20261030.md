# 模型就绪同步级间约束（2026-10-30）

在 `tools/workstation_custom_flash.py` 为现有模型就绪同步链加入 `model_memory_meta* → model_memory_ready*` 的 2.000 ns max-delay。原第一级 D 端异步例外、Flash MISO 输入延时及两级 RTL 保持原语义。此改动把原有物理门禁的要求交给实现器；没有放宽门禁或给第二级增加 false path。

原 F02 实现的 CLK→Q 为 0.306 ns、布线 1.732 ns，合计 2.038 ns，未满足原 2 ns 门禁。路径和后续 audio／USB 修复依据见 [只读分析](WORKSTATION_F02_TIMING_REPAIR_PLAN_20261030.md)。新约束必须在下一明确源码候选中重新综合和 P&R，实际 CLK→Q＋route 才是判定依据。

父级校验通过：`test_workstation_custom_timing.py` 7 项、`test_current_workstation_sources.py` 10 项，以及带明确 RISC-V／Gowin 环境的完整 `test_workstation_custom_board.py` 9 项（255.892 秒）。最后一项包括 prepare 和小型 TMDS 综合；不表示完整工作站综合或物理门禁通过。[机器证据](workstation_task_20261030/readiness_constraint.json)记录源码哈希、执行环境和日志身份。

首次运行缺少工具环境，随后一次外层 180 秒超时；最终在共享 EDA 锁下使用 900 秒外层上限完整通过，未遗留 EDA 进程。未启动完整工作站 P&R，未操作板卡、SRAM 或 Flash。F3 仍绑定原 revision 2 SDC，不包含本变更；revision 3 的来源锁保留旧身份，后续整合须显式生成新版本，不能冒用其验收。
