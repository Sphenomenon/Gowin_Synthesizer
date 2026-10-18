# TF 曲目清单与 Push 2 指引入口（2026-10-03）

## 当前结论

TF 直读核能从 FAT16/FAT32 根目录读取文件名。当前实现筛选所编译音频格式的文件，最多收录 16 首，并把每首的 8.3 短文件名显示为 12 个字符（`NNNNNNNN.EEE`）。FAT 长文件名不在当前显示范围；有长文件名的文件仍以对应短文件名出现在清单中。

Push 2 的歌曲清单、选曲、CNN 分析、曲谱指引与进度页已经接线。Play 进入/退出指引模式；在清单页用 Left/Right 浏览，Select 选曲；演奏页再次按 Select 返回清单。演奏页只点亮当前目标 pad，正确按下后才前进；三种效果键和合成器发声沿用工作站原链路。屏幕显示曲名、已演奏/总曲谱项数、进度条和三种效果的状态。

## 实现路径

- `rtl/tf_audio/storage/tang_mp3/sd/tf_sd_file_reader.v`：目录扫描保存短文件名、起始簇和文件大小，并提供文件名读端口。末项复制完成后才宣告清单就绪。
- `rtl/music/tf_playlist_bridge.sv`：将曲目数和文件名从 50 MHz TF 域传给 Push USB 域。
- `rtl/push2/push2_song_menu.sv`、`rtl/push2/push2_song_screen.sv`：菜单状态与 960×160 歌曲/进度画面。
- `rtl/audio/push2_controls.sv`、`rtl/push2/push2_score_guide.sv`、`rtl/push2_usb_a_control.sv`：模式按键、选曲、独占灯光指引和屏幕切换。
- `rtl/tf_audio/tf_workstation_audio_bridge.v`、`rtl/music/basic_pitch_workstation_link.sv`：选曲重启 TF 解码与 CNN，TF PCM 进入识别而不覆盖合成器音频；44.1 kHz 文件经 `rtl/music/basic_pitch_44100_to_48000.sv` 转成 CNN 所需采样率。
- `tools/build_song_guide_52.py`：以已通过上板曲谱验证的 0x52 工程为固定基线生成集成工程。

## 验证边界

0x52 基线已在实体 Push 2 上确认：Play 后仅目标 pad 亮，按错不前进，按对切到下一目标；TF→CNN 六页摘要与期望一致，生成 33 项曲谱。证据见 `reports/PUSH_CNN_SCORE_GUIDANCE_20261002.md`。

本次 0x58 位流已上板。TF 报告 48 kHz 文件格式有效；Push 2 USB 配置位为 1，屏幕帧确认数持续增加；模型上传在一次重试及随后一次重新烧录后通过 DDR 回读 CRC，状态 `E`。未选曲时曲谱项数为 0，符合等待选曲的设计。当前板端原始记录见 `reports/song_guide_board_status_58_20261003.txt`。模型上传有一次 DDR 回读 CRC 失败（实际 `E6615803`，期望 `AF01A61B`），因此 0x58 不能称为稳定通过。对应日志：`reports/song_guide_model_upload_58_20261003.log`、`reports/song_guide_model_upload_58_repeat_20261003.log`、`reports/song_guide_model_upload_58_restore_20261003.log`。

为处理偶发 CRC 失败，0x59、0x60 候选把 DDR 回读的两个 CRC 字节拆成两个 50 MHz 周期。两版均完成 P&R，但 DDR 用户时钟布线估计分别只有 64.676、55.611 MHz（目标 100 MHz）。0x59 上板后模型接收停在状态 `4`，90 秒内未完成，见 `reports/song_guide_model_upload_59_20261003.log`；0x60 因时序更差未写板。该候选改动保留在对应构建快照中，活动源码已恢复为 0x58 的已运行版本。当前板上也是 0x58，模型状态 `E`。三个版本的 BSRAM 布线统计均为 279/340；这属于完整工作站占用，不是 CNN 权重的片上存储数。

后续实体操作补证：用户在 Push 屏幕看到 `MUSIC02.WAV`，选中后先显示 `ANALYZING...`，随后切到演奏进度和目标灯。同期板端 `B138` 记录模型状态 `E`、曲谱 40 项、首项 MIDI 63、末项 MIDI 46。由此确认选曲后的 TF→CNN→指引入口实际运行。三种效果和乐声在该次选曲后的现场表现仍待单独确认。

**40 项并非整首 MUSIC02 的曲谱。** 当前工作站在 `basic_pitch_workstation_link.sv` 固定 `WIN_LEN=43844`、`FRAME_LIMIT=172`；前端先将 48 kHz PCM 重采样到 22.05 kHz，因此一次只覆盖约 1.99 秒。`basic_pitch_pcm_pipeline.sv` 在该窗结束后进入 `S_HOLD`，工作站没有续窗调度；Push 列表也固定最多 172 项。屏幕现有 `cursor/score_count` 只能表示这段窗口内的指引进度，不能解释为整首歌进度。要完成整首歌，需续窗、处理尾窗，并将曲谱容量和进度语义扩展到整首文件。

`reports/song_guide_selection_wait_58_20261003.log` 记录的是用户按键前约 212 秒的等待期，不能用它推断选曲后的耗时。

## 当前板上操作

板上运行 0x58，模型已加载。按 Play 查看歌曲清单，Left/Right 选一首，按 Select。分析完毕后，应只有当前目标 pad 亮；错误 pad 不推进，正确 pad 推进并更新屏幕进度。若只需恢复已通过的旧指引功能，可用 `results/score_guidance_4d_20261002_194539_384123/Prj1/impl/pnr/Prj1.fs` 写回 0x52。
