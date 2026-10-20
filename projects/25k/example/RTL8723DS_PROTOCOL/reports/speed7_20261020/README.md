# 第七轮：大 MTU / B3 与 ACL 分包

同一最终Flash固件交替测量三组，每次32768字节、460字节块、无响应写入及ACK_READ：B2中位数 **4361.42 → B3 5617.01 B/s（+28.79%）**。B3三次为5780.53/5617.01/5460.91，B2为4361.42/4317.63/4422.62 B/s。测量包含业务下载和最终ACK，不含扫描、连接、录音、编译及清除。电脑实际ATT MTU185/value182，满460字节块通知32→3条。数据均逐块匹配参考PCM/CRC；本结果不代表手机速率。

完整APP Kotlin在新固件下载192000字节用时42.4226秒，同一APP在旧OPEN_WIDE固件上为57.2202秒，耗时降低25.86%。均含取消/重开、14720/29440字节边界取消/断线续传、命令片丢失及已执行ACK_READ响应丢失后同请求重试、可靠检查点和WAV保存。两份192044字节WAV逐字节等于参考，SHA256 `2c492fa12189698f5abf3032cfd97aa322e8c4df5456b37f0c7bf56800d760ed`。完整流程比较使用旧宽块固件，纯速率比较使用同一新Flash固件，二者范围不同。

## 实现

- 新增 `adaptations/bt_acl_bridge.v`：按27字节ACL data拆分、逐物理包信用、匹配handle完成事件及饱和计数；接收完整ACL/L2CAP重组、同步RAM、mailbox背压、HCI事件穿插、无效片/超时/断线丢弃。初始化验证LE buffer长度与数量。
- GATT支持MTU23..247、每连接一次协商、重连回到23。新增B3同步RAM，最大508字节DATA按协商通知长度发送。原B1/B2长度与格式保持。
- OPEN_BULK0x38返回24字节payload，含value_limit；460字节PCM块、逻辑512字节上限、CRC和单窗口保留。详见[B3协议](../../docs/BULK_TRANSFER_EXTENSION.md)。
- APP0.2.5请求MTU247，严格验证OPEN元数据，设置重组器后才发布成功。0x38→0x37→0x36→0x30仅UNSUPPORTED允许回退，BUSY/超时/坏元数据不降级，相同请求字节重试。

## 交付与实测

[APK0.2.5](../../artifacts/gowin-control-0.2.5-gw25k-bulk-debug.apk)，versionCode8，原调试签名。SHA256 `4ed6e088bb50e5c1f2dbda9780f3ad24d6e770c601901d38a4d7cfddfc0ed055`。完整版本、签名及源码身份见 [apk.json](apk.json)、[签名](apk_signature.txt)、[Android源码快照](android_sources.json)。

最终固件 `builds/20261020_061852_003425/impl/pnr/ble_protocol.fs`，SHA256 `4f9c56ecdf04959360953516883367a86147d3c30345c65c57afa5185bde59ba`。Flash写入校验、重载及身份读回通过：UserCode079C、Status70022020。[最终Flash报告](flash.json)。曾临时写旧OPEN_WIDE固件做兼容测试，随后已恢复本镜像，恢复后协议及测速均通过。

50MHz约束，Fmax50.037MHz、setup/hold0/0，时序余量较小。16866 LUT、9229寄存器、11013/11520 CLS（96%）、34/56 BSRAM。后续RTL修改必须重新构建并验收时序。UART921600/8E1、请求间隔15ms、H5窗口1及业务窗口1保持。

| 验收 | 证据 |
|---|---|
| 21组RTL/主机回归 | [simulation.json](simulation.json)，含完整30147字节UART补丁、ACL桥接、MTU23/64/247、录音重放与拒绝 |
| Python额外8项编解码回归 | [codec_final.log](codec_final.log)，B3多种limit及1..512字节 |
| Android27项普通测试、Lint0 | [android_checks.json](android_checks.json)、[最终构建日志](android_qualified.log)、[JUnit](android_junit) |
| 新APP/大MTU固件完整音频 | [kotlin_bulk_sram2.json](kotlin_bulk_sram2.json) |
| 新APP/旧宽块固件回退 | [kotlin_old_firmware_current_app.json](kotlin_old_firmware_current_app.json) |
| 原始APP请求/通知独立核查 | [app_wire_check.json](app_wire_check.json)，两连接中每连接一次回退、920偏移同请求重试、所有DATA/CRC和续传边界 |
| WAV精确比较与完整耗时 | [complete_wav_check.json](complete_wav_check.json) |
| 同Flash三组交替测速 | [alternating_speed.json](alternating_speed.json) |
| 十份测速抓包独立核查 | [notification_wire_check.json](notification_wire_check.json)，片数、长度、PCM与CRC |
| Flash大MTU录音/原子错误拒绝/续传 | [recording_flash.json](recording_flash.json) |
| Flash紧凑B2兼容 | [recording_compact_flash.json](recording_compact_flash.json) |
| Flash原READ/ACK兼容 | [recording_legacy_flash.json](recording_legacy_flash.json) |
| 四种下载格式跨模式续传 | [profile_resume_flash.json](profile_resume_flash.json)，30→38→37→36→38→30 |
| 最终恢复Flash后的旧控制协议 | [protocol_restored_flash.json](protocol_restored_flash.json) |
| RTL构建输入身份 | [firmware_inputs.json](firmware_inputs.json)，当前30个输入匹配实际编译副本 |
| 交付汇总 | [summary.json](summary.json)，[源码/产物最终身份](final_identity_check.json) |

运行 `python3 reports/speed7_20261020/audit_captures.py` 可离线重现APP原始报文、全部测速通知和WAV检查。`source_before/`、`changes.patch`、`source_sha256.json`记录本轮改动及来源；未修改vendor包。

## 保留诊断与验收边界

`kotlin_bulk_sram.json`首次失败源于测试仍限制旧256字节块；修正测试上限后完整复测 `kotlin_bulk_sram2.json` 通过。`legacy_task_retention_diagnostic.json`为连续测试触发既有8任务槽/60秒保留BUSY，窗口到期后的原READ/ACK复测通过。诊断原文保留。

手机原生Android权限、GATT、UI、后台与实际速度未测；本镜像尚未物理断电验收。旧同镜像JTAG重载boot_id重复仍未修复，见[原始限制](../speed3_20261020/boot_identity_limitation.json)。**板卡重启或重配置后，先删除手机未完成下载，再开始新录音。** 音源为内置测试音频，尚无外部实时录音输入，未压缩音频。持续提速目标仍在进行。
