# 25K / Android 0.2.5 大 MTU 录音下载联调

2026-10-20，Android **0.2.5 / versionCode8**，包名 `cn.gowin.control`，最低Android8。服务器支持ATT MTU最高247，本轮电脑实际协商185，OPEN_BULK选择B3通知，每个460字节PCM块由32条通知减至3条。同一Flash固件三组交替测量、每次32768字节，中位数 **4361 → 5617 B/s（+28.8%）**。手机实际速率需安装后验收。

APP Kotlin完整192000字节下载、取消/重开、断线续传、一次命令片丢失和已执行响应丢失重试及WAV保存用时 **42.42秒**；相同APP连接旧OPEN_WIDE固件为57.22秒，耗时降低25.9%。两次均为460字节块、414次ACK_READ，在14720/29440字节处取消/断线，WAV与参考逐字节一致。这项完整流程比较使用不同固件；纯速率比较使用同一Flash固件。

## 手机操作

1. 安装 [0.2.5 APK](../artifacts/gowin-control-0.2.5-gw25k-bulk-debug.apk)，可覆盖相同调试签名的旧版并保留作品。
2. 板卡供电，扫描并选择 **GW25K-PROTO**。授予附近设备权限；Android8–11还需定位权限与定位服务。
3. 录音页最大时长保留 **0**，开始录音，等“可下载”后点击“下载 / 继续”。音源为FPGA内置的1秒双声道提示音。
4. 到作品页试听、导出或分享。普通断线可重连并继续下载；再次录音前清除设备录音，手机作品保留。
5. **板卡重启或重配置后，先删除手机未完成下载，再开始新录音。** 历史启动标识重复尚未修复，不能保证跨重启对象身份唯一。

APP在服务发现后请求MTU247；明确拒绝可继续ATT23，超时则关闭不确定的连接。每连接依次探测OPEN_BULK0x38、OPEN_COMPACT0x37、OPEN_WIDE0x36、原OPEN0x30，仅UNSUPPORTED0x80允许回退。BUSY、超时及损坏元数据不能降级；重试保持相同ID和逻辑字节。成功OPEN_BULK先验证24字节响应、value_limit和保留位，再配置Transfer重组器，B3仅对该Transfer启用。其余特征保留B1及20字节上限。

每块校验并可靠保存PCM和原子检查点后再确认，首块READ、后续ACK_READ、末块ACK后CLOSE。检查点4字节对齐，可在B1/256、B1/460、B2/460、B3/460间续传。格式见 [B3扩展](BULK_TRANSFER_EXTENSION.md)。

## 匹配版本

| 项目 | 结果 |
|---|---|
| APK | `artifacts/gowin-control-0.2.5-gw25k-bulk-debug.apk`，versionCode8 |
| APK SHA256 | `4ed6e088bb50e5c1f2dbda9780f3ad24d6e770c601901d38a4d7cfddfc0ed055` |
| 调试证书 SHA256 | `dc39e7120615a53f0bdf18629a361f0ebbf055d36c3b82f48adaf01cdae878ca` |
| 固件 | `builds/20261020_061852_003425/impl/pnr/ble_protocol.fs` |
| 固件 SHA256 | `4f9c56ecdf04959360953516883367a86147d3c30345c65c57afa5185bde59ba` |
| UserCode / Status | `0000079C` / `70022020` |
| Flash | cable1/channel0，2.5MHz，写入校验、重载和身份读回通过 |
| 时序 | 50MHz，Fmax50.037MHz，setup/hold违例0/0，余量较小 |
| 资源 | 16866 LUT，9229 Register，11013/11520 CLS（96%），34/56 BSRAM |
| 传输 | UART921600/8E1，ATT23..247，电脑实测185，单窗口，15ms请求 |
| 音频 | 48kHz、双声道、PCM16；48000帧、192000字节PCM、192044字节WAV |
| PCM CRC32 | `A54A47B0` |
| WAV SHA256 | `2c492fa12189698f5abf3032cfd97aa322e8c4df5456b37f0c7bf56800d760ed` |

## 验收与限制

[本轮报告](../reports/speed7_20261020/README.md)及[结构化汇总](../reports/speed7_20261020/summary.json)保存原始证据：21组RTL/主机回归、额外8项Python编解码测试、27项Android普通测试、Lint0；APP Kotlin真实BLE完整文件、旧固件每连接一次降级、相同请求重传、所有DATA PCM/CRC；四种协议检查点续传、B3/B2及原READ/ACK录音；最终Flash重载后的旧控制协议和交替测速。新增ACL桥接层按27字节物理包计数控制器信用，支持完整接收重组与事件穿插。

桥接器只转发GATT字节，APP Kotlin执行协议、持久化与WAV生成。手机原生权限、GATT、UI、后台及实际速度未测，本镜像未物理断电验收。音源仍为FPGA内置测试音频，未接入手机麦克风或外部实时输入，音频未压缩。历史同镜像JTAG重载boot_id重复问题仍保留，见[原始记录](../reports/speed3_20261020/boot_identity_limitation.json)。

高频连测曾触发既有8任务槽/60秒保留窗口BUSY；等待窗口到期后原READ/ACK复测通过，诊断保留。更改RTL后须重新验收时序，当前Fmax余量较小。

历史记录：[0.2.4紧凑分片](APP_INTEGRATION_0_2_4_COMPACT.md)、[0.2.3宽块](APP_INTEGRATION_0_2_3_WIDE.md)、[0.2.2 L2CAP](APP_INTEGRATION_0_2_2_L2CAP.md)、[0.2.2 ACK_READ](APP_INTEGRATION_0_2_2_ACK_READ.md)、[0.2.1 UART](APP_INTEGRATION_0_2_1_UART921600.md)。

## 重建

Android使用JDK17、SDK35、Build Tools35.0.0，在 `clients/android/local.properties` 配置SDK后执行：

```sh
sh gradlew :core:protocol:test :core:ble:testDebugUnitTest :core:data:testDebugUnitTest :app:assembleDebug :app:lintDebug
```

本例目录执行 `sh run_sim.sh`、`sh build.sh`；新构建使用 `reports/last_build.json`。`reports/ready_build.json` 固定指向已固化且无线实测的镜像，携带启动标识及验收范围限制；使用 `python3 program_flash.py --manifest reports/ready_build.json` 可重写此镜像。
