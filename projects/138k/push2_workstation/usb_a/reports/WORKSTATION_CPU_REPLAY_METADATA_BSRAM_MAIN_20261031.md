# CPU 重放元数据 BSRAM 主树复验

固定作者 `681bf5e` 导入为主树 `2224e1a`。32 槽、每槽 77 bit 的重放元数据
采用同步预取，预期映射三块 `workstation_sdp`，保留原容量、每槽一拍扫描和过期边界。
RAM 不复位，有效位继续隔离旧会话；未改变业务 owner 或共享邮箱 ABI。

主树重新执行真实 parent／new parser 对照：行为模型和官方 GW5A SDPB 各通过
103,617 次半周期检查、11,680 个回复字节，全部 32 槽命中。
四个编译 RTL mutant 被拒绝，覆盖旧预取地址、无效槽、时间截位和长度移位。
完整 C／APB／parser／raw-DDR 路径继续通过 1,701 个检查、15 个 C mutant，
136 条 WIRE／BLOCK 消息与锁定 legacy 参考一致；实际仿真时钟为 20 ns／14 ns。
accepted 来源 17 项和新 business prepare 的八项回归通过。

只刷新 business profile 中两份已核对 CPU-owner RTL 的来源哈希。
新候选 `1a806f236eaef843` 为 614 staged／272 enabled；相对 `b552eccb`，
仅两份实际 RTL 及其两份复制源改变。其余 native 配置、accepted 和 frozen baseline 保留。
before／after 的同功能组件综合输入已从主树重新生成和展开，尚未调用 EDA。

本批没有测得 LUT／CLS 收益；三块 SDPB 仍是预期映射，综合、物理 BSRAM、
CDC／routed 时序和整机功能需分别核验，不能只按 2464 bit 容量预记节省。
父级包 `~/.cache/gw138k-task-20261030/cpu-replay-metadata-main-parent-v1` 保存
462 份源码快照、930 个固定外部文件，seal
`10113f9f67f68231d2bb12eeb83a756943c2870fd427da82c2b154688554ceb2`。
机器索引见 [cpu_replay_metadata_bsram_main.json](workstation_task_20261030/cpu_replay_metadata_bsram_main.json)。
没有板卡、SRAM 或 Flash 操作；回退保留原 distributed 参数路径并重建原固定 profile。
