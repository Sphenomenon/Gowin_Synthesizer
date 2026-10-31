# B04 Delay Reporting 主树复验

2026-10-31，作者提交 `3c90448f14a38e8453e3c794de39b22b3d9a5272` 以 `4f8e42d` 合入。现有 Classic CPU service 新增可协商的 Delay Reporting、远端 SEID、独立发送事务与匹配响应、稳定延迟值入口，以及基于独立单调时钟的发送／响应期限。输出仍复用原有 TX token 与 owner；未接入工作站 profile。

主代理独立审查 TX 退休和缓存 RX 的顺序、双方 label、分片类型、失败／取消／会话隔离与期限后，分别在作者树和合入主树运行真实 C、ASan／UBSan 和实际 RV32 编译。两个来源的输入哈希及行为／预算结果一致：新向量各 11,049 次检查、18 个故障变体全部拒绝；原 Classic 各 44,612 次、15 个变体，以及 11 组实际 SBC 解码共 118,784 个样本保持通过，最大误差 6 LSB。

OPEN 可在 DelayReport 被发送 owner 接受后进入；START 仍等待对应 peer Accept。匹配 Reject、响应畸形或超时都会封锁并清空旧音频；每条链路最多使用 16 个不复用 label，耗尽需重建链路，未引入绕回接收旧响应的行为。组件消费外部实际稳定延迟值，不从队列瞬时水位编造端到端延迟。

当前工具链的增量 text＋rodata 为 15,549 B，service 对象 2,876 B，最大单函数栈帧 480 B。这不是完整固件容量或全调用链栈证明。该改动新增两个 API 并改变对象尺寸，ROM128 预算 adapter 和固定计数正在单独更新；旧容量与栈证据仅适用于各自封存输入。完整 HCI transport、安全／key owner、实际延迟与漂移控制和真实手机互通尚未闭环，也没有 EDA 或板卡操作。

作者父包 `/Users/sphenicidition/.cache/gw138k-task-20261030/b04-delay-reporting-v1` 的 verifier 已实际复验，5,755 份来源／266 份输出／833 个工具文件，seal `11a80fc866240e9d867a0013b807ee5180302cd35f8513d6241f8d4e605f78b9`。主代理父包 `/Users/sphenicidition/.cache/gw138k-task-20261030/b04-delay-reporting-main-parent-v1` 的 verifier 也已通过，529 项直接外部文件，seal `f803de6e5cea3dd03df9cbf53a5c2254202b909a65a370c924027251f977acf1`；[机器记录](workstation_task_20261030/ae350_delay_reporting_main.json)绑定输入、工具、模型结果及限制。
