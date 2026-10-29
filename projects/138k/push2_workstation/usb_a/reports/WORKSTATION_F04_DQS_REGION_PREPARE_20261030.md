# 固定父网表的 DQS HOLD 区域实验准备（2026-10-30）

F4（`C11030F4`）从 [F3 原物理证据](workstation_task_20261030/f03_physical.json)锁定派生，继续使用 revision 2 的原综合 VG 和 SDC，只在 F3 CST 末尾追加 8 条位置约束：四个 `read_rclksel_conf` 寄存器与各自 `hold_Z` LUT 靠近对应左侧 DQS lane。保留 F3 的 capture 区域、0.800 ns min-delay、所有 IO／硬资源和自动 hold 修复。未改 vendor、冻结来源、网表逻辑、频率或时序例外。

F3 最差 setup −2.475 ns 的数据路径有 8.179 ns 布线、0.454 ns cell 和 0.306 ns CLK→Q；配置寄存器及 LUT 原在约 C170…180，DQS 在 C0。本实验检验局部区域是否减少这段路由，不能提前认定修复。其他动态输入路径、配置寄存器其他扇出和全局布线也必须重新通过 STA。

沿用 `workstation_custom_board_implementation.py` 的显式物理派生入口，新增 `--ddr-dqs-hold-regions`；没有新增编号生产构建器。前置检查覆盖父证据／全部输入哈希、四组 FF→LUT2→DQS HOLD 的真实连接、FF 初始化／UI 时钟／复位、LUT truth table、DQS X4 配置以及硬资源／原 min-delay。任一漂移即失败。第二级物理子候选保留更早父快照原字节，并为直接父级保存独立命名快照，避免覆盖祖先证据。

5 项新边界／漂移测试、7 项原 capture 准备测试、22 项原物理准备测试全部通过。真实 F3 派生成功；[机器记录](workstation_task_20261030/f04_dqs_region_preparation.json)包含候选配置、源码及输入哈希。物理 manifest SHA256 为 `3ee6ef4a03d620de27a01fd012026686fe21c5e98d0cf51138277424cbd13e0a`。

P&R 已在共享 EDA 锁下另行启动，产物位于缓存 `f04-dqs-regions-C11030F4`；本报告只接受准备阶段，待物理报告给出实际位置、所有门禁和位流身份。此候选不包含新双率 DSP、最终 PCM、ADSR 或灯光源码变更；不能将其物理结果转授给下一整合候选。未操作板卡、SRAM 或 Flash。
