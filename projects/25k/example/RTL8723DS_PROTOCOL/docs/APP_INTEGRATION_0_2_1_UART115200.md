# 25K / Android 加速录音联调

2026-10-20，Android **0.2.1 / versionCode 4**，包名 `cn.gowin.control`，最低 Android 8。已接通 FPGA 内置音频录制、下载、续传和 WAV 保存；本版减少命令写入等待，实板短测吞吐由 488.5 提升至 1034.4 字节/秒，约 **2.12 倍**。

## 手机操作

1. 安装 [0.2.1 加速版 APK](../artifacts/gowin-control-0.2.1-gw25k-fast-debug.apk)，可覆盖相同调试签名的旧版并保留作品。
2. 板卡供电，重新扫描并选择 **GW25K-PROTO**。新固件更新了随机地址命名空间，应重新扫描，勿使用旧缓存地址。授予附近设备权限；Android 8–11 还需定位权限与定位服务。
3. “录音”页最大时长保留 **0**，开始录音，等“可下载”后点击“下载 / 继续”。音源是 FPGA 内置的 1 秒双声道提示音。
4. 下载完成后到“作品”试听、导出或分享。可暂停、保留检查点及断线重连续传；再次录音前清除设备录音，手机作品保留。

新 APP 自动识别设备的无响应写入属性，旧固件仍使用确认写入；持续超时会回退。电脑完整 192000 字节下载含取消/重连约 **196 秒**，手机实际耗时需安装验收。详细测量、协商与兼容规则见 [提速说明](SPEED_OPTIMIZATION.md)。

## 匹配版本

| 项目 | 结果 |
|---|---|
| APK | `artifacts/gowin-control-0.2.1-gw25k-fast-debug.apk`，9,737,009 字节 |
| APK SHA256 | `042d2653ea7bf8a3e704966884a04c5358c01a5ebbc4f5c904881dbabca9b1f1` |
| 调试证书 SHA256 | `dc39e7120615a53f0bdf18629a361f0ebbf055d36c3b82f48adaf01cdae878ca` |
| APP 来源 | 基于 `37c8913`，完整源码位于 [clients/android](../clients/android) |
| 固件 | `builds/20261020_040429_731960/impl/pnr/ble_protocol.fs` |
| 固件 SHA256 | `51b2e4a8d955ccb3e6901cb40d76cc6bc010117bf139557714d86dfe3fc3c07b` |
| UserCode / Status | `00004096` / `70022020` |
| FPGA / Flash ID | `0001281B` / `0B4017` |
| Flash 方法 | cable1 / channel0，2.5 MHz，operation54 写入校验、operation1 重载、身份读回 |
| 时序 | 50 MHz，Fmax 51.174 MHz，setup/hold 违例 0/0 |
| 资源 | 15665 LUT，8815 Register，10750/11520 CLS，30/56 BSRAM |
| 音频 | 48 kHz、双声道、PCM16；48000 帧、192000 字节 PCM、192044 字节 WAV |
| PCM CRC32 | `A54A47B0` |
| WAV SHA256 | `2c492fa12189698f5abf3032cfd97aa322e8c4df5456b37f0c7bf56800d760ed` |

## 验收与证据

- [12 组 HDL/主机回归](../reports/simulations/20261020_040438_955825/result.json)通过，包括完整 UART/H5/补丁下的确认写入与无响应写入两条路径。
- Android **11 项**常规单元测试通过，APK 构建、签名与 Lint 通过；Lint 0 errors / 0 warnings。新增持续超时回退时保持请求 ID、内容不变的测试。
- [加速录音实板回归](../reports/speed_20261020/recording_fast_sram.json)：音频逐字节对比、精确 READ 重放、错误/重复 ACK、BUSY、取消及断线续传、EOF/CLOSE/CLEAR、手动 STOP 通过。
- [APP Kotlin 完整下载](../reports/speed_20261020/kotlin_fast_sram.json)：两次连接均使用无响应写入；主动丢弃一个命令分片并成功重试；8192 字节取消重开、16384 字节断线后按持久检查点续传。完整 192000 字节下载约 196.18 秒，含上述续传和 WAV 保存。
- [完整 WAV 比对](../reports/speed_20261020/complete_wav_check.json)：帧数、双声道数据、CRC 与参考 WAV 逐字节一致。
- [Flash 写入/校验/重载](../reports/flash_20261020_041256_493362/summary.json)与 [固化后录音复验](../reports/speed_20261020/flash_recording.json)、[固化后速度](../reports/speed_20261020/speed_flash.json)、[原确认写入协议回归](../reports/speed_20261020/protocol_flash.json)留档。
- [最终汇总](../reports/speed_20261020/summary.json)、源码哈希、Android 相对 37c8913 的审阅补丁与 JUnit/XML 均在本轮目录。

桥接 Python 只转发 GATT 字节；协议、PCM 解码、检查点和 WAV 封装由 APP 原始 Kotlin 完成。Android 真机权限、GATT、UI 和后台行为仍由用户安装 APK 验收。Flash 使用 Reprogram 重载，未实际切断板卡电源。音源为内置测试音频，无手机麦克风或外部实时输入。

历史记录：[0.2.0 录音基线](APP_INTEGRATION_0_2_0.md)、[0.1.1 最小协议基线](APP_INTEGRATION_0_1_1.md)。

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
