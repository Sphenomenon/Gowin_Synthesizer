# P11 共享 DDR 显示数据：阶段 2

状态：阶段 2 已完成 RTL、必要仿真、综合/布局布线、SRAM 下载及实体回归验收；写后 UserCode 读回 **`0x0000D767`**。用户于 2026-09-14 确认当前运行正常。阶段 3/4 的 DDR reader 尚未接入。

本阶段把现有 waveform、李萨如位图、频谱列和效果元数据写入版本化双 bank DDR 数据块。HDMI 的原像素渲染与 scanout 保留；Push 尚未读取这些块。源码审计见 `DISPLAY_DATA_SOURCE_AUDIT.md`，字段/地址/快照规则见 `DISPLAY_DATA_LAYOUT_V1.md`。李萨如导出的是已有 MID/SIDE 位图，频谱导出的是对数列，不是原始 I/Q 或线性 FFT bins。

## 构建和源码范围

本次下载构建：`usb_a/results/build_20260914_190033_599011`。其 `workstation_inputs.json` 冻结构建输入，`p11_source_scope.json` 对照 P10：只修改三份 video RTL、GPRJ 和五个音频 PLL RESET 源/译码单元的局部位置约束，新增 writer/bridge、package 及局部综合约束 p11.gsc。当前关闭全局资源复制，使用原 P10 的 Tcl/时钟频率；在导出端显式补回 DAC 波形恒零的低 15 位，保持 Q1.31 数值不变。音频、Push RTL/固件、DDR 仲裁、scanout 和 AE350 与 P10 相同。p11.gsc 用 syn_preserve 保留视频 reference PLL 的两级 enable_r；官方 helper 源码与初始化顺序未变。原 full PLL_INIT 审计仍要求含输入 buffer 的全传播时间不超过 10 ns。原 SDC 已恢复，未保留无效的 PLL RESET max_delay。p11.cst 将音频 helper 的 enable_r_1、state_[0..2] 和 pll_reset_s 归到 R39C72；该位置来自 P10 的 enable FF 布线记录，P10 使用同一 PLL_B[2]，原 full PLL_INIT 最大值为 9.808 ns。overlay 放在 `usb_a/rtl/display_data/`，不修改已有结果目录、原 Xilinx 或 Mega_138K 工程。

另为已有 SRAM 脚本增加可指定的 debugger location/sysfs 路径，保留 serial=2025030317 检查。当前调试器由旧 location 54/3-6 变为 location 53/3-5；使用实际扫描结果，不把 USB-C/CH569 当作 Push 数据通道。

## 仿真

- `build_20260914_181551_220839/p11_shared_181627_439803`：通过四块 magic/version、所有 descriptor 字段、每个 waveform/bitmap/columns 元素、元数据、长度/valid、三个连续帧、提交顺序、双 bank 复用检测和 25 ms DDR 背压；背压期间修改 live effect 状态不改变已锁存包。与 P10 比较首帧全部 1,036,800 对像素（2,073,600 RGB888 像素），完全一致。复位后 FFT 尚未发布时，分析 payload 为零、valid/length 无效，waveform 和 metadata 仍有效。
- `build_20260914_174417_398552/p11_shared_174432_553824`：实际 shared writer、原 frame writer、新请求寄存桥和原 arbiter 集成；此前每 2963 个 UI 时钟注入 120 个行读请求，帧尾停顿 20 μs。更正后的 `build_20260914_175828_867938/p11_shared_181157_808638` 以 1080p 的每行 2200/148.5 MHz 计算，改为每 1481 个 UI 周期注入 120 个行读请求；同样验证旧 P5 提交完成前不能启动新帧。365 次共享写、129600 次 framebuffer 写和 P5 提交顺序正确，读 tag 无错。模型从 start 到 frame_pending 为 1,605,177 周期，即 **16.05177 ms**（更正后的行流量模型）；这不包含实体 DDR 全部延迟，也不是输入到画面的真实交互延迟。
- `build_20260914_170429_574392/cpu_audio_sim_171137_772490`：CPU/USB/音频回归通过 3696 音频帧、3574 非零帧，精确 48 kHz，无音频故障。当前候选与该回归的音频/USB可达输入及固件相同，仅未实例化的 hdmi_display 文件不同；哈希复核见 source_scope，未为相同音频输入重复跑回归。

