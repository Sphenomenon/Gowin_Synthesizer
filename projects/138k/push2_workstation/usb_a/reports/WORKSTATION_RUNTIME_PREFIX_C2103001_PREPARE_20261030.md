# Prefix 候选 C2103001 物理准备（2026-10-30）

已完成独立准备与父级复现，启动资源／时序探索 P&R。物理身份 `custom138k-r00-prefix-no-local-panel-nominal-experiment-C2103001`、新 UserCode `0xC2103001`；实际源仍为固定 `c7d66b419868f7f4`／VG `8c5d1e5a…`，不把后续 metadata prepare 或 Chorus 修订回填进去。物理 manifest SHA256 为 `98a5f5fac4b88efab35d8522dd5199ed5fc7da07fac5107b139ce230fe19aba5`。

父级核验 13 份控制 seal 文件及 1,517 份物理准备输入，重跑实际／来源／深层评审依赖／路径／UserCode／验收标记共 100 项负控，全部按预期拒绝。593 staged、269 enabled、四项综合输出、45 项维护依赖和 15 份 root 交付文件一致；两个独立评审的 81＋656 与九＋1,473 完整闭包均复制并核验。父级 verifier 只用两个精确锚点固定原控制目录、把自身结果写到新目录，不覆盖已封存证据。

place1／route0、禁止资源复制、timing-driven 和 hold correction 均保持。Tcl 相对 FF 只改变 UserCode，CST 与 SDC 字节相同，名义时钟及 `paired-nextq-v2` 不放宽；没有新增区域约束或删除功能。通用旧 launcher 首次因 manifest 的 candidate 字段层级不同在调用 EDA 前拒绝；独立精确适配读取已封存的 `source.candidate_identity` 后启动，未更改物理输入。实际运行持有 `/private/tmp/gw138k-build.lock`，避免并发 EDA。

本检查点仅记录已启动状态，结果另行封存。运行开始后不再使用要求“目录中无任何实现产物”的 prelaunch verifier；完成态需重新核验 manifest、全部输入、日志和输出，不能把新文件出现误判成准备漂移。已知完整 CDC／reset／PLL／routed STA 与功能门禁仍未通过；本阶段无板卡、SRAM 或 Flash 操作。参数、证据哈希与启动快照见[机器记录](workstation_task_20261030/runtime_prefix_C2103001_prepare.json)。
