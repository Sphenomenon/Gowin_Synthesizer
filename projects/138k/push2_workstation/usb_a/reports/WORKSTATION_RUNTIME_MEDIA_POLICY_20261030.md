# 受控媒体封存与采样率切换策略（2026-10-30）

源码身份：`runtime-media-policy-source-v1-cd07ca9dc3bc06ad`。此阶段只完成原生 opt-in 源码与离线验证，未综合、P&R、上板或部署。详细输入、各回归完整结果及源哈希在 [runtime_media_policy.json](workstation_task_20261030/runtime_media_policy.json)；该 JSON SHA-256 为 `6cbfbcb92ee050f678450b59829042cdab74e7f1068fb73cd55a0918c69e0b7c`。

## 结果与边界

`workstation_audio_clock_service` 在实际变率／恢复前保持媒体事务，等受控 REC／score 结束，再等 TF 的真实停止与现有物理媒体 inhibit 释放，重新检查平台和目标源后才发出唯一核心请求。持音、deferred 事件和公共参数 owner 不重置；不新增 MIDI CC 或隐式 PANIC。同率 no-op 不停止媒体。

REC_ENABLE 仍只由受控服务提交，正常 seal 保留 FIFO、POP 后未 RELEASE 的快照和对象身份／录制率／epoch／精确接受帧数。帧数包含已 POP 的快照，不等同当前队列长度。CPU-only reset 后对象元数据及这份快照仍可读。旧 96-bit 后端仍只支持 48 kHz；空录音与 overflow 都有明确终态，后续系统切到 44.1 kHz 不改写已封存对象的 48000 Hz 格式。

score 采用 planned rate-switch cancellation，取消优先于同沿 start、首／末 cue 完成以及已注册的 done 脉冲；cue RAM 保留，后续显式 restart 可继续正常完成。

TF stop_failed 后仍须等真实 stop_pending=0 才释放局部 hold／ready。媒体超时发布明确失败结果，但保留后台 fence；BUS14 拒绝重入，迟到的 stop 完成不会给已超时／CPU 复位的命令补发核心请求。接口、所有寄存器、错误码与 CDC 约束见 [MEDIA_STOP_POLICY.md](../rtl/services/MEDIA_STOP_POLICY.md)。

## 验证

| 回归 | 结果 |
|---|---|
| 新媒体策略：真实 APB CDC、REC FIFO、score、rate core，显式 TF 完成 fixture | 3 个 APB 相位，每相位 11 类事务；5 次核心请求、10 次 TF stop、11 次 seal 完成、10 个精确接受帧 |
| planned score 边界 | 5 项：同沿零时刻 start／stop、最终 cue、resident restart、已注册 done／stop、无新物理帧时停止 |
| 新策略负控 | 提前 core、seal 清 FIFO、丢失取消状态、复用旧媒体结果 4 个变体全部被语义断言否决 |
| 默认受控服务 ABI | 1106 笔事务／1106 次提交、256 cue；精确反向重建原 timing-prepared 源码通过 |
| 默认时钟服务 ABI | 3 相位各 146 笔事务；原 timeout／recovery／CPU-reset／epoch／DSP 故障用例通过 |
| 默认完整受控 runtime | 1078 physical = 1078 observed，48/44 FFT 128/256 bins，2 次切换、源寄存／CDC／display tuple 检查通过 |
| 默认 in-flight score 边界 | 13 次尝试获得显式失败，延迟捕获负控被否决 |

新策略启用路径由 Icarus 运行；Verilator lint 的 clock／controlled／consumer／bridge 新 RTL warning 为 0。保留了冻结 FFT 的宽度／timescale、原 FIFO 比较宽度以及 fixture 动态正相位 ZERODLY 提示，没有放宽实际时钟或 false path。所有运行的输入前后哈希一致；本报告另外核对每个运行中的 owner 输入仍与当前冻结源码匹配。

新策略回归使用真实 FIFO／score 和时钟控制状态机，但 TF 是明确 done／failed 的 fixture，不代替 TF drain 本体或物理证明。默认完整 runtime 回归包含原生 DSP、官方 DCS 和 I2S，但策略参数关闭；不能把两种验证范围拼成已完成的 enabled 整机验收。

## 后续接受与回退

独立 `workstation_bluetooth`／`ble_recording` 的 48 kHz 短录音尚须自己的正常 seal 与联合 preparation 事务。source_ready 掉低导致失败，不能当作正常封存。本报告只覆盖 APB 96-bit REC／score 与 TF 停止接口；父级的 BLE／联合装配、AE350 C API、真实 TF/BLE 同候选验证另立阶段。task.md 已记录用户确认的政策，但未勾选整体验收框。

没有实现 DDR 长录音、44.1 kHz 旧 REC、BLE 双率录制／下载；R00／R01／R02、资源、PLL／CDC／时序、上板与 SRAM／Flash 接受均保持独立。此阶段未改 accepted 输入策略、冻结 baseline 或 vendor bytes。默认 `ENABLE_MEDIA_POLICY=0` 是旧路径；回退源码身份可恢复先前代码，本阶段没有需要撤销的硬件写入。

## 父级独立复验

父级在新输出目录重新编译运行媒体策略、默认 controlled services、默认 clock service 和完整 native runtime。仅规范化重建 APB 文件的输出目录后，全部输入哈希及逐项指标与上表子阶段证据一致；默认完整链再次得到 1078 个 physical／1078 个 observed 帧，双率 FFT 128／256 bins。10 项 accepted／pinned 来源检查通过。独立原始结果记录于 [runtime_media_policy_parent.json](workstation_task_20261030/runtime_media_policy_parent.json)，SHA-256 `ef3330b2a39d34d4934ddb06e530401ac33b1d09820f6f8529264558a8da0ed3`。验证范围仍为离线源码，不包含 enabled 完整媒体联动或板测。
