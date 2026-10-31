# TF 准入分组：来源与四态等价验证

2026-11-01。实际 M13far Path37 从 `available_bytes_6_s0/Q` 到 `accepted_used_23_s0/D`，setup **−2.825 ns**，数据 12.794 ns、16 级逻辑，其中 cell 6.097 ns、route 6.391 ns、C2Q 0.306 ns。完整 VG／VO 终点 D 锥各 130 个组合单元、462 条有序输入边、149 个边界，无未解析输入；类型／参数相同，21 条 GND 实例位置变化归一后有序连线差异为零。不透明 DDR 的 `memory_calibrated` 作为已确认输出边界，不宣称其内部形式等价。

关键链的 `available[6:16]` 串行零判定既用于 full／chunk，又在父层 `audio_ddr_write` 中继续结合 17:26 和容量高位，随后经过读响应与占用更新。因此本轮同时对 full／chunk 和容量当前 upper 相等判定加 kept 分组。维护 DMA 从 `cad2a4ed…241e6273` 改为 **`cc2db83b…6f0eff1`**，与审阅通过的 cache 候选逐字相同。原 `<`、`upper+1`、incremented equality、低六位进位、占用算术、全部状态／取消／重启／hold 优先级不变，没有增加寄存器或周期。

full 判定以 7／7／7／6 位的四个 OR 组实现，但遇任意 X／Z 时保留原 `>=32` 比较，chunk 使用其反相。容量当前 upper 的 `==` 分为 6／7／7／6 位四组，保持已知不等优先于未知值的语义。

验证均直接消费维护 RTL：

- 原完整 DMA runner 的两种容量、8 个负对照与 4 种独立字节环形存储场景通过。每容量包含 400008 次公开输出／完整状态比较、32768 次四态占用检查、442368 次 delta 检查与 245760 次容量检查。
- 新增 `run_tf_dma_threshold_groups.py` 与专用 testbench，每容量 208960 向量／835840 检查，覆盖逐位 X／Z、已知高位与未知低位共存、eof 四态、pending 未知及组边界；丢 fallback、漏最高位、漏容量组、chunk 绕过 guard 的 4 个负对照均被拒绝。
- Z3 对 full guard、chunk guard 和任意 26 位容量常数的四态 equality 分组均为 UNSAT；容量 78 个自由位、阈值 64 个自由位，不作可达性假设。这是表达式代数证明，实际 SV 来源由上述模拟绑定。
- 真实 TF 服务有／无命令缓冲各 23 场景，legacy 默认路径 12531 周期比较，以及有／无缓冲 token clear 各 6 场景通过，ACK bypass 负对照被拒绝。

唯一 DMA SHA pin 只见于 M／W role profile 锁；运行时 bundle 直接 hash 维护源，既有 drift 检查也对比实际源。本轮按主线程分工保留所有 profile 锁，未改历史 origin。完整路径、哈希、日志、负对照和 proof seal 见[机器记录](dual138k_tf_threshold_groups_20261101.json)。

**本轮只完成源码与离线验证。** function-local `syn_keep` 是否保留必须由下一份实际 VG 查验；如果失效，另报 module-level 分组提案，不顺带改其它算术。尚未运行新综合／P&R，不预记资源或时序收益，未操作 SRAM／Flash／实板，也未提升候选接受状态。回退为恢复精确原 DMA SHA `cad2a4ede5e8b545fa829b10baf782851dc848091c681f0bd2406f7e241e6273` 及对应候选来源，保留原物理失败证据。
