# 第三轮：ACK_READ 合并命令提速

已写入并校验 Flash、重载后读回 UserCode `8E1E`、Status `70022020`。当前可下载镜像索引为 `reports/ready_build.json`，匹配 APP 0.2.2 / code5。

同板同样 32768 字节：原 READ+ACK 29.01s / 1130 B/s，候选 SRAM 21.36s / 1534 B/s，固化后 20.40s / 1606 B/s（+42.2%）。APP Kotlin 完整192000字节及WAV：173.14s → 135.22s（耗时 -21.9%），两次均含取消及断线恢复；新固件测试额外丢弃已执行组合命令的完整响应，计入约3秒重试等待。WAV 与参考逐字节一致。

14组RTL/主机回归、14项普通Android测试和Lint通过。实板确认新APP对旧固件每连接只探测一次扩展后回退，旧READ/ACK可用于新固件；组合命令错误不提交ACK，同ID响应与数据重放通过。原始检查和范围见 [summary.json](summary.json)。手机原生GATT/UI及实际吞吐未测。

**已知限制：** 同一候选镜像JTAG重载后的boot_id与SRAM阶段相同，启动标识唯一性验收失败，见 [失败记录](flash_boot_identity_repeat.json) / [限制说明](boot_identity_limitation.json)。初始化源码与上一轮相同，原因未完全定位。该项不计入下载通过结果；新镜像未物理断电测试。板卡重启/重配置后先删除手机未完成下载，再开始新录音。同次启动内取消和断线续传已通过。

APK：`artifacts/gowin-control-0.2.2-gw25k-ack-read-debug.apk`，SHA256 `bf48a9a2cf0192965dd4ff2b71d5f19bc8a26fe7ce0be149f9e1ba83be6cc22c`。固件：`builds/20261020_044829_666386/impl/pnr/ble_protocol.fs`，SHA256 `6c55032a3f2c2a29bb68ce6f5c4d0a6620e78e7190409f80fdc87e3d0b4626f9`。
