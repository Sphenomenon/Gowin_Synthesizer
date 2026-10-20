# 可选 OPEN_DIRECT / DATA 成功回执（APP 0.2.6）

`OPEN_DIRECT=0x39` 显式选择与OPEN_BULK相同的B3下载，同时将成功READ/ACK_READ的完整DATA作为该请求的成功回执。错误仍使用原Response特征，其他命令仍有Response。原0x30/0x36/0x37/0x38及旧APP行为保持原定义。

## 线格式

OPEN_DIRECT请求payload16字节：`boot_id:u64, recording_id:u32, offset:u32`。成功响应payload24字节，与[B3协议](BULK_TRANSFER_EXTENSION.md)相同：`transfer_id:u32, total_bytes:u32, object_crc:u32, accepted_offset:u32, max_chunk:u16=460, window:u8=1, reserved:u8=0, value_limit:u16, reserved:u16=0`。只在全部OPEN检查成功后提交本传输的direct模式；BUSY、对象或范围错误不改变模式。

Command仍B1/20字节，DATA仍B3，保留原逻辑消息头、请求ID、nonce、对象和块CRC、完整消息CRC。Capability仍v1/value20/logical512/flags0x68/chunk256/window1。无音频压缩，最大PCM460、逻辑512，服务器ATT MTU上限247。

成功READ0x31和ACK_READ0x35只发送原DATA0xD0；省略对应的成功Response。所有失败状态（>=0x80）、ACK、CLOSE、CANCEL、OPEN以及其他命令继续使用B1 Response。设备仍生成并缓存原成功响应，精确请求重试仍重放原响应语义及相同DATA，但direct模式不发送成功Response的线副本。

## 客户端验收与可靠性

每连接按0x39→0x38→0x37→0x36→0x30探测，仅明确UNSUPPORTED0x80允许回退。BUSY、超时及损坏元数据不能降级。OPEN_DIRECT丢失后重发相同ID和逻辑字节。接收协程验证OPEN响应后先设置B3重组器、当前对象和direct模式，再发布成功。

只有明确选择0x39，才允许DATA完成等待中的READ/ACK_READ。客户端须校验完整分片顺序/长度、逻辑CRC、nonce及请求ID、DATA状态、PCM CRC、transfer_id、boot_id、recording_id、请求偏移、请求长度和对象范围。任何不匹配都丢弃当前DATA并等待同请求重试；不能合成成功。其他下载模式仍等待原Response。

APP内部为已有下载器生成等价的读取成功结果（tid、offset、len、reserved16），这是已验证DATA的本地结果，不能当成收到独立Response的证据。电脑测试工具以 `response_synthesized_from_data` 标记此区别，原始通知另行保存。

收到DATA只表示当前读取成功。APP仍须先校验、可靠保存PCM和原子检查点，再ACK或发送下一条ACK_READ。ACK_READ只确认前一块并请求下一块，所有参数检查仍在ACK提交之前。末块须独立ACK，再校验完整对象CRC并CLOSE。单窗口、相同请求ID/逻辑字节重试、取消/断线续传规则保持。

## 验证范围

本扩展已完成[第九轮](../reports/speed9_20261020/README.md)电脑真实BLE和APP Kotlin验收；精确范围见该目录summary.json。`reports/ready_build.json`指向本轮已固化镜像并记录限制。手机原生GATT/UI/后台和实际速率需手机验收。
