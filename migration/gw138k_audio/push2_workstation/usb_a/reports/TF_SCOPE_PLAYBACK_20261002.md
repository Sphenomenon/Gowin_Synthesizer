# 2026-10-02 TF 播放入口与李萨如示波器音乐

软件与离线验证已完成；TF 实际复制、P&R/时序闭合、候选下载和板上按键/耳机/HDMI 验收尚未完成。板被另一会话占用，本次没有 programmer、SRAM/Flash、UserCode 或 git commit 操作。

## 完整 workstation 候选

构建：`results/build_20261002_173227_640023/Prj1`，顶层 `gw138k_push_workstation_top`，WAV profile。Gowin exit 0，所有综合输入文件未被工具改动。综合 **234/340 BSRAM**，剩余 106，与前次 Basic Pitch + scope 完整候选相同；该数包含 TF SPI/FAT/DDR/WAV、Basic Pitch、矢量 voice、P10 效果、USB/Push、HDMI/display-data 和 AE350。不是独立 TF 核的数，也不是 P&R 实测。详见同构建 `workstation_memory.json` / `.md`。

## 信号路径

```text
TF FAT16/FAT32 根目录 → DDR 音频环形双 bank → WAV PCM16 stereo
  → PCM CDC FIFO → 可变采样率 PT8211 serializer → 帧边界 DAC selector
  → 真实 hp_bck / hp_ws / hp_din → final PT8211 observer → 32-bit pair CDC
  → 既有 HDMI display-data → 李萨如 L=X / R=Y
```

先前 TF `track_index` 固定 0，HDMI 只观察合成器自己的 PT8211 serializer，分析页的几何投影又是 mid/side。现在在最终 DAC 选择之后采样左右声道，每次配对后经 acknowledged CDC 发布；切源期间 observer 清零，不把半帧送进分析器。原有 display-data/DDR/渲染架构保持，分析器增加 `XY_DIRECT` 参数（默认 0 保留旧接口），工作站 renderer 选 1，直接 L 作 X、R 作 Y（Y 正值向屏幕上方）。只改采样入口与投影，不另建显示通路。

`scope_tf_control.sv` 在音频域消费已经被 workstation 接受的 CC，保存模式、run、零起始 track 和 restart epoch。32-bit 状态定期通过 CDC 重传；50 MHz 只对 epoch 变化发 restart。暂停冻结 decoder 消费和 FIFO 读位置，serializer 持续送零；恢复沿用当前位置。手动接管标记防止退出 TF 模式后自动 monitor 又覆盖合成器。目录索引超出实际 `track_count` 时不访问未填充的 playlist RAM，bridge 的 unsupported 置位。

## Push 与 MIDI 入口

物理 CC 名称核对 Ableton 官方 `push-interface/doc/Push2-map.json`。按钮按下沿触发，松开不触发第二次。

| Push 键 | 物理 CC | workstation 逻辑事件 | 行为 |
|---|---:|---|---|
| Session | 51 | CC104=64 | 切入/退出 TF 示波器音乐；进入从头播放当前 track |
| New | 87 | CC105=64 | 暂停/继续；要求 TF 模式已进入 |
| Duplicate | 88 | CC105=127 | 当前 track 从头播放 |
| Left | 44 | CC108=0 | 前一首；禁止 0 下溢 |
| Right | 45 | CC108=127 | 后一首；禁止 15 上溢，实际目录数另由 TF 核校验 |
| Select | 48 | CC90=64 | 现场几何模式；成功进入时退出 TF 模式 |
| Stop / Stop Clip | 29 / 27 | CC120=0 | PANIC，TF 模式保留但音频静音，Duplicate 可重新播放 |

逻辑 MIDI 还支持 CC104=0/127 明确关闭/开启，CC105=0 暂停，CC106=0…15 直接选 track。其余 CC104/105 值与 CC106≥16 明确报错；控制 sticky error 位为 `tf_scope_control_o[15]` 并汇入 `scope_status_o[11]`。从现场合成切 TF 时要求两种合成 voice 均为零，避免遗留隐藏音符。TF 模式中的音符/压力不分配合成 voice；离开后再演奏。Play/Record 原有谱面/recorder 入口不改用作 TF 传输按钮。

控制字：`[31:16] restart epoch`、`[15] sticky control error`、`[14] manual source ownership`、`[13] run`、`[12] TF mode`、`[11:8] track`、`[7:0] reserved=0`。

TF 模式直达 DAC，不经合唱/延迟/混响或单声道叠加。几何模式继续使用默认精确干声和独立校准。外部 TF 文件播放是兼容演示；赛题实时合成展示必须用 Select/pad 的几何 voice，不能把预录 TF 文件算成实时合成或振荡器吞吐量。

## Basic Pitch 互斥

