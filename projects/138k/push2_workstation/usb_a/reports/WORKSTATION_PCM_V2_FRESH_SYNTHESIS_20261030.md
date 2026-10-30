# PCM v2 新综合及安装核验（2026-10-30）

候选 `custom138k-workstation-r00-no-local-panel-v1-7d1c3b9b464ff722` 综合返回 0，耗时 364.268 秒；584 项输入、四项输出与完整工具日志重新封存一致，无 AG 组合环诊断。综合资源为 Logic 103,147、Register 58,602、BSRAM 253；这不是物理占用，不从旧 FE 的 288 个物理 BSRAM 推导资源变化。

在该新封存 VG／SDC 上，PCM 父级 18 项／109 负控通过。`paired-nextq-v2` 已实际安装，四组 payload 的静态约束覆盖均无遗漏，审计身份为 `runtime-pcm-context-source-v2-4333f5e7fdfa89b2`。独立 clock topology 与 Gray/media partial CDC 安装检查也通过各自局部门禁。全部输入／输出及审计证据见 [runtime_pcm_v2_fresh_synthesis.json](workstation_task_20261030/runtime_pcm_v2_fresh_synthesis.json)。

这里只完成静态端点解析与源码行为边界核验；Gowin 查询、routed propagation、完整 CDC／reset／RAM 数据弧／PLL 与所有 STA 类别未接受。本候选尚未 P&R，没有位流或硬件操作。后续物理资源检查将使用实际接入 BLE DDR 的新候选，避免从未改变存储结构的本轮推测 BSRAM 收益。

该综合仍使用旧 `2323b54f…` 封存桥，不包含随后提交的本地同步释放修复，也不包含 BLE raw store／子区分配／authority／adapter。后续源码不得继承此网表或安装接受；回退和复现使用本候选独立复制及对应过程文件，不编辑历史 stage。
