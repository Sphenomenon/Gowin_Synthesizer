# 内置音频录音与下载测试

本版把 25K 的真实 BLE 通道、录音对象生命周期、分块下载与 APP WAV 保存接通。音源明确为 **FPGA 内置测试音频**：48 kHz、双声道、PCM16，左声道 515.625 Hz、右声道 328.125 Hz，最多 1 秒。不是麦克风、外部输入或完整合成器录音。

## 手机操作

安装 `artifacts/gowin-control-0.2.1-gw25k-fast-debug.apk` 后：

1. 扫描并连接 **GW25K-PROTO**，授予附近设备权限；Android 8–11 还需定位权限和定位服务。
2. 进入“录音”，最大时长保留 **0**，表示录满设备的 1 秒容量；点击“开始录音”。可在录制期间提前停止。
3. 状态变为“可下载”后点击“下载 / 继续”。下载速度取决于实际连接；支持暂停、继续和断线重连后的检查点恢复。
4. 下载完并通过整段 CRC 后，在“作品”页试听、导出或分享。作品标注“FPGA 内置测试音频”。
5. 下载对象为不可变录音；录完另一段前需点击“清除设备录音”。清除不会删除手机已保存 WAV。

控制页显示内置音频测试说明，声音设置仍未接入。不要把“体验模拟设备”产生的模拟音频当成实板结果。

## 设备实现

- Capability：`flags=0x68`，短录音、下载、续传；256 字节 PCM 块、窗口 1、录音槽 1。没有参数、状态订阅、DDR 连续录音或非易失录音能力。
- PCM 源为 1024 个双声道帧的同步块 ROM，录制时按 48 kHz 时基循环读取并累计 CRC；提交完整帧后增加已录帧数。1 秒容量为 48000 帧、192000 字节。下载使用同一不可变源重建已封存的连续前缀，不分配 192 KB 录音 RAM。
- `audio/test_tone.mem` 和参考 `audio/test_tone_1s.wav` 由 `tools/generate_test_audio.py` 生成，来源与哈希见 `audio/manifest.json`。测试音频是本工程生成的正弦信号。
- 支持 HELLO、GET_STATUS、GET_OPERATION、REC_START/STOP/INFO/CLEAR、REC_OPEN/READ、TRANSFER_ACK、REC_CLOSE、TRANSFER_CANCEL。
- START/STOP 返回 ACCEPTED 和任务 ID；GET_OPERATION 查询任务是否实际开始/封存。保留 8 个任务，未完成不淘汰，完成后至少保留 60 秒；本测试版使用任务查询，未实现 0xE0 主动任务事件。状态订阅位为 0，APP 使用轮询。
- 达到 max_frames 或容量自动封存；STOP 提前结束并返回已提交的完整帧前缀及相应 CRC。GET_STATUS 仅录音分组有效（valid_mask=4）；声音、声部、电平和故障计数未标为有效。
- 录音对象 `(boot_id,recording_id)` 在断线后保留；录制继续。设备重启后应使对象失效；当前同镜像 JTAG 重载存在 boot_id 重复的已知限制，重启后须先删除手机未完成下载，详见 [本轮限制](ACK_READ_EXTENSION.md#已知启动标识限制)。需重新扫描建立新会话。单次启动内 recording_id、operation_id、transfer_id 不复用。
- Response 与 Transfer 分别按 UUID 通知，使用各自完整逻辑消息 CRC。最大 Transfer 消息为 304 字节、22 个特征分片；数据块 CRC 只覆盖 PCM。
- 下载窗口只有一块：匹配 ACK 才推进 offset，错误 ACK 返回 TRANSFER_CONFLICT。缓存内精确 READ 重试同时重发同一响应与同一数据；新 ID 的最近 ACK 重试不再次推进。
- CLEAR 在下载引用存在时返回 BUSY。CANCEL、断线或 30 秒无传输活动释放引用，保留录音；重连可从任一合法完整帧偏移 OPEN。
- Transfer CCCD 开启后请求 7.5–15 ms 的连接间隔、延迟 0、4 秒 supervision timeout；中心设备可拒绝，协议正确性不依赖请求被接受。Android 下载期间也会请求高优先级连接。

这是明确的内置音源测试配置，对 v1 的 source=0 采用内置 PCM 源。将来接实时合成器、麦克风或 DDR 需要替换音源/存储适配器并重新验证，不能据此宣称已实现外部实时录音。

## 主机与回归工具

`tools/recording_check.py` 使用独立 Python 编解码器验证录音、任务、错误、READ 重放、错误/重复 ACK、取消续传、断线续传、EOF/CLOSE/CLEAR、手动 STOP，并逐字节对比参考 WAV。

```sh
.venv/bin/python tools/recording_check.py --frames 4800 --output reports/recording_next.json
```

`tools/app_session_check.py` 可用 GATT 字节桥接运行 APP 原始 Kotlin ProtocolSession、PCM 数据解码、持久检查点和 WAV 封装；测试类为 `cn.gowin.control.data.RealRecordingTest`，Gradle 任务为 `:core:data:testDebugUnitTest`。设置 `GW25K_RECORDING_OUTPUT` 为本次独立输出目录。该测试完整下载 192000 字节，期间取消重开一次并断线重连一次；它验证 APP 业务代码和实板无线通道，不代表 Android 手机权限/UI/后台验收。

常规 Android 构建跳过需要无线桥接的测试；对应实板执行日志单独归档。构建命令与安装步骤也见 [APP 联调说明](APP_INTEGRATION.md)。

## 0.2.0 本板验收（历史）

已固化录音镜像 UserCode `7379`（SHA256 `674a142df4f5b4efe0ed0c5285fe83aae59e23e77c019573e5355a0e51cc1f3d`），50 MHz 时序通过。APP Kotlin 实板下载完整 1 秒对象，含取消与断线检查点恢复，生成的 WAV 与本目录参考文件逐字节相同；PCM CRC32 `A54A47B0`。完整测试含构建、握手、重连约 375 秒，手机耗时取决于实际链路。

Flash 写入校验和 Reprogram 重载通过；重载后旧对象失效，新录音、下载、取消/断线恢复与手动 STOP 再次通过。该次复验下载 100 ms 对象（4800 帧、19200 字节），完整 1 秒对象在写入相同镜像前验证。未实际切断板卡电源，也没有宣称 Android 真机验收完成。

[最终汇总](../reports/recording_20261020/summary.json)包含 APK/位流/音频哈希与全部证据。控制器 ACL 额度按 LE Read Buffer Size 结果使用，最多 8 个，并按当前连接的完成包数回收；相较单额度减少下载等待。相应额度、外来句柄忽略与饱和回收均有仿真覆盖。

## 0.2.1 加速版

当前加速镜像 UserCode `4096`，SHA256 `51b2e4a8d955ccb3e6901cb40d76cc6bc010117bf139557714d86dfe3fc3c07b`，50 MHz、Fmax 51.174 MHz、setup/hold 0/0。通过可选 GATT 无响应写入减少命令往返，业务 CRC/重试/单块窗口保持不变；旧方式兼容，APP 可回退。短测约 2.12 倍，完整 192000 字节下载含取消与重连约 196 秒，WAV 与参考逐字节相同。完整方法和证据见 [提速说明](SPEED_OPTIMIZATION.md) 与 [本轮汇总](../reports/speed_20261020/summary.json)。
