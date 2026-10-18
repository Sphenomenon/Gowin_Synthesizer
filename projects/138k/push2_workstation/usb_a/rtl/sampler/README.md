# EP-133 style sampler P1 + P2

本目录提供独立 RTL、导入工具与验证；`gw138k_event_workstation.sv`、`build.py` 和现有 TF vendor 源码不由此交付修改。`MODE_D_INTEGRATION.md` 描述主会话接入步骤。所有 RTL 客户端端口属于 76.8 MHz 音频时钟域；48 kHz tick 每 1600 clocks 一次。DDR 原生口是 256-bit BL8，业务 PCM 为有符号 PCM16 单声道，输出 stereo PCM16。

## 模块

| 文件 | 作用 |
|---|---|
| sampler_pkg.sv | descriptor/pad ABI、错误码、CRC32、全 MIDI 音域 Q16.16 变调比 ROM |
| sampler_voice.sv | 16 voice、小缓存、线性插值、ADSR、one-shot/gated/loop、reverse、volume/pan/力度/压力 |
| sampler_ddr.sv | descriptor 窗口 guard、轮询公平、2-bit client + 8-bit epoch + 6-bit serial tag、超时计数 |
| sampler_pool.sv | 104 MiB growth pool 的连续 1 MiB descriptor 顺序扫描分配、reserve/commit/abort/free |
| sampler_tf_source.sv | 原样实例化 FAT16/32 SPI reader；2048-byte FIFO；overflow 显式报告 |
| sampler_import.sv | 原样实例化 WAV decoder；PCM16 写 DDR、CRC/长度、峰值 normalize |
| sampler_storage.sv | pool + import + resample 的事务协调；仅成功写完后提交可读 descriptor |
| sampler_sequencer.sv | 16 patterns × 4 tracks × 16 steps，同步事件 RAM、实录/门限时长、swing、BPM、串链 |
| sampler_fx.sv | CC110 BitCrush、CC111 Drive、CC112 P10 delay send；内部合成 click |
| sampler_push.sv | 4×4 主 pad、4 组选择、16 pattern pads，按下到松开保留映射 |
| sampler_slice.sv | 16 等分切片/16 手动起点；边界无效时 valid=0 |
| sampler_grid.sv | 16×4 pattern grid，P26 frame_start 快照、dirty 状态变化请求 |
| sampler_mode_d.sv | voice / sequencer / Push / FX / DDR 客户端整合边界 |
| sampler_resample.sv | RTL 母线单音回录、PCM16 packing + CRC；编排回录拒绝 |

## 素材边界

只允许 `single_note`（最长 6 秒）与 `single_hit`（最长 2 秒）。两项时长是本交付的保守导入规则，不是音乐内容识别算法。每个素材必须显式声明 `reviewed_single_sound=true`、`contains_rhythm=false`、`contains_melody=false`、`contains_arrangement=false`。缺项、声明为真、loop/phrase/song/breakbeat 或超时均拒绝。人声单个音素可在审核后声明为单音；人声乐句不允许。故意虚假声明无法由 PCM 长度或 CRC 检出，素材审核仍须检查内容。

工具接受 PCM WAV 8/16/24/32-bit、mono/stereo、8–192 kHz，记录原格式与转换，输出 canonical mono PCM16/48 kHz WAV。双声道取平均，采样率采用线性离线转换。此转换不是带限高品质 SRC；对高频素材先使用带限 SRC 准备素材。板上 canonical WAV 可为上述整数位深，但必须 mono/48 kHz；其他率、stereo、压缩 WAV 显式 `E_FORMAT`，不会静默当作 48 kHz。WAV 解码只接 DDR 写口，不直接接音频输出。MP3/FLAC 路径不参与本模式。

```sh
python3 rtl/sampler/import_samples.py /path/spec.json /path/new-card-directory
```

`example_spec.json` 给出声明字段。工具先验证所有条目，再创建输出目录，生成 8.3 `S00.WAV` 等文件与 `manifest.json`。每条记录包含 owner、slot、byte 地址、capacity、frames、PCM 格式、gain_q16、CRC32、SHA256、时长、粒度及审核声明。初次导入按 manifest 顺序进入全新池，工具从唯一地址表读取宏，不能在工具里另写 DDR base。运行中 free/reallocation 后地址会变化，应从 descriptor 查询端口回读更新 manifest，而不能继续使用初始预测地址。

