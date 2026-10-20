# 第十八轮：通用二阶无损下载与 APP 0.2.10

本轮已将二阶预测/Rice k5 接入 FPGA 和生产 APP 核心，通过实板比较后固化 A25D，并发布配套 [0.2.10 APK](../../artifacts/gowin-control-0.2.10-gw25k-second-debug.apk)。`reports/ready_build.json` 已切换到该镜像，前版 C678 索引保存在 [previous_ready_build.json](previous_ready_build.json)。持续优化目标仍待后续推进；本报告只确认这一版的交付与测量结果。

## 实测结果

同一 A25D 镜像、相同 8112 字节 PCM 块与 32768 字节下载，在一阶与二阶模式间交替三组，均与参考 PCM 完全一致。KB/s 按 1000 B/s 计算，吞吐分子为解码后的 PCM 字节，不是无线净载荷速率。

| 组次 | 一阶/k9 B/s | 二阶/k5 B/s |
|---|---:|---:|
| 1 | 14105.45 | 22091.52 |
| 2 | 14106.46 | 21874.26 |
| 3 | 14010.09 | 22092.53 |
| 中位数 | 14105.45 | 22091.52 |

中位吞吐 **14.11→22.09 KB/s，提升56.6%**，见 [paired_speed.json](paired_speed.json)。Flash 重载后另测 **20847.58 B/s**，见 [speed_flash.json](speed_flash.json)。压缩收益取决于音频内容；噪声可回退原始 PCM，不能把此测试音的提升外推到全部音源。

同一套生产 APP Kotlin 核心分别连接旧 C678 与新 A25D，完整 192000 字节 PCM 流程 **18.6473→14.1459 秒，耗时减少24.1%**；Flash 固化后复验 **13.7160 秒**。流程包含故意丢失一片命令、offset22832 的执行后 DATA 回执丢失及精确重试、offset14720 取消后重开、offset29440 断线重连、可靠检查点和 WAV 保存。三份 192044 字节 WAV 均与参考逐字节一致。

证据：[完整WAV核验](complete_wav_check.json)、[旧版APP连接记录](kotlin_old_sram.json)、[新版SRAM记录](kotlin_second_sram.json)、[新版Flash记录](kotlin_second_flash.json)、[固化后下载元数据](kotlin_second_flash_download.txt)、[固化后WAV](kotlin_second_flash.wav)。WAV SHA256：`2c492fa12189698f5abf3032cfd97aa322e8c4df5456b37f0c7bf56800d760ed`；PCM CRC32：`A54A47B0`。

## 协议与实现

新增显式 OPEN_SECOND40 / READ_SECOND41 / ACK_READ_SECOND42。FPGA 对每块比较 RAW、原一阶/k9 和二阶/k5 的编码长度，二阶严格更短才选 codec11，平局保留 codec10，两者都不节省则 RAW。每声道的样本与差分预测状态在每块起点清零，按16位模运算，不使用测试音字典或周期。实板24块共 **192000→80002 字节编码数据（减少58.33%）**，不含协议封装，见 [compression.json](compression.json)。

复用原四个2KiB传输RAM银行，保持完整13位地址；不增加音频缓冲。OPEN3d/READ3e/ACK_READ3f仍只允许RAW/codec10，旧31/35始终RAW，即使处于40会话。缓存41/42在降级会话中拒绝0x8d，无DATA且不改游标/缓存，重新OPEN40可恢复原编码。APP仅明确UNSUPPORTED0x80才按40→3d→3c→3b→39→38→37→36→30回退；成功40后读取失败不静默降级。

APP通过完整逻辑CRC、编码规范性、PCM CRC、会话/请求/对象身份和范围校验后才发成功回执，PCM与检查点可靠落盘后才ACK。PCM上限仍为 `min(8112,(value_limit-4)*64-48)`，B3最多64片/逻辑8160字节。UART921600/8E1、H5窗口1、ACL27字节/8额度、实际15ms连接间隔保持。协议详见 [SECOND_TRANSFER_EXTENSION.md](../../docs/SECOND_TRANSFER_EXTENSION.md)，设计草案保留于 [SECOND_PROTOCOL.md](SECOND_PROTOCOL.md)。

