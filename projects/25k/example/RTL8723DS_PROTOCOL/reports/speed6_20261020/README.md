# 第六轮：OPEN_COMPACT / B2 数据分片

已写入并校验 Flash、重载后复验通过，UserCode `9F4C`、Status `70022020`。配套 [APP0.2.4/code7](../../artifacts/gowin-control-0.2.4-gw25k-compact-debug.apk)。

同一候选固件、同板、32768字节 PCM，交替测量三次：

| 模式 | 吞吐样本（B/s） | 中位数 |
|---|---|---:|
| OPEN_WIDE / B1 | 3587、3581、3691 | 3587 |
| OPEN_COMPACT / B2 | 4177、4115、4309 | 4177 |

中位数提升 **16.5%**；Flash重载后单次测得 **4360 B/s**。完整APP Kotlin 192000字节音频含取消、断线持久续传、命令片丢失、已执行响应丢失重试和WAV保存，**59.37 → 55.31秒（耗时 -6.8%）**。两次均使用460字节块，在14720/29440字节处取消/断线。两份WAV与参考逐字节一致，SHA256 `2c492fa12189698f5abf3032cfd97aa322e8c4df5456b37f0c7bf56800d760ed`。

新命令0x37显式选择紧凑DATA：4字节分片头、每片最多16字节数据，将最大508字节报文从37片降为32片。保留16位token、FIRST/LAST、所有CRC、nonce、请求ID、持久化检查点和单窗口。Command/Response/Status仍B1；原OPEN和OPEN_WIDE仍B1；Capability仍256/0x68，旧APP继续兼容。新APP只在明确UNSUPPORTED时逐级回退0x36和0x30。

16组RTL/主机回归（含完整30147字节UART补丁模型）、22项普通Android测试和Lint0通过。实板完整APP下载、旧固件每连接一次回退、原始READ/ACK、256字节和460字节B1、B2重放/原子错误拒绝、跨三种协议的4字节对齐检查点续传，以及Flash重载后的录音/速度/旧控制协议均通过。原始回调逐片核查确认每个完整DATA确为32片，PCM/CRC一致。

7.5ms请求试验降到1851 B/s，未采用；最终恢复15ms。试验的UART模型仍固定预期15ms而报参数断言，属于未发布试验的记录。高频测试还触发一次既有8任务槽/60秒保留窗口BUSY，发生在PCM下载完成后的新START；等待窗口到期复测通过，原始失败保留。上述诊断不作为发布资格通过项。

固件 `builds/20261020_055737_599510/impl/pnr/ble_protocol.fs`，SHA256 `a9e3ab08b40f56c5d648dbc48daf24d69cc1d24947bb212d393368f3c7c42882`。APK SHA256 `f06a73a92f4893d6dd84166cc8d19cacc14f3e5ce00f2004c50fc84f0ac2aff6`，仍使用原调试证书，可覆盖安装。

历史boot_id重复未修复；本次SRAM/Flash标识不同不能证明唯一性。板卡重启/重配置后先删除手机未完成下载，再开始新录音。原生Android手机GATT/UI/后台及手机速度未测，新镜像未物理断电测试。

证据见 [summary.json](summary.json)、[交替测速](alternating_speed.json)、[通知逐片核查](notification_wire_check.json)、[APP原始协议核查](app_wire_check.json)、[完整WAV](complete_wav_check.json)、[Flash记录](flash.json)。协议格式见 [B2扩展](../../docs/COMPACT_TRANSFER_EXTENSION.md)。
