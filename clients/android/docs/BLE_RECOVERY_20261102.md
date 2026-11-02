# App 连接恢复与快速迭代边界

本次 Android 源码以已实装的 `0.3.1-demo-d3` 为基础：来源提交
`4349cc8404de17eca368223fd485130370d46d2d`，最近 Android 提交
`bb0319780f0c4c4bf12c45bec8f56afbbee67073`，Android tree
`d359e6d505645d65537c1355513bdd23932b36c7`。只引入该身份相对主线的 Android
源码／测试／文档差异，不合并 FPGA 分支，也不覆盖旧 APK 与历史构建清单。

旧绑定恢复候选为 `0.3.2-ble-recovery / versionCode 17`，后续生命周期候选为
`0.3.3-ble-lifecycle / versionCode 18`；源码实现、离线测试、Android
原生 UI 测试、实体手机正常连接、真实失效绑定自动恢复分别记录，不混为一项验收。

## 恢复条件

1. 保留失败的 GATT 阶段和原始状态码；133 不等于密钥缺失。
2. 每次建立连接单独监听目标设备的绑定状态。Android 16 起同时监听公开的
   `android.bluetooth.device.action.KEY_MISSING`；继续使用 compileSdk／targetSdk 35，
   不要求旧系统提供新广播。
3. 只有观察到既有绑定已被系统移除且当前为 `BOND_NONE`，才自动新建 GATT 重试一次。
   认证状态 5／15、已有绑定的 133 或密钥缺失事件可触发最多 3 秒的状态等待；
   普通 133 不会被直接判成配对故障。
4. 重试前释放旧 GATT，等待 350 ms，并再次检查没有进入新的配对过程。
   不重放用户按键、控制参数、录音或下载命令。
5. 用户取消／断开、任务取消或发起新连接会取消旧恢复；旧 GATT 回调继续由 epoch
   和实例身份隔离。第二次失败直接停止，保留两次异常，不进入无限重试。
6. 系统没有移除旧绑定时，不调用隐藏的 `removeBond`／`refresh`，不关闭加密，也不
   自动 `createBond`。有认证／密钥证据时给出明确的单设备处理提示及系统设置入口。

## 两种连接边界

- MIDI：连接、服务发现与 CCCD 订阅均在恢复范围内；成功后仍须发送原有 32 条
  全通道 PANIC，才允许新按键。连接建立后的掉线不会自动重放旧按键。
- 工作站业务：`BleTransport.establish` 将 GATT 建连、能力读取、通知订阅和 HELLO
  身份校验纳入同一次有界建立流程。每次尝试创建独立 `ProtocolSession`；只有真正
  完成协议握手，后续原有初始化才继续。恢复不包裹参数变更、录音或下载。
- BLE MIDI UUID 和工作站业务 UUID 不合并，不按设备名称猜测业务能力。首页的业务
  连接不接受仅有 MIDI 服务的固件。

## 页面与后台生命周期

- MIDI 连接继续归 Application 作用域所有，不归某个 Compose 页面或 Activity 所有。
  页面退出与 Activity `onStop` 统一调用 `releaseControls`：丢弃未发送的旧按键，
  清除持音，发送 PANIC 并停止扫描；不会调用 `disconnect`，也不会取消正在建立的连接。
- 连接中／已连接／主动断开前清理期间，由独立 `MidiConnectionService` 以
  `connectedDevice` 前台服务维持后台运行优先级。通知展示状态并提供明确的断开按钮；
  不与工作站业务服务共用通知 ID、作用域或关闭路径。服务组件销毁本身不关闭 MIDI。
- 主动断开时，`disconnecting` 状态保持服务有效，直到有界队列中的 PANIC 清理与
  关闭完成；重复点击不提前截断清理。发送失败仍明确报告并关闭，不伪装成连接正常。
- 所有页面同时区分“工作站业务连接”和“25K MIDI 独立连接”；没有工作站业务连接
  不表示 MIDI 未连接。只有真实 MIDI ready 状态允许演奏，返回页面不重放旧按键。
- 这不是无限自动重连，也不承诺强制停止、系统杀进程、关闭蓝牙或板端掉电后仍保持
  同一连接。前台服务启动失败会给出提示；系统省电策略下的持续运行仍需实体手机验收。

实现和候选身份、离线验证、既有手机观察与待做的切换／锁屏验收分别见
[生命周期报告](../reports/BLE_LIFECYCLE_20261102.md)。

## 不需要 FPGA 综合的验证

在 Android 工程目录，使用 JDK 17 和既有 Android SDK 35：

```sh
./gradlew :core:ble:testDebugUnitTest --tests cn.gowin.control.ble.GattConnectionRecoveryTest
./gradlew :core:data:testDebugUnitTest --tests cn.gowin.control.data.MidiKeyboardTest
./gradlew :core:protocol:test :core:ble:testDebugUnitTest :core:data:testDebugUnitTest
./gradlew :app:assembleDebug :app:assembleDebugAndroidTest :app:lintDebug
```

单元测试用真实故障顺序建模：旧绑定 → 订阅 133／认证 5 → 系统移除绑定 → 新连接。
同时覆盖不移除绑定、普通 133、用户取消新配对、恢复等待／延迟中取消、第二次失败、
配对状态改变、缺少工作站服务，以及 MIDI 恢复期间不接受按键。Compose 测试明确使用
带 fixture 标识的替身，不将其算成实体 25K 自动恢复验收。

原始手机故障见 [实体手机排查](../reports/PHONE_BLE_MIDI_20261102.md)。新的实测证据
另行保存；不为了制造旧密钥故障而擅自复位、重载或烧录 FPGA。App 不会让板端的易失
密钥变成持久密钥，也不能补齐未实现的 138K 业务服务／实际音频路径。
