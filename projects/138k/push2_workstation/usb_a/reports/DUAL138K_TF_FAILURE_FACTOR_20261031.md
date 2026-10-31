# 双 138K：TF 即时失败判定的等价因子化

2026-10-31。M11 `D2103115` 的真实 50 MHz 同域建立时序报告前 100 条路径有 11 条负裕量，最差 −0.766 ns，从 `stream_epoch_o[22]` 到 TF reader 的 `probe_resume_sector[3]/CE`，数据延迟 20.609 ns。实际组合锥串接 32 位 epoch 比较、诊断优先编码、非零判断、即时 invalidate 和 reader 准入。这是具体物理路径，报告条数上限不代表全设计违例总数。

维护源 `rtl/tf_audio/workstation_tf_runtime_service.sv` 现在将完整 epoch 比较写为 XOR 归约，将准入使用的“存在失败”条件与原诊断优先编码并行计算。`new_failure` 保留组合过程的默认 0，再检查原有 physical 条件和并行失败谓词；不增加寄存器或延迟。CARD／DDR／FORMAT／TRANSPORT／CONTEXT／EPOCH／RATE 原诊断优先级、即时 stop／cancel／invalidate、source_quiesce 寄存器与时钟保持不变。

## 完整源码与功能证据

旧 fixture 是 M11 实际消费的完整 service，SHA256 `c42dc0bbe4919adf86275388239f52ccf63d6670b30c2bdf362ebea5bcb0b483`；新维护源 SHA256 `90618bda686a82e9e4d61f4ef94feac72efa50723322acfbadb48c025421765f`。测试反向撤销且仅撤销这次组合变化后，完整文件必须逐字节恢复旧 fixture。

- 99 个自由比特的全域 Z3 证明为 UNSAT，涵盖全部 state 编码、完整 32 位 epoch 对、20 位文件采样率和上下文状态，不添加可达性假设。
- 原完整 service 仅改模块名，与新 service 双实例运行实际 FIFO／DMA／WAV／frame bridge。直接／缓冲 DDR 命令与分离／共同复位四种组合共比较 1,069,069 个三时钟上升沿；全部 50 个公共输出、24 组内部状态，以及 error_now／new_failure／invalidate／停止／准入控制一致。22 处既有路径故障注入同时施加于两边，不屏蔽初始化边沿。
- 独立有向检查遍历全部 32 个单比特 epoch 差异。四个真实源码破坏均被对应断言拒绝：漏掉 epoch bit22、移除 physical 条件、移除即时 stop veto、将 CARD 优先诊断改为 DDR。
- 最终源完整 service／clear／stop 既有回归通过，包含源时钟停高／停低、在途 DDR、末次清空与 mailbox ACK、重复停止、停止失败／合并，以及原有 ACK 绕过和组合环负控。
- 独立 reviewer 另外运行 physical 与七个失败条件的 0／1／X 共 6,561 组合，以及四位两个操作数全部 0／1／X／Z 共 65,536 对，分别确认过程式默认 0 和 `!=`／XOR 归约的四态语义。它补充完整 owner 对照，不声称穷举完整 32 位 owner 的四态空间。

首次纯连续表达式在 5 ns 首次 memory 边沿发现未知态差异；source 首次复位边沿为 10 ns，原过程式诊断默认 0，而连续 physical AND 将未初始化 state 的 X 传到 new_failure。失败目录和日志保留为 `tf-failure-factor-equivalence-v1`。最终正式源恢复默认 0 的过程式语义后，v2／v3 所有初始化和正常边沿均比较一致，没有放宽公共输出、stop 或 invalidate 断言。

## 原生边界审计器身份

`tools/workstation_native_protocol_audit.py` 仅将 `REVIEWED_BOUNDARY_SOURCES` 中的 TF service pin 从旧 SHA 更新至上述新 SHA。原审计器 SHA256 `49af05fd28776d3cae3ce64cb610df18462780325d4d91c5365e702e8d559658`，新 SHA256 `424e515ccb1c97e18059661bc3f765d3d460eb41454284a24665f325529ebb18`；其余 pins、结构检查和负控未改。

完整 `invalidate` 文本与 source_quiesce 的声明／复位／采样过程分别逐字节相等；两个 delay heartbeat 源及 frame bridge 的 pins 均未变化，当前 source_identity 的 14 项通过。使用新外部审计器重跑原 M11 实际 VG／VO：各 54 tests，VG 50 通过／4 跳过／45 个实际对象负控，VO 51 通过／3 跳过／46 个负控；vendor 18／36 bit RAM 的 1,024 次忙时写和 512 次停止读时钟检查通过。历史 M11 far CLI 的旧 pin 拒绝日志保留，未改写成通过。

机器证据：[dual138k_tf_failure_factor_20261031.json](dual138k_tf_failure_factor_20261031.json)，SHA256 `ac8abbbef29abc2b12c135ff44e3242392ee26d6f5f96f0e1d91d0a08da619c5`。最终对照在 `~/.cache/gw138k-dual-20261031/tf-failure-factor-equivalence-v3/`，完整停止回归在 `tf-failure-factor-stop-v2/`，独立四态审查在 `tf-failure-factor-independent-review-v1/`；原日志和输入身份均由机器证据引用。

## 后续物理验证

本阶段确认源码行为等价与原生边界审计器的单一源 pin 修订。SD／FAT 使用既有字节边界 endpoint 模型，DDR 使用有序模型；本阶段没有新综合／P&R、资源或时序收益、SRAM／Flash 或硬件验收。原 M11 VG／VO 回归验证其原网表，不代表新源物理实现通过。新 M 候选必须锁定上述 service 和新审计器身份，重新全量综合、P&R、核对真正的 clk50／音频／DDR／CDC 和声画功能；不追改 M11 原输入或证据。
