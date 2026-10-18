# P14 C 模式 32 声部候选

状态：C 模式 32 声部 overlay 已完成 RTL、综合/布局布线和 SRAM 下载；实体 HDMI、Push、耳机与交互回归等待验收。P13 的共享 DDR 显示数据、HDMI reader、Push 摘要、P10 串行效果链和 P2 低音逻辑保留。

## 改动范围

- `rtl/audio/unified_oscillator_engine.sv` 是当前 P13 引擎的局部 overlay：slot RAM 从 128×80 bit 扩为 1024×80 bit，slot/issue/读写地址统一为 10 bit；C 模式按 `slot_read_index[9:5]` 映射 32 个声部。
- `rtl/audio/gw138k_event_workstation.sv` 的满载判断改为检查完整 32 位 `allocated`。没有改变 Push USB-A 帧格式、MIDI 事件 FIFO、显示协议或效果链接口。
- `build.py` 只把上述两个 overlay 注入新的结果目录；P10/P13 冻结输入和旧结果目录未修改。

## RTL 仿真

结果目录：`results/c_mode_rtl_20260915_015045_799805008/`，其中 `simulation.log` 为最终运行记录。

`tb_unified_mode2_32.sv` 在 C 模式发送 32 个 NOTE_ON，检查 `allocated_mask=32'hffff_ffff`、`active_voice_count=32`，再发起一次 sample CE，统计完整 slot 扫描和结果返回：

- 32 个声部均被分配；
- `slot_read_valid` 扫描正好 1024 项，并命中最后 slot；
- sample result 返回延迟 1035 个 76.8 MHz 音频周期，低于 48 kHz 的 1600-cycle 周期预算；
- 未修改 Push/HDMI/DDR 协议。此测试是 RTL/ROM 模型，不是实体声音验收。

## 综合、布局布线与资源

构建目录：`results/build_20260915_013412_963961`，器件 `GW5AST-LV138PG484AC2/I1`。

| 项目 | 结果 |
|---|---:|
| setup 违例端点 | 0 |
| hold 违例端点 | 0 |
| 最差已报告 slack | +0.023 ns |
| Logic | 33,781 |
| Register | 24,931 |
| BSRAM | 253 |
| DSP | 42.5 |

旧完整 `check_build.py` 审计结果保留在 `results/build_20260915_013412_963961/Prj1/check_build.log`：仍是既有 DDR 历史证据路径缺失，以及 `u_managed/effect_mask_sync_[0..2]_s0/RESET` stopped-clock 覆盖缺口；没有将这些缺口写成通过。

## SRAM

- 位流：`results/build_20260915_013412_963961/Prj1/impl/pnr/Prj1.fs`
- SHA256：`5249dc938d6288e87a2e5ca2ae3ce21808a3c11671b3b47f38b767754a869a86`
- UserCode：`0x00005610`
- 下载记录：`../results/sram_20260915_014828_863405/result.json`
- 写前 UserCode：`0x0000F002`（P13）；写入与写后读回均通过；Flash 未写。

P13 位流和 P10 位流仍保留，可作为 SRAM 回退版本。

## 实体验收边界

请分别确认 HDMI waveform、李萨如图、频谱图、效果卡片顺序/箭头/动画；Push 屏幕与灯光；耳机声音、P10 串行效果链、P2 低音；以及 32 声部同时按下时的声音和交互延迟。RTL、数字回读或 P&R 报告不代替这些实体验收。
