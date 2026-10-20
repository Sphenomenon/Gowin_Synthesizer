# 第九轮：OPEN_DIRECT / DATA成功回执

同一候选固件三组交替测量、每次32768字节PCM：原OPEN_BULK中位数 **5436.30 → OPEN_DIRECT 6407.23 B/s（+17.86%）**。三次新模式6444.24/6278.38/6407.23，原模式5410.54/5436.30/5588.89 B/s。最终Flash重载后单次 **6278.15 B/s**。所有数据逐块匹配参考PCM和CRC，电脑实际ATT MTU185/value182。以上为电脑BLE结果，手机实际速率待测。

相同APP0.2.6在上一版B3固件和新模式的完整192000字节下载用时 **42.8643 → 35.3344秒（耗时 -17.57%）**。均为460字节块、414次ACK_READ、14720/29440字节处取消/断线续传，执行后回执丢失再以相同请求重试。两份192044字节WAV逐字节等于参考，SHA256 `2c492fa12189698f5abf3032cfd97aa322e8c4df5456b37f0c7bf56800d760ed`。计时从首个OPEN成功到WAV保存，包含一次执行后回执丢失重试；初始INFO命令片丢失检查在计时之前。完整流程比较使用两个固件，纯速率比较使用同一固件交替选择0x38/0x39。

## 实现与交付

OPEN_DIRECT0x39显式选择B3，同时以通过全部校验的DATA作为成功READ/ACK_READ回执，省略独立成功Response的三条通知。错误、其他命令、原OPEN/WIDE/COMPACT/BULK继续原Response。设备保留原成功响应缓存及精确重放；APP验证逻辑/PCM CRC、会话/请求ID、对象、偏移/长度与范围后生成等价的本地读取结果。先可靠保存PCM/检查点再ACK的顺序、单窗口和所有CRC保持。协议详见[DATA回执扩展](../../docs/DIRECT_TRANSFER_EXTENSION.md)。

[APK0.2.6](../../artifacts/gowin-control-0.2.6-gw25k-direct-debug.apk)，versionCode9，9703423字节，SHA256 `3b6bc5b6978a9df6e25d6d0d0eb6b443b9a87b6d01557e369843cd3910185250`。原调试证书SHA256 `dc39e7120615a53f0bdf18629a361f0ebbf055d36c3b82f48adaf01cdae878ca`，签名验证通过，可覆盖旧联调版。安装步骤见[APP说明](../../docs/APP_INTEGRATION.md)。

最终固件 `builds/20261020_070638_494400/impl/pnr/ble_protocol.fs`，SHA256 `c772c4b9783ccba175a0a8ec231cd4465019cc4415b17f3398409c891ad9b6f6`。Flash写入、校验、重载及身份读回通过，UserCodeEC9B、Status70022020。旧固件仅临时载入SRAM做APP回退测试；最终Flash已更新为本候选，且无线复验通过。

50MHz约束下Fmax50.016MHz、setup/hold0/0，最小setup slack仅0.006ns。17015 LUT、9230寄存器、11020/11520 CLS（96%）、34/56 BSRAM。UART921600/8E1、ATT最高247、逻辑512、最大PCM460、15ms请求、业务与H5窗口1保持。[第八轮](../speed8_20261020/README.md)无明显收益的2Mbps和456字节块均未采用。

## 证据

| 验收 | 记录 |
|---|---|
| 23组RTL/主机回归 | [simulation.json](simulation.json)，含完整补丁、direct OPEN/重放/ACK原子拒绝、仅省略显式成功读取响应及全部旧模式 |
| Android32项普通测试、Lint0 | [android_checks.json](android_checks.json)、[JUnit](android_junit)、[最终构建](android_qualified.log) |
| APP新模式完整WAV | [kotlin_direct_sram.json](kotlin_direct_sram.json)，完整DATA回执被测试桥丢弃后，相同请求恢复 |
| 新APP/上一版B3固件 | [kotlin_old_firmware.json](kotlin_old_firmware.json)，每连接仅一次0x39 UNSUPPORTED探测，然后0x38；执行后原Response丢失重试 |
| APP原始请求与通知独立核查 | [app_wire_check.json](app_wire_check.json)，全部对象/PCM/CRC、五个边界字段、920偏移精确重试、成功Response仅在direct省略 |
| 完整WAV与耗时 | [complete_wav_check.json](complete_wav_check.json)，两份逐字节匹配参考 |
| 同固件交替测速 | [alternating_speed.json](alternating_speed.json) |
| 七份测速通知独立核查 | [notification_wire_check.json](notification_wire_check.json)，每份32768字节/72块；direct成功读取Response为0，原模式72个 |
| 最终Flash编程 | [flash.json](flash.json)，实际program/verify/reload及身份 |
| Flash速度 | [speed_flash.json](speed_flash.json) |
| Flash录音及错误恢复 | [recording_flash.json](recording_flash.json)，CRC/范围错误原子拒绝、原请求重放、STOP/CLOSE/CLEAR、断线恢复 |
| 五种模式跨检查点续传 | [profile_resume_flash.json](profile_resume_flash.json)，30→39→38→37→36→39→30 |
| Flash旧控制协议与重连 | [protocol_flash.json](protocol_flash.json) |
| 固件30个实际编译输入 | [firmware_inputs.json](firmware_inputs.json) |
| APP源码与签名 | [android_sources.json](android_sources.json)、[apk_signature.txt](apk_signature.txt)、[apk.json](apk.json) |
| 最终交付身份与范围 | [summary.json](summary.json)、[final_identity_check.json](final_identity_check.json) |

运行 `python3 reports/speed9_20261020/audit_captures.py` 可离线重现原始通知和完整WAV核查。电脑工具的本地等价读取结果以 `response_synthesized_from_data` 标记，不能当作真实收到独立Response；实际省略由原始GATT通知核查证明。`source_before/`、`changes.patch`与`source_sha256.json`保存本轮改动及身份，vendor包未改。

## 验收边界

手机原生Android权限、GATT、UI、后台与实际速率未测，本镜像尚未物理断电验收。时序余量极小，后续RTL修改必须重新验收时序。既有同镜像JTAG重载boot_id重复问题未修复，见[历史限制](../speed3_20261020/boot_identity_limitation.json)。**板卡重启或重配置后，先删除手机未完成下载，再开始新录音。** 音源仍为内置测试音频，无外部实时输入，音频未压缩。持续提速目标仍在进行。