当前没有 HDMI 或 Push 的 DDR 分析 reader，因此 **HDMI/Push 读取同一 DDR 帧尚未实现、未验收**。仿真中使用本地 DDR 请求模型，不是实体 DDR 读回。结构上没有从显示背压到音频/MIDI ready 的路径；没有把上述两个独立仿真称为 USB PHY、音频、DDR 的全芯片联合压力测试。

## 综合、布局布线与审计

| 构建 | 结果 | 处理 |
|---|---|---|
| `build_20260914_170429_574392` | setup 302、hold 0，最差 −1.437 ns；Logic 31542、Register 22521、BSRAM 249、DSP 42.5 | 未下载；修复显示请求到 DDR ready 的长组合路径 |
| `build_20260914_171811_396774` | setup 0、hold 0，最差 0.000 ns；Logic 31475、Register 22806、BSRAM 249、DSP 42.5 | 未下载；额外 ACK 周期导致集成模型一帧 16.84037 ms，已去掉该周期 |
| `build_20260914_172627_729108` | setup 87、hold 0，最差 −0.336 ns；Logic 31673、Register 22804、BSRAM 249、DSP 42.5 | 未下载；将共享 writer ACK 单独寄存，保留像素快速 ACK |
| `build_20260914_173713_480963` | 已完成综合；在布局布线中主动终止，输入未改动 | 被上述 ACK 修正取代，保留日志；未下载 |
| `build_20260914_174417_398552` | setup 28、hold 0，最差 −0.121 ns；Logic 31460、Register 22805、BSRAM 249、DSP 42.5 | 未下载；共享 writer 关键路径已无违例，剩余为原卡片/音频路径 |
| `build_20260914_175828_867938` | setup 9、hold 0，最差 −2.833 ns；Logic 31457、Register 23276、BSRAM 249、DSP 42.5 | 普通数据路径通过，但复制了 CDC/复位寄存器，产生未覆盖端点和 DDR divider reset 审计错误；未下载，不采用 |
| `build_20260914_181551_220839` | setup 0、hold 0，最差 0.025 ns；Logic 31406、Register 22805、BSRAM 248、DSP 42.5 | 未下载；视频 PLL_INIT 复位全传播 10.981 ns，超过原审计 10 ns 门槛 |
| `build_20260914_183107_959144` | setup 0、hold 0；资源同 181551；9 ns SDC 显示 Actived，但无可计时路径，复位仍为 10.981 ns | 未下载；该 SDC 无效，已撤掉 |
| `build_20260914_184304_661902` | setup 0、hold 0，最差 0.043 ns；Logic 31436、Register 22807、BSRAM 248、DSP 42.5；video RESET 降至 8.129 ns，USB 布线审计通过 | 未下载；audio RESET 全传播 10.181 ns 超过 10 ns |
| `build_20260914_185619_135825` | 综合完成；多行 GROUP CST 在解析时 CT2000 失败，未进入布局布线 | 未下载；改为已有工程使用的单条 INS_LOC 语法 |
| `build_20260914_190033_599011` | setup 0、hold 0，最差 0.029 ns；Logic 31436、Register 22807、BSRAM 248、DSP 42.5；audio/video PLL_INIT 及音频/USB 分项审计通过 | 已 SRAM 下载；用户确认实体运行正常 |

最终资源对照：

| 资源 | P10 | P11 | 变化 |
|---|---:|---:|---:|
| Logic | 30019 | 31436 | +1417 |
| Register | 21652 | 22807 | +1155 |
| BSRAM | 248 | 248 | 0 |
| DSP | 42.5 | 42.5 | 0 |

