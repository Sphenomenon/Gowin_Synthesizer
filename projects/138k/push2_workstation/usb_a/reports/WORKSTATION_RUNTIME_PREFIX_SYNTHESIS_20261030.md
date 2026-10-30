# TF quiet／并行 counter 候选综合与父级审计（2026-10-30）

候选 `custom138k-workstation-r00-no-local-panel-v1-c7d66b419868f7f4` 已完成真实整机综合，退出码 0、耗时 360.472 秒。输入来自源码提交 `51b266a` 的独立 prepare 副本；593 项 staged 输入与四项综合输出已由父级逐项重新哈希核验。269 项编译输入明确选择 native balanced counter，旧串行 counter 仍暂存但禁用。该候选包含 TF quiet 发布寄存器与 counter 两项源码修订，不继承 serial277／FF 的实际网表接受。

实际 VG SHA256 为 `8c5d1e5a30baad7a7e4cd705cfdcf4fcc301369bcb6c69d78f9a7f47c10acb2c`。综合估算 Logic 106,720、Register 60,912、BSRAM 229；相对 serial277 为 +274 Logic、+1 Register、BSRAM 不变。这些数值不是物理资源占用。Gowin 未报告 AG 组合环诊断，该检查也不等于完整 lint 或组合环证明。

综合估算的前五条最慢路径全部为 Chorus `lfo_23_s0` 到 `read_address_{8,7,6,5,4}_s1`，最差 39 级、slack −18.817 ns。TF quiet 与 counter 不再出现在此五条列表中；这不能证明它们的路由后时序已经改善。后续按实际路径验证 Chorus 精确算术窄化，并保留当前候选的独立物理结果。

父级在该实际 VG 上完成三项公开审计，并逐项核对审计工具当前源码哈希：时钟 4 tests／28 负控；Gray／媒体／USB CDC 27 tests／75 负控（两个可选旧 VG 测试跳过）；PCM 18 tests／109 负控。PCM 审查保持 229 位源数据、896 个 selector 与 65／263／141／207 完整消费者闭包，已安装约束仍为 `paired-nextq-v2`。上述结果仅覆盖各自声明的部分源码契约，未接受完整 CDC、reset inventory、PLL 或物理时序。

旧 serial277 BLE DDR scope 对新编译来源保持拒绝；新的 prefix scope 和实际 TF／counter 网表独立复核另行封存。HDMI owner8 显式 provenance 是后续独立源码阶段，不向本候选回填新身份。机器记录及所有本地证据路径／SHA 见[父级记录](workstation_task_20261030/runtime_prefix_synthesis_parent.json)。本阶段没有 P&R、板卡操作、SRAM 或 Flash 部署；完整任务方框保持未完成。
