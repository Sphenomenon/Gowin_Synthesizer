# 第十一轮：OPEN_LONG / 972字节块，已固化

同一最终96FB固件、三组DIRECT460/LONG972交替、每次32768字节PCM，中位吞吐 **6407.61 → 8035.39 B/s（+25.40%）**。新模式7916.34/8035.39/8065.22，旧模式6407.61/6368.64/6445.23 B/s。Flash写入校验、重载及身份读回96FB/70022020成功，重载后单次 **7746.31 B/s**。数据逐块匹配参考PCM与CRC，电脑ATT MTU185/value182；不代表手机速度。

同一APP0.2.7在上一版EC9B和最终96FB上，完整192000字节PCM下载、WAV保存用时 **34.6310 → 31.2447秒（耗时 -9.78%）**。计时从首个OPEN成功到WAV保存，包含一次执行后DATA回执丢失重试、14720字节取消重开、29440字节断线续传。初始INFO命令片丢失测试在计时之前。新模式200个唯一块、196次ACK_READ，旧模式418块、414次ACK_READ；丢弃的回执以完全相同逻辑请求ID和字节重试。两份192044字节WAV逐字节等于参考，SHA256 `2c492fa12189698f5abf3032cfd97aa322e8c4df5456b37f0c7bf56800d760ed`。包含重连等操作的完整流程与纯传输测试的收益比例不同，分别记录。

## 实现与交付

显式OPEN_LONG0x3b协商972字节PCM、1020字节DATA逻辑上限、B3和DATA成功回执。计数/地址扩大10位、缓冲1024字节，避免1024回绕。MTU23时最长64片/序号63，MTU185时为6片。只有成功0x3b的Transfer/B3接收扩展长度，其他消息及Command/Response/Status继续512；Command仍原B1三片，没有采用第十轮B4方案。旧OPEN/WIDE/COMPACT/BULK/DIRECT保持原上限。完整逻辑/PCM CRC、会话/对象/范围检查、单窗口、精确重放和可靠保存后ACK保持。详见[长块协议](../../docs/LONG_TRANSFER_EXTENSION.md)。

缓存长READ在切回旧模式后重试会返回0x8d且无DATA，不移动新传输偏移，也不覆盖原缓存成功项；重新打开长模式后原请求仍可恢复相同DATA。新状态错误由缓存重放等待状态正常传回。该边界有修复前失败用例、最终RTL及实板证明，避免把长DATA送入旧B1/512路径。

[APK0.2.7](../../artifacts/gowin-control-0.2.7-gw25k-long-debug.apk)，versionCode10，9668978字节，SHA256 `085a6c22b65c026a9eb83d0dd6a4183b24fd4d9c297d3fcdaa7ab94ab9b4970d`。签名验证通过，与旧版相同调试证书，可覆盖安装。[APP操作](../../docs/APP_INTEGRATION.md)，旧版说明归档为[0.2.6](../../docs/APP_INTEGRATION_0_2_6_DIRECT.md)。新APP每连接仅一次0x3b UNSUPPORTED后回退0x39，错误或超时不能降级。

固件 `builds/20261020_074629_026662/impl/pnr/ble_protocol.fs`，SHA256 `155ac0f71ad9ae3ee3de265e682d7477c39ca486d551c462bbc5beb3d06b6ea2`；[ready_build.json](../ready_build.json)已更新。50MHz约束下Fmax50.506MHz、setup/hold0/0，最小setup slack0.201ns。17080 LUT、9237 Register、11034/11520 CLS（96%）、34/56 BSRAM。UART921600/8E1、H5窗口1、业务窗口1、15ms参数请求、27字节物理ACL保持。

## 诊断证据与试验阶段

[SRAM诊断](transport_profile.json)读取真实LE buffer长度 **27字节**；当前实现使用 **8个ACL额度**。**额度数量经过初始化器8封顶，未采集未封顶原始返回值，因此不能据此断言控制器原始数量恰好为8。** 一次32768字节、约5.07秒传输，H5确认等待约0.218秒，额度等待约1.860秒；这是50MHz计数差值，不是空口分析，也不代表全部等待分类。诊断值带独立CRC16校验；H5、ACL桥、原FFF1和诊断FFF1值测试通过。诊断镜像D513仅加载SRAM，未固化；[诊断输入](diagnostic_inputs.json)、[诊断源码](diagnostic_sources)归档，生产源码恢复原FFF1 BTST格式。

