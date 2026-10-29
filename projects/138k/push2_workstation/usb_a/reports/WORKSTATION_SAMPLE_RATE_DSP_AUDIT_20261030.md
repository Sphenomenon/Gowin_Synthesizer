# 运行时采样率切换：固定 rev2 DSP 审计

日期：2026-10-30（Asia/Shanghai）。本报告只读核对固定 `3d4b3175d0f20d0b787b61b43e4543739b26bca1` 的实际启用输入及综合网表。**当前完整工作站仍只实现 48 kHz；把参数改成 44100 或分别生成两个静态位流，都不能满足同一位流中的运行时切换。** 下文接口与系数适配属于实施建议，未写入候选。

机器记录：[sample_rate_dsp_audit.json](workstation_task_20261030/sample_rate_dsp_audit.json)。综合身份见 [F02 综合报告](WORKSTATION_F02_SYNTHESIS_20261030.md)。本审计未修改 DSP、冻结表、候选源码或约束，未执行板卡操作。

## 1. 来源与实际生效层次

候选为 `/Users/sphenicidition/.cache/gw138k-task-20261030/clean-rev2-profile-candidate`，profile revision 2、身份 `custom138k-workstation-v1-f5b723250388add5`。其 integration_inputs SHA256 为 `10deb0aa1cd172838c98b1f8d675b0ae41b812641549ba3bde432b355caabd2b`，综合网表 SHA256 为 `27b30ac791323f05dc68cd5d9ea6ccaaf14d6a122c5fe2b978cb4714b7fdcf18`。已按 profile 清单重验所选 38 项 staged 输入哈希，并核对全部 230 个启用输入及 legacy include 闭包。

下文源文件路径均相对于该候选的 `workstation/Prj1`，不是正在修改的活动目录副本。`legacy_audio.sv` 实际编译 `legacy/rtl/audio/*`；不能仅查看活动 `rtl/audio` 同名文件。综合网表确认以下实例仍存在：

| 实际实例（省略公共前缀） | 模块／作用 |
|---|---|
| `u_managed/u_audio/u_workstation/pitch` | `pitch_expression`，滑音／弯音／LFO |
| 同上 `/engine` | `unified_oscillator_engine`，含 MIDI step、分音 ratio、五音色 gain ROM |
| 同上 `/vector_engine` | `scope_vec_engine`，另有 48 kHz note step ROM |
| 同上 `/effects/chorus_stage` | `serial_chorus_effect` |
| 同上 `/effects/reverb_stage` | `serial_spatial_reverb` |
| `u_music/u_basic_pitch/u_frontend` | `basic_pitch_cqt_frontend` |
| `u_video/u_renderer/g_analysis.u_analysis` | `output_audio_analysis`，实际 2048 点 FFT |

旧 `spectrum_fft256` 虽由 include 编译，输出在当前 wrapper 未使用，综合网表中已被优化掉。旧 `audio_workstation` 定义也被编译，但实际工作站是 `gw138k_event_workstation`。不能用这些被清除的实现证明当前实时链路。

`src/ae350/gw138k_controlled_adapter.sv:110` 固定 `SAMPLE_RATE_HZ(48000)`；`:155` 的 PT8211 `BCK_HALF_CYCLES(25)` 产生每帧 1600 个 76.8 MHz clocks。`src/ae350/gw138k_event_workstation.sv:57` 对非 48000 参数直接 `$fatal`。现有 `sample_ce_i`／`sample_ready_o` 及 frame join 没有运行时 rate／generation 字段；18-bit MIDI 事件也没有隐含的该类元数据。

## 2. DDS、五音色及持音

主引擎 `legacy/rtl/audio/unified_oscillator_engine.sv:122,282` 用整数 `RATE_SCALE=192000/SAMPLE_RATE_HZ` 缩放 canonical 192 kHz MIDI 表。48000 和 44100 的整数商都为 4，因此单改参数会把 A4 从 439.999983 Hz 降至 404.249984 Hz，低约 146.707 cents。矢量引擎独立表的 A4 48 kHz step 为 39370534，主引擎为 39370532；44.1 kHz 的理想 A4 step 为 42852281。两个原有舍入结果都应被 48 kHz 回归保留。

五音色的 gain 与分音 ratio 为无量纲数据，可保留。当前 `1932735283≈0.45×2^32` 防混叠阈值应作用于**最终每帧有效 step**。高音／高分音在 44.1 kHz 可能越界，反切回 48 kHz 后应恢复原来的有效分音，不能因为一次越界永久写零 slot gain。

`slot_mem` 的 `[79:48]` 是相位、`[47:16]` 是已缓存的基础 step、`[15:0]` 是 gain；step 在 NoteOn 载入。只换 ROM 或采样率参数不会更新已持有声部。建议保留现有 canonical 48 kHz step 与相位，在已有 per-frame pitch 乘法中合并 unity／`160/147` rate factor，使用足够精度、明确舍入与溢出策略。切换不重发 NoteOn、不重分配声部、不重启包络。

