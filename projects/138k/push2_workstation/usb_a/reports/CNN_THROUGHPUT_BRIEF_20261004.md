# CNN 吞吐优化交接简报（2026-10-04，写给并行窗口）

当前板载 0x79 主线已验收（选歌→逐窗出谱），节律 **~0.37 帧/s（172 帧约 8 分钟/窗）**。本文档汇总已定位的瓶颈、修复建议与遥测陷阱，供吞吐优化窗口直接开工。

## 瓶颈 #1（最大嫌疑，已代码确认）：每帧从 DDR 重载全部权重

`basic_pitch_pcm_pipeline.sv` 的每帧 FSM 序列中，六个推理头各自经过
`S_PREP_* → S_LOAD_WEIGHT → S_WAIT_WEIGHT`：

| 层 | weight_blob_base | word_count |
|---|---:|---:|
| contour | 0 | 7488 |
| reduce | 7488 | 200 |
| notes | 7688 | 1568 |
| note_out | 9256 | 672 |
| onset | 9928 | 6400 |
| **合计** | | **16328 词 = 32.7 KB/帧** |

`basic_pitch_weight_cache.sv` 名为 cache 实为**单层流式缓冲**（MAX_WORDS=7488，8 块
BSRAM），每次 S_LOAD_WEIGHT 都逐 16 位词经共享仲裁器从 DDR 模型区重读。逐帧 × 172 帧
× 每窗，等于每窗 ~5.6 MB 的重复 DDR 读。

**建议修复**：把缓存扩为全层驻留（16328 词 ≈ 261 Kb ≈ +8 块 BSRAM，279→287 可接受），
首帧加载后各 S_PREP_* 直接命中缓存跳过 S_LOAD_WEIGHT。预期消掉每帧大部分时间。
改动集中在 `basic_pitch_weight_cache.sv`（容量+命中逻辑）与管线的 S_PREP_*/S_LOAD_WEIGHT
分支（加"已驻留"旁路）。

## 瓶颈 #2（待测量）：CQT 系数同样逐帧走 DDR

`USE_DDR_FRONT_COEFF=1` 时前端系数经 `basic_pitch_ddr_coeff_pair` 每帧从 DDR 读
（resampler_poly 147×44 对 + CQT 复系数表）。扩缓存方案 B 同理可驻留。

## 先测量再动刀的建议

在 `debug_progress_o`（B138 NN 字高 16 位）里加**每状态驻留周期计数器**（比如
S_LOAD_WEIGHT/S_CQT/S_REDUCE 等的累计毫秒数，轮换输出），一次上板就能把 2.7 s/帧
在"权重重载 / CQT / NN 推理"之间的分配量出来，避免盲改。

## 遥测解码陷阱（本窗口踩过的坑，勿重蹈）

- B138 四字 = BP/TF/NN/SD。NN 字 = `{debug_progress[15:0], rate[15:0]}`：
  **FSM state = (nn>>26)&0x3f**（(nn>>10) 读到的是采样率！43=44100、46=48000），
  nn_status=(nn>>22)&0xf；`stream_wave=(bp>>20)&0x1ff`（帧计数）；score_count=sd[31:24]；
  TF 字 trace=(tf>>5)&0x7ff（fs/card/busy/allow/scan/lost），seen_pcm=bit4。
- Viterbi 回溯特性：曲谱项在整窗（172 帧）完成后一次性吐出，窗口中段 count=0 是正常。
- BSRAM 口径：SYN"块当量"与 P&R"原语数"不可互减，见 `reports/WORKSTATION_BSRAM_AUDIT_20261004.md` 的单口径账本。
- vendor SPI 文件（tf_spi_session/tf_sd_spi_sector_reader）0x79 已把 token 窗扩到
  166ms——**不要回退**，否则 abort 风暴复发。
- 看门狗（4s/5s）、歌单保持（10s）、原地恢复（9.6s）是主线安全网，动 DDR/仲裁器时保持。

## 并行窗口协调约定

- 两窗口都会改 RTL 并构建：**烧板前互相打招呼**，构建基线一律从
  `usb_a/results/song_guide_full79_20261004_204059/Prj1` 暂存树复制（参照
  `tools/build_full_song_79.py` 的模式），UserCode 递增避免踩版本。
- 构建约 55 分钟；资源类验证可先用 `python3 sim/tf_audio/run.py`（分钟级）+
  `tools/workstation_memory.py`（SYN+P&R 双口径）。
- 回归底线：`sim/tf_audio/run.py` 16 项 + `sim/guidance/tb_playlist_hold`、
  `tb_tf_hotplug_probe` 必须保持绿。
