# 25K / Android APP 最小协议联调

2026-10-20，Android 0.1.1 / versionCode 2，包名 `cn.gowin.control`。本次用户选择先生成 APK，在手机测试。

## 手机操作

1. 将 [联调 APK](../artifacts/gowin-control-0.1.1-gw25k-debug.apk) 传到安卓手机安装，最低 Android 8。调试签名与原分支构建相同，可尝试覆盖安装；若手机已有其他签名版本，按系统提示处理，卸载前保留本地作品。
2. 板卡保持供电，打开 APP，点击“连接设备”→“扫描 10 秒”，授予附近设备权限；Android 8–11 同时需要定位权限及系统定位服务。
3. 选择 **GW25K-PROTO**。按业务服务 UUID 扫描；无需先在系统蓝牙页面配对。
4. 出现“已连接 · 最小协议测试”，控制页显示 boot_id、快照编号、设备时间、有效组 0 和控制窗口开启。点击“发送 GET_STATUS”，快照和时间应更新；APP 也会轮询状态。
5. 断开后重新扫描连接。普通重连 boot_id 保持；SW1 按住/释放各至少约 20 ms 或板卡重启后重新扫描，可重新建立会话。

当前固化版持续运行，不再 180 秒关闭。此板提供 HELLO / GET_STATUS；没有合成器、参数控制、录音或文件下载，APP 明确标注此边界。录音页提示能力未提供；“体验模拟设备”仍是独立模拟功能。

## 匹配版本

| 项目 | 结果 |
|---|---|
| APK | `artifacts/gowin-control-0.1.1-gw25k-debug.apk`，9,668,974 字节 |
| APK SHA256 | `ab222c2f70b0c1e259a5b449cce1009519fad5e54a8e0a66909c892d9da3e4f4` |
| APP 基线 | Android 分支 `codex/android-bluetooth-control`，提交 `37c8913` |
| 适配源码 | [clients/android](../clients/android)，协议、BLE、data 与 Compose 模块齐全 |
| 固件 | `builds/20261020_025919_563482/impl/pnr/ble_protocol.fs` |
| 固件 SHA256 | `17f92db8ece34d5933d77d4767adeacc742eb82cf4fe7a6aa3599bc09600d8c6` |
| UserCode / Status | `00008BA9` / `70022020` |
| FPGA / Flash ID | `0001281B` / `0B4017` |
| Flash 方法 | FT2CH channel0，2.5 MHz，operation54，起始地址 0；写入校验后 operation1 重载 |
| 时序 | 50 MHz，Fmax 51.279 MHz，setup/hold 违例 0/0 |
| 资源 | 10192 LUT，6303 Register，8862/11520 CLS，27/56 BSRAM |

源码以完整副本保存在本例下；补丁对比基线见 `reports/app_integration_20261020/android_vs_37c8913.patch`，源码哈希见同目录 `android_sources.json`。138K 主目录其他未提交内容没有修改；本次没有提交或推送 APP 分支。

## 验证范围

- 9 组 HDL/主机回归通过，新增零值持续运行、有限超时与 uptime 饱和检查。结果：`reports/simulations/20261020_025906_082700/result.json`。
- Android 常规回归 10 项通过，0 失败；可选实板测试在常规回归跳过，通过无线桥接单独执行。APK assembleDebug、Lint 通过，最终 Lint 0 errors / 0 warnings。日志及 JUnit/XML 保存在 `reports/app_integration_20261020/`。
- APP 原始 Kotlin `ProtocolSession`、`Capability`、`Snapshot` 与 CRC/分片代码通过 macOS BLE 连接实板两次。验证 Response CCCD、随机 nonce 的 HELLO、GET_STATUS、未知命令 0x80 后继续查询和自动重播/重连。桥接 Python 仅转发 GATT 字节，不替代 APP 逻辑编解码。
- 独立 Python BLE 客户端验证精确重传、ID 冲突 0x86、未知命令 0x80、坏 CRC 静默拒绝、乱序 ATT 错误后恢复，以及普通重连 boot_id 不变。设备时间达到 **195538 ms** 时仍成功收发，超过旧 180 秒期限。
- Flash 已写入、校验并重载，读回 `8BA9` / `70022020`；重载后 APP Kotlin 会话与独立客户端再次实测，记录见下方汇总。

手机 GATT/权限、APP 页面实际显示、锁屏及厂商后台行为由用户安装此 APK 后验收；电脑无线验证不代表 Android 射频测试。未实际切断板卡电源，本次通过重载验证 Flash 加载。

## 证据

- [联调汇总](../reports/app_integration_20261020/summary.json)
- [Flash 编程与读回](../reports/flash_20261020_030452_150244/summary.json)
- [APP 会话：SRAM](../reports/app_integration_20261020/kotlin_sram.json)
- [APP 会话：Flash 重载](../reports/app_integration_20261020/kotlin_flash.json)
- [完整独立 BLE 回归](../reports/app_integration_20261020/protocol_sram.json)
- [超过 180 秒实测](../reports/app_integration_20261020/protocol_after_180s.json)
- [Flash 后独立 BLE 回归](../reports/app_integration_20261020/protocol_flash.json)

## 重建和固化

Android 使用 JDK17、SDK35、Build Tools35.0.0，在 `clients/android/local.properties` 配置 SDK，执行：

```sh
./gradlew :core:protocol:test :core:ble:testDebugUnitTest :core:data:testDebugUnitTest :app:assembleDebug :app:lintDebug
```

本例目录中：

```sh
sh run_sim.sh
sh build.sh
python3 program_sram.py --manifest reports/last_build.json --frequency 2.5MHz
# 完成无线验证后，以下操作替换 Flash 启动区
python3 program_flash.py --manifest reports/last_build.json
```

`reports/ready_build.json` 固定指向本次固化的镜像；新构建不会自动改变该索引。Flash 脚本核验构建通过、位流哈希、器件/保护位、setup/hold，再检测 Flash 型号，执行写入及校验、重载与 UserCode/Status 核验；保留每步日志。
