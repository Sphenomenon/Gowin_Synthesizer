# Android MIDI 页面／后台切换候选

日期：2026-11-02，UTC+08:00。候选：`0.3.3-ble-lifecycle / versionCode 18`。

## 问题与本轮结论

用户明确指出：切换是正常的主动操作，切换后不能要求重新连接。此反馈按连接生命周期
问题处理，不归咎于用户打断测试，也不把持续停留 MIDI 页面当作解决办法。

检查既有源码后确认：MIDI 对象已在 Application 作用域内，页面退出和 Activity
`onStop` 原来只发送 PANIC，没有直接调用断开。但 MIDI 缺少独立后台连接服务，
而全局“设备连接”实际只显示工作站业务状态；MIDI 已连接时仍可能看到业务“未连接”。
本候选分别补齐后台生命周期与状态语义，不声称已证明每次用户切换都发生了 GATT 掉线。

本轮只读检查仍在使用的 versionCode 17 手机进程：`03:42:42.677` 有成功连接回调，
`03:42:43.055` 服务发现成功，`03:42:43.058` 启用 MIDI 通知。截至 `03:57:38`
采集到的该进程可用日志中未见之后的断开回调或崩溃。日志缓冲的缺失不能证明从未掉线，
也不能否定用户观察；新的前后台实际行为仍需安装 versionCode 18 后单独验收。

## 实现边界

- `MidiKeyboard.releaseControls` 统一处理页面退出及 Activity 停止：清持音、丢弃未发
  旧按键、发送 32 条全通道 PANIC、停止扫描，不关闭 GATT，不取消正在建立的连接。
  返回后继续使用同一连接，不补播退出前的按键。
- `MidiConnectionService` 是独立 `connectedDevice` 前台服务。应用级状态进入连接中、
  已连接或主动断开前清理阶段时启动；状态通知与“断开MIDI”按钮独立于工作站服务。
  Android 13 起从 MIDI 连接入口请求通知权限；拒绝通知不被伪报为 BLE 连接失败。
- 服务只订阅连接状态，不因按键计数更新而刷通知。其 `onDestroy` 只取消自身收集任务，
  不取消应用作用域或关闭 MIDI。若启动服务失败，界面明确提示保持应用前台。
- `disconnecting` 保持后台服务直到主动断开的 PANIC 队列排空并关闭；重复断开操作
  不提前截断清理。真正的无线掉线或发送失败仍清理本地状态并报告错误，不把残留 ready
  标志当作保活成功。
- 所有页面同时显示“工作站业务连接”和“25K MIDI · 独立连接”。MIDI 和业务 UUID、
  会话、服务、通知、关闭路径没有合并；工作站未连接不再被泛化为全部设备未连接。
- 保留 versionCode 17 的有证据、最多一次的失效绑定恢复。没有隐藏 API 删除绑定，
  没有关闭加密，也没有重放录音／下载／参数等业务命令。

## 来源与产物身份

本候选从工作区 Android 源码构建，不采用未声明的私有暂存输入。既有 App 功能源来自
提交 `4349cc8404de17eca368223fd485130370d46d2d` 的 Android tree
`d359e6d505645d65537c1355513bdd23932b36c7`，之后叠加本轮 App 恢复与生命周期改动；
未合并其 FPGA 分支。当前工作区包含未提交／新文件，因此不能只用根仓库 HEAD 表示候选。

| 项目 | 身份 |
|---|---|
| App | `cn.gowin.control`，versionCode 18，`0.3.3-ble-lifecycle` |
| 构建 | debug；JDK 17；Gradle 8.10.2；compileSdk／targetSdk 35；minSdk 26；offline |
| APK | `clients/android/artifacts/gowin-control-0.3.3-ble-lifecycle-debug.apk` |
| APK SHA256 | `d3160a8e539cb357bd25bfe75c7a8defc84f84c84cf1b656299a2631008bf0af` |
| 签名证书 SHA256 | `6aedebb7a983a64587b3e02be7e0323ea8dbcd3c0c0bc337b33115f4c883cf39`，与已安装候选一致 |
| 75 个 Android 输入的聚合 SHA256 | `b149d1917a46d31677e2bb50ad56d014d4917343a91e56589402c7880eb6de36` |
| 构建清单 SHA256 | `d6cc6552b3b092434a00f5c9f3f85a46d8a64a66e4e8b2078c703c5139656c8c` |

