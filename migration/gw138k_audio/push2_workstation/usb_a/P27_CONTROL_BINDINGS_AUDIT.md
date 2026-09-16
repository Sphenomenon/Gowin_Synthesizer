# P27 Push 控制绑定源码审计

2026-09-17：P26 实体通过后，本阶段只绑定既有曲谱、录音、模式、效果总开关和 PANIC 控制。当前稳定源仍由冻结工作站、USB-A overlay 和 `build.py` 的可复现阶段补丁组成；不修改原 Xilinx 工程、Mega_138K 队友工程、旧结果目录或旧位流。

## 现有路径

Push 2 的 USB-MIDI word 在 48 MHz `usb_clk` 域进入 `push2_midi_rx`。`push2_controls` 只在 CC 的非零按下沿产生一次映射事件，松开只清 `buttons[cc]`，因此适合 transport 类单次切换。事件经原异步 FIFO进入 76.8 MHz 音频域，再经过 `gw138k_three_event_arbiter` 与 AE350 APB、电脑串口和 G1 MIDI 的现有事件路径合并。消费者的 ready 仍受原事件寄存级、sample tick、声部装载/混音、模式提交和释放扫描背压控制；灯光与屏幕没有进入这条 ready 链。

曲谱和录音已经位于音频域 `gw138k_controlled_services`：录音为原 256 帧 PCM FIFO 的 enable/readout 服务；曲谱为原 256×64 bit cue RAM，数据只有绝对 48 kHz sample frame 和 32 bit LED mask。`score_led_player` 只改变 LED mask/running/done/frame，不生成统一音符事件，也不提供预录 PCM。AE350 APB 的装载、读出及错误语义保留。

A/B/C 模式和效果链已经由 `gw138k_event_workstation` 拥有。模式请求必须等待原 oscillator engine 的可提交条件；效果顺序和选择必须继续由音频核心维护。P23 PANIC 已固定为 CC120，并在音频域实际接受时清声部、held、释放扫描、处理流水线和效果尾音；CC123 仍是渐进 RELEASE。

## P27 映射与边界

| Push CC | P27 行为 | 事件路径 |
|---|---|---|
| 85 Play | 曲谱 start/stop toggle | 新 `kind=6, command=0`，经过原 FIFO/仲裁后由音频域服务接受 |
| 86 Record | 录音 enable toggle | 新 `kind=6, command=1`，经过同一路径 |
| 62 / 63 Page left/right | 循环切换前一个/后一个 A/B/C 模式 | 原 `kind=2` 控制事件，CC89 携带方向；仍由原模式提交状态机执行 |
| 28 Master | 效果总开关 | 原 `kind=2` 控制事件，CC88；关闭时保留选择与顺序，重新打开恢复 |
| 27 / 29 | 硬 PANIC | 保持 P23 的 CC120，不扩大 PANIC 清理范围 |

`kind=6` 只增加两个无音符的面板命令。AE350 写事件寄存器也可使用相同编码，合法性检查只接受 command 0/1。面板命令在 `gw138k_event_workstation` 实际消费后才产生一周期 pulse，因此不会绕过现有事件仲裁或越过尚未接受的音频事件。

曲谱状态、录音状态和 32 bit cue LED mask 从音频域以一次完整快照跨到 48 MHz USB 域。Push pad 的实际 held 灯优先于曲谱提示；曲谱只占前 32 个 pad 的提示层。屏幕保留原模式、音色、参数、路由、PANIC 和三效果显示，并增加 SCORE、RECORD、FX MASTER、MODE 左右状态行。HDMI 继续显示原统一分析页，不恢复 performance keyboard 页面。

## 不变项与验证范围

Push pad Note On/Off 去重、poly-aftertouch、P20 力度映射、32 声部分配、电脑长按、G1 MIDI、P23 PANIC、48 kHz 音频链、P10 串行效果顺序、PT8211、DDR、HDMI 三种分析图和公开 Push 屏幕协议保持不变。PANIC 不在本阶段额外停止曲谱或录音。

定向验证只覆盖按下沿/松开去重、五组绑定、曲谱 RAM/时间戳/LED mask 与 start/stop、录音 enable、模式循环、效果总开关恢复及既有 PANIC 编码；随后运行完整 CPU/USB/音频回归、P23 PANIC 回归、完整构建与 routed audit。完整 audit 若仍只缺 `effect_mask_sync_[0..2]_s0/RESET`，继续按旧缺口记录，不能写成通过。USB IN error 诊断仍为 `null`。
