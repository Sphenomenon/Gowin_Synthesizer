# TF capacity 模块级分组：维护源阶段验证

日期：2026-11-01。阶段仅为实际维护源实现及离线回归；未综合、P&R、上板或部署，不记资源／时序收益。

已落地 root 核准的精确五文件补丁。`pending_fits_ring` 保留任意 occupancy/pending 两个入参及原全部算术／比较等式，返回 bit0 原准入谓词、bits5:2 四个等值分组、bit1 分组 conjunction。唯一实际调用将六位解包为五个 module-level scalar `syn_keep` 网络和真实 `ring_can_commit`；无测试专用旧函数，无新增寄存器、周期或优先级。

实际维护源验证全部通过：

- occupancy：两种容量，每种 400008 状态检查、442368 small-delta 检查、245760 任意入参 capacity 调用（独立检查五字段），32768 parallel four-state 检查；8 个实际源码负控全部拒绝，4 个独立 byte/ring oracle 通过。原 modulo oracle 保持。
- threshold：两种容量，每种 208960 四态向量／2298560 检查；6 个负控全部拒绝，含返回字段交换与实际 consumer 的 predicate 错接。
- 实际 native runtime：service buffered0/1 各23案例、legacy default 12531周期、clear buffered0/1 各6案例、stop buffered0/1 各11案例、disabled；ACK、registered-source、原组合环负控及结构 lint 全过。

六个表达式代数 Z3 query 为 UNSAT；这是表达式证明及实际 SV 仿真，不是形式化 SV elaboration 或硬件验收。所有 runner 输入 SHA 在完成后重新核对无漂移。

保留先前 `dual138k_m14_tf_groups_vg_20261101` 的 partial structural failure：M14 实际 VG 的 full 阈值分组通过，function-local capacity keep 仅 group0 有独立实际节点，groups1/2/3 和最终 equality 不完整。当前源码测试不覆盖、更不抹去这一失败。

下一门槛是 M15 全量实际 VG：按 primitive 函数、独立 FF support 核验五个 kept 标量，并证明五者真实位于最终准入 consumer 的 live fanin 锥；仅作为保留旁路输出不通过。该阶段未改 profile、task2，也未 commit；这些由 root 统一维护。

维护DMA SHA256：`5ac87cbacd1ddc35f897fdf7c3427f80bcf7b151e44370baae6fb3305a596d3b`。

精确补丁 SHA256：`fd21d56b6b8b3f33597c3d1fbcb12ed73b019d25c8d280d63a521891f697006b`。

缓存阶段封存：`/Users/sphenicidition/.cache/gw138k-dual-20261031/tf-capacity-module-groups-production-v1/sealed_stage.json`，SHA256 `d652f3bd6509cff3ffe02863d8cfae0ed8b026e2505599e41f5b39af5c95d413`。

Proof seal：`c771637b4a2c2bfe33873c04a25e1cd284a9f4d0bfbf9703f0919ee94e2332d1`。
