# 25K / Android 0.2.6 DATA成功回执下载联调

2026-10-20，Android **0.2.6 / versionCode9**，包名 `cn.gowin.control`，最低Android8。OPEN_DIRECT0x39将已验证的DATA同时作为成功READ/ACK_READ回执，省去每块的独立成功Response。错误、其他命令、旧模式保持原响应；CRC、会话、对象与范围校验、精确重传、先可靠落盘再ACK均保留。

同一候选固件三组交替测速、每次32768字节，原B3 **5436 → 新模式6407 B/s（+17.9%）**；最终Flash重载后单次6278 B/s。相同APP在旧B3固件和新固件上的完整192000字节下载分别42.8643/35.3344秒，耗时降低17.6%，两份WAV与参考逐字节一致。完整下载计时从首个OPEN成功开始，包含取消/重开、断线续传、已执行请求回执丢失重试和WAV保存；启动阶段INFO命令片丢失检查在计时之前。电脑BLE结果不能替代手机速率验收。

## 手机操作

1. 安装 [0.2.6 APK](../artifacts/gowin-control-0.2.6-gw25k-direct-debug.apk)，可覆盖原调试签名版本并保留作品。
2. 板卡供电，在APP扫描并选择 **GW25K-PROTO**。授予附近设备权限；Android8–11还需定位权限及定位服务。
3. 录音页最大时长保留 **0**，开始录音，等“可下载”后点击“下载 / 继续”。音源为FPGA内置的1秒双声道提示音。
4. 到作品页试听、导出或分享。普通断线可以重连并继续下载；再次录音前清除设备录音，手机作品保留。
5. **板卡重启或重配置后，先删除手机未完成下载，再开始新录音。** 历史启动标识重复仍未解决。

APP发现服务后请求MTU247；本轮电脑实际185/value182。每连接按0x39→0x38→0x37→0x36→0x30探测，仅UNSUPPORTED0x80允许回退；BUSY、超时和损坏元数据不能降级。成功OPEN先设置重组器和对象信息再发布成功。未选择0x39时，DATA不能替代独立Response。

选择0x39后，DATA只有通过逻辑CRC、nonce/请求ID、PCM CRC、transfer_id/boot_id/recording_id、偏移/长度及对象范围验证，才能作为读取成功。APP仍校验并可靠保存PCM和原子检查点后再ACK_READ；末块独立ACK，完整CRC通过后CLOSE。检查点4字节对齐，可跨五种模式续传。格式见[DATA回执扩展](DIRECT_TRANSFER_EXTENSION.md)及[B3扩展](BULK_TRANSFER_EXTENSION.md)。

## 匹配版本

| 项目 | 结果 |
|---|---|
| APK | `artifacts/gowin-control-0.2.6-gw25k-direct-debug.apk`，9703423字节，versionCode9 |
| APK SHA256 | `3b6bc5b6978a9df6e25d6d0d0eb6b443b9a87b6d01557e369843cd3910185250` |
| 调试证书 SHA256 | `dc39e7120615a53f0bdf18629a361f0ebbf055d36c3b82f48adaf01cdae878ca` |
| 固件 | `builds/20261020_070638_494400/impl/pnr/ble_protocol.fs` |
| 固件 SHA256 | `c772c4b9783ccba175a0a8ec231cd4465019cc4415b17f3398409c891ad9b6f6` |
| UserCode / Status | `0000EC9B` / `70022020` |
| Flash | cable1/channel0，2.5MHz，写入校验、重载和身份读回通过 |
| 时序 | 50MHz，Fmax50.016MHz，setup/hold0/0，最小setup slack0.006ns |
| 资源 | 17015 LUT，9230 Register，11020/11520 CLS（96%），34/56 BSRAM |
| 传输 | UART921600/8E1，ATT23..247，电脑实测185，460字节PCM、单窗口、15ms请求 |
| 音频 | 48kHz、双声道、PCM16；48000帧、192000字节PCM、192044字节WAV |
| PCM CRC32 | `A54A47B0` |
| WAV SHA256 | `2c492fa12189698f5abf3032cfd97aa322e8c4df5456b37f0c7bf56800d760ed` |

## 验收与限制

[第九轮报告](../reports/speed9_20261020/README.md)和[汇总](../reports/speed9_20261020/summary.json)保存全部证据：23组RTL/主机回归、32项Android普通测试及Lint0；APP Kotlin新模式完整音频及DATA回执丢失重传；新APP连接上一版B3固件每连接一次回退及原Response丢失重传；原始抓包核查全部PCM/CRC、相同请求和成功响应省略；五种下载格式跨模式续传；Flash测速、录音错误原子拒绝/重放/重连、旧控制协议。

手机原生GATT/权限/UI/后台与实际速率未测，本镜像未物理断电验收。最小setup slack仅0.006ns，后续RTL改变必须重新构建并验收时序。音源为FPGA内置测试音频，未接入手机麦克风或外部实时输入，音频未压缩。历史同镜像JTAG重载boot_id重复问题仍保留，见[原始记录](../reports/speed3_20261020/boot_identity_limitation.json)。

历史：[0.2.5大MTU](APP_INTEGRATION_0_2_5_BULK.md)、[0.2.4紧凑分片](APP_INTEGRATION_0_2_4_COMPACT.md)、[0.2.3宽块](APP_INTEGRATION_0_2_3_WIDE.md)。

Android使用JDK17、SDK35、Build Tools35.0.0，在 `clients/android` 执行：

```sh
sh gradlew :core:protocol:test :core:ble:testDebugUnitTest :core:data:testDebugUnitTest :app:assembleDebug :app:lintDebug
```

本例目录执行 `sh run_sim.sh`、`sh build.sh`。`reports/ready_build.json`固定指向已固化并无线复验的镜像；新构建使用 `reports/last_build.json`，不会自动改变该交付索引。
