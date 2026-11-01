# TF 响应选路 cofactor 维护落地（2026-11-01）

已把审核通过的局部组合逻辑精确落到维护源码，SHA256 `3f9eb8afa2c3308d270ce215693723bfb7cb48584ee96c3c3fbe749a4902e7b6`。本阶段仅完成源码实现和离线校验；未执行综合、P&R、板测或烧录，不预记资源或时序收益。M16/W14 冻结输入、两份 demo 锁和 task2 由主线程管理，本阶段未修改。

## 改动及语义

M15 far 的实际长路径由 available_bytes 经过容量/写许可、共享 DDR ready 反馈、read_response 再到 accepted_used；首条 available_bytes[16]/Q → accepted_used[25]/D 为 −1.767 ns。本改动提前形成“不选择写”和“只等待已有读响应”的完整占用量候选，最终由 write_selected 选取。已选择写时，新读请求必定关闭，但已有读响应仍可与写同周期完成。

保留原有 case 作为 write_selected 未知时的完整 X/Z 回退，保留零 delta 的四态运算行为。六字段容量函数、kept module-level 分组及实际消费者、available_bytes 选路、采样/存储时序、复位/hold/restart 优先级和全部时序赋值均保持原状。旧 storage provenance、occupancy 与 threshold runner/TB/oracle 的 bytes 对 HEAD 均相同。

新增的版本化完整参考源 SHA256 为 `5ac87cbacd1ddc35f897fdf7c3427f80bcf7b151e44370baae6fb3305a596d3b`，与 M15 实际构建消费的 DMA 相同。新 runner 固定双方身份并执行精确逆变换；恢复后必须逐字等于参考源，全部 NBA target/RHS/order 相同。旧 fixture 和 oracle 未被替换。

## 校验结果

| 校验 | 结果 |
|---|---|
| 读取实际新旧控制方程与 case RHS 的全域二态证明 | 4 条 UNSAT；143 任意位，无可达态假设 |
| 实际源二态破坏性变异 | 4 条 SAT 反例 |
| 源身份/逆变换漂移控制 | 2 条拒绝 |
| 完整当前/参考模块四态组合 twin | 1,048,576 向量通过 |
| 新分支实际源破坏性变异 | 6 条全部拒绝 |
| 原始 occupancy 完整回归 | 14/14；两容量、8 负控、4 独立字节环路 oracle |
| 原始容量/阈值 module groups 回归 | 8/8；两容量、6 负控 |
| 真实 runtime service/clear/stop 闭环及旧负控 | 全部通过；23/6/11 业务 case 各 buffered 0/1，legacy 12,531 cycles，disabled 路径 |

143 任意位包含四个彼此独立的 32 位实际候选结果，以及 13 个 qualifier 位和 2 位状态；候选任意化比实际算术关系更强，精确逆变换另外保证候选定义不变。这是二态全域证明；四态结果为有限向量校验。

完整 occupancy twin 每容量仍执行 400,008 次状态比较、32,768 次四态输出检查、442,368 次小 delta 探针和 245,760 次独立容量/五字段检查。新四态 twin 打开真实读取前置条件，穷举八个四态控制并覆盖 16 个计数/X/Z/wrap 模式；六个负控明确检出即时读丢失、无 pending 响应、写时错误新读、同周期输入丢失、未知许可回退丢失和零 delta X 悲观性丢失。

stop 结构 lint 保留 WIDTHEXPAND=11、WIDTHTRUNC=22；正向无 UNOPTFLAT，原始组合环负控产生 1 条 UNOPTFLAT 并被拒绝。未通过放宽约束或删功能通过校验。

## 证据、复跑和后续边界

- [维护验证 JSON](/Users/sphenicidition/.cache/gw138k-dual-20261031/tf-response-cofactor-maintained-v1/verification.json)，SHA256 `80a3cd41ec21f6ad5416a4bea2dcf8b9b8c0e7924bedc732a567b0752683e5de`；[维护输入/输出封存](/Users/sphenicidition/.cache/gw138k-dual-20261031/tf-response-cofactor-maintained-v1/final-seal.json)，SHA256 `b0b9882270ac015dbb149818329a825b41bd498afd501c2d31d91575c2ccc08d`。
- [运行时闭环 JSON](/Users/sphenicidition/.cache/gw138k-dual-20261031/tf-response-cofactor-runtime-stop-v1/verification.json)，SHA256 `70c0bc4d5cc349821ab4eea1c50a1037e78128138a65f1414f7124de850a2307`；[其全部 35 项输入版本与输出封存](/Users/sphenicidition/.cache/gw138k-dual-20261031/tf-response-cofactor-stage-v1/runtime-stop-seal.json)，SHA256 `995e94d520cc88a5cabc670c39acebc1aa2a7518653afdc7e9265e9b3be74025`。
- [阶段机器可读记录](dual138k_tf_response_cofactor_20261101.json)；[阶段最终 seal](/Users/sphenicidition/.cache/gw138k-dual-20261031/tf-response-cofactor-stage-v1/final-seal.json)包含上述结果、全部输入版本和阶段记录哈希。
- 复跑入口：`python3 -B sim/tf_audio/run_tf_dma_response_cofactor.py --output <new-directory>`。需要 Python z3、iverilog/vvp；入口直接编译实际维护源，并调用未改动的 14/8 回归。运行时补充入口是原有 `run_workstation_tf_runtime_stop.py`。

未发现锁以外需要变更的 DMA native-source pin，因此未修改其他源 pin，未重签历史 M15 VG/VO 证据。历史证书仅对应其冻结输入，不能当作新 cofactor 的物理验证。共享 app_rdy 仍可能把上游 audio_ddr_write 带入无写候选；新候选必须以实际消费源完成综合/网表及 P&R 比较，再判断是否改善目标路径。

回退使用新增完整 fixture 恢复本次 DMA 维护源；候选身份和锁更新由主线程处理。架构边界没有变化，无需改稳定架构入口。
