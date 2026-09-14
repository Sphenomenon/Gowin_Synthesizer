# P11/P12 显示数据源码审计

审计基线为已验收 P10 `build_20260913_184716_871458/Prj1`；实现使用 `usb_a/build.py` 冻结的 P11/P12 构建输入。路径以下均相对相应 `Prj1`。阶段 2～3 改动以 `usb_a/rtl/display_data/` 的 overlay 进入构建，原结果目录和 P10/P11 位流保留。当前协议见 `DISPLAY_DATA_LAYOUT_V1.md`，不能使用此前阶段 1 草案的 byte 地址。

## 当前数据产生和流向

| 模块/当前实例 | 数据和长度 | 时钟域 | 更新/握手与背压 | DDR 地址 |
|---|---|---|---|---|
| `src/migration/gw138k_audio_adapter.sv`，`u_managed/u_audio/u_observer`、`u_display_cdc` | 从实际 DAC 串行信号重建 L16/R16，携带 trigger reference、voices mask、status，总计 128 位 | 76.8 MHz → 50 MHz | 每个 48 kHz DAC 样本；held-data + req/ack 邮箱，忙时计 observation_drop，不阻塞音频 | 无 |
| `src/video/feedback_capture.v`，`u_video/u_renderer/u_capture` | 512×Q1.31 波形，两 bank；peak/voices/status/sequence/skipped/revision | 50 MHz 写、100 MHz 读 | 六极平滑触发；8192 sample timeout；捕获 512 点需约 10.667 ms，触发等待最多约 170.667 ms；双 bank 均占用时丢弃观察 sample_valid，不回压音频 | 本地双时钟 BSRAM |
| `src/video/feedback_wave_align.v`，`u_align` | 拷贝上述 512 点至本地 trace RAM；当前 waveform_held 恒 0 | 100 MHz | 每点 READ/COPY 两周期；无相似度拒绝，PCM 不滤波；renderer busy 时保持 | 本地 RAM |
| `src/video/output_audio_capture.v`，`g_analysis/u_analysis/u_capture` | 2048×32 位 L16/R16，两 bank | 50 MHz 写、100 MHz 读 | 连续 2048 点约 42.667 ms；ready/release 加 bank req/ack；占满计 skipped sample_valid；不等待音频 | 本地双时钟 BSRAM |
| `src/video/output_audio_analysis.v` + `audio_analysis_rom.v` | L、R 分别进行 2048 点 radix-2 FFT，周期 Hann；内部复数 RAM 为有符号 24 位；输出 L/R 各 1024 个 8 位 log-height，再将 bin 2～853 映射到 512 对 L8/R8 列 | 100 MHz | 两声道顺序处理；完成后 ready，renderer start 时发布 ready bank；源块理论上限约 23.4375 次/秒，实际受计算/发布/背压限制 | 本地 work RAM 和显示双 bank |
| 同一 `output_audio_analysis.v` | 同一未加窗 PCM 计算 MID=L+R、SIDE=R−L，增益/限幅映射为 256×256 一位位图 | 100 MHz | 与 spectrum 同一 analysis source sequence、skipped、valid、发布动作 | 本地双 bank |
| `src/video/feedback_renderer.v` + 两个 `feedback_dashboard.v` 实例 | 每次两个 RGB888 像素装入 64 位；1920×1080；卡片顺序、箭头、动画和三图 | 100 MHz | P12 先把本地分析快照导出并由 DDR reader 验证到缓存，再用共享缓存绘制；pixel_valid/ready 停整条像素流水线；最后像素被接受后释放 waveform | 交给 frame writer |
| `src/memory/ddr_frame_writer.v` | 16 个 RGB565 像素/256 位 BL8；一帧 4,147,200 B；P5 256 位元数据 | 100 MHz | 8 对像素打包；DDR 忙时保持请求并停 renderer；最终像素与 P5 write 被接受后发布 pending | framebuffer 原生 0、0x100000；P5 0x200000 |
| `src/video/video_ddr_scanout.v` | DDR RGB565 → 两个带 epoch/line tag 的行缓冲 → RGB888 | UI 100 MHz → pixel 148.5 MHz；TMDS serial 742.5 MHz | 1080p60 时序；vblank 交换已完成 framebuffer；每行 120 个 BL8；req/ack、完成 tag 邮箱和双时钟行 RAM，超时/underrun 单独报错 | 读取 view_select 选择的 framebuffer；P4 默认 RTL 分析页 |
| `src/ae350/gw138k_ddr_arbiter.sv` | BL8 原生命令与 256 位数据，read response tag FIFO | 100 MHz | BIST 先行；随后 scan 优先、display reader、CPU/writer 轮转；display 只在 BIST 完成后复用空闲 owner 0，read-tag 仍为原 2 位；读按 tag 分发 | 由各 request 提供 |
| `src/ae350/gw138k_ahb_ddr.sv` | 64 位 AHB ↔ 256 位 DDR，单 outstanding CPU 请求 | CPU bus 50 MHz ↔ UI 100 MHz，经已有请求/响应 CDC | CPU 可等待 DDR，独立于音频处理 | 原生 base=4194304，物理 16～24 MiB，CPU 0x10000000～0x107FFFFF |
| `src/push2/gw138k_push_performance_uart.sv` 的 `u_performance_cdc` → `src/usb_a/push2_usb_a_control.sv` 的 `feedback` | 448 位 performance snapshot；control/options/held 等，非三图数据 | audio 76.8 MHz → 50 MHz → USB 48 MHz | 第一段每 65536 audio clocks（约 0.853 ms），第二段每 4096 source clocks（约 81.92 μs）；两段 held-data req/ack 邮箱 | 无 DDR 读口 |
| `src/push2/push2_surface_pixels.sv` + `usb_a/firmware.c` | 960×160 RGB565，USB 行宽含 1024 像素填充；模式/参数/持键/效果开关界面 | USB 48 MHz | frame_capture 请求加 5,000,000 clocks 定时门控（约 104.167 ms）锁存界面状态；P13 额外锁存 HDMI reader 提交的 64 位 display summary 并用共享 effect mask 标记效果卡片；实际传输帧率由 FS USB/固件循环决定；每个 512 B 屏幕包之间轮询 MIDI | 64 位摘要来自 ddr_ui100→usb_48m mailbox；不复制 framebuffer 或 FFT payload |

