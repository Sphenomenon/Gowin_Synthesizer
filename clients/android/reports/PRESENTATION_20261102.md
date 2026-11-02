# Android 演示页面与计时录音

2026-11-02，`0.3.5-presentation` / versionCode20，来源分支 `codex/dual-138k-workstation`，App 修改起点 `5f9c3163`。

本轮仅修改 Android 维护源码。蓝牙、MIDI、录音、作品与音乐页面清理协议握手、调试统计、测试标签和冗长免责声明，保留正常权限、断线、播放失败及删除确认。原本地工作站入口改为“扫描并接入 138K”，显示名称为“138K 工作站”；真实 BLE 扫描仍由“选择蓝牙设备”进入，未替换真实传输实现。

本地录音从左右固定测试音改为《小星星》前两句：C4 C4 G4 G4 A4 A4 G4 / F4 F4 E4 E4 D4 D4 C4，普通音半秒、句末一秒，8 秒一轮，最多录制 10 秒。单调时钟决定已录帧数；录制期间不可下载，停止或录满后才封存实际长度。PCM16 双声道相同，带音符起落和最终截断淡出，仍经过原报文、CRC、下载检查点与 WAV 保存链，未预写作品。内部 `demo` / `source` 来源元数据保留，页面呈现不改变实板无线完成状态。Push 对应操作见[演奏说明](../docs/TWINKLE_PUSH.md)。

## 验证

- 单测 114 项：112 通过，2 项既有无线测试跳过，零失败。
- 旋律专项验证 14 个音符频率、双声道、幅度和连续性；协议专项验证 3.25 秒对应 156000 帧、录制时拒绝下载、停止后长度固定，以及下载 PCM 与旋律逐字节一致。
- APK、测试 APK、lint 均通过；lint 零错误、零警告。
- 模拟器 9 项 instrumentation 全通过，包括旧 MIDI 生命周期、按下／释放／取消／停音、实际本地输出／定位／暂停、能力分支和新增整条录音流程。新增流程从连接、空录音开始，真实等待至少 2.3 秒，停止、下载、作品试听，验证 Android MediaPlayer 已开始播放。首轮旧测试仍查找已移除的路由提示，断言改为实际输出标签后，完整重跑通过；首轮日志保留。
- vivo Y77 / V2219A 已安装独立包 `cn.gowin.control.presentation`。原 `cn.gowin.control` v18 与数据保留；因签名不一致，使用显式 `-PpresentationInstall=true`，未卸载或清数据。系统身份验证由用户在手机完成。
- 手机现有本轮录音为 48 kHz、PCM16、双声道、289776 帧 / 6.037 秒，WAV 1159148 字节，SHA256 `5df09ca38460bb65ea61ad03ba65bf5957ac127f0350c3859cd70dbc44a43b6a`。读取副本后核对前 11 个完整音符和双声道一致性；未清除该作品。点击试听后，本应用独立播放器的 Android audio 日志出现 started、device、stopped，约 6.2 秒完成。

本轮不操作 FPGA，不综合、不烧录、不写 Flash；不将本地演示录音计为 138K BLE／DDR 录音或 A2DP／DAC 验收。

## 身份与复现

构建环境为 JDK17 / Gradle8.10.2 / SDK35；构建命令在 `clients/android`：

```sh
./gradlew --offline --console=plain -PpresentationInstall=true \
  :core:protocol:test :core:ble:testDebugUnitTest :core:data:testDebugUnitTest \
  :app:testDebugUnitTest :app:assembleDebug :app:assembleDebugAndroidTest :app:lintDebug
```

APK SHA256：`2df030629894a898f59459ede6d0ae41ed7f0aa65bcc48d7e67d8ee01c56b026`。
最终测试 APK SHA256：`01c32801f1117f670316c914a2c4f94d5136efbb1a3a579b0fb96dfb2b5d4bf2`。

源码逐文件 hash、APK 副本、手机录音副本／校验、手机及模拟器截图在本机外部证据目录 `~/.cache/gw138k-dual-20261031/android-v20-presentation-v1/verification.json`；完整构建和两轮界面测试日志在其父目录 `android-v20-presentation-*.log`。生成文件不入 Git。回退可撤销本轮 App 提交或直接打开保留的原包；不影响 M/W 冻结输入及其他未提交工作。
