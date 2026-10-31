# M14 TF 实际综合网表分组：部分保留

2026-11-01。M14 身份 `custom138k-workstation-m-demo-v1-0e7a7f996619ed83`，输入 SHA `0e7a7f996619ed83ecdda6855b9ccaa54189c2b38ed5c0790c5b3fe895eef1ae`。实际消费 DMA SHA `cc2db83be37cdb297d5cf4ef631c978802a0325e61f0b14991a814efa6f0eff1`；实际 VG SHA `414081bc2a6a233cdae0f7b4988ed126d44fb2f8ed5be93eefcdd7d6aba6db78`。本报告绑定 cache certificate v5，仅记录已完成的实际映射检查，不包含后续提案。

**full 四组与最终判定保留，容量函数内完整分组未保留。** 这表示结构门禁部分通过，不表示容量算术或源码等价回归失败。

`available_full_group_0..3` 分别对应真实 available FF 的 `[11:5]`、`[18:12]`、`[25:19]`、`[31:26]`，每组实际锥深度均为 2，分别含 3／2／3／2 个 LUT。逐组精确 LUT INIT／连线对任意输入位值的差异求解均为 UNSAT，实际结构 support 无多余或遗漏 FF。最终 `available_full_binary_s1/F` 的真实网络为 `read_has_full_beat`，11 个 LUT、3 级，完整锥确实经过全部四个组；其逻辑对任意 `[31:5]` 位值也等价。这两个源变量在网表中合并为同一节点，未仅凭名字判为保留。

容量检查反追 `accepted_used_23_s0` 的 D、CE，以及原 `app_wren` 被 Gowin 提升到父层后、实际 DMA 接收的 `audio_ddr_write` 完整上游锥。CE 实际为 VCC。对三个完整锥的全部单元输出按真实 FF support 与容量常数逐组求解，只找到组 0 `[11:6]==0` 的独立等价节点 `u_tf_audio/audio_ddr_write_s13/F`（2 个 LUT、2 级）。组 1／2／3 与最终 current-upper equality 均无独立等价节点，故 `capacity_all_kept_groups_and_final_present=false`，完整结构证书 `passed=false`。此结论不是根据 `upper_equal` 字样缺失推断的。

完整根、锥、类型／参数／连线、边界与证明封存见[机器记录](dual138k_m14_tf_groups_vg_20261101.json)。proof seal 为 `aa74aed06b522b8f10f6897891eab777aa86ae7359b612c62dbf3d81bc7ec0cf`。输入及每份锥的哈希在报告前再次核验稳定；不透明 DDR 的实际 `memory_calibrated` 输出明确列为边界。

本轮没有改维护 RTL、测试或 profile 锁，没有 module-level 提案；完整 chunk 数据／准入 next-state 的网表证明不在本证书范围。M14 的真实 P&R 由主线程继续测量。本报告不宣称资源／路由时序收益、物理接受或实板验收，未操作 SRAM／Flash。后续容量 module-level 分组须另给精确差异并经评审。
