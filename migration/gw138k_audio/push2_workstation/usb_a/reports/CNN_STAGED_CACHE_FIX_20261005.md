# CNN 吞吐优化：分级缓存修复（0x81 测量镜像 + 0x82 修复镜像）— 2026-10-05

接手 `CNN_THROUGHPUT_BRIEF_20261004.md` 的吞吐窗口。本文档记录：简报的修正、测量方法与
数据、修复方案、0x82 资源/时序、验收协议。

## 简报的两处修正（已代码确认）

1. **瓶颈机制修正**：板级实例化（`basic_pitch_workstation_link.sv`）一直是
   `USE_ALL_DDR(1'b1)`，此时 `basic_pitch_weight_cache` **根本未被实例化**，简报描述的
   `S_PREP_* → S_LOAD_WEIGHT → S_WAIT_WEIGHT` 权重重载路径不在板上生效。真实的每帧权重
   访问发生在 **`basic_pitch_nn_ddr` 的逐 MAC 取数**：每个 MAC 依次发起 1 次权重 + 1 次激活
   的 16 位 DDR 事务（`basic_pitch_ddr16_port` 一次 256-bit BL8 burst 只用其中 1 个半字），
   两次完整往返（CDC FIFO + 命令缓冲 + 仲裁器 + DDR3 + 回程）串行结束才出一个 MAC。
   `basic_pitch_weight_cache` 名为 cache 的单层流式缓冲是 `USE_EXTERNAL_WEIGHTS` 分支的。
2. **词数修正**：六个头合计 **16625 词**（简报的 16328 漏了 onset_out 的 297 词），但这在
   实际配置下无关紧要——逐 MAC 取数才是主导。

## 测量（先测量再动手）

**解析闭合**（3.3.x 型逐层核算，流式一窗 172 帧、每帧每层 1 输出行）：

| 层 | 输出/帧 | MAC/输出 | MAC/帧 |
|---|---:|---:|---:|
| contour 3×39×8→264×8 | 2112 | 936 | 1.977M |
| reduce 5×5×8→264 | 264 | 200 | 52.8K |
| notes 7×7→88×32 (sf3) | 2816 | 49 | 138K |
| note_out 7×3×32→88 | 88 | 672 | 59.1K |
| onset 5×5×8→88×32 (sf3) | 2816 | 200 | 563K |
| onset_out 3×3×33→88 | 88 | 297 | 26.1K |
| **合计** | | | **2.82M MAC/帧** |

每 MAC 2 次 DDR 事务 ≈ 5.6M 事务/帧；实测 0.37 帧/s = 2.7 s/帧 = 135M 周期 @50MHz
→ **~24 周期/事务**，与 CDC+命令缓冲+仲裁器+DDR3 往返量级吻合，模型闭合。
CQT/NormLog 每窗只跑一次（S_CQT/S_NORM 在帧循环前），不参与每帧节律。

**板上遥测（0x81 测量镜像）**：`basic_pitch_pcm_pipeline` 加 8 档每状态驻留周期计数器
（25M 周期窗 = 报告 tick 0.5s，锁存轮换），经 B138 NN 字低 16 位输出
`{page[1:0], cycles[24:11]}`（替换与 TF 字冗余的 sample_rate 半字；`debug_progress`
与 FSM 状态解码不变）。解码：`state=(nn>>26)&0x3f`，`page=(nn>>14)&3`，
`cycles=(nn&0x3fff)*2048`。host 工具 `tools/capture_bp_dwell.py`。

0x81 烧板记录 `results/sram_20261005_143650_689021`，模型上传 9s 状态 E，
遥测解码冒烟通过（state=0 CAPTURE、页轮换正常）。**基线驻留分布采集未能完成**：
40 分钟采集窗口内无人选歌（全空转数据已弃）。瓶颈排序最终由解析闭合 + 修复后遥测
分布位移双重确认（见下）。

## 修复：分级缓存（0x82）

**方案**：`USE_ALL_DDR 1→0`、`USE_EXTERNAL_WEIGHTS/FEATURES 1`——启用既有的分级缓存
路径（代码在树内但 0x4D 以来未上板）：

- 权重：每帧每层经 `S_LOAD_WEIGHT` 流入 8 块 BSRAM 的 weight cache，卷积期间 BSRAM
  直读（S_REQ/S_IC 2 周期/MAC）；
