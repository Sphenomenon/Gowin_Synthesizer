# 已选 shared CDC：维护工具与父级复验（2026-10-30）

此前 cache 中对实际 no-CNN shared88 的审查已移入维护工具 `tools/workstation_runtime_shared_cdc.py`。默认仍调用原 generic157 检查器；必须显式指定 `runtime-no-cnn-v1` 才审核已准备的 no-CNN 配置。完整 configuration、禁用识别策略及历史来源身份不匹配时拒绝，R00 明确不在该 precision scope 内，不能借此接受新增录音 CDC。

父级在 `525ffff10d622031` 的真实 VG `37c811ffcc0a0ae2ce55aa66550c95bec8bb04cc7fc92aa69c1cc7c17d6f3f4f` 上完成 **8项测试，无跳过**。先验证原对象正例，再逐项要求14个结构负控命中特定故障；另拒绝错误 USB defaults 布尔函数和在重算 retirement 元数据后将20ns放宽到200ns。571项原始输入和VG前后重核；14个主负控为内存对象变异，不改写原VG。

新审计身份为 `selected-shared-cdc-source-v1-7f69121e007e1bf1`。精确安装链保持 generic157→runtime105→no-CNN88，覆盖43首级位、8组182个Gray首级位、14组1308个保持负载位及其完整消费者；89个唯一query逐成员处理。13个加密DDR shared query继续deferred，110个reset／primitive pin仅列清单。历史profile SHA与当前profile SHA分别记录，完整configuration相等不冒充当前root字节等价。

三份 profile 增加三份工具／测试／说明来源锁，计341项。父级 fresh prepare 为 R00 `6f71fbdc2aeedf51`、保留识别 `a008efb3e20d8dd6`、no-CNN `9dc5e2bbced918ca`，各12项来源回归通过，583／570／571项staged与各自前序相同。accepted来源17项通过，generic checker原字节未改。父级将策略负控中的录音示例名称替换为真实R00名称，其余三文件交付内容保持。

这只是额外的来源结构门禁。Gray序列、负载保持握手、状态毛刺／脉宽、全部reset语义、DDR内部对象、工具时query、两种物理时钟模式与routed传播／偏斜仍未接受。本阶段没有新增EDA或板卡操作，也没有继承FC物理结果。命令、全部哈希及缺口见[父级机器记录](workstation_task_20261030/runtime_shared_cdc_parent_integration.json)；使用方法见[工具说明](../tools/WORKSTATION_RUNTIME_SHARED_CDC.md)。
