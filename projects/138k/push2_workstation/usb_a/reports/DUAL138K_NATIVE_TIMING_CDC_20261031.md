# 双 138K DEMO：Delay／APB response／TF quiesce CDC，2026-10-31

维护策略升级为 `native-demo-mailbox-structure-v3`。M8 的实际 VG、实际 routed VO 及 W7 的实际 VG 均通过新增局部结构证明；新增 SDC 已接入 `workstation_runtime_profile.protocol_constraints()`。**本阶段验证的是实际网表与拟安装的精确约束，原 M8／W7 `physical.sdc` 未修改，新指令尚未在这些旧候选中运行 STA。** 完整来源、散列与日志见 [配套 JSON](DUAL138K_NATIVE_TIMING_CDC_20261031.json)。

Delay 的两向心跳均来自实际 `heartbeat_counter_4/Q`，源寄存器具有正确时钟和恒开 CE；每一向只有对应 `peer_meta/D` 一个远端消费者，首级 Q 只驱动 `peer_sync/D`，无不透明 primitive 或顶层导出。例外限定为这一对 source Q／first D，首级到第二级仍受 2 ns 最大延迟约束。维护源中的五位自由运行加法计数器身份被固定校验；本阶段没有把含 ALU 的计数器网表冒称为算术等价证明。

`u_managed/control_cdc` 的 33 位 `response_held` 与 ACK 共用发布 CE 和复位。BDD 对实际局部使能锥证明：无论独立服务 ready 分支取何值，发布都必须满足 request 已解码、command reset 已释放、`req_settled != acknowledge_toggle`；发布边沿 ACK 取得 `req_settled`，因此同一请求不可能重复覆盖响应。三段 request／ACK 链、解码 next-Q、IDLE／WAIT_RESPONSE／COMPLETE 的完整有效 next-Q 均校验，包含 W7 将状态保持迁移到 CE 的合法优化。33 位响应只驱动逐位对应的 `response_local/D`；接收必须处于 WAIT_RESPONSE 且第三段 ACK 相等。响应保留 20 ns 有限飞行界限，仅取消这 33 对 payload 的 hold 检查。

TF 的 `source_quiesce` 是初值为静默的真实 DFFPE，先在 50 MHz 域注册，再进入 `frames/quiesce_sync_0`。完整消费者闭包证明其唯一远端消费者为该首级 D；本地 FIFO RAM 的 WRE 及其他本地消费者保留。首级只驱动第二级，源 Q 到首级 D 获精确例外，后级仍为 2 ns。`invalidate` 和最终 Gray generation 的停源取消语义保持独立，未把组合取消信号改为等待下一源时钟。W 角色适配实际验证退出全部 TF 指令，并保留 APB／Delay 指令。

| 实际网表 | 完整回归 | 网表破坏全部拒绝 | 新增待安装指令 |
|---|---:|---:|---:|
| M8 VG | 40 通过，1 项 routed-only 跳过 | 35 | 8 |
| M8 routed VO | 41／41 通过 | 36 | 8 |
| W7 VG | 30 通过，11 项 TF／routed-only 跳过 | 25 | 6 |

官方 RAM 18／36 位 registered-read 模型再次通过。真实 WAV frame bridge 的默认世代与回绕两次运行通过，每次覆盖 26 次 invalidate、23 次停源、240 次静默取消检查和 2080 次解码检查；过期 quiet publication 与不完整 Gray prefix 两项语义变异均被拒绝。SDC 回归覆盖缺失指令、非法 payload setup 例外以及所有新增同步后级／settled 级的 setup／hold 例外。

局部必要 SDC 指令计数为 M=20、W=16。routed 严格 named-port 词法检查覆盖新增 APB／Delay 实际层级；重复端口或歧义消费者失败。审计绑定维护源及 frozen APB 输入身份，保留前后稳定性与集成来源尚未完整封存的区分。下一候选需重新 prepare、综合、P&R、完整 setup／hold／CDC／reset 验证及实板声画验收；本报告不预记资源或时序收益，不改变旧候选整体失败状态，也未执行 SRAM／Flash 操作。

同一 `runtime_profile` 变更还接入振荡器 expression provenance 的 import、版本化依赖和 prepare 证据返回，局部优化与回归见 [独立报告](DUAL138K_EXPRESSION_PREFIX_20261031.md)。PLL 工具在本阶段保持冻结。
