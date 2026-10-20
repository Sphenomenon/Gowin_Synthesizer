# 第十轮：单次读取命令无吞吐收益，未采用

本轮完成 OPEN_FAST0x3a/B4 实验，**没有发布新固件或APP**。同一候选固件、每次32768字节PCM、460字节块、无响应写入及ACK_READ，按DIRECT/FAST顺序交替三组：原模式中位数 **6521.58 → 候选6352.40 B/s（-2.59%）**。完整样本见[alternating_speed.json](alternating_speed.json)。这组结果不支持继续部署候选；保留上一轮EC9B/APP0.2.6。

| 配对 | 原DIRECT B/s | 候选FAST B/s |
|---|---:|---:|
| 1 | 6368.64 | 6424.96 |
| 2 | 6620.69 | 6352.40 |
| 3 | 6521.58 | 6332.21 |

候选前EC9B Flash测得6171.96 B/s；候选测试后恢复EC9B SRAM，重新连接两次、校验控制协议及重传/错误处理，再次下载测得 **6332.57 B/s**，PCM与参考逐字节相同。前后EC9B结果用于状态复核，不代替同候选交替对比。最终[ready_build.json](../ready_build.json)及Flash始终保持第九轮版本，SRAM身份读回EC9B/70022020，见[恢复编程记录](restore_baseline_sram.log)、[恢复协议](protocol_restored.json)、[恢复测速](speed_restored.json)。

## 试验内容与观察

候选使用显式OPEN_FAST协商B3/DATA成功回执和B4完整READ/ACK_READ命令。原逻辑字节、请求ID、nonce、CRC32、单窗口及持久化顺序保持；36/40字节ATT值分别要求MTU39/43，MTU不足继续B1。旧模式不接收B4，仅明确UNSUPPORTED允许APP逐级回退。源码及未发布协议保存在[fast_command_sources](fast_command_sources)，[changes.patch](changes.patch)可查看本轮完整试验差异。生产源码已恢复，不能将归档中的0x3a视为当前设备支持项。

每72块下载的写入总数确实从224降到80（读取部分216→72，另有最终ACK、CANCEL、CLEAR）。但主机写入API累计耗时中位数仅从0.02347秒降到0.01414秒，约节省9.3毫秒；完整测量仍约5.0–5.2秒。收到的通知间隔约15毫秒，减少主机写入调用未带来持续吞吐提升。该结果来自GATT回调，不是外部空口分析，不能据此认定唯一瓶颈。后续应测量控制器ACL额度/H5可靠窗口与连接事件中的发送调度；本轮没有改变这些机制，也没有测得控制器实际最大ACL长度。

## 验证及归档

- [25组RTL/主机仿真](simulation.json)：24组完整回归，加独立实际GATT/命令端点B4门控测试；覆盖协商、MTU39/43、READ/ACK_READ、非法标志、坏CRC、重放及ACK原子拒绝。完整回归启动后才增加独立GATT用例，独立用例日志为[fast_gatt.log](fast_gatt.log)。
- [Android36项普通测试、Lint0](android_checks.json)，包含4项B4测试；[构建日志](android_final.log)。未运行候选APP完整实板录音测试、旧固件APP实板回退及手机原生GATT，未发布0.2.7。候选APK仅作实验归档，见[experimental_apk.json](experimental_apk.json)。
- [八份原始通知独立核查](notification_wire_check.json)：候选六份及前后EC9B两份，均32768字节/72块，逐块偏移、长度、PCM和CRC匹配，无独立成功读取Response。运行 `python3 reports/speed10_20261020/audit_captures.py` 可离线复现。写入数量来自实际调用记录，未进行外部空口抓包。
- [候选构建](candidate_build.json)仅加载SRAM，SHA256 `7ec83eb91b7f92087b879279bb5d7c6eb9999574212f672412a7f9eac7357b91`，UserCode4F15；Fmax50.312MHz、setup/hold0/0、最小setup slack0.124ns，17409 LUT、9393 Register、10975/11520 CLS、34/56 BSRAM。构建通过不代表吞吐资格通过。
- [30个候选实际编译输入](firmware_inputs.json)、[生产固件30输入恢复核查](restored_firmware_inputs.json)、[生产APP41输入恢复核查](restored_android_sources.json)、[恢复清单](restoration.json)、[汇总](summary.json)。`source_before/`保留原始快照。根README仅追加本轮试验索引；vendor未改。

当前可安装版本仍为[0.2.6 APK](../../artifacts/gowin-control-0.2.6-gw25k-direct-debug.apk)，已验收提速结果及完整WAV流程沿用[第九轮报告](../speed9_20261020/README.md)。手机速率和原生GATT/UI/后台仍待用户实测。当前镜像物理断电验收、本已知boot_id重复限制均未新增解决；板卡重启或重配置后先删除手机未完成下载。音源仍内置测试音频，未压缩。持续提速目标保持进行中。
