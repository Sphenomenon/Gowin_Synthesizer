# A07：采样率元数据、显式协商与 Android WAV

日期：2026-10-30（Asia/Shanghai）。本阶段完成维护协议与 Android 源码的双采样率录音格式支持：**旧 format 1 仍严格为 48 kHz；format 2 仅在当前会话显式协商后表示 44.1 kHz。** Android 协议、会话、文件和续传回归通过。显示 v1.1 只有合同，138K 设备后端尚未接入此扩展；不勾选 A07/R01/R03 整体验收。

机器记录：[a07_sample_rate_metadata.json](workstation_task_20261030/a07_sample_rate_metadata.json)，包含 15 个修改/新增源码及文档的身份、直接参与编译的 31 个维护 core 源文件/测试身份、完整 JUnit 汇总、工具来源和证据哈希。记录生成时尚未提交，没有运行 EDA、操作板卡、下载 SRAM 或写 Flash。

## 兼容设计与维护入口

线协议仍由根目录 [BLUETOOTH_PROTOCOL_V1.md 第 6.1 节](../../../../../BLUETOOTH_PROTOCOL_V1.md#61-显式协商的双采样率录音扩展2026-10-30) 维护。原 HELLO major=1/minor=0、20 byte Capability、48 byte REC_INFO、18-bit 音符事件及 PCM 下载编码均未改义，也没有占用 Capability 保留位。旧 Android 会拒绝 bit8 以上能力，因此扩展通过独立可选 opcode `0x43 REC_FORMATS` 启用。

请求固定 8 byte：extension_version=1、reserved=0、client_format_mask。bit0=format1/48k，bit1=format2/44.1k；Android 请求 mask=3。成功响应固定 16 byte，返回版本、零保留字段、接受的子集 mask 和当前非零 boot_id；必须包含原格式 1。原逻辑消息 CRC、request_id 和 HELLO nonce 继续保护这次请求/响应。

只有完整合法的 UNSUPPORTED 才回退到 legacy mask=1。timeout、CRC/nonce/boot 错、非零保留字段、非法版本/集合、BUSY 或畸形成功响应都会失败，不据此降级。grant 绑定启动身份与当前会话，在新握手、断连、close、合法状态明确关闭控制窗口，或 SESSION_REQUIRED/CONTROL_DISABLED 响应时撤销。重连重新协商，磁盘检查点不保存可跨会话复用的 grant。

只读检查独立 25K 后端：`ble_protocol_command.v` 先校验 CRC/nonce，再将非 HELLO/STATUS 命令交给 recording；`ble_recording.v` 的 unknown-op default 返回 `reject(8'h80)`。本次没有修改 `projects/25k/`，也没有把该独立后端冒充 138K 集成服务。

新设备端应在没有 grant 时拒绝格式 2 的 INFO、START 与所有 OPEN 变体；即使客户端猜中对象 ID 也不能绕过。格式授权不切换 DAC 时钟；实际输出率不匹配所请求格式时仍返回 INVALID_STATE。这个设备端行为目前是待集成合同，没有以 Android fixture 作为硬件实现证明。

## Android 改动

依赖方向保持 `app → data → ble → protocol`。新增 protocol `RecordingFormats` 是格式/rate 配对的统一校验入口；format1=48000、format2=44100、channels=2、PCM16LE、每帧 4 byte。REC_INFO 解码默认只接受旧格式，只有显式 grant 才放行格式 2，同时校验 boot、状态、READY/CRC-valid、帧数/容量和 `bytes=frames×4`。codec0/10/11 与采样率正交，其原协商规则、解码和 CRC 未改。

`ProtocolSession.handshake()` 保留原调用行为；data 连接流程在存在录音/下载能力时调用独立 `negotiateRecordingFormats()`。最小协议设备不被迫接受新命令。grant 只有在全部检查成功后发布给 data 层。

`Workstation.startRecording(seconds, format=1)` 默认仍请求旧格式；调用者可以明确选择 format=2。目标帧数按选中格式的率计算，设备必须确认实际时钟相符。**已封存对象的 rate 只描述该对象，不能用它推断当前 DAC 或下一段录音的 rate。** 本轮未新增 UI 采样率选择控件，也未宣称已经实现自动跟随文件/DAC 切换。

下载恢复核对 boot/id、format/channels/rate、frames/bytes/capacity/CRC 和 READY，禁止同一字节流被重解释为另一采样率。原可靠检查点已包含格式、声道和 rate；新增回归确认改变格式/rate 会清除不可信前缀。仍然先可靠落盘再 ACK。

WAV 封装要求 READY、已授权格式、完整 PCM 长度和全量 CRC 全部通过；sample_rate 取已验证对象值，byte_rate=sample_rate×4。44.1 kHz 对应 176,400 B/s，48 kHz 对应 192,000 B/s，block_align=4、bits=16 保持。作品元数据新增实际 rate，旧作品缺字段时仍按原 48 kHz 解释。UI 只调整时长显示，按录音/作品自身 rate 换算，没有在 UI 放报文编码。

## 显示合同的未集成范围

[DISPLAY_DATA_LAYOUT_V1.md](../DISPLAY_DATA_LAYOUT_V1.md) 新增显式选择的 major1/minor1 合同：音频 descriptor word4 为实际 rate，word14 为非零 stream_epoch；metadata word13 为实际 rate，word14 为同一 epoch，word15 仍保留 0。同一快照不得拼接不同 rate/epoch 的旧 analysis；source_sequence 的原独立含义保留。

minor1 只能在全部参与 reader 明确支持后启用，版本字段本身不算协商。当前 minor0 RTL、已验常量和默认 profile 均未改变。本轮没有改显示 writer/reader，也没有实现 epoch 的音频拥有者/CDC/切换清理；双率频轴、慢 reader 和跨 epoch 发布仍需独立实现与验证。BLE 录音 format ID 与显示 format 编号不共用。

## 实际验证

本机原无 JDK/Android SDK 配置。本轮在任务 cache 下载官方 Temurin17.0.21+9，按 Adoptium 发布 SHA256 验证；提取 Google 官方 API35 `android.jar`，先核对 repository XML 发布的 package SHA1，并另记归档 SHA256。没有修改全局 Java/SDK 设置。使用仓库 wrapper 锁定的 Gradle8.10.2、Kotlin2.0.21、coroutines1.9.0、JUnit4.13.2。

独立 JVM Gradle harness 直接读取维护的全部 core/protocol、core/ble、core/data 源目录，**包括真实 `AndroidBleTransport.kt` 与 `Workstation.kt`**，对官方 API35 jar 编译，没有替换成伪 API stubs。所有现有 core JUnit 类与新增回归实际执行：

| 层 | 总数 | 通过 | 原条件跳过 |
|---|---:|---:|---:|
| protocol | 16 | 16 | 0 |
| ble | 52 | 51 | 1 |
| data | 7 | 6 | 1 |
| 合计 | **75** | **73** | **2** |

0 failure、0 error，最终 `BUILD SUCCESSFUL`，10 秒。两项跳过仍是原 RealBoardSessionTest/RealRecordingTest 的物理 radio 前置条件；本轮没有连接物理 radio。第一次编译新增 fixture 时缺少 ExperimentalCoroutinesApi import，修复后完整运行通过，原始失败 log 和成功 log 均保留。

新增覆盖包括：未经协商的格式 2 拒绝；格式/rate/channels/geometry/boot 交叉错误；未知 mask/保留位/版本/长度；合法 UNSUPPORTED；BUSY、timeout、CRC、nonce、boot 错不回退；相同 ID/字节重试；新 HELLO/断连/控制窗口关闭/会话失效撤销 grant；旧 48 kHz Demo 命令、录音、PCM 下载和 WAV 流程继续通过。

44.1 kHz fixture 生成左 440 Hz、右 660 Hz、882 帧/3528 byte PCM，使用真实分片、逻辑 CRC、PCM 块 CRC、可靠落盘检查点和 ACK；在 offset=256 取消后，用新 HELLO 重新协商并核对原对象再续传。最终 WAV 的 PCM 逐字节相同，sample_rate=44100、byte_rate=176400。它证明离线客户端链路，不证明实际声学输入、138K DMA、射频或手机行为。

缓存根目录：`/Users/sphenicidition/.cache/gw138k-task-20261030/android-a07`。实际复核命令：

```sh
JAVA_HOME='/Users/sphenicidition/.cache/gw138k-task-20261030/android-a07/jdk-17.0.21+9/Contents/Home' GRADLE_USER_HOME=/Users/sphenicidition/.cache/gw138k-task-20261030/android-a07/gradle '/Users/sphenicidition/.cache/gw138k-task-20261030/android-a07/jdk-17.0.21+9/Contents/Home/bin/java' -classpath /Users/sphenicidition/Documents/Gowin_Synthesizer/clients/android/gradle/wrapper/gradle-wrapper.jar org.gradle.wrapper.GradleWrapperMain -p /Users/sphenicidition/.cache/gw138k-task-20261030/android-a07/jvm-check --no-daemon test
```

该 harness 是离线验证入口，不是新的生产输入。正常完整 Android SDK 环境仍用 `clients/android/README.md` 的原 Gradle 命令执行各模块测试、APK 和 lint。本轮未运行 Android AGP/Compose 编译、APK 构建或 lint；UI 时长的三行调用调整尚无 APK/真机验证。未发布新 APK，也未复用旧 0.2.10 的发布/硬件身份。

## 后续与回退

138K 还需在所属业务后端实现 0x43/session grant、真实 format2 录音和不混率对象生命周期；接最终 PCM 的实际 rate/连续性/流代次，完成 DDR DMA、格式1回归、双率真实 PCM、BLE 重连及完整硬件验收。显示 minor1 与全部消费者也需正式接入。源码支持和离线回归不能替代这些阶段。

当前 accepted profiles、板上 SRAM/Flash、25K 后端和实时 audio/event/top/PLL 均未改变。回退只需撤回机器记录列出的协议/Android/文档变化；没有本轮硬件部署需要撤销。

父级使用独立 `jvm-parent-check` 输出目录重新编译并实际运行全部 core 测试，11 秒通过：75 项中 73 通过、2 项按原物理前置条件跳过，0 failure/error；15 项交付源身份再次复核一致。独立日志、构建配置与全部 JUnit XML 哈希保存于机器记录。该复核同样不覆盖 APK/Compose、radio 或板卡。
