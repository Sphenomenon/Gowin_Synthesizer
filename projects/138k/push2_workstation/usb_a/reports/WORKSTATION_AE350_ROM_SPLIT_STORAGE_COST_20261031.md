# AE350 ROM 扩容的实际存储综合成本

2026-10-31，固定源码 `caf6c05`。对[已验证的 ROM64 组合预算](WORKSTATION_AE350_COMBINED_MEMORY_BUDGET_20261031.md)和 [ROM128 分区预算](WORKSTATION_AE350_ROM128_SPLIT_MAIN_20261031.md)分别做独立存储模块综合。两次使用同一维护存储 RTL、相同完整端口 wrapper、50 MHz 时钟和原 8 KiB scratch RAM，仅显式 ROM 容量与对应可执行布局不同。

| 实际综合对象 | vendor Logic | LUT 利用量 | ALU | Register | 综合 BSRAM | pROM／SDPB 实例 |
|---|---:|---:|---:|---:|---:|---:|
| ROM64／完整组合预算 | 281 | 241 | 40 | 255 | 40 | 32／8 |
| ROM128／冷热分区预算 | 310 | 270 | 40 | 256 | 72 | 64／8 |
| 分区扩容增量 | +29 | +29 | 0 | +1 | +32 | +32／0 |

原始 LUT 为 229／257，另有 INV 12／13，构成利用量 241／270；没有把 INV 漏出 vendor Logic 口径。综合输出 `.vg` 中真实 pROM 和 SDPB 实例数与报告一致。两次 EDA 分别 1.491／0.884 秒，退出 0，全部固定输入前后不变，按全局 Gowin 锁串行执行。

对于这两份实际布局，将外部 ROM 扩为 128 KiB 的存储成本是额外 32 个综合 BSRAM 实例和 29 Logic。原 scratch RAM 的 8 个 SDPB 保持。它支持“用 BSRAM 提供代码空间”的具体预算，但不是整机净 CLS 收益、物理 BSRAM 数或可布通承诺；两份布局还包含不同放置产生的远调用。整机采纳前，仍需把新增存储、邮箱／搬运成本和实际退出的业务逻辑同口径核算，并测 ROM 取指性能及完整物理时序。Cache 未启用。

本阶段没有 P&R 或板卡操作。输入 ROM 哈希、工具身份、完整报告及实际网表由[机器记录](workstation_task_20261030/ae350_rom_split_storage_cost.json)绑定。父包 `/Users/sphenicidition/.cache/gw138k-task-20261030/ae350-rom-split-storage-cost-parent-v1` 的 verifier 已实际通过，30 项直接外部文件；seal SHA256 `5b6c2297bf83d02faf74ecb0a56772785cef1c42ce12241ec398f854511d6ccf`。
