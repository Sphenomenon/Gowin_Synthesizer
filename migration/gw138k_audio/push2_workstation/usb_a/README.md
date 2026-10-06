# Push 2 USB-A 与完整音频工作站合并

## 2026-10-06 完整 0x83 工作站与示波器入口合并（离线候选）

最新已验收镜像是 `cnn83-accepted-20261006` 的完整 0x83：Basic Pitch 分层缓存、TF 歌曲菜单/热插拔/整曲指引、P10 delay DDR 均已保留，**PNR BSRAM 260/340**。下面 10 月 1 日的 **228** 是旧完整工程的 SYN 数，包含 TF 直读，但当时没有展开 Basic Pitch，不能用作当前占用。

本次在该完整工程上接回现场几何 voice 与 TF 示波器播放入口。TF 模式下歌曲菜单直接启动播放，无需 CNN 模型；左右键和重播作用于实际选中的曲目，暂停输出零并保持读取位置，拔卡后等待目录重扫、恢复同曲。最终 DAC 的 L/R、触发参考、voice 与健康状态作为同一帧发布给既有 display-data，李萨如用 L=X/R=Y。新候选的资源、验证及边界见 [合并记录](reports/SCOPE_WORKSTATION_MERGE_20261006.md)。板上已验收记录继续保留；新候选单独记在 `LATEST_WORKSTATION.json.offline_candidate`。

从 `usb_a` 使用当前完整工程入口：

```sh
python3 build.py --current-workstation --prepare-only
python3 build.py --current-workstation --synthesis-only
python3 sim/scope_vec/run_current.py results/<本次 workstation_scope83 目录>
```

该入口复用本机已经验收并有 SHA256 清单的 `results/song_guide_full83_20261006_203125_607466/Prj1`；缺失或漂移会明确失败。它仅允许 WAV profile 的准备/综合，拒绝 UserCode、P&R 和复用旧综合网表。下方不带 `--current-workstation` 的 `build.py` 命令保留为历史构建入口，不保证包含 0x83 缓存和地址隔离。

Session 切 TF 示波器模式；Play 打开/关闭原歌曲菜单，菜单内 Left/Right 浏览、Select 确认，菜单外 Left/Right 切实际播放曲目、Select 切现场几何。New 暂停/继续，Duplicate 重播当前曲目。外部预录 TF 播放与参赛现场几何实时合成分别使用，不计入实时矢量振荡器吞吐量。

## 2026-10-03 TF 曲目清单与 Push 2 指引

TF 直读核已提取 FAT16/FAT32 根目录中的 8.3 短文件名（最多 16 首）。Play 打开 Push 2 歌曲清单，Left/Right 浏览，Select 选曲并启动 TF→CNN；演奏页显示曲名和进度，按对当前亮起的 pad 才推进。合成器发声与三种效果仍可用。0x58 已上板，模型和 Push USB/屏幕传输工作；实体选曲与进度效果仍待确认，模型上传也出现过一次 DDR 回读 CRC 失败。详见 [实现与板测边界](reports/TF_PUSH_SONG_SELECTION_20261003.md)。

## 2026-10-02 TF 示波器音乐播放入口（离线候选）

Session 切 TF 模式，New 暂停/继续，Duplicate 从头播放，Left/Right 切曲；Select 保留现场几何 voice 入口。HDMI 改为采集最终 DAC 左右声道并使用直接 X-Y 投影，覆盖 TF 和合成器两个输出源。TF 模式不受 Basic Pitch PCM 背压影响，退出不自动被 TF monitor 重新覆盖。完整综合仍为 **234/340 BSRAM**，接入、原控制与 WAV 回归通过；未 P&R/下载/板测。开源 MIT 曲目已在仓库外生成并校验，当前未检测到读卡器，因此尚未实际写入 TF。详见 [播放入口与验证](reports/TF_SCOPE_PLAYBACK_20261002.md) 和 [卡外素材/复制工具](tools/tf_scope_media/README.md)。

## 2026-10-02 Basic Pitch 与示波器音乐引擎合并（离线候选）

以 Basic Pitch 已合入的完整 workstation 为基线，补齐示波器模式的 DAC 输出优先权：现场 X→L/Y→R、静音和 PANIC 不再被 TF monitor 覆盖，TF→识别继续运行。帧边界切换使用功放 shutdown 保护；修复 PANIC 取消效果帧后遗留的 inflight 状态。完整综合 **234/340 BSRAM**，与识别合并基线相同；矢量原有 5 个 TB、新增 2 个并行/串行 TB、P10/P27 和 DDR 回归通过。新候选未 P&R、未上板且时序未闭合，不能沿用原 0x4D 板测结论。见 [本次合并及验证](reports/SCOPE_VEC_BASIC_PITCH_MERGE_20261002.md) 和 [原 Basic Pitch 接入记录](reports/WORKSTATION_BASIC_PITCH_INTEGRATION_20261002.md)。

## 2026-10-01 BSRAM 优化汇总与最新离线工作站

`git pull --ff-only` 已完成，远端 main 没有新提交。已检查另一会话 9 月 30 日的 CNN/CQT 全 DDR 优化：独立识别镜像 P&R 43 BSRAM（SYN 23），当时其识别核尚未接入完整工作站，不能作为工作站节省数。该次完整工作站综合为 **228/340 BSRAM**，包括 TF WAV/FAT/SPI、DDR 双 bank、矢量引擎、USB、HDMI、AE350 和 P10 效果；回归通过，尚未 P&R、闭合时序或上板。资源层级、适用范围与接入冲突见 [优化汇总](reports/WORKSTATION_BSRAM_REVIEW_20261001.md)。

`build.py` 现于成功构建后强制生成 `workstation_memory.json`，只在完整顶层资源审计通过后更新 latest。`LATEST_WORKSTATION.json` 明确区分离线 SYN 候选与硬件验证状态。

## 2026-09-30 矢量示波器音乐引擎（离线候选）

