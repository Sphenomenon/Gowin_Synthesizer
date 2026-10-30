# C03 邮箱字地址译码主树复验

针对 [C04 实测新增成本](WORKSTATION_AE350_BUSINESS_C04_FIRST_BATCH_20261031.md)，导入作者 `d8e1105ddb93532ca44d44a157cef31fcd9e7f10` 的两份原字节修改，主树提交 `032eec2`。请求／结果读取和结果暂存写入使用固定字地址 case，消除 12-bit 地址减法、乘八及动态宽选位。存储容量、160-bit 完整身份、单周期 ready、结果尾清零、取消及超时契约保持。

父级重跑原 mailbox 三项回归，并以作者封存的旧实现逐半周期对照当前 RTL：34,196 次完整输出比较、全部 4,096 个读地址、15,302 次 bench checks 通过。实际 C/APB/parser/raw-DDR 联合回归的 35 条报文／DATA 与旧 owner 逐字一致。该轮仍用首批 fixture，仅作功能证据；ns/ps 时间比例修正与扩展下载情形由第二批复验。prepared/source 八项、accepted sources 十七项、六份 profile 来源锁加载均通过。

仅显式业务 profile 引用了该邮箱，故只更新这一份 source hash；其他配置未增加业务 owner。实际新 prepare 为 `custom138k-workstation-ae350-business-v1-09ae2f713f688bb7`，612 staged／271 enabled，配置 SHA256 `83ebc5df316e9f46e31fe335ac68403f443681815cbf4fd65f5864f25cf09201`。旧固定网表及其资源结果保持原身份，新候选尚待完整综合测量，不能用被移除选位锥的单独统计宣称净收益。

机器记录见 [ae350_mailbox_main_parent.json](workstation_task_20261030/ae350_mailbox_main_parent.json)。父级包 `/Users/sphenicidition/.cache/gw138k-task-20261030/ae350-mailbox-main-parent-v1` 保存实际源码快照和 693 项外部文件引用；seal SHA256 `cf9ba5e0166cd83281111941540223dffd7227aa5fe197d3c3c5c6a41f0dca73`，`verify.py` 可只读复核。无新增 P&R／时序／完整 CDC／实板或部署验收。回退可恢复原邮箱及该 profile hash 后重新准备，不能复用旧候选身份。
