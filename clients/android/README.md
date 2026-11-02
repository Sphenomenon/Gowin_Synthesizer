# GOWIN Control Android

当前演示候选为 **0.3.5-presentation / versionCode20**：简化蓝牙与录音页面，原本地工作站入口显示为“扫描并接入 138K”，录音按实际经过时间封存《小星星》短旋律，再经原协议下载与 WAV 保存后试听。底层仍保留本地来源元数据，真实 BLE／A2DP 路径独立保留；此呈现调整不构成实板无线验收。构建、安装及验证见[本轮记录](reports/PRESENTATION_20261102.md)。此前毫秒时长与生命周期修改继续保留，见[短录音显示报告](reports/RECORDING_DURATION_20261102.md)及[原交付记录](docs/DELIVERY_CHECK_20261102.md)。

已实装的生命周期版本为 **0.3.3-ble-lifecycle / versionCode18**，以0.3.1-demo-d3为基础，保留音乐／MIDI及工作站业务功能，包含单次、有证据的旧绑定恢复、独立MIDI前台连接服务，以及跨页面区分MIDI／工作站的连接状态。切页／后台只停音，不主动断开MIDI；只修改App，不要求FPGA综合或烧录。来源和边界见[连接恢复说明](docs/BLE_RECOVERY_20261102.md)，其手机安装、用户切换反馈、验证范围与剩余验收见[生命周期报告](reports/BLE_LIFECYCLE_20261102.md)。

历史25K独立业务协议联调版为 **0.2.10 / versionCode13**，[APK](artifacts/gowin-control-0.2.10-gw25k-second-debug.apk)。优先协商OPEN_SECOND0x40，每个最多8112字节PCM块选择RAW、一阶/k9或二阶/k5的更短结果；逐字节无损恢复。APP完成逻辑/PCM CRC、对象与范围校验后交付PCM，可靠落盘后确认。仅明确UNSUPPORTED才40→3d→3c→3b→39→38→37→36→30回退。协议见[二阶扩展](../../projects/25k/example/RTL8723DS_PROTOCOL/docs/SECOND_TRANSFER_EXTENSION.md)，验收见[第十八轮](../../projects/25k/example/RTL8723DS_PROTOCOL/reports/speed18_20261020/README.md)。

电脑同一固件三组一阶/二阶交替，中位有效PCM吞吐14.11→22.09 KB/s（+56.6%）；同一APP核心完整音频流程18.65→14.15秒（耗时−24.1%），含固定检查点取消重开、重连续传、执行后DATA丢失重试和WAV保存。Flash固化后完整下载13.72秒，三份WAV均精确匹配参考。详见[APP联调](../../projects/25k/example/RTL8723DS_PROTOCOL/docs/APP_INTEGRATION.md)及[第十八轮](../../projects/25k/example/RTL8723DS_PROTOCOL/reports/speed18_20261020/README.md)。手机原生GATT/UI/后台和实际速率待测；板卡重启或重配置后先删除未完成下载，历史boot_id重复问题仍保留。

APK与签名密钥按仓库规则不进入Git；`artifacts/`链接指本机归档文件。克隆后可按下面命令构建，在`app/build/outputs/apk/debug/app-debug.apk`取得APK。25K测试不代表138K业务固件已部署。

## 手机音频与25K MIDI（0.3.1-demo-d3源码）

“音乐”页使用系统文件选择器读取手机音频，支持本地播放及选定的 A2DP 媒体设备。先明确选择手机扬声器／耳机或实际蓝牙设备；播放器用 `setPreferredDevice` 请求输出，再以 `MediaPlayer.routedDevice` 的设备 ID 核对实际路由。输出不符超过两秒、已确认的路由改变或所选设备消失时暂停。BLE 业务或 MIDI 连接不代表 A2DP 已连接，也不以任意蓝牙设备名称冒充138K。进入后台暂停，不提供后台播放服务。

同页提供手机→25K的16键 MIDI 控制（音符48..63），支持力度1..127、通道1..16、按住／释放／取消手势、全通道 PANIC。连接独立扫描25K已有标准 BLE MIDI 服务 `03b80e5a-ede8-4b33-a751-6ce34ec4c700`，使用既有 `7772e5db-3868-4112-a1a9-f2669d106bf3` 特征的 Write Without Response；每个特征值只有一个5字节带时间戳事件，不新增业务协议 opcode，不依赖可能批量封包的 MIDI 适配器。数据层管理有界发送队列、旧会话清理和重连前 PANIC；UI 不编码报文。25K USB仍接138K Host，手机无需占用其USB口。

**当前25K维护固件收到BLE主机音符只更新远端灯光，不转发USB、不本地发声。** 因此本次 Android 实现不代表手机键盘能经25K驱动138K声音；后续转发由设备端另行实现和验收。用户已确认25K→138K的USB转发由用户自行实现，本分支本轮不修改25K源码或固件。GATT写入完成也不等于设备已应用或发声。现有业务连接、录音下载和25K内置音频测试分支保留。

当前 W 设备工作目标是 headless A2DP→D实时效果→DAC，并保留USB Host／25K；HDMI、分析、录音和下载暂停。旧版全HDMI／录音共存说明保留在历史记录，不转授给本轮。Android构建、83项单测（2项硬件测试跳过）、5项模拟器UI检查、APK身份与待验范围见[2026-11-01记录](docs/DEMO_D3_20261101.md)；此前 demo-d1/d2 见[历史记录](docs/DEMO_D1_20261031.md)。

## 构建

使用 JDK 17、Android SDK Platform 35、Build Tools 35.0.0。Android Studio 中打开本目录，或在本目录执行：

