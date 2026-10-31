# M14 全量综合、严格门与实际映射限制

2026-11-01。M14 `0e7a7f996619ed83` 已完成全量综合和完整 strict 门；实际 VG SHA256 `414081bc2a6a233cdae0f7b4988ed126d44fb2f8ed5be93eefcdd7d6aba6db78`。综合 Register 46,932、LUT 52,153、ALU 12,875、BSRAM equivalent 195、SSRAM 141；这些是综合统计，不能视为最终物理块数。综合 196.83 s、exit 0，590 个声明输入前后稳定，交付前重新复验全部 588 staged。

完整来源、功能／角色退出、声画公共链、时钟、CDC／SDC selector、约束 retirement 等严格门通过，SHA256 `1f0e3ee123df3fd2fed1e75d459f9439b7aa3234b6c4bce78dc6dc57328b36f4`。独立 native VG CLI 和 54 项测试（50 通过／4 跳过）、45 个真实网表负控通过；边界 7 项、61 个负控通过。1,207 个维护工具／RTL／测试／官方 primitive／DDR 参考文件先冻结，再执行审计并复验其哈希；后续 W 源码修改不进入该候选。

实际 TF 映射只达到部分目标：[独立 primitive 语义检查](dual138k_m14_tf_groups_vg_20261101.md)确认 full 的四个分组均为两级、最终许可三层，输入与函数 UNSAT；容量函数内只有最低组形成独立等价节点，其余三组及最终节点未保留。完整 D／CE／父写许可锥已覆盖，该限制如实保留。这不是源算术等价失败，也不据此提前宣称 routed 收益。

默认物理身份 `D2110108` 已从实际综合网表独立 prepare，重新运行完整 strict 门，与 CLI 审计对象深等价；物理 manifest SHA256 `07a0273bae202d8a893038262ac0da687b236da54e3f2e26af4f6f301a94d22f`。保留完整 VG／SDC／DDR 3.500 ns，只沿用 12 条 ULPI LVCMOS33 适配，未加 monitor 或 DDR far 区域。全量 P&R 已启动，结果另验。

[机器记录](dual138k_m14_synthesis_20261101.json)绑定运行、资源、严格门、真实网表负控、快照和部分映射证据。本阶段未声称时序闭合或部署，未操作 SRAM／Flash；M 基础 revision 仍不含 CNN，真实完整 HDMI／DAC／Push／25K／TF、W 手机无线及双板共存均未通过。
