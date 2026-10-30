# c7 TF 控制快照 CDC 父级复验（2026-10-31）

新增只读审计与测试已合入，范围严格为 `runtime-r00-no-local-panel-tf-control-v1`、c7／实际 VG `8c5d1e5a…`。仅新增六个工具／测试／契约文件，没有改生产 RTL、profile、SDC 或旧门禁；新 Chorus 与后续 pitch／FIFO 候选必须重新声明实际端点身份。

父级公开 CLI、10 项测试及 94 项实际 VG 故障注入全部通过。七组注册 Q 直连和一组 memory-open 补集回程逐一核对声明生产者、D／CE／INIT／时钟／完整首级与第二级扇出。完整 D／CE／CLEAR、opaque 原语端口和顶层输出都进入固定端点对象；RAM16SDP4/WRE 关联 CLK，SDPB/CEA 关联 CLKA，DSP 的多位时钟逐位检查。common CLEAR 精确为 `!(reset_n && memory_guard_started)`，不冒称原始 reset_n 或完整复位接受。

36-bit held／compute 快照的有效 next-Q 与 request／ACK／capture 延迟均由 BDD 全输入证明。厂商原始 ALU 模型 16 个真值向量与求值器一致，不支持的模式或 I3 不被当任意逻辑接受。实际存活取消门证明 `compute_control[2] && expected_valid && compute_control[35:4]==tf_expected_generation[31:0]`；它只接受该门，不替代 generation 传输证明。

主仓库重新通过三组源／目的时钟比、停高／停低、共同异步 assertion、未 ACK 数据保持、恢复及最后源沿后取消；三个故障版本分别被真实断言捕获。真实 frame bridge 默认／回卷、buffered／unbuffered runtime CLEAR／STOP、最终 mailbox ACK 及原组合环负控也重新通过。父级核验独立 86 份文件、731 外部依赖，并单独封存自己的回归与输入。证据与 hash 见[机器记录](workstation_task_20261030/tf_control_cdc_parent.json)。

source_seen 与 MIDI release 的别名研究仍未接受。完整 CDC、上游 generation／FIFO／Gray、held payload 飞行与 setup/hold、复位 recovery/removal／脉宽、selected mode 物理时序、PLL 和硬件都未关闭；本阶段未安装约束、未运行 EDA、未操作板卡或部署。