8 voice 几何波表、默认 X→L/Y→R 精确干声、SVG/参数方程编译器与 45 秒控制场景已接入 `build.py`。5 个独立 TB、P10/P27 回归和 Gowin 综合通过；没有上板、P&R 或 UserCode 分配。扫描率限制 2000 Hz，SYN 时序仍待后续闭合。入口、映射、审计与定量证据见 [矢量引擎说明](rtl/audio/scope_vec/README.md) 和 [验证记录](rtl/audio/scope_vec/VERIFICATION.md)。


## 2026-09-28 TF/FAT 音频、动态 DDR 双 bank 与地址表整合

当前 workstation 已纳入自包含的 micro-SD FAT16/FAT32 reader、WAV/MP3/FLAC decoder 和两个 64 MiB 音频 DDR bank。超过 128 MiB 的文件采用读后释放、动态回收的环形流，不以 128 MiB 静默回绕；32-bit 文件计数达到极限会明确报错。TF 产生有效 PCM 时才接管耳机，断流后自动回到原合成器。构建一次只展开一种 decoder：`build.py --tf-audio-kind wav|mp3|flac`。

视频、display-data、AE350 UI、音频、未来神经网络池和 BSRAM bulk 迁移池现由同一份 1 GiB DDR 地址表约束；完整地址、状态机、格式边界、验证命令和后续分配规则见 [TF 音频与 DDR 整合说明](TF_AUDIO_DDR_INTEGRATION.md)。本阶段不烧录上板。

## P30 A/B/C 响度 1.5 倍（源码已改，等待用户 IDE 构建）

A/B/C 的最终 PCM 统一乘以 `3/2`，保留音色谐波比例和 P24 的模式平衡，再沿用原有 32 位限幅。源码改动、准备工程命令和 Gowin IDE 综合、布局布线、位流生成、SRAM 下载步骤见 [P30 操作记录](P30_ABC_LOUDNESS_1_5X.md)。本阶段没有代做完整 Gowin 构建，也没有下载或写 Flash。

## 2026-09-18 P29 USB IN 错误诊断（离线候选，未下载）

P29 补齐 P138 word 6：四个独立的饱和 8 bit 计数分别记录 USB IN 传输/协议错误、重复 DATA toggle、正常 NAK 和 50 ms 失联。现有 USB 48 MHz → 50 MHz UART 快照、MIDI 事件 FIFO、背压、热插拔和 PANIC 路径保持不变；`control.py --usb-a` 不再返回 `usb_in_errors: null`。底层驱动仍会合并部分 CRC 与 timeout，因此错误总数不伪装成更细分类。

完整 routed audit、通用 MIDI/诊断回归和 CPU/audio 回归通过。P&R setup/hold 0/0，最差 setup slack +0.085 ns；Logic 35112、Register 25734、BSRAM 253、DSP 43.5。候选 UserCode `0x00000029`，SHA256 `b43d9e981cde16d571caeeea1ca2ca7e2031c556202cab48fa95eed6e6940581`。按用户要求，本会话没有执行 programmer、SRAM 下载或读回，Flash 也未写；板上最后一次已知实体稳定版本仍是 P28。见 [源码审计](P29_USB_IN_DIAGNOSTICS_AUDIT.md)、[验证记录](P29_USB_IN_DIAGNOSTICS_VERIFICATION.md) 和 [候选绑定](P29_USB_IN_DIAGNOSTICS_CANDIDATE.json)。

**UserCode 冲突：** 本候选的 `0x00000029` 与分支 `codex/post-p28-product-features` 上的 P29A 引导功能重号，而 P29A 已于 2026-09-18 实体验收并占用该号。本诊断候选从未下载，若要上板必须用新 UserCode（下一个可用 `0x0000002A`）重新构建。

## 2026-09-18 P28 效果状态 routed audit 修复（实体通过）

P28 关闭了从旧版本延续的 `effect_mask_sync_[0..2]_s0/RESET` 审计缺口。三位效果选择仍从 76.8 MHz 音频域经过两级同步进入 50 MHz 显示域；显示镜像改为初始化的无活动复位 DFFCE，旧 RESET false path 已删除。最终网表逐位证明 meta→sync 数据链、固定高 CE、固定低 CLEAR 和无 RESET/PRESET，负向变异检查也能拒绝断开的第二级。

完整 routed audit 通过。P&R setup/hold 0/0，最差 setup slack +0.063 ns；Logic 34895、Register 25638、BSRAM 253、DSP 43.5。位流 SHA256 `a6544465c4aad1bb7a07abfb6158f1a787927442698eaf8193e9bad080f2fbb1`，UserCode `0x00000028`。通用 MIDI 与完整 CPU/audio 必要回归通过。已从已验收通用 MIDI版本 `0x00006DE8` 仅写 SRAM 并读回 P28，Flash 未写。

用户确认 Push、连续压力、屏幕和灯光、通用 MIDI、电脑键盘、HDMI、耳机、效果链、曲谱和录音控制均正常，并报告“没问题，完美”。该实体版本的 USB IN error 诊断仍为 `null`；P29 离线候选已实现诊断，但尚未下载。见 [正式版本记录](BOARD_CURRENT_P28_EFFECT_MASK_AUDIT.json)、[源码审计](P28_EFFECT_MASK_AUDIT.md)、[验证记录](P28_EFFECT_MASK_AUDIT_VERIFICATION.md) 和 [候选绑定](P28_EFFECT_MASK_AUDIT_CANDIDATE.json)。

## 2026-09-18 通用 USB MIDI 1.0 自动识别（实体通过）

在保留 Push 2 专用 MIDI、屏幕和灯光路径的同时，USB Host 可从设备描述符中寻找 MIDI 1.0 Bulk IN 端点，并把 Note On/Off、poly pressure、CC、Program Change 和 Pitch Bend 送入现有音频事件 FIFO。普通 MIDI 设备不经过 Push 的音域、力度曲线或面板映射；Channel Pressure、SysEx 和实时消息尚未映射。

