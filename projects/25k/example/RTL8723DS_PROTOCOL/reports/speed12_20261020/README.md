# 第十二轮：OPEN_EXTENDED / 最多8112字节PCM块

22B4已通过SRAM实板并完成Flash写入、校验和重载：同一镜像、三组LONG972/EXTENDED8112交替、每次32768字节PCM，中位吞吐 **7382.61→9842.78 B/s（+33.32%）**。三对均有收益，8112模式9842.78/9457.21/9890.84 B/s；972模式7382.61/7884.57/7356.49 B/s。电脑ATT MTU185/value182，每个完整8112块为46个B3通知。每份原始通知均离线重组并核验完整逻辑CRC、PCM CRC、连续偏移和参考PCM，成功READ/ACK_READ没有额外Response。

新APP协议链路完整192000 PCM下载24.0774秒，包含一次执行后DATA回执丢失重试、14720字节取消重开、29440字节断线续传与WAV保存；第一次INFO缺一片命令的检查发生在计时前。25个唯一块、21次ACK_READ，丢回执发生在22832字节，重试使用完全相同逻辑ID/字节。WAV192044字节逐字节匹配参考，SHA256 `2c492fa12189698f5abf3032cfd97aa322e8c4df5456b37f0c7bf56800d760ed`。同一APP0.2.8在上一版96FB/LONG972为29.2523秒，新22B4/EXTENDED8112为24.0774秒，耗时降低17.69%；两份WAV均精确匹配参考。两次检查含相同操作类型与固定取消/断线检查点，丢回执的偏移分别1944/22832，随分块变化，不宣称为空口或手机原生GATT实测。

## 实现

显式OPEN_EXTENDED0x3c沿用24字节OPEN_LONG响应，max_chunk为`min(8112,(value_limit-4)*64-48)`，窗口1、4字节对齐；value20/61/182/244时为976/3600/8112/8112。最多64片B3，DATA逻辑最多8160。只有有效成功0x3c授权扩展Transfer，默认Capability、Command/Response/Status保持512，旧3b仍972/1020，其他旧模式保持。APP仅明确UNSUPPORTED时每连接探测一次，按3c→3b→39→38→37→36→30回退。完整CRC、会话/请求/对象/范围检查，可靠落盘后确认、业务窗口1、H5窗口1均保留。详见[扩展协议](../../docs/EXTENDED_TRANSFER_EXTENSION.md)。

13位计数/地址、8192字节缓冲避免8192回绕，四个2048字节同步RAM维持一周期读延迟。当前Gowin工具会将重复宽/窄地址表达式错误合并：最初BF46只保留7位地址，实板PCM每128字节重复，CRC失败；拆RAM后的C297仍仅保留bank0和7位。明确13位操作数、从完整地址切片得到窄Response地址后，22B4综合网表四个bank均保留11位地址，独立核对后实板通过。前两候选未写Flash，失败证据保留，不计入收益样本。`crc_failure_diagnostic.json`首次复查错误写死tid=1导致超时；`crc_failure_diagnostic2.json`使用实际返回tid，成功复现128字节重复与CRC失败，后者才是定位依据。

缓存长READ/ACK_READ降级到较小模式后，如果原长度超过当前上限，返回0x8d、无DATA，不改变新游标、不覆盖原成功缓存；重开扩展模式仍可恢复原DATA。MTU每连接只允许交换一次，不能中途缩小后造成B3序号溢出。

22B4固件`builds/20261020_081332_946818/impl/pnr/ble_protocol.fs`，SHA256 `558e7897b46277bb8a5ff0f94fa61c6a94b76cdcde980aa7e03c26781cb64d3d`。50MHz约束下Fmax50.403MHz、setup/hold0/0、最小setup slack0.160ns；17060 LUT、9263 Register、11031/11520 CLS（96%）、37/56 BSRAM。30个固件输入逐字节匹配构建暂存副本。

APK0.2.8/versionCode11，9668978字节，SHA256 `ec4b1e1b561870e60b75488fc47ca6deba6aa8d4621954f44ec17ff2dda40ef0`；v2签名验证成功，与旧APK同调试证书。41项普通Android测试通过，2项实板用例默认跳过；Lint0错误/警告，完整录音实板用例另有物理执行记录。

Flash operation54写入校验及operation1重载后，身份读回22B4/70022020成功；首个32768字节复测速9539.60 B/s，PCM精确匹配参考。Flash后的完整录音/错误/重放、七种模式检查点续传、缓存降级和原协议复验见交付记录。物理断电未执行。

