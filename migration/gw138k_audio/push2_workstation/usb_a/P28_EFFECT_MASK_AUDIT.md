# P28 效果状态跨时钟审计修复

2026-09-18：本阶段只收口从旧版本延续下来的 `effect_mask_sync_[0..2]_s0/RESET` routed audit 缺口。音频效果选择来自 76.8 MHz 音频域，三位状态只供 50 MHz 显示域显示；它不承载音频事件，也不参与效果处理、声部分配、USB 队列或背压。

## 原因

旧实现用异步输入复位两级效果状态镜像，并在 SDC 中把六个寄存器的 `RESET` 端点设为 false path。功能仿真能工作，但完整路由审计无法证明这些跨域复位端点，因此历代版本都必须把 audit 记为失败。

P28 保留原来的两级数据同步，只取消这组显示镜像的运行时复位。`effect_mask_meta` 和 `effect_mask_sync` 都以 0 初始化，音频域复位后的零值会通过正常数据路径传播到显示域。源采样网络带 `syn_keep`，六个寄存器带 `syn_preserve`，避免综合器把三位效果数据重新映射到 DFF 的复位脚。原 SDC false path 同时删除。

## 路由后证明

`audit.py` 直接检查最终 `Prj1.vo` 和时序约束：

- 三个 meta 和三个 sync 寄存器全部为 50 MHz `DFFCE`；
- `INIT=0`、CE 固定为高、CLEAR 固定为低，没有 RESET 或 PRESET；
- 每个 sync 的 D 都由对应 meta 的 Q 驱动；
- SDC 中不再存在针对该链 RESET/CLEAR 的 false path；
- 把第二级 D 人为改错后，负向变异检查会拒绝该网表。

完整 audit 还暴露了一个已经过时的 HDMI 检查：旧检查要求已经被 P5 统一分析页取代的 `composite_active` 和 `analysis_base` 寄存器。P28 没有为通过检查而保留常量逻辑，而是改为证明当前真实结构：源码固定选择 RTL 分析页，路由网表中选定的分析 bank 进入逐帧保持寄存器，波形、频谱和图像三条 reader 路径都存在。

## 保持不变

Push pad 按住逻辑、poly-aftertouch、P20 力度映射、32 声部分配、电脑键盘连击、通用 MIDI、P23 PANIC、HDMI 输出、耳机、48 kHz 音频链和 P10 串行效果顺序均未改动。效果 mask 的所有者仍在音频域，P28 只改变显示镜像的复位实现和对应审计。

USB IN error 诊断仍为 `null`，不在本阶段顺带扩展。板上已经下载 P28，但实体回归尚待用户确认。
