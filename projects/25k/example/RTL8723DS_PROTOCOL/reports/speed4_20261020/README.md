# 第四轮：L2CAP 外设连接参数协商

请求15ms连接间隔，替换上一版HCI连接更新路径。APP0.2.2源码和APK不变。固化后UserCode `EBE1`、Status `70022020`；Flash写入/校验、重载及无线复验通过。

| 测量 | 32768字节时间 | 吞吐 |
|---|---:|---:|
| 本轮同板基线 | 20.43s | 1604 B/s |
| 新固件SRAM | 10.86s | 3017 B/s |
| 新固件Flash重载 | 10.73s | 3055 B/s |

固化后较基线 +90.5%。APP Kotlin完整192000字节及WAV由 135.22s 降到 72.02s（耗时 -46.7%）。两次均含取消、断线持久续传和已执行ACK_READ响应丢失后的同ID重试；WAV与参考逐字节一致。

14组RTL/主机回归（含完整30147字节补丁）通过。新L2CAP信令检查覆盖正确ACL信用、接受/拒绝不回环、重复订阅只请求一次。实板组合命令、旧READ/ACK、旧确认写入协议、Flash后复验通过。实际链路层间隔未直接读取；回调间隔约28→13ms只是间接证据。手机原生GATT/UI及实际速率未验收。

固件 `builds/20261020_051436_956875/impl/pnr/ble_protocol.fs`，SHA256 `7ecbcf6012942f0c430c79e9e30ab47af4650fa1cbc0e0f140f2f2a834288a98`。APK `artifacts/gowin-control-0.2.2-gw25k-ack-read-debug.apk`，SHA256 `bf48a9a2cf0192965dd4ff2b71d5f19bc8a26fe7ce0be149f9e1ba83be6cc22c`。

已知限制仍为上一轮同镜像重载可能重复boot_id；本轮一次重载boot_id不同且旧对象拒绝通过，不构成问题已修复的证明。板卡重启/重配置后先删除手机未完成下载再开始新录音。新镜像未做物理断电测试。

详见 [summary.json](summary.json)、[协议/调度说明](../../docs/L2CAP_SPEED_OPTIMIZATION.md) 和 [APP操作说明](../../docs/APP_INTEGRATION.md)。