## 验证与交付身份

| 项目 | 结果 |
|---|---|
| 固件 | `builds/20261020_095747_100259/impl/pnr/ble_protocol.fs` |
| 固件 SHA256 | `18c34c97a7bbe233f12096818310bbd689cc6d688c0a1b8adc8c19818693248d` |
| UserCode / Status | A25D / 70022020 |
| 50MHz时序 | Fmax50.018MHz，setup/hold违例0/0，最小setup余量0.007ns |
| 资源 | 17557 LUT、9480寄存器、11140/11520 CLS（97%）、37/56 BSRAM |
| APK | 0.2.10 / versionCode13，9685370字节 |
| APK SHA256 | `e94f8731787ad04435762ad26e9ba5f918f3240a296ea8cb1f29c535be785a3b` |
| 调试证书 SHA256 | `dc39e7120615a53f0bdf18629a361f0ebbf055d36c3b82f48adaf01cdae878ca`，v2验证通过 |

构建、时序及安全门禁通过后才编程。Flash operation54写入校验、operation1重载和最终身份读取均通过：[候选构建](candidate_final.json)、[门禁](gate_final.log)、[Flash记录](flash.json)、[最终身份](final_device_identity.log)。初始候选66B2仅构建，未写入板卡；最终A25D所用RTL此后未改动。

- [50组RTL回归](simulation.json)全部通过，包括原UART/H5完整30147字节补丁、新旧模式、MTU值限制20/61/182/244、CRC和重放语义；新增二阶8组。
- [二阶38组编码向量](encoder_second/result.json)与[原一阶38组向量](encoder_legacy/result.json)均与独立参考编码器逐字节一致并精确解码。覆盖测试音、静音、极值、噪声、斜坡、不同长度随机输入与随机游走，实际选出0/10/11三种模式；另有[144组参考往返](codec_fuzz.json)。
- [Android检查](android_checks.json)：63项普通测试通过，2项需实板的测试在普通套件中跳过；完整录音实板用例另行实际执行。Lint零错误，5项现有依赖版本提示。归档见 [android_final.log](android_final.log)、[lint.xml](lint.xml)、[APK签名](apk_signature.txt)。
- 固化后[九模式任意4字节检查点续传](profile_resume_flash.json)、[二阶重放/降级](second_replay_flash.json)、[一阶重放](lossless_replay_flash.json)、[扩展重放](extended_replay_flash.json)、[原控制命令与重连](protocol_flash.json)均通过。
- [12份原始通知离线核查](wire_audit.json)：直接重组原始通知，核对逻辑CRC、解码PCM CRC、参考内容/偏移及重复请求的相同编码。未使用APP归一化后的DATA替代原始线格式。
- [最终一致性检查](final_identity_check.json)：30个固件输入、48个Android输入与31个仿真源文件均与记录哈希一致，APK/位流哈希一致，三份完整WAV一致。可运行 `python3 reports/speed18_20261020/verify_release.py` 重验文件与归档身份；它不接触蓝牙或板卡。

开发过程中修正过Verilog声明顺序和只假设codec10的向量检查。第一次second_replay_61离线核查混入旧临时转储；回归入口已在每例前清理转储，该例随后干净复验10条真实传输全部通过，见 [clean_replay_61.log](clean_replay_61.log)。完整50组报告对应的RTL与测试源哈希仍一致。

## 手机使用与剩余边界

覆盖安装0.2.10，板卡保持A25D。连接 `GW25K-PROTO` 前先删除重配置前的未完成下载，再用内置1秒测试音开始录音、下载和播放。普通断线后可继续当前对象；板卡重启或重配置后的历史boot_id重复问题尚未修复。

本轮实测使用电脑BLE与生产APP Kotlin核心，不包含手机原生Android GATT、权限、UI、后台及手机实际速率；未接入ADB手机。本镜像完成Flash重载验收，尚未做物理断电上电验收。录音仍为内置测试音，未接麦克风。资源已用97% CLS、当前时序余量仅0.007ns，继续改RTL必须重新构建并通过门禁。

机器可读汇总见 [summary.json](summary.json)。历史交付见 [第十七轮](../speed17_20261020/README.md)。
