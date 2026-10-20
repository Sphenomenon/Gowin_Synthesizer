# 25K 录音下载提速（2026-10-20）

后续已增加运行期 UART 921600，兼容本页的 APK 和协议，见 [第二轮提速](UART_SPEED_OPTIMIZATION.md)。本页保留第一轮原始测量。

本版沿用 v1 的 B1 分片、逻辑消息、256 字节 PCM 块、逐块 CRC、单块窗口和续传。新增可选的 ATT Write Command（无响应写入）传输方式，减少 READ/ACK 命令的逐片往返等待。原 Write Request 始终支持。

## 实测方法与结果

同一块板、同一台电脑、同一位置，连续下载 32 个 256 字节块（8192 字节），以纯传输时间比较，不包含录制、编译、连接。两次均逐字节比对参考音频。

| 项目 | 0.2.0 / 确认写入 | 0.2.1 / 无响应写入 |
|---|---:|---:|
| 8192 字节耗时 | 16.769 秒 | 7.919 秒 |
| 有效 PCM 吞吐 | 488.5 字节/秒 | 1034.4 字节/秒 |
| 每块 READ 到数据完成均值 | 338 ms | 188 ms |
| 每块 ACK 请求完成均值 | 186 ms | 60 ms |

该短测吞吐为原来的 **2.12 倍**。证据：[原版基线](../reports/speed_20261020/baseline.json)、[新版实板短测](../reports/speed_20261020/fast_salted_sram.json)。电脑使用 macOS BLE 字节桥；手机吞吐受实际射频、系统调度和存储影响，需用户安装 APK 验收。

## 协商、重试与兼容

- Command 声明属性由 0x08 扩展为 **0x0C**（Write + Write Without Response），UUID 和句柄不变。Capability flags 仍为 0x68，不借用非易失录音等能力位。
- 新 APP 在服务发现后检查 PROPERTY_WRITE_NO_RESPONSE，支持时使用 WRITE_TYPE_NO_RESPONSE；否则继续使用确认写入。每次写入仍经过串行系统操作，等待系统写入完成回调；不无界灌入手机 GATT 队列。
- 无响应写入不发 ATT 成功或错误响应；错误、忙、非法/乱序分片被丢弃。业务命令只有在完整长度、CRC、nonce、ID 验证后才执行。业务响应、DATA、块 CRC、整段 CRC 和持久检查点规则保持不变。
- 业务响应/数据超时先用同一 ID、相同逻辑请求、新分片 token 重试。连续两次超时后 APP 回退到确认写入，沿用原请求继续重试；缓存中的已执行动作不会因此重复执行。回退机制有虚拟时钟单元测试覆盖。
- 实测发现 macOS 曾保留旧的 0x08 属性，导致直接写入 0x52 无业务响应。新固件的静态随机地址在 boot_id 基础上加入数据库版本盐（低字节 XOR 0x5C、次字节 XOR 0x21，再施加合法静态地址约束），避开此前地址命名空间。地址仍随启动变化，boot_id 含义不变。重新扫描后发现 0x0C 并实测加速成功。
- 旧 APP 0.2.0 可继续用确认写入连接新固件；新 APP 0.2.1 连接旧固件时自动使用确认写入。v1 原协议快照保持冻结，本页明确记录可选 GATT 传输扩展。

## 验收记录

- [回归](../reports/simulations/20261020_040438_955825/result.json)：12 组通过，含 UART/H5 完整补丁模型下的 Write Request 与 Write Command 两条业务路径。
- [加速录音回归](../reports/speed_20261020/recording_fast_sram.json)：逐字节音频对比、READ 精确重放、错误/重复 ACK、清除 BUSY、取消与断线续传、EOF、CLOSE、手动 STOP 通过。
- Android 11 项普通单元测试及 Lint 通过，Lint 0 errors / 0 warnings。包含丢失两次业务响应后改用确认写入，并保证请求 ID 和内容完全不变的测试。

完整音频、Flash 与最终交付信息见 [APP 联调说明](APP_INTEGRATION.md) 和 [本轮汇总](../reports/speed_20261020/summary.json)。早期未加地址盐的 fast_sram / fast_sram_v2 是属性缓存诊断，保留为失败记录，不作为通过证据。

## 完整下载与固化后复验

APP 原始 Kotlin 完整 192000 字节下载（含 8192 字节取消重开、16384 字节断线续传）约 196.18 秒；额外主动丢弃一个命令分片，原 ID 重试恢复。生成 WAV 与参考逐字节一致。见 [完整下载](../reports/speed_20261020/kotlin_fast_sram.json) 和 [WAV 校验](../reports/speed_20261020/complete_wav_check.json)。

已写入 Flash 并重载，UserCode 4096 / Status 70022020；[录音复验](../reports/speed_20261020/flash_recording.json)和[原确认写入协议回归](../reports/speed_20261020/protocol_flash.json)通过。重载后 8192 字节纯下载为 8.790 秒、932.0 字节/秒，约原版 1.91 倍。两次新版短测为原版约 **1.9–2.1 倍**，如实保留无线波动，未挑选重测结果。见 [Flash 测速](../reports/speed_20261020/speed_flash.json)。

Flash 重载后旧对象被拒绝；新对象下载、取消/断线恢复及 STOP 再次通过。未实际断电，未宣称手机实测完成。
