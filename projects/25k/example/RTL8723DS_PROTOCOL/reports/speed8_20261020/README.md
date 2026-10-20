# 第八轮：排除串口与分块边界两条路线

本轮没有采用新默认值。现有固件及APP保持第七轮已验收的921600/OPEN_BULK/B3/460字节块和APP0.2.5，Flash未改写；SRAM已恢复相同的079C镜像。持续提速目标仍在进行。

## 实板结果

每次32768字节PCM，ATT MTU185/value182、B3、ACK_READ、无响应写入，全部数据及CRC与参考匹配。

| 试验 | 对照中位数 B/s | 候选中位数 B/s | 结果 |
|---|---:|---:|---|
| UART921600→2Mbps，各三次 | 5560.45 | 5559.62 | -0.015%，没有可测收益，拒绝 |
| 460→456字节块，同镜像交替三组 | 5587.91 | 5632.19 | +0.79%，小于运行波动，不修改默认值 |

UART对照为第七轮Flash镜像，2Mbps为实验SRAM镜像，按镜像先后各测三次；不能当作交替配对实验。分块试验在恢复后的同一921600 SRAM镜像上按460/456顺序交替三组。完整音频下载和手机性能未重复验收，不对其速度作新声明。

[summary.json](summary.json)记录全部样本、范围和决策；[notification_wire_check.json](notification_wire_check.json)重新组装十二份原始通知，校验每块PCM、偏移、长度和CRC。所有源抓包随报告保留。

## UART实验

Linux v6.12 [btrtl_convert_baudrate](https://github.com/torvalds/linux/blob/v6.12/drivers/bluetooth/btrtl.c)明确将 `0x00005002` 映射为2Mbps。来源及哈希见[baud_reference.json](baud_reference.json)，源文件快照为[linux_btrtl_v6.12.c](linux_btrtl_v6.12.c)。启动仍115200/8E1，完整补丁/Reset后通过FC17切速；50MHz下2Mbps使用25分频。

实验初始化器仅允许原速、921600和2000000，未知速率在任何HCI命令前失败；切速明确拒绝时保持原速失败。实验源码及测试保存在 `uart_2m_sources/`；`source_before/`保存原输入，生产源码已精确还原。

[candidate_build.json](candidate_build.json)是**未采用的实验候选**：位流SHA256 `943674e1a311c9f04ea23fd7b7e1c09daa753538baaafc5b45f624a32b1126ad`，UserCodeCE14。Fmax50.170MHz、setup/hold违例0/0，16803 LUT、9229寄存器、10861/11520 CLS、34/56 BSRAM。[25组仿真](simulation_2m.json)通过，包含50MHz模型下的2Mbps命令/无响应写入/切速拒绝、未知速率拒绝、完整30147字节补丁及既有回归。[firmware_inputs.json](firmware_inputs.json)描述实验输入，不能误认为当前生产源码；当前源码已恢复第七轮30个输入的原SHA256。

[UART耗时估算](uart_budget_estimate.json)显示，满460字节块的DATA需要21个ACL物理包，不计转义为751串口字节。2Mbps理论上可节省约4.79ms，但实板未转化为有效吞吐提升。这一结果把后续重点转向每块业务往返及无线调度。

## 分块实验

MTU185时B3每片逻辑数据178字节。460字节PCM对应508字节逻辑报文，分为178/178/152；最后一片加B3、ATT和L2CAP头为163字节，超过六个27字节ACL包的162字节容量。456字节PCM可将末片降至159字节，完整DATA从21个物理包减为20个，但PCM块也略小，实际吞吐提升仅0.79%。这些ACL数量由已实现的27字节分段规则及原始通知长度推导；未通过外部空口分析仪直接观测链路层包。

下一步可评估显式协商下的下载命令/成功响应合并：成功DATA已经包含请求ID、nonce、对象、偏移、长度及CRC，可作为读取完成的完整证据。只有经过协议定义、超时/精确重传/错误响应/持久化顺序验证，并与旧固件回退兼容后才能采用；目前尚未实现或对外宣告支持。

## 恢复与限制

[恢复SRAM记录](restore_baseline_sram.log)、[恢复后协议复测](protocol_restored.json)。当前交付索引仍为[ready_build.json](../ready_build.json)，指向第七轮079C固件；APP仍为[0.2.5 APK](../../artifacts/gowin-control-0.2.5-gw25k-bulk-debug.apk)。无需安装新的APK。

手机原生GATT/UI、实际速率、当前镜像物理断电验收，以及既有boot_id重复限制均沿用[第七轮报告](../speed7_20261020/README.md)。板卡重启或重配置后先删除手机未完成下载，再开始新录音。
