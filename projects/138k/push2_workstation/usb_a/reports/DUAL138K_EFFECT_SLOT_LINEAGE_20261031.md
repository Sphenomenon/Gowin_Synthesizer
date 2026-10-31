# 效果只读空槽接口的可逆来源校验

2026-10-31。M12 首次实际 prepare 被既有 D control 源码身份锁拒绝，原日志保留为 `m-demo-base-v12-prepare.log`。功能回归通过的新增只读接口并未纳入原效果源码的逆还原链；没有跳过该门或修改冻结基线使其通过。

维护工具 `workstation_delay_storage_provenance.py` 新增独立 `restore_effect_sample_slot`：只接受新效果源码 `e9355856…71c50`，按两个唯一锚点逆去只读端口／说明及其 assign，强制恢复旧 `7bd9a9f5…3b826`，随后正向逐字节还原为原新源码。未知来源继续由原身份门拒绝。原 `D_CONTROL_ADAPTATIONS`、D／delay 还原函数、provenance／storage manifest 均未改。

7 项来源校验测试通过，包括完整 native→prepared 链、原父源、逐字节往返，以及源码变异、锚点缺失／重复、无关字节和错误父源负控。条件式 `PreparedClosure` 测试因未提供其环境变量而明确跳过，未称通过；实际 M12b 已从新锁完成 prepare，独立复验全部588项封存输入通过。三项新维护 RTL 在实际编译路径的 SHA 完全匹配：事件模块位于 `src/ae350/`，效果与 TF service 位于各自 `rtl/` 路径。

M12b 新身份 `custom138k-workstation-m-demo-v1-0af82c38b1902d92` 已开始全量综合。此阶段只交付可逆来源链及实际 prepare，综合／物理／硬件状态继续独立记录。[机器证据](dual138k_effect_slot_lineage_20261031.json) SHA256 `ab5b8023065a6b6565cae91a17ff9edcf70c77ad34e1ecf17b5104ddabf9f965`，固定工具、测试、结果、实际消费来源及第一次失败日志。未下载 SRAM 或写 Flash。
