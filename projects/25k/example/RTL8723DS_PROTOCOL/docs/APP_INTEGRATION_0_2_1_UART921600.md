# 25K / Android 加速录音联调

2026-10-20，Android **0.2.1 / versionCode 4**，包名 `cn.gowin.control`，最低 Android 8。已接通 FPGA 内置音频录制、下载、续传和 WAV 保存；当前 FPGA 进一步将运行期 UART 提高至 921600，实测 **1119–1187 字节/秒**；APP 源码和 APK 保持 0.2.1。详细记录见 [第二轮提速](UART_SPEED_OPTIMIZATION.md)。

## 手机操作

1. 安装 [0.2.1 加速版 APK](../artifacts/gowin-control-0.2.1-gw25k-fast-debug.apk)，可覆盖相同调试签名的旧版并保留作品。
2. 板卡供电，重新扫描并选择 **GW25K-PROTO**。新固件更新了随机地址命名空间，应重新扫描，勿使用旧缓存地址。授予附近设备权限；Android 8–11 还需定位权限与定位服务。
3. “录音”页最大时长保留 **0**，开始录音，等“可下载”后点击“下载 / 继续”。音源是 FPGA 内置的 1 秒双声道提示音。
4. 下载完成后到“作品”试听、导出或分享。可暂停、保留检查点及断线重连续传；再次录音前清除设备录音，手机作品保留。

新 APP 自动识别设备的无响应写入属性，旧固件仍使用确认写入；持续超时会回退。电脑完整 192000 字节下载含取消/重连约 **176.8 秒**，手机实际耗时需安装验收。详细测量、协商与兼容规则见 [提速说明](SPEED_OPTIMIZATION.md)。

## 匹配版本

| 项目 | 结果 |
|---|---|
| APK | `artifacts/gowin-control-0.2.1-gw25k-fast-debug.apk`，9,737,009 字节 |
| APK SHA256 | `042d2653ea7bf8a3e704966884a04c5358c01a5ebbc4f5c904881dbabca9b1f1` |
| 调试证书 SHA256 | `dc39e7120615a53f0bdf18629a361f0ebbf055d36c3b82f48adaf01cdae878ca` |
| APP 来源 | 基于 `37c8913`，完整源码位于 [clients/android](../clients/android) |
| 固件 | `builds/20261020_042935_886410/impl/pnr/ble_protocol.fs` |
| 固件 SHA256 | `b8ba81e260538269e79512227734cac21a88ce74c5a9aca5f466863b181b9010` |
| UserCode / Status | `000002AD` / `70022020` |
| FPGA / Flash ID | `0001281B` / `0B4017` |
| Flash 方法 | cable1 / channel0，2.5 MHz，operation54 写入校验、operation1 重载、身份读回 |
| 时序 | 50 MHz，Fmax 50.314 MHz，setup/hold 违例 0/0 |
| 资源 | 16003 LUT，8783 Register，10856/11520 CLS，30/56 BSRAM |
| 音频 | 48 kHz、双声道、PCM16；48000 帧、192000 字节 PCM、192044 字节 WAV |
| PCM CRC32 | `A54A47B0` |
| WAV SHA256 | `2c492fa12189698f5abf3032cfd97aa322e8c4df5456b37f0c7bf56800d760ed` |

## 验收与证据

- [14 组 HDL/主机回归](../reports/simulations/20261020_043519_715862/result.json)全部通过。包含完整 30147 字节补丁及运行期切速/确认写入；其他 UART 场景使用 253 字节双片模型覆盖首/末片、无响应写入、原速、拒绝切速、错误 ROM、失败或全零 LE Rand。
- [APP Kotlin 完整下载](../reports/speed2_20261020/kotlin_fast_sram.json)：主动丢片恢复、8192 字节取消重开、16384 字节断线和持久检查点续传、192000 字节下载及 WAV 保存通过，下载过程约 176.79 秒。
- [完整 WAV 比对](../reports/speed2_20261020/complete_wav_check.json)：与参考 WAV 逐字节一致，CRC32 和 SHA256 均匹配。
- [录音边界](../reports/speed2_20261020/recording_sram.json)：READ 精确重放、错误/重复 ACK、BUSY、取消/断线续传、EOF/CLOSE/CLEAR、STOP 通过；[旧确认写入协议](../reports/speed2_20261020/protocol_sram.json)同样通过。
- [Flash 写入/校验/重载](../reports/flash_20261020_043811_340487/summary.json)、[固化后32768字节测速](../reports/speed2_20261020/speed_flash.json)、[固化后录音复验](../reports/speed2_20261020/recording_flash.json)和[固化后旧协议](../reports/speed2_20261020/protocol_flash.json)留档。
- 本轮 APP 的 47 个源文件和 APK 哈希均与上一轮一致，[核对结果](../reports/speed2_20261020/android_unchanged.json)。原 11 项 Android 普通单元测试和 Lint 结果保留在 [上一轮汇总](../reports/speed_20261020/summary.json)，本轮真实 BLE 再执行 APP Kotlin 完整下载测试。
- [本轮汇总](../reports/speed2_20261020/summary.json)和固件输入哈希、源码差异保存在本轮报告目录。

桥接 Python 只转发 GATT 字节；协议、PCM 解码、检查点和 WAV 封装由 APP 原始 Kotlin 完成。Android 真机权限、GATT、UI 和后台行为仍由用户安装 APK 验收。Flash 使用 Reprogram 重载，未实际切断板卡电源。音源为内置测试音频，无手机麦克风或外部实时输入。

历史记录：[0.2.1 / UART115200](APP_INTEGRATION_0_2_1_UART115200.md)、[0.2.0 录音基线](APP_INTEGRATION_0_2_0.md)、[0.1.1 最小协议基线](APP_INTEGRATION_0_1_1.md)。

## 重建

Android 使用 JDK17、SDK35、Build Tools35.0.0，在 `clients/android/local.properties` 配置 SDK，然后执行：

```sh
sh gradlew :core:protocol:test :core:ble:testDebugUnitTest :core:data:testDebugUnitTest :app:assembleDebug :app:lintDebug
```

在本例目录：

```sh
sh run_sim.sh
sh build.sh
python3 program_sram.py --manifest reports/last_build.json --frequency 2.5MHz
# 无线验收通过后替换 Flash 启动区
python3 program_flash.py --manifest reports/last_build.json
```

`reports/ready_build.json` 指向已固化且实测的镜像；新构建不会自动改变它。编程脚本预检器件、安全位、位流哈希和时序，每次独立保留日志。