候选 UserCode 为 `0x00006DE8`，位流 SHA256 为 `5ae02d9fac533df10f5921272b8243304acb7011d6bacd4877b6bbeb9dbf961f`。完整构建 setup/hold 0/0，最差 setup 裕量 +0.017 ns；Logic 34897、Register 25638、BSRAM 253、DSP 43.5。固件、MMIO/CDC、音频、P27 控制和 P26 屏幕回归通过。完整 routed audit 仍停在原有三个 `effect_mask_sync` reset 端点，没有写成通过。

用户自行完成下载和通用 MIDI 调通，并确认现有 Push、显示、音频与效果链回归正常。随后通过 `programmer_cli` 只读检查到 GW5AST-138C 设备 ID `0x0001081B`、UserCode `0x00006DE8`、状态码 `0x00026230`。下载过程不是本代理执行，仓库也没有对应写入记录，因此 SRAM/Flash 写入方式保持未知，不据读回结果推断。P27 `0x00000027` 保留为上一实体稳定回退版本。实现边界和复现方法见 [验证记录](GENERIC_MIDI_VERIFICATION.md)，验收绑定见 [实体版本记录](BOARD_CURRENT_GENERIC_MIDI.json)，精确离线构建信息见 [候选记录](GENERIC_MIDI_CANDIDATE.json)。

## 2026-09-17 P27 Push 控制绑定（实体通过）

P27 将 Push CC85/86 分别绑定到现有 LED-only 曲谱 start/stop 和有界 recorder enable，将 CC62/63 绑定到 A/B/C 左右循环，并用 CC28 控制效果总开关。效果关闭后仍保存选择 mask 和 P10 串行顺序，重新打开恢复；CC27/29 继续使用 P23 硬 PANIC。曲谱仍只使用既有 RAM、绝对 48 kHz sample 时间戳和 LED mask，不产生音符或预录音频。Push 公开屏幕协议、pad/连续压力、电脑键盘、MIDI、声部分配、HDMI、耳机和效果链保持原路径。

正式 P&R setup/hold 0/0，最差 setup slack +0.258 ns；Logic 34966、Register 25605、BSRAM 253、DSP 43.5。位流 SHA256 `dcd14a32b18a947ba807ea86a6780762176bbe3fcba1c7c020490b615016c101`，UserCode `0x00000027`。已从 P26 `0x00000026` 只写 SRAM 并读回，Flash 未写；用户完成新增控制和既有功能实体检查后回复“没问题”，验收后再次只读仍为 P27。完整 routed audit 仍只因旧三个 `effect_mask_sync` reset 端点失败。见 [正式版本记录](BOARD_CURRENT_P27_CONTROL_BINDINGS.json)、[源码审计](P27_CONTROL_BINDINGS_AUDIT.md)、[验证记录](P27_CONTROL_BINDINGS_VERIFICATION.md) 和 [候选绑定](P27_CONTROL_BINDINGS_CANDIDATE.json)。

## 2026-09-16 P26 交互延迟测量与 Push 屏幕 FIFO 优化（实体通过）

P26 量化了 Push、电脑 UART 和 DIN MIDI 到 core/PCM/DAC 的数字路径，并把 Push 每个 512 字节像素包从 CPU 寄存器逐字节握手改为同一 48 MHz 域直推现有 USB TX FIFO。每包装载由 1793 周期降到 769 周期，完整 640 包帧节省 13.653 ms；公开 16 字节帧头加 640 个 512 字节包、NAK 重装、每 4 包 MIDI 轮询、每 32 包灯光服务均保持不变。12 Mbit/s 纯载荷下限仍为 218.464 ms，没有把 0.2 秒写成达到。

正式 P&R setup/hold 0/0，最差 setup slack +0.041 ns；Logic 34971、Register 25380、BSRAM 253、DSP 43.5。位流 SHA256 `b23c31c0b35776ce459a01ef62889845dd58025a2977f705826fa8b8e46c10ba`，UserCode `0x00000026`。已从 P24 `0x00000024` 仅写 SRAM并读回 P26，Flash 未写。完整 routed audit 仍只因旧三个 `effect_mask_sync` reset 端点失败。用户检查 Push 屏幕操作速度和画面、Push pad/连续压力/灯光、电脑键盘长按、HDMI、耳机及效果链后报告“没问题，继续”。见 [正式版本记录](BOARD_CURRENT_P26_INTERACTION_LATENCY.json)、[路径审计](P26_INTERACTION_LATENCY_AUDIT.md)、[验证记录](P26_INTERACTION_LATENCY_VERIFICATION.md) 和 [候选绑定](P26_INTERACTION_LATENCY_CANDIDATE.json)。

## 2026-09-16 P25 频谱泄露受控实验（分析完成，板上仍为 P24）

P25 用同一个 MIDI 60 单正弦逐项改变窗函数、起始相位和 FFT 点数，并用 P24 十五组最终 DAC 采样核对真实谐波；另在完整音频/效果链中执行硬 PANIC。结果区分出：真实采样率为 48 kHz，改频率标签不会改变任何幅度 bin；周期 Hann 相对矩形窗把最大远端泄露从 −24.24 dBc 降到 −42.02 dBc；64 个起始相位的最大远端变化仅 0.022 dB；点数改变 Hz 分辨率，但因音符与 bin 非相干，相对泄露不会单调下降。十五组生产声音至少 99.9598% 功率落在已有 32 个谐波的 Hann 主瓣内。

硬 PANIC 后左右各 4096 个连续样本全部为零，排除持续音频残留；只有跨越 PANIC 的单个 2048 点块因“旧声音＋零”的硬截断产生宽带瞬态，下一整块为零。当前约 84.3 dB 的显示范围会同时显出真实谐波和低电平窗旁瓣。当前周期 Hann 应保留，未发现需要修改生产 RTL 的采样率、窗口或触发错误。P25 没有生成或下载位流，板上仍是已验收 P24 `0x00000024`，Flash 未写；旧 `effect_mask_sync` reset 审计缺口和 USB IN error `null` 均未改变。见 [路径审计](P25_SPECTRUM_LEAKAGE_AUDIT.md)、[验证记录](P25_SPECTRUM_LEAKAGE_VERIFICATION.md) 和 [实验绑定](P25_SPECTRUM_EXPERIMENT.json)。

