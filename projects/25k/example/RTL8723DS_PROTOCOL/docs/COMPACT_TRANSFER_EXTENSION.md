# 可选紧凑 DATA 分片扩展（APP 0.2.4）

`OPEN_COMPACT=0x37` 是 25K 的可选下载扩展。它沿用 OPEN_WIDE 的 460 字节 PCM 块，只有 Transfer 特征上的 DATA 改用 B2 分片。Command、Response、Status 继续使用 B1，Capability 仍报告 ATT value20、逻辑上限512、普通块256、window1、flags0x68。ATT MTU23、UART921600/8E1、15ms连接参数请求保持原值。

## 协商和兼容

请求 payload16 字节与原 OPEN 相同：`boot_id:u64, recording_id:u32, offset:u32`，小端。成功响应回显 opcode0x37，payload20 字节：`transfer_id:u32, total_bytes:u32, object_crc:u32, accepted_offset:u32, max_chunk:u16=460, window:u8=1, reserved:u8=0`。

APP 每个连接按 0x37 → 0x36 → 0x30 顺序探测。只有明确 UNSUPPORTED0x80 才允许退到下一协议，并停用本连接的失败探测；BUSY、对象失效及超时不能切换 OPEN。超时仍重发相同 ID、相同逻辑字节。普通 OPEN0x30 和 OPEN_WIDE0x36 的传输继续 B1，旧 APP 不会收到 B2。

紧凑标志属于活动传输。重新用普通 OPEN/OPEN_WIDE 打开会恢复 B1；断线释放传输。APP 在接收协程收到成功 OPEN 响应时更新解析配置、清除旧 Transfer 重组器，再将响应交给下载流程。未明确选择 0x37 时，Transfer 重组器拒绝 B2。

## B2 字节格式

每条 ATT 通知 value5..20 字节，四字节头之后是1..16字节逻辑数据：

| 偏移 | 字段 |
|---|---|
| 0 | marker=0xB2 |
| 1..2 | token:u16，小端；同一逻辑报文不变 |
| 3 bit0..5 | index，0..31 |
| 3 bit6 | FIRST，且仅 index0 置位 |
| 3 bit7 | LAST，最后一片置位 |
| 4.. | 逻辑数据；长度由 ATT value 长度减4得到 |

非末片必须正好16字节。末片可以包含完整16字节。512字节逻辑上限不变；本项目最大 DATA=460 PCM+48字节头/CRC=508字节，B2 共32片，最后一片12字节；B1 同报文37片。保留16位 token、FIRST/LAST、顺序校验、逻辑 CRC32、块 CRC32、对象 CRC32、nonce 和 request_id。

每个特征独立重组。完全相同的连续重复片可忽略；相同位置的不同字节、丢片、越界、B1/B2 混入同一报文都使当前报文失效，必须等待新的 FIRST。APP 沿用2秒重组超时。token 可以回绕，逻辑 nonce、request_id 和 CRC 仍必须匹配。

## 可靠下载

READ0x31、ACK_READ0x35、ACK0x32、CLOSE0x33、CANCEL0x34 的逻辑格式和提交条件不变。APP 仍先可靠落盘 PCM、持久化原子检查点，再发送下一条 ACK_READ；失败响应不能提交 ACK。重放 DATA 保留相同逻辑字节，允许重新分片时使用新的 token。

检查点按字节偏移和前缀 CRC 记录，要求4字节对齐。因此 B1/256、B1/460 与 B2/460 可以从同一个有效检查点继续，不要求块大小整除偏移。音频没有压缩，窗口仍为1。

## 验证范围

RTL 直接检查最大508字节、完整16字节末片、最小4字节 PCM 对应52字节报文，验证同步 RAM 延迟、每条 ACL/L2CAP/ATT 长度、token、flags、片数，并切回 B1 检查37片。录音回归分别以0x36和0x37运行，覆盖精确重放、ACK 原子拒绝和普通 OPEN 恢复。

Android 和 Python 重组器覆盖1..512字节、token边界、重复、丢片、冲突、混入版本及恢复。Android 会话测试还覆盖 OPEN 超时、B2 DATA 丢片后的同 ID 重试、旧固件一次回退、BUSY 不回退。实板测量与最终资格见 [第六轮报告](../reports/speed6_20261020/README.md)。

历史 boot_id 重复问题未修复；重启或重配置板卡后，应丢弃手机未完成下载再开始新录音。电脑桥接测试使用真实 APP Kotlin 协议和文件代码，但不能代替原生 Android 手机 GATT/UI、后台行为或手机吞吐验收。Flash 重载也不能代替物理断电上电测试。
