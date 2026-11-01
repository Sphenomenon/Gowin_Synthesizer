# M19 far 完整物理结果

2026-11-01。`custom138k-workstation-m-demo-v1-3b42d2cc55cc70d5`完成全量P&R并生成`0xD2110121`位流，**完整STA失败，未上板**。来源与综合见[M19／W17检查点](DUAL138K_M19_W17_SYNTHESIS_20261101.md)。

| 实测项目 | 结果 |
|---|---|
| 物理Logic／FF／CLS | 67766／46932／50954 |
| 物理BSRAM／DSP | 235／340；119／298 |
| LUT／ALU／SSRAM | 53795／13125／141 |
| setup负端点／最差 | 3476／-2.302 ns |
| hold负端点／最差 | 10／-0.586 ns |
| recovery／removal最差 | +2.428／+0.278 ns |
| 四张clk50表最差 | +1.353／+0.178／+0.608／+0.178 ns |

最差setup为delay underflow_sticky→config_state CE。DDR原3.500ns要求保持，定向区域实测hold +0.508ns；剩余10个hold负端点属于48k参考计数器binary→Gray／binary，不能放宽CDC或时钟绕过。DDR UI另有505个setup负端点／TNS −319.105ns。报告中仍有TF available_bytes→write_ring_offset／write_total_bytes路径，不能因为有界表未列出accepted_used而宣称TF时序通过。

actual VO原生58项55通过、3个具名不适用，71项负控全拒；边界7项与69项负控通过，官方六PLL、7项负控及held-v2通过。六组进程退出0不覆盖完整STA失败；物理CDC和整机接受仍为false。PC仍只接受power-up-only范围，无warm reset接受。

主线程独立复验30个物理文件和2970份来源／工具／审计证据。机器记录见[DUAL138K_M19_FAR_PHYSICAL_20261101.json](DUAL138K_M19_FAR_PHYSICAL_20261101.json)；原始cache为`/Users/sphenicidition/.cache/gw138k-dual-20261031/m19-far-physical-audits-v1/results/M`。位流SHA256：`003900dabfa638edc487f3e5743d3fda83ac9ca8a08820b4aa15a1af6efcc4e0`；root复核SHA256：`95db7b75c2b66fb983f7ca7afe3d1eba5cdd2c9cfcd1e8e05af8be2ffa5b0a55`。不修改默认／历史失败输入、原SDC、时钟或证据。

M基础无CNN，W唯一录音对象仍为16384帧／64KiB；真实HDMI／DAC／USB／25K、手机A2DP／D处理／BLE下载和双板并发未验收。未执行SRAM或Flash，原板及Flash回退保留，T2-D1／D2未完成。
