# 25K / Android 内置音频录音联调

2026-10-20，Android **0.2.0 / versionCode 3**，包名 `cn.gowin.control`，最低 Android 8。本版接通 FPGA 内置音频的录制、封存、分块下载、续传、WAV 保存与手机试听入口。用户选择自行安装 APK 进行手机验收。

## 手机操作

1. 安装 [0.2.0 录音测试 APK](../artifacts/gowin-control-0.2.0-gw25k-recording-debug.apk)。调试签名与 0.1.1 相同，可覆盖安装并保留作品。
2. 板卡供电，APP“连接设备”→“扫描 10 秒”，授予附近设备权限；Android 8–11 还需定位权限及系统定位服务。选择 **GW25K-PROTO**，无需先在系统蓝牙页配对。
3. 进入“录音”，最大时长保留 **0**，点击“开始录音”，等待状态变为“可下载”。音源是 FPGA 内置的 1 秒双声道测试提示音。
4. 点击“下载 / 继续”。此版固定小分片与可靠逐块 ACK，下载需要数分钟；可暂停保留进度，或断开后重新连接继续。
5. 完整 CRC 通过后进入“作品”试听、导出或分享 WAV，作品标注“FPGA 内置测试音频”。再次录音前清除设备录音；手机已保存作品保留。

详细功能和实现边界见 [录音说明](RECORDING_PROFILE.md)。当前不采集手机麦克风或板卡外部输入，也未接入完整合成器。控制页显示内置音频说明；模拟设备继续使用独立模拟音源。

## 匹配版本

| 项目 | 结果 |
|---|---|
| APK | `artifacts/gowin-control-0.2.0-gw25k-recording-debug.apk`，9,668,978 字节 |
| APK SHA256 | `028dc64c5774ddb79bfe35cdb77ca79042ec15f14950fad5104faf5060b57985` |
| 调试证书 SHA256 | `dc39e7120615a53f0bdf18629a361f0ebbf055d36c3b82f48adaf01cdae878ca` |
| APP 来源 | 基于 `codex/android-bluetooth-control` 提交 `37c8913`，适配源码完整保存在 [clients/android](../clients/android) |
| 固件 | `builds/20261020_033519_045081/impl/pnr/ble_protocol.fs` |
| 固件 SHA256 | `674a142df4f5b4efe0ed0c5285fe83aae59e23e77c019573e5355a0e51cc1f3d` |
| UserCode / Status | `00007379` / `70022020` |
| FPGA / Flash ID | `0001281B` / `0B4017` |
| Flash 方法 | cable1 / channel0，2.5 MHz，operation54 写入校验、operation1 重载、身份读回 |
| 时序 | 50 MHz，Fmax 50.430 MHz，setup/hold 违例 0/0 |
| 资源 | 15700 LUT，8782 Register，10826/11520 CLS（94%），30/56 BSRAM |
| 音频 | 48 kHz、双声道、PCM16；48000 帧、192000 字节 PCM、192044 字节 WAV |
| PCM CRC32 | `A54A47B0` |
| WAV SHA256 | `2c492fa12189698f5abf3032cfd97aa322e8c4df5456b37f0c7bf56800d760ed` |

## 验证与证据

- [11 组回归](../reports/simulations/20261020_033919_084196/result.json)通过：录音对象与 CRC、命令、板级复位、H5、控制器发送额度、原 GATT、完整 UART8E1/30147 字节补丁及错误 ROM/随机数，以及主机编解码。
- 常规 Android 单元测试 10 项通过。APK assembleDebug、签名核验和 Lint 通过，Lint 0 errors / 0 warnings。源码哈希和日志保存在 [本轮报告目录](../reports/recording_20261020/)。
- [独立实板录音测试](../reports/recording_20261020/credits_sram_short_v2.json)：100 ms 音频完整下载并逐字节对比，验证任务、READ 重放、错误/重复 ACK、BUSY、取消和断线续传、EOF/CLOSE/CLEAR、提前 STOP 及已提交前缀 CRC。
- [APP Kotlin 完整下载](../reports/recording_20261020/kotlin_credits_sram.json)：通过物理 BLE 下载 1 秒音频，8192 字节时取消重开，16384 字节时断线重连，从持久检查点继续；最终通过整段 CRC 并保存 WAV。包括构建、连接和续传的完整执行耗时约 375 秒。
- [完整 WAV 对比](../reports/recording_20261020/complete_wav_check.json)：下载 WAV 与生成的参考 WAV 逐字节相同，左右声道、格式、帧数、总字节和 CRC 一致。
- [Flash 写入、校验、重载与身份读回](../reports/flash_20261020_034804_337672/summary.json)通过。
- [Flash 重载后的录音回归](../reports/recording_20261020/flash_recording.json)通过：启动为空槽、boot_id 改变、旧对象 OPEN 返回 0x88；新建 100 ms 对象完整下载、逐字节参考对比、取消/断线续传及手动 STOP 再次通过。
- [固化后基础协议回归](../reports/recording_20261020/protocol_flash.json)与 [最终汇总](../reports/recording_20261020/summary.json)单独留档。

Python 桥接器仅转发 GATT 字节；协议、PCM 解码、检查点和 WAV 封装均由 APP 原始 Kotlin 代码完成。该验证不代表 Android 手机权限、GATT、UI、锁屏或厂商后台行为已验收。没有实际切断板卡电源，本次使用 Reprogram 重载验证 Flash 启动。

旧无录音 0.1.1 记录保存在 [历史联调说明](APP_INTEGRATION_0_1_1.md)。原 138K 主目录其他未提交内容未修改，本次未提交/推送 APP 分支。

## 重建

Android 使用 JDK17、SDK35、Build Tools35.0.0，在 `clients/android/local.properties` 配置 SDK，然后执行：

```sh
sh gradlew :core:protocol:test :core:ble:testDebugUnitTest :core:data:testDebugUnitTest :app:assembleDebug :app:lintDebug
```

在本例目录构建与验证 FPGA：

```sh
sh run_sim.sh
sh build.sh
python3 program_sram.py --manifest reports/last_build.json --frequency 2.5MHz
# 无线验收通过后替换 Flash 启动区
python3 program_flash.py --manifest reports/last_build.json
```

`reports/ready_build.json` 固定指向已固化且实测的镜像，新构建不会自动改变它。编程脚本预检器件、安全位、位流哈希和时序，日志单独保留。
