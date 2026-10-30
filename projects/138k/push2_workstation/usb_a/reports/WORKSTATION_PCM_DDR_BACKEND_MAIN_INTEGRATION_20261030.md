# R00：未选择 PCM DDR 组件进入主线（2026-10-30）

主线已导入默认未选择的 PCM DDR 后端及同拍命令修正。父级在实际主目录重新执行全部 24 项，输入哈希保持、严格 lint 零 warning；独立 reviewer 也重新执行 24 项，并用原最小刺激确认 clear/create、release/acquire 两个缺陷已修复。组件身份为 `native-pcm-ddr-backend-v2-d92df483e5ebf74b`，具体机制、56 项同拍检查及限制见[优先级修订](WORKSTATION_PCM_DDR_BACKEND_COMMAND_PRIORITY_20261030.md)。原首阶段证据保留，不能代表修订后源码。

本批仅预留地址图 `0x30500000..0x305fffff`，组件默认使用首 64 KiB。既有分配保持；没有新增生产 owner8、扩展四位 owner tag、接入最终 PCM CDC，或用真实音频替换 BLE 现有后备。竞争 fixture 借用 owner5 并替代 NN，不能证明 NN 与录音同时工作或最坏仲裁时限。没有长录音、物理净资源收益或整机录音能力声明，R00/R01/R02 方框保持未完成。

主 profile 文档和锁同步记录这一未选择组件，revision 仍为 5。新 prepare 身份：

```text
candidate: custom138k-workstation-v1-60f1c843ad79aa6e
candidate_input_sha256: 60f1c843ad79aa6e5a2ca53918d75fd6703697c3e4b65b40d6a4ab8749c46c8c
profile_sha256: 1cd28fabcfda5c5170667a434cc52c14b2cb0ffcbb57e2a4dee1794ccf768f14
```

新 prepare 的 profile 18 项、来源 12 项全部通过，无 skip；父级另跑 accepted sources 10 项通过。来源为 313 项显式锁、735 项快照、570 项 staged、259 项启用；预处理验证 256 个 HDL 编译单元、288 个 module、2 个 package，无重复 owner。相比已综合的 `f1be50e853d3700a`，快照新增未选择的后端，地址图和 profile 文档/配置发生来源变化；**全部 570 项 staged 文件的字节哈希完全相同**。两个 constraints 的 enabled 记录仅因文档来源哈希更新而变化，实际 CST/SDC 字节不变。新地址宏未进入当前编译输入，因此不能声称当前整机已经使用新增存储区。

新候选只完成 prepare 和上述离线来源验证。即使 staged 相同，也没有转移旧候选的综合、局部 CDC、P&R、硬件或部署接受；后续物理资源试验继续明确绑定封存的 f1be VG。机器记录见[主线父级证据](workstation_task_20261030/pcm_ddr_backend_main_integration.json)，其中包含父级组件完整结果、独立 review、两个来源回归日志、prepare 差异及 cache 原件哈希。

下一步需要给生产仲裁显式分配 owner、连接原子 PCM CDC 和对象业务，再比较同配置 P&R 的 FIFO/预取成本与原 32 块 PCM BSRAM，并完成双率真实录音/下载验收。本批未运行新增综合/P&R/JTAG，没有位流、SRAM 或 Flash 操作。回滚应同时撤回后端/契约/测试、地址预留、profile 文档及相应锁；原始历史证据继续保留。