```sh
./gradlew :core:protocol:test :core:ble:testDebugUnitTest :core:data:testDebugUnitTest :app:assembleDebug :app:lintDebug
```

若设备现装版本使用不同签名，可在同一构建命令加 `-PpresentationInstall=true` 生成独立包 `cn.gowin.control.presentation`；保留默认包名和手机原有 App／数据。此选项只改变安装包身份，源码和业务链路相同。

`local.properties` 中设置本机 `sdk.dir`（Android Studio 通常自动生成）。首次需要联网下载固定版本依赖。Wrapper 为 Gradle 8.10.2，发行包 SHA256 已锁定。APK 输出为 `app/build/outputs/apk/debug/app-debug.apk`。调试 APK 用于联调，发布签名不进入源码。

## 使用

1. 安装并打开 App，选择“扫描并接入 138K”进入本地演示工作站；真实扫描仍通过“选择蓝牙设备”进入。演示录音上限 10 秒，点击开始后按单调时钟计时，停止或录满才封存对应时长的《小星星》片段，开始前没有可下载录音。界面使用正常操作文案，来源由内部 `demo`／`source` 元数据保留。
2. 录音页开始录音，停止或等待容量满，点击“下载 / 继续”；完整 CRC 通过后生成 WAV，再到作品页试听、重命名、导出、分享或删除。
3. 真实设备在“选择蓝牙设备”中扫描业务服务并连接。授予附近设备权限；Android 8–11 还需满足系统 BLE 扫描的位置权限/位置服务要求。长连接使用可暂停/断开的前台通知。
4. 下载可以暂停或断线恢复。连接设备重启、录音清除或身份改变后，旧临时文件不能拼接到新录音。App 进程结束后，重新连接原对象并点击“下载 / 继续”可从可靠检查点恢复。

真实连接使用业务服务 `9b6d0000-4c2a-4f87-9a31-138000000001`。25K 本例已提供命令与内置音频录音子集；旧 FFF0/FFF1 BTST 底层固件不提供业务服务。

## 代码入口

| 模块 | 职责 |
|---|---|
| `app` | Compose UI、权限、前台连接服务、手机试听/SAF 导出/分享 |
| `core/protocol` | 小端报文、CRC32、分片、模型、严格边界校验和规范向量 |
| `core/ble` | 真实扫描、UUID 服务发现、串行 GATT 操作、会话/请求调度、响应/数据乱序处理 |
| `core/data` | 状态与录音业务、协议级模拟设备、检查点、PCM/WAV、作品元数据、下载重试与恢复 |

初版采用原子文件清单保存下载检查点和作品元数据，避免数据库与音频文件无法同时原子提交的问题；未引入 Room/DataStore。恢复以磁盘检查点和前缀 CRC 为准，UI 索引可重建。界面采用“松开滑条后提交”以避免旧值排队；效果排序提供上移/下移，提交时整链应用。

## 已实现边界

- 源码新增可选 `REC_FORMATS 0x43`：HELLO 后显式协商，只有合法 UNSUPPORTED 才保持旧格式1/48k；格式2严格对应44.1k，按对象rate封装WAV并绑定续传身份。未占用旧Capability保留位。此源码阶段尚未发布新APK，未接入138K设备后端，也不改变下述0.2.10/25K已验收范围；维护合同见[主协议6.1节](../../BLUETOOTH_PROTOCOL_V1.md#61-显式协商的双采样率录音扩展2026-10-30)。
- 协议v1.0默认MTU23、20字节特征值、256字节PCM块、窗口1；可选OPEN_WIDE/COMPACT/BULK/DIRECT使用460字节PCM块，OPEN_LONG使用972字节，OPEN_EXTENDED按协商MTU最多8112字节。B3 DATA最多64片；显式LONG/EXTENDED Transfer分别允许逻辑1020/8160字节，其他路径仍512。
- OPEN_LOSSLESS3d允许RAW/一阶codec10，OPEN_SECOND40允许RAW/一阶codec10/二阶codec11；旧READ31/35始终RAW，3e/3f始终只允许RAW/10。解码后原PCM16通过校验，再本地封装WAV。高速窗口、ADPCM、Wi-Fi/USB文件通道尚无已定义设备契约。
- 模拟模式使用同样的编解码和下载链，但不启动真实蓝牙前台服务，不承诺模拟模式在系统杀进程后自动继续。
- 活跃真实下载可在断连后最多退避重连 5 次；用户停止/权限撤销/对象失效等仍需处理。仅控制且无下载时断线会显示状态，需要用户重新连接。
- 逐块可靠保存后才 ACK 或 ACK_READ，持久化开销需要真机测量。进度分别记录 received/durable/confirmed；未校验数据不会显示为完成作品。
- 试听是前台手机播放，进入系统后台暂停，不是设备实时音频流。无麦克风、所有文件访问或媒体库读取权限。
- 当前没有稳定设备 ID、固件版本、RTC 录制时间字段，不以 MAC/名称冒充设备身份；作品显示的是手机保存时间。

## 验证

单元测试覆盖协议规范向量/CRC、37 片边界、重复/跳片/超时、无符号 ID、状态布局、文件尾截断/损坏恢复、WAV 头与 data CRC，以及模拟外设的数据先于响应到达、revision 冲突和重复 ACK。构建/模拟器验证记录见 `docs/VALIDATION.md`。

仍需真机验证 BLE 权限、射频连接、锁屏和厂商省电行为；工作站业务 RTL、控制窗口生命周期、DDR 录音和集成时序分别由设备端验收。详见仓库根目录的安卓方案与协议文档。
