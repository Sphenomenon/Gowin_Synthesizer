# P24 A/B/C 模式响度校准验证

2026-09-16：受控基线、两种校准方案比较、最终单音/最大复音仿真、完整构建、路由分项审计及 SRAM 下载/读回已完成。P24 UserCode 为 `0x00000024`，Flash 未写。用户完成实体听感和功能回归后报告“没问题，完美”，P24 已通过验收。

## 最终数字结果

正式单音记录：`results/p24_level_measure_20260916_182045_725593/measurement.json`。五种音色的 B/C 对应 A 计权偏差如下：

| 音色 | B 对 A | C 对 A |
|---|---:|---:|
| 笛 | +0.0001 dB(A) | −0.0004 dB(A) |
| 弦 | +0.0001 dB(A) | −0.0011 dB(A) |
| 铜管 | −0.0001 dB(A) | +0.0017 dB(A) |
| 马林巴 | −0.0001 dB(A) | −0.0003 dB(A) |
| 钢琴 | +0.0000 dB(A) | −0.3716 dB(A) |

十五组均采 8192 个最终 PCM 帧，左右声道一致，clip 为 0。未加权 RMS 仍因谐波能量分布不同而相差 `0…−8.54 dB`，这是预期结果，没有把它写成未加权 RMS 完全相等。

最大复音记录：`results/p24_polyphony_20260916_182045_577897/verification.json`。A/B/C × 五音色的 32 声部跨音高和弦全部无输出 rail、无效果链 clip；最高峰同音极限也通过：A 弦乐峰值 2146466849，B 马林巴 2046656512，C 钢琴 2089196748，均低于 32 bit 正峰值 2147483647。

P23 PANIC 定向回归 `p23_panic_182045_535384/verification.json` 全部通过。校准只改变 gain ROM 内容和 UserCode；AE350 boot binary、RTL、约束、Push、HDMI、DDR、效果器与事件路径相对 P23 不变。

## 构建与审计

正式构建：`results/build_20260916_181039_663260`。

| 项目 | P23 | P24 |
|---|---:|---:|
| setup 违例 | 0 | 0 |
| hold 违例 | 0 | 0 |
| 最差 setup slack | +0.087 ns | +0.087 ns |
| Logic | 34848 | 34848 |
| Register | 25381 | 25381 |
| BSRAM | 253 | 253 |
| DSP | 43.5 | 43.5 |

Gowin 完整综合和布局布线返回 0，生产输入在构建中未变化。位流 header CheckSum 为 `0x01F6`，SHA256 为 `7a37311de6df38ed1f0191bd2f07094904df826dd69c4b2007f2e0ec099c1c66`。

完整 `usb_a_audit.json` **未通过**，错误仍且只记录为 `u_managed/effect_mask_sync_0_s0/RESET`、`_1_s0/RESET`、`_2_s0/RESET` 未被 stopped-clock reset 审计覆盖。独立音频 PLL/mailbox routed audit `p24_audio_routed_audit.json` 通过，PLL_INIT 最长传播 9.711 ns；局部通过不覆盖完整失败。

## SRAM 与实体结果

下载记录：`../results/sram_20260916_182346_293937/result.json`。实际写前读回 P23 `0x00000023`，只执行 SRAM 操作 2，写后读回 P24 `0x00000024`；before/sram/after 均通过，`fpga_flash_written:false`。

用户按约定检查五种音色的 A/B/C 持续响度、高力度和弦，并回归电脑长按、PANIC、Push pad/连续压力、Push 屏幕/灯光、HDMI、耳机和效果链，报告“没问题，完美”。验收后再次只读：ID `0x0001081B`、UserCode `0x00000024`、status `0x00026230`；这次只读未执行编程，Flash 仍未写。数字 A 计权结果和实体结论分别保留，不以仿真代替实体验收。
