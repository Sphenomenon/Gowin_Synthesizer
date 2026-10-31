# HCI readiness 局部 drift 落地与完整源码回归

已将独立 review 的 HCI action drift 提案精确落到维护 host RX owner。仅 `rx_ready_o`、`release_ready_o`、`return_can_send_o` 三个既有消费者采用不含 disconnect 例外的局部 drift；原 full owner_drift、断开处理和所有 sequential 语句逐字保留。新源码的完整行为／四态回归通过，本报告没有新的综合、P&R、资源收益或板测结论。

## 变更与来源

维护 host SHA256 `20f45bf00fbb23ca09512d35f4bfff4273e3d4d865d56fc03bdb2e89a342b13f`，与核准 cache 提案相同。原 host 为 `271e3d701eb8f84e238ac9ccf3114c2669ef44e09d56407fc22afb1e5e9785ea`；新维护 runner 在运行前必须通过精确逆变换恢复该固定 SHA。逆变换任一锚点或其他任一字节漂移都会拒绝，完整原 sequential 源码因此没有被额外改写。native transport 保持 `02dc68255bad7182d6b1616f3809c53b672887726fbb69790a58271183700787`；没有新接口或改变 native/table 协议。

三个输出原已显式要求 `!disconnect_valid_i`。binary 0 时新旧 drift 相等，binary 1 时三个输出已被断开否决。保留的 `case` 在 X/Z 输入时退回原 full drift，维持源仿真的 procedural-if 行为。局部 fence 用 `syn_keep` 标注；没有新增时序状态或周期。原 close_generation 的零默认、last-match／duplicate-handle 优先级和存储比较不变。

新增 `sim/run_workstation_hci_action_drift.py` 为独立维护验证入口；参考源由精确逆变换生成，只作为外部验证工件，不依赖私有历史 staging。既有 `sim/run_workstation_hci_identity_compare.py` 的 W10 固定参考和 hash 保留，其 exact-source 审查显式加入这一核准变换及逆变换，且绑定新 helper 的 SHA。`twin_bench` 增加显式参考文件参数，专用 proof 不需 monkeypatch 参考解析。

## 验证结果

全部三条验证入口退出 0，完整身份与日志见[机器报告](dual138k_hci_action_drift_20261101.json)。

- 新 runner：以实际源 base／full exception／case／三个 consumer 的表达式为约束，1／2／16 个 handle slot 的 binary 与四态 cofactor 共六项 SMT 均 UNSAT，无 reachable-state 假设；去掉 X/Z fallback 的 symbolic 负控得到 SAT。
- 实际完整 owner 对精确 pre-action 源双实例：17,674 clocks、33 public outputs、39 original states 相符；独立 ledger／lease 模型完成 160,228 checks、12 scenarios、10,000 random steps、3,146 received、2,822 returned。
- 实际完整新旧模块内执行 147,464 个四态组合探针。其他 readiness gate 被独立强制打开以暴露所改锥，存储表在停止时钟时直接赋值。删除 fallback、丢 outstanding guard、删除 return disconnect veto 三个实际模块 mutant 全因公开 readiness 不同被拒绝；额外字节与 keep 漂移两项 source 逆审查负控也被拒绝。这是有限四态组合验证，未称为全 owner temporal formal 证明。
- W10 完整 identity 回归：host 再次比较 17,674 clocks／33 outputs／39 states；native 比较 6,545 clocks／33 outputs／2,716 states；12／16／32-bit 的 identity／分组关系证明和既有分组四态检查通过，11 项负控全部拒绝。未改 W10 fixture。
- 完整 native default 回归：包含共享 owner、host RX、bootstrap、native 整合及 UART8E1／H5。host 原 13 项行为 mutant 与 8 项无效参数检查通过；native 268 checks、11 项行为 mutant 通过。真实 UART 线级仿真核对 253 patch bytes、4 bootstrap、10 host returns、3 notifications 和 reconnect=1。这里的 physical UART 指 RTL wire simulation，未连接实板。
- host 严格 Verilator `-Wall` 无 waiver 通过；native 沿用既有 unused diagnostics／empty output pin 两项 lint 例外，没有放宽 width、latch、multidriver 或 timing 检查。

证据位于外部 `hci-action-drift-maintained-v1`、`hci-action-drift-identity-v1`、`hci-action-drift-native-v1` 三目录，索引为 `/Users/sphenicidition/.cache/gw138k-dual-20261031/hci-action-drift-sealed-v1.json`。本次维护回归没有失败后更换 oracle 的尝试；此前 cache 提案的模拟器／文件名失败记录仍在其原封存目录。

## 下一候选门禁

W13 的旧冻结输入和网表证据保持独立；此变更需要新的候选身份。下一完整 VG 必须检查 kept action fence 仍被三个真实 permission consumer 使用，ready／return 的实际锥不再依赖 selected close_generation／disconnect exception，而实际 full drift 与断开路径保留原行为。随后以真实资源、全量 P&R／STA 和相应实板声画／BLE 证据判断；源码 proof 不能预记收益。

本子任务没有改 profile 锁、task2、native transport 或板卡状态，没有 commit／push、SRAM 或 Flash 操作。主线程负责新候选冻结、阶段提交和后续硬件流程。
