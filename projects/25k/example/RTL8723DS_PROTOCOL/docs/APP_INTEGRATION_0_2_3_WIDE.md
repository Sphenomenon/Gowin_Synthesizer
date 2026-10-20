# 25K / Android 0.2.3 录音提速联调

2026-10-20，Android **0.2.3 / versionCode6**，包名 `cn.gowin.control`，最低Android8。新增可选OPEN_WIDE，单次PCM块由256提高至460字节，保留CRC、持久检查点和窗口1。已固化Flash，32768字节同板实测 **2952 → 3535字节/秒（+19.7%）**，SRAM首测3722字节/秒。APP Kotlin完整192000字节含取消、断线恢复、已执行响应丢失后的重试及WAV保存 **72.32 → 58.27秒（耗时 -19.4%）**，WAV与参考逐字节一致。测量通过电脑BLE桥接完成，手机实际速度待安装验收。详见 [OPEN_WIDE扩展](OPEN_WIDE_EXTENSION.md)。

## 手机操作

1. 安装 [0.2.3 APK](../artifacts/gowin-control-0.2.3-gw25k-wide-debug.apk)，可覆盖相同调试签名的旧版并保留作品。需升级到0.2.3才能使用本轮大块提速；旧版仍可按原流程连接。
2. 板卡供电，重新扫描并选择 **GW25K-PROTO**。授予附近设备权限；Android 8–11 还需定位权限与定位服务。
3. 录音页最大时长保留 **0**，开始录音，等“可下载”后点击“下载 / 继续”。音源是 FPGA 内置的1秒双声道提示音。
4. 到作品页试听、导出或分享。正常断线可重新连接并继续下载；再次录音前清除设备录音，手机作品保留。
5. **板卡重启或重配置后，先删除手机未完成的下载，再开始新录音。** 同镜像JTAG重载观察到启动标识重复，跨重启身份唯一性未通过，详见下方限制。

新APP先尝试OPEN_WIDE，旧固件明确返回UNSUPPORTED后，本连接回退普通OPEN并保留原ACK_READ/ACK逻辑。旧APP继续使用普通OPEN，最大256字节。每块仍先校验并可靠保存PCM和检查点，再确认；首块READ、末块独立ACK后CLOSE。超时同ID重试及持续超时的ATT确认写入回退保留。旧检查点偏移只需4字节对齐，可跨256/460块大小续传。详见 [OPEN_WIDE](OPEN_WIDE_EXTENSION.md)、[ACK_READ](ACK_READ_EXTENSION.md) 和 [L2CAP间隔优化](L2CAP_SPEED_OPTIMIZATION.md)。

## 匹配版本

| 项目 | 结果 |
|---|---|
| APK | `artifacts/gowin-control-0.2.3-gw25k-wide-debug.apk`，9668978 字节 |
| APK SHA256 | `62001b2cc03538da331cf4113afa97db7a1cab14d71ac52cba4bbdaa30fd4947` |
| 调试证书 SHA256 | `dc39e7120615a53f0bdf18629a361f0ebbf055d36c3b82f48adaf01cdae878ca` |
| APP 源码 | [clients/android](../clients/android)，基于 `37c8913`，当前源码和测试随工程保留 |
| 固件 | `builds/20261020_052940_831068/impl/pnr/ble_protocol.fs` |
| 固件 SHA256 | `c9dc3838c7be7e9358f4a8b5d306534a554d1f8811f6b827b3935b720e37a5f5` |
| UserCode / Status | `0000D769` / `70022020` |
| Flash 方法 | cable1/channel0，2.5MHz，operation54写入校验、operation1重载、身份读回 |
| 时序 | 50MHz，Fmax52.562MHz，setup/hold违例0/0 |
| 资源 | 15809 LUT，8789 Register，10758/11520 CLS，30/56 BSRAM |
| 传输 | UART921600/8E1，ATT23，普通OPEN256字节、OPEN_WIDE460字节PCM块，窗口1，Capability0x68 |
| 音频 | 48kHz、双声道、PCM16；48000帧、192000字节PCM、192044字节WAV |
| PCM CRC32 | `A54A47B0` |
| WAV SHA256 | `2c492fa12189698f5abf3032cfd97aa322e8c4df5456b37f0c7bf56800d760ed` |

## 验收与限制

- [14组RTL/主机回归](../reports/simulations/20261020_052935_544584/result.json)通过，含完整30147字节补丁、最大508字节DATA/CRC/重放及普通OPEN恢复256上限。[18项普通Android测试和Lint](../reports/speed5_20261020/android_checks.json)通过。
- [新APP/旧固件](../reports/speed5_20261020/kotlin_old_firmware.json)、[每连接一次大块探测后回退](../reports/speed5_20261020/old_firmware_fallback_wire_check.json)、[新APP/新固件完整下载](../reports/speed5_20261020/kotlin_wide_sram.json)、[完整WAV](../reports/speed5_20261020/complete_wav_check.json)通过。新固件414个ACK_READ组合块通过，取消、断线恢复和[丢响应后的相同请求重试](../reports/speed5_20261020/executed_response_loss_wire_check.json)保留。新旧完整测试均在各自块大小的32/64块处取消/断线，绝对字节偏移不同。
- [256↔460跨块大小检查点](../reports/speed5_20261020/profile_resume_sram.json)、[宽块边界](../reports/speed5_20261020/recording_wide_sram.json)、[普通256组合流程](../reports/speed5_20261020/recording_256_sram.json)、[旧READ/ACK](../reports/speed5_20261020/recording_legacy_sram.json)和[旧确认写入协议](../reports/speed5_20261020/protocol_sram.json)通过。
- [Flash写入/校验及重载](../reports/flash_20261020_054024_091526/summary.json)、[固化后测速](../reports/speed5_20261020/speed_flash.json)、[固化后录音](../reports/speed5_20261020/recording_flash.json)及[固化后旧协议](../reports/speed5_20261020/protocol_flash.json)通过。[本轮汇总](../reports/speed5_20261020/summary.json)记录通过范围、APK和源码哈希。
- **历史启动标识重复未解决：** 先前同镜像JTAG重载观察到boot_id重复，[原始失败](../reports/speed3_20261020/flash_boot_identity_repeat.json)保留。初始化逻辑未改；本次标识不同、旧对象拒绝通过不证明唯一性。板卡重启或重配置后，先删除手机未完成下载再开始新录音。

桥接器只转发GATT字节，逻辑协议、持久检查点及WAV由APP Kotlin执行。手机原生权限、GATT、UI、后台行为及手机实际速度未测，新镜像未物理断电验收。音源仍为FPGA内置1秒测试音频，无手机麦克风或外部实时输入。逻辑最大512字节、ATT23和每片14字节数据不变。

历史记录：[0.2.2 / L2CAP上一轮](APP_INTEGRATION_0_2_2_L2CAP.md)、[0.2.2 / ACK_READ前一轮](APP_INTEGRATION_0_2_2_ACK_READ.md)、[0.2.1 / UART921600](APP_INTEGRATION_0_2_1_UART921600.md)、[0.2.1 / UART115200](APP_INTEGRATION_0_2_1_UART115200.md)、[0.2.0](APP_INTEGRATION_0_2_0.md)、[0.1.1](APP_INTEGRATION_0_1_1.md)。

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

`reports/ready_build.json` 指向当前已固化且下载实测的镜像，并标注启动标识限制；新构建不自动改变该索引。编程脚本校验器件、安全位、位流哈希和时序，并独立保存日志。