## 2026-09-16 P24 A/B/C 模式响度校准（实体通过）

P24 用相同 MIDI 60、velocity 127、音色、包络年龄和效果关闭的最终 48 kHz PCM 测量，按 A 计权频谱能量对齐五种音色的 A/B/C 响度。A 保持不变，B/C 只对各自增益 ROM 行做固定缩放，谐波比例、包络、活动声部与效果链不变。十五组 32 音和弦及三个最高峰 32 同音极限均无饱和；C 钢琴为峰值余量保留约 0.37 dB。

完整构建 setup/hold 0/0，最差 setup slack +0.087 ns；资源与 P23 相同。位流 SHA256 `7a37311de6df38ed1f0191bd2f07094904df826dd69c4b2007f2e0ec099c1c66`，UserCode `0x00000024`。已从 P23 `0x00000023` 仅写 SRAM并读回，Flash 未写。完整 routed audit 仍只因旧三个 `effect_mask_sync` reset 端点失败。用户完成五种音色、A/B/C 响度、高力度和弦以及既有功能回归后报告“没问题，完美”；验收后只读仍为 `0x00000024`。见 [正式版本记录](BOARD_CURRENT_P24_MODE_LEVEL.json)、[源码审计](P24_MODE_LEVEL_AUDIT.md)、[验证记录](P24_MODE_LEVEL_VERIFICATION.md) 和 [候选绑定](P24_MODE_LEVEL_CANDIDATE.json)。

## 2026-09-16 P23 PANIC 同步硬清理（实体通过）

P23 将明确的 PANIC 改为 CC120：接受事件时立即清 held、延音/释放扫描、声部分配可达状态、处理流水线和效果尾音；CC123 继续作为正常 RELEASE。10 bit PANIC 世代沿现有状态快照清 Push mapper/画面、AE350 UI gate 和电脑窗口重复状态，不改变 pitch 低 22 bit、Push 连续压力、声部分配策略或效果选择/顺序。

完整构建 setup/hold 为 0/0，最差 setup slack +0.087 ns；Logic 34848、Register 25381、BSRAM 253、DSP 43.5。位流 SHA256 `8bd54510c9e0637420a49c9e4235c27659a9e48417a97eec35137e322dda25b6`，UserCode `0x00000023`。已从 P22 `0x00000022` 仅写 SRAM 并读回，Flash 未写。用户确认电脑与 Push PANIC、持键防重触发、电脑长按、Push/连续压力/屏幕/灯光、HDMI、耳机和效果链均正常；验收后只读确认仍为 P23。完整 routed audit 仍只因原三个 `effect_mask_sync` reset 端点缺口失败。见 [正式版本记录](BOARD_CURRENT_P23_PANIC_SYNC.json)、[源码审计](P23_PANIC_SYNC_AUDIT.md)、[验证记录](P23_PANIC_SYNC_VERIFICATION.md) 和 [候选绑定](P23_PANIC_SYNC_CANDIDATE.json)。

## 2026-09-15 P22 电脑键盘连击（实体通过）

修复现有电脑 Tk 串口入口的长按去重行为：短按一次，长按 300 ms 后每 80 ms 发送 Note Off/On，松键立即停止重复计时器；原 X11 松键窗口和声部释放包络保留。空格延音期间暂停连击。Tk 和 UART→音频定向仿真通过，完整构建 setup/hold 0/0、最差 setup slack +0.010 ns，资源与 P21 相同。完整 routed audit 仍因原三个 effect_mask reset 端点缺口失败。

新位流 UserCode `0x00000022` 只是 P22 发布标识，硬件生产输入与 P21 相同；功能修复在电脑脚本。本次已读回 P21 `0x0000D14C`、仅写 SRAM、再读回 `0x00000022`，Flash 未写；实体键盘验收后再次只读确认仍为 P22。U15 板端回报仍为 0 字节；窗口排旧缓存 2 秒后进入标黄的“单向演奏”状态，不伪造板端状态。用户确认电脑控制正常，会话中 Note On/Off 各 254 次且每个音高完全配对；随后确认 Push、连续压力、HDMI、耳机和效果链均正常。受保护原 Xilinx Web Serial 页也存在 `event.repeat`/active 去重根因，本轮未修改。P21/P10 回退完整保留。见 [正式版本记录](BOARD_CURRENT_P22_KEYBOARD_REPEAT.json)、[源码审计](P22_KEYBOARD_REPEAT_AUDIT.md)、[验证记录](P22_KEYBOARD_REPEAT_VERIFICATION.md) 和 [候选绑定](P22_KEYBOARD_REPEAT_CANDIDATE.json)。

## 2026-09-15 P21 屏幕硬件装包（实体通过，延迟约 0.35 秒）

用户确认 P20 力度正常，屏幕操作仍约 0.6 秒。P21 用同一 48 MHz 时钟域的装包状态机替代 CPU 逐像素读、XOR、暂存及逐字节搬运，经原寄存器握手直接装载原 512 字节 USB FIFO；每包 1793 周期、约 37.35 µs。模拟 CPU 阻塞装包、音频连续运行、NAK 重装及字节一致性已通过。用户实测屏幕延迟降至约 0.35 秒，画面、连续压力、灯光、HDMI、耳机和效果链正常。327696 字节在 12 Mbit/s 下仅载荷就需 218.464 ms，因此 0.2 秒目标未记为通过。

最终 P&R setup/hold 为 0/0，最差 setup slack +0.010 ns；Logic 33830、Register 25192、BSRAM 253、DSP 43.5。位流 SHA256 `77a4a62e8e0323c94f4c58b73e9de0b1142a5fa612966c4c7f86de3a346fb039`，UserCode `0x0000D14C`；已从 P20 `0x0000F9B7` 单独写入 SRAM并读回，Flash 未写。见 [P21 阶段记录](P21_SCREEN_LOADER_VERIFICATION.md) 和 [版本记录](BOARD_CURRENT_P21_SCREEN_LOADER.json)。

