# 可选 OPEN_WIDE 下载扩展（0.2.3）

在 ACK_READ 和 L2CAP 连接参数优化基础上，增加可选 `OPEN_WIDE=0x36`。仅由新客户端主动选择460字节PCM块，减少命令往返、块头与检查点持久化次数。音频内容、采样格式、CRC32和逐块可靠确认不变。

本轮32768字节同板基线2952字节/秒，460字节SRAM首测3722字节/秒、Flash重载后3535字节/秒（+19.7%）。APP Kotlin完整192000字节下载及WAV由72.32秒降至58.27秒（耗时 -19.4%），包含取消、断线恢复和已执行响应丢失后的重试等待。另试456字节对齐测得3709字节/秒，未观察到收益，保留460；单次探索不代表统计等价。

## 格式与范围

请求与原OPEN完全相同，payload16字节、小端：`boot_id:u64, recording_id:u32, offset:u32`。成功响应payload20字节也与原OPEN相同：`transfer_id:u32, total_bytes:u32, object_crc:u32, accepted_offset:u32, max_chunk:u16, window:u8, reserved:u8=0`，本命令回复max_chunk=460、window=1。响应回显opcode0x36。

原OPEN0x30仍回复256字节，Capability仍flags0x68、max_chunk256、window1。宽块标志只属于本次传输；重新用原OPEN会恢复256上限。仍只允许一个活动传输，要求录音READY、对象身份正确、Transfer CCCD启用、offset4字节对齐且不越界。错误码及精确请求缓存沿用OPEN。相同ID重放相同响应，不重复分配传输。

打开后继续使用原READ0x31、ACK_READ0x35、ACK0x32、CLOSE0x33及CANCEL0x34。READ/ACK_READ只在宽块传输中允许4..460且4字节对齐；错误下一块长度或前块CRC不会提交ACK。重试必须使用相同ID和相同逻辑字节。首块READ，末块独立ACK后CLOSE。

460字节PCM加28字节DATA块头、16字节逻辑头和4字节逻辑CRC，总长度508字节，仍在512字节逻辑报文和现有9位传输计数器内。继续B1分片，最多37片，每片最多14字节数据。没有提高ATT MTU、扩大业务窗口、压缩音频或跳过CRC。选择460也避开464+48=512在9位长度字段中回绕的问题。

## APP与旧版兼容

APP0.2.3每次OPEN优先尝试OPEN_WIDE。仅明确UNSUPPORTED0x80才停用本连接的大块探测并回退原OPEN；BUSY、对象失效、范围或超时不改为另一条OPEN。超时仍同ID重试，防止已经打开的传输被重复分配。新连接重新探测。

APP按成功OPEN的opcode和max_chunk验证范围：原OPEN最大256，OPEN_WIDE最大460；PCM解析的默认上限仍256，只有明确打开宽块传输才显式放宽到协商上限。完整逻辑CRC、每块CRC和完整对象CRC都保留。

仍须先可靠写PCM并持久化原子检查点，再允许下一条ACK_READ。检查点记录字节偏移和前缀CRC，要求4字节对齐，不要求256或460的整数倍。因此升级APP前的256字节检查点可继续使用宽块；反向用旧APP续传也能从宽块留下的4字节对齐偏移打开普通传输。

## 验证与证据

RTL定向覆盖最大508字节DATA和CRC、宽OPEN精确重放不重分配、宽块READ/ACK_READ重放、不合法长度/CRC不提交ACK，以及切回普通OPEN恢复256上限。Android增加宽OPEN超时同ID重试、一次探测后回退、BUSY不回退，以及508字节逻辑报文37片重组与显式PCM范围/CRC检查。

实板固定字节数对照、完整APP下载、新旧固件兼容、跨块大小续传、Flash资格及最终APK见 [本轮汇总](../reports/speed5_20261020/summary.json)。电脑桥接仅传递GATT字节，逻辑协议和持久化由APP Kotlin执行；手机原生GATT/UI及实际速度仍需安装APK验收。

原有启动标识重复限制未解决：上一轮JTAG重载曾出现boot_id重复，初始化源码未改。板卡重启或重配置后，先删除手机未完成下载，再开始新录音；不能将同次启动内续传通过扩大为跨重启身份唯一的保证。
