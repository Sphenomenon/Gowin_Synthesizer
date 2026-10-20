# 可选 OPEN_LONG / 972 字节 PCM 块

`OPEN_LONG=0x3b`显式选择B3 DATA与DATA成功回执，并将本次传输的PCM上限提高至972字节，DATA逻辑长度上限为1020。所有Command、Response、Status及默认Capability仍使用原512字节逻辑上限；旧OPEN/WIDE/COMPACT/BULK/DIRECT行为及块上限保持。未采用的0x3a/B4试验不在交付协议中。

## 协商与边界

请求payload16字节沿用boot_id:u64、recording_id:u32、offset:u32。成功响应payload24字节沿用[OPEN_DIRECT](DIRECT_TRANSFER_EXTENSION.md)：tid、total、object_crc、offset各u32，max_chunk:u16=972、window:u8=1、reserved:u8=0、value_limit:u16=ATT_MTU−3、reserved:u16=0，小端。只有有效成功响应授权长DATA；客户端必须验证长度、保留位、窗口、块对齐、对象范围、请求offset及ATT值上限，再切换Transfer重组器并发布成功。

DATA保持原16字节逻辑头、28字节音频块头、原PCM字节和末尾CRC32。972+48=1020，计数与地址扩大到10位，缓冲为1024字节，避免1024在10位长度字段回绕。没有改变音频格式或压缩。B3仍4字节头、6位分片序号、FIRST/LAST和16位token；MTU23/value20时最大1020字节为64片，末片序号63。MTU185/value182时为6片，最高MTU247。单条ATT/HCI包大小不扩大。

仅成功OPEN_LONG选择的Transfer/B3重组器允许1020字节和序号0..63；其他B3仍512字节/序号0..31，B1/B2继续原限额。大于512的逻辑报文还必须是成功DATA0xD0；其他类型即使CRC正确也不能使用长消息。READ与ACK_READ请求保持原B1和完整原字段，读取长度4..972且4字节对齐；末块可更短。

## 可靠性与回退

DATA仍须通过完整逻辑CRC、PCM CRC、nonce/请求ID、transfer_id/boot_id/recording_id、偏移/长度和总范围检查，才能作为成功READ/ACK_READ回执。错误独立返回原Response。先可靠保存PCM和原子检查点，再ACK_READ确认前一块；末块独立ACK并校验完整对象后CLOSE。业务窗口1、H5窗口1、27字节物理ACL与8个控制器额度保持。

仅明确UNSUPPORTED0x80允许每连接按0x3b→0x39→0x38→0x37→0x36→0x30回退。BUSY、超时或坏元数据不降级；超时先重试相同逻辑ID和字节。连接重建后重新探测。972上限只用于当前传输，其他OPEN撤销长块授权；任意4字节对齐的持久化检查点可在六种格式间续传。

执行后丢失DATA时，既有精确请求缓存重建相同DATA且不再提交ACK。切回旧格式后重试先前缓存的>460字节READ/ACK_READ，返回0x8d、无DATA，不改变新传输的确认偏移，也不覆盖原缓存成功项。这避免长消息通过旧B1/512路径发送；重新打开长模式后仍可按缓存规则重放。

## 验收

本扩展的实板统计、交替测速、回归、APP完整WAV/丢包/续传、旧固件回退及最终Flash身份以[第十一轮报告](../reports/speed11_20261020/README.md)为准。诊断镜像只用于SRAM并已从交付源码撤除，legacy FFF1仍原BTST格式。手机原生GATT/UI/后台和手机实际吞吐单独验收。