原 TF→Basic Pitch 会对 decoder 施加输入背压；这是原来整段识别验证的条件。TF 示波器音乐时关闭 recognition 的 PCM 输入和该背压，让 TF 以 DAC 采样率播放；模型/DDR 核仍在完整镜像中。若进入时打断了尚未完成的识别 capture，`music_capture_interrupted` 锁存，退出后不把两个不连续的 track 拼成一次识别输入。再次识别需系统复位并按既有流程重新上传模型。未打断/已完成的识别结果不受此锁存影响。

## 开源素材和卡

采用 `djmango/oscilloscope-music` MIT 原创源码的固定提交 `f1315f22b01a9baa9147c173ff00d3279212eff8`，原作可确定性生成。原始 stereo sum 含较大 DC 偏置；本机 adapter 在混音前关闭逐音符 dx/dy 定位，保留编排和音色，再左右共用 160/147 重采样和幅度余量转换到 48 kHz。不能把本机验证写成上游发行版/实体示波器已验收。

卡外目录：`/home/sphenicidition/Documents/oscilloscope_tf_assets_20261002`。待复制文件为 `OSCIMUS.WAV`、`OSCILIC.TXT`、`OSCISRC.TXT`；许可证与 SHA256 一并保留。曲目 105.6 秒、PCM16 stereo、48 kHz、20,275,244 bytes，SHA256 `bc4f84b199bc4360249bc494113430192fa19ad4d92a02c105ccbc08c22e48e7`。`XY_PREVIEW.png` 用最终 WAV 的 6 个 2048 点窗口作图，确认为两轴实际混音，不是分声部彩色视频。

素材生成/复制工具 `tools/tf_scope_media/media.py` 会拒绝仓库内 PCM 输出；卡目标必须是已挂载可移动 FAT 分区，保留既有文件，不格式化。当前 PC 未检测到 TF 读卡器，安装返回 `need exactly one mounted removable FAT16/FAT32 TF card; detected []`，所以没有实际写卡。

接入卡后，在 `usb_a` 执行 `python3 tools/tf_scope_media/media.py install`；见该工具 README。首测建议卡根目录无其他 WAV，此时曲目编号 0。多文件按 FAT 根目录扫描顺序而非文件名排序。复制成功后安全卸载；候选通过后续 P&R 和下载、卡插入 NEO Dock 后再用上述 Session/New/Duplicate 操作。板仍被占用时不得代做下载或启用模式。

## 离线验证

- `scope_merge_20261002_173443_694261`：5 TB 全通过。独立源切换跨 8/44.1/48/96 kHz，4231 synth + 152 TF stereo pair，最短 BCK 脉冲 12 audio 周期，无额外 rising edge，最长切换 28729 周期（76.8 MHz 下约 374.1 μs）。这些是安全串行帧边界数据，不声称任意波形切源的模拟听感绝无瞬态。
- 控制：13 个模式/暂停/恢复/restart/track/PANIC/越界/退出所有权断言通过。
- TF 入口：722 个最终 DAC→display stereo pair；暂停 77 帧全零，decoder cursor 不前进，恢复继续；NN ready=0 时 TF 模式仍推进。
- 投影：4 个 L/R 正负象限坐标验证通过，direct 路径没有混入 mid/side；默认 legacy 参数仍能复现原投影。
- coexist：vector 与 TF/analysis 共存，0 deadline miss，1683 analysis samples、782 vector frames、200 mute frames、775 XY observation frames。
- `scope_merge_20261002_174238_509020`：新增 actual TF reader 目录边界 TB，空目录/未填条目均拒绝，合法条目仍启动；3 个断言通过。只播种扫描后的目录 RAM，不声称验过物理卡 SPI。
- `results/scope_vec_sim_20261002_174019_783508`：原几何 5 TB 与编译器审计通过。voice 最坏 115 cycles / 完整 work帧 1067 cycles（预算 1600）；A4 实测 440.000004067 Hz。路径平滑移除 H13 的效果 A4 为 63.71 dB、MIDI95 为 62.90 dB。没有保存 PCM 样本文件。
- `scope_merge_20261002_174438_257096`：完整 workstation 实际事件接受入口验证，CC104/105/106、PANIC、live takeover 正确，TF 模式的 MIDI note 不分配隐藏 voice，最坏帧 1067 cycles。
- 同构建 `p27_controls_173723_664382`：Push/service/audio 原绑定回归通过。
- 同构建 `tf_wav_regression`：WAV PCM decoder、RIFF chunk parser、8/16/24/32-bit/mono/stereo/unsupported/backpressure formats 3 TB 通过；未生成 PCM 文件。

新 mode 不替代原 0x4D Basic Pitch 板测；本候选没有 P&R、时序闭合或实体声音/HDMI验收。
