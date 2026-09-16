# P25 频谱泄露路径审计

## 当前生产路径

P24 的音频 PLL 输出名义 76.8 MHz，`gw138k_event_workstation` 每 1600 个时钟产生一次 48 kHz 帧。合成、P10 串行效果链和响度校准完成后，`pt8211_tx` 把 32-bit 音频的高 16 bit 串行送到耳机 DAC；`pt8211_observer` 从同一 BCK/WS/DIN 恢复最终左右 16-bit PCM。显示 CDC 将 `{output_pcm, reference, voices, status}` 从音频域送到 50 MHz 域，频谱看到的就是 DAC 数据，而不是效果前旁路。

`output_audio_capture.v` 在 50 MHz source 域按 `sample_valid` 连续写 2048 个左右样本，双 bank 通过 toggle request/ack 交给 100 MHz 分析域。它没有零交叉或波形触发，不按 MIDI revision 重启；bank 暂时不可交付时累计 skipped，不向音频回压。`output_audio_analysis.v` 对左右声道分别执行 2048 点 radix-2 FFT，输入先乘 2048 点周期 Hann，每级除二并保留 6 个小数保护位。正频率 bin 2…853，即 46.875…19992.1875 Hz，按对数频率映射到 512 列，同列取峰；显示标尺约覆盖 84.3 dB。当前 bin 间距为 23.4375 Hz，Hann 主瓣零点到零点为 4 bins，即 93.75 Hz。

FFT 一块采样约 42.667 ms，运算最长 232714 个 100 MHz 周期，约 2.327 ms。完成结果在 renderer 帧边界换 bank，再经版本化 DDR writer/reader供 HDMI；FFT、DDR 和 HDMI 都不能阻塞音频。波形图使用另一个 `feedback_capture` 平滑触发器，不能把其触发行为归到频谱。Push 只读取共享摘要，不复制 FFT payload；本实验不改变三种分析图。

## 五个假设的隔离方法

| 假设 | 固定项 | 唯一变化 | 判据 |
|---|---|---|---|
| 采样率 | 同一 2048 点数字向量、Hann、FFT | 48 kHz 与旧 48.828125 kHz 标签 | 幅度 bin 是否变化 |
| 窗函数 | 48 kHz、MIDI 60、N=2048、相位 0 | 矩形/周期 Hann | ±2 bin 外功率、最大远端 bin、−84 dBc 可见 bin |
| 捕获相位 | 48 kHz、MIDI 60、N=2048、周期 Hann | 64 个等间隔起始相位 | 上述泄露量的范围 |
| FFT 点数 | 同一稳态正弦、48 kHz、周期 Hann | 512/1024/2048/4096/8192 | bin 间距、主瓣 Hz 宽度和分数 bin 偏移 |
| PANIC 残留 | P24 完整 allocator、振荡器、三效果器 | 稳态、跨 PANIC 块、首个完整 PANIC 后块 | 左右 PCM 是否仍非零；宽带是否只出现在跨界块 |

真实生产音色另外读取 P24 同音符、同力度、效果关闭的十五组 8192 点输出，先按 PT8211 规则截为最终 16-bit DAC PCM，再测每组首个 2048 点块。模式引擎最多 32 个整数谐波，因此分别以 1…32 倍 MIDI 60 为中心保留每个 Hann 主瓣 ±2 bins，统计其外功率；这一步把真实谐波与窗旁瓣分开。

## 时钟、队列、背压和 PANIC

- 音频生成与 DAC observer 在 76.8 MHz 音频域，采样帧为 48 kHz；显示 tuple 到 50 MHz，FFT/分析在 100 MHz，DDR UI 为 100 MHz，HDMI 扫描域保持原设计。
- 频谱捕获的所有权队列只有两个 PCM bank 和两个显示结果 bank。FFT 不能及时释放时丢弃后续观察样本并计 skipped，不会拖慢合成、耳机 DAC 或事件队列。
- PANIC 在音频域接受 CC120 后清声部、包络可达状态和效果历史长度/指针。频谱捕获 bank 不因 PANIC 清空，因此 PANIC 落在块中间时，该块合法地含有 PANIC 前声音与 PANIC 后零值；这属于有限窗硬截断，不是持续声部或效果残留。
- Push pad held、poly-aftertouch、电脑重复、MIDI 仲裁、声部分配和 P10 效果顺序均不在实验中修改。

本轮没有处理 `effect_mask_sync_[0..2]_s0/RESET` 的旧 routed audit 缺口，不能把它记为通过；USB IN error 诊断仍为 `null`。
