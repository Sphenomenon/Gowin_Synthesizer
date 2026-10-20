> 2026-10-20实现进展：基础v1及显式协商下载扩展已在25K独立工程验证，配套APP0.2.10。实现/兼容规则见[25K协议工程](projects/25k/example/RTL8723DS_PROTOCOL/README.md)及[二阶无损扩展](projects/25k/example/RTL8723DS_PROTOCOL/docs/SECOND_TRANSFER_EXTENSION.md)，实测见[第十八轮](projects/25k/example/RTL8723DS_PROTOCOL/reports/speed18_20261020/README.md)。这些可选扩展不改变默认v1上限；未声明138K工作站已实现业务GATT、外部实时录音或手机硬件验收。
# GW138K 蓝牙业务协议 v1.0

日期：2026-10-20。状态：供 FPGA 与客户端共同评审的接口定义；尚无对应业务实现和实测兼容性声明。需求、资源预算和实施顺序见 [准备方案](BLUETOOTH_CONTROL_PLAN.md)。

本版下载窗口 1、PCM 块最大 256 字节用于先验证正确性。后续高速模式拟采用窗口流式传输、紧凑数据通知及 MTU/速率协商，方向见[准备方案第 6.1 节](BLUETOOTH_CONTROL_PLAN.md#61-下载优化方案2026-10-20-补充)；该扩展须通过新版本和能力协商启用，不改变本文 v1.0 的线格式。

## 1. 范围与约定

BLE 外设为 GW138K＋RTL8723DS，单连接、单业务会话。首版 ATT MTU 固定 23，特征值最多 20 字节；不依赖大 MTU、蓝牙音频或实时 PCM 推流。

下文 `u8/u16/u32/u64` 是无符号整数，均为小端；`i16` 为小端二进制补码。字段紧密排列，无隐式 padding。保留位必须为 0；不符合长度、枚举或保留位要求的命令不得执行。时间单位 ms，音频长度中的“帧”为同时刻左右声道各一个样本。

## 2. GATT 数据库

业务服务 UUID：`9b6d0000-4c2a-4f87-9a31-138000000001`。下表中 UUID 简写 `xxxx` 替换完整 UUID 第一段的末四位，其余不变。例如 Capability 为 `9b6d0001-4c2a-4f87-9a31-138000000001`。

| UUID 简写 | 名称 | 属性 | 声明 / 值 / CCCD 句柄 |
|---|---|---|---|
| 0000 | Primary Service | 服务声明 | 0x0009，结束于 0x0016 |
| 0001 | Capability | Read，0x02 | 0x000A / 0x000B / 无 |
| 0002 | Command | Write with response，0x08 | 0x000C / 0x000D / 无 |
| 0003 | Response/Event | Notify，0x10 | 0x000E / 0x000F / 0x0010 |
| 0004 | Status | Read＋Notify，0x12 | 0x0011 / 0x0012 / 0x0013 |
| 0005 | Transfer | Notify，0x10 | 0x0014 / 0x0015 / 0x0016 |

现有句柄 1–8 的 GAP、GATT、FFF0/FFF1 测试服务保持原义；客户端按 UUID 发现，不能依赖上述句柄常量。业务协议修改数据库时必须同步更新本表。CCCD 只接受 0x0000/0x0001；断连清零，不记忆订阅。Command 不支持 Write Command、Prepare Write 或长写，每片使用 ATT Write Request，并等待对应 Write Response。

广告包包含 Flags 和业务服务 128 bit UUID；完整名称放 Scan Response。服务 UUID 按 BLE UUID 的线序编码，不能直接发送 UUID 字符串。需要补充服务发现、128 bit 声明发现和 Scan Response 的底层实现与仿真。

### Capability Read：固定 20 字节

| 偏移 | 类型 | 字段 |
|---|---|---|
| 0 | u8 | protocol_major＝1 |
| 1 | u8 | characteristic_value_limit＝20 |
| 2 | u16 | max_logical_message＝512 |
| 4 | u64 | boot_id，每次设备启动不同，0 无效 |
| 12 | u32 | capabilities，见下表 |
| 16 | u16 | max_pcm_chunk，首版最大 256 |
| 18 | u8 | max_transfer_window，首版＝1 |
| 19 | u8 | recording_slots，首版＝1 |

capabilities：bit0 参数读，bit1 参数写，bit2 状态订阅，bit3 短录音，bit4 DDR 连续录音，bit5 下载，bit6 续传，bit7 非易失录音保存；其余保留。仅实现且通过相应检查的能力置 1；M2 短录音不能宣告 bit4。未完成初始化时读取返回 ATT Application Error 0x80。

`boot_id` 必须跨重启避免复用。候选来源是启动时通过 HCI LE Rand（0x2018）取得的非零 64 bit 随机数，须验证控制器支持并检查返回状态；也可由可用管理层提供持久递增标识。不能用复位后清零的计数器代替。来源失败时拒绝建立业务会话，不能用固定值降级。这里是新增实现要求，现有驱动尚无该业务启动标识。

### Status Read：固定 20 字节摘要

`snapshot_id:u32, device_time_ms:u32, config_revision:u32, recording_id:u32, record_state:u8, actual_mode:u8, active_voices:u8, flags:u8`。

flags：bit0 mode_pending，bit1 clip，bit2 record_incomplete，bit3 control_window_open；其余 0。所有字段从同一快照取得。不存在录音时 recording_id＝0；未知模式或声部统计为 0xFF，详细通知中的有效位决定是否可用。Status Read 不采用下节分片格式；Status Notify 采用。

## 3. 特征值分片格式

适用于 Command Write、Response/Event Notify、Status Notify 和 Transfer Notify。每条逻辑消息不超过 512 字节。

| 偏移 | 类型 | 字段 |
|---|---|---|
| 0 | u8 | marker＝0xB1，表示分片格式 v1 |
| 1 | u16 | message_token，同一特征上的消息传输编号 |
| 3 | u8 | fragment_index，从 0 连续增加 |
| 4 | u8 | flags，bit0 FIRST，bit1 LAST，其余 0 |
| 5 | u8 | data_length，1–14 |
| 6 | byte[data_length] | 当前逻辑消息的连续字节 |

ATT 特征值长度必须等于 6＋data_length。除 LAST 片外 data_length 必须为 14。FIRST 仅出现在 index＝0；单片消息同时置 FIRST 和 LAST。最大 37 片，最后一片拼接后不得超过 512 字节。

每个特征单独维护一个重组槽，不在同一特征上交错两条逻辑消息。每个连接的 message_token 从 1 递增，u16 回绕；只有上一消息传输结束后才能在该特征开始下一条。不同特征可独立发送。token 只用于重组，不承担业务请求去重。

FIRST 开始或替换当前未完成消息，精确重复的上一片可忽略；索引跳号、同索引不同内容、错误 token 或保留位非零均丢弃当前重组。Command 分片错误返回 ATT Invalid Attribute Value Length 0x0D（长度类）或 Application Error 0x80（顺序/状态类）。队列无空位时返回 Insufficient Resources 0x11。接收端 2 秒没有收到下一片则释放该槽，客户端重新发送完整逻辑消息。

业务数据只在完整消息、总长度和 CRC 均通过后交给命令调度。片间等待、完整消息 CRC 计算和业务命令执行均不得阻塞音频域。

## 4. 逻辑消息

| 偏移 | 类型 | 字段 |
|---|---|---|
| 0 | u8 | opcode |
| 1 | u8 | status；请求固定为 0，响应见错误表 |
| 2 | u16 | payload_length，0–492 |
| 4 | u32 | request_id；请求及响应非零，主动事件/周期状态为 0 |
| 8 | u64 | session_nonce |
| 16 | byte[payload_length] | payload |
| 16＋payload_length | u32 | CRC32，覆盖此前所有逻辑消息字节 |

总长度严格等于 20＋payload_length。CRC 为 CRC-32/ISO-HDLC：poly 0x04C11DB7，反射实现 0xEDB88320，init 0xFFFFFFFF，refin/refout＝true，xorout＝0xFFFFFFFF；结果按小端发送。ASCII `123456789` 的校验值为 0xCBF43926。CRC 用于一致性检查，不是身份认证。

校验通过但 opcode 未知时返回 UNSUPPORTED。总长度错误或 CRC 不通过时不执行、不更新 request 高水位，也不根据未校验 header 发送业务响应；客户端超时后重传。

### 会话和请求生命周期

1. 连接后读取 Capability，开启 Response/Event 的 CCCD，再发送 HELLO。没有订阅响应时 HELLO 返回 ATT Application Error 0x80。
2. HELLO header 中携带客户端新生成的非零随机 session_nonce；设备在控制窗口开启时接受并回显。连接已存在会话时，同 nonce、同请求重传返回缓存；不同 nonce 的 HELLO 返回 BUSY，重新建立会话须先断连。
3. 后续消息均使用已接受 nonce。断连、设备重启或控制窗口关闭使会话失效，并清空分片、请求缓存及下载窗口；原录音默认继续。
4. request_id 从 1 开始严格递增，客户端最多保持一个尚未收到首次业务响应的请求。重发使用同 request_id 与逐字节相同的逻辑内容。即将 u32 回绕时重新连接，不能在同一会话复用 ID。
5. 设备缓存最多 32 个已接受请求及结果，完成条目保留至 60 秒到期或因容量需要淘汰最旧条目；未完成条目不能淘汰，全部被占用时新请求返回 BUSY。缓存内容不同的同 ID 返回 REQUEST_CONFLICT；ID 低于/等于高水位且无缓存返回 STALE_REQUEST。拒绝的新请求不消费 ID。客户端遇到 STALE_REQUEST 时查询实际状态，不以新 ID 盲目重放变更。
6. 完整合法请求被接受进入调度时推进高水位。结果缓存记录完整命令内容及语义响应，不能只凭 CRC 判断内容相同。重复请求不再次执行。ACCEPTED/PENDING 条目在任务结束前不得淘汰；完成后按上一条保留。缓存淘汰不降低 request 高水位。
7. 客户端等待首次业务响应超时默认 3 秒，再用同 ID 重传，最多 3 次；仍无响应则重连并查询状态。START/CLEAR 等变更不能在重连后自动以新 ID 重放。
8. ATT Write Response 只确认分片被接受；APPLIED 才表示已在所属控制域生效。ACCEPTED/PENDING 必须可通过 GET_OPERATION 查询，不能只靠单次通知判断完成。

### 状态码

| 值 | 名称 | 含义 |
|---|---|---|
| 0x00 | OK / APPLIED | 查询成功或修改已生效 |
| 0x01 | ACCEPTED | 后台任务已接受 |
| 0x02 | PENDING | 等待现有切换条件或封存条件 |
| 0x80 | UNSUPPORTED | 命令、参数或能力未实现 |
| 0x81 | INVALID_ARGUMENT | 长度、范围、枚举或保留位错误 |
| 0x82 | BUSY | 队列、状态、窗口或资源暂不可用 |
| 0x83 | INVALID_STATE | 当前状态不允许操作 |
| 0x84 | REVISION_CONFLICT | expected_revision 已过期 |
| 0x85 | SESSION_REQUIRED | nonce 无效或会话已失效 |
| 0x86 | REQUEST_CONFLICT | 同 ID 对应不同内容 |
| 0x87 | STALE_REQUEST | 旧 ID 已无去重缓存 |
| 0x88 | OBJECT_GONE | boot_id/recording_id 不匹配或对象已清除 |
| 0x89 | OUT_OF_RANGE | 文件偏移、块长度等越界 |
| 0x8A | STORAGE_ERROR | DDR 写入/读取、容量等失败 |
| 0x8B | TIMEOUT | 任务内部超时 |
| 0x8C | CONTROL_DISABLED | 本地控制窗口未开启或已关闭 |
| 0x8D | TRANSFER_CONFLICT | ACK 不匹配或引用状态冲突 |

除另有说明，错误响应 payload 固定为 `detail:u16, reserved:u16=0, config_revision:u32`；detail＝0 表示无附加信息，值 1 表示长度，2 范围，3 保留位，4 能力，5 录音忙，6 响应队列满。错误不允许部分修改状态。

## 5. 命令字段定义

下表仅列 payload；响应通过 Response/Event 特征返回，opcode、request_id 和 nonce 与请求相同。所有未列出的额外字节都应拒绝。

| opcode | 名称 | 请求 payload | 成功响应 payload |
|---|---|---|---|
| 0x01 | HELLO | `major:u16=1, minor:u16=0` | `boot_id:u64, capabilities:u32, config_revision:u32, device_time_ms:u32` |
| 0x02 | GET_STATUS | 无 | 第 8 节详细状态快照 |
| 0x03 | SUBSCRIBE | `mask:u16, status_period_ms:u16, record_period_ms:u16, reserved:u16=0` | 相同布局，返回实际接受值 |
| 0x04 | GET_OPERATION | `operation_id:u32` | 第 7 节任务结果 |
| 0x10 | GET_PARAMETER | `parameter_id:u16` | `parameter_id:u16, reserved:u16=0, actual:u32, requested:u32, config_revision:u32, operation_id:u32` |
| 0x11 | SET_PARAMETER | `parameter_id:u16, reserved:u16=0, value:u32, expected_revision:u32` | 同 GET_PARAMETER；需等待时 status=PENDING |
| 0x12 | GET_EFFECT_CHAIN | 无 | `expected_or_actual_revision:u32, enabled:u8, count:u8, e0:u8, e1:u8, e2:u8, reserved:byte[3]=0` |
| 0x13 | SET_EFFECT_CHAIN | 同 GET_EFFECT_CHAIN，revision 为预期值 | 同 GET_EFFECT_CHAIN，revision 为已生效值 |
| 0x20 | REC_START | `format:u8=1, source:u8=0, flags:u16=0, max_frames:u32` | `operation_id:u32, recording_id:u32`，status=ACCEPTED |
| 0x21 | REC_STOP | `boot_id:u64, recording_id:u32` | `operation_id:u32, recording_id:u32`，status=ACCEPTED |
| 0x22 | REC_INFO | `recording_id:u32`，0 表示当前槽 | 第 7 节录音元数据 |
| 0x23 | REC_CLEAR | `boot_id:u64, recording_id:u32` | `recording_id:u32`，仅清除完成后 status=APPLIED |
| 0x30 | REC_OPEN | `boot_id:u64, recording_id:u32, offset:u32` | `transfer_id:u32, object_bytes:u32, object_crc32:u32, accepted_offset:u32, chunk_limit:u16, window:u8=1, reserved:u8=0` |
| 0x31 | REC_READ | `transfer_id:u32, offset:u32, length:u16, reserved:u16=0` | `transfer_id:u32, offset:u32, length:u16, reserved:u16=0`；另在 Transfer 发送数据 |
| 0x32 | TRANSFER_ACK | `transfer_id:u32, next_offset:u32, block_crc32:u32` | `transfer_id:u32, next_offset:u32` |
| 0x33 | REC_CLOSE | `transfer_id:u32, object_crc32:u32` | `transfer_id:u32` |
| 0x34 | TRANSFER_CANCEL | `transfer_id:u32` | `transfer_id:u32` |

SUBSCRIBE mask：bit0 周期演奏状态，bit1 周期录音状态，bit2 参数变化事件，bit3 故障变化事件；其他位 0。相应 CCCD 未开启时订阅对应类别返回 INVALID_STATE。周期为 0 表示关闭，否则 status 为 100–1000 ms、record 为 1000–10000 ms；实际周期以响应为准。关键任务完成事件不受 mask 屏蔽，仍要求 Response/Event CCCD。

### 参数 ID

| ID | 名称 | 值域与规则 |
|---|---|---|
| 0x0001 | MASTER_VOLUME | 0–127，实际应用保留现有增益平滑 |
| 0x0002 | SYNTH_MODE | 0=A，1=B，2=C；等待声部释放时返回 PENDING |
| 0x0003 | TIMBRE_PROFILE | 0=笛，1=弦，2=铜管，3=马林巴，4=钢琴；业务适配需显式映射到现有 profile/program |
| 0x0004 | OUTPUT_ROUTE | 0=立体声，1=仅左，2=仅右，3=静音 |
| 0x0005 | VIBRATO_DEPTH | 0–127 |
| 0x0006 | GLIDE | 0–127 |
| 0x0007 | EFFECT_MASTER | 0/1；关时保留已选效果及顺序 |

支持参数读不等于每个参数已支持写；未实现的 ID 返回 UNSUPPORTED。参数表新增项目需版本化，不能复用旧 ID 改变含义。第一版不提供任意寄存器读写。

效果链：e0–e2 使用 0=delay、1=chorus、2=reverb；count 为 0–3，前 count 项不得重复，剩余项固定 0xFF。enabled 为 0/1；count＝0 时 enabled 必须为 0。整条链在音频域可接受的样本边界原子提交，不能逐个“按键切换”。

config_revision 初始为 1；Push/MIDI/蓝牙接受一次有效设置事务均加 1，跨过 0 后从 1 继续。SET 必须携带精确 expected_revision，不提供无条件写哨兵值。等待模式切换的请求在被接受时保留 requested 并推进 revision；完成时 actual 更新再次推进 revision。已有同一参数待生效时其他修改返回 BUSY，避免悬挂任务被静默替换。

## 6. 录音模型

首版格式 1：48,000 Hz，2 声道，有符号 PCM16 little-endian，交错顺序 L0、R0、L1、R1。source＝0 表示实时合成经效果/输出路由后的信号。TF 输出来源或非 48 kHz 输出时 REC_START 返回 INVALID_STATE。

max_frames＝0 表示以设备当前可用容量为上限；非零值不得超过设备公布的 capacity_frames。录音对象身份由 `(boot_id, recording_id)` 唯一确定；recording_id 在一次启动内递增，0 保留，不复用；耗尽时拒绝新建对象。客户端开始上传/续传前必须重新读取 boot_id。

状态值：0 EMPTY、1 STARTING、2 RECORDING、3 FINALIZING、4 READY、5 ERROR。下载是 READY 对象的只读引用，不改变录音状态，客户端由 transfer_id 判断是否正在下载。

录音开始/停止都以完整立体声帧为边界。容量满自动封存，录音不循环覆盖。断连继续录音；设备复位使 DDR 临时录音失效。READY 为不可变对象，未显式 CLEAR 不能开始另一段。开始/停止任务进行中重复请求返回该任务的最新状态；使用新 ID 的重复 START 在已有对象时返回 INVALID_STATE，不能隐式新建。

### REC_INFO 响应：固定 48 字节

依序为 `boot_id:u64, recording_id:u32, state:u8, format:u8, channels:u8, flags:u8, sample_rate:u32, frames:u32, pcm_bytes:u32, capacity_frames:u32, object_crc32:u32, stop_reason:u16, fault_detail:u16, operation_id:u32, reserved:u32=0`。

flags：bit0 incomplete，bit1 crc_valid，bit2 transfer_open，其余 0。录音过程中 frames/pcm_bytes 只统计已提交存储的数据，来自一致快照；封存后 pcm_bytes＝frames×4。EMPTY 时 recording_id、长度、CRC、operation_id 均为 0；状态、格式和容量字段仍有效。仅 READY 时 crc_valid＝1。

stop_reason：0 NONE、1 USER_STOP、2 CAPACITY_REACHED、3 FIFO_OVERFLOW、4 STORAGE_TIMEOUT、5 STORAGE_IO_ERROR、6 SOURCE_CHANGED。3–6 置 incomplete，尽可能排空并封存可证明连续的前缀；可完成封存时进入 READY，否则 ERROR 且拒绝下载，等待 CLEAR。

## 7. 后台任务与关键事件

operation_id 为设备本次启动内非零递增 u32，不复用；最多同时保留 8 个任务记录，其中未完成记录不可淘汰，完成记录至少保留 60 秒。资源不足返回 BUSY。任务执行状态通过 GET_OPERATION 和 opcode＝0xE0 的关键事件读取同一布局：

`operation_id:u32, original_request_id:u32, original_opcode:u8, state:u8, result_status:u8, reserved:u8=0, config_revision:u32, recording_id:u32`。

state：0 QUEUED、1 WAITING、2 DONE、3 FAILED；result_status 使用第 4 节状态码，DONE 应为 OK。关键事件 request_id＝0，携带当前 nonce。未知或已过期 operation_id 返回 OBJECT_GONE。

模式 SET、REC_START、REC_STOP 返回任务 ID，任务只有在实际生效/首个帧启动/录音封存后才完成。客户端收到 ACCEPTED/PENDING 后每 1 秒查询任务，直到终态；长期等待时可以降低查询频率，但不能将“查询超时”视为动作未发生。REC_INFO 仍是对象状态的最终依据。普通参数已立即生效时 operation_id＝0；GET_PARAMETER.requested 无待生效任务时等于 actual。

## 8. 详细状态与事件

GET_STATUS 响应以及 opcode＝0xE1 的 Status Notify 使用相同固定 64 字节 payload：

`snapshot_id:u32, device_time_ms:u32, valid_mask:u32, config_revision:u32, requested_mode:u8, actual_mode:u8, profile:u8, master_volume:u8, route:u8, effects_enabled:u8, effect_count:u8, effects:byte[3], active_voices:u8, record_state:u8, recording_id:u32, recorded_frames:u32, capacity_frames:u32, left_peak:u16, right_peak:u16, flags:u32, deadline_miss:u32, underrun:u32, note_drop:u32, record_drop:u32`。

valid_mask：bit0 设置字段（含 revision、模式、profile、音量、路由和效果），bit1 声部，bit2 录音字段，bit3 电平，bit4 四个故障计数；其余 0。snapshot_id/device_time 始终有效。无效分组字段填 0，客户端必须检查 valid_mask。

flags：bit0 mode_pending，bit1 clip，bit2 incomplete，bit3 control_window_open，其余 0。flags 中前三位的有效性分别跟随设置、电平、录音分组，控制窗口位始终有效。峰值按采样窗口内绝对幅度统计，0 静音、65535 满幅并饱和，窗口从上次成功锁存到本次锁存，不逐次累加已发送峰值。

设备时间为本次启动内 u32 ms，约 49.7 天回绕；客户端用模 2^32 差值处理。snapshot_id 同样回绕；分片完成后以序号比较丢弃旧快照，跨重连清空比较基准。

参数变化和故障变化分别用 opcode 0xE2 / 0xE3 在 Response/Event 发送相同快照布局，request_id＝0。事件可合并到最新快照；故障累计计数和 GET_STATUS 负责恢复遗漏。故障计数饱和于 0xFFFFFFFF，不回绕成“无故障”。

## 9. 文件下载、确认与续传

第一版仅允许一个 transfer_id、一块在途 PCM，窗口＝1；对象必须 READY 且 crc_valid＝1。offset 和 length 都是 PCM 字节偏移，不含 WAV 文件头，并须为 4 的倍数；0≤offset≤pcm_bytes，0<length≤min(256, pcm_bytes−offset)。offset＝EOF 时允许 OPEN，但不允许 READ。

1. REC_OPEN 验证 boot_id/recording_id 并占用对象引用；返回对象长度、整体 CRC、接受的 offset。重连续传可从任一合法帧边界打开，但客户端须先比对对象身份、格式、总长度和整体 CRC。
2. REC_READ.offset 必须等于服务端当前已确认 offset。返回 OK 后按同一 request_id 在 Transfer 特征发送 opcode＝0xD0 的逻辑消息，payload 为 `transfer_id:u32, boot_id:u64, recording_id:u32, offset:u32, data_length:u16, reserved:u16=0, block_crc32:u32, data:byte[data_length]`。块 CRC 只覆盖 data。
3. 服务端保留未确认块。重复同一 READ 请求重新发送相同数据，不能推进 offset；在未确认时发其他 READ 返回 BUSY。客户端收到重复块覆盖同一 offset，并重新确认，不追加。
4. 客户端验证逻辑 CRC、身份、offset、长度和 block_crc 后写入临时文件，发送 TRANSFER_ACK，其中 next_offset＝offset＋data_length。服务端只在匹配当前块及 CRC 后推进 offset。
5. 设备保留最近一次已确认块的结束 offset 与 CRC，重复相同 ACK 返回相同结果，即使 ACK 使用新 request_id 也不再次推进。其余不匹配返回 TRANSFER_CONFLICT，并在错误 payload 的 detail 中返回 0。
6. 客户端等待数据块超时 3 秒，先重发原 READ。ACK 响应丢失时优先重发原 ACK，避免误认为窗口仍占用。每步最多自动重试 3 次，再断连恢复。设备不因传输慢而停止音频。
7. 客户端完成所有字节后计算整体 CRC32；REC_CLOSE 要求已确认 offset＝总长度且客户端提交 CRC 与对象一致，成功后释放引用。失败保留引用，客户端可取消后重开校验。
8. CANCEL 只释放传输引用并丢弃在途块，录音对象保留。无传输活动 30 秒自动释放引用；断连立即释放。CLEAR 在下载引用存在时返回 BUSY。
9. 客户端保存续传清单：boot_id、recording_id、格式、总长度、整体 CRC、已持久写入的连续 offset。ACK 前应将对应数据和恢复 offset 可靠保存；客户端重启后从本地可证明存在的连续前缀重新 OPEN。boot_id 变化或对象不存在，旧续传清单失效。

首版无需把 WAV 头存入 FPGA。客户端下载成功后封装标准 44 字节 PCM WAV：RIFF size＝36＋pcm_bytes，audio_format＝1，channels＝2，sample_rate＝48000，byte_rate＝192000，block_align＝4，bits_per_sample＝16，data size＝pcm_bytes。整体和分块 CRC 均不包括 WAV 头。incomplete 对象允许导出已封存前缀，客户端必须显示录音中断原因。

## 10. 规范测试向量

HELLO：major＝1、minor＝0、request_id＝1、session_nonce＝0x0102030405060708。逻辑消息 24 字节：

```text
01 00 04 00 01 00 00 00 08 07 06 05 04 03 02 01
01 00 00 00 90 4b 7a da
```

CRC32＝0xDA7A4B90。message_token＝1 的两个 Command Write 特征值分别为：

```text
b1 01 00 00 01 0e 01 00 04 00 01 00 00 00 08 07 06 05 04 03
b1 01 00 01 02 0a 02 01 01 00 00 00 90 4b 7a da
```

联调验收至少包含：该向量逐字节匹配；CRC 错误不执行；37 片边界与 513 字节拒绝；跳片/重复片；缓存内重试仅执行一次；旧 nonce 拒绝；revision 冲突；模式等待后生效；录音容量满与故障封存；READ/ACK 丢响应重试；重启后旧对象拒绝；客户端下载 WAV 的左右声道、帧数、总字节与 CRC 一致。

## 11. 实现依赖与开发边界

该协议需要新增业务 GATT、boot_id 来源、常驻 BLE 生命周期、命令/响应 CDC、绝对值效果链接口、任务查询、连续录音 DMA、整体 CRC 及客户端状态机。默认分片和队列大小均有上界，不能以扩展无界 RAM 应对背压。

完整工作站 BLE/DDR 时序、设备供电与接线、138K 射频链路、音频回归均需分别验收。控制窗口只限制何时接受写入，不提供加密或身份认证；常开控制与认证需求进入后续协议版本。协议定义本身不代表这些依赖已经实现。
