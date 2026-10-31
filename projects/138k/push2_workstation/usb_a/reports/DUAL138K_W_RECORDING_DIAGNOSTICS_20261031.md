# W-DEMO：两个无消费者录音诊断端点的精确退出

2026-10-31。W6 完整综合已结束，但原严格审计拒绝四个未解析引脚：`recording_ble_store/failure_code_o_*_s*/D`、`/CE` 与 `recording_ble_store/start_done_o_s*/D`、`/CE`。此前 HCI 会话键问题已修复；本问题不是其继续恒零，也未把失败 W6 原 SDC／网表改成通过。

真实维护源码的 `workstation_ble_record_data_engine` 对 `raw_failure_code_i`、`raw_start_done_i` 各只有 input 声明，没有任何逻辑读取。上层 wrapper 只透传这两个诊断值，实际 VG 已将其全部删除，没有寄存器或 `raw_failure`／`raw_start_done` 别名。正式录音完成由接受／提交帧数、drained、实际 fault，以及 clear／fetch／cache 回执判断；没有把未消费的 start pulse 当成存储完成。

新 `independent_demo_endpoint_adaptation_v3` 仅对 W 退出这两个无消费者 diagnostic selector，保留混合查询的全部其他端点、原 10.000 ns max delay 和 hold 例外。旧 v1／v2 策略按各自冻结转换原样重放，M 及其他 accepted 配置不增加这些退休规则。

门禁不仅检查选择器不存在，还从冻结 engine 源码证明接口未读取，并逐项核对实际 50 MHz 状态驱动及真实 engine LUT／ALU 消费者：6 个 fault／完成／cache 状态与全部 32 个 committed-frame 位，共 38 个实际源。若未来源码开始读取这两个诊断值、出现实际别名、丢失真实驱动或 consumer，门禁失败。

[真实 W6 源码／VG 证据](dual138k_w6_recording_diagnostic_20261031.json) 由 `sim/run_workstation_w_recording_diagnostic_audit.py` 生成。正例通过；新增消费者、删除真实 fault 驱动、错误 committed 时钟、绕过 committed bit0 所有消费者，以及恢复实际 diagnostic alias 五个负控均精确拒绝。26 项 DEMO policy／audit／Classic CDC 回归通过，覆盖旧 v2 重放和只移除指定诊断的混合查询。

W6 驱动 stdout 没有重定向。用于审计的 `synthesis.log` 是 Gowin 自身生成的 `workstation/Prj1/impl/gwsynthesis/custom_138k_integration.log` 逐字节副本，SHA256 为 `8d30b180ca3d540ecfb275b9256176d824e9fb73d066ea7a439cf1068105b556`；原生日志有唯一完成标记且无 ERROR，原文件保留。它不是重新构造的 stdout。候选内 `synthesis_log_provenance.json` 明确记录来源、路径、长度和相同 hash。

新候选须重新 prepare 后使用新身份，按全部非 SDC 输入的逐字节比较决定能否复用 W6 综合；不能仅凭预期宣称只改约束。实际 HDL 不同时必须重新全综合。此阶段证明源接口和实际网表闭包，不表示 routed 时序、真实 D／25K 声画或录音下载板测通过，也不计任何 W5 错误裁剪造成的资源收益。
