# 采样率切换前的媒体收尾

本阶段是显式原生运行组合的 opt-in 源码与离线验证。`ENABLE_MEDIA_POLICY` 在时钟服务、受控服务、运行组合和观测消费者均默认为 0；旧命令地址、18-bit MIDI、PANIC、持音、参数提交和 96-bit 录音包不变。AE350 是首个命令入口，后续页面复用同一入口，不增加 MIDI CC。

## 所有权与顺序

1. 时钟服务接受实际变率或恢复命令，锁存命令身份／基准 epoch，拉高媒体 hold，发出一次 stop 请求。相同采样率的 no-op 直接沿旧核心路径执行，不停止媒体。
2. 50 MHz→compute 握手建立 hold，禁止新 REC／score 启动；现有录音继续捕获到 REC owner 接收 seal 请求的边沿。`gw138k_controlled_services` 是唯一 REC_ENABLE owner，在该边沿把 enable 提交为 0。消费者在看到 enable 已真正为 0 后封存，FIFO、POP 快照及对象元数据继续保留。它不靠输出掩码伪装停止。
3. 乐谱采用 planned rate-switch cancellation，优先于同沿 start／首末 cue 完成。已加载 cue RAM 保留；取消后需要显式 restart，既有 cue 单位仍是物理音频帧，不自动重采样时间。
4. 本地 seal 的实际 done／failed 与 score_running=0 均满足后，跨域桥才发出 TF stop。即使录音失败，也先完成 TF 停止，再返回失败结果。
5. TF service 自己拥有停止、已接受 DDR read drain、四 FIFO／DMA 本地域清理 ACK、帧桥 source quiet 和最终 inactive control-mailbox ACK。上层只等待 stop_done／stop_failed，不从 cancel 接受或 busy 下降推断完成。TF 停止锁存只由显式 restart 解除。
6. TF done 后再等待现有物理 REC／score／TF inhibit 与 `media_quiescent_i` 释放，才返回 combined done。时钟服务重新检查平台 permit、核心状态、目标源资格及基准上下文，随后发出唯一核心请求。持音／deferred 事件／参数 owner 未重置，也不产生隐式 PANIC。

50 MHz 的 request toggle 与 hold 都保持到事务完成；compute 的结果 payload 保持到下一事务。结果 ACK 在两级同步后额外等待一个 50 MHz settle edge，再采纳并行同步的失败位。hold 异步置位、同步释放。该 RTL 模型不是物理 CDC／亚稳态接受证明。

## 时钟页新增 ABI

基址沿用 `0xf8030000`。旧 0x00～0x5c 的布局保持；CAPABILITIES bit4 表示策略开启。COMMAND 仍只允许完整 strobe 的 0=48 kHz、1=44.1 kHz、2=recover，写响应仍是下一个非零 command_id。媒体等待期间旧 phase 字段保持 ISSUE=1，不表示已向核心请求或被核心接受。

| 偏移 | 只读含义 |
|---|---|
| 0x60 | bit0 hold、bit1 stop pending、bit2 combined completed、bit3 media failed、bit4 policy enabled、bit5 backend ready；其余为 0 |
| 0x64 | `MEDIA_TIMEOUT_CYCLES`，默认 50,000,000 个常开 50 MHz 时钟（1 秒） |
| 0x68 | 4-bit 最近媒体 failure code；TF 原因沿用 TF 1～8，9=活动受控录音封存失败，10=BLE 封存失败，11=后端准入竞争失败；超时无后端原因时为 0 |

RESULT_CODE 保留 0～7，追加 8=MEDIA_FAILED、9=MEDIA_TIMEOUT、10=MEDIA_GATE（实际收尾完成，但重新检查平台／时钟资格失败）。8～10 均未向核心发出该命令。媒体 completed／failed／reason 锁存到下一提交；核心事件 detail 的旧布局不挪用。BUS error 14=MEDIA_NOT_READY：需要收尾的命令在旧后端仍排空或 hold 未释放时拒绝，防止把上一事务迟到的完成归给新命令。旧 BUS 0～13 保留。

超时给 CPU 明确终态，但跨域桥保持未完成的硬件 fence，直到实际后端结束；backend_ready 继续为 0。TF stop_failed 也不会撤销该 fence，必须等 `tf_stop_pending_i` 真正回到 0 后再释放 hold／ready。晚到的后端 done 不补发已超时命令的核心请求。后续新命令在 backend ready 后才可接受。TF 本身失败后的 hold／继续清理语义由 TF service 保持，不能由上层超时强行清除。

