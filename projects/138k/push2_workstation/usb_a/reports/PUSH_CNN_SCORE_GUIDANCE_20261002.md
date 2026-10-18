# TF→CNN→Push 曲谱指引接入记录（2026-10-02）

## 接口与操作

- 现有 TF 直读／WAV PCM 与 Basic Pitch CNN 通路不变。172 帧 Viterbi 回溯完成后，按时间顺序导出稳定两帧以上的音高；同音的下一次起音由已经写入 DDR 的 onset 标志判定。原 UART 首音符报告继续保留。
- 音符经过 50 MHz→USB 48 MHz 双时钟 FIFO，存进最多 172 项的 Push 指引列表。CNN 权重、特征和动规历史仍在 DDR；这张小表只存 MIDI 音符号。
- Push 2 的 CC85（原曲谱播放按钮）切换指引模式。进入后先清掉全部 pad 和面板键灯，再只点亮当前目标 pad；CC85 再按一次退出，再进入会从第一音重新开始。
- 仅 Push 新的 note-on 且 MIDI 音符与目标一致时推进。错键、松键、压力事件、已按住键的重复事件都不会推进。列表结束后灯全灭。
- Push pad 仅覆盖 MIDI 36–99。CNN 给出的 21–35、100–108 音高按八度折入可按范围；原 CNN 音符结果不改。当前只解析已有的 172 帧分析窗口，不声称覆盖 TF 文件的整首曲子。

## 修改位置

| 位置 | 内容 |
|---|---|
| `rtl/music/basic_pitch_viterbi.sv` | 回溯路径提取序列；从 DDR 读重复起音标志；输出可背压的 score valid/ready/note。 |
| `rtl/music/basic_pitch_cnn_streaming.sv`、`basic_pitch_pcm_pipeline.sv`、`basic_pitch_workstation_link.sv` | 向完整 workstation 顶层贯通音符流。 |
| `build.py` | 音符流双时钟 FIFO、Push 模块加入工程；更新已经被综合合并的 CDC 复位引脚约束。 |
| `rtl/push2/push2_score_guide.sv` | 172 项列表、CC85 模式开关、严格按下推进、独占目标灯 mask。 |
| `rtl/audio/push2_controls.sv`、`rtl/push2_usb_a_control.sv`、`rtl/push2/push2_lights.sv` | 识别 CC85、用既有 mapped note-on 判定按键、模式内清灯再显示唯一目标；MMIO `0x5c` 可读模式／目标／游标。 |

## 验证

| 层次 | 结果 |
|---|---|
| Viterbi 路径本地状态 | `tb_viterbi_score.sv`：`60,60,62,60` 顺序、同音起音、FIFO 背压、旧首音符输出同时通过。 |
| 生产 DDR 起音路径 | `tb_viterbi_score_ddr.sv`：4 次 DDR onset 读取产生 4 个有序步骤，通过。 |
| 首音一致性 | `tb_viterbi_first_alignment.sv`：构造前帧路径 MIDI 36、确认首音 frame 2/MIDI 49 时，曲谱首项为 49，后续 62、60 顺序正确，通过。 |
| Push 控制与灯 | `tb_guidance.sv`：CC85 进出、85 个受控灯位清零／唯一 pad、错键阻塞、零力度 note-on 阻塞、旧键不重复推进、正确键推进、列表结束清灯，通过。 |
| 原 P27 控制回归 | Push／服务／音频三个 TB 均通过。 |

## 当前工作树完整候选 `0x50` 的实体结果

`results/build_20261002_172816_464963` 全顶层 Gowin 综合及 P&R 成功，输入哈希未变；SYN BSRAM 234/340，P&R BSRAM 278/340、DSP 154/298。位流 SHA-256 `6fed37dc46c97d6efe01a2902613271ef96dc6a1d2c086e1172e566c68fedb6a`，UserCode `0x50`。SRAM 下载的写前 `0x18D6`、下载、写后 `0x50` 均通过，记录在 `push2_workstation/results/sram_20261002_181636_515102/result.json`。Flash 未写。

模型 104478 字节、CRC32 `AF01A61B` 上传两次均由板端状态 `E` 确认。第一次 TF→CNN 运行结束的状态字为 `0022131F`，按 RTL 字段解码为 MIDI 24/frame 2（早先记录误写成 MIDI 49）；六层哈希高 29 位依次变为 `A002A6E0 C5EBE888 E1C916E0 56164CD0 429A4D48 C642A810`，不同于 `0x4D` 已验证的 `D1FFF498 C603CCE8 1E39D540 56F7DA28 D5816B28 CF7EF3A8`。这次耗时约 476 秒。第二次相同位流重新下载和上传后，TF 状态保持 `BB800002`，无格式就绪／PCM，CNN 未开始；120 秒后主动停止等待。这两次现象不能证明指引列表在板上正确生成，也不能把哈希偏差归因到单一模块。

`0x50` 的 P&R 时序未闭合：4331 个 setup、83 个 hold 违例端点；50 MHz Fmax 46.445 MHz、音频 76.8 MHz Fmax 56.936 MHz、DDR 100 MHz Fmax 69.320 MHz、USB 48 MHz Fmax 40.900 MHz。原 `0x4D` 也未闭合时序，不能因它曾跑出一次正确哈希便视作稳定位流。