## 2026-09-15 P20 力度校准与 Push 旧帧立即重启（力度通过，延迟约 0.6 秒）

P20 将 Push pad 的每个非零原始力度增加 28 并饱和到 127，精确实现 `002` → `030`；映射同时用于 Note-On、poly-aftertouch、channel pressure、声音事件和 Push 状态显示，零值仍为零。屏幕保留官方 16 字节帧头和 640×512 字节完整帧格式；传输旧保活帧期间检测到模式、音色、效果、路由或持键变化时，丢弃尚未发送的旧帧尾部并立即从新帧头重启，避免先等旧帧完成再排一个新帧。连续压力数值不触发中止，以免压力不断变化导致永远没有完整帧提交。

P&R setup/hold 0/0，最差 setup slack +0.247 ns，Logic 34293、Register 25165、BSRAM 253、DSP 43.5。位流 SHA256 `50bbf9eeddbc2184c5deeecc89340041b28e09e09f8c07288da05e0cb56084cb`，UserCode `0x0000F9B7`；已从 P19 `0x00005169` 单独写入 SRAM 并读回，Flash 未写。完整帧仍约需 450 ms，本次实体确认重点是 `002` → `030` 的声音/显示结果，以及离散操作不再承担旧帧尾部加新帧的近一秒等待。见 [版本记录](BOARD_CURRENT_P20_FORCE_SCREEN_RESTART.json) 和 [阶段验证](P20_FORCE_SCREEN_RESTART_VERIFICATION.md)。

## 2026-09-15 P19 Push 屏幕完整帧保活（保活通过，交互延迟由 P20 取代）

P18 实体确认连续压力正常，但静止超过约 2 秒后 Push 按官方行为自动黑屏。P19 保留状态变化立即发帧，并在上一完整帧结束后 1000 ms 发送合法完整保活帧；不试验协议保留的短帧或局刷格式。P&R setup/hold 0/0，Logic 33760、Register 25165、BSRAM 253、DSP 43.5。位流 SHA256 `08db9c8fd1c97e9a9bcad63e330eaaa43fe6158ed022ae13f3793d4b825adab9`，UserCode `0x00005169`；已从 P18 `0x0000D914` 单独 SRAM 下载并读回，Flash 未写。用户实体确认屏幕保活和连续压力正常，随后复测确认操作刷新仍接近一秒；压力灵敏度也未在本阶段改动。这两项由 P20 处理。见 [版本记录](BOARD_CURRENT_P19_PUSH_SCREEN_KEEPALIVE.json) 和 [阶段验证](P19_PUSH_SCREEN_KEEPALIVE_VERIFICATION.md)。

## 2026-09-15 P18 官方 poly-aftertouch 与事件驱动 Push 屏幕（压力通过，屏幕由 P19 取代）

P18 显式发送 Ableton 文档规定的 `Set Aftertouch Mode 0x1E, mode 1`，使按住 pad 的持续压力以带 note 的 poly key pressure 返回并只更新原声部 expression。Push 屏幕改为 UI 状态变化时才发送合法完整帧，空闲每轮轮询 MIDI，传帧中每 4 个包轮询；不再让无变化整帧持续占用 FS 链路。P&R setup/hold 0/0，Logic 33760、Register 25165、BSRAM 253、DSP 43.5。位流 SHA256 `b9ef014335aec28ac3f1272c128b710ca4cb8bfe87a93044c88d168eee5af72f`，UserCode `0x0000D914`；已从 P17 `0x0000F123` 单独 SRAM 下载并读回，Flash 未写。用户实体确认连续压力正常，灵敏度略高；静止屏幕因 Push 的 2 秒无完整帧黑屏规则而未通过，由 P19 保活修复。见 [版本记录](BOARD_CURRENT_P18_PUSH_AFTERTOUCH_SCREEN.json) 和 [阶段验证](P18_PUSH_AFTERTOUCH_SCREEN_VERIFICATION.md)。

## 2026-09-15 P17 连续压力兼容与 Push 屏幕调度候选（待本轮实体验收）

P17 在 P16 基础上兼容 Push 的 CIN A poly-aftertouch 与 CIN D channel-pressure 两种压力包；按住同一 pad 时只更新已有声部的 expression，不重新分配音符。屏幕仍使用原 16 字节帧头和 640 个 512 字节包，固件改为每 16 包轮询 MIDI、每 32 包服务灯光，去掉每包空闲 IN 轮询造成的额外等待。P&R setup/hold 0/0，Logic 33820、Register 25164、BSRAM 253、DSP 43.5。位流 SHA256 `90a3d5563149a5ae40c431647fdb229730e8f3078812be4657e5d22f34fe9e02`，UserCode `0x0000F123`；已从 P16 `0x0000C706` 单独 SRAM 下载并读回通过，Flash 未写。RTL、CPU/USB 和生产固件回归通过；真实压力和 Push 屏幕延迟待本轮用户验收，见 [版本记录](BOARD_CURRENT_P17_PRESSURE_PUSH_LATENCY.json) 和 [阶段验证](P17_PRESSURE_PUSH_LATENCY_VERIFICATION.md)。

## 2026-09-15 P16 连续压力与 Push 屏幕刷新候选（待本轮实体验收）