中间版的 BSRAM 增量来自 u_align trace RAM。导出端恢复已知恒零的低 15 位后，总量回到 P10；没有删除分析图或削减音频 RAM。各时钟保持原配置：DDR memory 400 MHz/UI 100 MHz、HDMI pixel 148.5 MHz/serial 742.5 MHz、audio 76.8 MHz（采样 48 kHz）、USB 48 MHz、CPU bus/core 50/100 MHz。

后布局分项证据为本构建下 `p11_routed_summary.json`、`p11_usb_routed_summary.json` 和 `p11_pll_reset_paths.json`：音频 PLL_INIT 最大 9.762 ns，视频 reference/TMDS RESET 分别 8.331/8.783 ns，均满足原 10 ns 门槛。音频 MIDI/display 邮箱最大 C2Q+route 为 0.807/1.205 ns；USB 事件 FIFO 的 14 位 Gray CDC 最大 0.963 ns，既有 USB 反馈/遥测邮箱最大 1.669 ns。新增 writer 603 个 FF、bridge 284 个 FF 均接原 DDR UI 100 MHz 时钟，异步复位连接与原 frame writer 一致；没有新增显示数据 CDC。

**完整 DDR/video reset audit 仍未通过**：`usb_a_audit.json` 保留原有 `effect_mask_sync_[0..2]_s0/RESET` 三个覆盖缺口。没有删除审计条目、放宽 10 ns 门槛或把该缺口记为通过。最终构建的完整审计错误列表只剩这项已知缺口；音频、USB 和新增显示 FF 的分项检查不能替代完整审计。

## SRAM

受保护 P10 位流：`usb_a/results/build_20260913_184716_871458/Prj1/impl/pnr/Prj1.fs`，SHA256 `dd80b9009241836b3266b6407aa1a36cf8973d0b660d239e2e0f1fe8e0e4f793`，UserCode `0x0000ED8B`，文件哈希已复核不变。

P11 位流 SHA256：`97d7a7a19809fce5bb9bb26dd3823f785d0e88b12d5614f3ff6eccfb39a73a82`，UserCode `0x0000D767`。版本记录见 `BOARD_CURRENT_P11_SHARED_DISPLAY_DATA.json`。

下载记录：`push2_workstation/results/sram_20260914_191457_270893/result.json` 及同目录 before/sram/after.log：

1. 写前 operation 0 读回 P10 `0x0000ED8B`。
2. operation 2 SRAM 写入成功。
3. 写后 operation 0 读回 P11 `0x0000D767`。
4. **Flash 未写**。UserCode 读回不是完整 SRAM 内容读回。

## 真机与延迟

下载后短时采集：`push2_workstation/results/capture_20260914_191542_317624`。两秒 warmup 和正式八秒窗口均没有收到字节，因此不能据此确认音频采样率、HDMI 帧率、Push 运行计数或零错误。此前 P10 的 `capture_20260914_173945_860685` 也没有新的周期记录，仅 warmup 排出了旧记录；本轮不推测原因、不将无数据记为通过。

用户于 2026-09-14 确认 P11 当前实体运行正常，覆盖本阶段回归清单：HDMI 三图、卡片顺序/箭头/洗牌与滑动动画、三选满再清零，Push 屏幕/灯光，以及耳机/P10 串行效果/P2 低音。本阶段尚无硬件 DDR reader，因此实体 DDR 新数据区仍无读回证明，新增区域也不在旧前 8 MiB BIST 内；该限制留给阶段 3 reader 验证。真实交互延迟仍未单独测量。

显示导出 nominal 约 2 ms、额外 DDR 写约 0.701 MB/s（按 60 帧）；本阶段仍保留完整 framebuffer，未声称带宽或 BSRAM 已下降。真实按键/压力输入到耳机、HDMI、Push 的交互延迟单独列为待测。
