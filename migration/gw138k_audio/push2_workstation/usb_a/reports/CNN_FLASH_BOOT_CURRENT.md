# CNN Flash→DDR 当前交付状态

完整功能已实现并在完整工作站AD上实体证明；新功能尚未提升为默认固化版本。

- 外部Flash地址 `0x600000` 保留BPF1头+模型，104510字节；有效载荷为52239个16-bit系数，CRC32 `AF01A61B`。
- FPGA配置后等待CPU DDR/音频/UI自检，通过SPI逐字节读取，首遍校验后重新读取，经片内BPN1串行线交给原模型解析器，写入已有CNN DDR区并回读CRC。过程无需PC模型上传。
- AD实际配置Flash测试连续3次重载，精确UserCodeAD/status26020、每次至少3条fresh E/source1报告；三音/LR/静音/Panic健康测试通过。没有执行物理断电。
- AD时序未过发布门禁，诊断完成后无条件写回并验证full85，恢复其易失模型及现场测试。当前默认及板上均为full85；2026-10-10 00:31只读核验UserCode85/status26020/modelE；01:18只读健康检查modelE/health0/CRC0/精确48000样本每秒/Push屏幕帧增长。
- B1把官方参考PLL辅助逻辑放入邻近物理区域，所有独立PLL_INIT传播通过，最差7.964ns/预算10ns。DDR及视频仍未闭合，没有写板。
- B2保留上述物理约束，加入逐位验证的卡片动画和TMDS统计优化，路由完成但clk50/DDR时序拒绝；B3针对实际路径增加本地DDR校准寄存、波形/背景预解码与同拍tagflags，已完成路由：clk50/视频/PLL/CDC通过，DDR UI full→renderer CE −2.049ns未过且未烧录；B4时序门禁也未过且未烧录；B5写背压缓冲已完成，clk50/视频/PLL/CDC/协议通过，DDR UI −0.995ns仍未过且未烧录；B6 TF进位/背景几何等价修正在布线，均已通过完整帧提交测试；真实资源与时序以最终automatic_acceptance/result.json为准。综合220BSRAM不是完整物理占用，已完成AD/B0/B1/B2均为268/340物理BSRAM。

## 已完成的验证

B2及B3完整模型仿真52239写/52239读CRC AF01A61B，通过；B3测试包括本地DDR就绪寄存、注册tag flags、并发扫描/写入及原生DDR背压；全内容仅在仿真RX副本加速波特率，另31字使用真实115200。原CNN算术、固件和DDR PHY冻结。

- 2137105次完整像素内容比较、1036800完整双像素renderer beats含独立DDR停顿。
- 卡片动画3145728组、相对坐标4194304组穷举。
- TMDS100000周期全部256数据、消隐/控制码/325复位周期的10-bit输出逐拍一致。
- TF16组合及11容量1100022环形偏移，延迟32-bit指针1001024组全进位/回绕检查。
- P10正常43000样本逐位、2000长停顿故障、4800冷启动帧和有序Panic恢复。
- CPU全效果预设73的CC123释放1189帧，干声及双音sustain释放23887帧，均小于48000截止。
- 11个离线部署/回滚失败分支，无实体IO。

仿真激励仅在内存，不保存PCM或音频文件。权重二进制只包含模型系数。

## 证据入口

实际Flash诊断及full85恢复：`results/workstation_flashad_20261009_local_payload/temporary_flash_diagnosis/result.json`。

源码绑定测试：`reports/CNN_FLASH_BOOT_B0_COORDINATE_TESTS.json`、`CNN_FLASH_BOOT_B2_CARD_TMDS_TESTS.json`。发布比较：`CNN_FLASH_BOOT_RELEASE_COMPARISON.json`。详细历史：`CNN_FLASH_BOOT_IMPLEMENTATION.md`。构建/部署方法：`docs/CNN_FLASH_BOOT.md`。

发布脚本保留原时钟要求，独立检查clk50、真实same-clockDDR UI setup/hold、scope/clk50 CDC、PLL初始化及固件/源/资源工件。通过后才执行模型/配置Flash校验、3次真实重载及实时演奏；失败回滚。默认LATEST不会因为仿真或Fmax摘要PASS而更新。
