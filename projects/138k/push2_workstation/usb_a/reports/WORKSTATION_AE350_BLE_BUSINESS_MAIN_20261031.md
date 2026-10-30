# C01/C03 第一批主树独立复验

主树按原字节导入作者 `0e12cfd6d1653fc721c4198e1f1c8325cf8b1f43` 的 34 份源码／配置／证据，导入提交 `72f5d71`。显式 `custom138k-workstation-ae350-business-v1` 才选择真实 C 任务表、ID 分配与录音／传输开关命令；旧 `ble_recording.v` 从该候选的暂存树及编译列表移除。下载 READ／ACK／恢复／超时策略仍为下一批，外部协议、原实时采集／CRC／Rice 与独立 R00 不改。职责和不确定提交处理见[第一批报告](WORKSTATION_AE350_BLE_BUSINESS_FIRST_BATCH_20261031.md)。

父级在主树重新运行实际 C/APB/parser/raw-DDR 联合仿真，794 checks、35 条完整 response/block 与旧 RTL 逐字一致，六个真实 C 行为突变均被拒绝。这次使用最终 data engine，独立于先前中间版本的父级复跑。实际 prepared/source 八项、runtime sources 十二项、ProfileSources 六项、accepted sources 十七项、默认固件十项、callback 栈四项通过。作者固定包另经 `verify_seal.py` 重新校验，990 项产物／34 份版本源码保持。

实际主树 prepare／verify 为 `custom138k-workstation-ae350-business-v1-8f615119768bfbf2`，配置 SHA256 `ed438e9743cea2e9c653248657eec5699567202d45db7bf7c6f3a541045400a3`；612 staged、271 enabled，268 编译单元／300 modules／2 packages。与作者 `9c0f652c977f2323` 比较仅 USB `build.log` 的源码根目录诊断路径不同，路径替换后逐字相同；ELF／binary／ROM 完全一致。独立 CLI 初次因缺少 PYTHONPATH 未加载工具包，正确环境的 v2 verify 成功，原日志保留。

当前冷镜像 26,864 B、ILM 26,256 B、data/BSS 16/528 B，保守可达栈 1,328/16,384 B，63 个间接调用位置绑定实际反汇编及完整固件输入。实际 RV32 启动模型执行 229,589 条指令后到达 ILM `services_main`，没有执行完整业务运行期，不当作硬核或周期证据。ELF／ROM 等完整哈希见[机器记录](workstation_task_20261030/ae350_ble_business_main_parent.json)。

迁移前固定 C02 网表的 PCM 检查现已通过十八项／109 负控、896 个 selector；原时钟修正报告中的 pending 状态保留其原时点。此检查仍只证明维护的 PCM 子集，完整 reset／CDC 不继承给新业务候选。新的迁移后综合已从独立副本启动，结果及同配置资源对照另记。

父级包 `/Users/sphenicidition/.cache/gw138k-task-20261030/ae350-business-main-parent-v1` 保存 34 份源码快照和 834 项外部输入／产物，`verify.py` 可只读复核；seal SHA256 `d53c32be7aca0b57179d226cacc92bafef34b8317a99b23f86923347bde287ab`。尚无净 CLS／物理 BSRAM、routed timing、实际 CPU 服务期限、硬件 cache／DMA、真实 BLE 录音／Android 或部署验收。未操作板卡或写 Flash。回退选择原 no-panel profile，或恢复 `3f8cf5f` 后以新身份重建，不复用已固定的旧候选身份。
