# P16 连续压力与 Push 屏幕刷新候选

状态：P16 已完成 RTL、综合/布局布线和 SRAM 下载，等待本轮实体验收。P14 的 C 模式 32 声部改动、P13 共享 DDR 显示数据、P12 HDMI reader、P10 串行效果链和 P2 低音路径均保留。

## 本轮改动

- Push USB-A 的 CIN `0xA` poly-aftertouch（按下的 pad）映射为内部 expression 事件，保留 pad 的 held 状态，不重触发音符；非 held pad 的压力消息忽略。
- 统一振荡器为每个声部保存 8 位压力增益：MIDI 压力 0 映射到静音，127 映射到 unity，中间值连续缩放当前声部输出。压力事件按 MIDI note 匹配活动声部。
- Push 屏幕像素模块把主机的 frame request 作为提交点。保留原计数器，但不再用它阻塞快照，因此每个 USB-A 屏幕帧都会重新采集 control、options、held、note、velocity；同周期到达的共享 effect metadata 也一并提交。USB-A 帧格式未改。

## RTL 仿真

- `results/push_pressure_rtl_recheck_20260915_021104_854926952/simulation.log`：Push pad 按下后发送压力 0 和 127，输出内部 kind 5 事件，held 保持，映射事件数为 3。
- `results/unified_expression_recheck_20260915_021101_743817716/simulation.log`：同一活动音符的压力增益依次锁存为 0、128。
- `results/push_surface_refresh_rtl_20260915_022817_045672204/simulation.log`：在旧计时器仍忙时提交第二个 frame request，control/options/pads/note/velocity 均更新；覆盖了原先导致 UI 停在首帧的条件。
- `results/c_mode_32_recheck_20260915_021058_644339381/simulation.log`：压力改动后 C 模式 32 声部回归仍通过，32 个活动声部、1024 slot 扫描、1035/1600 音频周期延迟。

这些是 RTL/ROM 模型检查，不代替实体 HDMI、Push 或耳机验收。

## 综合、布局布线与资源

构建目录：`results/build_20260915_022851_841406`，器件 `GW5AST-LV138PG484AC2/I1`。

| 项目 | 结果 |
|---|---:|
| setup 违例端点 | 0 |
| hold 违例端点 | 0 |
| Logic | 33,793 |
| Register | 25,164 |
| BSRAM | 253 |
| DSP | 43.5 |

相对 P14，新增每声部压力增益状态和一个窄乘法路径；BSRAM 未增加，DSP 仍在器件容量内。Gowin 路由日志中的 `clk_50m_d` generic routing 警告保留记录，没有把它改写成 reset audit 通过。

`results/build_20260915_022851_841406/Prj1/scripts/check_build.py` 仍报告两个既有缺口：历史 DDR reset 证据源路径缺失，以及 `u_managed/effect_mask_sync_[0..2]_s0/RESET` stopped-clock 覆盖缺口。本轮没有伪造或隐藏这两项。

## SRAM

- 位流：`results/build_20260915_022851_841406/Prj1/impl/pnr/Prj1.fs`
- SHA256：`85f6eba4b9db18468b300a58567bfb4a096123fbf699eea041ecc8f426450e82`
- UserCode：`0x0000C706`
- 下载记录：`../results/sram_20260915_023952_987997/result.json`
- 写前读回：P14 `0x00005610`；SRAM 写入通过；写后读回 `0x0000C706`；三步均通过。
- `fpga_flash_written` 为 `false`，本轮未写 Flash。

P14 位流和 P10 位流及其结果目录均保留，可直接作为 SRAM 回退依据。

## 实体验收边界

请在当前 P16 SRAM 上确认：

1. 按住同一 Push pad 改变压力，声音随压力连续改变，不重触发、不串到别的声部；松开仍按原逻辑释放。
2. Push 屏幕上的 pad 状态、模式/音色/效果卡片、数值和箭头随交互更新，灯光保持正常。
3. HDMI waveform、李萨如图、频谱图、效果卡片顺序/箭头/动画保持正常。
4. C 模式多键声音、P10 串行效果链、P2 低音和耳机输出保持正常。

真实屏幕、Push、耳机和交互延迟以用户本次验收为准；RTL、数字回读和 P&R 报告不代替这些项目。
