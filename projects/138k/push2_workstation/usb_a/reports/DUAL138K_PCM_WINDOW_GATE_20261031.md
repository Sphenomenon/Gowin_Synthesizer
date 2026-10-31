# 双 138K：PCM RAM 窗口资格因子化

2026-10-31。W7 完整物理报告的最差 setup −8.598 ns 从 audio 域 `staged_frames_0` 到 PCM memory CE／written 状态，数据延迟约 21.4 ns。维护源码 `rtl/audio/workstation_ae350_pcm_owner.sv` 的 COMMIT 帧完整性通过 `required_mask=~128'd0>>(128-staged_frames)`、动态 written 选择和 `response_error_o` 返回；原全局 `accepted&&!response_error_o` 也包住无关的 RAM 窗口写入，令该组合路径进入 RAM CE。

本次只把 RAM／written 置位资格因子化为其完整原规则：已接受的窗口写、对齐且全 strobes、armed、完整 raw key 相等、目标 slot 未 owned。非窗口命令仍使用原 `response_error_o`。RAM 写的位置仍在原非窗口命令和最终撤销分支之前；同拍 session／TF／CPU／物理上下文撤销的优先级、错误响应、溢出计数、COMMIT mask、序号、SRC／效果／输出节拍均未改变。没有提前收缩 key、增加权威副本或更改失败语义。

冻结原整模块 reference 位于 `sim/audio/fixtures/workstation_ae350_pcm_owner_before_window_gate.sv`，SHA256 `765e05213e6de5df1c729ef9b43ac2a40025fdaf90ebc060080079855d31dfb8`。它只作为测试输入，未被生产编译选择。`sim/audio/run_ae350_pcm_window_gate.py` 给原、新整 owner 相同输入，每拍逐项比较全部列明状态／输出、512 个 RAM 字、4 个 written bitmap 和 frames；覆盖 6,000 个确定随机命令及合法／非法 strobes、旧 key、owned slot、未 armed、任意描述符、并发提交／消费、同拍 TF 撤销与 RAM 写、复位和会话变化。四个负控分别删除 strobes／key／ownership 校验或改变同拍撤销资格，全部在逐拍整模块比较处被拒绝。

[完整整模块 reference 证据](dual138k_pcm_window_gate_reference_20261031.json) 与 [真实 runtime 证据](dual138k_pcm_window_gate_runtime_20261031.json) 均通过。真实 APB／CDC、PCM owner、DSP／chorus、唯一最终音量和解码 I2S 验证了 1,454 个物理帧（1,436 good、18 契约错误帧）、119 direct、37 half-volume、9 history、446 wet；MIDI 保留、CPU／session fence、TF 和双采样率覆盖通过。既有七项 owner 功能回归也通过，包含短块、分数 SRC、满队列、部分描述符、序号边界、history 超时及同拍发布／消费。长期 ±2000 ppm 测试未在此阶段重复，不能据此新增 sustained 声明。

此阶段仅声明源码、同拍等价和实际 runtime 仿真通过，尚无新候选完整综合／P&R 资源或时序结果；不能预记 −8.598 ns 的收益。COMMIT mask 本身保持原实现，只有新完整物理报告仍证明它是剩余瓶颈且存在等价证明时才另行窄修。没有下载 SRAM／Flash 或硬件验收，板卡镜像未改变。
