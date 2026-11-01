# 当前手机交付复核

日期：2026-11-02（Asia/Shanghai）。当前 App 仍为 `0.3.1-demo-d3`／versionCode16。本次核对维护源码、重新执行测试并恢复隔离模拟器，未修改 App 业务源码、协议、依赖或25K／138K固件。手机向25K发送 MIDI、本机音频文件选择、本地播放和向具体 A2DP 设备播放的入口均已存在，不以新增页面代替真实接口。

用户已确认25K→138K的USB转发由用户自行实现，本分支本轮不修改25K。当前25K维护源码收到BLE主机音符仍只更新灯光；App发送完成不能证明25K转发或138K发声。

## 当前构建与执行

使用既有 JDK17、Android SDK35／Build Tools35.0.0 和 Gradle8.10.2，执行原有全部单测、App构建、lint和测试APK构建。首次构建成功，大部分任务命中缓存；随后以 `--rerun-tasks` 强制重新执行三个核心模块的测试及其输入任务，35项任务实际执行，23秒成功。83项单测中81项通过，2项原有实体设备测试跳过，零失败／错误。Lint零错误，7条既有固定依赖版本提示；没有为这些提示升级依赖。

APK SHA256为 `c19645ec9e981a267738d3f637b94cbd7febfdc19d28c79ac9ae41a69139c5be`，与已记录的demo-d3相同。测试APK也保持原身份。重新安装到模拟器并执行完整instrumentation，5项通过，13.789秒：3项能力分支UI检查、真实MediaPlayer本地路由／定位／暂停、明确标记为夹具的MIDI按下／释放／取消／PANIC检查。MIDI夹具不证明真实GATT或射频接收。

本机可安装文件为 [gowin-control-0.3.1-demo-d3-current-debug.apk](../artifacts/gowin-control-0.3.1-demo-d3-current-debug.apk)，已从本次复核的APK逐字节归档并重新核对上述SHA256；APK按规则留在ignored目录，不进入Git。README首入口指向此版，原0.2.10仅保留为独立25K录音联调历史。克隆到其他机器后需按README重新构建。

## 隔离模拟器和实际文件选择

检查时ADB没有设备、默认位置没有已注册AVD。复用已安装的 `system-images;android-35;google_apis;arm64-v8a`，在本机证据目录内创建独立AVD `dual138k-delivery-v4`，无窗口、无音频、2核／2GB启动；不下载系统镜像、不改其他虚拟机。首次创建因命令行工具所在SDK根与系统镜像所在SDK根不同而失败，日志保留；显式设置工具的 `com.android.sdkmanager.toolsdir` 后创建成功。实际启动和ADB设备身份均单独记录。

对同一正式App另做系统SAF路径核验：进入“音乐”→“选择音频文件”→系统Downloads→选择明确命名的8秒静音WAV夹具。App显示实际文件名、8秒时长；未选择输出时播放按钮的可点击父节点保持disabled。明确选择系统本地扬声器后播放，界面实际显示“手机扬声器”和“已确认实际路由与选择一致”，再暂停。截图及UI层次已保存并人工查看。此静音文件仅验证手机文件访问和MediaPlayer路由，不用作W输入或音频功能验收。

完整来源、APK、测试XML、命令日志、AVD配置、进程身份和截图SHA256清单：

`/Users/sphenicidition/.cache/gw138k-dual-20261031/android-current-delivery-v4/verification.json`

## 仍待实体设备验收

本次没有连接实体安卓手机或修改板上镜像。真实25K BLE MIDI发现／订阅／写入、真实手机A2DP配对与设备路由、断连暂停、长时间无线播放，以及W的SBC解码／D效果／25K控制／I2S与DAC连续输出仍须分别实测。模拟器本地输出和MIDI夹具不能替代这些验收。
