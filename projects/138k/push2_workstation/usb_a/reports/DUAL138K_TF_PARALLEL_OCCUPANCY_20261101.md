# TF occupancy 的晚许可组合路径因子化

2026-11-01。M12b 默认布局的实际 Path3 从 `available_bytes[7]` 到 `available_bytes[25]/CE`，−1.642 ns、16级、数据11.401 ns（cell5.845、route5.250、C2Q0.306）；far 布局同类 Path191 为 −0.915 ns、16级。VO 都显示容量许可经过 `audio_ddr_write`、返回字节选择、7位 `committed_delta` 减法、低6位加法、carry/sign XOR 和 CE。该路径没有穿过26位 upper±1 链。默认布局还有 `available_bytes[7]→accepted_used` 的 −1.491 ns 同类路径。

维护源与 M12b 实际消费字节原 SHA256 均为 `5be6f263083122794b82f2e9d8069fae96a6d044b4cb02c024d92c58b4de2810`。本次仅在两个 occupancy 更新前加入并行组合候选，及替换两条 next 赋值；其余源码逐字节相同，原 upper±1 函数、容量规则、state／restart／hold 优先级和传输记账保持。原 `read_response_bytes` 保留；occupancy 的早期大小由 `read_pending` 选择。现有 `read_accept` 定义直接保证其不会与已置位的 `read_pending` 同时成立，因此有效响应大小相同，保留立即响应及写入与旧读响应同沿发生的情况。

available 并行预算 P−0、0−R、P−R；accepted 并行预算1−0、0−R、1−R，均保留7位减法和32位回绕。完整二态 case 在晚许可后只选结果；00仍调用原函数加零，未知许可走原 delta 和原函数，保留 partial-X 的既有悲观语义。没有新增时钟周期或顺序寄存器。修改后 RTL SHA256 为 `cad2a4ede5e8b545fa829b10baf782851dc848091c681f0bd2406f7e241e6273`。

复用既有 occupancy runner、冻结旧 DMA 和 ring oracle：两容量各通过400008模块检查、442368 signed-delta 检查、245760容量检查，并各覆盖16384个有限四态向量／32768次实际 next 比较。89自由位模型的有效响应大小、available next、accepted next 三项关系均为 UNSAT，不使用状态可达性假设。原六类破坏负控保持有效，仅迁移 input／simultaneous 的锚点到真实新 case；另加两类负控，确认把00改成 base 或丢弃未知许可回退都会失败。最终8／8负控拒绝，四组 stall×立即／延迟返回的独立 ring oracle 全通过。

[机器证据](dual138k_tf_parallel_occupancy_20261101.json) SHA256 `d103f508e2c764cafd8e8072f15f88df649b1f80f842f3f6c1d2e4c1eaab2daf` 固定全部源码、原实际路径及最终回归身份；最终外部 `tf-occupancy-candidates-regression-v2/verification.json` SHA256 为 `abaa1884c6ddab30256581f561d5d02a1fba6bfef1eb81730a7fdda55fe330b9`。四态检查为有限向量，不宣称任意四态全域证明。新源码尚未综合、P&R 或实板验证；综合是否消去旧 default 反馈、实际时序和资源收益均待新候选测量。未修改 profile／task2，未下载 SRAM、未写 Flash。回退恢复上述 M12b 源字节，并以新候选身份重建。
