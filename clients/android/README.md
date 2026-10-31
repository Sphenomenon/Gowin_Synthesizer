# GOWIN Control Android

当前25K联调版为 **0.2.10 / versionCode13**，[APK](artifacts/gowin-control-0.2.10-gw25k-second-debug.apk)。优先协商OPEN_SECOND0x40，每个最多8112字节PCM块选择RAW、一阶/k9或二阶/k5的更短结果；逐字节无损恢复。APP完成逻辑/PCM CRC、对象与范围校验后交付PCM，可靠落盘后确认。仅明确UNSUPPORTED才40→3d→3c→3b→39→38→37→36→30回退。协议见[二阶扩展](../../projects/25k/example/RTL8723DS_PROTOCOL/docs/SECOND_TRANSFER_EXTENSION.md)，验收见[第十八轮](../../projects/25k/example/RTL8723DS_PROTOCOL/reports/speed18_20261020/README.md)。

电脑同一固件三组一阶/二阶交替，中位有效PCM吞吐14.11→22.09 KB/s（+56.6%）；同一APP核心完整音频流程18.65→14.15秒（耗时−24.1%），含固定检查点取消重开、重连续传、执行后DATA丢失重试和WAV保存。Flash固化后完整下载13.72秒，三份WAV均精确匹配参考。详见[APP联调](../../projects/25k/example/RTL8723DS_PROTOCOL/docs/APP_INTEGRATION.md)及[第十八轮](../../projects/25k/example/RTL8723DS_PROTOCOL/reports/speed18_20261020/README.md)。手机原生GATT/UI/后台和实际速率待测；板卡重启或重配置后先删除未完成下载，历史boot_id重复问题仍保留。

APK与签名密钥按仓库规则不进入Git；`artifacts/`链接指本机归档文件。克隆后可按下面命令构建，在`app/build/outputs/apk/debug/app-debug.apk`取得APK。25K测试不代表138K业务固件已部署。

## W-DEMO手机音乐入口（0.3.0-demo-d2源码）

新增“音乐”页：使用系统文件选择器选取手机音频，异步准备后通过Android的真实媒体播放接口播放／暂停／定位，系统蓝牙入口用于配对和连接138K媒体音频。音乐播放与原BLE参数／录音下载分别保持各自连接，未把BLE业务连接当成A2DP已连接。

页面先报告系统是否存在A2DP媒体输出，再根据`MediaPlayer.routedDevice`报告实际路由。未连接A2DP时播放按钮关闭；播放后两秒内未形成实际A2DP输出则暂停，媒体断连也暂停，不将手机扬声器或模拟设备标成工作站声音。切换到BLE控制／录音／下载页时音乐继续，应用进入后台时暂停；本阶段不提供后台播放服务。选择的文件通过SAF授权读取，不申请所有文件或媒体库读取权限。

真实设备未公布参数读取／设置能力时，控制页只显示其已公布的录音／下载能力、状态刷新和音乐页入口，提示在工作站／25K调参；不显示默认A/B/C、音色或声部数，也不推断D实际状态。25K内置音频与最小协议测试页保留各自说明。

这是手机侧实现，实际手机→138K A2DP／SBC→D效果→DAC／HDMI及BLE录音共存仍需与同一W候选实测。模拟器可以验证文件选择、播放器准备和未连接状态，不能证明真实蓝牙媒体传输。本次源码／构建回归、APK身份及待验范围见[2026-10-31验证记录](docs/DEMO_D1_20261031.md)。

## 构建

使用 JDK 17、Android SDK Platform 35、Build Tools 35.0.0。Android Studio 中打开本目录，或在本目录执行：

```sh
./gradlew :core:protocol:test :core:ble:testDebugUnitTest :core:data:testDebugUnitTest :app:assembleDebug :app:lintDebug
```

`local.properties` 中设置本机 `sdk.dir`（Android Studio 通常自动生成）。首次需要联网下载固定版本依赖。Wrapper 为 Gradle 8.10.2，发行包 SHA256 已锁定。APK 输出为 `app/build/outputs/apk/debug/app-debug.apk`。调试 APK 用于联调，发布签名不进入源码。

## 使用

1. 安装并打开 App，选择“体验模拟设备”，无需蓝牙权限即可查看控制、录音、作品页面。模拟录音上限 10 秒，生成左 440 Hz、右 660 Hz 的测试音频；结果标记为模拟文件。
2. 录音页开始录音，停止或等待容量满，点击“下载 / 继续”；完整 CRC 通过后生成 WAV，再到作品页试听、重命名、导出、分享或删除。
3. 真实设备在“连接设备”中扫描业务服务并连接。授予附近设备权限；Android 8–11 还需满足系统 BLE 扫描的位置权限/位置服务要求。长连接使用可暂停/断开的前台通知。
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
