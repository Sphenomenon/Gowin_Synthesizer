# 25K / Android 0.2.4 录音提速联调

2026-10-20，Android **0.2.4 / versionCode7**，包名 `cn.gowin.control`，最低Android8。新增显式OPEN_COMPACT，460字节PCM块的DATA采用紧凑B2分片，将最大508字节报文由37片降为32片。相同候选固件交替测量三次，普通宽块中位数 **3587 → 4177 B/s（+16.5%）**；Flash重载后单次4360 B/s。完整APP Kotlin 192000字节含取消、断线续传、命令片丢失、已执行响应丢失重试及WAV保存，**59.37 → 55.31秒（耗时 -6.8%）**，WAV逐字节一致。电脑桥接测量不能代替手机实际速度验收。

## 手机操作

1. 安装 [0.2.4 APK](../artifacts/gowin-control-0.2.4-gw25k-compact-debug.apk)，可覆盖相同调试签名的旧版并保留作品。需要本版才能启用紧凑分片；旧APP保持兼容。
2. 板卡供电，扫描并选择 **GW25K-PROTO**。授予附近设备权限；Android8–11还需定位权限与定位服务。
3. 录音页最大时长保留 **0**，开始录音，等“可下载”后点击“下载 / 继续”。音源为FPGA内置的1秒双声道提示音。
4. 到作品页试听、导出或分享。普通断线可重连并继续下载；再次录音前清除设备录音，手机作品保留。
5. **板卡重启或重配置后，先删除手机未完成下载，再开始新录音。** 历史启动标识重复尚未修复，不能保证跨重启对象身份唯一。

APP每个连接依次探测OPEN_COMPACT0x37、OPEN_WIDE0x36、原OPEN0x30，只有明确UNSUPPORTED0x80才回退；BUSY或超时不能更换OPEN。超时重试相同ID和逻辑字节。B2仅用于明确选择0x37后的Transfer DATA，其他特征保持B1，未协商时拒绝B2。每块仍先校验、可靠保存PCM和原子检查点，再确认；首块READ、末块独立ACK后CLOSE。检查点只需4字节对齐，可在B1/256、B1/460、B2/460间切换。格式见 [B2扩展](COMPACT_TRANSFER_EXTENSION.md)。

## 匹配版本

| 项目 | 结果 |
|---|---|
| APK | `artifacts/gowin-control-0.2.4-gw25k-compact-debug.apk`，9668978字节 |
| APK SHA256 | `f06a73a92f4893d6dd84166cc8d19cacc14f3e5ce00f2004c50fc84f0ac2aff6` |
| 调试证书 SHA256 | `dc39e7120615a53f0bdf18629a361f0ebbf055d36c3b82f48adaf01cdae878ca` |
| APP 源码 | [clients/android](../clients/android)，基于 `37c8913`，当前源码和测试随工程保留 |
| 固件 | `builds/20261020_055737_599510/impl/pnr/ble_protocol.fs` |
| 固件 SHA256 | `a9e3ab08b40f56c5d648dbc48daf24d69cc1d24947bb212d393368f3c7c42882` |
| UserCode / Status | `00009F4C` / `70022020` |
| Flash | cable1/channel0，2.5MHz，写入校验、重载和身份读回通过 |
| 时序 | 50MHz，Fmax51.649MHz，setup/hold违例0/0 |
| 资源 | 15716 LUT，8788 Register，10799/11520 CLS，30/56 BSRAM |
| 传输 | UART921600/8E1，ATT23，Capability0x68，单窗口，原OPEN256，宽/紧凑OPEN460字节 |
| 音频 | 48kHz、双声道、PCM16；48000帧、192000字节PCM、192044字节WAV |
| PCM CRC32 | `A54A47B0` |
| WAV SHA256 | `2c492fa12189698f5abf3032cfd97aa322e8c4df5456b37f0c7bf56800d760ed` |

## 验收与限制