[构建清单](../artifacts/gowin-control-0.3.3-ble-lifecycle-build.json) 包含工作区 HEAD、
来源树、逐文件输入哈希、聚合算法、配置、APK／签名身份、验证范围和回退身份。
输入清单包含生产／测试源码和构建配置，不将文档、报告、生成目录当作构建输入。
APK 同时复制到本机 `~/Downloads/gowin-control-0.3.3-ble-lifecycle-debug.apk`；
两份 SHA256 一致。产物与原始证据不纳入源码，离开本机后需另行保留这些文件。

本轮未触及 FPGA 输入、综合、P&R、SRAM 或 Flash；没有新 bitstream。此修改不增加
25K／138K 的 RTL 资源，也不声称释放了已占用的逻辑或 BSRAM。

## 离线验证

使用既有 JDK／SDK，从 `clients/android` 运行：

```sh
./gradlew --offline --no-daemon --console plain \
  :core:data:testDebugUnitTest --tests cn.gowin.control.data.MidiKeyboardTest \
  :app:assembleDebug :app:assembleDebugAndroidTest
./gradlew --offline --no-daemon --console plain \
  :core:protocol:test :core:ble:testDebugUnitTest :core:data:testDebugUnitTest \
  :app:assembleDebug :app:assembleDebugAndroidTest :app:lintDebug
```

- MIDI 定向单测 10 项通过；包括新增的退出后仍连接、返回无需重连、连接中退出不取消、
  多次生命周期清理不关闭、主动断开清理期间保活、清理写失败不伪报正常这 6 项。
- 完整单测 106 项：104 通过，2 项显式 opt-in 的无线测试跳过，0 失败、0 错误。
  其中 protocol 20，BLE 68，data 18；最终回归允许 Gradle 复用未变输入的既有结果。
- 主 APK 和 instrumentation APK 编译通过；lint 为 `No issues found.`；
  `git diff --check -- clients/android` 通过。最后一次构建为 27 秒。
- 新增 Compose 的页面销毁／返回回归用替身验证持音清理与同一连接语义，已编译，
  **本候选没有执行设备上的 instrumentation**。不将此前候选的 UI 结果算到本候选。
- 工具仍有既有 SDK XML 版本兼容警告，没有为消除该警告更换工具链或修改工程依赖。

日志与签名检查保存在 `~/.cache/fpga-android/20261102_ble_lifecycle/`：
`targeted-build.log`、`full-validation.log`、`final-validation.log`、`signature.txt`、
`phone-existing-app-events.log`。手机日志只作既有候选的观察，不作新版部署证据。

## 打包时状态、后续验收与回退

**本候选仅完成源码、离线测试和打包，未安装到手机。** 手机仍为
`0.3.2-ble-recovery / versionCode 17`；没有清 App 数据、重置蓝牙或删除绑定，
没有操作手机／模拟器界面，也没有重新复位或编程板卡。暂不干扰用户当前操作。

用户确认可以安装后，再保留数据覆盖安装并分别验证：

1. 连接 `GWK-MIDI`，确认真实连接 ready 及 MIDI 前台服务／通知状态。
2. 按住音符切到控制、录音、作品页，再回音乐页：停音、无旧按键补播、MIDI 保持连接，
   业务未连接不影响该状态；返回可直接发送新音符，无需重新选设备。
3. Home 切后台、打开其他应用、锁屏和恢复，检查连接、进程与服务日志；覆盖用户手机
   的系统省电行为，不能只依据模拟器或单测。
4. 明确点击“断开MIDI”后才走清理并关闭；关闭蓝牙或实际无线失联时不得仍显示已连接。
5. 在接线与授权明确时另做真实 USB／138K 音频验收，不把 App 发送成功当作实板发声。

强制停止、系统杀进程、蓝牙关闭、板端掉电／重配不在“同一连接始终保持”的承诺内；
原有板端易失配对密钥问题也不会因前台服务变为持久密钥。新版长期后台、真实旧绑定
自动恢复及手机→25K→138K 发声均保留为独立验收缺口。