P16 在 P14 C 模式 32 声部基础上加入 Push USB-A poly-aftertouch 连续压力控制，并修复 Push 屏幕只显示首帧的问题：主机每次发起屏幕帧请求都会提交新的 control/options、pad held、note 和 velocity 快照。P&R setup/hold 0/0，Logic 33793、Register 25164、BSRAM 253、DSP 43.5。位流 SHA256 `85f6eba4b9db18468b300a58567bfb4a096123fbf699eea041ecc8f426450e82`，UserCode `0x0000C706`；已从 P14 `0x00005610` 单独 SRAM 下载并读回通过，Flash 未写。RTL 压力、声部和 Push 刷新回归通过；真实压力听感、Push 动态画面、HDMI 和耳机仍待用户验收，见 [版本记录](BOARD_CURRENT_P16_PRESSURE_PUSH_REFRESH.json) 和 [阶段验证](P16_PRESSURE_PUSH_REFRESH_VERIFICATION.md)。

## 2026-09-15 P14 C 模式 32 声部候选（已保留，可回退）

P14 在 P13 共享 DDR 显示数据基础上恢复 C 模式 32 声部：统一振荡器使用 1024×80 bit slot RAM，C 模式按 32 个 voice 映射，上层满载判断检查完整 32 位。RTL 满载扫描为 1024 slots、sample latency 1035/1600 个 76.8 MHz 周期；P&R setup/hold 0/0，Logic 33781、Register 24931、BSRAM 253、DSP 42.5。位流 SHA256 `5249dc938d6288e87a2e5ca2ae3ce21808a3c11671b3b47f38b767754a869a86`，UserCode `0x00005610`。已从 P13 `0x0000F002` 单独 SRAM 下载，写后读回通过，Flash 未写。实体 HDMI、Push、耳机、32 声部声音和交互延迟待确认，见 [版本记录](BOARD_CURRENT_P14_C_MODE_32.json) 和 [阶段验证](P14_C_MODE_32_VERIFICATION.md)。

## 2026-09-15 P13 阶段 4（已保留，可回退）

P13 已完成共享 DDR → HDMI reader → Push 64 位摘要 mailbox 的 RTL、仿真、P&R 和 SRAM 下载；它是 P14 的直接回退版本，UserCode `0x0000F002`，写前 P12 `0x0000C8A1`、写后 P13 均读回，Flash 未写。位流 SHA256 `894c51d40336fe86213adfddb3b151bc2c5d019b3cbd2e46a62acc0aa696539c`，setup/hold 0/0，最差 slack +0.024 ns。Push 仍走原 USB-A 协议，见 [版本记录](BOARD_CURRENT_P13_PUSH_SHARED_SUMMARY.json) 和 [阶段验证](P13_VERIFICATION.md)。

## 2026-09-15 P12 当前 SRAM 候选（待实体回归）

当前板上 UserCode `0x0000C8A1`。HDMI 已从 P11 版本化双 bank DDR 紧凑块读取 waveform、李萨如位图、频谱列和效果元数据，并保持原 dashboard、RGB565 framebuffer 与 scanout。setup/hold 违例 0/0，最差 slack +0.002 ns；Logic 33502、Register 24893、BSRAM 254、DSP 42.5。写前 P11 `0x0000D767`、写后 P12 `0x0000C8A1` 均读回，Flash 未写。见 [版本记录](BOARD_CURRENT_P12_HDMI_SHARED_DISPLAY_READER.json)、[阶段验证](P12_VERIFICATION.md) 和 [数据布局](DISPLAY_DATA_LAYOUT_V1.md)。Push 读取同一 descriptor 留在阶段 4；当前等待用户检查 HDMI、Push、耳机和效果链实体运行。

## 2026-09-13 P10 当前 SRAM 候选（待人工验收）

当前板上 UserCode `0x0000ED8B`。HDMI 卡片顺序已接入真实音频调度：一至三个不同效果按选择次序串联，前一级输出进入后一级；单个效果只处理一次。选满三个后再按任一效果仍会清零并淡出到精确干声。P9 已获用户“没问题，继续”反馈。见 [版本记录](BOARD_CURRENT_P10_SERIAL_EFFECT_ORDER.json) 和 [分层验证](P10_VERIFICATION.md)。只写 SRAM，Flash 未写。

656 帧效果单元仿真、Push 统一事件回归、完整 CPU/USB/音频回归、综合/布局布线、后布局音频审计及 SRAM 写后数字遥测均通过。setup/hold 违例 0/0；BSRAM 248/340，DSP 42.5/298。旧完整 DDR/video 审计仍保留 P8/P9 已知的三个显示效果 mask 复位端点覆盖缺口。实际顺序听感、实体 HDMI 动画、Push 和耳机输出待用户验收。

## 2026-09-13 P9 当前 SRAM 候选（待人工验收）

当前板上 UserCode `0x0000C2D3`，选满三个不同效果后再按任一效果键会全部清零，下一次按键才开始新一轮。去重与左右滑动保留。P8 已获用户“没问题”反馈，版本记录见 [BOARD_CURRENT_P9_CLEAR_ALL_EFFECTS.json](BOARD_CURRENT_P9_CLEAR_ALL_EFFECTS.json)。分层验证保存在对应的本地构建目录，未写 Flash。实际音频串联和旧显示复位审计覆盖缺口仍待处理。

## 2026-09-13 P8 当前 SRAM 候选（待人工验收）

当前板上 UserCode `0xA64B`，左右连续移动动画与队列去重已下载，未写 Flash。版本记录见 [BOARD_CURRENT_P8_SLIDE_UNIQUE_QUEUE.json](BOARD_CURRENT_P8_SLIDE_UNIQUE_QUEUE.json)，分层验证保存在对应的本地构建目录。未选满时重复按同一种效果不占新槽；选满三种后下一次按键开始新一轮。

源码核对纠正：当前音频只接收 effect_mask，并叠加 wet 输出；UI 顺序尚未接入实际串联处理。旧文档的“固定串联”不能作为现版验收结论。综合/PNR、功能仿真、SRAM 下载通过；旧路由审计仍有六个显示复位例外的覆盖缺口，失败报告保留。硬件听感与实际 HDMI 动画待用户验收。

## 2026-09-12 热插拔修正版

用户反馈 D50E 正常操作“完美”，但插拔 Push USB 后失去 MIDI、灯光、屏幕。D50E 原固件只在启动时枚举；现已补齐失联检测和重新枚举，保持所有 RTL、音频、HDMI 三图、DDR、AE350 和约束与 D50E 相同。

