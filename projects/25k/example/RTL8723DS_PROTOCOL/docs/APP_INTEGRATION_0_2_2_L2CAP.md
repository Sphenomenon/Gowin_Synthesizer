# 25K / Android 0.2.2 录音提速联调

2026-10-20，Android **0.2.2 / versionCode 5**，包名 `cn.gowin.control`，最低 Android8。本轮在 ACK_READ 基础上改用外设 L2CAP 连接参数请求，申请15毫秒间隔，APP源码和APK不变。已固化Flash，32768字节同板实测 **1604 → 3055字节/秒（+90.5%）**；APP Kotlin完整192000字节含取消、断线恢复、已执行响应丢失后的重试及WAV保存 **135.22 → 72.02秒（耗时 -46.7%）**，WAV与参考逐字节一致。电脑BLE桥接测量，手机实际速度待验收；已装0.2.2无需重装。详见 [L2CAP提速说明](L2CAP_SPEED_OPTIMIZATION.md)。

## 手机操作

1. 安装 [0.2.2 APK](../artifacts/gowin-control-0.2.2-gw25k-ack-read-debug.apk)，可覆盖相同调试签名的旧版并保留作品。已装0.2.2无需重装；更早版本需升级后使用ACK_READ。
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
| 固件 | `builds/20261020_051436_956875/impl/pnr/ble_protocol.fs` |
| 固件 SHA256 | `7ecbcf6012942f0c430c79e9e30ab47af4650fa1cbc0e0f140f2f2a834288a98` |
| UserCode / Status | `0000EBE1` / `70022020` |
| Flash 方法 | cable1/channel0，2.5MHz，operation54写入校验、operation1重载、身份读回 |
| 时序 | 50MHz，Fmax51.312MHz，setup/hold违例0/0 |
| 资源 | 15906 LUT，8818 Register，10962/11520 CLS，30/56 BSRAM |
| 传输 | UART921600/8E1，ATT23，256字节PCM块，窗口1，Capability0x68 |
| 音频 | 48kHz、双声道、PCM16；48000帧、192000字节PCM、192044字节WAV |
| PCM CRC32 | `A54A47B0` |
| WAV SHA256 | `2c492fa12189698f5abf3032cfd97aa322e8c4df5456b37f0c7bf56800d760ed` |

## 验收与限制

- [14组RTL/主机回归](../reports/simulations/20261020_051432_050610/result.json)通过，含完整30147字节补丁及真实UART/H5路径中的L2CAP请求。定向检查ACL额度、接受/拒绝不回环和重复订阅不重复请求。
- [本轮APP Kotlin完整下载](../reports/speed4_20261020/kotlin_sram.json)、[WAV比对](../reports/speed4_20261020/complete_wav_check.json)、[丢响应后的同ID重试](../reports/speed4_20261020/executed_response_loss_wire_check.json)通过。746个组合块，取消、断线检查点恢复及主动丢片保留。
- [录音边界及组合重放](../reports/speed4_20261020/recording_sram.json)、[旧READ/ACK](../reports/speed4_20261020/recording_legacy_sram.json)、[旧确认写入协议](../reports/speed4_20261020/protocol_sram.json)通过。
- [Flash写入、校验和重载](../reports/flash_20261020_052052_196449/summary.json)、[固化后测速](../reports/speed4_20261020/speed_flash.json)、[固化后录音](../reports/speed4_20261020/recording_flash.json)、[固化后旧协议](../reports/speed4_20261020/protocol_flash.json)通过。本次重载启动标识不同、旧对象拒绝通过。
- [48个Android源文件与APK哈希核对](../reports/speed4_20261020/android_unchanged.json)确认与上一轮一致。上一轮[14项普通Android测试及Lint](../reports/speed3_20261020/android_checks.json)结果保留，本轮重新执行完整实板Kotlin测试。
- **历史启动标识重复未解决：** 上一轮同镜像JTAG重载观察到boot_id重复，[原始失败记录](../reports/speed3_20261020/flash_boot_identity_repeat.json)保留。初始化逻辑未变，本次启动标识不同不证明其唯一性；重启后先删除手机未完成下载，再开始新录音。

[本轮汇总](../reports/speed4_20261020/summary.json)明确通过范围和限制。请求的15ms间隔未通过诊断接口直接读回；通知回调组间间隔约28→13ms为间接证据。对端拒绝或无响应时继续原连接，不阻塞业务。桥接器只转发GATT字节，协议、持久检查点和WAV由APP Kotlin执行。Android手机原生权限、GATT、UI及后台行为未测，新镜像未物理断电测试。音源仍为FPGA内置音频。

历史记录：[0.2.2 / ACK_READ前一轮](APP_INTEGRATION_0_2_2_ACK_READ.md)、[0.2.1 / UART921600](APP_INTEGRATION_0_2_1_UART921600.md)、[0.2.1 / UART115200](APP_INTEGRATION_0_2_1_UART115200.md)、[0.2.0](APP_INTEGRATION_0_2_0.md)、[0.1.1](APP_INTEGRATION_0_1_1.md)。

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