TF 源使用 vendor reader 的编译参数 FILE_NAME，一次导入一个指定 8.3 文件；该 vendor reader 没有运行时文件名口。本期多素材批量部署由 canonical 文件 + manifest + 主控制器逐事务 byte-stream 导入；要在板上运行时任意选 TF 文件，还需要主会话增加文件选择服务，不能把媒体播放器的 PCM mux 接进来。TF SPI 初始/传输均使用保守 divider 100；不用于播放实时取流。

## 控制与音色

`pad_t` 为每个逻辑 pad 指定 sample slot、root MIDI note、独立 trim/loop 的起止（end exclusive）、播放模式、reverse、ADSR 增量、volume Q0.16、pan 0..127。多个 pads 指向同一 slot、设置同一 root 就形成跨垫 keygroup。voice 存完整 pad/descriptor 快照；演奏中改变 pad 配置不会突然改动已有声部。ADSR 在每次样本推进；attack=0 为即时满幅，decay=0 保持满幅，release=0 为立即释放。NOTE_OFF 只释放 gated/loop，one-shot 播到 trim 末尾；CC123 释放全部模式，CC120 硬清理。

变调覆盖所有 MIDI 0..127 与 root 0..127。Q16.16 极低音比约 42/65536；这是定点精度，不是 clamp。插值在 loop_end-1 到 loop_start 之间连接，reverse 为 phase 递减；loop 输入本身若首尾 PCM 不连续，无法凭指针保证无听感接缝，TB 的周期素材有逐样本对照。MIDI 力度/压力/pan 的定点比例端点精确、内部比例相对误差 <0.012%。ADSR 与 volume 的 65535 表示接近 unity。

Push 的物理 note36 为左下：底部四行、左四列是 16 主 pad；最上行左四列为 A/B/C/D 组选择；右上 4×4 为 pattern0..15。逻辑主 pad note=`36+group*16+row*4+col`。未定义的 pad 不触发乐器。pattern-per-pad 在运行时请求下个小节边界启动，在停止时直接选 pattern。力度与 poly-aftertouch 保留连续值，组变化不改变已按下 pad 的 key-off。

音序器只存 `{note, velocity, gate_frames}`，每轨每步一个音符；声部复音来自 gate 重叠、现场演奏和 voice 引擎。16 patterns、最多16项串链、BPM30..300、swing0..50%。奇数步延后，偶数步保持两步总周期。BPM 改变保留相位余数。实录 note-on 对最近 swung step 量化；note-off 把实际按住样本数写回 gate。start 对齐下一48 kHz tick，stop 发 note-off，PANIC 清事件队列和 held 状态。事件槽 full/无效 BPM 返回明确错误；控制器应显示错误并 PANIC。

切片器输出 trim 范围，由主控制器写入各 pad 的 `trim_start/end` 与 `loop_start/end`。手动 marker 是起点，最后 end 为 trim_end；必须递增且在 trim 内。normalize 不重写 PCM，而在导入计算 gain 并由 voice 每样本应用。

母线回录必须显式 `approved_single_note`，音序器停止且 active_voices 始终=1，并冻结新 note-on、pattern launch、外部媒体路由。可连接 sampler 或其他单音实时合成母线；没有 ADC。默认最长期限6秒。到达 max_frames/stop 后 flush 最后 BL8 并 commit。任何第二声部、编排运行、未授权声明、producer overflow 或 DDR 错误都会 abort；不能保存整首或整个 pattern。新 descriptor 再次进入 voice 才有音频输出。

## 验证

```sh
python3 sim/sampler/run.py
python3 sim/sampler/synth.py --top sampler_mode_d
python3 sim/sampler/synth.py --top sampler_storage
```

输出位于 `out/sampler_*` 和 `out/sampler_synthesis_*`，含输入 hashes、逐测试日志、数值 metrics、vendor hashes。最终固定证据汇总见 `evidence.json`。综合测试为独立模块综合，不能代表整机 P&R 或板上 DDR 时延。具体数值与集成边界见 `MODE_D_INTEGRATION.md`。
