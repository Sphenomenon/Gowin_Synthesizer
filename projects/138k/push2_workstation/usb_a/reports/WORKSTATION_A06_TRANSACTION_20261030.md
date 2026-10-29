# A06 阶段：常开域双采样率切换事务

2026-10-30，继 F01 源码检查点 `cbb9687`。新增独立 `workstation_sample_rate_switch.sv`；接口、器件依据及待接入边界见 [SAMPLE_RATE_SWITCH.md](../rtl/audio/SAMPLE_RATE_SWITCH.md)，源码哈希与完整测试结果见 [a06_transaction.json](workstation_task_20261030/a06_transaction.json)。

核心在常开控制域处理请求、完整帧静音／排空应答、DCS 撤选／停低确认、目标资格、局部复位、预填充和首个完整新代次输出应答。只有实际输出恢复后才原子提交采样率／epoch 与 applied；接受、拒绝和失败分开。忙请求不覆盖在途事务；失钟、停高和各阶段超时保持受控静音，显式恢复不使用全局复位或 SELFORCE。

官方 GW5A `DCS(FALLING)` 模型 SHA256 `2ec53fec48601d2d491299bc3a28b4b199d3a79708f1dd38f72555a5c688ebd5`，真实原语仿真通过 1,375 个控制周期，覆盖双向切换和脉宽、连续请求、同模式 no-op、目标未就绪／失钟、旧源停高、quiesce／qualification／prefill／resume／running／startup 故障及恢复。Verilator 5.052 `--lint-only -Wall` 零警告。独立复核发现的当前源失钟隔离延迟与过早报告应用问题已修正，并复跑官方模型。

本阶段未接入整机 top、真实时钟监测器、serializer、帧调度、DSP 或 profile。持音／Note Off／PANIC、录音与 TF 忙时策略以及板上电气／时序仍待集成验证；没有新增 MIDI CC 或产品操作。A06 整项不勾选，未综合此模块到整机、未下载 SRAM、未写 Flash。
