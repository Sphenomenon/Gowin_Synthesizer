# Android 首版验证记录

日期：2026-10-20（Asia/Shanghai）。版本：0.1.0 / versionCode 1，包名 `cn.gowin.control`。本记录验证安卓代码、协议模拟链路和文件完整性；实际工作站业务固件尚未提供，未完成实物蓝牙验收。

## 构建与自动检查

环境：JDK 17.0.20.1、Gradle 8.10.2、AGP 8.7.3、Kotlin 2.0.21、Android Platform 35、Build Tools 35.0.0。最低 API 26，target API 35。

```sh
./gradlew :core:protocol:test :core:data:testDebugUnitTest :app:assembleDebug :app:lintDebug
```

结果：`BUILD SUCCESSFUL`。共 8 项测试，0 失败、0 错误、0 跳过。

| 测试类 | 数量 | 覆盖内容 |
|---|---:|---|
| WireTest | 5 | 报文规范向量、CRC、分片边界/重复/跳片/超时、无符号标识和状态布局 |
| RecordingFilesTest | 2 | 检查点恢复、尾部截断与损坏前缀处理、WAV 头和数据 CRC |
| DemoProtocolTest | 1 | 协议模拟外设握手、参数 revision 冲突、数据先于响应、下载及重复 ACK |

Lint：0 errors、6 warnings；报告含 5 条固定依赖的新版提示与 1 条资源目录版本限定提示。报告位于 `app/build/reports/lint-results-debug.html`，测试 XML 位于各模块 `build/test-results/`。未设置忽略错误或禁用检查。

## 最终 APK 模拟器验证

设备：Android Emulator `Medium_Phone_API_37.0`，Android 17 / API 37，1080 × 2400，使用只读临时实例。安装最终调试 APK 后执行：

1. 冷启动并进入明确标注的模拟工作站，无需蓝牙权限。
2. 将合成模式切至 B，确认选中状态和状态同步。
3. 开始录音，观察录音进度；达到模拟设备 10 秒容量后转为可下载。此前也验证过手动停止后下载。
4. 下载至 100%，接收、已保存、已确认偏移均为 1,920,000 字节。
5. 删除该对象的临时下载文件并重新下载，在确认偏移 275,200 字节时暂停；点击继续后确认偏移前进至 407,808 字节，最终完整下载并通过 CRC。
6. 作品页出现 10 秒模拟 WAV；旧版 APK 保存的 3 秒作品在更新安装后仍保留。
7. 点击试听，系统媒体诊断记录到本应用音频播放。模拟器关闭音频输出，因此未做听感验收。
8. 系统 SAF 导出和分享选择器均正常打开；导出文件的逐字节一致性单独核验。分享仅验证选择器，没有向外部联系人发送文件。
9. 崩溃日志缓冲区为空；对控制、下载、暂停和作品截图进行了视觉检查。

界面记录：[控制](screenshots/control.png)、[下载](screenshots/download.png)、[暂停](screenshots/paused.png)、[作品](screenshots/library.png)。截图中的传输速度来自进程内模拟器，不代表 BLE 射频吞吐量。

## 独立文件校验

从应用私有目录读取最终 WAV，用 Python 标准库 `wave` / `zlib.crc32` 独立解析，与持久化检查点对照：

| 字段 | 结果 |
|---|---:|
| 采样率 / 声道 / 位深 | 48,000 Hz / 2 / 16 bit |
| 音频帧 | 480,000 |
| PCM 数据长度 | 1,920,000 字节 |
| WAV 总长度 | 1,920,044 字节 |
| PCM CRC32（十进制） | 3,522,820,426 |
| 检查点 offset / bytes | 均为 1,920,000 |
| 检查点 prefixCrc / 对象 crc | 均为 3,522,820,426 |

SAF 导出至系统 Downloads 后，与应用私有 WAV 逐字节相同，长度 1,920,044 字节；文件 SHA256 为 `8e1038f3d0c30860a6c1e4877461df26559bd00acfca32480967d78cecb22325`。

## 安装包

调试安装包：`artifacts/gowin-control-0.1.0-debug.apk`（构建产物已由 Git 忽略）。

SHA256：

```text
d5f4b5b5505c070c8ef31236fa77751f5f079104344d60d7c3b7fea93198b958
```

这是联调用调试签名包；尚未配置正式发布签名、应用商店发布和发行合规验收。

## 待实物验收

- 设备端需实现 `9b6d0000-4c2a-4f87-9a31-138000000001` 及协议 v1.0 业务特征。当前 FFF0/FFF1 BTST 测试服务不能替代该契约。
- 安卓真机扫描权限、CCCD 通知、实际射频连接、断连退避恢复、锁屏/后台/厂商省电、API 26–30 与不同手机的兼容性尚未验证。
- 真正 DDR 录音、设备重启后的录音失效、长文件、吞吐和持久化性能需在工作站上验收。进程终止恢复目前有文件层单元测试，尚无真实手机强杀恢复验收。
- 首版采用 v1.0 窗口 1、256 字节 PCM 块；高速窗口、压缩、Wi-Fi/USB 通道仍需设备契约与后续实现。