`feedback_capture.v` 中关于 48,828.125 Hz、1024 点的旧注释不代表当前实例；本表采用实例参数、PLL/DAC 配置和连接。FFT 源块从 DAC observer 而来，不能把 legacy `spectrum_fft256` 的闲置诊断输出认作当前 HDMI 频谱。

## 重复工作和帧字段

HDMI 每个 renderer frame 仍重新生成完整像素，即便 analysis source sequence 没更新，但三图与效果元数据现在从共享 DDR 缓存取得，不再从本地分析 RAM 作为 HDMI 可见数据源。双 dashboard 是每拍偶/奇两个不同像素，不是重复生成同一个 framebuffer。Push 目前自行画模式和参数界面，没有重复采样或计算三种分析图；与 HDMI 重复的是部分状态取样和界面表达，不是 FFT。共享数据集中已有结果，保留各屏尺寸所需的最终绘制。

P10 的 P5 元数据 magic 在高 32 位，最低 word 是 memory status；没有版本字段，也没有 analysis sequence/skipped。它包含 waveform sequence/skipped，不能将其误称为统一分析序号。HDMI dashboard 另外直接取得 analysis sequence/skipped 和 peak/gain；bitmap 和 spectrum 共享该序号，waveform 独立。effect mask/order、memory status、显示帧计数在 renderer start 锁存，waveform 的 peak/voices/status 属于捕获结束。卡片动画计数按 renderer frame 推进，不按 FFT 帧推进。P13 Push 摘要事件来自同一已提交 display frame，但 Push 仍不读取完整 waveform/李萨如/spectrum payload。

P11 四个 descriptor 共有新增 display frame sequence，同时保留各 source sequence 和 sample skipped。analysis 在启动时未发布 front bank，就将两分析块 valid 清零、valid_length=0，payload 清零；有效 waveform 和 metadata 仍导出。后续已有 analysis 可连续被多个 display frame 引用，valid 不能被解读成“本帧刚计算”。

## 阶段 2 最小改动

