# 第十七轮：通用无损 PCM 下载（C678 / APP 0.2.9）

已完成 Flash 编程校验、重载及无线验收，`reports/ready_build.json` 指向 C678。新模式在 FPGA 编码、APP 解码，输出 PCM/WAV 与参考逐字节一致。不能缩小的数据使用 RAW；没有音源字典或测试音专用重建。

## 实测速率

同一 C678 镜像、同为8112字节PCM块，三组RAW/LOSSLESS交替，每次32768字节：

| 组 | RAW B/s | LOSSLESS B/s | 提升 |
|---|---:|---:|---:|
| 1 | 9340.05 | 13252.50 | 41.89% |
| 2 | 8957.29 | 13928.32 | 55.50% |
| 3 | 9107.11 | 13484.00 | 48.06% |

中位 **9107.11→13484.00 B/s（+48.06%）**，三对均提升。Flash后复测13330.23 B/s。这里是解码后的有效PCM吞吐，非无线链路速率。完整192000 PCM分24块编码为130129字节，减少32.22%，逻辑与蓝牙分片头另计。

同一APP源码在22B4旧固件和C678新固件完整下载分别27.1705/18.6010秒（−31.54%）；包括相同22832偏移DATA回执丢失、相同逻辑ID/字节重试、14720取消重开、29440断线续传及WAV落盘。Flash后的再次完整APP验收19.8510秒。三份192044字节WAV均与参考一致，SHA256 `2c492fa12189698f5abf3032cfd97aa322e8c4df5456b37f0c7bf56800d760ed`。结果是电脑BLE桥接真实APP Kotlin代码；手机原生GATT、权限/UI/后台和手机实际吞吐尚未测试。

## 实现

显式OPEN_LOSSLESS3d协商与3c相同的MTU/PCM上限，READ_LOSSLESS3e、ACK_READ_LOSSLESS3f保持原业务与原子ACK语义。DATA旧reserved16改为codec:u8+zero:u8，0为RAW、10为通用stereo PCM16模差分/Rice k9，预测器每块清零。PCM长度、CRC、偏移、确认及检查点均指原始解码PCM；逻辑CRC覆盖实际编码负载。编码长度不更短时RAW，无额外头字节。原31/35始终RAW，即使处于3d会话。新读取缓存只有当前3d且上限足够时才能重放；降级后的8d不覆盖成功缓存，重新3d可重建完全相同编码数据。

FPGA两遍处理：先计长，再编码写入原四个2KiB缓冲；无额外负载RAM。编码阶段由原ROM取样，CRC阶段回读已编码缓冲。保留完整13位地址，综合网表四个bank均为独立11位读写地址，实板RAW和编码跨bank逐字节通过。

APP仅明确UNSUPPORTED80才3d→3c→3b→39→38→37→36→30回退。只有成功3d与对应3e/3f请求授权解码；拒绝未知模式、截断、非规范转义、多余整字节、非零填充。完整逻辑/PCM CRC、会话/请求、对象/范围通过后才发布DATA成功回执及归一化PCM，后续仍先可靠写PCM与检查点再ACK。3d承诺后的新读取失败不会静默退回RAW操作。UART921600/8E1、H5窗口1、ACL27/8额度、业务窗口1维持原设置。

详见[协议](../../docs/LOSSLESS_TRANSFER_EXTENSION.md)。音源仍是内置1秒测试音；本轮未接实时麦克风。

## 固件与APK

C678：`builds/20261020_093455_977383/impl/pnr/ble_protocol.fs`，SHA256 `ea2a59dac6df327f1cde88d332d8f1374138de8f7733de45c2a04bffa33daef2`。50MHz约束Fmax50.586MHz，setup/hold0/0，最小setup slack0.232ns；16848 LUT、9427 Register、11024/11520 CLS（96%）、37/56 BSRAM。30项固件输入匹配原构建暂存副本。Flash operation54写入校验、operation1重载，最终C678/70022020。

[APK0.2.9 / versionCode12](../../artifacts/gowin-control-0.2.9-gw25k-lossless-debug.apk)，9668978字节，SHA256 `304618feb70694a5529bec31ab7ae8e8f9425bd0ada6ddb9709335cece467659`。v2签名核验通过，与原测试APK同证书，可覆盖安装。

板卡重新配置后先删除手机未完成下载，再新建录音。同镜像重载boot_id仍可能重复。新镜像物理断电重启未验收；已通过Flash重载。原生手机测试需用户安装新APK后执行。

## 验证与证据

- [三组交替测速](paired_speed.json)、[原始通知独立CRC/PCM审计](wire_audit.json)，12份捕获包含旧/新APP与Flash下载。可执行`python3 reports/speed17_20261020/audit_captures.py`复核。
- [完整WAV与时间对照](complete_wav_check.json)、[APP SRAM](kotlin_lossless_sram.json)、[旧固件回退](kotlin_old_sram.json)、[APP Flash](kotlin_lossless_flash.json)。每份原始GATT请求/通知都保留，含精确DATA重放。
- [完整录音/错误ACK/重放/恢复](recording_sram.json)、[Flash八种模式续传](profile_resume_flash.json)、[编码缓存跨模式](lossless_replay_flash.json)、[原扩展缓存](extended_replay_flash.json)、[原控制协议](protocol_flash.json)。
- [原35组RTL回归](simulation.json)全部通过；[新增7组](components.json)：value20/61/182/244与三种缓存降级，通过实际逻辑CRC、独立PCM解码、RAW回退和原读取保持RAW的核查。新版`run_sim.sh`已纳入7组；35组原回归与7组新增在本轮分别执行，未宣称一次42组完整运行。
- [35组真实RTL编码器向量](encoder/result.json)：24个音频块、静音、常量变化/符号极值、独立通道斜坡、噪声与7种随机长度，对照独立参考逐字节编码和解码。使用`python3 tests/check_rice_rtl.py`复现。
- [Android检查](android_checks.json)：51项普通测试通过，2项物理用例默认跳过；物理录音用例另有实际执行。Lint零错误、5项既有依赖更新提示，未改依赖版本。新增错误报文、回退、超时精确重试和协商后禁止静默降级测试。
- [Flash](flash.json)、[门禁](gate_initial.log)、[固件输入/完整RAM地址](firmware_inputs.json)、[最终身份](final_device_identity.log)、[APK签名](apk_signature.txt)、[APP输入](android_inputs.json)、[汇总](summary.json)。

初版测试中的BUSY期望列表错误、短块offset0误以为应RAW（实际零样本能压为3字节）、审计块数误设11均已修正测试；失败日志保留。最初审计把不存在于便携源码的构建生成顶层以及Gradle缓存也列入比较，改为30项实际固件输入后通过。Lint最初断言无警告失败于5项依赖更新提示，未作隐藏或抑制。未发现因此需要变更候选RTL，发布镜像与首轮C678相同。

持续优化目标仍保持进行中。