CPU-only reset 只重置命令 observer／IDs，不重置音频或存储。旧 tickets 必须丢弃；不声称消除了 32-bit ID wrap／reset ABA。若本地收尾中 CPU 复位，桥等待 owner 重启后重发幂等 seal。该事务仍完成媒体收尾，但已被复位的 observer 不向核心补发原请求。ACTUAL_STATUS 读取完成后再读 SNAPSHOT_EPOCH，不能把旧 epoch 与新状态拼接。

## 受控录音页新增 ABI

受控服务沿用 `0xf8010000`。CAPABILITIES bit6 表示扩展，旧 REC 0x80～0x98 与 SCORE 0x100～0x12c 保留。下列寄存器仅在策略开启时可读：

| 偏移 | 只读含义 |
|---|---|
| 0x09c | 对象状态：bit0 valid、bit1 sealed、bit2 failed、bit3 FIFO queued、bit4 POP snapshot owned、bit5 当前 REC start permit；bits10:8 是旧失败码 1～7 |
| 0x0a0 | 对象 ID；每次合法新 REC 递增，0 保留，0xffffffff 后回 1 |
| 0x0a4 | 对象录制格式采样率 48000 Hz；不随后续系统率改写 |
| 0x0a8 | 新 REC 开始时的已观测物理帧 epoch |
| 0x0ac | 精确接受的帧数（饱和）；包含已 POP／RELEASE 或仍为快照所有的包，不是当前 FIFO 占用量 |
| 0x0b0 | seal 状态：bit0 pending、bit1 最近完成有效、bit2 最近 seal failed |
| 0x0b4 | 完成的 seal 握手次数（饱和），包括空对象／幂等重发 |
| 0x130 | 乐谱停止结果：bit0 cancelled、bit1 physical-timebase failed；旧 SCORE_STATUS done sticky 不被取消伪造成成功 |

此后端仍是有界 96-bit `{sequence,left32,right32}` FIFO，只接受 48 kHz；没有新增包字段或 DDR 存储。新 REC 要求最新可信 48 kHz 物理观测、没有 switch fence、FIFO 已空、快照已经 RELEASE，且没有媒体 hold；否则 REC_ENABLE=1 报总线错误，面板启动被忽略。旧对象元数据只在合法新 REC 时换代；活动中只读计数可变，应用应先停止／封存并核对 object ID 后再读取稳定的元数据。

正常停止／seal 不清 FIFO；只有原有 context／gap／物理错误／CDC loss／不支持采样率／overflow／switch race 失败会清理无效队列，并保留独立的对象 failure 元数据。已失败且关闭的历史对象不会永久阻止后续空闲采样率切换。CPU-only reset 在策略模式下保留已 POP、尚未 RELEASE 的快照；只有 board/storage reset 清除这份所有权。空录音仍有有效对象身份、48000 Hz 格式、0 帧和 sealed 状态。

## 装配与尚未接受范围

时钟服务 `.media_stop_request_o/.media_stop_hold_o` 接受控运行组合同名 `_i`；运行组合 `.media_stop_ready_o/.media_stop_done_o/.media_stop_failed_o/.media_stop_failure_code_o` 接时钟服务同名 `_i`。运行组合 `.tf_stop_request_o` 接 TF `.stop_request_i`；TF pending／done／failed／failure_code 回运行组合（`tf_stop_pending_i` 必须接真实 stop_pending，失败后的实际排空不能省略）。两边策略参数需显式选择；TF 还需 `EXTERNAL_STOP_PROTOCOL=1`。

时钟服务的 `switch_permit_i` 是平台许可，不能预先用 TF busy 拒绝需要收尾的请求。受控 runtime 的实际 core permit 仍保留平台许可和 REC／score／TF 的物理 busy inhibit；`media_quiescent_i` 仍来自真实 TF 帧桥。

独立 `workstation_bluetooth`／`ble_recording` 的 48 kHz 短录音不属于这套 APB 96-bit 后端。显式 revision 5 profile 通过[媒体准备组合器](MEDIA_PREPARATION_CONTRACT.md)并行请求本 runtime 与[BLE 正常封存](../bluetooth/WORKSTATION_BLE_SEAL_CONTRACT.md)，等待双方真实终态后才回答时钟服务。BLE source_allowed 保留实际采样率／epoch／来源资格，不能用 media hold 掩码伪装来源可用；EMPTY／READY 对象可幂等 seal，活动对象完成已经接受的 stereo word／CRC 后封存。BLE 五层 seal 参数仍默认为关闭，只有 native profile 显式开启。后端 ready 观察与实际接收之间发生竞争时，返回失败 11，调用者重新读取状态，不自动重试。

本契约不完成 R00／R01／R02 的长录音、双率 BLE 录音／下载、同候选全链路验收、综合、P&R、SRAM 或 Flash 部署。