最初长块候选1E0D已证明约22.0%收益，见[初候选构建](candidate_build_initial.json)与[探索测速](exploratory_speed/alternating_speed.json)。补齐跨模式重放边界后重新构建最终96FB，重做三组交替、完整APP新模式和Flash复验；本文采用最终镜像结果。`kotlin_long_sram.json`为初候选28.35秒记录，不能代替最终31.24秒的验收值。两次新模式用例均只有一次预设DATA丢失重试，没有额外逻辑请求重试；不筛选较快样本。

`profile_replay_before_fix.log`保留先复现的跨模式错误；[最终仿真](simulation.json)覆盖修复。`android_initial.log`中的失败为原测试仍以464作为非法最大块能力；新扩展允许更高显式上限，将非法测试改为976后重新运行全部Android测试通过，默认256及旧OPEN460校验仍保留。

## 验收记录

| 项目 | 记录 |
|---|---|
| 最终25组RTL/主机回归 | [simulation.json](simulation.json)，含长块、跨模式缓存保护、完整补丁与全部旧模式 |
| 额外MTU23/64/185/247长DATA构建 | [long_component_checks.json](long_component_checks.json)，覆盖1020字节与序号63 |
| Android36项普通测试、Lint0 | [android_checks.json](android_checks.json)、[JUnit](android_junit)、[构建](android_final.log) |
| 最终APP长块完整WAV | [kotlin_long_sram_final.json](kotlin_long_sram_final.json)、[文件](kotlin_long_final_files) |
| 新APP/EC9B回退及完整WAV | [kotlin_old_firmware.json](kotlin_old_firmware.json)、[文件](kotlin_old_files) |
| 全部APP原始请求/通知核查 | [app_wire_check.json](app_wire_check.json)，CRC/PCM、相同重试、回退、固定检查点 |
| 完整WAV、耗时及计时范围 | [complete_wav_check.json](complete_wav_check.json) |
| 最终同固件三组交替 | [alternating_speed.json](alternating_speed.json) |
| 七份测速通知核查 | [notification_wire_check.json](notification_wire_check.json)，新34块、旧72块，无独立成功READ Response |
| Flash编程、校验、重载、身份 | [flash.json](flash.json) |
| Flash速度 | [speed_flash.json](speed_flash.json) |
| Flash录音、错误原子拒绝及重放 | [recording_flash.json](recording_flash.json) |
| 六种格式跨检查点续传 | [profile_resume_flash.json](profile_resume_flash.json)，30→3b→39→38→37→36→3b→30 |
| Flash跨格式缓存与游标保护 | [profile_replay_flash.json](profile_replay_flash.json)，错误后原缓存成功项保留 |
| Flash原控制协议及重连 | [protocol_flash.json](protocol_flash.json) |
| 最终编译30输入与APP42输入 | [firmware_inputs.json](firmware_inputs.json)、[android_sources.json](android_sources.json) |
| APK签名和版本 | [apk.json](apk.json)、[apk_signature.txt](apk_signature.txt) |
| 交付身份与汇总 | [final_identity_check.json](final_identity_check.json)、[summary.json](summary.json) |

执行 `python3 reports/speed11_20261020/audit_captures.py` 可离线复现原始通知、逻辑/PCM CRC、完整WAV、精确重试与回退核查。`source_before/`、`changes.patch`、`source_sha256.json`保存本轮改动和身份，vendor未改。所有物理BLE操作串行，FPGA编程均在BLE客户端退出后执行。

## 限制与后续

手机原生Android权限/GATT/UI/后台、实际速率及当前镜像物理断电仍待实测；Flash校验/重载已测。既有同镜像JTAG重载boot_id重复问题未解决。**板卡重启或重配置后先删除手机未完成下载，再开始新录音。** 音源仍内置测试音频，未压缩，没有接入外部实时录音。资源占用96%，后续RTL需重新验收时序。

持续提速目标仍在进行。下一条有证据支持的检查是采集控制器未封顶的原始ACL packet count；若高于8，再验证按实际数量使用额度，保持handle匹配、逐物理包计数和饱和归还。现有诊断不支持盲目提高额度，也不支持把H5窗口作为唯一主要瓶颈。
