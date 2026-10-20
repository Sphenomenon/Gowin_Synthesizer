# 25K / Android 0.2.10 蓝牙音频联调

当前配套为 [0.2.10 APK](../artifacts/gowin-control-0.2.10-gw25k-second-debug.apk)，固件A25D。协议见[二阶扩展](SECOND_TRANSFER_EXTENSION.md)，完整验收见[第十八轮报告](../reports/speed18_20261020/README.md)。包名`cn.gowin.control`，最低Android8，与旧联调版使用相同调试签名，可覆盖安装。

电脑同一镜像三组交替，一阶/二阶有效PCM吞吐中位 **14.11→22.09 KB/s（+56.6%）**。同一生产APP核心在旧C678与新A25D上完整192000字节流程 **18.65→14.15秒（耗时−24.1%）**，含DATA回执丢失重试、取消重开、断线恢复与WAV保存。Flash固化后复验13.72秒，三份192044字节WAV均与参考逐字节一致。电脑结果不能代替手机速率验收，压缩收益取决于音频内容。

## 手机操作

1. 覆盖安装上面的0.2.10 APK，保留手机作品。
2. 板卡供电，在APP扫描选择 **GW25K-PROTO**。授予附近设备权限；Android8–11还需定位权限与定位服务。
3. 板卡刚重新配置过，先删除手机未完成下载。录音页最大时长保留0，开始录音，等“可下载”后点“下载 / 继续”。音源仍为内置1秒双声道测试音。
4. 到作品页试听、导出或分享。普通断线可重新连接后继续；再次录音前清除设备录音，手机作品保留。
5. 板卡重启或重新配置后，仍需先删除手机未完成下载；历史boot_id重复问题未解决。

## 下载与兼容

优先OPEN_SECOND40，每块选择RAW、原一阶/k9或二阶/k5的较短编码，无损恢复原PCM。最多8112字节PCM/8160字节DATA，按ATT值限制最多64片B3；MTU23/value20时976字节PCM，电脑MTU185/value182时8112。原OPEN3d只允许RAW/codec10，旧31/35始终RAW，3e/3f即使在40会话中仍仅允许RAW/10。

APP仅明确UNSUPPORTED0x80才按40→3d→3c→3b→39→38→37→36→30回退，每连接每项只探测一次。BUSY、超时、损坏元数据不降级，成功40后READ41/ACK_READ42失败也不静默降级。成功OPEN先配置重组器与对象范围。扩展仅作用于Transfer/B3，超过512的消息必须是成功DATA，其他路径仍512。

完整逻辑/PCM CRC、规范编码、nonce/请求ID、对象身份、偏移/长度和总范围校验后才发布读取成功回执。APP先可靠写入PCM与原子检查点，再ACK_READ确认前块；末块独立ACK、完整对象CRC后CLOSE。偏移和CRC均以原PCM为准，九种格式可跨任意4字节对齐检查点续传。降级后缓存二阶读取返回0x8d，无DATA且保留游标/原成功缓存；重新OPEN40恢复相同编码。

业务窗口1、H5窗口1、UART921600/8E1保留。FPGA不使用测试音字典，不能缩小则RAW；参考192000字节PCM编码为80002字节，协议封装另计。

## 匹配版本

| 项目 | 结果 |
|---|---|
| APK | 0.2.10 / versionCode13，9685370字节 |
| APK SHA256 | `e94f8731787ad04435762ad26e9ba5f918f3240a296ea8cb1f29c535be785a3b` |
| 调试证书SHA256 | `dc39e7120615a53f0bdf18629a361f0ebbf055d36c3b82f48adaf01cdae878ca` |
| 固件 | `builds/20261020_095747_100259/impl/pnr/ble_protocol.fs` |
| 固件SHA256 | `18c34c97a7bbe233f12096818310bbd689cc6d688c0a1b8adc8c19818693248d` |
| UserCode / Status | A25D / 70022020 |
| 时序 | 50MHz、Fmax50.018MHz、setup/hold0/0，最小setup余量0.007ns |
| 资源 | 17557 LUT、9480 Register、11140/11520 CLS（97%）、37/56 BSRAM |
| 音频 | 48kHz双声道PCM16、48000帧、192000字节PCM，无损传输 |
| PCM CRC32 | `A54A47B0` |
| WAV SHA256 | `2c492fa12189698f5abf3032cfd97aa322e8c4df5456b37f0c7bf56800d760ed` |

Flash写入校验、重载、实板下载与原命令回归通过，`reports/ready_build.json`指向本版。手机原生Android GATT、权限、UI、后台、实际速率与当前镜像物理断电上电尚需单独验收。音源仅内置测试音，没有接入麦克风或实时外部输入。

历史：[第十七轮一阶无损](../reports/speed17_20261020/README.md)、[第十二轮大块RAW](../reports/speed12_20261020/README.md)、[0.2.7 LONG](APP_INTEGRATION_0_2_7_LONG.md)、[0.2.6 DIRECT](APP_INTEGRATION_0_2_6_DIRECT.md)。

## 构建

使用JDK17、SDK35、Build Tools35.0.0，在`clients/android`执行：

```sh
sh gradlew :core:protocol:test :core:ble:testDebugUnitTest :core:data:testDebugUnitTest :app:assembleDebug :app:lintDebug
```

本例目录执行`sh run_sim.sh`、`sh build.sh`。新构建不会自动更新交付索引；编程前必须运行`python3 program_sram.py --manifest reports/last_build.json --check-only`通过时序、哈希、器件与安全位门禁。