- [16组RTL/主机回归](../reports/speed6_20261020/simulation.json)通过，含完整30147字节UART补丁、紧凑GATT同步RAM与片数/flags/token、普通和紧凑录音重放及原子拒绝。[22项Android普通测试及Lint0](../reports/speed6_20261020/android_checks.json)通过。
- [同固件交替测速](../reports/speed6_20261020/alternating_speed.json)、[通知逐片核查](../reports/speed6_20261020/notification_wire_check.json)、[新APP/旧固件](../reports/speed6_20261020/kotlin_old_firmware.json)、[新APP/紧凑固件](../reports/speed6_20261020/kotlin_compact_sram.json)及[完整WAV](../reports/speed6_20261020/complete_wav_check.json)通过。两次均为460字节块、414个ACK_READ，在14720/29440字节处取消/断线。[原始协议核查](../reports/speed6_20261020/app_wire_check.json)确认旧固件每连接一次回退、已执行响应丢失后的相同请求重试，以及所有DATA PCM/CRC。
- [跨三种协议检查点续传](../reports/speed6_20261020/profile_resume_sram.json)、[紧凑录音](../reports/speed6_20261020/recording_compact_sram.json)、[旧460格式](../reports/speed6_20261020/recording_wide_sram.json)、[普通256](../reports/speed6_20261020/recording_256_sram.json)、[原READ/ACK](../reports/speed6_20261020/recording_legacy_sram.json)及[旧控制协议](../reports/speed6_20261020/protocol_sram.json)通过。
- [Flash写入校验与重载](../reports/flash_20261020_060735_415406/summary.json)、[固化后测速](../reports/speed6_20261020/speed_flash.json)、[固化后录音](../reports/speed6_20261020/recording_flash.json)及[固化后旧协议](../reports/speed6_20261020/protocol_flash.json)通过。[本轮汇总](../reports/speed6_20261020/summary.json)记录精确范围、诊断、APK和源码身份。
- **历史启动标识重复未解决：** [原始失败](../reports/speed3_20261020/flash_boot_identity_repeat.json)保留，初始化逻辑未改。本次SRAM/Flash标识不同不能证明唯一性。板卡重启或重配置后，先丢弃手机未完成下载再开始新录音。

7.5ms请求试验实际变慢，未采用；最终仍请求15ms。高频连测曾在PCM下载完成后的新START触发既有8任务槽/60秒保留窗口BUSY，窗口到期后复测通过，原始诊断保留。

桥接器仅转发GATT字节，协议和持久化由APP Kotlin执行。手机原生权限、GATT、UI、后台及实际速度未测，新镜像未物理断电验收。音源仍为FPGA内置测试音频，无手机麦克风或外部实时输入。音频未压缩，ATT23和逻辑512上限保持。

历史记录：[0.2.3宽块](APP_INTEGRATION_0_2_3_WIDE.md)、[0.2.2 L2CAP](APP_INTEGRATION_0_2_2_L2CAP.md)、[0.2.2 ACK_READ](APP_INTEGRATION_0_2_2_ACK_READ.md)、[0.2.1 UART](APP_INTEGRATION_0_2_1_UART921600.md)。

## 重建

Android使用JDK17、SDK35、Build Tools35.0.0，在 `clients/android/local.properties` 配置SDK后执行：

```sh
sh gradlew :core:protocol:test :core:ble:testDebugUnitTest :core:data:testDebugUnitTest :app:assembleDebug :app:lintDebug
```

在本例目录：

```sh
sh run_sim.sh
sh build.sh
python3 program_sram.py --manifest reports/last_build.json --frequency 2.5MHz
python3 program_flash.py --manifest reports/last_build.json
```

`reports/ready_build.json` 指向当前已固化且下载实测的镜像，并标注启动标识限制；新构建不会自动改变该索引。编程脚本校验器件、安全位、位流哈希和时序，并独立保存日志。
