# 示波器音乐引擎并入 Basic Pitch 完整工作站（2026-10-02）

合并候选为 `results/build_20261002_112428_408291/Prj1`，顶层 `gw138k_push_workstation_top`。Basic Pitch、TF/FAT、8 个矢量 voice、原合成器、USB/Push、P10、HDMI 与 AE350 在同一完整工程中展开。Gowin 综合和本文列出的功能回归通过；**本次仅离线综合，未 P&R 或上板，时序未闭合**。

前置基线来自另一会话的 `results/build_20261001_222442_709782` 和 `WORKSTATION_BASIC_PITCH_INTEGRATION_20261002.md`。该基线已有示波器算法文件，本次处理的是合并后的输出所有权、实际控制链路及并行回归，避免只把 RTL 文件放入工程却被 TF 音频覆盖。

## 输出和控制行为

`scope_status_o[8]` 从音频域工作站经 controlled adapter / USB-managed wrapper 直通到同一音频域的输出选择器，没有新增跨时钟使用。新增 `rtl/audio/scope_vec/scope_dac_select.sv` 只控制最终 DAC 引脚：

| 状态 | 耳机/DAC 来源 | TF → Basic Pitch |
|---|---|---|
| 示波器模式关闭，TF 有效 | TF decoder 的原采样率 DAC | 维持原识别握手/背压 |
| 示波器模式开启，有 pad/控制音符 | 实时矢量 X→L、Y→R，默认 P10 精确干声 | 继续接收原 TF PCM |
| 示波器模式开启，现场静音或无 voice | 实时合成路径的零/包络输出，不回落到 TF | 继续运行 |
| PANIC 后仍处于示波器模式 | cue/voice/效果清空后的现场静音 | 维持原识别状态 |
| 全部 voice 空闲后显式退出示波器 | 恢复 TF monitor；无 TF 时保留普通合成器 | 维持原识别状态 |

选择器先在旧 BCK 低电平时停止引脚转送，从目标帧的右声道 MSB 起点重新接入，使用 NS4263 active-high shutdown 保护两个完整目标帧。复位后也等待完整帧，避免复位释放产生额外 BCK 上升沿。它不停止 TF decoder、FIFO、扫描时钟或识别内存请求。数字仿真证明完整立体声和边沿约束；**功放开关的模拟瞬态仍需以后实体确认，不能由此宣称物理切换绝无爆音**。

原几何 ROM、ADSR、音高/弯音/颤音、力度、旋转、morph 和 X/Y 校准保持原实现。现场 Push Select（物理 CC48）映射到逻辑 CC90 的模式切换；Mute（CC60）映射 CC95；Layout（CC31）启动控制场景；旋钮 74–78 控制缩放、旋转、morph、目标图形和场景速度。支持通用 MIDI/CPU 的逻辑 CC。活动 voice 时拒绝模式切换，并保持 DAC 所有权；不会把尚未结束的音符丢到另一个引擎。

Basic Pitch 原有模型装载期间 PC UART 被隔离的限制保留，因此现场演奏以独立 Push/USB 事件链为主；没有把 `BPN1` 模型字节当作音符。当前识别输入仍是原来支持的 48 kHz WAV。45 秒 `scope_vec/data/scene.json` 是样本时间戳控制事件，不是音频；本次没有新增录音、媒体、音频 ROM 或自动播放场景。

## 混音帧调度修复

真实 USB-managed wrapper 并行测试发现：PANIC 可以在两个振荡器结果已经完成、效果帧尚未返回 valid 的间隙被接受。既有 PANIC 已清空 join 和效果状态，但没有清除 `pending/frame_inflight`。下一采样 tick 因上一帧被主动取消而误计一次 deadline miss。

本次只在 `gw138k_event_workstation.sv` 的帧调度边界增加 PANIC 取消状态清理。原 unified oscillator 和识别计算 RTL 没有改动。修改前的新测试记录了 PANIC 前 0、后 1；修改后的完整 USB 控制/8 voice/静音/PANIC 测试保留严格断言，结果为 0，没有放宽 deadline 检查。

## 与 Basic Pitch 基线的逐字节比较

新 staged 工程的 `rtl/music` 全部 **70 个源码/头文件/系数文件**与基线 staged 工程逐字节相同。TF bridge、共享 DDR arbiter、DDR 地址表、HDMI、音频分析 renderer、P10 效果 RTL及 6 个生产几何/控制表也相同。TF owner 4、识别 owner 5、模型上传 CRC、CQT 系数/信号锁存、识别背压及 UART 遥测维持原接入。