追溯限制：固定克隆未找到受 Git 跟踪的 stage13 MIDI／ADSR／ratio 或 stage15 gain 表生成器，已有冻结表和 baseline 来源可核验。实施时不能转向私有历史生成器补齐来源。

## 3. ADSR、滑音与 LFO

主引擎的 ADSR step 对原 192 kHz 表乘 4；矢量引擎直接使用同一原始表。当前不同语义必须在本次适配中保留，不能顺便把矢量包络改成主引擎时长。

| 音色 | 主引擎当前 attack | 矢量当前 attack |
|---|---:|---:|
| flute | 45 ms | 180 ms |
| strings | 35 ms | 139.979 ms |
| brass | 12 ms | 48 ms |
| marimba | 2 ms | 8 ms |
| piano | 3 ms | 12.021 ms |

最低改动是保留每声部 envelope level／state 及各自 canonical 48 kHz step，在 44.1 kHz 按 `160/147` 缩放每帧 attack／decay／release 增量。Sustain level 本身不依赖 Fs。声部没有足够可靠的原 profile 身份供简单换表后重载，运行时缩放可避免破坏已有持音。

`legacy/rtl/audio/pitch_expression.sv:11,36` 的 5 Hz LFO step 是 elaboration-time 常量，应保留相位并选择运行时 step。`rtl/control/workstation_parameters.sv:128` 仍是滑音参数权威：CC5=0 关闭，否则每帧 `256−2×CC5`；改采样率需缩放 delta，以保留物理滑音时长。矢量 gain／morph／scale 的固定 256/frame slew 同样受 Fs 影响。弯音比例、波形几何不应随 Fs 改变。

## 4. Delay、Chorus、Reverb 与历史作废

当前有效 Delay 是 DDR 实现。音频消费者和 `delay_ddr_dma` 的环形位置计算都依赖 `ECHO_SAMPLES`，整机固定为 9600（200 ms）；44.1 kHz 对应 8820。两个端点必须在同一个已确认事务中变更，不能让 DMA 和消费者分别提交。现有 65-bit FIFO 的 marker 表示有序 flush，不是通用 stream generation；需扩展配置／generation 确认、导出 flush completion，并处理旧 outstanding read 返回。

| 量 | 当前 48 kHz | 44.1 kHz 候选 |
|---|---:|---:|
| Delay samples | 9600 | 8820 |
| Chorus base | 480 | 441 |
| Chorus depth | 96 | 88（目标 88.2，量化待验证） |
| Chorus 24-bit LFO step | 349 | 380（nearest） |
| Reverb FDN lengths | 1429／1789／1999／2131 | 1313／1644／1837／1958（仅缩放草案） |

Chorus 当前 LFO 为约 0.998497 Hz，运行时应保留 LFO phase。Reverb 的 early-reflection 表由 `tools/generate_room_preset.py` 按 48000 生成，需版本化两组 rate 数据。FDN nearest 长度还未做互素性、频响、稳定性与 T60 验证，不能直接作为验收系数。若物理环路时长保持，7/8 的 per-traversal loop loss 可保留；当前每帧 0.5 damping pole 的等效 44.1 kHz 值约 0.470271，也需定点及听感验证。

建议使用原 48 kHz 最大容量的 RAM，以运行时 wrap／tap／coefficient bank 改变有效长度，不复制完整效果工程。受控静音期间清除 Delay／Chorus／Reverb 历史、作废旧 PCM 和 DDR 读请求，但保留声部分配、相位、包络、held/deferred notes、压力、延音及公共参数。现有 PANIC／reset 会清声部，不能直接拿来当 rate-history clear；应增加专用 frame-cancel／history-clear 及完成确认，原 PANIC 语义保持。

## 5. FFT 与 CNN 的速率含义不同

实际显示分析为 2048 点。Hann／twiddle 只依赖变换长度，可以复用；受 Git 跟踪的 `projects/138k/ae350/scripts/generate_fft2048_rom.py` 已重新生成核对，ROM 和 bin-to-column 映射与 staged 字节一致。Fs=48 kHz 时 bin 间隔 23.4375 Hz，现有 bin 2..853 对应 46.875..19992.1875 Hz；44.1 kHz 时变成 21.533203125 Hz/bin，旧 bin 853 仅为 18367.822266 Hz。需要把真实 Fs 绑定到频率标签、映射与快照元数据，不能继续标为原来的频率范围。

切换需中止未完成的 capture／FFT，并拒收旧 generation 结果。`DISPLAY_DATA_LAYOUT_V1` 固定 48000，需显式版本／capability 处理；不能无声明地改变 v1 含义。

CNN 当前输入是 TF 解码后的文件 PCM／file sample_rate，不是最终 DAC PCM tap。`basic_pitch_workstation_link` 将 48 kHz 直通、44.1 kHz 经 analyzer-only `160/147` nearest-sample repeat converter 后送入固定 `147/320` polyphase frontend，得到 22050 Hz CQT／模型输入。不能只改 `BP_SRC_SR`，也不能把该分析适配器当作最终音频的高质量 SRC。

