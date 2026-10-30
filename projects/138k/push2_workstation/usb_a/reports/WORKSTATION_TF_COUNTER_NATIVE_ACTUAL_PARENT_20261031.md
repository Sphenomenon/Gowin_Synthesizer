# 实际 18ed TF／counter 父级复核（2026-10-31）

新只读范围 `runtime-r00-no-local-panel-pitch-delay-tf-counter-v1` 精确绑定 18ed／VG `c9f88c71…`、原 process 和 599 staged／269 enabled。父级重哈独立 53 文件／619 外部输入，重放实际图正向审计、完整消费者闭包、BDD 与厂商 ALU 真值核验；五项 scope 负控重新执行且完整结果一致。独立 276 个实际图突变全部拒绝，父级验证其不可变封存与报告，本轮没有再次运行这 276 项；两种验证范围分别登记，不把报告数量写成父级执行数量。

四组计数器均核对 32 个注册 Gray 生产者、64 个接收 FF、CLEAR／CE／INIT／时钟及本地 D／CE 顺序前沿。三个实际 full32 输出逐位证明 suffix-XOR，录音计数器的 full32 输出明确为 mapped-absent，只接受真实存活后缀的有限结论。缺失 required full32、伪造录音 full32 和旧 CLI 错 scope 的负例均拒绝；没有以 parser 异常代替部分接受。display 实际注册 Gray 编码与本地公共断言关系也通过，不能据此接受上游／全局 reset。

TF 七组 Q 直连加一组 memory-open 补集回程、36-bit source／compute held 有效 next-Q、request／ACK／capture 与实际取消门函数通过。旧 c7 的取消 LUT `n1033_s1` 在新网表消失，初次拒绝保留；新声明只绑定实际 `n1038_s1` 及完整布尔函数，没有改旧 helper 或接受任意同名门。实际 SDPB CLKA、DSP 各 CLK、首级所有 D／CE 消费者和 opaque endpoint 均进入闭包。16 个既有厂商 ALU 模型实测真值与当前 BDD 重核一致，本轮没有新 EDA 仿真。

原始尝试、精确适配和 SHA 见[机器记录](workstation_task_20261030/tf_counter_native_actual_parent.json)。source_seen 别名、generation 传输、held payload flight/setup/hold、完整 CDC／reset／RAM／PLL／routed STA、资源与实板仍未接受。没有安装新 SDC、运行 EDA 或操作板卡、SRAM、Flash。
