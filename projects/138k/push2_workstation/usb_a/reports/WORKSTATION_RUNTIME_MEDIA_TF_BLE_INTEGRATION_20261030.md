# 原生音频、TF 与 BLE 封存联合验证

日期：2026-10-30。阶段身份：`runtime-media-TF-BLE-integration-source-v1-b92f6259521863f1`。机器证据：[runtime_media_tf_ble_integration.json](workstation_task_20261030/runtime_media_tf_ble_integration.json)。本阶段只新增离线联合验证与报告，没有修改产品源码、顶层、profile、冻结基线或 vendor 数据，也未综合、P&R、操作硬件或部署。

## 覆盖的实际链路

在上一阶段 [runtime＋TF 联合回归](WORKSTATION_RUNTIME_MEDIA_TF_INTEGRATION_20261030.md)上，新增真实 `workstation_media_preparation` 与维护中的 `workstation_bluetooth`，通过既有 checked prepare 生成真实 BLE 五层连接；prepare 的维护输入、生成文件、ROM 路径头及 ROM 全部纳入 hash。BLE 初始化／连接和已解析命令 dispatch 是明确的夹具边界；不伪造录音器的 PCM、RAM、CRC、seal done 或失败结果。

音频仍走完整原生 APB → 公共参数／持音 → 合成／效果／TF → 官方 DCS／双参考 → 最终路由 → I2S 串行器。BLE 从最终物理 `mclk` 域的 98-bit `rate/error/epoch/sequence/PCM` tuple 经真实 `gw138k_stream_cdc` 到 50 MHz。source_allowed 保留原生的 rate-valid、48k、非 busy／fault、帧 rate/error/epoch 条件，memory-ready 由该 DDR endpoint 夹具提供；**没有用 media hold 屏蔽真实 source loss**。

录音数据 oracle 来自已核对的物理 I2S PCM，独立做固定的立体声布局转换与逐字节 reflected IEEE CRC32；封存后逐字比较真实录音 RAM，并核对 ID、精确提交帧数和 CRC。另以物理 valid、原生 source_allowed、公开 ARMING1／RECORDING2 状态及 `!seal_request/!seal_pending` 独立定义每帧 eligibility，要求每个 eligible 帧都实际写入，且不允许写入不 eligible 帧。该谓词不使用内部 capture/CRC FSM 状态来豁免丢帧。本夹具没有 remote STOP/state3，正常 PCM 相隔超过 1000 个控制周期，足够完成四字节 CRC 提交。

## 结果

最终联合身份：`real-runtime-TF-BLE-media-offline-v1-b92f6259521863f1`。136 项实际输入的源集合 SHA：`b92f6259521863f1b6c5f4c28479c54615178a363f8a22b8cd1e578924b464f5`。所有输入及 560 项冻结支持闭包／综合 VG 在运行前后保持；该旧支持闭包仅为测试提供依赖，不等于改变后的整机候选已综合或验收。

| 场景 | 实际检查 |
|---|---|
| 活动 TF＋本地非空 REC＋score＋BLE 非空录音，48k → 44.1k | 全部真实后端封存／停止后才发 core request；持音、公共参数和原 BLE 对象 ID／RAM／CRC 保留 |
| TF 已接受读与最终 inactive control mailbox ACK | 读返回扣留 30 memory edges；最终 ACK 累计扣留 12900 control edges，期间不能切钟 |
| 44.1k → 48k 的 EMPTY，以及不可用 44.1k 音源下 READY 幂等 | 不为旧格式对象重标采样率；EMPTY 保持零身份，READY 保留已封存对象 |
| CPU observer reset | 真实本地／BLE 封存继续，废弃时钟命令不会复活，持音及参数保留 |
| TF transport failure／clock timeout／TF late cleanup | 实际 core 不切换，迟到清理只恢复后端可接受状态 |
| BLE 真正 seal watchdog failure＋更慢的 TF 最终 ACK | BLE 先以 reason8 失败，aggregate 等到另一真实后端 terminal 才以 RESULT8／媒体 reason10 结束；后续真正清理没有第二个成功 terminal |
| 后端 ready 在时钟准入后、aggregate 接收前下降 | 返回 RESULT8／媒体 reason11，实际 core request 和 epoch 不前进 |

10 个场景通过；5 个实际 core requests，8 个 TF stop requests，TF done6／failed2。140 个物理 I2S 帧与 140 个观察帧一致；48 个真实 TF packets、45 个非零 TF 物理帧。BLE 独立 eligible35 = 实际 capture35，seal done7／failed1；封存 RAM 和 CRC 均对应真实物理 PCM。

六个临时副本负控均精确失败，未改维护源码：

1. 取消 wrapper 的 stereo conversion，触发物理前缀的 CRC／RAM oracle；独立复核现场为 ID1、19 帧，错误 CRC `0012612f`，预期 `4f4fc448`。
2. 丢弃 wrapper 到 recorder 的 pcm_valid，触发 eligible 物理帧漏录断言。
3. aggregate 忽略 runtime terminal，触发两真实后端尚未全部结束的断言。
4. 恢复旧 ready 准入，复现活动媒体 BUS11 拒绝。
5. 无条件放宽 ready，捕获早于媒体停止的实际 core request。
6. 删除 TF 最终 control ACK 完成条件，捕获早于该 ACK 的实际 core request。

独立 reviewer 核对了 v4 的全部 136 项输入、正向／六负控日志 hash、精确 fatal、物理帧及 eligible/capture 数量，并另行编译运行了 stereo-swap 负控。审计记录和 hash 已附于机器证据。

父级随后在独立输出目录完整重跑正向和六个负控，源集合身份、136 项输入哈希和全部计数与 v4 一致；运行结束后再次逐项读取实际输入校验。0 项 owner／结构警告，六个负控均按指定断言失败。独立证据为 [runtime_media_tf_ble_integration_parent.json](workstation_task_20261030/runtime_media_tf_ble_integration_parent.json)。这次功能仿真未覆盖 Gowin 对异步置位／清零的映射；后续 revision 5 综合在 `media_stop/hold_compute` 检出的组合自反馈须另行修复，不能由本结果豁免。

## 编译诊断和限制

新 TB、aggregate、clock、runtime bridge 与 TF owner 为 0 warnings；全局结构检查为零，唯一例外是既有 BLE core 中未消费的 `bt_acl_bridge.errors` 诊断输出。例外严格绑定 core SHA `89d47ee7ae8144e39b30743b0c1073aa9757e982fae863590ad74173252579d1`、第 80 行 `bt_acl_bridge/acl_bridge` 实例、`errors` 端口及恰好一条完整 PINMISSING；其他 PIN、UNOPTFLAT、LATCH、多驱动等诊断仍失败。官方库、既有 DSP／FFT／存储／BLE 宽度警告保留于完整日志，未全局屏蔽。

BLE 测试容量为 128 帧，生产默认容量 16384 帧未改变；TF 仍是实际 DDR 中转路径。SD/FAT 字节与有序共享 DDR endpoint、memory-ready、BLE 初始化／连接／解析后命令均为夹具。没有验证无线 H5／GATT 实际收发、Android、真实 SD 卡、DDR PHY／物理仲裁最坏服务、真实参考时钟／DAC、电气或 routed CDC／PLL／时序。BLE 无线协议默认回归和 standalone seal 证据仍属各自阶段。

本阶段交付只有三份新仿真文件及本报告／机器证据。后续完整候选须使用独立来源身份，重新综合并通过诊断、物理时序／CDC／PLL、功能保持及实板门禁；本离线结果不表示硬件接受或部署完成。回退只需移除此阶段新测试和报告，产品输入保持原样。
