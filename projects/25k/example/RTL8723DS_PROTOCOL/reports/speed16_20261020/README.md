# 第十六轮：6包通知边界试验与无损编码可行性

MTU158试验未带来收益，恢复原交付22B4/MTU上限247（电脑有效MTU185），Flash与APK不变。本轮另完成通用无损差分/Rice编解码离线验证，内置参考PCM字节减少32.2%；尚未接入FPGA、APP或协议，不宣称实板下载提速。持续优化目标保持进行。

## MTU158实板

只将服务端MTU响应及有效MTU上限从247改为158；电脑有效value155，B3每片151逻辑字节，完整通知162个L2CAP/ATT字节、6个27字节ACL包。原电脑MTU185/value182每片178逻辑字节，完整通知7个ACL包。两者OPEN_EXTENDED最大PCM均8112，不改音频块、UART921600、H5窗口1、实际控制器8包额度、15ms请求和应用确认策略。

| 阶段 | 32768字节吞吐B/s | 中位B/s |
|---|---|---|
| 原MTU185前测 | 9980 / 9893 / 9981 | 9980 |
| MTU158候选 | 9627 / 9301 / 9978 | 9627 |
| 原MTU185回测 | 9849 / 9714 / 9757 | 9757 |

候选中位较原前测−3.54%、较原回测−1.34%，无已证实收益，未采用。这是分组后回测，不是交替配对；不据此推断精确因果。每次同为5个DATA块，MTU185为187个Transfer通知/推导1299个DATA物理ACL包，MTU158为223个通知/1315包（约多1.23%）。九份原始通知全部独立重组验证逻辑CRC32、PCM CRC32、对象身份、连续偏移和逐字节参考音频。推导包数不等于空口抓包。

F602候选`builds/20261020_092025_412082/impl/pnr/ble_protocol.fs`，SHA256 `2be33a2353e609ea793ab6b6cb0aae07c4fbe585c44ac6f93fc4a15b864a6dc1`，时序通过后才加载SRAM。构建/输入/编程分别为mtu158_build.json、mtu158_inputs.json、mtu158_program.log。五种MTU请求23/64/158/185/247覆盖上限响应、有效值裁剪、畸形和重复请求隔离、重连重新协商；155-value的最大块分片与完整录音命令状态机回归、253字节补丁UART/H5系统冒烟均通过，见component_simulations.json和mtu158_clamp_sim.json。

初次clamp测试继承了旧测试中相对ROM路径，又重复覆盖AUDIO_FILE，虽报PASS但含readmemh ERROR；旧日志保留为*.old_rompath.log，不计作验收。去除重复路径后五项全部重跑，无ERROR/FATAL。原生产测试文件未修改。

## 无损编码离线证据

[lossless_feasibility.py](lossless_feasibility.py)实现独立通用编解码：双声道16位有符号模差分、zigzag、分块Rice参数k、15位一元逃逸到16位残差。每块重置预测器，不使用测试音周期、字典或参考音频辅助解码；只有主验证流程读取参考并比对。若编码不比原PCM短则使用原始PCM回退，带1字节离线模式头，最坏PCM+1。此头不是已部署线格式。

192000字节参考PCM分24块、每块最多8112；编码130153字节，减少32.21198%，每块最优k9。解码PCM SHA256与原PCM同为`3c42476a276269189432da893676a23ead1af624a260f95e1d0b319dbf02844c`。静音、常量、正负极值、独立双声道斜坡、噪声和参考前缀验证通过；56项确定性随机往返及8项畸形输入拒绝通过，另有手工码字验证。噪声回退RAW8113字节，不宣称随机PCM可压缩。

解码严格检查模式、尺寸、截断、非规范逃逸、残差越界、尾随字节和非零填充。重新执行脚本可得到[lossless_feasibility.json](lossless_feasibility.json)。结果只证明当前算法在这些数据上的正确性和编码字节数，不能代替RTL/APP实现、资源/时序、协议协商、精确重放、断点续传、损坏帧拒绝和实板WAV验收。后续若接入必须显式新模式协商，保持旧RAW模式，并保留原始PCM偏移/长度/CRC和可靠落盘后ACK。当前8160逻辑上限须精确计入模式元数据，不能直接把PCM+1原型塞入现有最大块。

## 记录与恢复

- [audit_speed.py](audit_speed.py)、speed_audit.json：九份通知重组、CRC和PCM独立核查；mtu185_before/after_*.json及mtu158_*.json保留原始数据。
- source_before/为原生产GATT；mtu158_sources/为实验输入和定向测试。
- baseline_restore_program.log恢复22B4，release_recording.json/.wav记录完整192000字节复验，final_device_identity.log和restored_identity.json封存身份。
- summary.json是最终汇总。所有BLE客户端串行，编程等待客户端结束；最终30个固件输入、43个Android输入、ready_manifest和0.2.8 APK与交付一致。本轮未为未采用候选重跑全部RTL/Android回归。

手机原生GATT/权限/UI/后台及吞吐、当前镜像物理上电未在本轮验收。跨重启boot_id可能重复，重配置后删除手机未完成下载；音源仍为内置1秒双声道48kPCM16。
