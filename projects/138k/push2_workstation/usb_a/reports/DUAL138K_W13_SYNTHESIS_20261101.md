# W13 全量综合与严格门

2026-11-01。W13 `custom138k-workstation-w-demo-v1-bc065b3de8977725` 全量综合 exit 0、221.969 s，647 个声明输入前后保持。综合 FF 45,092、LUT 55,249、ALU 14,135、BSRAM equivalent 257、SSRAM 298；这些是综合结果，物理资源与收益另验。

实际 VG SHA256 `3c7866321188f7b36dc601c36f6b572b04ee5c5f7786f434a10a1b0d2bb4a787`。完整来源、角色退出／功能保全、资源、时钟、CDC 结构及 SDC selector／retirement strict 门通过，SHA256 `6d1fa73fb6a5cb5f37647cfc686784056d5ee15d22dc96ae3f5c9a12c232a612`。951 份原始来源快照、645 staged 文件、284 启用输入及 1365 份审计工具／源码／测试文件独立封存复验；后续维护源变化不改变本候选身份。

固定快照上的 native VG CLI 通过；54 项回归执行 40／跳过 14，35 个实际网表破坏负控全部拒绝。DEMO boundary VG 7 项及 61 负控通过。PCM 新 20 组 key／COMMIT 与 raw START 的实际映射目标另行检查，不把源证明或这些通用门当作完整映射等价。

默认物理 prepare 又重新执行完整 strict 审计，其 `parent_synthesis_audit.json` 与 CLI 结果深等价。新身份 `D211010A` 已启动完整 P&R，place=2、route=0、replicate=false；保持原时钟／例外和 DDR 3.500 ns，仅有既有 ULPI IO type 适配，没有继承 W12 far 或 reference-monitor 区域。physical manifest SHA256 `8249c3266a87c818e7e5b43d106158a9c004174e487dade8b9c344bc8ccf5a9c`。

[机器记录](dual138k_w13_synthesis_20261101.json)绑定全部阶段身份、命令、测试和来源。P&R、routed STA／CDC／PLL、真实手机、25K、完整 HDMI／DAC 尚未验收，唯一录音仍为 16384 帧。未烧录 SRAM／Flash，未写受保护主区，未宣告两套声画或双板并发交付完成。
