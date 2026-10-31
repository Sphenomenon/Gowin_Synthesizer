# M15 far 完整物理对照

M15 `D211010D` 完成 P&R、生成位流并通过独立子门。全局 hold 0 个违例、最小 +0.143 ns，原 DDR 路径 +0.619 ns；setup 仍有 3,081 个违例端点、最差 −1.774 ns，因此不能部署。[机器报告](dual138k_m15_far_physical_20261101.json)记录完整资源、时序、执行命令和证据哈希。

来源仍为 `custom138k-workstation-m-demo-v1-cf9d6319a310d6fe`。逐字节沿用[默认 M15](DUAL138K_M15_DEFAULT_PHYSICAL_20261101.md)的 VG `4707d235626cd446faf4ab00174f51c363c32db7926199cb2aa2449f51eb6a06` 和完整 SDC `6fa398b1bf7418d052e6cdc0c98c90512d506cc75931fa952b974f7b7db1562c`。仅在 CST 追加 DDR capture `R[2:10]C[2:20]` 与 launch `R[104:110]C[175:181]` 两条区域，未继承 reference monitor 区域；DDR 3.500 ns、自动 hold 修复、place2／route0、关闭资源复制及全部功能保持。未重综合或消费后续维护 RTL。

physical manifest SHA256 `aa8c3b612c0f54523f6e51c0930cdc88e413198b542afa669dcdf8a0a84f85ff`；FS `8875cac0561cc232adfac39a7794720f6239287d0fa01ef1e2dba04ba54e30a3`。Gowin V1.9.12 P&R 705.860 秒，exit 0。实际 FF 46,932／LUT 52,008／ALU 13,410／CLS 50,221／SSRAM 141／BSRAM 235／DSP 119；综合 equivalent BSRAM 195 分列。这些是相同源的不同物理结果，不记为新 RTL 资源收益。

| 时序 | 默认 D211010C | far D211010D |
|---|---:|---:|
| 最差 setup／违例端点 | −1.914 ns／3,590 | −1.774 ns／3,081 |
| 最差 hold／违例端点 | −3.478 ns／1 | +0.143 ns／0 |
| 最差 recovery | +3.239 ns | +0.686 ns |
| 最差 removal | +0.275 ns | +0.281 ns |

最差 setup 是 chorus LFO→read_address −1.774 ns，其后 oscillator allocated_mask→envelope_state CE −1.768 ns、TF available_bytes→accepted_used −1.767 ns。原 DDR launch 实际 R104C175、capture R2C2，arrival 6.037、required 5.418、skew 0.474 ns，关系仍为 3.500 ns。四条真实 clk50 专项报告分别为同域 setup −0.169 ns（表内 1 条负路径）、同域 hold +0.183 ns、全来源 setup −0.333 ns（表内 2 条负路径）、全来源 hold +0.183 ns；报告限制 100 条，不冒称完整专项违例数。

实际 VO native 54 项（51 通过／3 跳过）及 46 个破坏负控、boundary 7 项及 61 个破坏负控、官方六 PLL／三 shared tuple／七负控全部通过。六任务前后确认 32 个物理文件稳定；结束后重读 588 staged、1,365 冻结工具／源码输入和 685 个 PLL 依赖。最终 seal `m15-audits-v1/far-complete-seal-v1.json` SHA256 `c39b9018113831ba6fa540ad9809d4f2a2b72d0fcf0d05955b8f577fb2a15147`。

保留两个 M15 失败候选及原板上镜像，无 SRAM／Flash 或其他板卡操作。下一候选需重新绑定新维护来源和真实物理门禁；本次未完成完整 CDC／IO／电气、真实 HDMI／I2S／DAC／Push／25K、CNN／跟奏或双板联合验收。
