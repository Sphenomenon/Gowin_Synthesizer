# B04 CPU 标准协议实验源代码阶段

复核：2026-10-31（task 2026-10-30 批次）。这是未选择的 CPU 源代码基础阶段，
**不是 B04 整项、A2DP1.4 合规、手机互通、完整固件容量／时限或硬件验收**。
本阶段未改生产 profile、builder、boot ROM、冻结基线、task.md 或主工作区，
未综合、P&R、操作板卡或 push；父级负责集成、独立复核及发布。

来源起点 `a6d8300fca3332736c22033ebb4236f61c151932`，隔离克隆分支
`codex/b04-cpu-standard`。实验输入集合标识：
`4865542f99f49cf85abf9ffac1d27c60492b912bfd34cab27acf31b299ddb3e7`，
由最终机器报告 `inputs` 表按键排序、紧凑 JSON 编码后取 SHA256 产生。

实现及边界见 [组件契约](../firmware/ae350/CLASSIC_SOURCE_STAGE.md) 和
[来源收据](../firmware/ae350/classic_source_provenance.json)。
[机器证据](workstation_task_20261030/b04_cpu_standard_source.json)
SHA256 为 `70573b9e67dd0561a5dd2f38fab767cb3b4c4cb6656095a37c38370515fd311d`。
外部完整编译／运行日志保留在
`/Users/sphenicidition/.cache/gw138k-task-20261030/b04-cpu-standard-v1/evidence-v7/`。
最终报告生成后逐个重新核对全部 `inputs` 哈希，源码与本轮测试输入一致。

## 本阶段得到的行为

`classic_service.c/.h` 是单 cooperative CPU owner、无 heap 的有界组件。
它接原始 HCI ACL 及 PL 明确赋予的 link epoch／handle generation，执行
BR/EDR Basic-mode L2CAP 重组、SDP 单实验 Sink record 与有界 continuation、
单 SEP AVDTP acceptor、RTP／SBC 拆帧和四帧压缩队列。
原始 HCI event observer 仅处理匹配的成功 Disconnection Complete，不是 GAP 栈。

CPU 不拥有 UART／H5、控制器命令／ACL credits、HCI reset 或物理采样率。
本组件只产生 ACL，连接／配对等 HCI 命令仍须由未来 connection policy 通过
唯一 HCI owner 提交。CPU TX 每片的上限来自实际 BR ReadBufferSize，取其与
276 的较小值；27／276 两种容量已重组出完全相同的 SDP 响应。
`ACCEPTED` 才推进分片；`REJECTED` 保留同一 token；`UNCERTAIN` 封锁会话，
不自动重放。AVDTP 状态及配置在最后一片响应接受后提交。

接收 MTU672 与物理 HCI payload276 分开；官方 A2DP1.4 §5.2.1 要求最少335。
L2CAP 参数 MTU 按方向记录；未知 mandatory 参数、配置调整或 continuation
安全拒绝，跨 PSM／新 identifier 的 SCID 复用返回0x0007。
只有相同 PSM、SCID 和原 ConnectionRequest identifier 的重传可复用结果。

SET_CONFIGURATION 仅接受已有解码器实际覆盖的44.1/48kHz、SBC 所有四种
channel mode、4/8 subbands、4/8/12/16 blocks、loudness/SNR、bitpool2..53。
START 另需真实音频 owner 对所选采样率给出 `audio_ready`。
媒体缺口、坏包或满队列清除旧帧并递增 stream epoch，消费者必须重新建立
解码历史；不允许为了这些工作停止实时音频采样。重复／乱序包不重复解码。
RTP、SBC 分片计数3→2→1、共同时间戳及非末片等长均有验证。

## 离线验证

最终运行：

```sh
python3 projects/138k/push2_workstation/usb_a/sim/run_ae350_classic_service.py --output /Users/sphenicidition/.cache/gw138k-task-20261030/b04-cpu-standard-v1/evidence-v7
```

| 范围 | 结果 |
|---|---|
| 实际 C 原生字节向量 | 44,612 checks 通过 |
| 同一实际 C ASan＋UBSan | 44,612 checks 通过，未见 sanitizer 报错 |
| 确定性随机载荷 | 5,000 个原始 ACL 长度／PB 样例，4,000 个有效 L2CAP 封包内的 SDP／AVDTP 随机载荷 |
| SDP 长度与 continuation | 672/673、65535/65536、0xfffffffb..ffffffff 等32位长度极值；search／attribute 两条路径；不同 TID continuation、伪造 token |
| 传输／生命周期 | 多 ACL 切点、27/276 TX 分片、稳定 token、重复 result、旧 generation、uncertain fence、断开、重连、UINT32_MAX 流代次耗尽 |
| 协议及媒体 | 双向 L2CAP config/options、多个 signaling 命令、跨 PSM CID、AVDTP signaling fragments、延迟 START、RTP 回绕／重复／乱序／缺口、PT/M/X、四帧满队列及 SBC 分片计数 |
| 行为负控 | 15 个变异全部被拒绝，含32位序列长度加法回绕、跨 PSM CID、忽略实际控制器容量及配置调整、忽略音频 ready、丢弃 config commit、重复媒体、漏分片计数、queue overrun、RX 覆写、旧 generation、uncertain 重放、错误 TID 绑定 |
| 实际 SBC 端到端 | 11 组真实压缩数据，经 ACL→L2CAP→RTP→帧队列→实际 Apache OI 解码器；原生／sanitized PCM 逐字节相同，共118,784 scalar samples；与独立 BlueZ 参考最大误差6（门限8） |

Sanitizer fixture 还 poison 每次收到的 PDU 后面未用的 RX 尾部，检测位于
大对象内、但已经越过本次 PDU 的旧字节读取。单靠常规对象越界检查不能证明
这个边界。复核发现的 SDP32 位加法回绕已改成先做减法界限判断，旧行为变异
在该检查下失败。随机 fuzz 是确定性的有限覆盖，不是穷尽证明。

## RV32 增量与未完成边界

`rv32im_zicsr_zifencei`、ILP32、O2、freestanding、严格告警的实际目标编译通过：

| 测量项 | 数值／范围 |
|---|---|
| `.text`＋只读数据 | 14,485 bytes |
| 该 TU 全局 data／BSS | 0；状态由调用方分配 |
| RV32 service 对象 | 2,848 bytes |
| 单个 frame／TX 返回对象（host 同布局） | 252／296 bytes |
| 最大单函数 stack frame | 480 bytes，非调用链总栈证明 |
| 运行库依赖 | memcpy、memset；预算编译只提供声明，完整固件必须链接实际实现 |

尚缺的硬条件包括：A2DP1.4 Sink **mandatory Delay Reporting**、配对／安全／
可发现与连接策略、请求／fragment 超时及恢复、完整配置协商、主动媒体断开、
与唯一 HCI owner 的真实 MMIO／RX lease／host credit 交接、旧 BLE credit owner
退役、BLE／BR 并发压力、PCM 硬件队列及代次提交、音频真实采样率 grant、
同标称采样率的长期时钟漂移、完整固件链接／ILM/DLM／调用链栈、解码周期和
最坏服务间隔、资源／时序／CDC／手机／真实声音验收。

SDP record 保留目标 profile1.4，但名称明确为 `138K experimental sink`；因
mandatory Delay Reporting 等缺口，它只用于离线实验，不可作为标准 Sink
合规宣称或直接对手机发布。没有为绕过缺口而无依据降低 profile 版本。
后续生产集成必须关闭这些缺口并创建新的显式来源身份；本阶段未选择文件，
回退只需撤销该源代码提交，无板上／Flash 状态需要恢复。