`tools/workstation_memory.py` 现在强制检查识别计算实例 `u_music/u_basic_pitch`、16-bit DDR port、矢量引擎、cue RAM 和最终输出选择器的实际综合层级；不能再用含有 “music” 名称的任意模块冒充识别核已展开。

## 综合资源

| 顶层直接子树 | SYN BSRAM |
|---|---:|
| USB Host | 34 |
| Push 链路 | 1 |
| 原合成器 + 矢量 voice/cue + P10 + 曲谱/recorder | 109 |
| TF capture/playback FIFO | 4 |
| Basic Pitch（Viterbi） | 6 |
| 共享 DDR 控制器 | 16 |
| HDMI / 音频分析 | 48 |
| AE350 boot | 16 |
| **完整工作站** | **234/340** |

SYN 余量 106。矢量引擎 9、控制 cue RAM 1；新的 DAC selector 0 BSRAM。与 Basic Pitch 合并基线的 SYN 234 相同。基线 P&R 的 278 是另一统计阶段，**不是这个新候选的 P&R 结果**。

当前 SYN 音频域估计 50.933 MHz，低于要求的 76.8 MHz；USB 估计 42.750 MHz，低于 48 MHz。没有依据功能仿真或基线的一次板测声明新候选时序闭合。

## 验证

所有路径相对 `usb_a/`，机器证据见配套 `SCOPE_VEC_BASIC_PITCH_MERGE_20261002.json`。

- 综合：新构建 `tool_result.json` 为 exit 0、输入哈希未变；`workstation_memory.json` 为完整 top、Basic Pitch/WAV/矢量/selector 实际展开。
- 原矢量 5 个 TB + 编译器/频谱检查：`results/scope_vec_sim_20261002_112529_894447/verification.json`。8 voice、ADSR、morph、校准、扫频与 L/R 干声成立；引擎 115 周期，完整音频 1067/1600 周期；440 Hz 误差 +0.000004067 Hz，MIDI95 的第 13 次谐波折叠峰抑制 62.898 dB。
- 新串行输出 TB：两个真实 serializer 的相位不对齐，覆盖 48/44.1/96/8 kHz。解码 4231 对合成器 L/R、152 对 TF L/R；没有 mux 生成的 BCK 上升沿，最短脉冲 12 音频时钟。最大所有权交接 28,729 周期，按 76.8 MHz 为约 374.08 µs（包含 8 kHz 两帧保护）。
- 新并行 TB：实际 USB-managed wrapper、真实 TF bridge/FIFO 和选择器；解码器使用 HDL 计数器测试端点，识别 sink 使用可控 ready。1683 个分析样本逐个检查顺序；8 voice 产生 782 个非零矢量帧；200 帧静音仍隔离 TF；775 个立体声观察帧；deadline 0。分析 backpressure 停止/恢复时，矢量演奏及静音继续成立。
- P10：精确旁路、单效果一次、6 种串联顺序、clear 恢复干声，656 帧通过。
- P27：Push、services、audio 三项通过。runner 补上了新增 `rtl/music` include 搜索路径；初次缺少头文件的失败日志保留，修复后重跑通过，没有通过排除识别源码隐藏解析错误。
- DDR：TF/识别 masked writes、owner 4/5 响应归属、scanout 优先与持续请求公平性、TF DMA、DDR 地址表通过。
- 资源负向检查：缺少 selector、缺少真实识别实例、层级资源矛盾、超出 340 块均明确失败。

新并行 TB 验证的是接入/调度边界，**没有重跑完整 CNN 数值或 172 帧识别，也没有重新上板验证模型 CRC/六层指纹**。原 0x4D 的板测证据继续保留在原报告；新候选不继承 `hardware_tested=true`。

## 复现与交付状态

```sh
python3 build.py --synthesis-only --no-update-latest
python3 sim/scope_vec/run.py results/build_20261002_112428_408291
python3 sim/scope_vec/run_merge.py results/build_20261002_112428_408291
python3 sim/p10/run.py results/build_20261002_112428_408291
python3 sim/p27/run.py results/build_20261002_112428_408291
```

需要重建时，后四条将路径换成第一条新打印的结果。新结果只保留几何/控制数据、模型系数、HDL/固件和验证产物，不存音频样本 dump 或媒体文件。历史共享工作目录中的其他音频文件仍由原任务拥有，本次没有删除它们，也不把全工作目录写成无音频。

最新离线工程指针在所有检查成功后发布；原 Basic Pitch 板测 baseline 的完整 JSON 另存于新构建内。没有执行 programmer、SRAM/Flash 操作、UserCode 分配或 `git commit`。