- 在 renderer start 与第一对像素之间插入共享导出；源 front bank 保持到原 renderer 最后像素完成。
- 复用 waveform/bitmap/columns 现有 RAM 读端口，三周期读一个元素，按 256 位顺序移位打包；不增加采样器、FFT 或多端口 RAM。当前顶层 waveform=(DAC L16+R16)<<15，低 15 位恒零，HDMI 配置 SHARED_WAVE_ZERO_BITS=15 在导出时显式补零；导出的 Q1.31 数值不变，并允许工具裁剪恒零 RAM 位。其他实例默认 0，保持完整位宽。
- 新 writer 与原 frame writer 通过单请求寄存桥接入原 arbiter writer 槽位。桥接先保存请求；像素 writer 在真实 DDR 接受时得到 ACK，共享 writer 在下一拍收到寄存后的 ACK，避免其复杂状态译码连接到 DDR ready。该桥无新时钟域，像素流不额外增加 ACK 周期。原 frame writer 的 renderer_ready 在旧写请求未完成时关断，避免上一帧 P5 commit 遇背压时提前启动下一帧。
- 先使目标 bank 头为 odd，再写 payload、descriptor，最后提交 bank even 和全局记录。任意慢的读者必须前后校验 bank 头，不能只相信双 bank 不会被覆盖。
- 保留原 framebuffer、scanout、DDR 仲裁、AE350、音频、Push 协议和事件通道；此阶段没有硬件共享 reader，也没有消除全帧光栅开支。

新增 payload 不在前 8 MiB BIST 覆盖范围内。阶段 2 仿真覆盖写出的地址、数据与提交顺序；实体 DDR 数据完整性需后续 reader 或受控读回验证，不能凭写入 RTL 仿真宣称已验证实体 DDR。

## 阶段 3 HDMI reader

P12 新增 `display_data_reader.v`。reader 只在 writer 完成全局提交后启动，一次保留一个 DDR read request；检查全局记录、bank 头、四个 descriptor 和 payload 后再次读取 bank 头，前后头不一致或 generation 为 odd 时不发布缓存。waveform、bitmap、spectrum 分别缓存为 512×32、2048×32 和 512×16 位，metadata 直接锁存；renderer 以 `SHARED_RENDER=1` 从这些缓存重绘原页面。最终 RGB565 framebuffer/scanout、P5 兼容 metadata、分析采样和 FFT 都保留。

reader 与 writer/scanout 同属 DDR UI 100 MHz 域，没有新增分析数据 CDC。仲裁器仍保持原 2 位 tag；owner 0 在 BIST 结束后才供 display reader 使用，scanout 优先级不变。背压只延长本次共享快照装载和显示帧保持，不进入 audio ready 或 Push MIDI ready。

## 阶段 4 Push 摘要 reader

P13 从 HDMI reader 已提交的 metadata 形成 64 位摘要，在 ddr_ui100 域产生一次性事件，经过 `u_display_push_cdc` 的 held-data mailbox 进入 USB 48 MHz。Push 屏幕继续按原 USB-A frame_capture 请求读取像素，只把摘要锁存结果用于效果卡片状态；没有增加 USB endpoint、改变 MIDI 事件 FIFO 或复制 1920×1080 framebuffer。该 mailbox 的 held-data/hold/reset 约束列在 `usb_a.sdc`，分项路由结果见 P13 记录。

## 检查边界

仿真检查 packet/descriptor、每个 payload 元素、连续序号、bank 复用、启动 invalid、25 ms DDR 背压和 P10 单帧逐像素等价；这不是实体 HDMI 验收。CPU/USB/音频回归单独确认 48 kHz 和事件路径。RTL 结构确认 DDR backpressure 不进入音频/MIDI ready，但当前仿真没有把 USB PHY、音频和实体 DDR 模型全部同时运行。

布局布线需分别记录 setup/hold、资源以及各时钟。既有 stopped-clock reset audit 对 `u_managed/effect_mask_sync_0_s0/RESET`、`_1_s0/RESET`、`_2_s0/RESET` 的覆盖缺口仍必须如实保留。P12 已检查 writer 和 HDMI reader 使用同一 display frame；P13 进一步检查 Push 摘要只在同一 reader 提交事件后更新，但 Push 没有读取完整三图 payload，不能宣称 HDMI/Push 已显示同一组原始样本。输入到耳机/HDMI/Push 的真实交互延迟须独立测量。