最低改动可保留现有前端结构，在文件／实时输入速率变化时 restart，并以 generation fence 和 DDR pending-response 保护旧窗口／模型任务。另一个方案是直接为 44.1→22.05 kHz 提供 1/2 滤波前端，但需新系数来源、可复现生成器、golden-vector 和识别精度回归。头文件提到的 `music/export_basic_pitch_fixed.py` 与 `models/basic_pitch_onnx_manifest.json` 不在固定克隆 tracked 文件内；现有 `resampler_poly.mem` 受跟踪。未补齐来源前，不改变 coefficient geometry。

## 6. 其他时间基准、deadline 与时钟差

TF NCO 的 `RATE_MUL=916260` 与 76.8 MHz 时钟绑定，若切换 compute clock，必须重算并定义文件 Fs 与输出 Fs 不同时采用 SRC 或受控切换。`scope_control_player` 的 cue 是 canonical 48 kHz sample timestamp；运行时应按 `48000/currentFs` 推进，或显式版本化时间单位，否则 44.1 kHz 会把时序拉长约 8.8435%。关闭后的录音应保留录制时 Fs 元数据。

| 调度方案 | 每帧预算 | 当前证明范围 |
|---|---:|---|
| 当前 76.8 MHz／48 kHz | 1600 clocks，20.833333 µs | rev2 固定接口 |
| 70.56 MHz／44.1 kHz | 1600 clocks，22.675737 µs | 算术候选，未集成／约束 |
| 76.8 MHz／44.1 kHz | 1741.496599 clocks | 需 output-paced 1741／1742 调度，当前 PT8211 不支持 |

本次**没有新测得 rev2 全功能 worst-case 渲染 latency**。`scope_vec/VERIFICATION.md` 的 1067/1600 clocks、余 533 clocks（6.940104 µs）属于 2026-09-30 的不同源码／配置，既不是当前整机证明，也不是 44.1 kHz 证明。当前综合的 audio Fmax 估计仅 60.489 MHz；本轮固定候选 routed STA 的 audio 仅 72.236 MHz < 76.8 MHz，且整机 setup −1.867 ns、hold −0.910 ns；完整结果见 [F02 P&R 报告](WORKSTATION_F02_PHYSICAL_20261030.md)。该结果仍不是逐帧算法 latency 测量，不能以名义分频证明 deadline。

FPC 实际从独立 12.288 MHz 参考按 /256 串行输出，消费 49-bit latest-value mailbox；无新数据时最多保持 16 帧。这不是永久速率转换。48 kHz producer 对 44.1 kHz consumer 每秒差 3900 帧，512-frame FIFO 约 131.282 ms 就耗尽全部漂移容量，448-frame 可用容量约 114.872 ms。FIFO 只能承受有界突发，不能消除永久频差。

实际参考钟 ppm 差本轮未测。通式为 `Δframes/s=Fs×(producer_relative_error−consumer_relative_error)`；例如相对差 100 ppm 时，48 kHz 下差 4.8 frames/s，512-frame 理想容量约 106.667 s，此例不是板测。需规定同步／速率匹配方法、bounded stall、溢出／欠载与故障行为。

## 7. 最小运行时提交合同与实施门槛

由一个 always-on 事务拥有 requested／applied rate 和 stream generation，沿现有公共参数权威提交，向 DSP、效果、分析、serializer 发不可变 pending config，收集确认后只在完整帧边界静音应用一次。控制与超时不能依赖被停掉的时钟。跨域 metadata 另设契约，不改写现有 18-bit MIDI layout。

必须保留的状态是公共参数、held/deferred notes、声部分配、相位、包络 level/state、力度／压力、音色、滑音位置和 LFO phase。必须作废的是旧 generation 的 rendered／serial pending PCM、frame join flags、效果历史与旧 DDR 读、partial FFT／CQT／resampler window 和异步结果。

实施后的最低验收包括：

1. 48 kHz 全 A/B/C、五音色和效果组合 bit-equivalence；保持原本主／矢量差异。
2. 同一位流 48→44.1→48 切换，含持音、压力、延音、滑音、release、近 Nyquist 分音；检查音高／物理包络时间及反切恢复。
3. 不产生半个串行帧、旧 generation 输出或重触发；Delay outstanding return、拥塞、overflow／underflow／timeout 均有界并可观察。
4. 两个 rate 的完整 worst-case frame latency 与实际 clocks 下 routed STA、CDC、PLL；测量独立参考钟误差，证明持续流速率匹配。
5. 效果 delay／T60／damping／LFO 的定量与听感结果，FFT Fs metadata／窗口 fence，CNN golden inputs／识别精度。

审计状态：source audit 完成；运行时 rate support 未实现；当前候选未改；未以双静态构建代替运行时支持；未做硬件验收。
