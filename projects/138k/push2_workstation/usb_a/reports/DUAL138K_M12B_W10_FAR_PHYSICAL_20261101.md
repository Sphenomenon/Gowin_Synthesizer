# M12b／W10：DDR far 完整物理测量

2026-11-01。`D210311A`／`D2103119` 分别从本次 M12b／W10 默认测量及 SHA／VO 派生；完整 VG／SDC 逐字节不变，CST 仅追加已审阅的初始化 launch／capture 对角放置区。两份均完成完整 P&R、生成新位流，DDR 原3.500 ns要求保留。没有改写默认候选或冻结来源。

| far P&R | Logic | FF | CLS | 物理 BSRAM | DSP | setup 端点／最差 ns | hold 端点／最差 ns | recovery／removal ns |
|---|---:|---:|---:|---:|---:|---|---|---|
| M12b `D210311A` | 66,194 | 46,931 | 50,286 | 235／340 | 120 | 1,524／−1.299 | 0／+0.143 | +2.010／+0.275 |
| W10 `D2103119` | 83,718 | 45,073 | 57,500 | 293／340 | 67.5 | 5,532／−5.338 | 1／−0.063 | +1.274／+0.278 |

实际 launch／capture 均为 R104C175→R2C2，位于要求的区域内。目标 DDR hold 分别 +0.624／+0.662 ns。两份全部物理输入和测量记录的输出再次校验；这些结果不代表整机时序通过。

M 的四条实际50 MHz专项报告均无负路径，同域 setup +1.166 ns、同域 hold +0.164 ns、to-clock setup +0.850 ns、to-clock hold +0.164 ns。报告各最多100条，不代替全局端点计数。M 全局最差路径已转为 chorus LFO→read_address，−1.299 ns；音频采样许可和显示发布路径仍有 setup 缺口。

W 同域50 MHz setup 专项最差 −2.934 ns、hold +0.202 ns。余下一条全局 hold 为 `u_managed/midi_bytes/acknowledge_toggle_s0/Q`→`ack_meta_s0/D`，audio76m8→clk50，data0.385 ns、skew−0.400 ns、slack−0.063 ns。尚未添加例外或认定 CDC 接受，不能把 DDR 目标修复当作完整 hold 关闭。同步 reference48、功能写指针 recovery／removal 等原检查保持。

M 默认与 far 的实际路由 VO／SDC 分别通过原生协议、接收边界和官方 simlib PLL 子门，两份前后来源哈希一致，未套用旧候选结论，也未重复未变工具的全部负控。W far 原生 VO／实际 SDC、PLL／selftest通过；VO回归54项中40通过、14角色不适用跳过、35负控拒绝，PLL保留7负控。**两份整机仍不可部署**。

[机器证据](dual138k_m12b_w10_far_physical_20261101.json) SHA256 `3eb9c61896b8ceabc3d2f43d581873879cab6d6d5ef3601b6eea0ae8d6a2e29e`，绑定两份完整物理清单、默认→far不变输入、实测资源／时序和独立子门。M far 位流 SHA256 `b97d7f9fee29c9cf753586b01c44101a1da2a6e829e4b37a6a5d24cbe94577bf`；W far 为 `12e7d56a108cab93b6e3ea2a26495a9b04c5a3da0ce024f666c6e0ea4f048d3b`。

本阶段没有 SRAM／Flash 操作，未做真实声画或手机验收。主工作区和板上镜像未改；M CNN、W长录音、独立演示、LCD和双板并发均继续保持未完成状态。下一候选消费已验证的 owning-module 修复后重新综合／P&R，不沿用此处失败候选的身份。
