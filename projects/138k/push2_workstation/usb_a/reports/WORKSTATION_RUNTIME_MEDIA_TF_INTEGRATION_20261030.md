# 原生运行时与真实 TF 媒体停止联合回归

日期：2026-10-30。身份：`runtime-media-TF-integration-source-v1-9a3e36d2da8f4217`。机器证据：[runtime_media_tf_integration.json](workstation_task_20261030/runtime_media_tf_integration.json)。本阶段是源码与离线联合验证，未综合、P&R、上板或部署；完整候选的来源选择由后续独立阶段处理。

## 发现与修复

真实 `workstation_runtime_controlled` 的公开 request-ready 包含活动 REC、score 和 TF 的门控。旧时钟命令服务在发出媒体停止请求之前，先以公开 ready=0 拒绝真实切换，得到 BUS11。原始现场复现保存在机器证据的 `original_bug` 中，旧 clock SHA `e8b73e6c6794e53c6dc69c887b3af859b187da357ba8585512c6f350cd3e6880`；该行为还由本轮可重复的 legacy-admission mutant 捕获。

修复仅允许 `ENABLE_MEDIA_POLICY && needs_media_stop` 的真实切换在公开 ready=0 时进入媒体准备。active-valid、busy、fault、DSP fault、目标参考资格、外部许可及后端准入仍检查；停止完成后仍在实际 core request 发出前重验真实 ready。默认关闭和同率 no-op 的准入保持严格。

## 真实边界与测试夹具

测试通过真实 APB CDC 连接维护中的时钟服务及完整原生 runtime，使用 12.288 MHz／16.9344 MHz 独立参考、官方 Gowin DCS、帧调度、合成／效果、最终路由、I2S 串行输出及物理到计算域观察。TF 为真实 service、清空协议、DDR DMA、有界字节 FIFO、WAV 解析／解码、代次传输和单项 DDR 命令缓冲。唯一 SD/FAT 夹具只提供真实 WAV 字节；每文件 4096 stereo16 帧，16428 字节。DDR 夹具在两个真实客户端之间每 memory edge 最多接受一项事务，保留全局读写顺序并检查原生地址分区。

冻结支持项目为 `custom138k-workstation-v1-41e653fe462e5ea3` 的 560 项输入及综合 VG，运行前后均完整核对。它只提供既有支持闭包，不代表已对改变后的维护源码综合。本轮源清单去除未被原生 runtime 实例化的历史组合根和两个重复 Delay wrapper，使用唯一维护 owner；不修改缓存工程或冻结 baseline。

最终 ACK 注入只在真实 clear-done、memory reopen 和 RESTART_SETTLE 边界扣留 TF 的 ACK 返回同步值；所有时钟与真实目标 mailbox 持续运行。没有伪造 TF done、core accepted 或 core applied。

## 验证结果

最终联合身份：`real-runtime-TF-media-offline-v1-9a3e36d2da8f4217`。源集合 SHA：`9a3e36d2da8f421765ef84878d489794b7388832f8b2bf3b97c2f620f568219c`。

| 场景 | 结果 |
|---|---|
| 活动 TF 的同率请求 | 保持 BUS11 严格准入，无提前 core request |
| 48k → 44.1k，持音＋已提交参数＋非空 REC＋score＋真实 TF | 先封存 REC、取消 score、停止 TF，再真实切钟；持音和参数保留 |
| 已接受 TF 读与最终 mailbox ACK | 读返回扣留 30 memory edges，最终 ACK 扣留 200 control edges，均阻止实际时钟请求 |
| 封存对象与 POP 快照 | 48000-Hz 格式、原 epoch、精确接受计数及原 POP 数据保留，可逐包消费 |
| 44.1k → 48k | 真实 TF 停止后反向切换，epoch 只增加一次 |
| 非法目标参考／CPU observer reset | 不合格参考拒绝；CPU reset 不撤销封存或恢复废弃的时钟请求 |
| TF transport failure／clock timeout＋TF late cleanup | RESULT8/reason7 与 RESULT9，均不切换；晚清理后才恢复准入 |

合计 7 个定向场景、3 个实际 core requests、5 个 TF stop requests，TF done 3／failed 2。100 个物理 I2S 帧与 100 个观察帧逐项一致；真实 TF packet 35 个，33 个 TF 非零物理输出帧；累计最终 ACK 等待 12700 control edges。正向编译为 0 owned warnings、0 全局结构 warnings；既有 DSP／FFT／FIFO／存储参数宽度及官方库警告保留于完整日志。

三个临时源副本负控均精确失败：恢复旧 ready 准入得到 BUS11；无条件放宽 ready 导致实际 core request 早于媒体停止；删除最终 control ACK 完成条件导致实际 core request 早于最终 TF mailbox ACK。负控不改维护源码。

另外，默认时钟服务 3 APB 相位 × 146 交易通过；原媒体策略 3 相位 × 11 场景、score 5 场景及原四个负控通过。所有本阶段输入及支持闭包在运行前后保持同一 hash。

## 交付与限制

本阶段白名单：clock service 的 5 行差异；四个新联合仿真支持文件；本报告与机器证据。TF service 使用独立修复阶段的冻结 SHA `debe8ca8c0515ea0ef5b1c7c45c9835373a4720731df0cef97f11daddb467612`，其组合环修复和定向验收由该 owner 的报告负责。本阶段不修改顶层、profile、BLE、冻结基线或 vendor 数据。

SD 卡、DDR PHY／整机仲裁及其最坏服务、物理参考时钟、真实 DAC、无线链和 BLE recorder 不在本报告验收范围。后续将 aggregate＋真实 BLE recorder 接入该联合链，再建立改变后的完整候选身份、综合与物理门禁；当前离线结果不代表硬件接受。

回退：clock service 可回到 `3be6d20` 的准入实现；四个新增仿真支持文件可独立移除。既有 accepted／pinned profile 和 560 项冻结支持输入未被此阶段改变。

## 父级独立复验

父级在新目录重新编译运行真实联合链和三个负控，source identity／全部输入hash／逐项PASS指标与冻结子阶段完全一致；正向0 owner和0结构warning。另重新运行修改后的默认clock三相位和原媒体policy／score／四负控，全部通过。默认clock记录中的profile清单已从revision4更新至5，实际编译输入与测试配置保持相同，此唯一元数据差异明确保留。独立原始结果见 [runtime_media_tf_integration_parent.json](workstation_task_20261030/runtime_media_tf_integration_parent.json)，SHA-256 `7c44245a3aca1d26a4ccc3d4698234293307c5fa3ea0b34d12fea0723a9f0a5c`。仍未包含真实BLE recorder或板级接受。
