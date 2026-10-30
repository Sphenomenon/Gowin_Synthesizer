# 未选择的 TF 文件 owner：线级来源阶段（2026-10-31）

本阶段在 base `dc6e0fd80b27116715f330e86e0566eb8ceb34eb` 的独立克隆新增 `workstation_tf_file_reader`，接入既有且保持原字节的 native sector/session。没有任何 profile 选择新 owner，也没有综合、P&R、板卡操作或部署。M03 尚未完成。

原 GPL FAT16/32 playlist reader、版权/许可证、vendor、baseline 和 selected profile 全部保留。新源是版本化 maintained owner，18 条 exact edits 在 provenance 中逐项登记，并正向重构、反向恢复到原始 SHA256 `57ee8873418fe2fa00e40782e1509495c8eb779e11d4175884a79f741fcc0441`。重构只供验证，不生成生产输入。新源 SHA256 为 `13495665a2c01dc3b2d129790e570a21122850e8664743efa44fa7d8d36c236b`。

保留 16 曲、12 字节 8.3 名称与选曲。文件 data sector 只在 `sector_allow/data_sector_start` 同沿预留完整 512B，metadata/CRC/padding 不进入文件字节。`track_applied` 与首个 reservation 不同沿，忙时最新选曲在原 sector/CRC 排空后应用；stop 优先且立即屏蔽迟到 output，drain 后单次 cancelled，保持期间不重播。reset 真实取消 SPI 并重扫，恢复需显式选择。自然 EOF 晚于最后字节，并且必须验证末 cluster 的 FAT EOC；错误与取消均不发 EOF。完整合同见 `rtl/tf_audio/storage/WORKSTATION_TF_FILE_READER_CONTRACT.md`。

只支持文档列明的 512B/power-of-two cluster、FAT16/32 superfloppy 或首 primary MBR 分区及受检几何。坏 MBR/BPB 不再无界递增扫描；FAT16 root 按 ceil(entries/16) 和独立 16-bit cursor；FAT32 屏蔽保留高 4 位、覆盖整个 EOC 区间。根目录有 sector budget；非法/提前 EOC/末尾非 EOC、空目录/无效选择、transport FAULT/read_error 和 watchdog 都有明确终态。严格支持文件链恰为 ceil(file_size/cluster_bytes) 个 cluster；额外分配或循环链不会冒充 EOF。此界限并不接受通用文件系统、原子介质修改或所有 FAT 布局。

最终线级矩阵 **56 项通过**：FAT16/FAT32 × superfloppy/MBR、JMP MBR、碎片两曲、八种 FAT32 EOC、258-sector FAT16 root/部分末 sector、名称、metadata 隔离、预留、连续请求/切曲、stop/迟到字节、真实传输中 reset、坏 BPB/链/空与无效 track、初始化及 probe/transport 故障。另 **8 个真实源故障负控全部拒绝**：应用/预留同拍、allow 绕过、早 EOF、FAT32 高位不屏蔽、root cursor 回绕、末链不验证、metadata 泄漏、stop 后字节泄漏。fixture 只接公开 SPI/文件口，不 force/deposit DUT 寄存器，也不以 session stub 替代线级卡模型。

原 native sector/session 线级回归 **21 项通过**，包含 historical duplicate CMD17 和 R1-valid 绕过负控；accepted source-boundary **17 项通过**。原 full1 的 DBR-signature fixture 期望分类错误记录保留在外部缓存，最终修正为 MBR 内 DBR 测试；没有为适配错误期望修改产品行为。外部完整日志/镜像/输入身份由同名 JSON 引用，均以 SHA256 固定。

复现：`python3 projects/138k/push2_workstation/usb_a/sim/tf_audio/run_workstation_tf_file_reader_wire.py --output <new-directory>`；原 sector 回归为同目录 `run_workstation_tf_sd_sector_wire.py`；source boundary 为 `sim/test_current_workstation_sources.py`。所有输出须在源树外的新目录。

CRC 仍只排空不校验；无 card-detect/CID，probe 只能建立响应存在，快速未观察到的换卡需显式 reset。已发 payload 中拔卡可能先产生未经 CRC 检验的填充值，后续失败才作废 session。本阶段没有 FAT cache、PCM ingress/prefill、ordered physical EOS、即时播放无 DDR profile、吞吐/资源/时序/硬件资格；后续组合必须保持单 SD owner，另验这些边界。回滚只需不选入或移除新增未选择文件，既有 selected profile 和部署不受影响。
