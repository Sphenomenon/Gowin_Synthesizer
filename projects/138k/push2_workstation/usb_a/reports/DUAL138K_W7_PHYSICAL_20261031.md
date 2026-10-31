# 双 138K：W7 首次完整物理实现

2026-10-31。W7 完成完整综合、严格可见 SDC／功能保留审计及 P&R，并生成 UserCode `D2103102` 位流。**真实资源可容纳，整机时序尚未闭合，未下载 SRAM、未写 Flash、未进行实板验收。**

候选 `custom138k-workstation-w-demo-v1-aec83bda901d0042` 来自 `/Users/sphenicidition/.cache/gw138k-dual-20261031/w-demo-d-v7`，完整新综合使用维护 HCI capability capture 修复和 W-only 未消费诊断端点策略 v3，不复用旧候选综合结果。实际 VG SHA256 `823bf08d45c27ed765c80ae47d52683cd14a8a0f38a49eb00e204dc268034fef`。严格综合网表审计通过，所有可见保留 SDC 成员分别解析，退役端点均不存在，真实录音的 38 个状态驱动及业务消费者通过。不能把被错误优化掉的逻辑计作资源收益。

物理目录 `/Users/sphenicidition/.cache/gw138k-dual-20261031/w-demo-d-v7-physical-v1`，Gowin V1.9.12 工具退出 0、全布通且完成位流生成；全部 `physical_inputs.json` 输入 hash 在 P&R 后复核一致。

| 项目 | W7 实测 |
|---|---:|
| Logic／FF | 83,721／45,041 |
| CLS／容量 | 57,639／69,120 |
| 物理 BSRAM／容量 | 293／340 |
| DSP／容量 | 68／298 |
| SSRAM | 310 |
| setup／hold 违例端点 | 9,178／2 |
| 最差 setup／hold | −8.598／−3.644 ns |
| 最差 recovery／removal | −3.513／+0.284 ns |
| audio Fmax／要求 | 46.255／76.8 MHz |
| clk50 Fmax／要求 | 40.029／50 MHz |
| video pixel Fmax／要求 | 165.645／148.5 MHz |

最差建立路径为 audio 同域 `u_managed/runtime/cpu_pcm.owner/staged_frames_0` 到 PCM owner 的 memory CE／written 状态，数据延迟 21.397 ns；需要在该维护子系统内修复实际组合路径。两个 hold 端点分别是保持原 `3.500 ns` 要求的 DDR 初始化路径 −3.644 ns，以及 `midi_bytes/acknowledge_toggle` 到 `ack_meta/D` −0.098 ns。最差 recovery 是 clk50 `u_reset/started` 到 performance CDC 的 audio 域 `source_release` CLEAR −3.513 ns；该 CDC 的反向 destination release 另有 −1.831 ns。不能通过放宽时钟、全时钟 false path 或删除实时音效／画面来声明通过。

[完整物理测量、前 50 条负 setup 路径及所有输入／输出 hash](dual138k_w_demo_v7_physical_20261031.json)，JSON SHA256 `48b9c2aa49fd82a2ba09c022d63c6f5f2cb3dee7a3a133b126428a9d79a67444`。位流 FS SHA256 `7d53e2ec3415396e723b8c034167224bc372582221592999f4187eef2e034831`，头部 UserCode 独立核实为 `D2103102`。

验证仅到源码、综合和失败的物理时序阶段；D 流式音频、25K 参数／反馈、唯一 DDR 录音对象、手机录音下载以及业务期间 HDMI／DAC 有效尚需实板证据。板卡回退保持此前镜像，没有改变板卡状态；单板分时验证也不能视作双板并发联合验收。
