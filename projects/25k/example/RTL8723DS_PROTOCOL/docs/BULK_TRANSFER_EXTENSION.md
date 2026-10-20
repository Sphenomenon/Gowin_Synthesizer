# 可选 OPEN_BULK / B3 大通知下载（APP 0.2.5）

`OPEN_BULK=0x38` 选择460字节PCM块，以及按本连接ATT MTU分片的B3 DATA。服务器最大ATT MTU247，默认23。新APP在发现服务后请求247；中央可协商较小值，本轮macOS实际ATT185、通知value182。没有协商MTU时仍可使用value20的B3。所有Command、Response、Status继续原B1；原OPEN/OPEN_WIDE仍B1，OPEN_COMPACT仍B2/value20。

## OPEN格式与降级

请求payload16字节与其他OPEN相同：`boot_id:u64, recording_id:u32, offset:u32`，小端。成功响应回显0x38，payload24字节：

| 字段 | 类型 | 含义 |
|---|---|---|
| transfer_id | u32 | 非零传输ID |
| total_bytes | u32 | 封存音频字节数 |
| object_crc | u32 | 完整PCM CRC32 |
| accepted_offset | u32 | 接受的字节偏移 |
| max_chunk | u16 | 460 |
| window | u8 | 1 |
| reserved | u8 | 0 |
| value_limit | u16 | 当前ATT MTU减3，20..244 |
| reserved | u16 | 0 |

Capability仍报告v1/value20/logical512/flags0x68/chunk256/window1。value_limit仅授权本传输的B3 DATA，不能扩展Command或Response分片。成功OPEN的格式、保留位、窗口和范围都必须验证。

每个连接按0x38 → 0x37 → 0x36 → 0x30探测，只有明确UNSUPPORTED0x80才停用该探测并进入下一项。BUSY、对象失效和超时不能切换OPEN。超时继续同ID、相同逻辑字节；APP在接收协程验证成功OPEN后，设置B3上限并清除旧Transfer重组器，再发布成功。旧固件仅需回复原有UNSUPPORTED。

## B3分片

每条通知value由4字节头和1..value_limit-4字节数据组成。头与B2同布局，marker改为0xB3：`marker:u8, token:u16 LE, tag:u8`。tag bit0..5是index，bit6 FIRST，bit7 LAST。FIRST仅用于index0；非末片必须填满协商容量；LAST可以填满。token保持16位，完整逻辑报文仍不超过512字节。不同特征分别重组，未通过OPEN_BULK协商的特征拒绝B3。

最大DATA仍是460字节PCM加48字节逻辑/块头和CRC，总508字节。在ATT185时容量178，共3片（178+178+152），value长度182/182/156；ATT247时容量240，也是3片。ATT23时容量16，共32片。逻辑nonce、request_id、所有CRC和逐块可靠确认均保留，没有音频压缩。

完整重复片可忽略；相同位置不同字节、丢片、B1/B2/B3混入当前报文、超出协商长度和超出512上限均使当前报文失效。APP仍使用2秒重组超时；请求层重新发送相同逻辑请求恢复。

## 完整ACL适配

`bt_acl_bridge.v` 位于初始化后的H5与GATT之间。GATT继续处理完整ACL+L2CAP PDU；桥接层在发送时按27字节HCI ACL data保守分段，第一包PB00、续包PB01，保持connection handle。初始化验证控制器LE ACL data length至少27且缓冲数量非零。HCI命令原样通过。

每个物理ACL包单独消耗controller credit。只有匹配连接handle的NumberOfCompletedPackets事件恢复信用，计数饱和到初始化获得的控制器容量；H5确认本身不恢复ACL信用。上游GATT的原有PDU信用门控保留，桥接层负责实际分段后的信用边界。

接收端支持PB00/PB10首包、PB01续包，验证handle、广播位、ACL长度、L2CAP总长、容量和续包边界，再向GATT交付规范化完整包。重组内存与HCI事件内存分开，完整包可接收前允许HCI事件穿插；上游mailbox满时对H5施加背压。孤立/过长续包被丢弃，未完成包在2秒超时或断线后失效。收发缓冲采用同步BSRAM，并经过实际一周期RAM延迟测试。

服务器仅在一次连接内接受一次MTU交换，响应最大247，实际取max(23,min(peer,247))；新连接回到23。Android的MTU请求被明确拒绝时继续ATT23，操作超时则关闭不确定的GATT会话并由用户重连，避免与后续GATT操作重叠。

## 可靠性与验收范围

READ、ACK_READ、ACK、CANCEL、CLOSE和对象格式不变。APP仍先可靠保存PCM及原子检查点，再确认或发送下一条ACK_READ。检查点偏移只需4字节对齐，可在普通256、宽460、紧凑B2和B3间续传。

RTL覆盖27字节分段、物理信用耗尽/恢复/饱和、多连接完成事件、完整247字节ATT接收与事件穿插、同步RAM、mailbox背压、孤立/过长/超时续包和断线。GATT按MTU23/64/247验证B3最大报文、末片、token及字节一致性；录音测试覆盖0x38响应元数据、重放及ACK原子拒绝。Python与Kotlin覆盖1..512字节及多种value_limit的重组、显式协商、长度/flags/混合版本/丢片/冲突；APP会话覆盖OPEN和DATA丢失后同ID重试、旧设备一次回退、BUSY与损坏元数据不能降级。

真实电脑BLE、APP Kotlin持久化/WAV、旧固件回退、最终Flash复验及详细测速见 [第七轮报告](../reports/speed7_20261020/README.md)。原生Android手机GATT/UI/后台及手机实际速率尚未验收。历史boot_id重复问题未修复，板卡重启/重配置后先删除手机未完成下载；Flash重载通过不能代替物理断电上电验证。
