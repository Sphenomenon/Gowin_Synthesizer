# W11 参考 monitor 源寄存器区域派生

2026-11-01，离线 helper／实际 prepare 阶段。已完整实测的 W11far `D2110102` 仍有 11 个同域参考时钟 hold 违例，最差 −0.585 ns；PRIMARY／LW 均为 8/8。不能将这些 binary→Gray 同域路径视为异步例外，也不能预设仍有全局时钟资源。

实际 VO 的 `reference_48_monitor`、`reference_44_monitor` 和 `selected_monitor` 各有完整 32 位 binary＋32 位 Gray，初始 16 位假设已按真实清单纠正。既有 `tools/workstation_custom_board_implementation.py` 增加显式 `--reference-monitor-source-regions`，沿用 floorplan parent-evidence＋SHA 的完整派生校验，与原 DDR 放置选项互斥。固定前两个 scope 的完整 128 个 source FF，逐个核对唯一实例名、DFFCE、INIT、全部五个端口、CLK／CE／CLEAR／Q 及对应直连 IBUF；不以数量过滤或自适应位宽放行。第三个 selected monitor 保持原放置。

只给 48k scope 追加 `R[54:54]C[64:84]`，44.1k scope 追加 `R[56:56]C[64:84]`，共 128 条 `INS_LOC`。安装版 SUG1018-1.7E §2.3 明确支持 DFF 使用与 LUT 相同的行列区域语法；每行 21 个 grid 的实际可用性仍由 P&R 验证。维护 RTL、业务配置和 SDC 没有改动；原 CST 的全部字节、IO／hard LOC、DDR 两端远区和唯一 3.500 ns 绑定保持。自动 hold repair 和全部物理门保留。

39 次 floorplan 单元回归通过，覆盖既有 DDR 模式、新模式及输入／结构漂移。实际 W11far 父成功派生 `D2110105`，校验全部输入哈希：VG `4288ba15b267eee1a8d29c358c0a625b10061c3cfe2896e24be2048de8f016b2`、SDC `fa6bfc049f6a1f4910d8c4391f04457534ef67deeb5eccb5d4f38aaaef704f65` 均与父相同；新 CST `30da7d27d507ca97267bd18db851f2db7817ffd952dc34f1aa4a63f33340a115` 精确等于父字节＋这 128 条区域声明。另用实际输入执行五项负控：错误父证据 SHA、混合 DDR 模式、改低最低延迟、缺失最高 Gray 位及错误 IBUF，均拒绝。

helper 冻结 SHA256 `8a4c16445632d6e6ee48933aab0622eecf07a95e54052d71ea78161c81423601`。[机器记录](dual138k_reference_monitor_regions_prepare_20261101.json) 绑定完整实际 scope 清单、父子身份、手册、回归和五项真实输入负控。复现通过现有模块的 `--ddr-floorplan-parent-evidence <完整父实测JSON> --expected-parent-evidence-sha256 <SHA> --reference-monitor-source-regions`，要求新输出、新 UserCode 及原有风险声明。

本阶段冻结时，`D2110105` 已解析完整 CST 并在 placement。首次直接运行因未设置安装版动态库路径，在 EDA 开始前退出；失败日志保留，补齐两项 DYLD 路径后启动正常。新 VO、PLL、完整资源／时序和区域效果尚未验证，结果另行封存；不预记资源或 hold 收益，未操作 SRAM／Flash，不提升硬件验收。
