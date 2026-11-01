# M19 reference 区域布局完整物理结果

2026-11-01。`custom138k-workstation-m-demo-v1-3b42d2cc55cc70d5` 的独立布局 `0xD2110124` 完成全量 P&R 与六项审计，**完整 STA 失败，未上板**。

从 [M19 far D2110121](DUAL138K_M19_FAR_PHYSICAL_20261101.md) 派生，VG／SDC 及 DDR 3.500 ns 要求逐字保持。CST 仅追加两个 reference monitor 的各 64 个 binary／Gray FF 区域：48k 为 `R[54:54]C[64:84]`，44.1k 为 `R[56:56]C[64:84]`。DDR 原 far 区域保留；没有逻辑、时钟或时序例外改动。

| 实测项目 | 结果 |
|---|---|
| P&R 耗时／退出码 | 343.220 秒／0 |
| 物理 Logic／FF／CLS | 67,752／46,932／50,878 |
| 物理 BSRAM／DSP | 235／340；119／298 |
| LUT／ALU／SSRAM | 53,795／13,111／141 |
| setup 负端点／最差 | 5,526／−3.417 ns |
| hold 负端点／最差 | 11／−0.198 ns |
| recovery／removal 最差 | +1.807／+0.281 ns |
| 四张 clk50 表最差 | −1.264／+0.123／−1.264／+0.123 ns |
| DDR 指定 hold | +0.503 ns，arrival5.851／required5.348 ns |

reference hold 较原 far 的 −0.586 ns 改善，但仍有 11 个真实同域同沿违例，最差为 binary[30]→Gray[29]，不能按 CDC 误豁免。setup 最差为 delay `peer_fault`→`config_state[0]` CE，另有矢量 DSP 输入长链。DDR UI 有 571 个 setup 负端点／TNS −476.102 ns，实测 Fmax78.412 MHz，仍未达到 100 MHz。局部 hold 变化不代表整机收敛。

原生 VO 58 项中 55 通过、3 个具名不适用／71 负控全部拒绝；边界 7／69，官方六 PLL／7 负控及 held-v2 通过。主线程独立重验 12 份物理输入、30 份完整物理文件、2,972 份来源／审计证据。机器记录见[完整身份与测量](DUAL138K_M19_REFERENCE_PHYSICAL_20261101.json)。

位流 SHA256：`b0501ac37ad700327d099c291c40a99cf686b47b5e68de5967704da16e065336`。root 复核 SHA256：`84e385017003a3755c3b4c1d43e762a90e184a71c400c022a1f7c0c19850db50`。cache 为 `m-demo-base-v19-physical-reference-v1/` 与 `m19-reference-physical-audits-v1/`。

完整物理 CDC 与真实 HDMI／DAC／Push／25K／TF 均未接受，M 基础仍无 CNN；T2-D1／D2 保持未完成。未操作 SRAM／Flash，原板内容不作推断。原 far 输入与失败证据保留为比较／回滚身份，均不是已接受部署。