修正版已 SRAM 下载，见 [HOTPLUG_READY.json](HOTPLUG_READY.json) 和 [BOARD_CURRENT.json](BOARD_CURRENT.json)。**UserCode 仍为 D50E，必须用 SHA256 区分新旧固件**：新位流 `0e5a3cd5d6641c76777d76e1b5f5feddf65d661586ef0de14587cf0e1f09c1af`，构建 `results/build_20260912_001551_009746`。门级初始化比较的 359 个变化块全部属于 USB 固件 RAM。

- EP2 IN 连续 50 ms 没有有效 DATA/NAK 回复 → 清连接状态，由现有 RTL 松音和重置灯光/屏幕会话 → USB 复位、枚举、各方向 DATA0 重新开始 → 完整初始化恢复。
- 空闲 MIDI 的 NAK 是活跃连接，不误判断线；灯光/显示 NAK 重试间仍轮询 MIDI。USB OUT STALL 本身不停止正常 MIDI。
- 使用实际固件的离线测试通过：枚举失败重试、静默 NAK、短暂错误、计时回绕、重复 IN 包、ACK/NAK toggle、屏幕中途拔线、重连后 MIDI 和完整帧。
- 完整构建和路由审计通过，setup/hold 0，资源仍为 Logic 29178、BSRAM 244/340、DSP 42.5/298。下载后音频 48 kHz、HDMI 60 帧/秒、DDR/AE350/UI 数字检查通过。实际拔插验收以 `BOARD_CURRENT.json` 的对应捕获记录为准。

本轮下载前曾读到旧 Flash 版本 18D6；用户表示挪动板子时可能短暂断电。它与 USB 枚举问题不同：SRAM 位流断电即丢，重新上电会加载原 Flash。没有为此改写 Flash。

## D50E 首次合并记录（2026-09-11）

**当前：用户已在后续消息明确授权烧录，D50E 已 SRAM 下载并回读通过，Flash 未写。** 版本绑定及当前验收状态见 [BOARD_CURRENT.json](BOARD_CURRENT.json)。HDMI 三种图形、音频、DDR、AE350/UI 全部保留。

10 秒板端数字验证通过：音频 48000 样本/秒；HDMI 渲染/扫描均 60 帧/秒且欠载 0；DDR 和 AE350/UI 检查通过。Push 已配置，84 条灯光命令 ACK，屏幕持续约 2 帧/秒，OUT 错误 0。首次稳定窗口没有新增映射事件；累计 13 个映射事件不能充当本次人工按垫验收。耳机听感与实际屏幕画面等待用户确认。

此前离线阶段遵守了“不烧录、不占用板端”的要求；`READY.json` 和构建内 `verification_summary.json` 保留为该阶段的不可混用验收快照。

**离线交付已完成：D50E**，见 [READY.json](READY.json)。构建目录 `results/build_20260911_210232_835684`；原音频/DDR/HDMI/AE350 检查与新增 USB/跨时钟布线路径检查全部通过，setup/hold 违例均为 0。位流 SHA256：`4d8648cbc1e059e2b0367fbd6537fe8ad2010426bf14bbffe7214e0855bc5a17`。

资源：Logic 29178/138240，BSRAM 244/340，DSP 42.5/298。相对 3BE2 完整工作站，Logic +302，BSRAM +30，DSP 不变。D50E 已完成 SRAM 下载和数字运行验证；用户声光验收与此分开。

链路：Push 2 ⇄ J18 USB-A（D+ H13、D− G13）⇄ FPGA 内 VexRiscv USB Host + RTL PHY ⇄ 既有 Push 控制映射 ⇄ 异步事件 FIFO ⇄ 原音频工作站。

这条已上板工作的参考方案使用 **VexRiscv 固件处理 USB**，不属于“USB 全部纯 RTL”。音频仍由 RTL 逐样本运行，AE350 继续负责工作站 UI/控制；不使用 CH569、电脑中转或 DDR 来传演奏事件。

## 复用范围

- 音频/HDMI/DDR/AE350：冻结的 `../results/workstation_20260911_174045_306332`（3BE2）。保留精确 48 kHz、三模式/五音色、力度/弯音/滑音/颤音、延迟/合唱/混响、PT8211、三种分析图和原有 PC/G1 控制入口。
- USB：仓库内冻结的 [`vendor/usb_host_fs_8fc3`](vendor/usb_host_fs_8fc3)（来源版本 8FC3）。VexRiscv、USB Host、PHY 和 512 字节收发 FIFO 源码保持一致；构建时只给 SoC 增加控制寄存器接口。
- Push 映射、状态灯和屏幕像素使用既有 `push2_controls`、`push2_midi_rx`、`push2_lights`、`push2_led_tx`、`push2_surface_pixels`。屏幕显示实际合成器状态，经应答握手快照传入；电脑改参数也能反馈到 Push。
- 删除新顶层里的 CH569 HSPI 接口和旧 J18 Host 实例。原源码/旧位流/证据保留在原位置。

## 操作映射

| Push 操作 | 功能 |
|---|---|
| 64 垫，Note 36–99 | 音符/力度；按住不重复触发，松开或速度 0 释放 |
| 触摸条 Pitch Bend | 弯音；触摸条松开 Note 12 Off 回中心 |
| 上排 CC 102–104 | A / B / C 模式 |
| 上排 CC 105–109 | 笛 / 弦 / 铜管 / 马林巴 / 钢琴 |
| 下排 CC 20–22 | 延迟 / 合唱 / 混响开关 |
| 下排 CC 23–26 | 立体声 / 左 / 右 / 静音 |
| CC 27 或 29 | 硬 PANIC：立即清声部与效果尾音 |
| CC 28 | 效果总开关；重新打开恢复原选择与串行顺序 |
| CC 62 / 63 | A/B/C 模式向前 / 向后循环 |
| CC 85 Play | 进入 / 退出 TF 曲目指引模式 |
| 指引模式下 CC 44 / 45 | 歌曲清单向前 / 向后浏览 |
| 指引模式下 CC 48 Select | 选择歌曲；演奏页返回清单 |
| CC 86 Record | 开启 / 关闭既有有界 recorder |
| 旋钮 CC 71 或 79 | 音量；有符号相对增量，范围钳位 |
| 旋钮 CC 72 / 73 | 颤音 / 滑音 |

