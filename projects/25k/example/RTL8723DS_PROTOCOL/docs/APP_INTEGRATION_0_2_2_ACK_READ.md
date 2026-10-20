# 25K / Android 0.2.2 录音提速联调

2026-10-20，Android **0.2.2 / versionCode 5**，包名 `cn.gowin.control`，最低 Android 8。APP 和 FPGA 新增可选 ACK_READ 命令，将上一块确认与下一块读取合并。已固化 Flash，32768 字节实测 **1130 → 1606 字节/秒（+42.2%）**；APP Kotlin 完整192000字节含取消、断线恢复及WAV保存 **173.14 → 135.22秒（耗时 -21.9%）**。新测试含主动丢弃已执行命令响应后的重试等待，WAV 与参考逐字节一致。测量通过电脑BLE桥接完成，手机实际速度需安装验收。

## 手机操作

1. 安装 [0.2.2 APK](../artifacts/gowin-control-0.2.2-gw25k-ack-read-debug.apk)，可覆盖相同调试签名的旧版并保留作品。需要新 APP 与本轮 FPGA 固件配合提速。
2. 板卡供电，重新扫描并选择 **GW25K-PROTO**。授予附近设备权限；Android 8–11 还需定位权限与定位服务。
3. 录音页最大时长保留 **0**，开始录音，等“可下载”后点击“下载 / 继续”。音源是 FPGA 内置的1秒双声道提示音。
4. 到作品页试听、导出或分享。正常断线可重新连接并继续下载；再次录音前清除设备录音，手机作品保留。
5. **板卡重启或重配置后，先删除手机未完成的下载，再开始新录音。** 同镜像JTAG重载观察到启动标识重复，跨重启身份唯一性未通过，详见下方限制。

新 APP 对旧固件收到明确 UNSUPPORTED 后，在本连接回退原 ACK / READ；旧 APP 可继续连接新固件，按原方式下载。每块仍先校验、可靠保存PCM及检查点，再确认；首块READ、末块独立ACK后CLOSE。连续超时的ATT确认写入回退保留。详细线格式、原子性和重试规则见 [ACK_READ 扩展](ACK_READ_EXTENSION.md)。

## 匹配版本

| 项目 | 结果 |
|---|---|
| APK | `artifacts/gowin-control-0.2.2-gw25k-ack-read-debug.apk`，9737067 字节 |
| APK SHA256 | `bf48a9a2cf0192965dd4ff2b71d5f19bc8a26fe7ce0be149f9e1ba83be6cc22c` |
| 调试证书 SHA256 | `dc39e7120615a53f0bdf18629a361f0ebbf055d36c3b82f48adaf01cdae878ca` |
| APP 源码 | [clients/android](../clients/android)，基于 `37c8913`，当前源码和测试随工程保留 |
| 固件 | `builds/20261020_044829_666386/impl/pnr/ble_protocol.fs` |
| 固件 SHA256 | `6c55032a3f2c2a29bb68ce6f5c4d0a6620e78e7190409f80fdc87e3d0b4626f9` |
| UserCode / Status | `00008E1E` / `70022020` |
| Flash 方法 | cable1/channel0，2.5MHz，operation54写入校验、operation1重载、身份读回 |
| 时序 | 50MHz，Fmax50.625MHz，setup/hold违例0/0 |
| 资源 | 15654 LUT，8816 Register，10674/11520 CLS，30/56 BSRAM |
| 传输 | UART921600/8E1，ATT23，256字节PCM块，窗口1，Capability0x68 |
| 音频 | 48kHz、双声道、PCM16；48000帧、192000字节PCM、192044字节WAV |
| PCM CRC32 | `A54A47B0` |
| WAV SHA256 | `2c492fa12189698f5abf3032cfd97aa322e8c4df5456b37f0c7bf56800d760ed` |

## 验收与限制

- [14组RTL/主机回归](../reports/simulations/20261020_044810_787927/result.json)通过；完整30147字节补丁模型保留。[14项普通Android测试及Lint](../reports/speed3_20261020/android_checks.json)通过。
- [新APP/旧固件](../reports/speed3_20261020/kotlin_old_firmware.json)、[新APP/新固件完整下载](../reports/speed3_20261020/kotlin_combined_sram.json)与[完整WAV比对](../reports/speed3_20261020/complete_wav_check.json)通过。新固件运行746个组合块；取消、断线检查点恢复、主动丢命令片段及已执行组合请求的响应丢失均通过。[同ID重试字节核对](../reports/speed3_20261020/executed_response_loss_wire_check.json)保留。
- [组合命令边界](../reports/speed3_20261020/recording_combined_sram.json)、[旧READ/ACK](../reports/speed3_20261020/recording_legacy_sram.json)、[旧确认写入协议](../reports/speed3_20261020/protocol_sram.json)通过。
- [Flash写入、校验和重载](../reports/flash_20261020_050505_152961/summary.json)、[固化后测速](../reports/speed3_20261020/speed_flash.json)、[固化后录音下载](../reports/speed3_20261020/recording_combined_flash_download.json)、[固化后旧协议](../reports/speed3_20261020/protocol_flash.json)通过。[本轮汇总](../reports/speed3_20261020/summary.json)记录通过范围与限制。
- **启动标识唯一性未通过：** 同一镜像SRAM到Flash重载后boot_id重复，原始失败见 [记录](../reports/speed3_20261020/flash_boot_identity_repeat.json)。初始化源码与上一轮一致，原因未完全定位；不能承诺重启后身份唯一。本轮下载通过项仅涵盖同次启动内续传。[限制及处理方式](../reports/speed3_20261020/boot_identity_limitation.json)随固件索引保留。

桥接器只转发GATT字节，协议、持久检查点和WAV封装由APP Kotlin执行。Android真机权限、GATT、UI及后台行为尚未验收；新镜像未实际切断板卡电源。音源为内置测试音频，无手机麦克风或外部实时输入。

历史记录：[0.2.1 / UART921600](APP_INTEGRATION_0_2_1_UART921600.md)、[0.2.1 / UART115200](APP_INTEGRATION_0_2_1_UART115200.md)、[0.2.0](APP_INTEGRATION_0_2_0.md)、[0.1.1](APP_INTEGRATION_0_1_1.md)。

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