回退保留原 `0.3.2-ble-recovery / versionCode 17` APK，SHA256
`8e60b0e23174d99205bcdfce8b2c119163073e1fba9996b0b5b883c27d696960`。
它与新版签名一致，但降级仍受 Android 安装规则限制；只有用户另行授权后才尝试，
不以卸载或清数据绕过限制，也不覆盖其历史 APK／构建记录。

## 用户授权后的手机安装

2026-11-02 `04:06:32`，用户同意保留数据覆盖安装后，对实体手机执行了指定设备的
`adb install -r`，返回 `Success`。安装 APK 的 SHA256 再次核对为本报告候选身份，
没有重新构建或替换产物。随后仅启动一次 `cn.gowin.control/.MainActivity`，
`am start -W` 返回 `Status: ok`，冷启动耗时 1145 ms；未自动点击连接或切页。

安装后读取包信息确认：`versionCode=18`、`versionName=0.3.3-ble-lifecycle`，
`lastUpdateTime=2026-11-02 04:06:32`；原首次安装时间
`2026-11-01 23:50:29` 保留。没有卸载、清数据、重置蓝牙、删除绑定或操作板卡。
`BLUETOOTH_SCAN`／`BLUETOOTH_CONNECT` 仍已授权；通知权限仍未授权，没有通过 ADB
强制授予，用户可在首次 MIDI 连接时按应用提示选择。

本节将部署状态推进到“实体手机已安装并成功启动”，**不代表切页、后台或锁屏验收
通过**。此后由用户手动重连 `GWK-MIDI` 并切换，观察全局 MIDI 状态和返回后的演奏；
尚未记录这些操作的实际结果。原构建清单保留打包时未部署的历史字段，不回写其哈希。

安装前后包信息、安装输出、启动输出和启动日志保存在本机证据目录的
`phone_install_v18/` 子目录；不收集用户应用内容，也不清空系统日志缓冲。

## 用户手动反馈与运行核验

2026-11-02，用户在收到新版手动切换验证步骤后反馈“没问题”。记录为本轮实际使用中
切换问题未再出现的用户确认，不扩写成每一项锁屏、后台时长、按键或音频路径的独立测量。

随后仅做只读核验，没有代用户切页、点击按键、重连、停止应用或操作板卡：

- 手机仍运行 versionCode 18，进程 PID `11919`。通知权限现在为已授权，附近设备
  扫描与连接权限仍已授权；本轮未通过 ADB 修改权限。
- `04:10:43` 的服务检查确认 `MidiConnectionService` 存活，`isForeground=true`，
  `foregroundId=2`，类型 `0x00000010`（connectedDevice），`startForegroundCount=1`，
  使用独立的 `midi_connection` 通知通道。
- 目标进程日志记录 `04:08:35.247` 成功连接（`status=0`、`connected=true`），
  `04:08:35.687` 服务发现成功，`04:08:35.688` 发起 MIDI 通知使能调用。
  本次取得的该进程可用日志中，未见之后的断开回调、重新建立 GATT 或运行时崩溃。
  这是日志窗口内的观察，不把无回调单独当作长期连接保证。
- APK 对应的 75 个源码／配置输入哈希仍与打包清单一致；本轮只更新说明与验收记录，
  没有改实现、重新构建、覆盖 APK 或回写历史构建清单。

部署／验收状态现在为：**已安装启动、用户手动切换反馈正常、实体手机前台服务运行
已确认**。长时间后台稳定性、逐项锁屏场景、板端重配后的失效绑定自动恢复，以及
手机→25K→138K 实际音频仍为独立验收项；本轮没有执行设备 instrumentation。

只读证据保存在 `~/.cache/fpga-android/20261102_ble_lifecycle/phone_manual_check_v18/`。
其中 `services.txt` SHA256 为
`072bca1ce35f82a7148d7ab099e865c809ae5f62b1e4c33cb3c7e9d67e1192cc`，
`app-connection-events.log` SHA256 为
`ed7c602be43a2bebc98be99d368ca3dc5d8c60f839d7231b5a2b97bf2d744c60`。