- 激活：`feature_ddr` 写穿（contour/notes/onset）+ 消费前按时间依赖窗加载行窗
  （7×88×32 共享缓存）；CQT 平面经 `plane_cache`（5 行）每帧填充；
- notes 层输入走 `reduce_mem` 行环；DP 进料读 note_post/onset_post BSRAM 环；
- CQT 信号/系数、前端系数、NormLog 平面、Viterbi DP 历史全部保持 DDR（新增
  `USE_DDR_SIGNAL` 参数与 `USE_ALL_DDR` 解耦）；
- `g_ddr_weights` 分支的分布式 ROM loader 换成 `basic_pitch_uart_model_loader`
  （BPN1+CRC 回读校验，52,239 词，与板上模型上传流程一致）。

改动集中在 `rtl/music/basic_pitch_pcm_pipeline.sv`（参数、u_cqt、g_ddr_weights 的
loader）与 `basic_pitch_workstation_link.sv`（实例化参数），冻结文件零接触。
构建脚本 `tools/build_full_song_82_bp_staged_cache.py`（基线 full81 暂存树，
哈希断言 + user_code 00000082）。

**预期**：~0.15 s/帧（计算 2.82M MAC × 2cy ≈ 5.6M cy 主导 + 权重/特征装载数十万 cy）
vs 基线 2.7 s/帧，≈18×。

## 0x82 资源与时序

- P&R BSRAM **260/340**（0x80/0x81 为 215；实际净增 45）。2026-10-06 按
  full81/full82 综合层级资源表复核：feature_ddr +32、weight_cache +8、plane_cache +2、
  basic_pitch 管线内部缓冲 +3。Viterbi 两版均为 6 块，不能计入增量。
  full83 保持 260 块；低于 0x79 的 279，芯片还剩 80 块。
- 时序未闭合，但与 0x80 同类：audio_76m8 最差路径仍是 engine final_accumulator→
  quantized_mix（-3.49ns vs 0x80 -3.23ns）与 delay FIFO Gray（-4576ns TNS vs 0x80
  -2419ns，布线压力加深）；ddr_ui100 仍为 CDC Gray 悲观类；clk_50m TNS -435ns/298
  端点（0x80 -186/126）。新增 50MHz CNN 读路径无独立报告节，正确性由板上层哈希
  位精确校验兜底。
- 烧板 `results/sram_20261005_154809_815290` 三段校验过，模型上传 9s 状态 E，
  遥测正常（NN 字 0x00004000 = CAPTURE/页1/零驻留）。

## 验收协议（TRAVLER，48kHz）

1. **帧速率**：B138 `stream_wave`（bp[28:20]）斜率 vs 0.37 帧/s 基线；
2. **出谱正确性**：首窗完成 `score_count`（sd[31:24]）= **36**（0x79 基线，次窗 +33），
   记录首末音符（sd[23:17]/sd[16:10]）；
3. **层哈希**：result_valid 期间 6 页哈希页（0x82 新参考值，供后续回归）；
4. **驻留分布位移**：修复后页 2-5（CNN 各层）应大幅缩水，P0/P1（CQT/NORM，每窗一次）
   占比相对上升。

## 回归底线（2026-10-06 复核）

- `sim/tf_audio/run.py` **16/16 PASS**（`out/tf_audio_20261006_161840_743237`）；
- `sim/guidance/tb_playlist_hold` PASS、`sim/guidance/tb_tf_hotplug_probe` PASS
  （0x80 时段的 vendor SPI token 窗 166ms 修复未触碰）。
  本窗口改动（basic_pitch 管线/link 参数）不被这些 TB 实例化，结果与预期一致。

## 状态与遗留

- 0x81/0x82 镜像、构建脚本、遥测工具均已提交；`LATEST_WORKSTATION.json` 已更新。
- 基线（0x81）驻留分布未采到（无人选歌）；如需完整前后对比，0x81 比特流在
  `results/song_guide_full81_20261005_133345`，可回烧 + 上传模型 + 选歌复采。
- TRAVLER 全曲约 90 窗；修复后每窗 ~30-60s 量级，整曲扫描从 ~12 小时降到
  ~1 小时以内（待实测）。
- 计算成为新瓶颈后，下一步吞吐空间在 conv2d 展开度（现 1 MAC/2cy）与
  weight cache 双端口化，属独立任务。