A/B/C 改变振荡器分配，原合成器在所有释放尾音结束后才提交模式。64 垫映射不等于三种模式都有 64 路同时发声；保留原核心声部分配。

## 时序与 USB 实机特例

USB 时钟 48 MHz；音频时钟 76.8 MHz，每 1600 周期一帧，即准确 48 kHz。音频事件 FIFO 满时，只让 USB CPU 的寄存器写等待；音频不等待灯光、屏幕、AE350 或 DDR。

MIDI IN 保留 DATA0/DATA1 去重；EP1 OUT 屏幕与 EP2 OUT 灯光分别维护 toggle，仅 ACK 推进。发送屏幕每个 512 字节包之前轮询 MIDI；OUT NAK 重试间也轮询。灯光命令保持至 USB ACK，失败可重试。

当前 Push 实测 Full-Speed 身份是 **2982:9999，9 字节配置描述符且接口数为 0**，但 EP1 OUT 屏幕和 EP2 IN/OUT MIDI 可用。按已验证设备特例处理，不能用旧 HS 描述符条件将其拒绝。屏幕保留 16 字节帧头 + 640 个 512 字节包及行填充/XOR 编码。

参考 demo 的用户已确认垫灯/屏幕，且有实际 MIDI 输入记录；**这不等于合并工作站已真机验收**。合并版已测得 Push 屏幕传输约 2 帧/秒、HDMI 60 帧/秒；操作延迟和耳机听感仍待用户确认。首次 D50E 沿用参考固件的无热插拔恢复限制；2026-09-12 修正版已补恢复流程。USB IN 错误计数仍未实现，回读标为未知。

## 离线构建与验证

```sh
python3 migration/gw138k_audio/push2_workstation/usb_a/build.py
python3 migration/gw138k_audio/push2_workstation/usb_a/sim/run.py <新构建目录>
python3 migration/gw138k_audio/push2_workstation/usb_a/sim/p23/run.py <新构建目录>
python3 migration/gw138k_audio/push2_workstation/usb_a/audit.py <新构建目录>
```

本地 `LATEST_BUILD.txt` 指向最近成功构建且通过完整顶层资源审计的结果，不进入 Git；准备阶段和失败构建不覆盖它。`LATEST_WORKSTATION.json` 记录 build mode、BSRAM 统计阶段、TF profile 和硬件状态。仍须结合 `tool_result.json`、`workstation_memory.json` 及对应 routed audit 判断验证范围；SYN 成功不代表 P&R 时序或实体通过。所有新构建结果初始都带 `hardware_tested:false`。

- MMIO/CDC 仿真：450 个事件按序通过，1746 个等待周期，覆盖 64 垫、零速度松键、通道/端口过滤、模式/音色/效果/声道/旋钮/触摸条；LED 不 ACK 时不阻塞音频事件；输出 960×160 像素并验证行填充。
- Vex 实际执行测试固件 → 真正 SoC 寄存器总线 → 既有合成器：3696 帧 PCM，其中 3574 帧非零；A/B/C、五音色、三效果、表达/声道路由/松音通过，帧间隔始终 1600 周期，音频错误计数为 0。AE350 总线时钟全程停止。
- `sim/run.py` 的测试固件只用于仿真。实际位流嵌入的是 `firmware.c` USB Host 固件，不是测试程序。

USB-A 工作站版本的 P138 回读应使用 `../scripts/control.py --usb-a`。它保留 A138/C350/K138/E138，P138 给出收到字数、映射数、灯光 ACK、屏幕帧数、OUT 错误，以及 P29 起新增的 USB IN 错误、重复包、NAK 和失联计数。P28 及更早位流的 word 6 仍是旧占位值，不能当作有效 P29 诊断。此命令会打开串口；P29 离线阶段未执行。

后续 30 秒交互窗口（序列 108–137）：新增 7 个映射事件、8 条灯光 ACK、58 帧 Push 屏幕，OUT 错误 0；实际核心回读观察到左右/立体声、钢琴、C 模式变化。该窗口未采到持键状态，不推断耳机发声或实际画面已由用户验收。记录：`../results/capture_20260911_212820_205862/interaction_summary.json`。

## P2–P5 核对（2026-09-13）

本轮未改 RTL、未删除 HDMI/DDR/AE350 或原音频旁路。补丁计划保存在 [`P2P5_PATCH_PLAN.md`](P2P5_PATCH_PLAN.md)，板上版本记录见 [`BOARD_CURRENT_P2P5_V3.json`](BOARD_CURRENT_P2P5_V3.json)：

- P2：48 kHz 下沿用 192 kHz 频率表乘 4，MIDI 0–36 最大误差 0.00449 cents；32 位相位连续，滑音/颤音按帧更新，不加 PLL。
- P3：固定链顺序为合成混音 → 延迟 → 合唱 → 混响 → 路由 → PT8211；mask 0=关闭、1/2/3 可单独或叠加、7=全开；映射仿真覆盖 1/3/7，关闭由复位/清零路径覆盖。
- P4：256×64 位曲谱 RAM、绝对帧、LED 掩码、开始/停止/完成状态及 APB 入口均已存在；不产生音符。
- P5：已统计当前绑定 CC 20–29、71–73、79、102–109。已按 Ableton MIDI Implementation Chart 补齐物理按键 CC 清单（3/9、28–31、35–63、85–90、102–113、116–119）；未根据另一台 2982:1967 Push 的 CC14/15 记录猜测映射。曲谱/录音按键需要把 UI 命令接入统一事件协议后再绑定。
