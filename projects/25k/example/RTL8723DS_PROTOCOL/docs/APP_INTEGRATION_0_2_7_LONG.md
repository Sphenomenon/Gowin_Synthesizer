# 25K / Android 0.2.7 长音频块下载联调

Android **0.2.7 / versionCode10**，包名 `cn.gowin.control`，最低Android8。新固件支持OPEN_LONG0x3b，PCM块460→972，DATA逻辑上限512→1020；完整CRC、对象/会话、精确重传、可靠落盘后确认和单窗口保持。服务器最大ATT MTU247，电脑实测185/value182；单条ATT值和27字节HCI ACL大小保持。

最终固件三组交替32768字节下载：6408→8035 B/s，吞吐提升25.4%。同一APP在原EC9B和新96FB上的完整192000字节音频流程分别34.6310/31.2447秒，耗时降低9.8%；包含一次执行后DATA回执丢失重试、14720字节取消重开、29440字节断线恢复及WAV保存。启动INFO丢失一片命令的检查在计时之前。两份192044字节WAV逐字节匹配参考。电脑结果不能替代手机速率验收。

## 手机操作

1. 安装 [0.2.7 APK](../artifacts/gowin-control-0.2.7-gw25k-long-debug.apk)，同调试签名，可覆盖旧联调版并保留作品。
2. 板卡供电，在APP扫描选择 **GW25K-PROTO**。授予附近设备权限；Android8–11还需定位权限与定位服务。
3. 板卡刚重新配置过，先删除手机未完成下载。录音页最大时长保留0，开始录音，等“可下载”后点“下载 / 继续”。音源仍内置1秒双声道提示音。
4. 到作品页试听、导出或分享。普通断线可重新连接后继续；再次录音前清除设备录音，手机作品保留。
5. 板卡后续重启或重新配置后，仍需先删除手机未完成下载；历史boot_id重复问题未解决。

APP优先3b→39→38→37→36→30，仅明确UNSUPPORTED允许回退，每连接每项只探测一次。BUSY、超时与损坏元数据不降级。成功OPEN先验证全部元数据、配置B3重组器及对象范围，再发布成功。只有成功0x3b允许Transfer/B3接收1020字节及序号63；其他特征与旧模式保持512上限。大于512的消息必须是成功DATA。详见[长块扩展](LONG_TRANSFER_EXTENSION.md)。

DATA通过逻辑/PCM CRC、nonce/请求ID、对象身份、偏移/长度和范围验证后作为读取回执。APP先可靠写入PCM和原子检查点，再ACK_READ确认前一块；末块独立ACK、完整对象CRC通过后CLOSE。检查点4字节对齐，可跨六种下载模式续传。切回旧格式后重试缓存长请求返回明确状态错误且无DATA，原缓存成功项仍保留。

## 匹配版本

| 项目 | 结果 |
|---|---|
| APK | 0.2.7 / versionCode10，9668978字节 |
| APK SHA256 | `085a6c22b65c026a9eb83d0dd6a4183b24fd4d9c297d3fcdaa7ab94ab9b4970d` |
| 调试证书 SHA256 | `dc39e7120615a53f0bdf18629a361f0ebbf055d36c3b82f48adaf01cdae878ca` |
| 固件 | `builds/20261020_074629_026662/impl/pnr/ble_protocol.fs` |
| 固件 SHA256 | `155ac0f71ad9ae3ee3de265e682d7477c39ca486d551c462bbc5beb3d06b6ea2` |
| UserCode / Status | `96FB` / `70022020` |
| 时序 | 50MHz，Fmax50.506MHz，setup/hold0/0，最小setup slack0.201ns |
| 资源 | 17080 LUT，9237 Register，11034/11520 CLS（96%），34/56 BSRAM |
| 音频 | 48kHz、双声道、PCM16，48000帧、192000字节PCM，未压缩 |
| PCM CRC32 | `A54A47B0` |
| WAV SHA256 | `2c492fa12189698f5abf3032cfd97aa322e8c4df5456b37f0c7bf56800d760ed` |

## 验证与限制

完整证据和最终Flash状态见[第十一轮报告](../reports/speed11_20261020/README.md)。手机原生GATT、权限、UI、后台、实际速率与物理断电边界未新增验收。CLS使用96%，后续RTL改动需重新构建并验收时序。音源仅内置测试音频，未接入手机麦克风或外部实时输入。历史：[0.2.6 DATA回执](APP_INTEGRATION_0_2_6_DIRECT.md)、[0.2.5 B3](APP_INTEGRATION_0_2_5_BULK.md)。

构建使用JDK17、SDK35、Build Tools35.0.0，在 `clients/android` 执行：

```sh
sh gradlew :core:protocol:test :core:ble:testDebugUnitTest :core:data:testDebugUnitTest :app:assembleDebug :app:lintDebug
```

本例目录执行 `sh run_sim.sh`、`sh build.sh`。`reports/ready_build.json`指向已固化且实测的镜像，新构建不会自动更新交付索引。
