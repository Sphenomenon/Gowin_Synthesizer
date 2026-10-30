# 222fb761 原生 Delay FIFO 父级复验（2026-10-31）

本阶段只审查固定显示请求候选 `222fb761448fb6c0` 的实际综合网表。编译源码仍为 `9bc8fc5`，VG `f621fcbe…`、process `2b9a71d6…`；没有改变 profile、SDC、CST 或业务 RTL，没有运行新 EDA 或操作板卡。

两组 65-bit×512 原生 Delay FIFO 各映射四块 SDPX9B，合计八块，选定 FIFO 的 SSRAM 为零。实际 DI 位映射、64 位写格式化真值、完整输出头扇出、pop 后有效 bit0 与 40 条 Gray 两级同步链通过新网表复验。这里的八块是所选 FIFO 的综合 primitive 映射，不是完整候选的物理资源结果。

原审查任务实际完成 410 个图负控及 66 个载荷负控，全部拒绝；独立审查核对完整 case 内容与原方法的 canonical multiset，并重放正向映射、全部格式化真值和九个定向负控。九项包括两处 RAM 位宽、两组协调 DI bank 交换、三处格式化边界位，以及两处首级 Gray Q 到真实异域 FF CE 的新增消费者。修改后的图字段和 consumer index 均恢复；旧 18ed scope 仍拒绝新候选。八份 helper 仅有四处明确身份／路径适配，算法及旧 scope 保持。

父级完整重放独立 `verify.py`，正向和九个定向负控通过；未重复运行全部 476 个负控，原执行日志及每个 case 均有哈希绑定。初次整数／JSON 字符串键排序比较失败与修正证据保留；未删除字段、数组项或覆盖旧结果。独立 seal 为 `b8a4cc2a…`，24 文件／4,101 输入；父级另冻结一份 root 来源并核对其与编译 commit 的 Git blob 一致，seal 为 `6f23a756…`，五文件／4,125 外部输入。父级最终 seal 校验只重算哈希，其与前述语义重放分列。完整身份见[机器记录](workstation_task_20261030/display_load_native_fifo_parent.json)。

本阶段没有重新证明所有 Gray 生产端的 D／CE 有效 next-Q 或 DSP feedback 算术；完整 CDC／reset、RAM 物理数据弧、PLL、routed STA、物理资源与硬件验收仍未通过。没有位流、SRAM 或 Flash 部署，不据此勾选整机任务。公共 shared／TF-counter 的新范围继续独立检查，之后再绑定新的物理实验。
