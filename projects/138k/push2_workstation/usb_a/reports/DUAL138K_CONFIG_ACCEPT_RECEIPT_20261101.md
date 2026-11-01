# 配置事务等待实际广播接受回执

2026-11-01。原 runtime 在 CFG_ACCEPT 仅看 service ready：PCM hard fault 同拍撤销 config_valid、core fault 尚未置位时，ready 仍可能为 1，FSM 会进入 ACK，而核心并未广播接受配置。本次修复直接导出既有 `engine_rate_commit` 作为只读接受回执，service 只对外部请求返回该回执，runtime 据此进入 ACK。ready 接口保持；没有新状态、延迟或参数副本。健康路径保持，故障／撤销路径禁止虚假 ACK。

三份维护 RTL 和必要旧证明兼容入口已验证：

- M／W 完整 service 共 33,280 个四态组合检查，接受回执严格对应外部请求的实际广播；错误 ready 回执变异被拒绝。
- 实际 M／W runtime FSM 覆盖 PCM／core fault、underflow、同拍撤销、健康广播同拍 ACK、applied 后回 IDLE；恢复旧 ready 条件的实际负控触发 PHANTOM_ACK。
- 原 config-ready、sample-admission、effect-slot 证明、负控及完整 service 对照通过；旧 service 对照覆盖 264,605 半周期。历史 fixture 保持，三份 RTL 的严格逆变换逐字等于 Git 前版，NBA 目标／值／顺序不改。
- M 完整 runtime 22,532 帧、生产启动 1,028 帧通过；完整 sample miter 独立定点模型比较 48,645 帧（48k 24,323／44.1k 24,322）、31 个私有边界、115,929,947 次 effect 对照。配套 PCM 通用／D-only 正式路径与本批 bitmap 修复一起验证。

主线程独立阅读实际接受链与十一份变更，执行封印复核器，通过 797 文件／220 当前输入／11 owned 身份与内容快照。17 项来源门、26 项 demo 门（1 项 skip）的此前终端结果单列，没有伪造持久化原始日志；完整记录与身份见同名 JSON。

本阶段未更新 profile、综合或 P&R，未验收物理时序／资源收益、HDMI 像素、真实 DAC 或手机，未 SRAM／Flash。旧 prepare 只提供明确列出的历史模拟输入，不是新生产候选。下一完整 M/W 候选显式刷新来源锁后重新测量；回滚应还原本阶段十一份 RTL／sim 文件并使用原候选，同时重新评估上述原有虚假 ACK 问题。