## 隔离候选 `0x51` 的实体结果与修正

`results/score_guidance_4d_20261002_185521_686029` 从已板验的 `0x4D` 输入完整复制，只叠加曲谱指引。Gowin 综合、P&R 成功且输入哈希未变；SYN BSRAM 234/340，P&R BSRAM 278/340、DSP 154/298。位流 SHA-256 `8fde80442fcec9326531bac7688d2fa7a5f873b25a75563b2f9a534fac6210f6`，SRAM 写前 `0x50`、写后 `0x51` 已校验，Flash 未写。记录在 `../results/sram_20261002_192639_133707/result.json`。时序仍未闭合：2742 个 setup、84 个 hold 违例端点；50 MHz Fmax 44.447 MHz、音频 61.112 MHz、DDR 74.726 MHz、USB 43.066 MHz。

重新插 TF 卡后，48 kHz PCM 与 CNN 均在板上运行，约 478 秒完成；`B138` 显示非空曲谱 28 项，原首音状态 `0022131F` 实际解码为 MIDI 24/frame 2，折叠到 Push 音域后正是曲谱首项 MIDI 36。先前把该状态误解成 MIDI 49、进而认为曲谱首项错误，是状态字段解码错误。六层哈希高 29 位是 `C88347A8 94FE9C18 3FF85718 019AFDE0 416BAC30 7E699080`，与 `0x4D` 参考六项全部不同；完整运行日志见 `push_score_cnn_capture_51_20261002.log`。这个实体结果证明了 TF→PCM→CNN→曲谱计数路径有数据流，但不能证明 CNN 数值正确。哈希偏差仍需独立定位，可能涉及输入文件或未闭合时序。

Push 2 重新插线后，8 秒板端遥测 `P138` 报 `configured=1`、775 个收到的 USB 字、258 个映射事件、190 条灯光 ACK、53 帧屏幕 ACK、OUT 错误 0。用户现场确认：Play 进入指引后仅最低音 pad 亮，其余 pad 与面板键灯全灭；按错键灯保持，按正确键切到下一目标，重复按旧键不推进。对应遥测在 `../results/capture_20261002_195915_438876/`、`../results/capture_20261002_200646_934960/`。

## `0x52` 修正版实体结果

首个曲谱项直接使用 Viterbi 已确认的 `cmt_note`，从 `cmt_frame+1` 继续扫描；指引推进增加非零力度条件。四组针对性仿真已通过。由于 `0x51` 的首项原本已经与确认首音相符，这不是对一个已证实的板端首音错误的修复。

`results/score_guidance_4d_20261002_194539_384123` 完整 Gowin 构建退出码 0，输入哈希未变；综合 BSRAM 234/340，P&R BSRAM 278/340、DSP 154/298。位流 SHA-256 `f5784e4f03d7f4f99b2c68daf79be8a25cd83985bb5f9d0536f81222ceed2152`，SRAM 写前 `0x51`、写后 `0x52` 均读回通过，记录 `../results/sram_20261002_201632_863671/result.json`；Flash 未写。模型 104478 字节、CRC32 `AF01A61B` 上传，板端 DDR 读回状态 `E`。

TF 音频为 48 kHz，CNN 完成后的 `B138` 为 `0022131F BB80001C`。六层哈希高 29 位依次为 `D1FFF498 C603CCE8 1E39D540 56F7DA28 D5816B28 CF7EF3A8`，与 `0x4D` 参考 6/6 一致。曲谱非空，共 33 项；确认首音 MIDI 24/frame 2，折叠后的 Push 目标 MIDI 36，与曲谱首项严格相符；末项 MIDI 82。运行日志 `push_score_cnn_capture_52_20261002.log`。这次完整板测证明 TF→PCM→CNN→Viterbi→曲谱流数值可复现。

`0x52` 的 Push 2 实体验收通过：用户按 Play 进入指引后，只亮最低音目标 pad，其他 pad 和面板键灯全灭；按错键不跳，按正确目标跳到下一项，并确认整体“完美运行”。同期 `P138` 的 43 条 CRC 正确记录显示 `configured=1`、映射事件从 0 到 86、灯光 ACK 从 90 到 188、USB OUT 错误 0；见 `../results/capture_20261002_202616_397264/`。该遥测支持 USB 输入和灯光发送确实在运行，物理灯光位置与按键行为以用户现场观察为准。

`0x52` 的 P&R 时序仍未闭合：2980 个 setup、91 个 hold 违例端点；50 MHz Fmax 43.892 MHz、音频 76.8 MHz Fmax 62.440 MHz、USB 48 MHz Fmax 42.295 MHz。该实体运行成功不等同于时序保证。CNN 存储延续 DDR 方案，曲谱列表保存在逻辑中；本接口未增加 BSRAM 相比 `0x51`。

当前曲谱来自首次 172 帧分析窗口，最多容纳 172 个步骤；新的 TF 曲目需要重新运行分析并清空列表。本次验收没有覆盖整首长曲或重新换曲的自动更新。
