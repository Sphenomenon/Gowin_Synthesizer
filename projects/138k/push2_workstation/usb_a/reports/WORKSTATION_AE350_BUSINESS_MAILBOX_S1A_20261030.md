# AE350 已解析业务邮箱 S1a（2026-10-30）

已加入未选择的业务命令邮箱和有界 C API，作为 C01 后续迁移的组件基础。一个请求槽容纳 16 字节、完成槽 64 字节；完整 boot／owner／session／ticket 键负责观察隔离，邮箱不搬运 PCM，也不分配业务任务或录音 ID。没有生产实例、APB 页、BLE parser hook 或固件调用入口。

邮箱明确区分 claim、后台任务和结果观察。QUEUED 未交付时的 fence 可返回本地拒绝；CLAIMED／已发布后则返回不确定，并保留已知 operation ID。observer reset、断连、timeout 和 cancel 均不取消后台任务。最终 COMMAND 回调失败可能已经提交，C API 返回 COMMIT_UNCERTAIN，绝不自动重试。

独立审查执行了 560 项 RTL 检查、23 项同拍 fence／command／consume 竞争，三项 RTL 负控均被拒绝。它还复现了原 C 读函数在一次调用跨过 common reset 时混合旧键与新 payload／operation 的问题。本次合入同时修复该问题：request、当前结果及历史结果均双读完整键，成功前才改写输出。15 项身份变化回归、三项独立 C 负控通过；父级三项组件测试全部通过，其中 C API 使用 ASan／UBSan，另检查生产源码未选择该组件。

完整键双读仍不证明跨任意多次 reset 的全局原子快照。生产集成须在 common reset／总线身份中断时终止调用，证明 ACK／错误传播及 CPU fault 策略，并提供真正 owner 的恢复机制；直接 volatile MMIO 适配器不能自行报告 slave error。API 最大访问数为 context 8 读、request 21 读、observe 28 读、complete 24 写，不包含无线等待。

独立 RV32 编译中，完整 API 的 text 从 3,844 增至 3,976 字节，data／bss 为零，最大单函数 stack 160 字节；这不是完整调用链栈界限或 ROM 可容纳证据。历史余量与当前实际 firmware link 也须分别核对，后续继续评估完整保留原有服务的 GC／LTO 和实际调用子集，不通过裁掉未引用 pump 假报容量通过。

契约见 [BUSINESS_MAILBOX_CONTRACT.md](../rtl/services/BUSINESS_MAILBOX_CONTRACT.md)，父级与独立证据见[机器记录](workstation_task_20261030/business_mailbox_hardened_parent.json)。独立 seal SHA256 为 `39827cdf0f7ac8b08f40b3d5bbb7a1d6637d296430d23a657fd53eecd7ab494c`，父级已重新核对 seal 内全部文件及实际合入源码。旧 `business_mailbox_s1a_verification.json` 保留原 f7c831b 版本来源；本报告的 hardened source 使用独立新哈希，不继承旧源码身份。

本阶段未综合、未迁移录音、未退役 BLE PCM RAM，也未操作板卡。C01／C03、ROM／服务时限、完整 CDC、物理和硬件验收均不提前完成。回退可移除此未选择组件；所有现有 profile、固件源选择和 wire 格式保持原状态。