交付索引`reports/ready_build.json`已更新到22B4；最终JTAG读回22B4/70022020。Flash后完整192000字节录音及独立WAV、非法ACK_READ范围/CRC原子拒绝、精确READ/ACK_READ重放、手动停止、七种模式续传、缓存降级和原协议两连接均通过。

## 排除的其他路线

[原始额度读取](raw_acl_quota.json)：在SRAM诊断镜像4DFD中读取未封顶HCI LE Read Buffer Size0x2002，三份CRC16有效样本均为ACL27字节、实际8包，与生产有效8一致。没有额外额度，不能盲目扩大软件信用。诊断源码保存在diagnostic_sources，生产初始化器/核心/FFF1已恢复，Flash未加载诊断。

[964字节对齐](alignment_speed.json)：当前MTU理论ACL计数972→41、964→40，但三组交替中位8003.12→7773.04 B/s（−2.87%），未采用为APP策略。六份原始通知独立核查通过。ACL计数为分包推导，非空口抓包。

## 记录

| 项目 | 记录 |
|---|---|
| 未封顶真实ACL数量与诊断 | [raw_acl_quota.json](raw_acl_quota.json)、[diagnostic_build.json](diagnostic_build.json)、diagnostic_sources/ |
| 964对齐三组与通知核查 | [alignment_speed.json](alignment_speed.json)、[alignment_wire_audit.json](alignment_wire_audit.json) |
| 最初失败候选BF46/C297 | [extended_build.json](extended_build.json)、[banked_build.json](banked_build.json)、[crc_failure_diagnostic2.json](crc_failure_diagnostic2.json) |
| 地址修正候选构建/加载 | [address_build.json](address_build.json)、[address_program.log](address_program.log) |
| 最终固件输入/综合RAM核查 | [firmware_inputs.json](firmware_inputs.json)、[synthesis_memory_check.json](synthesis_memory_check.json) |
| 972/8112三组同镜像交替 | [extended_speed.json](extended_speed.json)、[extended_wire_audit.json](extended_wire_audit.json) |
| 完整APP及原始请求/通知核查 | [kotlin_extended_sram.json](kotlin_extended_sram.json)、[app_wire_audit.json](app_wire_audit.json) |
| 七种模式实板检查点续传 | [profile_resume_sram.json](profile_resume_sram.json) |
| 大块缓存降级及原成功项恢复 | [extended_replay_sram.json](extended_replay_sram.json) |
| MTU边界RTL与完整回归 | [extended_component_checks.json](extended_component_checks.json)、[banked_component_checks.json](banked_component_checks.json)、[simulation.json](simulation.json)，35组输入稳定回归 |
| Flash编程校验/重载/身份 | [flash.json](flash.json)、[final_device_identity.log](final_device_identity.log) |
| Flash速度/完整录音及错误/重放 | [speed_flash.json](speed_flash.json)、[recording_flash.json](recording_flash.json) |
| Flash续传/缓存降级/原控制协议 | [profile_resume_flash.json](profile_resume_flash.json)、[extended_replay_flash.json](extended_replay_flash.json)、[protocol_flash.json](protocol_flash.json) |
| 同一APP旧固件回退/完整WAV对照 | [kotlin_old_sram.json](kotlin_old_sram.json)、[complete_wav_check.json](complete_wav_check.json) |
| 最终交付身份/汇总 | [final_identity_check.json](final_identity_check.json)、[summary.json](summary.json) |
| APP构建/测试/Lint/签名 | [android_checks.json](android_checks.json)、[android_final.log](android_final.log)、[apk.json](apk.json)、[apk_signature.txt](apk_signature.txt) |

执行`python3 reports/speed12_20261020/audit_captures.py`复现最终原始通知、APP相同请求重试、回退和完整WAV核查。source_before/保存修改前文件；试验与交付源文件身份分别记录。首次完整回归因运行时修改RTL由输入身份检查拒绝，后续final_regression才是验收记录；首次Android失败为旧测试把976当非法通用PCM上限，更新为8116后全部通过，旧OPEN/LONG的协商上限仍严格校验。所有物理BLE客户端串行，编程均等待客户端退出。

手机原生Android GATT/权限/UI/后台及手机实际吞吐、当前新镜像物理断电尚未验收。音源仍内置1秒测试音，无实时麦克风或压缩。同镜像JTAG重载boot_id可能重复，板卡重启或重配置后先删除手机未完成下载。持续提速目标仍在进行。
