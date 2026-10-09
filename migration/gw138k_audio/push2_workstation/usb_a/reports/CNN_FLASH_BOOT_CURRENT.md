# CNN Flash→DDR 当前交付状态

完整功能已实现并在完整工作站AD上实体证明；新功能尚未提升为默认固化版本。

- 外部Flash地址 `0x600000` 保留BPF1头+模型，104510字节；有效载荷为52239个16-bit系数，CRC32 `AF01A61B`。
- FPGA配置后等待CPU DDR/音频/UI自检，通过SPI逐字节读取，首遍校验后重新读取，经片内BPN1串行线交给原模型解析器，写入已有CNN DDR区并回读CRC。过程无需PC模型上传。
- AD实际配置Flash测试连续3次重载，精确UserCodeAD/status26020、每次至少3条fresh E/source1报告；三音/LR/静音/Panic健康测试通过。没有执行物理断电。
- AD时序未过发布门禁，诊断完成后无条件写回并验证full85，恢复其易失模型及现场测试。当前默认及板上均为full85；2026-10-10 00:31只读核验UserCode85/status26020/modelE；01:18只读健康检查modelE/health0/CRC0/精确48000样本每秒/Push屏幕帧增长；02:40及03:44只读健康检查全部通过、模型E/health0/CRC0/48000样本每秒/Push帧+2。
B1起官方PLL参考辅助逻辑邻近放置，PLL全传播独立10ns预算均已验证。B8修正后TF读计数旧−5.551ns路径消失，剩BIST比较−2.936ns和TF重启clear/card坐标；BB的BIST分级比较明确启动+5.24288ms/0BSRAM，BC的TF byte-valid clear额外0周期/0BSRAM；BE的成对TF读响应/数据寄存每块+10ns/0BSRAM。所有新候选保留完整工作站606个输入，paired FIFO物理上限268；综合220不能当作完整物理占用。最终以各目录automatic_acceptance/result.json为准。

| 候选 | 实际状态 | clk50 MHz | 视频 MHz | DDR UI setup ns | 物理BSRAM | 写板 |
|---|---|---:|---:|---:|---:|---|
| B3 | routed_rejected | 51.197 | 156.577 | -2.049 | 268 | 未烧录 |
| B4 | routed_rejected | 50.79 | 180.112 | -2.362 | 268 | 未烧录 |
| B5 | routed_rejected | 57.536 | 163.513 | -0.995 | 268 | 未烧录 |
| B6 | routed_rejected | 55.134 | 164.64 | -4.714 | 268 | 未烧录 |
| B7 | routed_rejected | 54.7 | 182.441 | -5.551 | 268 | 未烧录 |
| B8 | routed_rejected | 58.176 | 167.823 | -2.936 | 268 | 未烧录 |
| B9 | routed_rejected | 55.212 | 174.628 | -2.688 | 268 | 未烧录 |
| BA | routed_rejected | 51.52 | 188.468 | -2.254 | 268 | 未烧录 |
| BB | routed_rejected | 54.518 | 193.624 | -2.461 | 268 | 未烧录 |
| BC | routed_rejected | 58.04 | 167.399 | -2.336 | 268 | 未烧录 |
| BD | routed_rejected | 60.168 | 183.284 | -1.463 | 268 | 未烧录 |
| BE | routing | 待报告 | 待报告 | 待报告 | 待报告 | 未烧录 |
| BF | placement | 待报告 | 待报告 | 待报告 | 待报告 | 未烧录 |
| C0 | synthesizing | 待报告 | 待报告 | 待报告 | 待报告 | 未烧录 |

状态表从实际构建和验收工件生成：2026-10-10T04:03:27.397331+08:00。

## 已完成的验证

B2/B3/B8完整模型仿真52239写/52239读CRC AF01A61B，通过；B3测试包括本地DDR就绪寄存、注册tag flags、并发扫描/写入及原生DDR背压；全内容仅在仿真RX副本加速波特率，另31字使用真实115200。原CNN算术、固件和DDR PHY冻结。

- 2137105次完整像素内容比较、1036800完整双像素renderer beats含独立DDR停顿。
- 卡片动画3145728组、相对坐标4194304组穷举。
- TMDS100000周期全部256数据、消隐/控制码/325复位周期的10-bit输出逐拍一致。
- B8绑定实际源码：TF36组合（含同周期响应）、65-bit读计数SAT和12-bit频谱地址SAT，完整分析页1036800双像素beats及129601 DDR命令逐位相同。
- BD/BE实际TF前级缓冲＋客户端队列＋注册DDR仲裁器50/54组协议；各18组读命令在途切换、旧响应丢弃和新65字节流完整字节/地址检查。
- TF16组合及11容量1100022环形偏移，延迟32-bit指针1001024组全进位/回绕检查。
- P10正常43000样本逐位、2000长停顿故障、4800冷启动帧和有序Panic恢复。
- CPU全效果预设73的CC123释放1189帧，干声及双音sustain释放23887帧，均小于48000截止。
- 11个离线部署/回滚失败分支，无实体IO。

本任务仿真激励仅在内存，不保存PCM或音频文件；当前BA～BE构建目录没有音频文件，BPF1镜像严格为104510字节模型头＋系数。全工作站已有两份2026-10-06的MP3解码回归工件，本任务未改动；它们是压缩TF测试音频，不属于本任务生成内容。内容审计见CNN_FLASH_BOOT_CONTENT_AUDIT.json。

## 证据入口

实际Flash诊断及full85恢复：`results/workstation_flashad_20261009_local_payload/temporary_flash_diagnosis/result.json`。

源码绑定测试：`reports/CNN_FLASH_BOOT_B0_COORDINATE_TESTS.json`、`CNN_FLASH_BOOT_B2_CARD_TMDS_TESTS.json`。发布比较：`CNN_FLASH_BOOT_RELEASE_COMPARISON.json`。B8源码绑定回归：`CNN_FLASH_BOOT_B8_TF_SPECTRUM_TESTS.json`。详细历史：`CNN_FLASH_BOOT_IMPLEMENTATION.md`。构建/部署方法：`docs/CNN_FLASH_BOOT.md`。

发布脚本保留原时钟要求，独立检查clk50、真实same-clockDDR UI setup/hold、scope/clk50 CDC、PLL初始化及固件/源/资源工件。通过后才执行模型/配置Flash校验、3次真实重载及实时演奏；失败回滚。默认LATEST不会因为仿真或Fmax摘要PASS而更新。
