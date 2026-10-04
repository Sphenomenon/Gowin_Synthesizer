# TF 外部示波器音乐素材

这是独立的 **TF 预录文件播放模式**。赛题白名单的现场实时几何合成入口仍在 `rtl/audio/scope_vec/` 和 `tools/scope_score/`；本工具不会把文件播放计作实时振荡器吞吐量，也不会把录音写进路径 ROM、场景 JSON 或工程目录。

## 已核实的开源来源

- GitHub：`https://github.com/djmango/oscilloscope-music`
- 固定提交：`f1315f22b01a9baa9147c173ff00d3279212eff8`。
- 作者：Sulaiman Khan Ghori；MIT。原仓库声明旋律、和声、编排及合成为原创，有演示视频和确定性生成 CLI。此次选取源码生成的曲目，不下载 Jerobeam 的商业作品。
- 原曲：A minor / 100 BPM / 105.6 秒，44.1 kHz 立体声 PCM16。
- 本机保留原作、许可证、生成日志和转换说明。没有把 GitHub 宣传视频的分声部彩色图像当成实际混音的 X-Y 图形。

原作逐音符 `dx/dy` 定位在和弦混音中重复叠加，经 `tanh` 后原始左右均值为 −24954/−21833 LSB，图形偏向角落。因此 `centered_song.py` 适配器在混音前关闭这两个定位参数，保留音符、包络、谐波比例、节拍、鼓声和原有混音流程。它不更改上游 checkout，原始输出也保留在卡外。适配版本是本项目验证的衍生文件，不声称是上游未改动发行版。

随后两通道共用 `scipy.signal.resample_poly` 的 160/147 滤波器转换为 48 kHz；两轴使用同一幅度系数，不削波、不单声道混合、不加效果、不改变时长。最终 `OSCIMUS.WAV` 是 5,068,800 帧 / 20,275,244 字节，峰值 L/R 为 31915/32105 LSB，DC 为 +45.07/−168.69 LSB。左右是最终混音的一条轨迹；不会出现上游视频的四个独立颜色层。

## 准备与复制

依赖 Python、git、numpy、Pillow、scipy；只生成音频，无需 ffmpeg。默认素材目录为 `/home/sphenicidition/Documents/oscilloscope_tf_assets_20261002`，位于 FPGA 仓库外。

```sh
python3 tools/tf_scope_media/media.py prepare
python3 tools/tf_scope_media/media.py inspect
python3 tools/tf_scope_media/media.py install --dry-run
python3 tools/tf_scope_media/media.py install
```

`prepare` 拒绝仓库内输出路径，要求干净的固定上游提交。输出 `OSCIMUS.WAV`、`OSCILIC.TXT`、`OSCISRC.TXT`；来源记录含 SHA256、采样率、帧数、时长和改动说明。源 WAV 和居中中间文件只在同一个卡外目录。PCM 不进入 HDL 的 `$readmemh`、几何工具或控制事件场景。

`install` 从 `lsblk` 选择已挂载、removable 的 FAT16/FAT32 分区。若候选不唯一，可用 `--mount /run/media/<user>/<card>` 指定现有挂载根目录。它复核 `findmnt` 的真实挂载和写权限、根目录最多 16 个 WAV、空间及素材 SHA256，再原子复制上述三个 8.3 文件并逐字节读回校验。拒绝系统分区、普通目录、只读挂载、exFAT、覆盖内容不同的已有文件和未确认目标；不格式化、不分区、不操作原始块设备。安装收据留在卡外。

卡里有多首 WAV 时，HDL 按 FAT 根目录条目扫描顺序编号，不是文件名排序；从 0 开始。最明确的首测是原本没有 WAV 的 FAT 卡，此时 `OSCIMUS.WAV` 为 track 0。工具保留已有文件，不替用户清卡。

2026-10-02 本机 `lsblk` 只有 NVMe 系统盘和 zram，`inspect` 返回 `[]`，因此本次实际复制尚未执行。接入读卡器并挂载 TF 后可运行 `install`；成功标志为生成 `install_receipt.json` 且三个读回 SHA256 一致。复制完成后先安全卸载，再把 TF 放到 NEO Dock。当前 FPGA 镜像仍需后续 P&R/下载及板测，软件准备不代表模式已在板上运行。

## 使用

完整操作、输入映射和互斥规则见 `../../reports/TF_SCOPE_PLAYBACK_20261002.md`。Push Session 切入 TF 示波器模式，New 暂停/继续，Duplicate 从头播放，Left/Right 切曲。Select 进入现场几何模式。TF 播放不经 P10 效果，李萨如显示采样最终 DAC 引脚，L→X、R→Y。
