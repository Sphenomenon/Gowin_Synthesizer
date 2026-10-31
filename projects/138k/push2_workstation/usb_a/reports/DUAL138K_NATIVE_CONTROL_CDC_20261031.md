# 双 138K DEMO：TF 控制邮箱与 PC 健康状态，2026-10-31

在 `ec223df` 的局部邮箱/RAM 证明之后，本阶段补 M7 实际时序报告中仍缺约束的两个边界。生产输入于 **19:00:44 CST** 冻结，未修改 RTL、时钟、复位、音频调度或协议格式。

`u_tf_audio/held_control[35:0]` 在 50 MHz 域保存 generation、rate、active、run、busy。实际 VG 和 routed VO 均证明：只有返回 ACK 相等且完整 36 位 desired 不同时才接受；payload 与 request 同边沿更新；接收方经过两级 request_sync 和注册 control_capture，使用同一 CE 捕获 36 位并更新 ACK。BDD 校验全部 36 对比较位和精确 next-Q，所有远端消费者恰为 36 个 compute_control/D，其余反馈均在 50 MHz 域。

该数据路径新增 **13.020 ns 最大飞行界限**，仅免除其异步 hold 检查。既有 request/ACK 首级例外和后级 2 ns 界限保留；第二级及 control_capture 的 setup/hold 不切除。W 已退出 TF owner，角色适配继续退休这些约束。

PC 的两条路径分别为 `pc_framing_sticky/Q → pc_health_meta_0/D → pc_health_sync_0/D` 和 `pc_drop_seen_50/Q → pc_health_meta_1/D → pc_health_sync_1/D`。新增例外精确限定 source Q 到对应首级 D，后级继续 2 ns 约束。实际网表还证明 drop counter 的完整 32 位 OR 在 50 MHz 域先注册，首级始终使能且只驱动第二级。

`workstation_native_protocol_audit.py` 升为 `native-demo-mailbox-structure-v2`。M 的实际 SDC 必须包含 12 条本地 RAM/loss/TF/PC 指令，W 为 10 条；缺失、重复、错误源/目标，以及对后级 setup/hold 的例外均失败。before/after 审计代码、依赖、维护契约、网表和可选 SDC 稳定性封存继续保留。

| 实际快照 | 新边界结果 | 新负控与 SDC 测试 |
|---|---|---|
| M7 VG | TF36、PC2 及已有边界通过 | 12/12，通过 11 项网表破坏拒绝 |
| M7 routed VO | 同上，含完整远端消费者闭包 | 12/12，通过 11 项网表破坏拒绝 |
| W5 VG | PC2 通过，TF owner 确认不存在 | 4/4 通过；8 项 TF 专属测试按退出策略跳过 |
| W6 封存 VG + 实际 SDC | v2 全部局部结构和 10 条必要 SDC 通过；source/netlist/SDC seal 均通过 | 19 项通过、9 项按角色/阶段跳过，15 项网表破坏全部拒绝 |
| M8 封存 VG + 实际 SDC | v2 全部局部结构和 12 条必要 SDC 通过；source/netlist/SDC seal 均通过 | 27 项通过、1 项按阶段跳过，23 项网表破坏全部拒绝 |

SDC 子测试另覆盖 M=22、W=17 个删除或非法后级例外场景；既有配置选择回归通过。正向结果、散列、source_seal 和负控清单见配套 `DUAL138K_NATIVE_CONTROL_CDC_20261031.json`。这些是实际网表结构及新约束策略的离线验证，**尚未把新约束安装到新的 M routed 结果中验收**；W6 全量综合 exit 0 后，已核对封存新 VG 及实际 `constraints/custom_138k.sdc`，两者局部 v2 验证通过；P&R 和整机接受仍分开进行。M8 prepare 身份为 `f11f1756db68044a`，全量综合 exit 0 后，已核对新 VG 和实际 SDC，局部 v2 验证通过。其 28 项完整回归中 27 项通过、1 项仅适用于 routed RAM 拆分的测试跳过；官方 18/36 位 registered RAM 模型测试通过。

M7 的旧实际 SDC 不包含本阶段新增指令，因此 v2 CLI 携带旧 SDC 时应失败。前阶段 v1 安装证明保留在原报告，不因维护源码更新而重写。整机 CDC、PLL、reset、完整时序、真实声画和硬件部署继续未接受，本阶段不预记资源或时序收益。
